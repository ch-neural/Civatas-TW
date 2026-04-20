"""Refusal classification pipeline.

Loads a pickled sklearn pipeline produced by ``calibration train`` and applies
it to raw vendor responses (from ``vendor_call_log.response_raw`` or from the
labelled calibration JSONL). Returns refusal rates by vendor (× topic, when the
data carries a topic column).
"""
from __future__ import annotations

import json
import pickle
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np


LABELS = ("hard_refusal", "soft_refusal", "on_task")


@dataclass
class RefusalClassifier:
    pipeline: object
    labels: tuple[str, ...]
    train_size: int = 0
    test_accuracy: float | None = None
    test_macro_f1: float | None = None

    @classmethod
    def load(cls, path: str | Path) -> "RefusalClassifier":
        with open(path, "rb") as fh:
            obj = pickle.load(fh)
        if isinstance(obj, dict):
            pipe = obj.get("pipeline") or obj.get("model")
            labels = tuple(obj.get("labels") or LABELS)
            return cls(
                pipeline=pipe, labels=labels,
                train_size=int(obj.get("train_size", 0)),
                test_accuracy=obj.get("test_accuracy"),
                test_macro_f1=obj.get("test_macro_f1"),
            )
        return cls(pipeline=obj, labels=LABELS)

    def predict(self, texts: Iterable[str]) -> list[str]:
        xs = [t or "" for t in texts]
        if not xs:
            return []
        preds = self.pipeline.predict(xs)
        return [str(p) for p in preds]


def _rate_block(counter: Counter, total: int) -> dict:
    if total <= 0:
        return {"total": 0, **{lbl: 0 for lbl in LABELS}, **{f"{lbl}_rate": 0.0 for lbl in LABELS}}
    out: dict = {"total": int(total)}
    for lbl in LABELS:
        n = int(counter.get(lbl, 0))
        out[lbl] = n
        out[f"{lbl}_rate"] = n / total
    # Aggregate refusal rate (hard + soft)
    refusals = int(counter.get("hard_refusal", 0) + counter.get("soft_refusal", 0))
    out["refusal_rate"] = refusals / total
    return out


def classify_rows(
    rows: Iterable[Mapping],
    classifier: RefusalClassifier,
    *,
    text_key: str = "response_text",
    vendor_key: str = "vendor",
    topic_key: str | None = "topic",
) -> dict:
    """Classify each row and aggregate by vendor (× topic if present).

    ``rows`` is any iterable of dicts (calibration JSONL rows, or DB rows
    converted via sqlite3.Row.keys).
    """
    rows_list = list(rows)
    texts = [str(r.get(text_key, "") or "") for r in rows_list]
    preds = classifier.predict(texts) if texts else []

    by_vendor: dict[str, Counter] = {}
    by_vendor_topic: dict[tuple[str, str], Counter] = {}

    for row, pred in zip(rows_list, preds):
        vendor = str(row.get(vendor_key, "unknown"))
        by_vendor.setdefault(vendor, Counter())[pred] += 1
        if topic_key and row.get(topic_key):
            topic = str(row[topic_key])
            by_vendor_topic.setdefault((vendor, topic), Counter())[pred] += 1

    vendor_out: dict[str, dict] = {}
    for vendor, ctr in by_vendor.items():
        vendor_out[vendor] = _rate_block(ctr, sum(ctr.values()))

    topic_out: dict[str, dict[str, dict]] = {}
    for (vendor, topic), ctr in by_vendor_topic.items():
        topic_out.setdefault(vendor, {})[topic] = _rate_block(ctr, sum(ctr.values()))

    return {
        "labels": list(LABELS),
        "n_rows": len(rows_list),
        "by_vendor": vendor_out,
        "by_vendor_topic": topic_out if topic_out else None,
    }


def load_labeled_jsonl(path: str | Path) -> list[dict]:
    """Load the Phase A5 ``labeled_n*.jsonl`` (also works on calibration ``responses_n*.jsonl``)."""
    rows: list[dict] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows
