"""Playwright-based web crawler that simulates human browsing behaviour.

Fetches headlines and summaries from preconfigured and user-provided URLs.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── Political leaning options ────────────────────────────────────────

LEANING_OPTIONS = ["偏綠", "中間", "偏藍"]   # 3-tier simplified for source tagging

# ── Default source registry ──────────────────────────────────────────

@dataclass
class CrawlSource:
    source_id: str
    name: str
    url: str
    tag: str                 # e.g. "聯合報", "自由時報"
    selector_title: str      # CSS selector for headline elements
    selector_summary: str    # CSS selector for summary text
    max_items: int = 10
    is_default: bool = True
    leaning: str = "中間"      # political leaning of this source (5-bucket or 3-tier)

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


async def crawl_source(source: CrawlSource) -> list[CrawledArticle]:
    """Use Playwright to crawl a single source URL and extract articles."""
    articles: list[CrawledArticle] = []
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("Playwright not installed — cannot crawl.")
        return articles

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                locale="zh-TW",
            )
            page = await context.new_page()

            # PTT requires age verification cookie
            if "ptt.cc" in source.url:
                await context.add_cookies([{
                    "name": "over18",
                    "value": "1",
                    "domain": ".ptt.cc",
                    "path": "/",
                }])

            logger.info(f"Crawling {source.name}: {source.url}")
            await page.goto(source.url, wait_until="domcontentloaded", timeout=600.0)

            # Give dynamic pages a moment to render
            await page.wait_for_timeout(2000)

            html = await page.content()
            await browser.close()

        # Parse with BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        # Extract titles
        title_els = soup.select(source.selector_title) if source.selector_title else []
        title_els = title_els[:source.max_items]

        # Extract summaries (if selector provided)
        summary_els = (
            soup.select(source.selector_summary)
            if source.selector_summary
            else []
        )

        now = datetime.now(timezone.utc).isoformat()

        for i, title_el in enumerate(title_els):
            raw_title = title_el.get_text(strip=True)
            if not raw_title or len(raw_title) < 4:
                continue
            # Clean title
            title = re.sub(r"\s+", " ", raw_title)[:120]

            # Try to get a matching summary
            summary = ""
            if i < len(summary_els):
                summary = summary_els[i].get_text(strip=True)[:100]

            aid = _make_id(f"{source.url}:{title}")
            articles.append(CrawledArticle(
                article_id=aid,
                title=title,
                summary=summary,
                source_url=source.url,
                source_tag=source.tag,
                source_leaning=source.leaning,
                crawled_at=now,
            ))

        logger.info(f"  → {len(articles)} articles from {source.name}")

    except Exception as e:
        logger.exception(f"Failed to crawl {source.name}: {e}")

    return articles


async def crawl_all(sources: list[CrawlSource]) -> list[CrawledArticle]:
    """Crawl all sources sequentially (share one browser instance to save RAM)."""
    all_articles: list[CrawledArticle] = []
    for src in sources:
        batch = await crawl_source(src)
        all_articles.extend(batch)
        # Be polite — small delay between sources
        await asyncio.sleep(1)
    return all_articles
