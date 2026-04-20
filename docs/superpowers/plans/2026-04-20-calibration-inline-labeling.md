# Calibration Inline Labeling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an in-browser labeling UI to the Paper/ webui so the single rater can annotate `responses_n*.csv` files (`hard_refusal` / `soft_refusal` / `on_task`) with keyboard shortcuts + confirmatory reveal instead of round-tripping through Excel.

**Architecture:** Thin FastAPI layer (`labeling.py`) with 3 endpoints (load / set / clear) that rewrites the target CSV in-place with an `os.path.getmtime` optimistic lock. Alpine.js modal in `index.html` renders a hybrid focus-mode + mini-list UI; label buttons call `/api/labeling/set`, reveal expected label post-commit, auto-advance on consistent rows and pause on inconsistent ones.

**Tech Stack:** FastAPI + pydantic (existing), Alpine.js (existing CDN), csv stdlib (utf-8-sig for BOM), pytest + FastAPI TestClient.

**Spec:** `docs/superpowers/specs/2026-04-20-calibration-inline-labeling-design.md`

---

## File Structure

**New**
- `Paper/src/ctw_va/webui/labeling.py` — FastAPI router + CSV read/write helpers (~160 lines)
- `Paper/tests/test_webui_labeling.py` — endpoint tests (~180 lines)

**Modified**
- `Paper/src/ctw_va/webui/app.py` — import and mount the labeling router
- `Paper/src/ctw_va/webui/static/index.html` — preview-header button + modal Alpine component

---

## Task 1: CSV I/O helpers (pure functions)

**Files:**
- Create: `Paper/src/ctw_va/webui/labeling.py`
- Test: `Paper/tests/test_webui_labeling.py`

Pure functions first; routing wires on top in Task 2-4.

- [ ] **Step 1: Write the failing test for `_read_csv_rows`**

```python
# Paper/tests/test_webui_labeling.py
import csv
from pathlib import Path

import pytest

from ctw_va.webui import labeling


CSV_HEADERS = [
    "prompt_id", "vendor", "prompt_text", "response_text",
    "label", "expected", "topic", "status", "model_id",
    "cost_usd", "latency_ms", "tokens_in", "tokens_out",
    "error_detail",
]


def _make_csv(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "responses_n3.csv"
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**{k: "" for k in CSV_HEADERS}, **r})
    return p


def test_read_csv_rows_parses_bom_and_returns_progress(tmp_path):
    csv_path = _make_csv(tmp_path, [
        {"prompt_id": "HR01", "vendor": "deepseek", "label": "hard_refusal",
         "expected": "hard_refusal_expected", "status": "ok"},
        {"prompt_id": "HR02", "vendor": "deepseek", "label": "",
         "expected": "hard_refusal_expected", "status": "ok"},
        {"prompt_id": "OT01", "vendor": "deepseek", "label": "",
         "expected": "on_task_expected", "status": "error",
         "error_detail": "timeout"},
    ])

    result = labeling._read_csv_rows(csv_path)

    assert len(result["rows"]) == 3
    assert result["rows"][0]["prompt_id"] == "HR01"
    assert result["rows"][0]["label"] == "hard_refusal"
    assert result["progress"] == {
        "total": 3, "labeled": 1, "unlabeled": 2, "inconsistent": 0,
    }
    assert result["file_mtime"] == pytest.approx(csv_path.stat().st_mtime)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd Paper && .venv/bin/pytest tests/test_webui_labeling.py::test_read_csv_rows_parses_bom_and_returns_progress -v`
Expected: FAIL — `AttributeError: module 'ctw_va.webui.labeling' has no attribute '_read_csv_rows'`

- [ ] **Step 3: Implement `labeling.py` module skeleton + `_read_csv_rows`**

```python
# Paper/src/ctw_va/webui/labeling.py
"""In-browser labeling for calibration CSVs.

See docs/superpowers/specs/2026-04-20-calibration-inline-labeling-design.md
for the full design. This module exposes three FastAPI endpoints on a router
that `app.py` mounts at application startup.
"""
from __future__ import annotations

import csv
import os
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..refusal.csv_io import CSV_COLUMNS
from ..refusal.prompts import VALID_LABELS


# Files we are allowed to write via this router. The generic whitelist
# (`experiments/ runs/ data/`) still applies — this regex is an extra
# safety net that rejects arbitrary CSVs within those roots.
_LABELING_FILENAME_RE = re.compile(r"^responses_n\d+(_\w+)?\.csv$")


def _read_csv_rows(path: Path) -> dict:
    """Parse the CSV and return rows + progress + current mtime."""
    rows: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if "label" not in (reader.fieldnames or []):
            raise HTTPException(400, "CSV is missing `label` column")
        for row in reader:
            # Normalise every expected column to string (DictReader can miss
            # columns if a row is short; we want stable shape for the UI).
            rows.append({k: (row.get(k) or "") for k in CSV_COLUMNS})

    labeled = sum(1 for r in rows if r["label"])
    inconsistent = sum(
        1 for r in rows
        if r["label"] and not _is_consistent(r["label"], r["expected"])
    )
    return {
        "rows": rows,
        "file_mtime": path.stat().st_mtime,
        "progress": {
            "total": len(rows),
            "labeled": labeled,
            "unlabeled": len(rows) - labeled,
            "inconsistent": inconsistent,
        },
    }


def _is_consistent(label: str, expected: str) -> bool:
    """Map e.g. ``hard_refusal`` == ``hard_refusal_expected``."""
    if not label or not expected:
        return True  # nothing to compare against yet
    return expected == f"{label}_expected"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd Paper && .venv/bin/pytest tests/test_webui_labeling.py::test_read_csv_rows_parses_bom_and_returns_progress -v`
Expected: PASS

- [ ] **Step 5: Write failing test for `_write_label`**

Append to `tests/test_webui_labeling.py`:

```python
def test_write_label_updates_in_place_preserving_bom(tmp_path):
    csv_path = _make_csv(tmp_path, [
        {"prompt_id": "HR01", "vendor": "deepseek", "label": "",
         "expected": "hard_refusal_expected", "prompt_text": "一個問題",
         "response_text": "一個含逗號, 的回應"},
        {"prompt_id": "HR02", "vendor": "openai", "label": "",
         "expected": "hard_refusal_expected"},
    ])
    original_bytes = csv_path.read_bytes()
    assert original_bytes.startswith(b"\xef\xbb\xbf"), "precondition: BOM present"

    new_mtime = labeling._write_label(
        csv_path, prompt_id="HR01", vendor="deepseek", label="hard_refusal",
    )

    assert new_mtime > 0
    new_bytes = csv_path.read_bytes()
    assert new_bytes.startswith(b"\xef\xbb\xbf"), "BOM preserved"

    # Re-read through csv to verify field-level correctness.
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["label"] == "hard_refusal"
    assert rows[0]["response_text"] == "一個含逗號, 的回應"
    assert rows[1]["label"] == ""  # untouched


def test_write_label_unknown_row_raises_400(tmp_path):
    csv_path = _make_csv(tmp_path, [
        {"prompt_id": "HR01", "vendor": "deepseek", "label": ""},
    ])
    with pytest.raises(HTTPException) as exc:
        labeling._write_label(
            csv_path, prompt_id="HR99", vendor="deepseek", label="hard_refusal",
        )
    assert exc.value.status_code == 400
```

