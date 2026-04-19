"""Taiwan news source taxonomy and media-habit map.

Replaces the US-era ``us_feed_sources.py`` for Taiwan workspaces.
Schema mirrors the US module so ``feed_engine`` consumes it identically:

    DEFAULT_SOURCE_LEANINGS  — {source_name_zh: 5-tier bucket}
    DEFAULT_DIET_MAP         — {media_habit_zh: [source_name_zh, ...]}
    sources_by_bucket()      — grouping helper for the UI

New in PR-1 (2026-04-18):
    DOMAIN_LEANING_MAP       — {domain: 5-tier bucket} for URL-based resolution
    DEEP_BLUE_FALLBACK_DOMAINS — set of fallback domains for 深藍 agents
    MEDIA_HABIT_EXPOSURE_MIX — per-agent target exposure distribution matrix
    domain_to_leaning()      — resolve a domain or URL → 5-bucket leaning

Leaning buckets use the canonical TW 5-tier spectrum:
    深綠 / 偏綠 / 中間 / 偏藍 / 深藍

Bias assignments follow common Taiwan media-literacy surveys (卓越新聞獎基金會 2023
媒體信任度、台灣事實查核中心 2024 媒體立場) — where sources overlap significantly
we pick the closer-to-中間 classification. UI can surface the raw assignment so
users can override per workspace.

This file has no cross-imports; it can be loaded standalone for tests and
exposed via /api/runtime/news-sources.
"""
from __future__ import annotations


DEFAULT_SOURCE_LEANINGS: dict[str, str] = {
    # ── 中間 / 通訊社 / 公視 ─────────────────────────────────────────
    "中央通訊社":       "中間",
    "公視新聞":         "中間",
    "關鍵評論網":       "中間",
    "鏡週刊":           "中間",
    "天下雜誌":         "中間",
    "遠見雜誌":         "中間",
    "商業周刊":         "中間",
    "財訊":             "中間",
    "報導者":           "中間",
    "風傳媒":           "中間",
    "今周刊":           "中間",
    "Yahoo 新聞":       "中間",
    "Google 新聞":      "中間",
    "經濟日報":         "中間",
    "工商時報":         "中間",

    # ── 偏綠 ────────────────────────────────────────────────────────
    "自由時報":         "偏綠",
    "新頭殼":           "偏綠",
    "上報":             "偏綠",
    "Newtalk 新頭殼":   "偏綠",
    "壹蘋新聞網":       "偏綠",

    # ── 深綠 ────────────────────────────────────────────────────────
    # 三立新聞網 / 民視新聞網 re-classified per NCC / 媒觀教育基金會
    # academic consensus (2024). Aligned with DOMAIN_LEANING_MAP.
    "三立新聞網":       "深綠",
    "民視新聞網":       "深綠",
    "民報":             "深綠",
    "台灣蘋果日報":     "深綠",
    "大紀元（台灣版）": "深綠",   # 反共深綠
    "芋傳媒":           "深綠",

    # ── 偏藍 ────────────────────────────────────────────────────────
    "聯合新聞網":       "偏藍",
    "中時新聞網":       "偏藍",
    "TVBS 新聞":        "偏藍",
    "ETtoday 新聞雲":   "偏藍",   # 中間偏藍
    "NOWnews 今日新聞": "偏藍",
    "聯合報":           "偏藍",

    # ── 深藍 ────────────────────────────────────────────────────────
    "中天新聞網":       "深藍",
    "中國時報":         "深藍",
    "中視新聞":         "深藍",
    "旺報":             "深藍",

    # ── 社群平台 / 論壇 ─────────────────────────────────────────────
    "PTT Gossiping":    "中間",
    "PTT HatePolitics": "中間",
    "Dcard 時事":       "中間",
    "Facebook 動態":    "中間",
    "LINE 群組轉傳":    "中間",
    "LINE Today":       "中間",
    "Instagram Reels":  "中間",
    "Threads":          "中間",
    "X（Twitter）":     "中間",

    # ── YouTube / 政論節目 ──────────────────────────────────────────
    "YouTube":           "中間",
    "八點檔政論":         "中間",
    "關鍵時刻 (東森)":   "偏藍",
    "少康戰情室 (TVBS)": "偏藍",
    "鄭知道了 (三立)":   "偏綠",
    "新聞面對面 (民視)": "偏綠",
    "年代向錢看":         "偏藍",
    "頭家來開講":         "偏綠",

    # ── 事實查核 / 第三勢力 ──────────────────────────────────────────
    "台灣事實查核中心": "中間",
    "MyGoPen":          "中間",
    "Cofacts":          "中間",

    # ── 英文外電 / 國際 ──────────────────────────────────────────────
    "BBC 中文網":                "中間",
    "紐約時報中文網":            "中間",
    "Reuters 中文":              "中間",
    "DW 德國之聲":               "中間",
    # 台灣本地英文媒體（台灣人英文閱讀圈常讀）
    "Focus Taiwan (中央社英文版)":  "中間",
    "Taipei Times (自由時報英文版)": "偏綠",
    "Taiwan News":                  "中間",
    # 國際媒體寫台灣（加 Taiwan keyword 定向）
    "Reuters (Taiwan)":             "中間",
    "Bloomberg (Taiwan)":           "中間",
    "BBC News (Taiwan)":            "中間",
    "Nikkei Asia (Taiwan)":         "中間",
    "The Guardian (Taiwan)":        "中間",

    # ── 廣播 ────────────────────────────────────────────────────────
    "央廣":             "中間",
    "News 98":          "中間",
    "中廣新聞網":       "偏藍",

    # ── Generic ─────────────────────────────────────────────────────
    "地方新聞":         "中間",
    "人工注入":         "中間",
    "Manual Injection": "中間",
}


# ── Media-habit → source set ─────────────────────────────────────────
# Keys must match the `media_habit` dimension values in TW templates
# (data/templates/*.json).

DEFAULT_DIET_MAP: dict[str, list[str]] = {
    "電視新聞": [
        "TVBS 新聞", "中天新聞網", "三立新聞網", "民視新聞網", "中視新聞",
        "公視新聞", "ETtoday 新聞雲", "關鍵時刻 (東森)", "少康戰情室 (TVBS)",
        "鄭知道了 (三立)", "新聞面對面 (民視)",
    ],
    "網路新聞": [
        "自由時報", "聯合新聞網", "中時新聞網", "ETtoday 新聞雲", "Newtalk 新頭殼",
        "中央通訊社", "風傳媒", "關鍵評論網", "上報", "NOWnews 今日新聞",
    ],
    "社群媒體": [
        "Facebook 動態", "LINE 群組轉傳", "LINE Today", "Instagram Reels",
        "Threads", "X（Twitter）", "Dcard 時事", "PTT Gossiping", "PTT HatePolitics",
    ],
    "報紙": [
        "聯合報", "中國時報", "自由時報", "經濟日報", "工商時報",
    ],
    "PTT/論壇": [
        "PTT Gossiping", "PTT HatePolitics", "Dcard 時事",
    ],
    "廣播": [
        "央廣", "News 98", "中廣新聞網",
    ],
    # Fallback categories for personas with English / legacy labels
    "TV News": [
        "TVBS 新聞", "三立新聞網", "公視新聞", "民視新聞網",
    ],
    "Social Media (Facebook / X / TikTok)": [
        "Facebook 動態", "Threads", "X（Twitter）", "LINE Today",
    ],
}


# Probability that a feed item leaks across media bubbles (matches feed_engine
# default; tunable per workspace via scoring_params).
SERENDIPITY_RATE = 0.05


