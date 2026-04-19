"""Feed engine: selects which news articles to push to each agent.

Implements the 'algorithmic filter bubble' logic:
  - Match articles to agent based on media_habit / diet rules
  - Apply political leaning affinity scoring
  - Apply serendipity rate for occasional 'bubble breaking'
"""
from __future__ import annotations

import json
import logging
import os
import random
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

DATA_DIR = os.environ.get("EVOLUTION_DATA_DIR", "/data/evolution")
RULES_FILE = os.path.join(DATA_DIR, "diet_rules.json")

# ── Taiwan feed source registry (restored from Stage 1.9-era TW path) ──
try:
    from .tw_feed_sources import (  # type: ignore
        DEFAULT_SOURCE_LEANINGS as _TW_SOURCE_LEANINGS,
        DEFAULT_DIET_MAP as _TW_DIET_MAP,
        DOMAIN_LEANING_MAP,
        DEEP_BLUE_FALLBACK_DOMAINS,
        MEDIA_HABIT_EXPOSURE_MIX,
        domain_to_leaning,
    )
except ImportError:
    from tw_feed_sources import (  # type: ignore
        DEFAULT_SOURCE_LEANINGS as _TW_SOURCE_LEANINGS,
        DEFAULT_DIET_MAP as _TW_DIET_MAP,
        DOMAIN_LEANING_MAP,
        DEEP_BLUE_FALLBACK_DOMAINS,
        MEDIA_HABIT_EXPOSURE_MIX,
        domain_to_leaning,
    )

# 5-tier Taiwan Blue-Green spectrum (analogous to US Cook PVI)
LEANING_SPECTRUM = ["深綠", "偏綠", "中間", "偏藍", "深藍"]

DEFAULT_SOURCE_LEANINGS: dict[str, str] = dict(_TW_SOURCE_LEANINGS)
DEFAULT_DIET_MAP: dict[str, list[str]] = dict(_TW_DIET_MAP)

SERENDIPITY_RATE = 0.05  # 5% chance of cross-bubble article


# ── Political leaning utilities ──────────────────────────────────────

def _leaning_index(leaning: str) -> int:
    """Return the index on the political spectrum (0=Solid Dem ... 4=Solid Rep)."""
    try:
        return LEANING_SPECTRUM.index(leaning)
    except ValueError:
        return 2  # default to Tossup

def _leaning_distance(a: str, b: str) -> int:
    """Distance between two leanings on the spectrum (0-4)."""
    return abs(_leaning_index(a) - _leaning_index(b))

def _leaning_affinity(agent_leaning: str, article_leaning: str) -> float:
    """Score 0.0-1.0 for how well an article's leaning matches an agent's."""
    dist = _leaning_distance(agent_leaning, article_leaning)
    # Distance 0 → 1.0, 1 → 0.5, 2 → 0.0 (Left vs Right)
    return max(0.0, 1.0 - dist * 0.5)


# ── Diet rules ───────────────────────────────────────────────────────

def get_diet_rules() -> dict:
    """Return the current diet configuration."""
    if os.path.isfile(RULES_FILE):
        with open(RULES_FILE) as f:
            return json.load(f)
    return {
        "diet_map": DEFAULT_DIET_MAP,
        "source_leanings": DEFAULT_SOURCE_LEANINGS,
        "serendipity_rate": SERENDIPITY_RATE,
        "articles_per_agent": 3,
        "channel_weight": 0.5,        # 50% weight for media channel match
        "leaning_weight": 0.3,        # 30% weight for political leaning
        "recency_weight": 0.2,        # 20% weight for article freshness
        "demographic_weight": 1.0,    # multiplier for demographic affinity (1.0 = full effect, 0 = disabled)
        "read_penalty": 0.3,          # score multiplier for already-read articles (lower = stronger dedup)
        "district_news_count": 2,     # max local news articles per district per day
        "kol_probability": 0.4,       # probability of KOL post reaching an agent
        "custom_sources": [],         # [{name, url, leaning, channel, keywords}]
    }