Add `from fastapi import HTTPException` to the test imports.

- [ ] **Step 6: Run tests — expect the two new ones to fail**

Run: `cd Paper && .venv/bin/pytest tests/test_webui_labeling.py -v`
Expected: 2 FAIL (`_write_label` not defined)

- [ ] **Step 7: Implement `_write_label`**

Append to `labeling.py`:

```python
def _write_label(
    path: Path, *, prompt_id: str, vendor: str, label: str,
) -> float:
    """Rewrite the CSV with ``label`` updated for the matching row.

    ``label`` may be an empty string (clear). Returns the new mtime.
    """
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = list(reader.fieldnames or [])
        rows = list(reader)

    matched = False
    for r in rows:
        if r.get("prompt_id") == prompt_id and r.get("vendor") == vendor:
            r["label"] = label
            matched = True
            break
    if not matched:
        raise HTTPException(400, f"row not found: {prompt_id}×{vendor}")

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    return path.stat().st_mtime
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd Paper && .venv/bin/pytest tests/test_webui_labeling.py -v`
Expected: 3 PASS

- [ ] **Step 9: Commit**

```bash
cd /Volumes/AI02/Civatas-TW
git add Paper/src/ctw_va/webui/labeling.py Paper/tests/test_webui_labeling.py
git commit -m "[CTW-VA-2026] labeling: CSV I/O helpers (read + write) with tests"
```

---

## Task 2: `GET /api/labeling/load` endpoint

**Files:**
- Modify: `Paper/src/ctw_va/webui/labeling.py` (add router + endpoint)
- Modify: `Paper/src/ctw_va/webui/app.py` (mount router — deferred until Task 5 is wired in; for now we test via `TestClient(APIRouter)` through a mini app)

Because the path-safety helper lives in `app.py` (`_resolve_safe`) and depends on `PAPER_ROOT`, we keep the router stand-alone but inject a `path_resolver` callable so the router is testable without mounting.

- [ ] **Step 1: Write failing test for `/api/labeling/load`**

Append to `tests/test_webui_labeling.py`:

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_test_app(csv_path: Path) -> TestClient:
    """Build a FastAPI app that mounts labeling.router with a fake resolver
    that always returns ``csv_path`` (bypasses the real whitelist so tests
    don't need to touch PAPER_ROOT)."""
    app = FastAPI()
    labeling.configure(path_resolver=lambda rel: csv_path)
    app.include_router(labeling.router)
    return TestClient(app)


def test_load_returns_rows_and_progress(tmp_path):
    csv_path = _make_csv(tmp_path, [
        {"prompt_id": "HR01", "vendor": "deepseek", "label": "hard_refusal",
         "expected": "hard_refusal_expected", "status": "ok"},
        {"prompt_id": "HR02", "vendor": "deepseek", "label": "",
         "expected": "hard_refusal_expected", "status": "ok"},
    ])
    client = _make_test_app(csv_path)

    r = client.get("/api/labeling/load", params={"path": "fake/path.csv"})
    assert r.status_code == 200
    body = r.json()
    assert body["progress"]["total"] == 2
    assert body["progress"]["labeled"] == 1
    assert len(body["rows"]) == 2
    assert body["file_mtime"] > 0