# ── Domain → leaning map ──────────────────────────────────────────────
# Derived from 3-stage pilot verification (Stage A/B/C 2026-04-18).
# setn.com = 深綠 per NCC / 媒觀教育基金會 academic consensus.
# ETtoday = 中間 despite some academic dispute (mostly non-political content).
# ctitv.com.tw / peoplenews.tw verified dead / non-indexed.
DOMAIN_LEANING_MAP: dict[str, str] = {
    # 深綠
    "ftvnews.com.tw":       "深綠",   # 民視新聞
    "setn.com":             "深綠",   # 三立新聞網
    # 偏綠
    "ltn.com.tw":           "偏綠",   # 自由時報
    "newtalk.tw":           "偏綠",   # Newtalk
    "thenewslens.com":      "偏綠",   # 關鍵評論網
    # 中間
    "cna.com.tw":           "中間",   # 中央社
    "pts.org.tw":           "中間",   # 公視
    "newsroom.cw.com.tw":   "中間",   # 天下雜誌
    "commonwealth.tw":      "中間",   # 天下 alt
    "bnext.com.tw":         "中間",   # 數位時代
    "businesstoday.com.tw": "中間",   # 今周刊
    "ettoday.net":          "中間",   # ETtoday
    "taiwanhot.net":        "中間",   # 台灣好新聞
    "tw.news.yahoo.com":    "中間",   # Yahoo 聚合
    # 偏藍
    "chinatimes.com":       "偏藍",   # 中時
    "udn.com":              "偏藍",   # 聯合
    "tvbs.com.tw":          "偏藍",   # TVBS
    "ebc.net.tw":           "偏藍",   # 東森
    "storm.mg":             "偏藍",   # 風傳媒
    # 深藍: structural vacuum. Use DEEP_BLUE_FALLBACK_DOMAINS for those agents.
}

# For 深藍 agents — no online 深藍 source exists (中天 TV revoked, no successor).
# Route deep-blue agents to the most-right partisan subset of 偏藍 media.
DEEP_BLUE_FALLBACK_DOMAINS: set[str] = {"chinatimes.com", "tvbs.com.tw", "udn.com"}

# Per-agent exposure matrix: for each media_habit, what leaning distribution
# their daily article pool should follow. Values are proportions (sum ≈ 1.0).
#
# Calibration note: Initial values based on expert judgement. Paper-ready
# version should re-calibrate to TEDS 2024 post-election media consumption
# questionnaire. See `docs/superpowers/specs/.../news-exposure-calibration.md`.
MEDIA_HABIT_EXPOSURE_MIX: dict[str, dict[str, float]] = {
    "深綠": {"深綠": 0.50, "偏綠": 0.35, "中間": 0.15, "偏藍": 0.00, "深藍": 0.00},
    "偏綠": {"深綠": 0.15, "偏綠": 0.45, "中間": 0.30, "偏藍": 0.10, "深藍": 0.00},
    "中間": {"深綠": 0.05, "偏綠": 0.20, "中間": 0.50, "偏藍": 0.20, "深藍": 0.05},
    "偏藍": {"深綠": 0.00, "偏綠": 0.10, "中間": 0.30, "偏藍": 0.45, "深藍": 0.15},
    "深藍": {"深綠": 0.00, "偏綠": 0.00, "中間": 0.15, "偏藍": 0.85, "深藍": 0.00},
    # 深藍 の 深藍 = 0 (structural). 85% 偏藍 routed through top-partisan fallback.
}


def domain_to_leaning(domain: str) -> str | None:
    """Resolve a bare domain (or URL) to its 5-bucket leaning. Returns None if unknown."""
    if not domain:
        return None
    # Strip protocol / path if URL was passed
    from urllib.parse import urlparse
    if "://" in domain:
        domain = urlparse(domain).netloc or domain
    # Strip leading www.
    domain = domain.lower().removeprefix("www.")
    if domain in DOMAIN_LEANING_MAP:
        return DOMAIN_LEANING_MAP[domain]
    # Try suffix match (e.g., news.ltn.com.tw → ltn.com.tw)
    for mapped_domain, leaning in DOMAIN_LEANING_MAP.items():
        if domain.endswith("." + mapped_domain):
            return leaning
    return None


# ── Grouping helper for the UI ───────────────────────────────────────
# Returns sources organized by 5-tier bucket. Used by the
# /api/runtime/news-sources endpoint and by any UI surface that enumerates
# sources grouped by political leaning.

def sources_by_bucket() -> dict[str, list[str]]:
    """Return {bucket_label: [source names]} sorted by name within each bucket."""
    buckets: dict[str, list[str]] = {
        "深綠": [], "偏綠": [], "中間": [], "偏藍": [], "深藍": [],
    }
    for src, lean in DEFAULT_SOURCE_LEANINGS.items():
        if lean in buckets:
            buckets[lean].append(src)
    for lst in buckets.values():
        lst.sort()
    return buckets
