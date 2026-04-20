# Calibration Inline Labeling — Design Spec

**Date**: 2026-04-20
**Scope**: `Paper/` (CTW-VA-2026 experiment platform)
**Context**: arXiv-only submission path (see `CLAUDE.md` Stage 11). User
adopts single-rater labeling with κ ≥ 0.6; Excel round-trip workflow to be
replaced by in-browser labeling UI.

## 1. Problem

The Phase A5 refusal calibration pipeline produces a CSV (e.g.
`responses_n20.csv`) with 200–1000 rows whose `label` column is empty. The
existing workflow asks the user to open the CSV in Excel / Numbers, fill
`hard_refusal` / `soft_refusal` / `on_task` in the `label` column, save, and
run `civatas-exp calibration import-labels` to merge back.

For a single rater labeling ~1000 rows (200 prompts × 5 vendors), the Excel
flow is slow (Tab-to-column, manual typing) and offers no reading aids
(response text gets clipped in cells; no visual progress; no keyboard
shortcuts).

## 2. Goals

- Reduce per-row labeling time from ~20 s (Excel) to ~6-10 s (dedicated UI
  with keyboard shortcuts).
- Eliminate the need to quit the browser workflow during labeling.
- Preserve methodological rigor: avoid confirmation bias from the
  `expected` column by hiding it until after the rater commits a label.
- Keep the existing CLI (`import-labels`) as the source of truth for
  downstream training; the UI is purely an editor for the CSV `label`
  column.

## 3. Non-goals

- No second-rater / reviewer / disagreement-resolution UI (κ relaxed to
  ≥ 0.6 means single-rater is acceptable for arXiv).
- No cross-file batch operations (label multiple CSVs at once).
- No search or full-text filter inside the labeling UI.
- No edit history / undo stack beyond one-click clear.
- No auth / multi-user locking (single-user local tool).

## 4. Key Decisions (from brainstorming 2026-04-20)

| Decision | Choice | Rationale |
|---|---|---|
| UX pattern | Hybrid focus mode + mini list | Table alone is slow for 1000 rows; pure focus mode loses overview. Hybrid gets both. |
| Label persistence | In-place CSV write | Single source of truth; `git pull` cross-PC resume; no sidecar drift. |
| `expected` visibility during labeling | Confirmatory reveal (shown only *after* rater commits) | Eliminates confirmation bias; gives paper methodology claim. |
| Mini list filtering | Single "只看未標" toggle | MVP-sufficient; more filters can be added later per YAGNI. |
| Entry point | Button in file preview header (only when path matches `responses_n*.csv`) | Contextual; scales automatically to n=200 output; no nav changes. |

## 5. UX Design

### 5.1 Entry

In the existing file-preview block rendered by `index.html` for calibration
outputs, the header gains a button:

```
┌─── 📥 產出預覽 ───────────────────────────┐
│  responses_n20.csv  ·  20 rows            │
│  [📥 下載]  [✏️ 進入標註模式]             │
├───────────────────────────────────────────┤
│  (existing CSV preview table)             │
└───────────────────────────────────────────┘
```

The `✏️ 進入標註模式` button is shown only when the previewed path matches
`responses_n*.csv` (calibration output). Clicking opens a full-viewport
modal overlay; `ESC` or the `✕` header button closes it. The underlying
preview stays mounted (no URL change, no route).

### 5.2 Focus-mode layout

The modal is split 70% / 30%:

- **Left (focus pane)**: prompt metadata header (`HR34 · deepseek · topic:
  sovereignty`), prompt text (large), response text (scrollable if long),
  three big label buttons with keyboard hints, footer with Prev / Clear /
  Next.
- **Right (mini list)**: one row per CSV row, showing `prompt_id · vendor`
  and a status glyph (▉ labeled / ▨ inconsistent / ☐ unlabeled / ▶
  current). Clicking a row jumps the focus pane to it.

Header (full width) shows: close button, file path, progress counter
(`7 / 20 labeled (35%)`), and the `☐ 只看未標` toggle.

Deliberately hidden from the focus pane: `cost_usd`, `latency_ms`,
`tokens_in/out`, `model_id`, `expected` (the latter only while label is
uncommitted).

### 5.3 Label interaction

Keyboard + mouse dual-mode:

