"""Build Taiwan election templates from data/census + data/elections output.

Produces up to 31 template files under data/templates/:

  [A] National presidential (5):
      presidential_national_generic.json   三黨 generic 模板
      presidential_2024.json                賴清德 vs 侯友宜 vs 柯文哲（回測用）
      presidential_2028_lai_vs_lu.json      賴清德 vs 盧秀燕
      presidential_2028_lai_vs_cheng.json   賴清德 vs 鄭麗文
      presidential_2028_lai_vs_chiang.json  賴清德 vs 蔣萬安

  [B] Public opinion poll (1):
      poll_2028_preferred_candidate.json    7 人民調（賴/蕭/黃/盧/蔣/韓/鄭）

  [C] 2026 三都市長選舉 (3):
      mayor_2026_taipei.json       蔣萬安（KMT）vs 沈伯洋（DPP）          藍白合→無 TPP
      mayor_2026_taichung.json     江啟臣（KMT）vs 何欣純（DPP）vs 麥玉珍（TPP）
      mayor_2026_kaohsiung.json    柯志恩（KMT）vs 賴瑞隆（DPP）

  [D] 22 single-county presidential (22):
      presidential_county_<NAME>.json       每個縣市的獨立 template

Run:
    python3 scripts/build_templates.py --all
    python3 scripts/build_templates.py --national
    python3 scripts/build_templates.py --poll
    python3 scripts/build_templates.py --mayors
    python3 scripts/build_templates.py --counties

Schema (both national and county scope share the same backbone):

  {
    "name": str, "name_zh": str,
    "region": str, "region_code": str, "country": "TW", "locale": "zh-TW",
    "target_count": int,
    "metadata": {sources, bucket_counts, population_total, …},
    "dimensions": {
      gender, age, county, township, education, employment,
      tenure, household_type, household_income, ethnicity,
      party_lean (5-bucket 深綠/偏綠/中間/偏藍/深藍)
    },
    "election": {                     # optional per template
      type, scope, cycle, candidates[], party_palette, party_detection,
      default_macro_context, default_search_keywords, default_calibration_params,
      default_kol, default_poll_groups, party_base_scores, default_sampling_modality,
      default_evolution_window
    }
  }
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CENSUS = ROOT / "data" / "census"
ELEC = ROOT / "data" / "elections"
TPL = ROOT / "data" / "templates"


# ─────────────────────────── helpers ───────────────────────────

def round_weights(pairs: list[tuple[str, float]]) -> list[dict]:
    """Normalize weights to sum=1.0 (4dp). Residual is absorbed into the largest."""
    total = sum(w for _, w in pairs)
    if total <= 0:
        return [{"value": v, "weight": 0.0} for v, _ in pairs]
    rounded = [(v, round(w / total, 4)) for v, w in pairs]
    diff = round(1.0 - sum(w for _, w in rounded), 4)
    if diff != 0 and rounded:
        idx = max(range(len(rounded)), key=lambda i: rounded[i][1])
        v, w = rounded[idx]
        rounded[idx] = (v, round(w + diff, 4))
    return [{"value": v, "weight": w} for v, w in rounded]


def sum_dim(entries: list[dict], dim: str) -> dict[str, int]:
    """Sum each bucket of `dim` across a list of summaries."""
    out: dict[str, int] = {}
    for e in entries:
        block = e.get(dim, {})
        for k, v in block.items():
            if isinstance(v, (int, float)):
                out[k] = out.get(k, 0) + v
    return out


# ───────────────── dimension builder (shared) ─────────────────

GENDER_VALUES = [("男", "gender.Male"), ("女", "gender.Female")]
AGE_VALUES = ["未滿18歲", "18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
EDU_VALUES = ["國小以下", "國中", "高中職", "專科大學", "研究所"]
EMPLOY_VALUES = ["就業", "失業", "非勞動力"]
TENURE_VALUES = ["自有住宅", "租屋", "其他"]
HOUSEHOLD_TYPE_VALUES = ["家庭戶", "非家庭戶"]
INCOME_VALUES = ["3萬以下", "3-5萬", "5-8萬", "8-12萬", "12-20萬", "20萬以上"]
ETHNICITY_VALUES = ["閩南", "客家", "外省", "原住民", "新住民", "其他"]
PARTY_LEAN_VALUES = ["深綠", "偏綠", "中間", "偏藍", "深藍"]
MEDIA_HABIT_VALUES = ["電視新聞", "網路新聞", "社群媒體", "報紙", "PTT/論壇", "廣播"]
MEDIA_HABIT_DEFAULT = [0.28, 0.32, 0.22, 0.05, 0.08, 0.05]


def build_dimensions(
    census_entries: list[dict],
    leaning: dict,
    include_county: bool = True,
    include_township: bool = True,
) -> tuple[dict, dict]:
    """Given a list of census summaries (counties or townships), compose
    categorical/range dimensions and return (dims, metadata_summary)."""
    pop_total = sum(e["population_total"] for e in census_entries)

    # Gender (from census entry.gender)
    gender = sum_dim(census_entries, "gender")
    gender_dim = {
        "type": "categorical",
        "categories": round_weights([("男", gender.get("Male", 0)), ("女", gender.get("Female", 0))]),
    }

    # Age (labels already in Chinese in census)
    age = sum_dim(census_entries, "age")
    age_dim = {
        "type": "range",
        "bins": [{"range": k, "weight": w["weight"]}
                 for k, w in zip(AGE_VALUES, round_weights([(k, age.get(k, 0)) for k in AGE_VALUES]))],
    }

    # Education
    edu = sum_dim(census_entries, "education_15plus")
    edu_dim = {
        "type": "categorical",
        "categories": round_weights([(k, edu.get(k, 0)) for k in EDU_VALUES]),
    }

    # Employment
    emp = sum_dim(census_entries, "employment_15plus")
    emp_dim = {
        "type": "categorical",
        "categories": round_weights([(k, emp.get(k, 0)) for k in EMPLOY_VALUES]),
    }

    # Tenure
    tenure = sum_dim(census_entries, "tenure")
    tenure_dim = {
        "type": "categorical",
        "categories": round_weights([(k, tenure.get(k, 0)) for k in TENURE_VALUES]),
    }

    # Household type
    ht = sum_dim(census_entries, "household_type")
    ht_dim = {
        "type": "categorical",
        "categories": round_weights([(k, ht.get(k, 0)) for k in HOUSEHOLD_TYPE_VALUES]),
    }

    # Household income
    inc = sum_dim(census_entries, "household_income")
    inc_dim = {
        "type": "categorical",
        "categories": round_weights([(k, inc.get(k, 0)) for k in INCOME_VALUES]),
    }

    # Ethnicity
    eth = sum_dim(census_entries, "ethnicity")
    eth_dim = {
        "type": "categorical",
        "categories": round_weights([(k, eth.get(k, 0)) for k in ETHNICITY_VALUES]),
    }

    # Party lean (derived from leaning profile; weight by township population)
    # Map township → bucket → pop, aggregated.
    bucket_pop: dict[str, float] = {k: 0.0 for k in PARTY_LEAN_VALUES}
    pvi_towns = leaning["townships"]
    # index census entries by admin_key (township-level) or by county (for county-aggregate)
    for e in census_entries:
        admin_key = e.get("admin_key") or f"{e.get('county','')}|"
        if admin_key in pvi_towns:
            bucket = pvi_towns[admin_key]["bucket"]
            bucket_pop[bucket] = bucket_pop.get(bucket, 0) + e["population_total"]
        else:
            # county-level aggregation: look up county in leaning.counties
            county = e.get("county", "")
            if county and county in leaning.get("counties", {}):
                bucket = leaning["counties"][county]["bucket"]
                bucket_pop[bucket] = bucket_pop.get(bucket, 0) + e["population_total"]
    lean_dim = {
        "type": "categorical",
        "categories": round_weights([(k, bucket_pop.get(k, 0)) for k in PARTY_LEAN_VALUES]),
    }

    # Media habit — national prior (no ACS equivalent; placeholder until survey wired)
    media_dim = {
        "type": "categorical",
        "categories": round_weights(list(zip(MEDIA_HABIT_VALUES, MEDIA_HABIT_DEFAULT))),
    }

    dims: dict[str, dict] = {
        "gender": gender_dim,
        "age": age_dim,
        "education": edu_dim,
        "employment": emp_dim,
        "tenure": tenure_dim,
        "household_type": ht_dim,
        "household_income": inc_dim,
        "ethnicity": eth_dim,
        "party_lean": lean_dim,
        "media_habit": media_dim,
    }

    # County-level geographic dimension (22 counties)
    if include_county:
        by_county: dict[str, float] = {}
        for e in census_entries:
            c = e.get("county", "")
            if c:
                by_county[c] = by_county.get(c, 0) + e["population_total"]
        counties_sorted = sorted(by_county.items(), key=lambda kv: -kv[1])
        dims["county"] = {
            "type": "categorical",
            "categories": round_weights(counties_sorted),
        }

    # Township-level dimension (full granularity, but clip weights < 1e-5 to keep JSON tidy)
    if include_township:
        township_pairs: list[tuple[str, float]] = []
        for e in census_entries:
            ak = e.get("admin_key") or (f"{e.get('county','')}|{e.get('township','')}" if e.get("township") else None)
            if ak:
                township_pairs.append((ak, float(e["population_total"])))
        dims["township"] = {
            "type": "categorical",
            "categories": round_weights(township_pairs),
        }

    summary = {
        "population_total": int(pop_total),
        "township_count": len([e for e in census_entries if e.get("admin_key")]) or None,
        "county_count": len({e.get("county") for e in census_entries if e.get("county")}),
        "bucket_counts": {k: sum(1 for e in census_entries
                                 if e.get("admin_key") in pvi_towns
                                 and pvi_towns[e["admin_key"]]["bucket"] == k)
                          for k in PARTY_LEAN_VALUES},
    }
    return dims, summary


# ─────────────── election block builders ───────────────

PARTY_PALETTE = {
    "DPP": ["#1B9431", "#63B83A", "#1A5C2F"],  # 綠營
    "KMT": ["#000095", "#3358D4", "#07124E"],  # 藍營
    "TPP": ["#28C8C8", "#79E0E0", "#1A8A8A"],  # 白營（偏青）
    "IND": ["#6B7280", "#9CA3AF", "#4B5563"],  # 獨立/無黨籍
}

PARTY_DETECTION_ZH = {
    "DPP": ["民進黨", "民主進步黨", "民進", "綠營", "綠色", "DPP"],
    "KMT": ["國民黨", "中國國民黨", "國民", "藍營", "藍色", "KMT"],
    "TPP": ["民眾黨", "台灣民眾黨", "民眾", "白營", "白色力量", "TPP"],
    "IND": ["無黨籍", "無黨", "獨立"],
}


def party_code_to_lean_bucket(code: str) -> str:
    """Map party code to which 5-bucket it primarily draws from."""
    return {"DPP": "深綠", "KMT": "深藍", "TPP": "中間", "IND": "中間"}.get(code, "中間")


def _calibration_defaults(profile: str) -> dict:
    """Differentiated calibration params by template type.

    profile ∈ {"generic", "2024_backtest", "2028", "mayor", "county"}
    """
    # Note: news_mix_* are 0-100 integer percentages (sum should = 100).
    # The UI slider expects integers; 0-1 floats would floor to 0 and break
    # the mix totaliser.
    base = {
        "news_impact": 2.0,
        "serendipity_rate": 0.05,
        "articles_per_agent": 3,
        "forget_rate": 0.1,
        "delta_cap_mult": 1.0,
        "satisfaction_decay": 0.04,
        "anxiety_decay": 0.05,
        "base_undecided": 0.12,
        "max_undecided": 0.25,
        "party_align_bonus": 15,
        "incumbency_bonus": 8,
        "individuality_multiplier": 1.0,
        "neutral_ratio": 0.3,
        "news_mix_candidate": 20,
        "news_mix_national": 45,
        "news_mix_local": 25,
        "news_mix_international": 10,
        "shift_sat_low_threshold": 25,
        "shift_anx_high_threshold": 75,
        "shift_consecutive_days_req": 5,
        "negativity_dampen": 0.70,
        "positivity_boost": 1.30,
    }
    if profile == "2024_backtest":
        # 2024 回測：候選人新聞占比高（使用者常想驗證特定候選人）
        return {**base, "news_impact": 2.5, "base_undecided": 0.08,
                "shift_consecutive_days_req": 7,
                "news_mix_candidate": 35, "news_mix_national": 35,
                "news_mix_local": 20, "news_mix_international": 10}
    if profile == "2028":
        # 2028 推測：情境更開放（高 base_undecided），候選人比例略高
        return {**base, "news_impact": 1.8, "base_undecided": 0.22,
                "incumbency_bonus": 5, "shift_consecutive_days_req": 4,
                "news_mix_candidate": 25, "news_mix_national": 40,
                "news_mix_local": 25, "news_mix_international": 10}
    if profile == "mayor":
        # 直轄市長：本地新聞占比大幅提高（城市 vs 中央政策）
        return {**base, "news_impact": 2.2, "incumbency_bonus": 12,
                "news_mix_candidate": 25, "news_mix_national": 25,
                "news_mix_local": 45, "news_mix_international": 5}
    if profile == "county":
        # 單一縣市回測：地方新聞主導
        return {**base, "news_impact": 2.2,
                "news_mix_candidate": 20, "news_mix_national": 30,
                "news_mix_local": 45,
                "news_mix_international": 5}
    return base  # generic


def _build_election_block(
    *,
    etype: str,
    scope: str,
    cycle: int | None,
    is_generic: bool,
    candidates: list[dict],
    calib_profile: str,
    macro_en: str,
    macro_zh: str,
    local_keywords: list[str],
    national_keywords: list[str],
    election_window: tuple[str, str] | None = None,
    sampling_modality: str = "mixed_73",
    use_electoral: bool = False,  # Taiwan has no EC; retained for cross-template schema
) -> dict:
    parties_used = {c["party"] for c in candidates}
    palette = {p: PARTY_PALETTE.get(p, PARTY_PALETTE["IND"]) for p in parties_used}
    detection = {p: PARTY_DETECTION_ZH.get(p, []) for p in parties_used}

    base_scores = {"DPP": 50, "KMT": 50, "TPP": 30, "IND": 25}
    party_base_scores = {p: base_scores.get(p, 30) for p in parties_used}

    poll_groups = [{"id": "likely_voters", "name_zh": "可能投票者", "name_en": "Likely Voters", "weight": 1.0}]

    return {
        "type": etype,
        "scope": scope,
        "cycle": cycle,
        "is_generic": is_generic,
        "candidates": candidates,
        "party_palette": palette,
        "party_detection": detection,
        "party_base_scores": party_base_scores,
        "default_macro_context": {"en": macro_en, "zh-TW": macro_zh},
        "default_search_keywords": {
            "local": local_keywords,
            "national": national_keywords,
        },
        "default_calibration_params": _calibration_defaults(calib_profile),
        "default_kol": {"enabled": True, "ratio": 0.06, "reach": 0.30},
        "default_poll_groups": poll_groups,
        "default_sampling_modality": sampling_modality,
        "default_evolution_window": list(election_window) if election_window else None,
        "use_electoral_college": use_electoral,  # False for TW (no EC, use county-level aggregation)
    }


# ─────────────── template composition ───────────────

def compose(name_en: str, name_zh: str, region: str, region_code: str,
            target_count: int, dims: dict, summary: dict,
            metadata_extra: dict, election: dict | None) -> dict:
    t = {
        "name": name_en,
        "name_zh": name_zh,
        "region": region,
        "region_code": region_code,
        "country": "TW",
        "locale": "zh-TW",
        "target_count": target_count,
        "metadata": {
            "source": {
                "geo": "g0v / ronnywang twgeojson (MOI segis 2011)",
                "demographics": "主計總處 110 年 人口及住宅普查 + 戶政司 2024 月報 + 客委會 2021 族群調查",
                "elections": "中選會 2024 總統大選鄉鎮級開票資料",
                "leaning": "Blue-Green PVI computed from 2024 two-party share",
            },
            **summary,
            **metadata_extra,
        },
        "dimensions": dims,
    }
    if election is not None:
        t["election"] = election
    return t


# ────────── candidate libraries ──────────

PRESIDENTIAL_2024 = [
    {"id": "lai", "name": "賴清德", "name_en": "William Lai",
     "party": "DPP", "party_label": "民進黨", "is_incumbent": False, "color": "#1B9431",
     "description": "民進黨籍，時任副總統，主張延續蔡英文政府路線、深化對美日合作與對中強硬；支持者偏向本土、年輕世代、南部地區。"},
    {"id": "hou", "name": "侯友宜", "name_en": "Hou Yu-ih",
     "party": "KMT", "party_label": "國民黨", "is_incumbent": False, "color": "#000095",
     "description": "國民黨籍，時任新北市長，主張兩岸和平、維持現狀、擁核；支持者偏向中高齡、北部藍營、傳統公務員族群。"},
    {"id": "ko", "name": "柯文哲", "name_en": "Ko Wen-je",
     "party": "TPP", "party_label": "民眾黨", "is_incumbent": False, "color": "#28C8C8",
     "description": "民眾黨籍，前台北市長，主張務實中間、藍綠皆批、科技治理；支持者偏向年輕、中產、科技業、對藍綠失望的中間選民。"},
]

# 2028 pairs — 賴清德連任 vs 藍營三位主要人選
LAI_2028 = {
    "id": "lai", "name": "賴清德", "name_en": "William Lai",
    "party": "DPP", "party_label": "民進黨", "is_incumbent": True, "color": "#1B9431",
    "description": "民進黨籍，時任總統尋求連任，主張延續台美合作、中小企業扶持、健保與社福擴張；執政成績是主要評價標的。",
}

LU_2028 = {
    "id": "lu", "name": "盧秀燕", "name_en": "Lu Shiow-yen",
    "party": "KMT", "party_label": "國民黨", "is_incumbent": False, "color": "#000095",
    "description": "國民黨籍，時任台中市長，被視為中南部藍營明日之星，主張實用治理、地方建設優先、兩岸對話；支持者偏向中台灣、女性、中間藍營。",
}

CHENG_LIWEN_2028 = {
    "id": "cheng", "name": "鄭麗文", "name_en": "Cheng Li-wun",
    "party": "KMT", "party_label": "國民黨", "is_incumbent": False, "color": "#07124E",
    "description": "國民黨籍，口才犀利的立法委員，媒體聲量高，立場鮮明批判民進黨；支持者偏向深藍鐵粉、北部年長族群。",
}

CHIANG_2028 = {
    "id": "chiang", "name": "蔣萬安", "name_en": "Chiang Wan-an",
    "party": "KMT", "party_label": "國民黨", "is_incumbent": False, "color": "#3358D4",
    "description": "國民黨籍，時任台北市長，蔣中正曾孫，形象年輕溫和，主張務實治理；支持者偏向北台灣、年輕藍營、外省二三代。",
}

# 7-人民調候選人（2028 民意調查 template）
POLL_2028_7 = [
    LAI_2028,
    {"id": "hsiao", "name": "蕭美琴", "name_en": "Hsiao Bi-khim",
     "party": "DPP", "party_label": "民進黨", "is_incumbent": True, "color": "#63B83A",
     "description": "民進黨籍，時任副總統，曾任駐美代表，外交形象強；支持者偏向綠營、國際化菁英、女性。"},
    {"id": "huang", "name": "黃國昌", "name_en": "Huang Kuo-chang",
     "party": "TPP", "party_label": "民眾黨", "is_incumbent": False, "color": "#28C8C8",
     "description": "民眾黨籍，時任立法院黨團總召，戰鬥力強，擅長國會監督；支持者偏向年輕、網路族群、對藍綠不滿的中間選民。"},
    LU_2028,
    CHIANG_2028,
    {"id": "han", "name": "韓國瑜", "name_en": "Han Kuo-yu",
     "party": "KMT", "party_label": "國民黨", "is_incumbent": True, "color": "#000095",
     "description": "國民黨籍，時任立法院長，高雄前市長，庶民魅力強；支持者偏向高齡、南部韓粉、中南部藍營基層。"},
    CHENG_LIWEN_2028,
]

# 2026 三都市長候選人
MAYOR_TAIPEI = [
    {"id": "chiang_mayor", "name": "蔣萬安", "name_en": "Chiang Wan-an",
     "party": "KMT", "party_label": "國民黨", "is_incumbent": True, "color": "#000095",
     "description": "國民黨籍，時任台北市長尋求連任，主打市政穩健、基層建設；支持者為北市傳統藍營、中高齡。"},
    {"id": "shen", "name": "沈伯洋", "name_en": "Puma Shen",
     "party": "DPP", "party_label": "民進黨", "is_incumbent": False, "color": "#1B9431",
     "description": "民進黨籍，時任不分區立委，黑熊學院創辦人，國防與反認知戰專業；支持者偏向年輕、進步派、網路族群。"},
]

MAYOR_TAICHUNG = [
    {"id": "chiang_ch", "name": "江啟臣", "name_en": "Johnny Chiang",
     "party": "KMT", "party_label": "國民黨", "is_incumbent": False, "color": "#000095",
     "description": "國民黨籍，時任立法院副院長、中市第八選區立委，國民黨初選勝出，形象年輕溫和、主打務實；支持者為台中藍營、中部中產。"},
    {"id": "ho", "name": "何欣純", "name_en": "Ho Hsin-chun",
     "party": "DPP", "party_label": "民進黨", "is_incumbent": False, "color": "#1B9431",
     "description": "民進黨籍，時任中市第七選區立委，蔡其昌陣營支持，主打地方深耕；支持者為台中綠營、南屯太平豐原地區。"},
    {"id": "mai", "name": "麥玉珍", "name_en": "Mai Yu-chen",
     "party": "TPP", "party_label": "民眾黨", "is_incumbent": False, "color": "#28C8C8",
     "description": "民眾黨籍，時任不分區立委，新住民代表，公開表態參選；支持者為新住民社群、年輕族群、中部白色力量。"},
]

MAYOR_KAOHSIUNG = [
    {"id": "ko_chihen", "name": "柯志恩", "name_en": "Ko Chih-en",
     "party": "KMT", "party_label": "國民黨", "is_incumbent": False, "color": "#000095",
     "description": "國民黨籍，時任立法委員，曾任淡江大學副校長，教育背景深，上屆大幅縮小高雄藍綠差距；支持者為高雄藍營、中上階層、教師族群。"},
    {"id": "lai_jui", "name": "賴瑞隆", "name_en": "Lai Jui-lung",
     "party": "DPP", "party_label": "民進黨", "is_incumbent": False, "color": "#1B9431",
     "description": "民進黨籍，時任高雄第八選區立委，民進黨初選勝出，高雄深耕多年；支持者為高雄綠營基層、鳳山小港前鎮旗津地區。"},
]


# ─────────────── builders per template type ───────────────

def _load_all() -> tuple[dict, dict, dict]:
    townships = json.loads((CENSUS / "townships.json").read_text(encoding="utf-8"))
    counties = json.loads((CENSUS / "counties.json").read_text(encoding="utf-8"))
    leaning = json.loads((ELEC / "leaning_profile_tw.json").read_text(encoding="utf-8"))
    return townships, counties, leaning


def build_national_presidential() -> list[Path]:
    townships, _counties, leaning = _load_all()
    tw_entries = list(townships.values())
    dims, summary = build_dimensions(tw_entries, leaning)
    paths = []

    common_kw_local = ["台北", "新北", "桃園", "台中", "台南", "高雄"]
    common_kw_national_2024 = ["賴清德", "侯友宜", "柯文哲", "總統", "大選", "政見"]
    common_kw_national_2028 = ["2028", "總統大選", "政見", "兩岸", "經濟"]

    # Generic
    generic_candidates = [
        {"id": "generic_dpp", "name": "民進黨候選人", "party": "DPP",
         "party_label": "民進黨", "is_incumbent": False, "color": "#1B9431",
         "description": "綠營 generic 候選人，主張維持現狀、對美合作、社福擴張。"},
        {"id": "generic_kmt", "name": "國民黨候選人", "party": "KMT",
         "party_label": "國民黨", "is_incumbent": False, "color": "#000095",
         "description": "藍營 generic 候選人，主張兩岸和平、穩健經濟、傳統價值。"},
        {"id": "generic_tpp", "name": "民眾黨候選人", "party": "TPP",
         "party_label": "民眾黨", "is_incumbent": False, "color": "#28C8C8",
         "description": "白營 generic 候選人，主張科技治理、實用中間、藍綠共批。"},
    ]
    elect = _build_election_block(
        etype="presidential", scope="national", cycle=None, is_generic=True,
        candidates=generic_candidates, calib_profile="generic",
        macro_en="Taiwan presidential election — generic scenario for any cycle.",
        macro_zh="台灣總統大選 — 通用情境，可套用於任一屆次。",
        local_keywords=common_kw_local,
        national_keywords=["總統", "大選", "民進黨", "國民黨", "民眾黨"],
        sampling_modality="unweighted",
    )
    t = compose("Taiwan Presidential — Generic", "台灣總統大選 — 通用模板",
                "台灣", "TW", 200, dims, summary, {}, elect)
    dest = TPL / "presidential_national_generic.json"
    dest.write_text(json.dumps(t, ensure_ascii=False, indent=2))
    paths.append(dest)

    # 2024 回測
    elect_2024 = _build_election_block(
        etype="presidential", scope="national", cycle=2024, is_generic=False,
        candidates=PRESIDENTIAL_2024, calib_profile="2024_backtest",
        macro_en="2024 Taiwan presidential election: William Lai (DPP) vs Hou Yu-ih (KMT) vs Ko Wen-je (TPP).",
        macro_zh="2024 總統大選：民進黨賴清德、國民黨侯友宜、民眾黨柯文哲三腳督。",
        local_keywords=common_kw_local,
        national_keywords=common_kw_national_2024,
        election_window=("2024-01-08", "2024-01-13"),
    )
    t = compose("Taiwan Presidential 2024", "2024 總統大選（賴侯柯）",
                "台灣", "TW", 200, dims, summary, {}, elect_2024)
    dest = TPL / "presidential_2024.json"
    dest.write_text(json.dumps(t, ensure_ascii=False, indent=2))
    paths.append(dest)

    # 2028 三組 head-to-head
    for slug, opp, label_suffix in [
        ("lai_vs_lu", LU_2028, "賴清德 vs 盧秀燕"),
        ("lai_vs_cheng", CHENG_LIWEN_2028, "賴清德 vs 鄭麗文"),
        ("lai_vs_chiang", CHIANG_2028, "賴清德 vs 蔣萬安"),
    ]:
        elect_2028 = _build_election_block(
            etype="presidential", scope="national", cycle=2028, is_generic=False,
            candidates=[LAI_2028, opp], calib_profile="2028",
            macro_en=f"2028 Taiwan presidential election scenario — William Lai (DPP) vs {opp['name_en']} ({opp['party']}).",
            macro_zh=f"2028 總統大選假設情境：{label_suffix}。兩強對決，無第三勢力候選人。",
            local_keywords=common_kw_local,
            national_keywords=common_kw_national_2028 + [LAI_2028["name"], opp["name"]],
            election_window=("2028-10-25", "2028-10-31"),
        )
        t = compose(f"Taiwan Presidential 2028 — {label_suffix}",
                    f"2028 總統大選 — {label_suffix}",
                    "台灣", "TW", 200, dims, summary, {}, elect_2028)
        dest = TPL / f"presidential_2028_{slug}.json"
        dest.write_text(json.dumps(t, ensure_ascii=False, indent=2))
        paths.append(dest)

    return paths


def build_poll() -> list[Path]:
    townships, _counties, leaning = _load_all()
    dims, summary = build_dimensions(list(townships.values()), leaning)
    elect = _build_election_block(
        etype="poll", scope="national", cycle=2028, is_generic=False,
        candidates=POLL_2028_7, calib_profile="2028",
        macro_en="2028 Taiwan presidential primary-style poll: which candidate do you prefer among 7 cross-party figures?",
        macro_zh="2028 總統大選民意調查 — 7 位跨黨派候選人中，您最屬意哪一位？（涵蓋民進黨賴/蕭、國民黨盧/蔣/韓/鄭、民眾黨黃）",
        local_keywords=["台北", "高雄", "台中"],
        national_keywords=["2028", "總統", "民調", "支持度", "最屬意"],
        election_window=("2026-01-01", "2028-01-13"),
    )
    t = compose("Taiwan 2028 Preferred Candidate Poll",
                "2028 最屬意總統候選人民調（7 人）",
                "台灣", "TW", 200, dims, summary,
                {"note": "This is a poll template — no electoral outcome, just preference ranking."},
                elect)
    dest = TPL / "poll_2028_preferred_candidate.json"
    dest.write_text(json.dumps(t, ensure_ascii=False, indent=2))
    return [dest]


def build_mayors() -> list[Path]:
    """3 個直轄市長 template (single-county scope)."""
    townships, _counties, leaning = _load_all()
    paths = []
    mayor_specs = [
        ("taipei", "臺北市", "Taipei", "台北市長選舉", "Taipei Mayor Election", MAYOR_TAIPEI,
         "2026 台北市長選舉：國民黨蔣萬安尋求連任，民進黨由沈伯洋挑戰。藍白合使本選區僅兩強對決。",
         "2026 Taipei mayoral race: incumbent Chiang Wan-an (KMT) vs challenger Puma Shen (DPP)."),
        ("taichung", "臺中市", "Taichung", "台中市長選舉", "Taichung Mayor Election", MAYOR_TAICHUNG,
         "2026 台中市長選舉：國民黨江啟臣（現任盧秀燕接班）、民進黨何欣純、民眾黨麥玉珍三強對決。",
         "2026 Taichung mayoral race: Johnny Chiang (KMT, successor to Lu Shiow-yen) vs Ho Hsin-chun (DPP) vs Mai Yu-chen (TPP)."),
        ("kaohsiung", "高雄市", "Kaohsiung", "高雄市長選舉", "Kaohsiung Mayor Election", MAYOR_KAOHSIUNG,
         "2026 高雄市長選舉：民進黨賴瑞隆、國民黨柯志恩對決。民進黨南台灣鐵票區能否守住是焦點。",
         "2026 Kaohsiung mayoral race: Lai Jui-lung (DPP) vs Ko Chih-en (KMT) in the southern DPP stronghold."),
    ]
    for slug, county_zh, _county_en, name_zh, name_en, candidates, macro_zh, macro_en in mayor_specs:
        townships_in = [t for t in townships.values() if t["county"] == county_zh]
        if not townships_in:
            print(f"  WARNING: no townships for {county_zh}, skipping")
            continue
        dims, summary = build_dimensions(townships_in, leaning,
                                          include_county=False, include_township=True)
        elect = _build_election_block(
            etype="mayoral", scope="county", cycle=2026, is_generic=False,
            candidates=candidates, calib_profile="mayor",
            macro_en=macro_en, macro_zh=macro_zh,
            local_keywords=[county_zh, county_zh[:-1] if county_zh.endswith("市") else county_zh],
            national_keywords=["2026", "九合一", "市長", "地方選舉"],
            election_window=("2026-11-21", "2026-11-28"),
        )
        t = compose(f"2026 {name_en}", f"2026 {name_zh}",
                    county_zh, county_zh, 150, dims, summary, {}, elect)
        dest = TPL / f"mayor_2026_{slug}.json"
        dest.write_text(json.dumps(t, ensure_ascii=False, indent=2))
        paths.append(dest)
    return paths


def build_counties() -> list[Path]:
    """22 縣市 single-county presidential template."""
    townships, _counties, leaning = _load_all()
    paths = []
    by_county: dict[str, list[dict]] = {}
    for t in townships.values():
        by_county.setdefault(t["county"], []).append(t)

    for county, ts in sorted(by_county.items()):
        dims, summary = build_dimensions(ts, leaning,
                                          include_county=False, include_township=True)
        # Use 2024 presidential candidates but scoped to this county.
        elect = _build_election_block(
            etype="presidential", scope="county", cycle=2024, is_generic=False,
            candidates=PRESIDENTIAL_2024, calib_profile="county",
            macro_en=f"2024 Taiwan presidential election — {county} single-county backtest.",
            macro_zh=f"2024 總統大選 — {county} 單一縣市回測（賴清德 vs 侯友宜 vs 柯文哲）。",
            local_keywords=[county],
            national_keywords=["賴清德", "侯友宜", "柯文哲", "總統", "大選"],
            election_window=("2024-01-08", "2024-01-13"),
        )
        # Sanitize slug: ASCII-safe fallback
        slug_map = {
            "臺北市": "taipei", "新北市": "new_taipei", "桃園市": "taoyuan",
            "臺中市": "taichung", "臺南市": "tainan", "高雄市": "kaohsiung",
            "基隆市": "keelung", "新竹市": "hsinchu_city", "嘉義市": "chiayi_city",
            "新竹縣": "hsinchu_county", "苗栗縣": "miaoli", "彰化縣": "changhua",
            "南投縣": "nantou", "雲林縣": "yunlin", "嘉義縣": "chiayi_county",
            "屏東縣": "pingtung", "宜蘭縣": "yilan", "花蓮縣": "hualien",
            "臺東縣": "taitung", "澎湖縣": "penghu", "金門縣": "kinmen",
            "連江縣": "lienchiang",
        }
        slug = slug_map.get(county, county)
        t_file = compose(f"2024 {county} Presidential", f"2024 {county} 總統大選",
                         county, county, 100, dims, summary,
                         {"parent_template": "presidential_2024.json"}, elect)
        dest = TPL / f"presidential_county_{slug}.json"
        dest.write_text(json.dumps(t_file, ensure_ascii=False, indent=2))
        paths.append(dest)
    return paths


# ───────────────── CLI ─────────────────

def main() -> int:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group()
    g.add_argument("--all", action="store_true", help="Build every template (default)")
    g.add_argument("--national", action="store_true", help="Only build the 5 national presidential templates")
    g.add_argument("--poll", action="store_true", help="Only build the 2028 poll template")
    g.add_argument("--mayors", action="store_true", help="Only build the 3 2026 municipal mayor templates")
    g.add_argument("--counties", action="store_true", help="Only build the 22 single-county presidential templates")
    args = p.parse_args()

    TPL.mkdir(parents=True, exist_ok=True)
    all_mode = args.all or not (args.national or args.poll or args.mayors or args.counties)

    produced: list[Path] = []
    if all_mode or args.national:
        print("[national] Building 5 presidential templates …")
        produced += build_national_presidential()
    if all_mode or args.poll:
        print("[poll] Building 1 民調 template …")
        produced += build_poll()
    if all_mode or args.mayors:
        print("[mayors] Building 3 市長 templates …")
        produced += build_mayors()
    if all_mode or args.counties:
        print("[counties] Building 22 single-county templates …")
        produced += build_counties()

    print()
    print(f"Total: {len(produced)} templates written to {TPL.relative_to(ROOT)}/")
    for path in produced:
        print(f"  {path.relative_to(ROOT)}  ({path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
