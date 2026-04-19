# CTW-VA-2026: Civatas-TW Vendor Audit

Standalone experimental platform for comparing 5 LLM vendors simulating
Taiwan 2024 presidential election voters. Full research specification:
[docs/01_RESEARCH_PLAN.md](docs/01_RESEARCH_PLAN.md).

**No Docker required** — pure Python CLI + single-file HTML dashboard.

## Quick install

```bash
pip install -e Paper/
# or, from inside Paper/:
pip install -e .
```

For dev dependencies (pytest, ruff):
```bash
pip install -e Paper/[dev]
```

## Quick usage

### Phase A: Build the frozen news pool

```bash
# Fetch articles (requires SERPER_API_KEY in .env)
civatas-exp news-pool fetch-a --output experiments/news_pool_2024_jan/stage_a_output.jsonl
civatas-exp news-pool fetch-b --output experiments/news_pool_2024_jan/stage_b_output.jsonl
civatas-exp news-pool fetch-c --output experiments/news_pool_2024_jan/stage_c_output.jsonl

# Merge, dedup, compute SHA-256 (freezes the pool)
civatas-exp news-pool merge

# Print leaning / stage / domain statistics
civatas-exp news-pool stats
```

### All commands

```
civatas-exp --help          # top-level command list
civatas-exp news-pool       # Phase A1: news pool management
civatas-exp persona-slate   # Phase A3: deterministic persona export (stub)
civatas-exp calibration     # Phase A5: refusal calibration (stub)
civatas-exp run             # Phase C4-C5: run experiment (stub)
civatas-exp cost            # Phase B5: cost estimation (stub)
civatas-exp analyze         # Phase C7: statistical analysis (stub)
civatas-exp dashboard       # Phase D: HTML dashboard generation (stub)
civatas-exp paper           # Phase C9: paper figures (stub)
```

## Standalone design

- SQLite for experiment storage (no Postgres, no Docker)
- Rule-based persona generation (no LLM calls during setup)
- All API keys via `.env` / environment variables (python-dotenv)
- Dashboard: single-file HTML + Chart.js (no React SPA)
- Outputs under `runs/<experiment-id>/` (gitignored)

See [docs/02_CLAUDE_CODE_TASKS.md](docs/02_CLAUDE_CODE_TASKS.md) for the
full task spec and acceptance criteria per phase.
