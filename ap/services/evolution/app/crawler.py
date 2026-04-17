"""Serper-based news fetcher.

Civatas-TW 2026-04-17: retired the Playwright + BeautifulSoup crawler in favour
of Google's Serper News API. Each configured "source" is now mapped to a
``site:<domain>`` query; Serper handles the actual crawling (Google's index
is always fresher than anything we could scrape) and lets us specify an exact
date window via the ``tbs`` parameter. This trims ~500 MB off the Docker
image (no Chromium) and avoids brittle CSS selectors / anti-bot measures.

The dataclass shape is unchanged — ``selector_title`` / ``selector_summary``
fields remain on ``CrawlSource`` so legacy ``sources.json`` files load
cleanly, but those fields are now ignored.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# Serper News defaults for Taiwan traditional Chinese.
_SERPER_URL = "https://google.serper.dev/news"
_SERPER_GL = "tw"
_SERPER_HL = "zh-tw"
_SERPER_LR = "lang_zh-TW"
_DEFAULT_WINDOW_DAYS = 7


def _get_serper_key() -> str:
    """Load SERPER_API_KEY from (a) shared/settings.json if available,
    (b) env var, (c) raise. Matches tavily_research.py's behaviour so the
    same onboarding-wizard key reaches both the api gateway and evolution."""
    try:
        from shared.global_settings import load_settings  # type: ignore
        key = (load_settings() or {}).get("serper_api_key", "")
    except Exception:
        key = ""
    if not key:
        key = os.getenv("SERPER_API_KEY", "") or ""
    return key.strip()


def _domain_of(url: str) -> str:
    """Extract a domain usable with Google's `site:` operator.
    www.cna.com.tw/list/aipl.aspx → cna.com.tw
    """
    try:
        host = urlparse(url).netloc or url
    except Exception:
        host = url
    host = host.lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return host

# ── Political leaning options ────────────────────────────────────────

LEANING_OPTIONS = ["偏綠", "中間", "偏藍"]   # 3-tier simplified for source tagging

# ── Default source registry ──────────────────────────────────────────

@dataclass
class CrawlSource:
    source_id: str
    name: str
    url: str
    tag: str                 # e.g. "聯合報", "自由時報"
    selector_title: str      # CSS selector (legacy; ignored by Serper path)
    selector_summary: str    # CSS selector (legacy; ignored by Serper path)
    max_items: int = 10
    is_default: bool = True
    leaning: str = "中間"      # political leaning of this source (5-bucket or 3-tier)
    # Civatas-TW 2026-04-17: fields for mixed-language source pool.
    # ``language``: "zh-TW" (default; pulls Traditional-Chinese-language results)
    #               or "en" (for Taiwan-English outlets & international bureaus).
    # ``default_keywords``: extra terms appended to every query from this source.
    # For international outlets (Reuters / BBC / Bloomberg …) set it to
    # "Taiwan" so we don't pull their domestic politics coverage.
    language: str = "zh-TW"
    default_keywords: str = ""

DEFAULT_SOURCES: list[dict[str, Any]] = [
    # ── 中間 / 通訊社 ──
    {
        "name": "中央通訊社",
        "url": "https://www.cna.com.tw/list/aipl.aspx",
        "tag": "CNA",
        "leaning": "中間",
        "selector_title": "h2 a, .mainList h2 a",
        "selector_summary": "p",
        "max_items": 10,
    },
    {
        "name": "公視新聞",
        "url": "https://news.pts.org.tw/",
        "tag": "PTS",
        "leaning": "中間",
        "selector_title": "h2 a, h3 a",
        "selector_summary": "p",
        "max_items": 10,
    },
    {
        "name": "關鍵評論網",
        "url": "https://www.thenewslens.com/",
        "tag": "TNL",
        "leaning": "中間",
        "selector_title": "h2 a, h3 a",
        "selector_summary": "p",
        "max_items": 10,
    },
    # ── 偏綠 ──
    {
        "name": "自由時報",
        "url": "https://news.ltn.com.tw/list/breakingnews/politics",
        "tag": "LTN",
        "leaning": "偏綠",
        "selector_title": "a.tit, h3 a",
        "selector_summary": "p",
        "max_items": 10,
    },
    {
        "name": "三立新聞網",
        "url": "https://www.setn.com/ViewAll.aspx?PageGroupID=6",
        "tag": "SETN",
        "leaning": "偏綠",
        "selector_title": "h3 a, .view-li a",
        "selector_summary": "p",
        "max_items": 10,
    },
    {
        "name": "民視新聞網",
        "url": "https://www.ftvnews.com.tw/politics/",
        "tag": "FTV",
        "leaning": "偏綠",
        "selector_title": "h2 a, h3 a",
        "selector_summary": "p",
        "max_items": 10,
    },
    {
        "name": "新頭殼",
        "url": "https://newtalk.tw/news/category/1",
        "tag": "Newtalk",
        "leaning": "偏綠",
        "selector_title": "h3 a, .news-list a",
        "selector_summary": "p",
        "max_items": 10,
    },
    # ── 偏藍 ──
    {
        "name": "聯合新聞網",
        "url": "https://udn.com/news/cate/2/6638",
        "tag": "UDN",
        "leaning": "偏藍",
        "selector_title": "h2 a, h3 a",
        "selector_summary": "p",
        "max_items": 10,
    },
    {
        "name": "中時新聞網",
        "url": "https://www.chinatimes.com/politic/?chdtv",
        "tag": "CTimes",
        "leaning": "偏藍",
        "selector_title": "h3 a, .title a",
        "selector_summary": "p",
        "max_items": 10,
    },
    {
        "name": "TVBS 新聞",
        "url": "https://news.tvbs.com.tw/politics",
        "tag": "TVBS",
        "leaning": "偏藍",
        "selector_title": "h2 a, h3 a",
        "selector_summary": "p",
        "max_items": 10,
    },
    {
        "name": "ETtoday 新聞雲",
        "url": "https://www.ettoday.net/news/focus/%E6%94%BF%E6%B2%BB/",
        "tag": "ETtoday",
        "leaning": "中間",
        "selector_title": "h3 a, .title a",
        "selector_summary": "p",
        "max_items": 10,
    },
    {
        "name": "中天新聞網",
        "url": "https://www.ctitv.com.tw/category/%e6%94%bf%e6%b2%bb/",
        "tag": "CTiTV",
        "leaning": "偏藍",
        "selector_title": "h2 a, h3 a",
        "selector_summary": "p",
        "max_items": 10,
    },
    # ── 台灣本地英文媒體（不用強制 Taiwan keyword；文章本身就是台灣新聞）──
    {
        "name": "Focus Taiwan (中央社英文版)",
        "url": "https://focustaiwan.tw/politics",
        "tag": "FocusTW",
        "leaning": "中間",
        "selector_title": "", "selector_summary": "",
        "max_items": 8,
        "language": "en",
        "default_keywords": "",
    },
    {
        "name": "Taipei Times (自由時報英文版)",
        "url": "https://www.taipeitimes.com/News/front",
        "tag": "TaipeiTimes",
        "leaning": "偏綠",
        "selector_title": "", "selector_summary": "",
        "max_items": 8,
        "language": "en",
        "default_keywords": "",
    },
    {
        "name": "Taiwan News",
        "url": "https://www.taiwannews.com.tw/news/politics",
        "tag": "TWNews",
        "leaning": "中間",
        "selector_title": "", "selector_summary": "",
        "max_items": 8,
        "language": "en",
        "default_keywords": "",
    },
    # ── 國際主流媒體涵蓋台灣議題（強制 Taiwan keyword，避免拉到美國內政）──
    {
        "name": "Reuters (Taiwan)",
        "url": "https://www.reuters.com/",
        "tag": "Reuters",
        "leaning": "中間",
        "selector_title": "", "selector_summary": "",
        "max_items": 6,
        "language": "en",
        "default_keywords": "Taiwan",
    },
    {
        "name": "Bloomberg (Taiwan)",
        "url": "https://www.bloomberg.com/",
        "tag": "Bloomberg",
        "leaning": "中間",
        "selector_title": "", "selector_summary": "",
        "max_items": 6,
        "language": "en",
        "default_keywords": "Taiwan",
    },
    {
        "name": "BBC News (Taiwan)",
        "url": "https://www.bbc.com/news",
        "tag": "BBC",
        "leaning": "中間",
        "selector_title": "", "selector_summary": "",
        "max_items": 6,
        "language": "en",
        "default_keywords": "Taiwan",
    },
    {
        "name": "Nikkei Asia (Taiwan)",
        "url": "https://asia.nikkei.com/",
        "tag": "NikkeiAsia",
        "leaning": "中間",
        "selector_title": "", "selector_summary": "",
        "max_items": 6,
        "language": "en",
        "default_keywords": "Taiwan",
    },
    {
        "name": "The Guardian (Taiwan)",
        "url": "https://www.theguardian.com/world",
        "tag": "Guardian",
        "leaning": "中間",
        "selector_title": "", "selector_summary": "",
        "max_items": 5,
        "language": "en",
        "default_keywords": "Taiwan",
    },
    # ── 社群媒體／論壇（只有 media_habit 含「PTT/論壇」或「社群媒體」
    #    的 persona 會在 feed_engine 看到這些；見 DEFAULT_DIET_MAP）──
    {
        "name": "PTT Gossiping",
        "url": "https://www.ptt.cc/bbs/Gossiping/index.html",
        "tag": "PTT Gossiping",
        "leaning": "中間",
        "selector_title": "", "selector_summary": "",
        "max_items": 8,
        "language": "zh-TW",
        "default_keywords": "",
    },
    {
        "name": "PTT HatePolitics",
        "url": "https://www.ptt.cc/bbs/HatePolitics/index.html",
        "tag": "PTT HatePolitics",
        "leaning": "中間",
        "selector_title": "", "selector_summary": "",
        "max_items": 8,
        "language": "zh-TW",
        "default_keywords": "",
    },
    {
        "name": "Dcard 時事",
        "url": "https://www.dcard.tw/f/trending",
        "tag": "Dcard 時事",
        "leaning": "中間",
        "selector_title": "", "selector_summary": "",
        "max_items": 6,
        "language": "zh-TW",
        "default_keywords": "",
    },
    {
        "name": "LINE Today",
        "url": "https://today.line.me/tw/v2/tab/news",
        "tag": "LINE Today",
        "leaning": "中間",
        "selector_title": "", "selector_summary": "",
        "max_items": 8,
        "language": "zh-TW",
        "default_keywords": "",
    },
]


def _make_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


def build_default_sources() -> list[CrawlSource]:
    """Return the default source list as CrawlSource objects."""
    results = []
    for s in DEFAULT_SOURCES:
        results.append(CrawlSource(
            source_id=_make_id(s["url"]),
            name=s["name"],
            url=s["url"],
            tag=s["tag"],
            selector_title=s["selector_title"],
            selector_summary=s.get("selector_summary", ""),
            max_items=s.get("max_items", 10),
            is_default=True,
            leaning=s.get("leaning", "中間"),
            language=s.get("language", "zh-TW"),
            default_keywords=s.get("default_keywords", ""),
        ))
    return results


# ── Crawl engine ─────────────────────────────────────────────────────

@dataclass
class CrawledArticle:
    article_id: str
    title: str
    summary: str
    source_url: str
    source_tag: str
    source_leaning: str  # political leaning of the source
    crawled_at: str  # ISO format


async def crawl_source(
    source: CrawlSource,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    extra_keywords: str = "",
) -> list[CrawledArticle]:
    """Fetch news for one source via Google Serper News API.

    Args:
      source: CrawlSource with a URL whose domain becomes the ``site:`` filter.
      start_date / end_date: ISO yyyy-mm-dd (inclusive). If both omitted,
        defaults to the last ``_DEFAULT_WINDOW_DAYS`` (7) days.
      extra_keywords: optional free-text appended to the query (e.g.
        "賴清德 民調" would narrow results beyond just "site:ltn.com.tw").

    Returns a list of CrawledArticle. Returns empty list on any API/network
    failure (logged, but won't raise) — this matches the Playwright-era
    behaviour so a single bad source can't break the whole crawl_all batch.
    """
    articles: list[CrawledArticle] = []
    api_key = _get_serper_key()
    if not api_key:
        logger.warning(f"SERPER_API_KEY 未設定，跳過 {source.name}")
        return articles

    domain = _domain_of(source.url)
    if not domain:
        logger.warning(f"{source.name}: 無法從 URL 解析網域 ({source.url})")
        return articles

    # Build Google date-range tbs. Serper accepts the same cdr:1 format used
    # by tavily_research.py in the api service.
    now = datetime.now(timezone.utc).date()
    try:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else now
    except ValueError:
        end_dt = now
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else (end_dt - timedelta(days=_DEFAULT_WINDOW_DAYS))
    except ValueError:
        start_dt = end_dt - timedelta(days=_DEFAULT_WINDOW_DAYS)
    tbs = f"cdr:1,cd_min:{start_dt.strftime('%m/%d/%Y')},cd_max:{end_dt.strftime('%m/%d/%Y')}"

    # Build query: site:domain + source's own default_keywords + any extras.
    # Chinese sources: no keyword needed (already returns Taiwan news).
    # English international sources: default_keywords="Taiwan" keeps us out
    # of their US/UK domestic coverage.
    query_parts = [f"site:{domain}"]
    src_kw = (getattr(source, "default_keywords", "") or "").strip()
    if src_kw:
        query_parts.append(src_kw)
    if extra_keywords.strip():
        query_parts.append(extra_keywords.strip())
    query = " ".join(query_parts)

    # Language: zh-TW (default) or en. Forced via lr + hl parameters.
    lang = (getattr(source, "language", "zh-TW") or "zh-TW").lower()
    if lang.startswith("en"):
        hl, lr = "en", "lang_en"
    else:
        hl, lr = _SERPER_HL, _SERPER_LR

    num = max(1, min(source.max_items or 10, 100))
    payload = {
        "q": query,
        "gl": _SERPER_GL,  # always Taiwan locale for rank signal
        "hl": hl,
        "lr": lr,
        "num": num,
        "tbs": tbs,
    }
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}

    logger.info(f"Serper → {source.name} ({domain})  window={start_dt}~{end_dt}  num={num}")
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(_SERPER_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        body = (e.response.text or "")[:200]
        logger.warning(f"Serper {e.response.status_code} for {source.name}: {body}")
        return articles
    except Exception as e:
        logger.warning(f"Serper request failed for {source.name}: {e}")
        return articles

    raw = data.get("news", []) or []
    fetched_at = datetime.now(timezone.utc).isoformat()
    for r in raw:
        title = (r.get("title") or "").strip()
        if not title or len(title) < 4:
            continue
        link = r.get("link") or source.url
        summary = (r.get("snippet") or "")[:200]
        aid = _make_id(f"{link}:{title}")
        articles.append(CrawledArticle(
            article_id=aid,
            title=title[:200],
            summary=summary,
            source_url=link,
            source_tag=source.tag,
            source_leaning=source.leaning,
            crawled_at=fetched_at,
        ))

    logger.info(f"  → {len(articles)} articles from {source.name}")
    return articles


async def crawl_all(
    sources: list[CrawlSource],
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    extra_keywords: str = "",
) -> list[CrawledArticle]:
    """Fetch news for all sources (concurrently — Serper calls are HTTP, not
    browser automation, so parallelism is cheap)."""
    tasks = [
        crawl_source(src, start_date=start_date, end_date=end_date, extra_keywords=extra_keywords)
        for src in sources
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    all_articles: list[CrawledArticle] = []
    for res in results:
        if isinstance(res, Exception):
            logger.warning(f"crawl_all: one source raised — {res}")
            continue
        all_articles.extend(res)
    return all_articles