def update_diet_rules(rules: dict) -> dict:
    """Persist updated diet rules."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(RULES_FILE, "w") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)
    return rules


# ── Time decay utilities ─────────────────────────────────────────────

def _recency_score(crawled_at: str | None, now: datetime | None = None) -> float:
    """Score 0.0-1.0 based on article freshness.

    Within 1 day → 1.0, 3 days → 0.7, 7 days → 0.4, older → 0.1.
    """
    if not crawled_at:
        return 0.5  # unknown age → neutral
    try:
        ts = datetime.fromisoformat(crawled_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return 0.5
    if now is None:
        now = datetime.now(timezone.utc)
    age_hours = max(0, (now - ts).total_seconds() / 3600)
    if age_hours <= 24:
        return 1.0
    elif age_hours <= 72:
        return 0.7
    elif age_hours <= 168:
        return 0.4
    else:
        return 0.1


# ── Irrelevant article filter ────────────────────────────────────────

# Source / board patterns that indicate non-political content.
# Matched case-insensitively against title and source_tag.
_IRRELEVANT_BOARD_PATTERNS = [
    # Entertainment / Lifestyle
    "joke", "food", "beauty", "recipe", "celebrity", "gossip",
    # Sports
    "baseball", "nba", "nfl", "mma", "espn", "sports",
    # Media / Gaming
    "marvel", "movie", "drama", "youtube", "steam", "playstation", "nintendo",
    # Tech / Cars / Hardware (non-political)
    "car", "tech", "gadget", "hardware", "review",
    # Other non-political
    "fashion", "travel", "diy", "fitness",
]

# Same intent as `_IRRELEVANT_BOARD_PATTERNS` but in 繁中 — needed because
# the English-only list was a no-op against TW news (e.g. PTT/Dcard board
# names, 食譜 / 棒球 / 追星 titles), so non-political noise leaked into
# the agent feed and crowded out the actual political coverage.
_IRRELEVANT_BOARD_PATTERNS_ZH = [
    # 娛樂 / 八卦 / 生活
    "八卦", "閒聊", "笑話", "美食", "食譜", "美妝", "追星", "明星",
    # 運動
    "棒球", "中職", "籃球", "足球", "MLB", "PLG", "T1聯盟", "運動",
    # 影劇 / 遊戲
    "電影", "影劇", "戲劇", "韓劇", "日劇", "動漫", "遊戲", "電玩",
    # 3C / 汽車
    "汽車", "機車", "3C", "開箱", "評測", "硬體", "手機評",
    # 旅遊 / 健身 / 寵物
    "旅遊", "出國", "健身", "減肥", "寵物", "貓咪", "毛孩",
]

_IRRELEVANT_TITLE_KEYWORDS = [
    # Non-political content markers (EN)
    "[ad]", "[sponsored]", "[quiz]", "[video]", "[gallery]",
    # Product / consumer content
    "product review", "best deals", "gift guide", "coupon",
    # Entertainment
    "celebrity", "kardashian", "reality tv", "box office",
    # 繁中
    "[廣告]", "[業配]", "[抽獎]", "[影片]", "[圖輯]",
    "團購", "限時優惠", "折扣碼", "開箱文",
]

# Content-level keywords that indicate non-political articles even if the
# title looks political. Combined EN + ZH for parity across locales.
_NOISE_CONTENT_KEYWORDS = [
    # EN
    "product review", "best buy", "amazon deal",
    "coupon code", "promo code", "affiliate link",
    # ZH
    "蝦皮", "momo購物", "團購優惠", "業配文", "聯盟行銷",
]


def _is_relevant_article(article: dict) -> bool:
    """Return True if the article is likely politically relevant."""
    title = article.get("title", "")
    source = article.get("source_tag", "")
    summary = article.get("summary", "")

    # English board / source patterns (case-insensitive)
    title_l = title.lower()
    source_l = source.lower()
    for pattern in _IRRELEVANT_BOARD_PATTERNS:
        p_l = pattern.lower()
        if p_l in title_l or p_l in source_l:
            return False

    # 繁中 board / source patterns (case-sensitive — Chinese has no case)
    for pattern in _IRRELEVANT_BOARD_PATTERNS_ZH:
        if pattern in title or pattern in source:
            return False

    # Title keywords (EN markers are bracketed and case-sensitive; ZH is
    # case-sensitive by nature)
    for kw in _IRRELEVANT_TITLE_KEYWORDS:
        if kw in title or kw.lower() in title_l:
            return False

    # Check content-level noise (title + summary)
    text = title + " " + summary
    text_l = text.lower()
    for kw in _NOISE_CONTENT_KEYWORDS:
        if kw in text or kw.lower() in text_l:
            return False

    return True


# ── Semantic Categorization ──────────────────────────────────────────

def _categorize_article(title: str, summary: str) -> str:
    """Classify the article into a primary demographic impact category.

    Keywords intentionally cover both 繁中 and English so the
    classifier works on TW news (the original list was English-only,
    which silently labelled every Chinese article as "General" and
    disabled the demographic-affinity multiplier downstream).
    """
    text_l = (title + " " + summary).lower()
    text_zh = title + " " + summary

    cat_keywords_en = {
        "Economy": ["inflation", "economy", "stock", "wages", "gas price", "housing", "jobs", "unemployment", "gdp", "recession", "interest rate", "cost of living", "minimum wage"],
        "ForeignPolicy": ["china", "russia", "ukraine", "nato", "tariff", "trade war", "immigration", "border", "defense", "military", "sanctions", "diplomacy"],
        "Livelihood": ["traffic", "infrastructure", "school", "transit", "power outage", "childcare", "crime", "gun violence", "police", "scam", "fentanyl", "opioid"],
        "GenderSocial": ["abortion", "roe", "dobbs", "lgbtq", "gender", "metoo", "dei", "civil rights", "affirmative action", "voting rights"],
        "Politics": ["election", "congress", "senate", "supreme court", "president", "corruption", "impeach", "primary", "polling", "campaign", "legislation"],
    }
    cat_keywords_zh = {
        "Economy": ["通膨", "通貨膨脹", "經濟", "股市", "台積電", "薪資", "薪水", "加薪", "油價", "房價", "房市", "就業", "失業", "GDP", "衰退", "利率", "升息", "降息", "物價", "基本工資", "電費", "匯率", "央行"],
        "ForeignPolicy": ["中共", "中國", "兩岸", "美中", "美國", "日本", "韓國", "烏克蘭", "俄羅斯", "北約", "關稅", "貿易戰", "軍演", "國防", "軍購", "外交", "制裁", "AIT", "晶片戰"],
        "Livelihood": ["交通", "捷運", "高鐵", "停電", "供電", "停水", "學校", "教育部", "兒童", "托育", "治安", "詐騙", "毒品", "酒駕", "食安", "颱風", "地震", "豪雨", "醫療", "健保", "長照"],
        "GenderSocial": ["性別", "同婚", "同志", "LGBT", "MeToo", "性騷", "性侵", "婦女", "墮胎", "人權", "原住民", "新住民", "移工", "勞權"],
        "Politics": ["選舉", "立委", "立法院", "總統", "罷免", "公投", "貪污", "弊案", "民調", "政黨", "藍綠", "藍白合", "提名", "初選", "黨主席", "行政院"],
    }

    # Simple highest-match logic — combine EN + ZH hit counts per category
    best_cat = "General"
    max_hits = 0
    for cat in cat_keywords_en.keys():
        hits = sum(1 for kw in cat_keywords_en[cat] if kw in text_l)
        hits += sum(1 for kw in cat_keywords_zh.get(cat, []) if kw in text_zh)
        if hits > max_hits:
            max_hits = hits
            best_cat = cat

    return best_cat


def _demographic_affinity(agent: dict, category: str) -> float:
    """Calculate how strongly this agent cares about this category. Returns 0.0 to 1.5 multiplier.

    Accepts BOTH the legacy US 5-tier leaning labels and the TW 5-bucket
    labels (深綠 / 偏綠 / 中間 / 偏藍 / 深藍). The original code only
    matched US labels, which silently disabled every partisan-affinity
    boost for Taiwan agents. Occupation keywords likewise gained 繁中
    aliases (服務業 / 業務 / 金融 / 主管 …) so TW occupations contribute
    to economic-news affinity instead of falling through.
    """
    affinity = 1.0

    age_str = agent.get("context", {}).get("age", "40")
    try:
        age_num = int("".join(c for c in str(age_str) if c.isdigit()))
    except ValueError:
        age_num = 40

    gender = agent.get("context", {}).get("gender", "")
    occupation = agent.get("context", {}).get("occupation", "")
    leaning = agent.get("political_leaning", "Tossup")

    _strong_partisan = leaning in (
        "Solid Dem", "Solid Rep", "Lean Dem", "Lean Rep",   # legacy US
        "深綠", "偏綠", "深藍", "偏藍",                        # TW 5-bucket
    )

    if category == "Economy":
        if age_num > 40: affinity += 0.2
        occ_lower = (occupation or "").lower()
        en_hit = any(w in occ_lower for w in ["business", "finance", "manager", "sales", "service"])
        zh_hit = any(w in (occupation or "") for w in [
            "商", "業務", "金融", "銀行", "保險", "證券", "會計",
            "經理", "主管", "老闆", "服務業", "店員", "業務員",
        ])
        if en_hit or zh_hit: affinity += 0.3

    elif category == "ForeignPolicy":
        # Strong partisans and older generations track foreign policy more closely
        if _strong_partisan: affinity += 0.3
        if age_num > 50: affinity += 0.2

    elif category == "Livelihood":
        if 25 <= age_num <= 45: affinity += 0.3

    elif category == "GenderSocial":
        if age_num < 35: affinity += 0.4
        # Female agents care more on gender-social (TW persona uses "女" too)
        _g = (gender or "").strip()
        if _g and (_g.lower().startswith("f") or _g.startswith("女")):
            affinity += 0.3

    elif category == "Politics":
        if _strong_partisan: affinity += 0.2

    return min(affinity, 1.8)  # Cap the multiplier


# ── Domain-aware article helpers (PR-1: 2026-04-18) ─────────────────

def _article_domain(article: dict) -> str:
    """Extract the domain of an article's source URL.

    Prefers explicit ``source_domain`` if set by upstream (e.g. site_scoped_search);
    falls back to parsing ``link`` / ``url`` field.
    """
    if article.get("source_domain"):
        return article["source_domain"].lower().removeprefix("www.")
    from urllib.parse import urlparse
    url = article.get("link") or article.get("url") or ""
    if not url:
        return ""
    return (urlparse(url).netloc or "").lower().removeprefix("www.")


def _article_leaning(article: dict) -> str:
    """Resolve an article's leaning using (in order, authoritative first):
       1. domain → DOMAIN_LEANING_MAP (authoritative, derived from Stage A-C pilots)
       2. source_tag → DEFAULT_SOURCE_LEANINGS (Chinese source name mapping)
       3. explicit ``source_leaning`` field (legacy; stale "中間" default in pre-Stage 8.3
          injected articles means this is only used as last resort before fallback)
       4. fallback '中間'

    Priority rationale: injected-article pools predating Stage 8.3 carry
    `source_leaning="中間"` as a hard default regardless of actual leaning.
    Domain / source_tag are more reliable because they reflect the real source.
    """
    # 1. Domain lookup (most authoritative)
    domain = _article_domain(article)
    if domain:
        by_domain = domain_to_leaning(domain)
        if by_domain:
            return by_domain
    # 2. Chinese source name lookup
    source_tag = article.get("source_tag") or article.get("source") or ""
    by_name = DEFAULT_SOURCE_LEANINGS.get(source_tag)
    if by_name:
        return by_name
    # 3. Explicit source_leaning (last resort — may be stale default)
    explicit = article.get("source_leaning")
    if explicit and explicit not in ("Tossup", "中間"):
        return explicit
    # 4. Fallback
    return "中間"


def sample_k_from(pool: list, k: int, rng) -> list:
    """Sample up to ``k`` items from ``pool`` using ``rng``. Safe for empty/small pools."""
    if not pool or k <= 0:
        return []
    k = min(k, len(pool))
    return rng.sample(pool, k)


def resolve_feed_for_agent(
    agent: dict,
    news_pool: list[dict],
    day: int,
    replication_seed: int = 0,
    target_n: int = 30,
) -> list[dict]:
    """Return the candidate article pool for an agent on a given simulation day.

    Uses MEDIA_HABIT_EXPOSURE_MIX as the target exposure distribution.
    For each leaning bucket, takes ``proportion × target_n`` articles
    (rounded, at most what the bucket has available), so the final list
    has the requested leaning mix regardless of pool-bucket size imbalances.

    RNG is seeded by (agent.id or person_id, day, replication_seed) so the
    same simulation can be reproduced exactly.

    Special case: 深藍 agents have no online 深藍 source; the 偏藍 bucket
    is restricted to DEEP_BLUE_FALLBACK_DOMAINS (chinatimes, tvbs, udn).

    Note: This is an additive, opinionated alternative to ``select_feed``.
    Evolution callers can opt in; existing code remains unchanged.
    """
    agent_id = agent.get("id") or agent.get("person_id") or agent.get("agent_id") or ""
    rng = random.Random(hash((str(agent_id), day, replication_seed)))

    # MEDIA_HABIT_EXPOSURE_MIX is keyed by 5-bucket political leaning (深綠/偏綠/
    # 中間/偏藍/深藍) — despite the legacy name. Real personas have `media_habit`
    # as consumption channel ("網路新聞"/"電視新聞"/...) and `party_lean` as the
    # political bucket. Read party_lean first; only fall back to media_habit if
    # its value happens to be a 5-bucket label (legacy / custom data).
    _bucket_labels = {"深綠", "偏綠", "中間", "偏藍", "深藍"}
    _raw_habit = agent.get("party_lean") or agent.get("media_habit") or "中間"
    leaning_bucket = _raw_habit if _raw_habit in _bucket_labels else "中間"
    mix = MEDIA_HABIT_EXPOSURE_MIX.get(leaning_bucket)
    if not mix:
        # Unknown leaning → return full pool (no filtering)
        return list(news_pool)

    # Pre-bucket articles by leaning once
    by_leaning: dict[str, list[dict]] = {l: [] for l in ("深綠", "偏綠", "中間", "偏藍", "深藍")}
    for a in news_pool:
        l = _article_leaning(a)
        if l in by_leaning:
            by_leaning[l].append(a)

    # For 深藍 agent: restrict their 偏藍 pool to DEEP_BLUE_FALLBACK_DOMAINS
    selected: list[dict] = []
    for leaning, proportion in mix.items():
        if proportion <= 0:
            continue
        pool = by_leaning.get(leaning, [])
        if leaning_bucket == "深藍" and leaning == "偏藍":
            # 深藍 fallback accepts article if EITHER:
            #   - its domain is in DEEP_BLUE_FALLBACK_DOMAINS (chinatimes/tvbs/udn), OR
            #   - its source_tag matches a top-partisan Chinese source name
            # This handles manual-inject articles without URLs (no domain available).
            _deep_blue_source_tags = {"中時新聞網", "中時電子報", "TVBS 新聞", "TVBS新聞", "聯合新聞網", "聯合報"}
            pool = [
                a for a in pool
                if _article_domain(a) in DEEP_BLUE_FALLBACK_DOMAINS
                or (a.get("source_tag") or a.get("source") or "") in _deep_blue_source_tags
            ]
        if not pool:
            continue
        # Determine count: proportion of target_n (min 1 when proportion > 0)
        k = max(1, round(proportion * target_n))
        selected.extend(sample_k_from(pool, k, rng))

    return selected


# ── Feed generation ──────────────────────────────────────────────────

def select_feed(
    agent: dict,
    news_pool: list[dict],
    rules: dict | None = None,
    read_history: set | None = None,
    current_day: int | None = None,
) -> list[dict]:
    """Pick N articles from the news pool for a specific agent.

    Uses a combined scoring approach:
      - Media channel match (agent's media_habit vs article source_tag)
      - Political leaning affinity (agent's political_leaning vs source leaning)
      - Time decay (newer articles score higher)
      - Demographic Affinity (Agent's Age/Gender vs Article Category)
      - Read dedup (articles the agent already read are penalised)
      - Temporal causality: when ``current_day`` is supplied, articles
        whose ``assigned_day`` is greater than the current sim day are
        excluded — agents cannot read "future" news. Articles without
        an ``assigned_day`` (e.g. legacy events, KOL posts) bypass the
        filter.
    """
    if not news_pool:
        return []

    # ── Strict temporal causality filter ───────────────────────────
    # Prevents agents on sim day N from reading articles assigned to
    # sim day N+1 or later. Critical under time compression where the
    # cycle's news pool spans many real days mapped onto few sim days.
    if current_day is not None:
        news_pool = [
            a for a in news_pool
            if a.get("assigned_day") is None or a.get("assigned_day") <= current_day
        ]
        if not news_pool:
            return []

    if rules is None:
        rules = get_diet_rules()

    diet_map = rules.get("diet_map", DEFAULT_DIET_MAP)
    source_leanings = rules.get("source_leanings", DEFAULT_SOURCE_LEANINGS)
    n = rules.get("articles_per_agent", 3)
    serendipity = rules.get("serendipity_rate", SERENDIPITY_RATE)
    channel_w = rules.get("channel_weight", 0.5)
    leaning_w = rules.get("leaning_weight", 0.3)
    recency_w = rules.get("recency_weight", 0.2)
    demo_w = rules.get("demographic_weight", 1.0)
    read_pen = rules.get("read_penalty", 0.3)

    # ── Determine agent preferences ─────────────────────────────────
    media_habit = agent.get("media_habit") or ""
    agent_leaning = agent.get("political_leaning") or "中間"

    preferred_tags: set[str] = set()
    for habit_key, tag_list in diet_map.items():
        if habit_key in media_habit:
            preferred_tags.update(tag_list)

    # Fallback to mainstream TW neutral outlets if no match.
    # Deliberately excludes 社群媒體 / PTT/論壇 sources — agents without a
    # specified social-media habit should NOT be exposed to PTT / Dcard /
    # LINE Today content (those are only for personas who actively read them).
    if not preferred_tags:
        preferred_tags = {"中央通訊社", "公視新聞", "關鍵評論網", "聯合新聞網"}

    now = datetime.now(timezone.utc)

    def _fuzzy_match_source(source_tag: str, known_names: set[str]) -> str | None:
        """Fuzzy match a Serper source_tag to a known diet_map source name.
        E.g. 'CNN Politics' matches 'CNN', 'Fox News Digital' matches 'Fox News'.
        """
        if source_tag in known_names:
            return source_tag
        tag_lower = source_tag.lower()
        for name in known_names:
            name_lower = name.lower()
            if len(name_lower) >= 3 and (name_lower in tag_lower or tag_lower in name_lower):
                return name
        return None

    # Build set of all known source names for fuzzy matching
    _all_known_sources = set(source_leanings.keys())
    for tag_list in diet_map.values():
        _all_known_sources.update(tag_list)

    # ── Score each article ──────────────────────────────────────────
    scored: list[tuple[float, dict]] = []
    for article in news_pool:
        # Skip irrelevant articles (PTT jokes, food reviews, etc.)
        if not _is_relevant_article(article):
            continue

        tag = article.get("source_tag", "")
        # Fuzzy match source_tag to known names for both channel and leaning scoring
        matched_name = _fuzzy_match_source(tag, _all_known_sources)
        effective_tag = matched_name or tag

        art_leaning = (
            article.get("source_leaning")
            or source_leanings.get(effective_tag, source_leanings.get(tag, "Tossup"))
        )

        # Channel match: 1.0 if in preferred set (fuzzy), 0.0 if not
        # Special: injected articles always get delivered (prediction scenarios)
        if tag in ("Scenario inject", "Manual inject"):
            channel_score = 1.0
            rec_score = 1.0  # Always fresh
        else:
            channel_score = 1.0 if effective_tag in preferred_tags else 0.0
            # Time decay: newer articles score higher
            rec_score = _recency_score(article.get("crawled_at"), now)

        # Political leaning affinity
        leaning_score = _leaning_affinity(agent_leaning, art_leaning)
        
        # Demographic Topical Affinity
        art_category = _categorize_article(article.get("title", ""), article.get("summary", ""))
        demo_mult = _demographic_affinity(agent, art_category)

        # Combined score
        base_total = channel_w * channel_score + leaning_w * leaning_score + recency_w * rec_score
        # Apply demographic affinity as interpolated multiplier (0=no effect, 1=full effect)
        effective_demo = 1.0 + (demo_mult - 1.0) * demo_w
        total = base_total * effective_demo

        # Candidate boost: articles mentioning tracked candidates get priority
        # This ensures candidate news reaches agents despite competing with general news
        _title_summary = (article.get("title", "") + " " + article.get("summary", "")).lower()
        _tracked = rules.get("tracked_candidate_names", []) if rules else []
        if any(cn in _title_summary for cn in _tracked):
            total *= 1.8  # significant boost for candidate-related articles

        # Read dedup: penalise articles the agent already saw
        if read_history and article.get("article_id") in read_history:
            total *= read_pen

        scored.append((total, article))

    # Sort by score descending, with some randomness for equal scores
    random.shuffle(scored)  # shuffle first for tiebreaking
    scored.sort(key=lambda x: x[0], reverse=True)

    # If pool is smaller than N, just return all
    if len(scored) <= n:
        return [a for _, a in scored]

    # Add jitter when scores are too uniform (common with scenario injection)
    unique_scores = set(s for s, _ in scored)
    if len(unique_scores) <= 2:
        scored = [(s + random.uniform(-0.2, 0.2), a) for s, a in scored]
        scored.sort(key=lambda x: x[0], reverse=True)

    # ── Pick top-N with serendipity ─────────────────────────────────
    high_score = [a for s, a in scored if s >= 0.5]
    low_score = [a for s, a in scored if s < 0.5]

    feed: list[dict] = []
    for _ in range(n):
        # Serendipity: small chance to pick from low-scoring articles
        if low_score and random.random() < serendipity:
            pick = random.choice(low_score)
            low_score.remove(pick)
        elif high_score:
            pick = high_score.pop(0)
        elif low_score:
            pick = low_score.pop(0)
        else:
            break
        feed.append(pick)

    return feed


def preview_feed(agent: dict, news_pool: list[dict]) -> dict:
    """Preview what a specific agent would see today."""
    feed = select_feed(agent, news_pool)
    return {
        "agent_id": agent.get("person_id"),
        "media_habit": agent.get("media_habit", ""),
        "political_leaning": agent.get("political_leaning", "Tossup"),
        "articles_count": len(feed),
        "articles": feed,
    }