def test_load_rejects_missing_label_column(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("\ufeffprompt_id,vendor\nHR01,deepseek\n", encoding="utf-8")
    client = _make_test_app(p)

    r = client.get("/api/labeling/load", params={"path": "fake/path.csv"})
    assert r.status_code == 400
    assert "label" in r.json()["detail"]
```

- [ ] **Step 2: Run tests — expect the two new ones to fail**

Run: `cd Paper && .venv/bin/pytest tests/test_webui_labeling.py -v`
Expected: 2 FAIL (`labeling.configure` / `labeling.router` not defined)

- [ ] **Step 3: Add router + `configure` + `load` endpoint**

Append to `labeling.py` (after the helpers, before any `if __name__`):

```python
router = APIRouter(prefix="/api/labeling")


# The resolver maps a user-supplied relative path to a safe absolute
# ``Path``. Production wiring (`app.py`) passes in the existing
# ``_resolve_safe`` which enforces the whitelist. Tests can inject a stub.
_path_resolver = None


def configure(*, path_resolver) -> None:
    """Inject a path-resolving callable (rel_path -> Path). Called from
    ``app.py`` at module import time."""
    global _path_resolver
    _path_resolver = path_resolver


def _resolve(rel_path: str) -> Path:
    if _path_resolver is None:
        raise HTTPException(500, "labeling router not configured")
    resolved: Path = _path_resolver(rel_path)
    if not _LABELING_FILENAME_RE.match(resolved.name):
        raise HTTPException(
            400, f"filename must match responses_n*.csv (got {resolved.name})"
        )
    return resolved


@router.get("/load")
def load_csv(path: str) -> dict:
    full = _resolve(path)
    data = _read_csv_rows(full)
    return {"path": path, **data}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd Paper && .venv/bin/pytest tests/test_webui_labeling.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add Paper/src/ctw_va/webui/labeling.py Paper/tests/test_webui_labeling.py
git commit -m "[CTW-VA-2026] labeling: GET /api/labeling/load endpoint"
```

---

## Task 3: `POST /api/labeling/set` endpoint with optimistic lock

**Files:**
- Modify: `Paper/src/ctw_va/webui/labeling.py`
- Modify: `Paper/tests/test_webui_labeling.py`

- [ ] **Step 1: Write failing test for happy-path `set`**

Append to `tests/test_webui_labeling.py`:

```python
def test_set_writes_label_and_returns_new_mtime(tmp_path):
    csv_path = _make_csv(tmp_path, [
        {"prompt_id": "HR01", "vendor": "deepseek", "label": "",
         "expected": "hard_refusal_expected"},
    ])
    client = _make_test_app(csv_path)
    load = client.get("/api/labeling/load", params={"path": "x.csv"}).json()

    # The mtime filesystem resolution is seconds on many macOS volumes;
    # sleep a touch so write actually bumps the stamp.
    import time; time.sleep(0.01)

    r = client.post("/api/labeling/set", json={
        "path": "x.csv",
        "prompt_id": "HR01",
        "vendor": "deepseek",
        "label": "hard_refusal",
        "expected_file_mtime": load["file_mtime"],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["new_mtime"] >= load["file_mtime"]

    # Verify on-disk CSV content actually changed.
    import csv as _csv
    with csv_path.open(encoding="utf-8-sig") as f:
        rows = list(_csv.DictReader(f))
    assert rows[0]["label"] == "hard_refusal"


def test_set_stale_mtime_returns_ok_false(tmp_path):
    csv_path = _make_csv(tmp_path, [
        {"prompt_id": "HR01", "vendor": "deepseek", "label": "",
         "expected": "hard_refusal_expected"},
    ])
    client = _make_test_app(csv_path)

    r = client.post("/api/labeling/set", json={
        "path": "x.csv", "prompt_id": "HR01", "vendor": "deepseek",
        "label": "hard_refusal",
        "expected_file_mtime": 1.0,  # a long time ago
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["reason"] == "file_modified_externally"
    # Verify on-disk CSV was NOT changed.
    import csv as _csv
    with csv_path.open(encoding="utf-8-sig") as f:
        rows = list(_csv.DictReader(f))
    assert rows[0]["label"] == ""


def test_set_invalid_label_returns_400(tmp_path):
    csv_path = _make_csv(tmp_path, [
        {"prompt_id": "HR01", "vendor": "deepseek", "label": ""},
    ])
    client = _make_test_app(csv_path)
    load = client.get("/api/labeling/load", params={"path": "x.csv"}).json()

    r = client.post("/api/labeling/set", json={
        "path": "x.csv", "prompt_id": "HR01", "vendor": "deepseek",
        "label": "totally_bogus",
        "expected_file_mtime": load["file_mtime"],
    })
    assert r.status_code == 400
```

- [ ] **Step 2: Run — expect 3 new failures**

Run: `cd Paper && .venv/bin/pytest tests/test_webui_labeling.py -v`
Expected: 3 FAIL (`/api/labeling/set` not registered)

- [ ] **Step 3: Add `SetLabelRequest` model + endpoint**

Append to `labeling.py`:

```python
# Allowed mtime drift when comparing the client's stamp to the current
# on-disk stamp. Filesystem resolution varies (APFS ≈ 1 ns, HFS+ ≈ 1 s);
# a small tolerance avoids spurious conflict reports after a write in the
# same second.
_MTIME_TOLERANCE_SEC = 0.001


class SetLabelRequest(BaseModel):
    path: str
    prompt_id: str
    vendor: str
    label: str
    expected_file_mtime: float


@router.post("/set")
def set_label(req: SetLabelRequest) -> dict:
    if req.label not in VALID_LABELS:
        raise HTTPException(
            400, f"label must be one of {VALID_LABELS} (got {req.label!r})"
        )
    full = _resolve(req.path)
    current_mtime = full.stat().st_mtime
    if abs(current_mtime - req.expected_file_mtime) > _MTIME_TOLERANCE_SEC:
        return {
            "ok": False,
            "reason": "file_modified_externally",
            "new_mtime": current_mtime,
        }
    new_mtime = _write_label(
        full, prompt_id=req.prompt_id, vendor=req.vendor, label=req.label,
    )
    return {"ok": True, "new_mtime": new_mtime}
```

- [ ] **Step 4: Run tests — expect all pass**

Run: `cd Paper && .venv/bin/pytest tests/test_webui_labeling.py -v`
Expected: 8 PASS

- [ ] **Step 5: Commit**

```bash
git add Paper/src/ctw_va/webui/labeling.py Paper/tests/test_webui_labeling.py
git commit -m "[CTW-VA-2026] labeling: POST /api/labeling/set with optimistic lock"
```

---

## Task 4: `POST /api/labeling/clear` endpoint

**Files:**
- Modify: `Paper/src/ctw_va/webui/labeling.py`
- Modify: `Paper/tests/test_webui_labeling.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_webui_labeling.py`:

```python
def test_clear_empties_label(tmp_path):
    csv_path = _make_csv(tmp_path, [
        {"prompt_id": "HR01", "vendor": "deepseek",
         "label": "hard_refusal",
         "expected": "hard_refusal_expected"},
    ])
    client = _make_test_app(csv_path)
    load = client.get("/api/labeling/load", params={"path": "x.csv"}).json()

    r = client.post("/api/labeling/clear", json={
        "path": "x.csv", "prompt_id": "HR01", "vendor": "deepseek",
        "expected_file_mtime": load["file_mtime"],
    })
    assert r.status_code == 200
    assert r.json()["ok"] is True

    import csv as _csv
    with csv_path.open(encoding="utf-8-sig") as f:
        rows = list(_csv.DictReader(f))
    assert rows[0]["label"] == ""
```

- [ ] **Step 2: Run — expect failure**

Run: `cd Paper && .venv/bin/pytest tests/test_webui_labeling.py::test_clear_empties_label -v`
Expected: FAIL (`/api/labeling/clear` not registered)

- [ ] **Step 3: Implement `ClearLabelRequest` + endpoint**

Append to `labeling.py`:

```python
class ClearLabelRequest(BaseModel):
    path: str
    prompt_id: str
    vendor: str
    expected_file_mtime: float


@router.post("/clear")
def clear_label(req: ClearLabelRequest) -> dict:
    full = _resolve(req.path)
    current_mtime = full.stat().st_mtime
    if abs(current_mtime - req.expected_file_mtime) > _MTIME_TOLERANCE_SEC:
        return {
            "ok": False,
            "reason": "file_modified_externally",
            "new_mtime": current_mtime,
        }
    new_mtime = _write_label(
        full, prompt_id=req.prompt_id, vendor=req.vendor, label="",
    )
    return {"ok": True, "new_mtime": new_mtime}
```

- [ ] **Step 4: Run tests — all pass**

Run: `cd Paper && .venv/bin/pytest tests/test_webui_labeling.py -v`
Expected: 9 PASS

- [ ] **Step 5: Commit**

```bash
git add Paper/src/ctw_va/webui/labeling.py Paper/tests/test_webui_labeling.py
git commit -m "[CTW-VA-2026] labeling: POST /api/labeling/clear endpoint"
```

---

## Task 5: Wire router into `app.py`

**Files:**
- Modify: `Paper/src/ctw_va/webui/app.py`

- [ ] **Step 1: Add import + configure at module load**

Edit `Paper/src/ctw_va/webui/app.py`. Find the existing import block (lines 15-18):

```python
from . import jobs as jobs_mod
from . import spec as spec_mod
from . import status as status_mod
from ..adapter.clients import register_default_clients
```

Replace with:

```python
from . import jobs as jobs_mod
from . import labeling as labeling_mod
from . import spec as spec_mod
from . import status as status_mod
from ..adapter.clients import register_default_clients
```

- [ ] **Step 2: Mount the router after `_resolve_safe` is defined**

Find the `/api/path-exists` endpoint (around line 330). Immediately after its `def path_exists(...)` block ends (but before `# -------- Static index --------` around line 345), insert:

```python

# -------- Labeling router (calibration CSV in-browser labeler) --------

labeling_mod.configure(path_resolver=_resolve_safe)
app.include_router(labeling_mod.router)
```

- [ ] **Step 3: Sanity-check the app still boots**

Run: `cd Paper && .venv/bin/python -c "from ctw_va.webui.app import app; print([r.path for r in app.routes if 'labeling' in r.path])"`
Expected output contains:
```
['/api/labeling/load', '/api/labeling/set', '/api/labeling/clear']
```

- [ ] **Step 4: Run the full test suite to make sure nothing regressed**

Run: `cd Paper && .venv/bin/pytest tests/ -v`
Expected: all tests (9 labeling + 70 existing) pass.

- [ ] **Step 5: Commit**

```bash
git add Paper/src/ctw_va/webui/app.py
git commit -m "[CTW-VA-2026] webui: mount labeling router at /api/labeling"
```

---

## Task 6: Frontend — preview-header button

Frontend TDD requires a headless browser stack we don't have; we use a structural-smoke approach (edit → reload → click → inspect). Each task ends with a manual checklist.

**Files:**
- Modify: `Paper/src/ctw_va/webui/static/index.html`

- [ ] **Step 1: Add the button in the preview-actions block**

Open `Paper/src/ctw_va/webui/static/index.html`. Find the preview actions around line 690-695 (look for `📥 下載` and `🔄 重新預覽`):

```html
                  <div class="preview-actions">
                    <a :href="'/api/file?path=' + encodeURIComponent(o.path)"
                       :download="o.path.split('/').pop()"
                       title="下載原始檔">📥 下載</a>
                    <button @click="loadPreview(o.path)" title="重新讀取預覽">🔄 重新預覽</button>
                  </div>
```

Replace with:

```html
                  <div class="preview-actions">
                    <a :href="'/api/file?path=' + encodeURIComponent(o.path)"
                       :download="o.path.split('/').pop()"
                       title="下載原始檔">📥 下載</a>
                    <button @click="loadPreview(o.path)" title="重新讀取預覽">🔄 重新預覽</button>
                    <button x-show="isCalibrationCsv(o.path)"
                            @click="openLabeler(o.path)"
                            class="label-btn"
                            title="在瀏覽器中直接標註這個 CSV">✏️ 進入標註模式</button>
                  </div>
```

- [ ] **Step 2: Add a small style for `.label-btn`**

In `index.html`, locate any existing `.preview-actions button` rule or the top `<style>` block. Add (near other preview-related styles, searchable by `.preview-actions`):

```css
.preview-actions .label-btn {
  background: linear-gradient(180deg, #2d5a3d, #1f4030);
  border: 1px solid #3a7351;
  color: #d6ffec;
}
.preview-actions .label-btn:hover {
  background: linear-gradient(180deg, #367247, #26513a);
}
```

- [ ] **Step 3: Add `isCalibrationCsv` helper on the Alpine component**

Find `function app() {` around line 962. Within the returned object, near other helpers (e.g. `formatCell`, `formatSize`), add:

```js
    isCalibrationCsv(path) {
      if (!path) return false;
      const name = path.split('/').pop() || '';
      return /^responses_n\d+(_\w+)?\.csv$/.test(name);
    },
```

- [ ] **Step 4: Add a placeholder `openLabeler` (full implementation in Task 8)**

Also inside `app()`, add (will be replaced by the real modal launcher in Task 8):

```js
    labelerOpen: false,
    labelerPath: null,
    openLabeler(path) {
      this.labelerPath = path;
      this.labelerOpen = true;
      console.log('[labeler] open', path);  // removed after Task 8
    },
```

- [ ] **Step 5: Manual smoke check**

1. Start the webui: `cd Paper && .venv/bin/civatas-exp webui serve --port 8765`
2. Browser: http://127.0.0.1:8765/
3. Navigate to `calibration / fetch` (or whatever page surfaces the existing
   `responses_n20.csv` preview).
4. Expected: the preview header shows a green `✏️ 進入標註模式` button.
5. Clicking it: browser console logs `[labeler] open experiments/refusal_calibration/responses_n20.csv` (no UI yet — that's Task 7 onwards).

- [ ] **Step 6: Commit**

```bash
git add Paper/src/ctw_va/webui/static/index.html
git commit -m "[CTW-VA-2026] webui: preview-header button to enter labeling mode"
```

---

## Task 7: Frontend — modal skeleton + open/close

**Files:**
- Modify: `Paper/src/ctw_va/webui/static/index.html`

- [ ] **Step 1: Add modal markup inside `<body>` (outside any template loops)**

At the very end of the `<body>` but *before* `</body>`, insert:

```html
<!-- ============= Labeling modal ============= -->
<div class="labeler-modal"
     x-show="labelerOpen"
     x-trap.inert.noscroll="labelerOpen"
     @keydown.escape.window="closeLabeler()"
     @keydown.window="onLabelerKey($event)"
     style="display:none;">
  <div class="labeler-header">
    <button class="labeler-close" @click="closeLabeler()" title="離開 (ESC)">✕</button>
    <span class="labeler-path" x-text="labelerPath || ''"></span>
    <span class="labeler-progress" x-show="labeler.rows.length">
      進度：<span x-text="labeler.progress.labeled"></span> /
              <span x-text="labeler.progress.total"></span>
      已標 (<span x-text="Math.round(100 * labeler.progress.labeled / Math.max(1, labeler.progress.total))"></span>%)
      · 不一致 <span x-text="labeler.progress.inconsistent"></span>
    </span>
    <label class="labeler-toggle">
      <input type="checkbox" x-model="labeler.onlyUnlabeled"> 只看未標
    </label>
  </div>
  <div class="labeler-body">
    <!-- Focus pane + mini list come in Task 8-11. For now just a stub. -->
    <div class="labeler-focus">
      <template x-if="labeler.loading"><div>讀取中…</div></template>
      <template x-if="labeler.error">
        <div style="color:var(--red);" x-text="'錯誤：' + labeler.error"></div>
      </template>
      <template x-if="!labeler.loading && !labeler.error">
        <div>（focus pane — 待 Task 8 實作）</div>
      </template>
    </div>
    <div class="labeler-minilist">（mini list — 待 Task 8 實作）</div>
  </div>
</div>
```

- [ ] **Step 2: Add modal styles in the `<style>` block**

```css
.labeler-modal {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(8, 10, 14, 0.96);
  display: flex; flex-direction: column;
  color: var(--fg);
  font-family: var(--mono);
}
.labeler-header {
  display: flex; align-items: center; gap: 16px;
  padding: 10px 18px; border-bottom: 1px solid #222;
  background: #111;
}
.labeler-close {
  background: #222; border: 1px solid #333; color: #ccc;
  padding: 4px 10px; cursor: pointer; border-radius: 4px;
}
.labeler-path { color: #8cf; font-size: 13px; flex: 0 1 auto; }
.labeler-progress { color: #9a9; font-size: 13px; flex: 1; }
.labeler-toggle { font-size: 13px; color: #bbb; user-select: none; }
.labeler-body {
  flex: 1; display: grid; grid-template-columns: 7fr 3fr;
  min-height: 0;
}
.labeler-focus {
  padding: 24px 32px; overflow-y: auto;
  display: flex; flex-direction: column; gap: 18px;
}
.labeler-minilist {
  padding: 12px; border-left: 1px solid #222;
  overflow-y: auto; background: #0b0d10;
}
```

- [ ] **Step 3: Extend `openLabeler` to actually load data; add `closeLabeler`, `onLabelerKey`, `labeler` state**

Replace the placeholder `openLabeler` + state from Task 6 with a fuller structure. Inside `app()` return:

```js
    labelerOpen: false,
    labelerPath: null,
    labeler: {
      loading: false, error: null,
      rows: [], fileMtime: 0,
      progress: { total: 0, labeled: 0, unlabeled: 0, inconsistent: 0 },
      cursor: 0,
      onlyUnlabeled: false,
      revealFor: null,  // {label, expected, consistent} while chip visible
    },

    async openLabeler(path) {
      this.labelerPath = path;
      this.labelerOpen = true;
      await this.labelerLoad();
    },

    async labelerLoad() {
      this.labeler.loading = true;
      this.labeler.error = null;
      try {
        const r = await fetch('/api/labeling/load?path=' + encodeURIComponent(this.labelerPath));
        if (!r.ok) throw new Error((await r.json()).detail || ('HTTP ' + r.status));
        const data = await r.json();
        this.labeler.rows = data.rows;
        this.labeler.fileMtime = data.file_mtime;
        this.labeler.progress = data.progress;
        // Cursor: first unlabeled if any, else 0.
        const firstUnlabeled = data.rows.findIndex(r => !r.label);
        this.labeler.cursor = firstUnlabeled >= 0 ? firstUnlabeled : 0;
        this.labeler.revealFor = null;
      } catch (e) {
        this.labeler.error = e.message;
      } finally {
        this.labeler.loading = false;
      }
    },

    closeLabeler() {
      this.labelerOpen = false;
      // Refresh file-preview so the header progress / cell styles reflect
      // new labels.
      if (this.labelerPath) this.loadPreview(this.labelerPath);
    },

    onLabelerKey(ev) {
      if (!this.labelerOpen) return;
      // Specific bindings come in Task 10.
    },
```

- [ ] **Step 4: Manual smoke check**

1. Reload the page.
2. Click `✏️ 進入標註模式` on the `responses_n20.csv` preview.
3. Expected: full-screen modal opens, header shows path + progress + toggle,
   body shows «focus pane 待 Task 8» + «mini list 待 Task 8» placeholders.
4. Press ESC → modal closes, underlying page unaffected.

- [ ] **Step 5: Commit**

```bash
git add Paper/src/ctw_va/webui/static/index.html
git commit -m "[CTW-VA-2026] webui: labeling modal skeleton (open/close + load)"
```

---

## Task 8: Frontend — focus pane + mini list rendering + click-to-jump

**Files:**
- Modify: `Paper/src/ctw_va/webui/static/index.html`

- [ ] **Step 1: Replace focus-pane stub with real rendering**

Find the `.labeler-focus` div's inner `<template>` blocks (from Task 7). Replace the entire `.labeler-focus` block content with:

```html
    <div class="labeler-focus">
      <template x-if="labeler.loading"><div>讀取中…</div></template>
      <template x-if="labeler.error">
        <div style="color:var(--red);" x-text="'錯誤：' + labeler.error"></div>
      </template>
      <template x-if="!labeler.loading && !labeler.error && labeler.rows.length && currentRow">
        <div class="lf-inner">
          <div class="lf-meta">
            <span class="lf-pid" x-text="currentRow.prompt_id"></span>
            <span class="lf-vendor" x-text="currentRow.vendor"></span>
            <span class="lf-topic" x-text="'topic: ' + currentRow.topic"></span>
            <template x-if="currentRow.status === 'error'">
              <span class="lf-err" x-text="'⚠ error: ' + (currentRow.error_detail || 'unknown')"></span>
            </template>
          </div>
          <div class="lf-section">
            <div class="lf-heading">── PROMPT ──</div>
            <div class="lf-prompt" x-text="currentRow.prompt_text"></div>
          </div>
          <div class="lf-section">
            <div class="lf-heading">── RESPONSE ──</div>
            <div class="lf-response" x-text="currentRow.response_text || '(空)'"></div>
          </div>
          <div class="lf-buttons">
            <button class="lf-btn hard" @click="labelCurrent('hard_refusal')"
                    :disabled="currentRow.status === 'error'">
              <span class="lf-k">1</span> 硬拒 <small>hard_refusal</small>
            </button>
            <button class="lf-btn soft" @click="labelCurrent('soft_refusal')"
                    :disabled="currentRow.status === 'error'">
              <span class="lf-k">2</span> 軟拒 <small>soft_refusal</small>
            </button>
            <button class="lf-btn ontask" @click="labelCurrent('on_task')"
                    :disabled="currentRow.status === 'error'">
              <span class="lf-k">3</span> 正常 <small>on_task</small>
            </button>
          </div>
          <!-- Confirmatory reveal chip (Task 9). -->
          <template x-if="labeler.revealFor">
            <div :class="'lf-reveal ' + (labeler.revealFor.consistent ? 'ok' : 'warn')">
              <template x-if="labeler.revealFor.consistent">
                <span>✓ 你：<b x-text="labeler.revealFor.label"></b> · 預期：<span x-text="labeler.revealFor.expected"></span></span>
              </template>
              <template x-if="!labeler.revealFor.consistent">
                <div>
                  <span>⚠ 你：<b x-text="labeler.revealFor.label"></b> · 預期：<span x-text="labeler.revealFor.expected"></span></span>
                  <div class="lf-reveal-actions">
                    <button @click="clearCurrent()">撤回 (u)</button>
                    <button @click="advanceCursor(1)">確認並繼續 (→)</button>
                  </div>
                </div>
              </template>
            </div>
          </template>
          <div class="lf-nav">
            <button @click="advanceCursor(-1)" title="上一題 (←)">← Prev</button>
            <button @click="clearCurrent()" title="清除 (u)">U 清除</button>
            <button @click="advanceCursor(1)" title="下一題 (→)">Next →</button>
          </div>
        </div>
      </template>
      <template x-if="!labeler.loading && !labeler.error && labeler.rows.length && !currentRow">
        <!-- Happens when onlyUnlabeled filters all rows away OR all labeled. Completion card in Task 11. -->
        <div>🎉 沒有要標的 row 了</div>
      </template>
    </div>
```

- [ ] **Step 2: Replace mini-list stub**

Replace the `.labeler-minilist` div with:

```html
    <div class="labeler-minilist">
      <template x-for="(r, idx) in visibleRows" :key="r.prompt_id + '@' + r.vendor">
        <div class="ml-row"
             :class="miniRowClass(r, idx)"
             @click="jumpToCursor(r)">
          <span class="ml-glyph" x-text="miniGlyph(r, idx)"></span>
          <span class="ml-pid" x-text="r.prompt_id"></span>
          <span class="ml-vendor" x-text="r.vendor"></span>
        </div>
      </template>
      <template x-if="!visibleRows.length">
        <div class="ml-empty">（沒有符合條件的 row）</div>
      </template>
    </div>
```

- [ ] **Step 3: Add styles for focus pane + mini list**

Append to the existing `<style>` block:

```css
.lf-inner { display: flex; flex-direction: column; gap: 18px; max-width: 900px; }
.lf-meta { display: flex; gap: 12px; font-size: 12px; color: #8af; flex-wrap: wrap; }
.lf-meta .lf-vendor { color: #fc8; }
.lf-meta .lf-topic  { color: #9a9; }
.lf-meta .lf-err    { color: var(--red); }
.lf-heading { color: #777; font-size: 11px; letter-spacing: 0.1em; margin-bottom: 4px; }
.lf-prompt  { font-size: 18px; line-height: 1.55; color: #f0f0f0; }
.lf-response{ font-size: 15px; line-height: 1.6; color: #cfd4da; white-space: pre-wrap;
              background: #10141a; padding: 12px 16px; border-radius: 6px;
              border-left: 3px solid #345; max-height: 40vh; overflow-y: auto; }
.lf-buttons { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.lf-btn { padding: 18px; font-size: 16px; border-radius: 8px; cursor: pointer;
          border: 1px solid #333; background: #181c22; color: #ddd; font-family: var(--mono);
          display: flex; flex-direction: column; gap: 4px; align-items: center; }
.lf-btn:hover:not(:disabled) { background: #20262e; }
.lf-btn:disabled { opacity: 0.35; cursor: not-allowed; }
.lf-btn .lf-k { font-size: 24px; font-weight: bold; color: #ffe680; }
.lf-btn.hard { border-color: #5a2a2a; }
.lf-btn.soft { border-color: #5a4a2a; }
.lf-btn.ontask { border-color: #2a5a3a; }
.lf-btn small { font-size: 11px; color: #8a8a8a; }
.lf-reveal { padding: 10px 14px; border-radius: 6px; font-size: 14px; }
.lf-reveal.ok { background: #143a24; color: #b2f0c4; border: 1px solid #2d5a3a; }
.lf-reveal.warn { background: #3a3014; color: #f0e0a0; border: 1px solid #5a4a2a; }
.lf-reveal-actions { margin-top: 8px; display: flex; gap: 8px; }
.lf-reveal-actions button { background: #222; border: 1px solid #444; color: #ddd; padding: 4px 10px; cursor: pointer; border-radius: 4px; }
.lf-nav { display: flex; gap: 12px; margin-top: 6px; color: #888; font-size: 12px; }
.lf-nav button { background: #181c22; border: 1px solid #333; color: #bbb; padding: 4px 10px; cursor: pointer; border-radius: 4px; }

.ml-row { display: flex; gap: 8px; padding: 4px 8px; font-size: 12px; cursor: pointer; border-radius: 3px; }
.ml-row:hover { background: #141820; }
.ml-row.current { background: #243040; color: #fff; }
.ml-row.labeled { color: #7a9; }
.ml-row.inconsistent { color: #d9b45a; }
.ml-row.unlabeled { color: #888; }
.ml-glyph { font-family: monospace; width: 1em; }
.ml-pid { font-weight: bold; }
.ml-vendor { color: #888; margin-left: auto; }
.ml-empty { color: #666; padding: 8px; }
```

- [ ] **Step 4: Add computed properties + helpers to Alpine component**

Inside `app()`, append to the returned object:

```js
    get currentRow() {
      const rows = this.visibleRows;
      if (!rows.length) return null;
      const cur = this.labeler.rows[this.labeler.cursor];
      if (cur && (!this.labeler.onlyUnlabeled || !cur.label)) return cur;
      // Cursor filtered out — fall back to first visible row.
      return rows[0];
    },

    get visibleRows() {
      if (!this.labeler.onlyUnlabeled) return this.labeler.rows;
      return this.labeler.rows.filter(r => !r.label);
    },

    miniGlyph(row, _idx) {
      if (!row.label) return '☐';
      if (row.expected && row.expected !== (row.label + '_expected')) return '▨';
      return '▉';
    },

    miniRowClass(row, _idx) {
      const cls = [];
      const cur = this.currentRow;
      if (cur && cur.prompt_id === row.prompt_id && cur.vendor === row.vendor) {
        cls.push('current');
      }
      if (!row.label) cls.push('unlabeled');
      else if (row.expected && row.expected !== (row.label + '_expected')) cls.push('inconsistent');
      else cls.push('labeled');
      return cls.join(' ');
    },

    jumpToCursor(row) {
      const idx = this.labeler.rows.findIndex(
        r => r.prompt_id === row.prompt_id && r.vendor === row.vendor
      );
      if (idx >= 0) {
        this.labeler.cursor = idx;
        this.labeler.revealFor = null;
      }
    },

    advanceCursor(delta) {
      // Move within visibleRows; map current visible cursor then shift.
      const rows = this.labeler.rows;
      if (!rows.length) return;
      const visible = this.visibleRows;
      if (!visible.length) return;
      const cur = this.currentRow;
      let vi = visible.findIndex(r => r === cur);
      if (vi < 0) vi = 0;
      const next = Math.max(0, Math.min(visible.length - 1, vi + delta));
      this.jumpToCursor(visible[next]);
    },

    labelCurrent(_label) {
      console.log('labelCurrent stub — real impl in Task 9', _label);
    },

    clearCurrent() {
      console.log('clearCurrent stub — real impl in Task 9');
    },
```

- [ ] **Step 5: Manual smoke check**

1. Reload page, open labeler on `responses_n20.csv`.
2. Expected: focus pane shows HR01 or first row's prompt + response; 3 big
   buttons; mini list on right shows 20 rows with `☐` glyph (if unlabeled)
   and one `▶`-ish current row highlight.
3. Click a different mini-list row → focus pane updates.
4. Toggle `只看未標` → list filters correctly; current row may switch.
5. Buttons log to console (no CSV write yet — that's Task 9).

- [ ] **Step 6: Commit**

```bash
git add Paper/src/ctw_va/webui/static/index.html
git commit -m "[CTW-VA-2026] webui: labeling modal focus pane + mini list"
```

---

## Task 9: Frontend — label-action + confirmatory reveal

**Files:**
- Modify: `Paper/src/ctw_va/webui/static/index.html`

- [ ] **Step 1: Replace `labelCurrent` + `clearCurrent` stubs with real implementations**

Find the two stub methods added in Task 8 and replace them:

```js
    async labelCurrent(label) {
      const row = this.currentRow;
      if (!row) return;
      if (row.status === 'error') return;  // disabled on error rows

      const r = await fetch('/api/labeling/set', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path: this.labelerPath,
          prompt_id: row.prompt_id, vendor: row.vendor,
          label, expected_file_mtime: this.labeler.fileMtime,
        }),
      });

      if (!r.ok) {
        alert('標註失敗：' + (await r.text()));
        return;
      }
      const body = await r.json();
      if (!body.ok) {
        if (body.reason === 'file_modified_externally') {
          if (confirm('檔案被外部修改（Excel / git pull？）— 重新載入？')) {
            await this.labelerLoad();
          }
        } else {
          alert('未知錯誤：' + JSON.stringify(body));
        }
        return;
      }

      // Persist locally.
      row.label = label;
      this.labeler.fileMtime = body.new_mtime;
      this._recomputeProgress();
      const consistent = !row.expected || row.expected === (label + '_expected');
      this.labeler.revealFor = {
        label, expected: row.expected || '(未預期)', consistent,
      };
      if (consistent) {
        setTimeout(() => {
          this.labeler.revealFor = null;
          this.advanceCursor(1);
        }, 300);
      }
    },

    async clearCurrent() {
      const row = this.currentRow;
      if (!row) return;
      const r = await fetch('/api/labeling/clear', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path: this.labelerPath,
          prompt_id: row.prompt_id, vendor: row.vendor,
          expected_file_mtime: this.labeler.fileMtime,
        }),
      });
      if (!r.ok) { alert('清除失敗：' + (await r.text())); return; }
      const body = await r.json();
      if (!body.ok) {
        if (body.reason === 'file_modified_externally') {
          if (confirm('檔案被外部修改 — 重新載入？')) await this.labelerLoad();
        }
        return;
      }
      row.label = '';
      this.labeler.fileMtime = body.new_mtime;
      this.labeler.revealFor = null;
      this._recomputeProgress();
    },

    _recomputeProgress() {
      const rows = this.labeler.rows;
      const labeled = rows.filter(r => r.label).length;
      const inconsistent = rows.filter(
        r => r.label && r.expected && r.expected !== (r.label + '_expected')
      ).length;
      this.labeler.progress = {
        total: rows.length, labeled, inconsistent, unlabeled: rows.length - labeled,
      };
    },
```

- [ ] **Step 2: Manual smoke check**

1. Open labeler on `responses_n20.csv`.
2. Click the `1 硬拒` button on the current row.
3. Expected:
   - Reveal chip appears showing consistency (green if matched, yellow if not).
   - After 300 ms (consistent case) focus advances.
   - On inconsistent case, chip stays until you click `撤回` or `確認並繼續`.
4. Open the CSV in another terminal tab: `.venv/bin/python -c "import csv;print(list(csv.DictReader(open('experiments/refusal_calibration/responses_n20.csv', encoding='utf-8-sig')))[0])"` → label field should be populated.
5. Click `U 清除` → label empties in CSV.

- [ ] **Step 3: Commit**

```bash
git add Paper/src/ctw_va/webui/static/index.html
git commit -m "[CTW-VA-2026] webui: labeling action + confirmatory reveal"
```

---

## Task 10: Frontend — keyboard shortcuts

**Files:**
- Modify: `Paper/src/ctw_va/webui/static/index.html`

- [ ] **Step 1: Fill in `onLabelerKey`**

Replace the existing stub (from Task 7):

```js
    onLabelerKey(ev) {
      if (!this.labelerOpen) return;
      // Avoid intercepting typing inside form controls (none today, but
      // safe guard for future inputs).
      const tgt = ev.target;
      if (tgt && (tgt.tagName === 'INPUT' || tgt.tagName === 'TEXTAREA')) return;

      const k = ev.key;
      if (k === '1') { ev.preventDefault(); this.labelCurrent('hard_refusal'); return; }
      if (k === '2') { ev.preventDefault(); this.labelCurrent('soft_refusal'); return; }
      if (k === '3') { ev.preventDefault(); this.labelCurrent('on_task'); return; }
      if (k === 'u' || k === 'U' || k === 'Backspace') {
        ev.preventDefault(); this.clearCurrent(); return;
      }
      if (k === 'ArrowRight' || k === ' ') {
        ev.preventDefault();
        this.labeler.revealFor = null;
        this.advanceCursor(1);
        return;
      }
      if (k === 'ArrowLeft') {
        ev.preventDefault();
        this.labeler.revealFor = null;
        this.advanceCursor(-1);
        return;
      }
      if (k === 'n' || k === 'N') {
        ev.preventDefault();
        const nextU = this.labeler.rows.findIndex(r => !r.label);
        if (nextU >= 0) {
          this.labeler.cursor = nextU;
          this.labeler.revealFor = null;
        }
        return;
      }
    },
```

- [ ] **Step 2: Manual smoke check**

1. Open labeler, click into the body (so focus is inside the modal).
2. Press `1` / `2` / `3` → labels with reveal chip, advances on consistent.
3. Press `←` / `→` → navigates without labeling.
4. Press `u` or `Backspace` → clears current.
5. Press `n` → jumps to next unlabeled.
6. Press `ESC` → closes modal.

- [ ] **Step 3: Commit**

```bash
git add Paper/src/ctw_va/webui/static/index.html
git commit -m "[CTW-VA-2026] webui: keyboard shortcuts for labeling (1/2/3/u/arrows/n)"
```

---

## Task 11: Frontend — completion card + import-labels trigger

**Files:**
- Modify: `Paper/src/ctw_va/webui/static/index.html`

- [ ] **Step 1: Replace the "🎉 沒有要標的 row 了" placeholder with a real completion card**

Find the `<template x-if="!labeler.loading && !labeler.error && labeler.rows.length && !currentRow">` block in `.labeler-focus`. Replace with:

```html
      <template x-if="!labeler.loading && !labeler.error && labeler.rows.length && !currentRow">
        <div class="lf-done">
          <h2>🎉 全部標註完成</h2>
          <div class="lf-done-counts">
            <div>總計：<b x-text="labeler.progress.total"></b> rows</div>
            <div> · hard_refusal: <b x-text="labelCounts.hard_refusal"></b></div>
            <div> · soft_refusal: <b x-text="labelCounts.soft_refusal"></b></div>
            <div> · on_task: <b x-text="labelCounts.on_task"></b></div>
            <div>與 expected 不一致：<b x-text="labeler.progress.inconsistent"></b> rows</div>
          </div>
          <div class="lf-done-actions">
            <button @click="labeler.onlyUnlabeled = false; gotoInconsistent()"
                    :disabled="!labeler.progress.inconsistent">
              🔁 回列表檢視不一致的 rows
            </button>
            <button @click="runImportLabels()">
              📤 執行 calibration import-labels
            </button>
            <button @click="closeLabeler()">✕ 關閉</button>
          </div>
        </div>
      </template>
```

- [ ] **Step 2: Add `lf-done` styles**

```css
.lf-done { max-width: 640px; }
.lf-done h2 { color: #d6ffec; }
.lf-done-counts { background: #10141a; padding: 12px 16px; border-radius: 6px;
                  display: flex; flex-direction: column; gap: 4px; color: #cfd4da;
                  margin: 12px 0; }
.lf-done-actions { display: flex; gap: 10px; flex-wrap: wrap; }
.lf-done-actions button { background: #1c2630; border: 1px solid #2d5a3a; color: #d6ffec;
                          padding: 10px 16px; border-radius: 6px; cursor: pointer; }
.lf-done-actions button:disabled { opacity: 0.4; cursor: not-allowed; }
```

- [ ] **Step 3: Add `labelCounts` getter + helper methods**

Inside `app()`:

```js
    get labelCounts() {
      const out = { hard_refusal: 0, soft_refusal: 0, on_task: 0 };
      for (const r of this.labeler.rows) {
        if (r.label in out) out[r.label]++;
      }
      return out;
    },

    gotoInconsistent() {
      const idx = this.labeler.rows.findIndex(
        r => r.label && r.expected && r.expected !== (r.label + '_expected')
      );
      if (idx >= 0) this.labeler.cursor = idx;
    },

    async runImportLabels() {
      const csvPath = this.labelerPath;
      const outPath = csvPath.replace(/\.csv$/, '.labeled.jsonl');
      try {
        const r = await fetch('/api/jobs', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            group: 'calibration', subcommand: 'import-labels',
            fields: [
              { flag: '--csv', value: csvPath },
              { flag: '--output', value: outPath },
            ],
            label: 'import-labels (from labeler)',
          }),
        });
        if (!r.ok) throw new Error(await r.text());
        const job = await r.json();
        alert('已派出 job ' + job.id + '，可在右側 job 面板查看 log。');
        this.closeLabeler();
        this.selectedJob = job.id;
      } catch (e) {
        alert('派出 job 失敗：' + e.message);
      }
    },
```

- [ ] **Step 4: Manual smoke check**

1. Label all rows in `responses_n20.csv` (or, faster: in a fresh CSV with 2 rows, label both).
2. Expected: focus pane replaced by completion card with counts.
3. Click `📤 執行 calibration import-labels` → alert shows job id, modal
   closes, job appears in right-side job list with streaming log.
4. The spawned job produces `responses_n20.labeled.jsonl` next to the CSV.

- [ ] **Step 5: Commit**

```bash
git add Paper/src/ctw_va/webui/static/index.html
git commit -m "[CTW-VA-2026] webui: labeling completion card + import-labels trigger"
```

---

## Task 12: End-to-end verification + commit sweep

**Files:**
- No source changes. This task is pure verification.

- [ ] **Step 1: Run the full test suite**

Run: `cd Paper && .venv/bin/pytest tests/ -v`
Expected: all tests green (9 new labeling tests + all existing pass).

- [ ] **Step 2: Manual E2E flow in the browser**

Starting from a clean server:

```bash
cd Paper && .venv/bin/civatas-exp webui serve --port 8765
```

1. Open http://127.0.0.1:8765/
2. Navigate to `calibration/fetch` (existing spec entry).
3. In the preview area for `responses_n20.csv`, click `✏️ 進入標註模式`.
4. Label rows with keyboard `1`/`2`/`3` and mouse; verify:
   - Green chip + auto-advance on consistent.
   - Yellow chip pauses; `撤回`/`確認並繼續` work.
   - `u` / `Backspace` clears the current label.
   - `←` / `→` / `n` navigate as specified.
   - `ESC` closes modal.
   - Mini-list glyph updates (☐ → ▉ or ▨).
   - `只看未標` toggle filters and still lets you navigate.
5. Close the modal mid-session, reopen → cursor lands on first unlabeled.
6. Finish all rows → completion card shows correct counts; click
   `📤 執行 calibration import-labels` → job fires.
7. Confirm CSV on disk has expected `label` values:
   `.venv/bin/python -c "import csv; print([(r['prompt_id'], r['label']) for r in csv.DictReader(open('experiments/refusal_calibration/responses_n20.csv', encoding='utf-8-sig'))])"`

- [ ] **Step 3: Confirm no untracked files were left behind**

```bash
git status
```

Expected: only intentional changes visible; no stray logs or swap files.

- [ ] **Step 4: Push**

```bash
git push
```

- [ ] **Step 5: Update CLAUDE.md Stage-11 blocking chain**

Edit `CLAUDE.md` §11.3 — mark A5 labeling UI as shipped; §11.5 建議明天第一件事 → now just "use webui labeler to annotate".

Commit:

```bash
git add CLAUDE.md
git commit -m "[CTW-VA-2026] Stage 11: note in-browser labeler shipped; A5 unblocked"
git push
```

---

## Self-Review Checklist

- **Spec coverage:** §5.1 entry → Task 6. §5.2 layout → Tasks 7-8. §5.3 shortcuts → Task 10. §5.4 reveal → Task 9. §5.5 edge cases → Tasks 1, 3, 9 (mtime + error rows + missing file). §5.6 completion → Task 11. §6 API → Tasks 2-4. §7 persistence → Task 1. §8 safety → Task 5 (via `_resolve_safe` injection) + filename regex in Task 2. §9 tests → Tasks 1-4. §10 files → covered.
- **Placeholder scan:** No TBD / TODO / "add appropriate error handling" / "similar to Task N" with missing code. All code blocks show exact content.
- **Type consistency:** `_write_label` signature (`path, *, prompt_id, vendor, label`) stable across Tasks 1/3/4. Pydantic models `SetLabelRequest` (Task 3) / `ClearLabelRequest` (Task 4) have matching field names. Alpine `labeler` state shape defined once in Task 7 and only extended (not renamed) in later tasks. `visibleRows`, `currentRow`, `labelCounts` computed getter names are stable. JS method names `labelCurrent` / `clearCurrent` / `advanceCursor` / `jumpToCursor` / `_recomputeProgress` / `runImportLabels` / `gotoInconsistent` defined once each.
