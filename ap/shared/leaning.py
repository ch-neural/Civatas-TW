"""Taiwan political leaning utilities — Blue/Green/White spectrum, 5-bucket PVI.

Canonical 5-bucket system (analogous to US Cook PVI):
    深綠 (Solid DPP)  — safe DPP
    偏綠 (Lean DPP)
    中間 (Tossup)
    偏藍 (Lean KMT)
    深藍 (Solid KMT)

White force (TPP / 民眾黨) 在政黨層級是獨立第三軸，不在 5-bucket 上。
Agents may still carry `白` / `中立` as legacy values — normalised below.
"""

from typing import Optional

# Canonical 5-bucket spectrum (preferred by compute_pvi.py + templates)
LEANING_SPECTRUM_5 = ["深綠", "偏綠", "中間", "偏藍", "深藍"]

# 3-tier spectrum (used by older data / simpler UI surfaces)
LEANING_SPECTRUM_3 = ["偏綠", "中間", "偏藍"]

# Party → primary bucket
PARTY_LEANING: dict[str, str] = {
    # 綠營
    "民主進步黨": "偏綠",
    "民進黨": "偏綠",
    "DPP": "偏綠",
    "時代力量": "偏綠",
    "台灣基進": "偏綠",
    "社民黨": "偏綠",
    # 藍營
    "中國國民黨": "偏藍",
    "國民黨": "偏藍",
    "KMT": "偏藍",
    "新黨": "偏藍",
    "親民黨": "偏藍",
    # 白色力量 — 視為中間 bucket（第三勢力不直接落在藍綠軸）
    "台灣民眾黨": "中間",
    "民眾黨": "中間",
    "TPP": "中間",
    # 其他
    "無黨籍": "中間",
    "獨立": "中間",
}

# 5-tier → 3-tier mapping
FIVE_TO_THREE: dict[str, str] = {
    "深綠": "偏綠",
    "偏綠": "偏綠",
    "中間": "中間",
    "偏藍": "偏藍",
    "深藍": "偏藍",
}

# Legacy labels used by pre-TW-revival code paths — normalise to canonical.
LEGACY_NORMALISE: dict[str, str] = {
    "強烈左派": "深綠",
    "偏左派": "偏綠",
    "中立": "中間",
    "偏右派": "偏藍",
    "強烈右派": "深藍",
    "偏白": "中間",  # TPP 支持者歸入中間 bucket
    "白": "中間",
    # English US-era buckets
    "Solid Dem": "深綠",
    "Lean Dem": "偏綠",
    "Tossup": "中間",
    "Lean Rep": "偏藍",
    "Solid Rep": "深藍",
}


def normalize_leaning(s: str) -> str:
    """Normalize any leaning string to the canonical 5-tier spectrum."""
    if not s:
        return "中間"
    s = s.strip()
    if s in LEANING_SPECTRUM_5:
        return s
    if s in LEGACY_NORMALISE:
        return LEGACY_NORMALISE[s]
    # Fuzzy matching — look for a canonical label as substring
    for label in LEANING_SPECTRUM_5:
        if label in s:
            return label
    return "中間"


def normalize_leaning_3(s: str) -> str:
    """Collapse to the 3-tier spectrum (偏綠/中間/偏藍)."""
    five = normalize_leaning(s)
    return FIVE_TO_THREE.get(five, "中間")


def leaning_distance(a: str, b: str) -> float:
    """Distance between two leanings on the 5-tier spectrum (0.0 to 1.0)."""
    a_norm = normalize_leaning(a)
    b_norm = normalize_leaning(b)
    idx = {label: i for i, label in enumerate(LEANING_SPECTRUM_5)}
    a_idx = idx.get(a_norm, 2)  # 中間 = index 2
    b_idx = idx.get(b_norm, 2)
    return abs(a_idx - b_idx) / 4.0  # max distance = 4 (深綠 ↔ 深藍)


def leaning_affinity(agent_leaning: str, article_leaning: Optional[str]) -> float:
    """Affinity score (0.0 to 1.0) between an agent and article leaning."""
    if not article_leaning:
        return 0.5  # neutral for unknown
    dist = leaning_distance(agent_leaning, article_leaning)
    return 1.0 - dist


def get_party_leaning(party_name: str) -> str:
    """Map a Taiwan political party name to its 5-bucket leaning."""
    return PARTY_LEANING.get(party_name, "中間")