| Action | Key | Effect |
|---|---|---|
| Label `hard_refusal` | `1` / click | Write to CSV → reveal expected comparison → auto-advance if consistent |
| Label `soft_refusal` | `2` / click | Same |
| Label `on_task` | `3` / click | Same |
| Clear label | `u` / `Backspace` / click Clear | Empty the CSV `label` cell for this row |
| Next row | `→` / `Space` | Move focus without changing label |
| Previous row | `←` | Move focus without changing label |
| Jump to first unlabeled | `n` | Sprint helper |
| Close modal | `ESC` / click ✕ | Modal closes; CSV state already persisted |

### 5.4 Confirmatory reveal

After a label button is pressed, the row is written to CSV. Immediately
after the write, a comparison chip appears below the buttons showing the
rater's choice vs. the `expected` field:

- **Consistent** (e.g. rater chose `hard_refusal`, expected is
  `hard_refusal_expected`): green chip; focus auto-advances to next row
  after 300 ms.
- **Inconsistent**: yellow chip with `[撤回 (u)]` and `[確認並繼續 (→)]`
  buttons. Auto-advance is suppressed; the rater must explicitly confirm
  or revert. This makes "rater disagreed with the prompt author" rows a
  deliberate choice, not an accident.

The 300 ms consistent auto-advance preserves sprint feel; the
inconsistent-row pause forces reflection on the interesting cases.

### 5.5 Edge cases

| Situation | Handling |
|---|---|
| CSV file missing or deleted mid-session | `load` returns 404; UI shows "檔案不存在，請重跑 fetch" toast |
| CSV header missing `label` column | `load` returns 400; UI shows "非 calibration CSV 格式" |
| All rows already labeled on open | Completion card instead of focus pane (see 5.6) |
| Row with `status=error` | Label buttons disabled; `error_detail` shown; rater presses `u` or `→` to skip |
| User closes modal mid-session | No special handling needed; CSV already up-to-date; resume = re-open and auto-jump to first unlabeled |
| Rapid clicks on same row (different labels) | Last-write-wins; CSV overwritten each time; no history |

### 5.6 Completion flow

When every row has a non-empty label, the focus pane is replaced by:

```
🎉 全部標註完成

總計：20 rows
 · hard_refusal:  12
 · soft_refusal:   5
 · on_task:        3

與 expected 不一致：4 rows

下一步：
  [🔁 回列表檢視不一致的 4 row]
  [📤 執行 calibration import-labels]
  [✕ 關閉]
```

`[📤 執行 calibration import-labels]` fires a subprocess job via the
existing `jobs.py` manager: `civatas-exp calibration import-labels --csv
<path> --output <path>.labeled.jsonl`. The job log streams into the main
webui job panel.

## 6. Backend API

Three endpoints added to `Paper/src/ctw_va/webui/`, wired into `app.py`.

### 6.1 `GET /api/labeling/load`

- Query: `path` (relative, under `experiments/ runs/ data/`).
- Response:
  ```json
  {
    "path": "experiments/refusal_calibration/responses_n20.csv",
    "file_mtime": 1714567890.123,
    "progress": {"total": 20, "labeled": 7, "inconsistent": 2, "unlabeled": 13},
    "rows": [
      {
        "prompt_id": "HR34",
        "vendor": "deepseek",
        "prompt_text": "...",
        "response_text": "...",
        "label": "",
        "expected": "hard_refusal_expected",
        "topic": "sovereignty",
        "status": "ok",
        "error_detail": ""
      },
      ...
    ]
  }
  ```
- Errors: 400 if CSV header lacks `label`; 404 if file missing; 403 if
  path escapes whitelist.

### 6.2 `POST /api/labeling/set`

- Body: `{"path": ..., "prompt_id": ..., "vendor": ..., "label": ...,
  "expected_file_mtime": 1714567890.123}`
- Validates `label` ∈ `{"hard_refusal", "soft_refusal", "on_task"}`.
- Optimistic lock: if on-disk mtime differs from `expected_file_mtime`,
  returns `{"ok": false, "reason": "file_modified_externally", "new_mtime":
  ...}` without writing.
- Otherwise rewrites CSV preserving UTF-8-BOM and all other rows untouched,
  returns `{"ok": true, "new_mtime": ...}`.
