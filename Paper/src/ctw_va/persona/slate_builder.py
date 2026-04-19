"""Persona slate builder — deterministic stratified sampling (spec §A3).

Rule-based generator for CTW-VA-2026. NO LLM calls.

Marginal distributions sourced from:
  - party_lean_5: TEDS 2024 post-election weighting (provisional; user to
    replace with authoritative file if available — see TODO).
  - ethnicity: 客委會 2021 + 原民會 2024 統計 + 移民署 2024.
  - county / age / gender / education / occupation / income / media_habit:
    主計總處普查 + 戶政司月報 + TEDS 2024.

Algorithm:
    1. Compute exact integer quotas for each dimension's marginal distribution.
    2. Build a list of N slots, fill each dimension independently using
       seeded RNG permutations of the quota list.
    3. Joint distribution is product of marginals (simplifying assumption
       for N=300; note in paper limitations).
    4. Assign persona_id "p_000001"..."p_000300", sort by persona_id.
    5. Write JSONL with sort_keys=True for byte-identical reproducibility.

Two calls with same seed → byte-identical file → same SHA-256.
"""
from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..data.schemas import Person


def _stable_seed(*parts) -> int:
    """Deterministic cross-process seed from arbitrary parts.

    Python's built-in hash() is randomized per-process (PYTHONHASHSEED), so
    we use blake2b over stringified parts to get process-independent seeds.
    Byte-identical slates across CLI invocations depend on this.
    """
    h = hashlib.blake2b(
        "|".join(str(p) for p in parts).encode("utf-8"), digest_size=8
    )
    return int.from_bytes(h.digest(), "big", signed=False)


# ── Target marginal distributions ───────────────────────────────────

# Political leaning (spec §A3 acceptance: ±2%)
PARTY_LEAN_5_RATIOS = {
    "深綠": 0.19,
    "偏綠": 0.15,
    "中間": 0.33,
    "偏藍": 0.21,
    "深藍": 0.12,
}

# Ethnicity (spec §A3 acceptance: ±1%)
ETHNICITY_RATIOS = {
    "Hoklo":    0.70,
    "Hakka":    0.15,
    "外省":     0.10,
    "原住民":   0.025,
    "新住民":   0.025,
}

# County — top 6 cities (2024 投票權人口) + 16 others proportional
COUNTY_RATIOS = {
    "新北市":   0.136,
    "臺中市":   0.120,
    "高雄市":   0.110,
    "臺北市":   0.104,
    "桃園市":   0.096,
    "臺南市":   0.078,
    "彰化縣":   0.050,
    "屏東縣":   0.033,
    "雲林縣":   0.028,
    "新竹縣":   0.024,
    "苗栗縣":   0.023,
    "嘉義縣":   0.022,
    "南投縣":   0.020,
    "宜蘭縣":   0.019,
    "新竹市":   0.019,
    "基隆市":   0.015,
    "花蓮縣":   0.014,
    "嘉義市":   0.011,
    "臺東縣":   0.009,
    "澎湖縣":   0.004,
    "金門縣":   0.005,
    "連江縣":   0.000,   # sparse; 300 × 0.0005 ≈ 0
}

AGE_RATIOS = {
    "20-24": 0.10,
    "25-34": 0.15,
    "35-44": 0.18,
    "45-54": 0.17,
    "55-64": 0.17,
    "65+":   0.23,
}

GENDER_RATIOS = {"男": 0.4966, "女": 0.5034}

EDUCATION_RATIOS = {
    "國小以下":     0.13,
    "國中":         0.11,
    "高中職":       0.29,
    "專科大學":     0.37,
    "研究所":       0.10,
}

OCCUPATION_RATIOS = {
    "服務業":       0.42,
    "工業":         0.29,
    "農林漁牧":     0.04,
    "公教":         0.12,
    "學生":         0.08,
    "退休/無業":    0.05,
}

HOUSEHOLD_INCOME_RATIOS = {
    "3萬以下":      0.15,
    "3-5萬":        0.20,
    "5-8萬":        0.28,
    "8-12萬":       0.20,
    "12-20萬":      0.12,
    "20萬以上":     0.05,
}

MEDIA_HABIT_RATIOS = {
    "網路新聞":     0.35,
    "電視新聞":     0.30,
    "社群媒體":     0.20,
    "報紙":         0.07,
    "廣播":         0.05,
    "PTT/論壇":     0.03,
}


# ── Deterministic allocation ─────────────────────────────────────────

def _build_quota_list(ratios: dict[str, float], n: int) -> list[str]:
    """Produce exactly n items distributed per marginal ratios (largest-remainder rounding).

    Guarantees sum(counts) == n. Output list is ordered (largest ratio first) —
    caller must shuffle with seeded RNG for random assignment.
    """
    # Stage 1: floor-round each ratio × n; record remainder
    raw = {k: v * n for k, v in ratios.items()}
    floor_counts = {k: int(v) for k, v in raw.items()}
    remainders = sorted(
        ((k, raw[k] - floor_counts[k]) for k in raw),
        key=lambda kv: -kv[1],
    )
    # Stage 2: distribute residual one-by-one to largest remainder
    residual = n - sum(floor_counts.values())
    for i in range(residual):
        k, _ = remainders[i % len(remainders)]
        floor_counts[k] += 1
    # Assertion
    if sum(floor_counts.values()) != n:
        raise RuntimeError(f"quota allocation off: {floor_counts}")
    # Expand to list
    items: list[str] = []
    for k, c in floor_counts.items():
        items.extend([k] * c)
    return items


