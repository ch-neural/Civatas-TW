"""Serper news fetchers for CTW-VA-2026 Stage A / B / C.

Ported from:
  /tmp/serper_songshan_test.py   (Stage A — generic 7-keyword search)
  /tmp/serper_siteb_test.py      (Stage B — site-scoped blue-leaning media)
  /tmp/serper_sitec_test.py      (Stage C — site-scoped deep-spectrum media)

Key difference from originals: API key read from env var SERPER_API_KEY
(via python-dotenv) instead of ap/shared/settings.json.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

# ── Default constants ────────────────────────────────────────────────

STAGE_A_KEYWORDS = [
    "賴清德", "侯友宜", "柯文哲", "2024總統大選",
    "民進黨", "國民黨", "民眾黨",
]

STAGE_B_DOMAINS = [
    "chinatimes.com",    # 中時
    "udn.com",           # 聯合
    "tvbs.com.tw",       # TVBS
    "ettoday.net",       # ETtoday
    "ctitv.com.tw",      # 中天（known low yield, kept for completeness）
    "ebc.net.tw",        # 東森
    "setn.com",          # 三立
]

STAGE_C_DOMAINS = [
    "ltn.com.tw",        # 自由時報
    "ftvnews.com.tw",    # 民視新聞
    "newtalk.tw",        # Newtalk
    "peoplenews.tw",     # 民報 (may be dead)
    "taiwanhot.net",     # 台灣好新聞
    "news.cti.com.tw",   # 中天新聞網
    "storm.mg",          # 風傳媒
]

STAGE_BC_KEYWORDS = ["賴清德", "侯友宜", "柯文哲"]  # site-scoped uses core 3 only

DEFAULT_DATE_RANGE = "cdr:1,cd_min:1/1/2024,cd_max:1/13/2024"

SERPER_API_URL = "https://google.serper.dev/news"


# ── Helpers ─────────────────────────────────────────────────────────

def _get_api_key() -> str:
    key = os.environ.get("SERPER_API_KEY", "")
    if not key:
        raise RuntimeError(
            "SERPER_API_KEY not set. Copy .env.example to .env and fill in the key, "
            "then run: source .env  (or use python-dotenv load_dotenv() before calling)."
        )
    return key


def _article_id(url: str) -> str:
    """SHA-1 of URL, first 12 hex chars."""
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def _extract_domain(url: str) -> str:
    """Extract bare domain (no www.) from a URL."""
    try:
        netloc = urlparse(url).netloc or ""
        return netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _make_record(
    n: dict,
    stage: str,
    keyword_used: str,
    page_fetched: int,
) -> dict:
    """Convert a Serper news item to the standard JSONL record schema."""
    url = n.get("link", "")
    return {
        "article_id": _article_id(url),
        "url": url,
        "title": n.get("title", ""),
        "snippet": n.get("snippet", ""),
        "source_domain": _extract_domain(url),
        "source_tag": n.get("source", ""),
        "stage": stage,
        "keyword_used": keyword_used,
        "page_fetched": page_fetched,
        "published_date": n.get("date") or None,
        "ingestion_ts": datetime.now(timezone.utc).isoformat(),
    }


def _append_jsonl(path: str, records: list[dict]) -> None:
    with open(path, "a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _serper_post(api_key: str, payload: dict) -> list[dict]:
    """POST to Serper and return news items. Raises on HTTP error."""
    r = requests.post(
        SERPER_API_URL,
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=20,
    )
    r.raise_for_status()
    return r.json().get("news", [])


# ── Stage A: generic 7-keyword search ────────────────────────────────

def fetch_stage_a(
    keywords: list[str] = STAGE_A_KEYWORDS,
    date_range: str = DEFAULT_DATE_RANGE,
    max_pages: int = 10,
    output_path: str = "experiments/news_pool_2024_jan/stage_a_output.jsonl",
) -> int:
    """Stage A: generic 7-keyword Serper search.

    Returns total article count written (including duplicates across keywords;
    dedup happens at merge stage).
    """
    api_key = _get_api_key()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    # Clear output file
    open(output_path, "w").close()

    total = 0
    seen_urls: set[str] = set()
    total_calls = len(keywords) * max_pages
    call_idx = 0

    for kw in keywords:
        for page in range(1, max_pages + 1):
            call_idx += 1
            try:
                news = _serper_post(api_key, {
                    "q": kw,
                    "tbs": date_range,
                    "gl": "tw",
                    "hl": "zh-tw",
                    "page": page,
                })
            except requests.HTTPError as e:
                print(f"[HTTP ERROR] Stage A kw={kw!r} page={page}: {e}", file=sys.stderr)
                break
            except requests.RequestException as e:
                print(f"[NET ERROR] Stage A kw={kw!r} page={page}: {e}", file=sys.stderr)
                break

            if not news:
                print(f"[A {call_idx}/{total_calls}] kw={kw} page={page} → 0 (stop)", flush=True)
                break  # no more results for this keyword

            new_records = []
            new_count = 0
            for n in news:
                url = n.get("link", "")
                if not url:
                    continue
                rec = _make_record(n, "A", kw, page)
                new_records.append(rec)
                if url not in seen_urls:
                    new_count += 1
                    seen_urls.add(url)

            _append_jsonl(output_path, new_records)
            total += len(new_records)
            print(f"[A {call_idx}/{total_calls}] kw={kw} page={page} → {len(new_records)} ({new_count} new) · total {total}", flush=True)

            if new_count == 0:
                break  # no new unique articles — stop paginating

            time.sleep(0.1)

    return total


# ── Stage B: site-scoped blue-leaning media ───────────────────────────

def fetch_stage_b(
    blue_media_domains: list[str] = STAGE_B_DOMAINS,
    keywords: list[str] = STAGE_BC_KEYWORDS,
    date_range: str = DEFAULT_DATE_RANGE,
    max_pages: int = 5,
    output_path: str = "experiments/news_pool_2024_jan/stage_b_output.jsonl",
) -> int:
    """Stage B: site-scoped queries for blue-leaning media missed by Stage A.

    Returns total article count written.
    """
    api_key = _get_api_key()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    open(output_path, "w").close()

    total = 0
    seen_urls: set[str] = set()
    total_calls = len(blue_media_domains) * len(keywords) * max_pages
    call_idx = 0

    for domain in blue_media_domains:
        for kw in keywords:
            for page in range(1, max_pages + 1):
                call_idx += 1
                try:
                    news = _serper_post(api_key, {
                        "q": f"{kw} site:{domain}",
                        "tbs": date_range,
                        "gl": "tw",
                        "hl": "zh-tw",
                        "page": page,
                    })
                except requests.HTTPError as e:
                    print(f"[HTTP ERROR] Stage B site={domain} kw={kw} page={page}: {e}", file=sys.stderr)
                    break
                except requests.RequestException as e:
                    print(f"[NET ERROR] Stage B site={domain} kw={kw} page={page}: {e}", file=sys.stderr)
                    break

                if not news:
                    print(f"[B {call_idx}/{total_calls}] {domain} kw={kw} p{page} → 0 (stop)", flush=True)
                    break

                new_records = []
                new_count = 0
                for n in news:
                    url = n.get("link", "")
                    if not url:
                        continue
                    rec = _make_record(n, "B", kw, page)
                    new_records.append(rec)
                    if url not in seen_urls:
                        new_count += 1
                        seen_urls.add(url)

                _append_jsonl(output_path, new_records)
                total += len(new_records)
                print(f"[B {call_idx}/{total_calls}] {domain} kw={kw} p{page} → {len(new_records)} ({new_count} new) · total {total}", flush=True)

                if new_count == 0:
                    break

                time.sleep(0.1)

    return total


# ── Stage C: deep-spectrum media ─────────────────────────────────────

def fetch_stage_c(
    deep_spectrum_domains: list[str] = STAGE_C_DOMAINS,
    keywords: list[str] = STAGE_BC_KEYWORDS,
    date_range: str = DEFAULT_DATE_RANGE,
    max_pages: int = 5,
    output_path: str = "experiments/news_pool_2024_jan/stage_c_output.jsonl",
) -> int:
    """Stage C: site-scoped deep-spectrum media (deep-green + deep-blue probes).

    Returns total article count written.
    """
    api_key = _get_api_key()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    open(output_path, "w").close()

    total = 0
    seen_urls: set[str] = set()
    total_calls = len(deep_spectrum_domains) * len(keywords) * max_pages
    call_idx = 0

    for domain in deep_spectrum_domains:
        for kw in keywords:
            for page in range(1, max_pages + 1):
                call_idx += 1
                try:
                    news = _serper_post(api_key, {
                        "q": f"{kw} site:{domain}",
                        "tbs": date_range,
                        "gl": "tw",
                        "hl": "zh-tw",
                        "page": page,
                    })
                except requests.HTTPError as e:
                    print(f"[HTTP ERROR] Stage C site={domain} kw={kw} page={page}: {e}", file=sys.stderr)
                    break
                except requests.RequestException as e:
                    print(f"[NET ERROR] Stage C site={domain} kw={kw} page={page}: {e}", file=sys.stderr)
                    break

                if not news:
                    print(f"[C {call_idx}/{total_calls}] {domain} kw={kw} p{page} → 0 (stop)", flush=True)
                    break

                new_records = []
                new_count = 0
                for n in news:
                    url = n.get("link", "")
                    if not url:
                        continue
                    rec = _make_record(n, "C", kw, page)
                    new_records.append(rec)
                    if url not in seen_urls:
                        new_count += 1
                        seen_urls.add(url)

                _append_jsonl(output_path, new_records)
                total += len(new_records)
                print(f"[C {call_idx}/{total_calls}] {domain} kw={kw} p{page} → {len(new_records)} ({new_count} new) · total {total}", flush=True)

                if new_count == 0:
                    break

                time.sleep(0.1)

    return total