- Errors: 400 on bad label; 404 on missing file; 400 on unmatched
  `(prompt_id, vendor)`.

### 6.3 `POST /api/labeling/clear`

- Body: `{"path": ..., "prompt_id": ..., "vendor": ...,
  "expected_file_mtime": ...}`
- Same shape / semantics as `set`, but writes an empty string to the
  `label` column.

Providing a separate `clear` endpoint (rather than `set` with
`label=""`) keeps request intent explicit at the audit-log level and lets
`set` enforce the non-empty-label invariant.

## 7. Data / persistence

CSV is rewritten via:

```
read whole file → List[dict] (csv.DictReader with BOM-aware open)
locate row where prompt_id and vendor match → update label
write whole file (csv.DictWriter, utf-8-sig, fieldnames preserved)
return os.path.getmtime(path)
```

Justification for full rewrite vs byte-level patch:
- `response_text` contains quoted newlines and CJK commas → byte offsets
  cannot be derived cheaply.
- n=1000 file is ~500 KB; full rewrite is under 10 ms on SSD.
- A half-written file is structurally invalid; full-rewrite guarantees
  atomicity at CSV level.

## 8. Safety

- Path whitelist: reuse the `_resolve_safe_path()` helper from the
  existing preview endpoint (roots: `experiments/`, `runs/`, `data/`).
- Filename regex: `^responses_n\d+(_\w+)?\.csv$` — rejects arbitrary CSV
  writes (safety net even within whitelist).
- Label whitelist: `VALID_LABELS` reused from `refusal.prompts`.
- No auth: tool is local-only; binding stays on `127.0.0.1`.

## 9. Testing

New file `Paper/tests/test_webui_labeling.py`:

1. **test_load_returns_rows_and_progress** — fixture CSV with 3 rows (one
   labeled, one unlabeled, one `status=error`); assert `rows` length,
   `progress.labeled==1`, `file_mtime` is a positive float.
2. **test_set_updates_in_place_preserving_bom** — set label on a row,
   re-read file bytes, assert BOM preserved, target row's `label` is
   written, other rows unchanged.
3. **test_set_stale_mtime_returns_ok_false** — simulate external edit by
   touching file, post with old `expected_file_mtime`, assert
   `ok==false`, `reason=="file_modified_externally"`, CSV on disk is
   unchanged.
4. **test_clear_empties_label** — happy-path clear round-trip.
5. **test_set_invalid_label_returns_400** — unknown label string rejected.

Tests use FastAPI's `TestClient` against an in-memory app instance, with
a `tmp_path` fixture for the CSV.

## 10. Files touched

**New**
- `Paper/src/ctw_va/webui/labeling.py` (handler + helpers, ≈150 lines)
- `Paper/tests/test_webui_labeling.py` (≈150 lines)
- `docs/superpowers/specs/2026-04-20-calibration-inline-labeling-design.md`
  (this doc)

**Modified**
- `Paper/src/ctw_va/webui/app.py` — import and register labeling router
- `Paper/src/ctw_va/webui/static/index.html` — add `✏️ 進入標註模式`
  button to preview header; add Alpine component for the modal (focus
  pane, mini list, confirmatory reveal, completion card, keyboard
  bindings)

**Unchanged**
- `Paper/src/ctw_va/refusal/csv_io.py` — existing `import_labels_from_csv`
  remains the downstream consumer.
- `Paper/src/ctw_va/refusal/prompts.py` — `VALID_LABELS` imported for
  server-side validation.
- `Paper/src/ctw_va/cli/calibration.py` — CLI surface unchanged.

## 11. Rollout

No feature flag, no migration. The feature is additive:
- Old Excel workflow continues to work (CLI `export-labels` / user fills
  CSV / `import-labels`).
- New UI edits the same CSV directly; the two paths are interchangeable.
- Existing `test_webui_*` suites untouched.

## 12. Open questions deliberately deferred

- Multi-file labeling session (jump between `responses_n20.csv` and
  `responses_n200.csv`): defer until n=200 is actually fetched.
- Filter by vendor/topic in mini list: defer until labeling fatigue on
  n=1000 proves it necessary.
- Inter-rater agreement UI: out of scope for arXiv (single rater by
  choice).