def _generate_township(county: str, rng: random.Random) -> str:
    """Produce a plausible township (admin_key form) for given county.

    Paper uses generic suffix pattern since full township census is in main
    Civatas (not standalone). For N=300 this is sufficient — the experiment
    uses county-level news feeds.
    """
    _generic_suffixes = {
        "臺北市": ["大安區", "中正區", "士林區", "松山區", "信義區", "內湖區", "文山區", "北投區", "中山區", "大同區", "萬華區", "南港區"],
        "新北市": ["板橋區", "三重區", "中和區", "新店區", "永和區", "土城區", "樹林區", "新莊區", "淡水區", "汐止區"],
        "桃園市": ["桃園區", "中壢區", "平鎮區", "八德區", "龜山區", "蘆竹區", "楊梅區"],
        "臺中市": ["北區", "西屯區", "北屯區", "南屯區", "大里區", "太平區", "豐原區", "沙鹿區"],
        "臺南市": ["中西區", "東區", "北區", "南區", "安平區", "安南區", "永康區", "仁德區"],
        "高雄市": ["三民區", "鳳山區", "前鎮區", "苓雅區", "左營區", "楠梓區", "鼓山區", "小港區"],
    }
    suffixes = _generic_suffixes.get(county, [county.replace("縣", "").replace("市", "") + "市區"])
    return f"{county}|{rng.choice(suffixes)}"


def _age_int_from_bucket(bucket: str, rng: random.Random) -> int:
    if bucket == "20-24": return rng.randint(20, 24)
    if bucket == "25-34": return rng.randint(25, 34)
    if bucket == "35-44": return rng.randint(35, 44)
    if bucket == "45-54": return rng.randint(45, 54)
    if bucket == "55-64": return rng.randint(55, 64)
    if bucket == "65+":   return rng.randint(65, 85)
    return 45


def build_slate(n: int = 300, seed: int = 20240113) -> list[Person]:
    """Produce a deterministic slate of N personas.

    Same (n, seed) → identical Person list (same order, same field values).
    Ordering: sorted by persona_id ascending (p_000001..p_00000N).
    """
    rng = random.Random(seed)

    # Build quota lists for each dimension; shuffle each independently.
    dims: dict[str, list[str]] = {
        "party_lean":       _build_quota_list(PARTY_LEAN_5_RATIOS, n),
        "ethnicity":        _build_quota_list(ETHNICITY_RATIOS, n),
        "county":           _build_quota_list(COUNTY_RATIOS, n),
        "age_bucket":       _build_quota_list(AGE_RATIOS, n),
        "gender":           _build_quota_list(GENDER_RATIOS, n),
        "education":        _build_quota_list(EDUCATION_RATIOS, n),
        "occupation":       _build_quota_list(OCCUPATION_RATIOS, n),
        "household_income": _build_quota_list(HOUSEHOLD_INCOME_RATIOS, n),
        "media_habit":      _build_quota_list(MEDIA_HABIT_RATIOS, n),
    }
    for key in dims:
        sub_rng = random.Random(_stable_seed(seed, key, "dim_shuffle"))
        sub_rng.shuffle(dims[key])

    personas: list[Person] = []
    for i in range(n):
        age_bucket = dims["age_bucket"][i]
        county = dims["county"][i]
        # Deterministic but diversified township: seed with (seed, i, county)
        tr_rng = random.Random(_stable_seed(seed, i, county, "township"))
        age_rng = random.Random(_stable_seed(seed, i, age_bucket, "age_int"))
        township = _generate_township(county, tr_rng)
        age = _age_int_from_bucket(age_bucket, age_rng)

        personas.append(Person(
            person_id=f"p_{i+1:06d}",
            age=age,
            gender=dims["gender"][i],
            county=county,
            township=township,
            education=dims["education"][i],
            occupation=dims["occupation"][i],
            ethnicity=dims["ethnicity"][i],
            household_income=dims["household_income"][i],
            party_lean=dims["party_lean"][i],
            media_habit=dims["media_habit"][i],
        ))

    # Sort by persona_id for byte-identical output
    personas.sort(key=lambda p: p.person_id)
    return personas


def write_slate_jsonl(personas: list[Person], output_path: str | Path) -> dict[str, Any]:
    """Write slate as JSONL (sort_keys=True per row), compute SHA-256.

    Returns {"count": int, "sha256": str, "slate_id": str, "path": str}.
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for p in personas:
            f.write(json.dumps(asdict(p), ensure_ascii=False, sort_keys=True) + "\n")

    h = hashlib.sha256(out.read_bytes()).hexdigest()
    return {
        "count": len(personas),
        "sha256": h,
        "slate_id": h[:16],
        "path": str(out),
    }


def verify_distributions(personas: list[Person]) -> dict[str, dict[str, float]]:
    """Return observed marginal distributions for each dimension."""
    from collections import Counter
    n = len(personas)
    by_dim = {
        "party_lean":   Counter(p.party_lean for p in personas),
        "ethnicity":    Counter(p.ethnicity for p in personas),
        "county":       Counter(p.county for p in personas),
        "gender":       Counter(p.gender for p in personas),
    }
    return {dim: {k: v / n for k, v in c.items()} for dim, c in by_dim.items()}
