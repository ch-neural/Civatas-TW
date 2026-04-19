# News pool — 2024 Taiwan presidential election (2024-01-01 ~ 2024-01-13)

Frozen news corpus for CTW-VA-2026 Vendor Audit experiment.

## Acquisition protocol

Three-stage Serper (Google News) fetch strategy to counter Google News
SEO bias against paywalled / low-SEO Taiwanese media. See `01_RESEARCH_PLAN.md`
§5.3 for rationale.

### Stage A — broad keyword search (organic discovery)
- 7 keywords: 賴清德, 侯友宜, 柯文哲, 2024總統大選, 民進黨, 國民黨, 民眾黨
- Up to 10 pages each
- Date range: `cdr:1,cd_min:1/1/2024,cd_max:1/13/2024`
- Locale: gl=tw, hl=zh-tw
- API calls: 70
- Raw articles: 700

### Stage B — site-scoped blue-leaning media
- 7 domains: chinatimes.com, udn.com, tvbs.com.tw, ettoday.net, ctitv.com.tw,
  ebc.net.tw, setn.com
- 3 core keywords: 賴清德, 侯友宜, 柯文哲
- Up to 5 pages each
- API calls: 85
- Raw articles: 775

### Stage C — site-scoped deep-spectrum media
- 7 domains: ltn.com.tw (自由), ftvnews.com.tw (民視), newtalk.tw,
  peoplenews.tw (民報, dead), taiwanhot.net, news.cti.com.tw (中天網, dead),
  storm.mg (風傳媒)
- 3 core keywords
- Up to 5 pages each
- API calls: 73
- Raw articles: 604

### Merge (A1)
- Dedup by URL → 1,445 unique articles
- 51 excluded as non-news (party offices, social platforms, non-political)
- Final classified pool: 1,394 articles
- SHA-256: `29a4dacd0662479b35677cd51ece094c9b740041ccb908cfd5493315d425bcb6`
- `news_pool_id` (first 16 hex chars): `29a4dacd0662479b`

## Leaning distribution

| Bucket | Articles | % of classified (n=1340) | Target range |
|---|---|---|---|
| 深綠 | 221 | 16.5% | 15-25% ✅ |
| 偏綠 | 268 | 20.0% | 20-30% ✅ |
| 中間 | 366 | 27.3% | 25-35% ✅ |
| 偏藍 | 478 | 35.7% | 30-40% ✅ |
| 深藍 | 7 | 0.5% | 0 (structural) ✅ |
| unknown | 54 | 3.9% | - (not in DOMAIN_LEANING_MAP) |

深藍 near-zero reflects the structural online news vacuum post-中天 TV revocation.
深藍 agents use `DEEP_BLUE_FALLBACK_DOMAINS` = {chinatimes, tvbs, udn} per
`MEDIA_HABIT_EXPOSURE_MIX`.

## Frozen files

| File | SHA-256 |
|---|---|
| `merged_pool.jsonl` | see `merged_pool.sha256` |
| `merged_pool.sha256` | plain-text hex of merged_pool.jsonl |
| `ingestion_metadata.json` | metadata {news_pool_id, created_at, article_count, ...} |

## Reproducing

```bash
cd Paper/
source .venv/bin/activate
civatas-exp news-pool fetch-a --output experiments/news_pool_2024_jan/stage_a_output.jsonl
civatas-exp news-pool fetch-b --output experiments/news_pool_2024_jan/stage_b_output.jsonl
civatas-exp news-pool fetch-c --output experiments/news_pool_2024_jan/stage_c_output.jsonl
civatas-exp news-pool merge
```

Expected cost: ~USD 0.08 (Serper $0.0003 / call × ~230 calls).

Note: `fetch-*` output volume may vary slightly between runs (±3%) due to
Google News ranker stochasticity. The `merge` step produces identical SHA-256
when inputs are identical. Leaning distribution is robust to small fetch
variance because `DOMAIN_LEANING_MAP` is domain-based (not URL-dependent).

## Known limitations

1. **深藍 structural vacuum**: 中天新聞網 (ctitv.com.tw / news.cti.com.tw) post-NCC
   revocation carries near-zero online presence. 深藍 voters in reality follow
   political talk shows on YouTube (not web-indexed text) and LINE groups
   (unscrapable). Fallback to top-partisan 偏藍 is methodologically explicit.

2. **民報 (peoplenews.tw)**: Pilot verified as non-responsive to Serper queries
   (likely site reorganization or de-indexed). Kept in Stage C config for
   completeness; yields 0 articles in current runs.

3. **Unknown domains (3.9%)**: Domains not yet in `DOMAIN_LEANING_MAP`. These
   are treated as "unknown" in feed routing and may be present in any agent's
   daily pool via the catch-all fallback. To reduce, extend `DOMAIN_LEANING_MAP`
   in `src/ctw_va/data/feed_sources.py`.

4. **Date range stochasticity**: Stage B/C's site-scoped queries sometimes
   return articles slightly outside 2024-01-01..2024-01-13 due to Google's
   date filter tolerance. Current pool includes ~2% of articles from
   2024-01-14 to 2024-01-16. Minor — does not affect experimental validity.
