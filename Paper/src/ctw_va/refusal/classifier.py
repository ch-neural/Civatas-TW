"""Train a small refusal classifier on human-labeled responses.

TF-IDF(char 1-2 gram + word 1-2 gram) → LogisticRegression. Trained on
``response_text`` → ``label``. Keeps the model small (<100 KB) so it ships
in the repo; classifier quality is not the point — the point is having a
reproducible, deterministic refusal detector that the analyze phase can
apply uniformly across all 5 vendors.
"""
from __future__ import annotations

import json
import pickle
from collections import Counter
from pathlib import Path

from .prompts import VALID_LABELS


def _load_labeled(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def train(input_jsonl: str, output_pkl: str, test_ratio: float = 0.2,
          seed: int = 20240113) -> dict:
    """Fit TF-IDF + LR on labeled rows. Returns diagnostics dict."""
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import (
            classification_report, confusion_matrix, accuracy_score, f1_score,
        )
    except ImportError as e:
        raise RuntimeError(
            "scikit-learn 未安裝。請先：pip install 'scikit-learn>=1.3'"
        ) from e

    rows = _load_labeled(input_jsonl)
    if len(rows) < 30:
        raise ValueError(
            f"Only {len(rows)} labeled rows — too few to train. Label at "
            f"least 30 rows across all 3 categories first."
        )

    # Drop rows with unexpected labels (should already be filtered by CSV import,
    # but double-check in case user hand-edited the JSONL).
    rows = [r for r in rows if r.get("label") in VALID_LABELS]

    label_counts = Counter(r["label"] for r in rows)
    if any(label_counts.get(lbl, 0) < 3 for lbl in VALID_LABELS):
        missing = [lbl for lbl in VALID_LABELS if label_counts.get(lbl, 0) < 3]
        raise ValueError(
            f"Class imbalance — each label needs ≥3 examples. "
            f"Too few: {missing} ({dict(label_counts)})"
        )

    X = [r.get("response_text", "") for r in rows]
    y = [r["label"] for r in rows]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_ratio, random_state=seed, stratify=y,
    )

    pipe = Pipeline([
        ("tfidf", TfidfVectorizer(
            analyzer="char_wb", ngram_range=(2, 4),
            min_df=2, max_features=5000,
        )),
        ("clf", LogisticRegression(
            max_iter=500, C=1.0, class_weight="balanced",
            random_state=seed,
        )),
    ])
    pipe.fit(X_train, y_train)

    y_pred = pipe.predict(X_test)
    acc = float(accuracy_score(y_test, y_pred))
    macro_f1 = float(f1_score(y_test, y_pred, average="macro"))
    report_txt = classification_report(
        y_test, y_pred, labels=list(VALID_LABELS), zero_division=0,
    )
    cm = confusion_matrix(y_test, y_pred, labels=list(VALID_LABELS)).tolist()

    Path(output_pkl).parent.mkdir(parents=True, exist_ok=True)
    with open(output_pkl, "wb") as f:
        pickle.dump({
            "pipeline": pipe,
            "labels": list(VALID_LABELS),
            "train_size": len(X_train),
            "test_size": len(X_test),
            "test_accuracy": acc,
            "test_macro_f1": macro_f1,
        }, f)

    print(
        f"\nTrained on {len(X_train)} rows, tested on {len(X_test)}.\n"
        f"Test accuracy:  {acc:.3f}\n"
        f"Macro-F1:       {macro_f1:.3f}\n\n"
        f"{report_txt}\n"
        f"Confusion matrix (rows = true, cols = pred, labels = {list(VALID_LABELS)}):\n"
        + "\n".join(str(r) for r in cm)
        + f"\n\n✓ Classifier saved to {output_pkl}",
        flush=True,
    )

    return {
        "train_size": len(X_train),
        "test_size": len(X_test),
        "test_accuracy": acc,
        "test_macro_f1": macro_f1,
        "label_counts": dict(label_counts),
        "confusion_matrix": cm,
        "output": str(output_pkl),
    }


def predict(model_pkl: str, texts: list[str]) -> list[str]:
    """Helper for downstream analyze pipeline."""
    with open(model_pkl, "rb") as f:
        bundle = pickle.load(f)
    return list(bundle["pipeline"].predict(texts))
