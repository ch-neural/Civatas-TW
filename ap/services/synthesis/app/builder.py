"""Population builder: joint-table sampling with marginal fallback."""
from __future__ import annotations

import random
import re
from collections import defaultdict

import numpy as np

from shared.schemas import Dimension, DimensionType, Person, ProjectConfig

# ── Chinese → English field name mapping ──────────────────────────────
# Only map dimensions that are CLEARLY personal attributes.
# Civatas-USA Stage 1.5+: added US dimension aliases
# (county / state / employment_status / household_tenure / media_habit / party_lean).
_DIM_TO_FIELD: dict[str, str] = {
    "gender": "gender", "性別": "gender",
    # Taiwan 3-level admin hierarchy: district is the free-form string;
    # county / township are the structured fields.
    "district": "district", "行政區": "district", "地區": "district", "區域": "district",
    "township": "township", "鄉鎮": "township", "鄉鎮市區": "township",
    "county": "county", "縣市": "county",
    "state": "county",   # legacy US fallback (state granularity maps to county here)
    "age": "age", "年齡": "age", "年齡層": "age",
    "education": "education", "教育程度": "education", "教育程度別": "education",
    "occupation": "occupation", "職業": "occupation", "職業別": "occupation",
    "經濟戶長職業別": "occupation",
    "employment": "occupation", "employment_status": "occupation",
    "household_type": "household_type", "家庭型態": "household_type",
    "tenure": "household_tenure",
    "household_tenure": "household_tenure",
    "marital_status": "marital_status", "婚姻狀態": "marital_status",
    # Taiwan ethnicity (primary); race / hispanic kept for legacy US data
    "ethnicity": "ethnicity", "族群": "ethnicity",
    "race": "race",
    "hispanic_or_latino": "hispanic_or_latino",
    "household_income": "household_income", "家戶所得": "household_income",
    "party_lean": "party_lean",
    "media_habit": "media_habit",
    "cross_strait": "cross_strait",
}

_PERSON_FIELDS = {
    "person_id", "age", "gender", "district",
    # Taiwan: structured admin fields + ethnicity
    "county", "township", "ethnicity", "cross_strait",
    # Legacy US fields kept for backward-compat
    "race", "hispanic_or_latino",
    "household_income",
    "education", "occupation", "income_band", "household_type", "household_tenure",
    "marital_status", "party_lean", "issue_1", "issue_2",
    "media_habit", "mbti", "vote_probability", "custom_fields",
}

# ── Generic semantic classifier ───────────────────────────────────────
# Dimensions whose NAME contains these keywords are statistical categories,
# not personal attributes. They describe what the data measures, not who.
_STAT_NAME_KEYWORDS = {
    "項目", "類別", "分類", "指標", "統計", "金額",
    "計畫", "面積", "概況", "彙整",
}

# If >30% of a dimension's VALUES contain these terms, it's statistical.
_STAT_VALUE_KEYWORDS = {
    "收入", "支出", "所得", "報酬", "總額", "淨額",
    "移轉", "利息", "紅利", "租金", "稅", "保險",
    "儲蓄", "消費", "財產", "營業", "盈餘",
}

# Known personal attribute field names — always included.
_KNOWN_PERSONAL = {"gender", "age", "district",
                   "county", "township", "ethnicity", "cross_strait",
                   "education", "occupation",
                   "race", "hispanic_or_latino",  # legacy US compat
                   "household_income",
                   "income_band", "household_type", "household_tenure",
                   "marital_status"}


def _is_personal_attribute(dim_name: str, dim: Dimension) -> bool:
    """Determine if a dimension represents a personal attribute.

    Returns False for statistical categories/indicators that shouldn't
    be assigned up to individual persons.

    Generic heuristics:
    1. Known mapped field names → always personal
    2. Dimension name contains statistical keywords → not personal
    3. >30% of values contain financial/statistical terms → not personal
    """
    # Check if it maps to a known personal field
    field = _resolve_field_name(dim_name)
    if field in _KNOWN_PERSONAL:
        return True

    # Check dimension name for statistical keywords
    base = dim_name.rsplit("_", 1)[-1] if "_" in dim_name else dim_name
    for kw in _STAT_NAME_KEYWORDS:
        if kw in base:
            return False

    # Check dimension values for statistical terms
    values: list[str] = []
    if dim.categories:
        values = [c.value for c in dim.categories]
    elif dim.bins:
        values = [b.range for b in dim.bins]

    if values:
        stat_count = sum(
            1 for v in values
            if any(kw in v for kw in _STAT_VALUE_KEYWORDS)
        )
        if stat_count / len(values) > 0.3:
            return False

    return True


def _row_matches_filters(row: dict[str, str], filters: dict[str, list[str]]) -> bool:
    if not filters:
        return True
        
    for f_dim, allowed in filters.items():
        if not allowed:
            continue
        
        # Resolve the filter dimension name to canonical field name
        f_field = _resolve_field_name(f_dim)
        
        # Try to find the matching value in the row:
        # 1. Direct key match
        # 2. Canonical field name match (e.g. "年齡" filter matches "年齡層" row key because both → "age")
        val = None
        if f_dim in row:
            val = str(row[f_dim]).strip()
        else:
            for rk, rv in row.items():
                if _resolve_field_name(rk) == f_field:
                    val = str(rv).strip()
                    break
        
        if not val:
            continue
            
        # Check if the value matches any of the allowed filter values
        matched_any = False
        for a in allowed:
            # Exact match
            if a == val:
                matched_any = True
                break
            # Range containment heuristic
            if a in val:
                if re.fullmatch(r'\d+', a) and re.fullmatch(r'\d+', val):
                    pass # already checked exact equality
                else:
                    matched_any = True
                    break
        
        if not matched_any:
            return False
            
    return True


# ── Public API ────────────────────────────────────────────────────────

def build_population(config: ProjectConfig) -> list[Person]:
    """Build N persons (Person model)."""
    rows = build_population_flat(config)
    persons = []
    
    selected_set = set(config.selected_dimensions) if getattr(config, "selected_dimensions", None) is not None else None
    
    for row in rows:
        # Extract custom fields, fill defaults
        person_data = {"person_id": row.get("person_id", 0)}
        custom = {}
        for k, v in row.items():
            if k == "person_id":
                continue
            if selected_set is not None and k not in selected_set:
                continue
                
            field = _resolve_field_name(k)
            if field in _PERSON_FIELDS:
                person_data[field] = v
            else:
                custom[k] = str(v)
        if custom:
            person_data["custom_fields"] = custom
        _fill_defaults(person_data)
        persons.append(Person(**person_data))
    return persons


def build_population_flat(config: ProjectConfig) -> list[dict]:
    """Build N persons as flat dicts — only populated fields, no nulls.

    Sampling strategy:
    1. Sort joint tables by number of dimensions (most first)
    2. Primary table: weighted sample N rows → fills multiple dims at once
    3. Secondary tables: condition on shared dims, then sample
    4. Remaining dims: independent marginal sampling
    """
    n = config.target_count
    joint_tables = config.joint_tables or []
    
    print(f"DEBUG: Starting build_population_flat with target_count={n}")
    print(f"DEBUG: filters keys={list(config.filters.keys()) if config.filters else 'None'}")
    if config.filters:
        for fk, fv in config.filters.items():
            print(f"DEBUG: filter[{fk!r}] = {fv[:5]}... (total {len(fv)} values)" if len(fv) > 5 else f"DEBUG: filter[{fk!r}] = {fv}")

    # --- Apply Filters to Joint Tables ---
    filtered_jts = []
    _skip_keywords = {"計", "總計", "合計", "小計", "total", "subtotal", "unknown"}
    for jt in joint_tables:
        if not jt.rows or not jt.weights:
            continue
        
        zero_count = 0
        nonzero_count = 0
        new_weights = []
        for row, w in zip(jt.rows, jt.weights):
            # Skip rows representing totals
            if any(str(v).strip().lower() in _skip_keywords for v in row.values()):
                new_weights.append(0.0)
                zero_count += 1
                continue
                
            if config.filters and not _row_matches_filters(row, config.filters):
                new_weights.append(0.0)
                zero_count += 1
            else:
                new_weights.append(w)
                nonzero_count += 1
                
        print(f"DEBUG: JT {jt.dim_names}: kept={nonzero_count}, filtered={zero_count}")
        if sum(new_weights) > 0:
            jt.weights = new_weights
            filtered_jts.append(jt)
        else:
            print(f"DEBUG: Joint table {jt.dim_names} dropped because sum(new_weights) == 0")

    # --- Phase 1: Joint table sampling ---
    # Sort by dimension count (most dimensions first)
    sorted_jts = sorted(filtered_jts, key=lambda jt: len(jt.dim_names), reverse=True)

    # Track which dimensions are already sampled for each person
    sampled: list[dict[str, str]] = [{} for _ in range(n)]

    for jt in sorted_jts:
        if not jt.rows or not jt.weights:
            continue

        # Which dims does this JT cover?
        jt_dims = set(jt.dim_names)
        # Which are already sampled? (from a previous, larger JT)
        already_sampled_dims = set(sampled[0].keys()) if sampled[0] else set()
        shared_dims = jt_dims & already_sampled_dims
        new_dims = jt_dims - already_sampled_dims

        if not new_dims:
            continue  # This JT adds nothing new

        if not shared_dims:
            # No shared dimensions → sample independently from this JT
            weights = np.array(jt.weights, dtype=float)
            weights /= weights.sum()
            indices = np.random.choice(len(jt.rows), size=n, p=weights)
            for i in range(n):
                row = jt.rows[indices[i]]
                for dim in new_dims:
                    if dim in row:
                        sampled[i][dim] = row[dim]
        else:
            # Shared dimensions exist → conditional sampling
            # Group JT rows by shared-dim values
            groups: dict[tuple, list[int]] = defaultdict(list)
            for idx, row in enumerate(jt.rows):
                key = tuple(row.get(d, "") for d in sorted(shared_dims))
                groups[key].append(idx)

            for i in range(n):
                # Get the already-sampled values for shared dims
                key = tuple(sampled[i].get(d, "") for d in sorted(shared_dims))
                matching = groups.get(key, [])

                if matching:
                    # Conditional sample from matching rows
                    sub_weights = np.array([jt.weights[j] for j in matching], dtype=float)
                    sub_weights /= sub_weights.sum()
                    chosen = matching[np.random.choice(len(matching), p=sub_weights)]
                    row = jt.rows[chosen]
                    for dim in new_dims:
                        if dim in row:
                            sampled[i][dim] = row[dim]
                else:
                    # No match → fall back to unconditional sample
                    weights = np.array(jt.weights, dtype=float)
                    weights /= weights.sum()
                    chosen = np.random.choice(len(jt.rows), p=weights)
                    row = jt.rows[chosen]
                    for dim in new_dims:
                        if dim in row:
                            sampled[i][dim] = row[dim]

    # --- Phase 2: Marginal sampling for remaining dimensions ---
    all_sampled_dims = set()
    for s in sampled:
        all_sampled_dims.update(s.keys())

    # Pre-compute the effective allowed age range from ALL age-related filters (numeric intersection)
    # This is used to constrain coarse 'age' marginal bins using range overlap rather than string matching
    eff_age_min, eff_age_max = None, None
    if config.filters:
        for fk, fv in config.filters.items():
            if _resolve_field_name(fk) == "age" and fv:
                for label in fv:
                    nums = re.findall(r"\d+", label)
                    if not nums:
                        continue
                    if len(nums) == 2:
                        lo, hi = int(nums[0]), int(nums[1])
                    elif "\u4ee5\u4e0a" in label or "+" in label:
                        lo, hi = int(nums[0]), 120
                    elif "\u4ee5\u4e0b" in label:
                        lo, hi = 0, int(nums[0])
                    else:
                        lo = hi = int(nums[0])
                    eff_age_min = lo if eff_age_min is None else min(eff_age_min, lo)
                    eff_age_max = hi if eff_age_max is None else max(eff_age_max, hi)
    print(f"DEBUG Phase2: effective age range from all filters = [{eff_age_min}, {eff_age_max}]")

    for dim_name, dim in config.dimensions.items():
        if dim_name in all_sampled_dims:
            continue  # Already sampled from a joint table
        if not _is_personal_attribute(dim_name, dim):
            continue  # Skip statistical categories (not personal traits)
        try:
            values, weights = _extract_values_weights(dim)
            if not values:
                continue

            is_age_dim = _resolve_field_name(dim_name) == "age"
                
            # Apply filters — check both direct name and canonical field name
            filter_allowed = None
            if config.filters:
                if dim_name in config.filters:
                    filter_allowed = config.filters[dim_name]
                else:
                    # Try canonical field name match
                    dim_field = _resolve_field_name(dim_name)
                    for fk, fv in config.filters.items():
                        if _resolve_field_name(fk) == dim_field:
                            filter_allowed = fv
                            break
            
            if is_age_dim and eff_age_min is not None:
                # For age dimensions, use numeric range OVERLAP with the effective age range
                # rather than exact string matching. This correctly handles coarse bins like
                # '18-64歲' vs fine-grained filter values like '20～24', '25～29'.
                new_pairs = []
                for v, w in zip(values, weights):
                    v_nums = re.findall(r"\d+", str(v))
                    if len(v_nums) == 2:
                        blo, bhi = int(v_nums[0]), int(v_nums[1])
                    elif v_nums and ("\u4ee5\u4e0a" in str(v) or "+" in str(v)):
                        blo, bhi = int(v_nums[0]), 120
                    elif v_nums and "\u4ee5\u4e0b" in str(v):
                        blo, bhi = 0, int(v_nums[0])
                    elif v_nums:
                        blo = bhi = int(v_nums[0])
                    else:
                        continue
                    # Keep this bin only if it overlaps with [eff_age_min, eff_age_max]
                    if bhi >= eff_age_min and blo <= eff_age_max:
                        # Clip the weight proportionally to the overlap
                        overlap = min(bhi, eff_age_max) - max(blo, eff_age_min) + 1
                        span = bhi - blo + 1
                        new_pairs.append((v, w * overlap / span))
                if new_pairs:
                    values = [p[0] for p in new_pairs]
                    weights = [p[1] for p in new_pairs]
                else:
                    continue
            elif filter_allowed is not None:
                if not filter_allowed:
                    # All values unchecked → exclude this dimension entirely
                    continue
                allowed = set(filter_allowed)
                filtered_pairs = [(v, w) for v, w in zip(values, weights) if v in allowed]
                if not filtered_pairs:
                    continue
                values = [p[0] for p in filtered_pairs]
                weights = [p[1] for p in filtered_pairs]

            weights_arr = _normalize(weights)
            draws = list(np.random.choice(values, size=n, p=weights_arr))
            for i in range(n):
                sampled[i][dim_name] = draws[i]
        except Exception:
            continue

    # --- Phase 3: Build output rows ---
    age_filter_groups = []
    if config.filters:
        # Check all filter keys that resolve to "age" field
        for fk, fv in config.filters.items():
            if _resolve_field_name(fk) == "age" and fv:
                age_filter_groups.append(fv)
    
    # Compute the absolute minimum age from filter labels for hard enforcement
    age_min_from_filter = None
    if age_filter_groups:
        mins_per_group = []
        for grp in age_filter_groups:
            grp_min = None
            for label in grp:
                nums = re.findall(r"\d+", label)
                if nums:
                    lo = int(nums[0])
                    if grp_min is None or lo < grp_min:
                        grp_min = lo
            if grp_min is not None:
                mins_per_group.append(grp_min)
        if mins_per_group:
            age_min_from_filter = max(mins_per_group) # intersection must be >= the highest minimum
        print(f"DEBUG: age_filter_groups count={len(age_filter_groups)}, age_min_from_filter={age_min_from_filter}")
    
    under20_debug_count = 0
    
    persons: list[dict] = []
    for i in range(n):
        row: dict[str, object] = {"person_id": i}
        custom: dict[str, str] = {}

        for dim_name, raw in sampled[i].items():
            field_name = _resolve_field_name(dim_name)

            if field_name == "age":
                resolved_age = _resolve_range(str(raw), config.filters)
                row["age"] = resolved_age
                # Debug: track where under-20 ages come from
                if age_min_from_filter and resolved_age < age_min_from_filter and under20_debug_count < 5:
                    print(f"DEBUG: Person {i}: raw age label='{raw}' → resolved={resolved_age} (below min {age_min_from_filter})")
                    under20_debug_count += 1
            elif field_name == "vote_probability":
                try:
                    row["vote_probability"] = float(raw)
                except ValueError:
                    row["vote_probability"] = 0.5
            elif field_name in _PERSON_FIELDS:
                row[field_name] = raw
            else:
                custom[dim_name] = raw

        # Flatten: no nulls, custom fields inline
        _fill_defaults(row, config.filters)
        # Inject county from config.region ONLY if the dim didn't already sample
        # one, and ONLY if region is a real Taiwan county (22-county list).
        # For national templates (region="台灣"), keep the dimension-sampled
        # county — overwriting with "台灣" loses the per-agent geographic signal.
        if not row.get("county"):
            _tw_counties = {
                "臺北市","新北市","桃園市","臺中市","臺南市","高雄市","基隆市","新竹市","嘉義市",
                "新竹縣","苗栗縣","彰化縣","南投縣","雲林縣","嘉義縣","屏東縣","宜蘭縣",
                "花蓮縣","臺東縣","澎湖縣","金門縣","連江縣",
            }
            _r = (config.region or "").strip()
            if _r in _tw_counties:
                row["county"] = _r
        _enforce_logical_consistency(row)
        
        # --- Post-validation: enforce age filter constraint ---
        if age_filter_groups and isinstance(row.get("age"), (int, float)):
            age_val = int(row["age"])
            valid = all(_age_in_allowed_labels(age_val, grp) for grp in age_filter_groups)
            if not valid:
                new_age = _random_age(age_filter_groups)
                if under20_debug_count < 10:
                    print(f"DEBUG: Post-validation person {i}: age {age_val} not in intersected labels, rewriting to {new_age}")
                row["age"] = new_age
        
        # Hard enforcement: if we have a computed minimum age, force it
        if age_min_from_filter is not None and isinstance(row.get("age"), (int, float)):
            if int(row["age"]) < age_min_from_filter:
                row["age"] = _random_age(age_filter_groups)
        
        flat = {k: v for k, v in row.items() if v is not None}
        flat.update(custom)
        persons.append(flat)

    return persons


# ── Field name resolution ─────────────────────────────────────────────

def _resolve_field_name(dim_name: str) -> str:
    """Map a dimension name to a Person model field name."""
    if dim_name in _DIM_TO_FIELD:
        return _DIM_TO_FIELD[dim_name]
    if "_" in dim_name:
        suffix = dim_name.rsplit("_", 1)[-1]
        if suffix in _DIM_TO_FIELD:
            return _DIM_TO_FIELD[suffix]
        if suffix in _PERSON_FIELDS:
            return suffix
    for key, field in _DIM_TO_FIELD.items():
        if len(key) >= 2 and key in dim_name:
            return field
    return dim_name


# ── Helpers ───────────────────────────────────────────────────────────

def _extract_values_weights(dim: Dimension) -> tuple[list[str], list[float]]:
    _skip = {"計", "總計", "合計", "小計", "total", "subtotal", "unknown"}
    
    if dim.type == DimensionType.CATEGORICAL and dim.categories:
        vals, wts = [], []
        for c in dim.categories:
            if str(c.value).strip().lower() not in _skip:
                vals.append(c.value)
                wts.append(c.weight)
        return vals, wts
        
    if dim.type == DimensionType.RANGE and dim.bins:
        vals, wts = [], []
        for b in dim.bins:
            if str(b.range).strip().lower() not in _skip:
                vals.append(b.range)
                wts.append(b.weight)
        return vals, wts
        
    return [], []


def _normalize(weights: list[float]) -> list[float]:
    total = sum(weights)
    if total == 0:
        return [1.0 / len(weights)] * len(weights)
    return [w / total for w in weights]


def _age_in_allowed_labels(age: int, labels: list[str]) -> bool:
    """Check if a concrete age falls within any of the allowed label ranges."""
    for label in labels:
        nums = re.findall(r"\d+", label)
        if len(nums) == 2:
            lo, hi = int(nums[0]), int(nums[1])
            if lo <= age <= hi:
                return True
        elif len(nums) == 1:
            n = int(nums[0])
            if "以上" in label or "+" in label:
                if age >= n:
                    return True
            elif "以下" in label:
                if age <= n:
                    return True
            else:
                if age == n:
                    return True
    return False


def _resolve_range(label: str, filters: dict = None) -> int:
    """Convert a range label like '18-24', '65+', '70歲以上' to a concrete int."""
    if "以上" in label or "+" in label:
        nums = re.findall(r"\d+", label)
        if nums:
            base = int(nums[0])
            return random.randint(base, base + 20)
    cleaned = re.sub(r"[歲岁]", "", label)
    match = re.match(r"(\d+)\s*[-–—～~]\s*(\d+)", cleaned)
    if match:
        return random.randint(int(match.group(1)), int(match.group(2)))
    try:
        return int(cleaned)
    except ValueError:
        age_filter_groups = []
        if filters:
            for fk, fv in filters.items():
                if _resolve_field_name(fk) == "age" and fv:
                    age_filter_groups.append(fv)
        return _random_age(age_filter_groups or None)


_AGE_RANGES = [(0, 17), (18, 24), (25, 34), (35, 44), (45, 54), (55, 64), (65, 80)]
_AGE_WEIGHTS = [0.15, 0.09, 0.16, 0.18, 0.18, 0.14, 0.10]


def _random_age(allowed_groups: list[list[str]] = None) -> int:
    # If no filters, fallback to normal distribution
    if not allowed_groups:
        lo, hi = random.choices(_AGE_RANGES, weights=_AGE_WEIGHTS, k=1)[0]
        return random.randint(lo, hi)
        
    valid_ages = None
    for grp in allowed_groups:
        grp_candidates = set()
        for a in grp:
            nums = re.findall(r"\d+", a)
            if len(nums) == 2:
                grp_candidates.update(range(int(nums[0]), int(nums[1]) + 1))
            elif len(nums) == 1:
                if "以上" in a or "+" in a:
                    grp_candidates.update(range(int(nums[0]), 120))
                elif "以下" in a or "-" in a:
                    grp_candidates.update(range(0, int(nums[0]) + 1))
                else:
                    grp_candidates.add(int(nums[0]))
        if valid_ages is None:
            valid_ages = grp_candidates
        else:
            valid_ages &= grp_candidates
    
    if valid_ages:
        return random.choice(list(valid_ages))
        
    # Fallback if intersection is empty
    lo, hi = random.choices(_AGE_RANGES, weights=_AGE_WEIGHTS, k=1)[0]
    return random.randint(lo, hi)


def _fill_defaults(row: dict, filters: dict = None) -> None:
    # Find age filter from any key that resolves to "age"
    age_filter_groups = []
    if filters:
        for fk, fv in filters.items():
            if _resolve_field_name(fk) == "age" and fv:
                age_filter_groups.append(fv)

    # Taiwan admin-hierarchy derivation: township ("縣市|鄉鎮") is the source of
    # truth. county + district are *derived* from township so they are always
    # consistent. Templates expose both `county` and `township` as independent
    # categorical dimensions; without this override we'd sample a random
    # county-wide distribution AND a random township-wide distribution, which
    # produces agents like 「county=新北市 but township=雲林縣|西螺鎮」.
    township = str(row.get("township") or "").strip()
    county = str(row.get("county") or "").strip()
    district = str(row.get("district") or "").strip()
    if township and "|" in township:
        parsed_county, parsed_town = township.split("|", 1)
        # Force county to match the township's parent — overrides any value the
        # county dimension may have independently sampled.
        row["county"] = parsed_county
        county = parsed_county
        if not district or district == "unknown":
            row["district"] = f"{parsed_county}{parsed_town}"
    elif county and (not district or district == "unknown"):
        row["district"] = county

    row.setdefault("age", _random_age(age_filter_groups or None))
    row.setdefault("gender", "unknown")
    row.setdefault("district", "unknown")


# 黨員基準率 (count / adult_pop_20plus)；從 ap/shared/tw_data/party_members_2026.json 同步
_PARTY_MEMBER_BASE_RATES = {
    "KMT": 331_410 / 19_500_000,   # ~1.70%
    "DPP": 240_000 / 19_500_000,   # ~1.23%
    "TPP":  32_546 / 19_500_000,   # ~0.17%
}

# 乘數表：tuple = (KMT_×, DPP_×, TPP_×)
#
# Calibration note (2026-04-18): 初版 plan spec 乘數（深藍 6.0 / 深綠 6.0）會推出
# 深藍 KMT 約 15% 黨員率（不合理 —— 真實 ~4-5%）。實證校準後取約 2.5× 上限，
# 使 overall 率 1.5-3%、deep-blue KMT 5-8%、deep-green DPP 4-7%，與 2025 實際
# 黨員數（KMT 331k / DPP 240k / TPP 32.5k）除以成人人口 19.5M 後的集中度相符。
_PARTY_MEMBER_LEAN_BOOST = {
    "深藍":  (2.5, 0.05, 0.8),
    "偏藍":  (1.8, 0.20, 1.2),
    "中間":  (0.5, 0.5,  1.2),
    "偏綠":  (0.15, 1.8, 0.7),
    "深綠":  (0.08, 2.5, 0.3),
}

_PARTY_MEMBER_AGE_BOOST = {
    "20-24": (0.3, 0.6, 2.0),
    "25-34": (0.6, 0.9, 2.2),
    "35-44": (0.8, 1.2, 1.8),
    "45-54": (1.2, 1.5, 1.0),
    "55-64": (1.8, 1.4, 0.5),
    "65+":   (2.2, 0.9, 0.2),
}

_PARTY_MEMBER_ETHNICITY_BOOST = {
    "閩南":   (0.9, 1.2, 1.0),
    "客家":   (1.1, 1.1, 0.9),
    "外省":   (3.5, 0.3, 1.0),
    "原住民": (1.8, 0.8, 0.5),
    "新住民": (1.0, 0.8, 0.7),
    "其他":   (1.0, 1.0, 1.0),
}

_PARTY_MEMBER_COUNTY_BOOST = {
    "臺北市":  (1.5, 0.8, 1.4),
    "新北市":  (1.2, 1.0, 1.1),
    "臺中市":  (1.3, 1.0, 1.0),
    "臺南市":  (0.6, 1.8, 0.9),
    "高雄市":  (0.6, 1.7, 0.9),
    "花蓮縣":  (1.6, 0.4, 0.7),
    "臺東縣":  (1.5, 0.5, 0.7),
    "金門縣":  (3.0, 0.2, 0.5),
    "連江縣":  (3.0, 0.2, 0.5),
}


def _age_to_bucket(age_or_bucket) -> str:
    """Resolve row['age_bucket'] if present else derive from row['age'] int."""
    if isinstance(age_or_bucket, str):
        return age_or_bucket
    try:
        a = int(age_or_bucket)
    except (TypeError, ValueError):
        return "45-54"
    if a < 25: return "20-24"
    if a < 35: return "25-34"
    if a < 45: return "35-44"
    if a < 55: return "45-54"
    if a < 65: return "55-64"
    return "65+"


def _derive_party_member(row: dict, rng) -> None:
    """Derive kmt_member / dpp_member / tpp_member bool flags.

    Probability = base_rate × lean_boost × age_boost × ethnicity_boost × county_boost,
    capped at 0.6 (沒人會因為堆乘數就 100% 機率是黨員).

    Writes row["kmt_member"] / ["dpp_member"] / ["tpp_member"] in-place.
    """
    lean = row.get("party_lean") or "中間"
    age_bucket = _age_to_bucket(row.get("age_bucket") or row.get("age"))
    ethnicity = row.get("ethnicity") or "其他"
    county = row.get("county") or ""

    lean_m = _PARTY_MEMBER_LEAN_BOOST.get(lean, (1.0, 1.0, 1.0))
    age_m = _PARTY_MEMBER_AGE_BOOST.get(age_bucket, (1.0, 1.0, 1.0))
    eth_m = _PARTY_MEMBER_ETHNICITY_BOOST.get(ethnicity, (1.0, 1.0, 1.0))
    cty_m = _PARTY_MEMBER_COUNTY_BOOST.get(county, (1.0, 1.0, 1.0))

    for i, party in enumerate(("KMT", "DPP", "TPP")):
        p = _PARTY_MEMBER_BASE_RATES[party] * lean_m[i] * age_m[i] * eth_m[i] * cty_m[i]
        p = min(max(p, 0.0), 0.6)
        row[f"{party.lower()}_member"] = rng.random() < p


def _enforce_logical_consistency(row: dict) -> None:
    """Post-processing to fix physically/logically impossible combinations."""
    # Fix district name format (remove stray spaces: "中 區" → "中區")
    if row.get("district"):
        row["district"] = row["district"].replace(" ", "")

    age = row.get("age", 30)
    if not isinstance(age, int):
        return

    # marital_status: heuristic from age + gender when template did not supply it
    # (TW 主計總處普查: age-banded marital distribution; labels are Traditional Chinese.)
    if not row.get("marital_status"):
        import random as _rng
        gender = (row.get("gender") or "").lower()
        # (未婚, 已婚, 離婚/分居, 喪偶)
        if age < 18:
            buckets, weights = ["未婚"], [1.0]
        elif age < 25:
            buckets = ["未婚", "已婚", "離婚/分居"]
            weights = [0.85, 0.13, 0.02]
        elif age < 35:
            buckets = ["未婚", "已婚", "離婚/分居"]
            weights = [0.40, 0.50, 0.10]
        elif age < 55:
            buckets = ["未婚", "已婚", "離婚/分居", "喪偶"]
            weights = [0.18, 0.62, 0.18, 0.02]
        elif age < 75:
            buckets = ["未婚", "已婚", "離婚/分居", "喪偶"]
            weights = [0.09, 0.64, 0.18, 0.09]
        else:
            buckets = ["未婚", "已婚", "離婚/分居", "喪偶"]
            # 喪偶女性較多（平均壽命差距）
            if gender in ("female", "f", "女"):
                weights = [0.04, 0.42, 0.10, 0.44]
            else:
                weights = [0.06, 0.66, 0.13, 0.15]
        row["marital_status"] = _rng.choices(buckets, weights=weights, k=1)[0]

    # Education logic
    edu = row.get("education", "")
    if age < 6:
        row["education"] = "無"
    elif age < 12:
        row["education"] = "國小"
    elif age < 15:
        if edu not in ("無", "國小", "國中"):
            row["education"] = "國中"
    elif age < 18:
        if edu not in ("無", "國小", "國中", "普通教育高中", "職業教育高職"):
            row["education"] = "普通教育高中"

    # Occupation logic — uses census DB for real distributions
    # Census provides: per-district occupation counts + age groups + working ratios
    # This allows data-driven assignment instead of hardcoded assumptions.
    occ = row.get("occupation", "")
    import random as _rng
    gender = row.get("gender", "")
    county = row.get("county", "")
    district = row.get("district", "")

    def _assign_from_census():
        """Assign specific occupation from census industry distribution."""
        try:
            from .census_lookup import get_occupation_distribution
            dist = get_occupation_distribution(county, district)
        except Exception:
            dist = {}
        if dist:
            return _rng.choices(list(dist.keys()), weights=list(dist.values()), k=1)[0]
        # Taiwan 行業分類（主計總處 2024 勞動力調查簡化為 10 類）
        return _rng.choices(
            ["製造業", "批發零售", "營建業", "住宿餐飲",
             "金融保險", "教育", "醫療照護", "資訊科技",
             "運輸倉儲", "公部門"],
            weights=[19, 14, 8, 10, 6, 9, 9, 8, 7, 10], k=1
        )[0]

    if age < 18:
        row["occupation"] = "學生"
    elif occ in ("無工作", "無", "", "待業", "有工作", "就業", "失業", "非勞動力",
                 "Unemployed", "Not in labor force"):
        if occ in ("有工作", "就業"):
            row["occupation"] = _assign_from_census()
        else:
            # Infer sub-category based on age/gender using census ratios
            if age >= 65:
                row["occupation"] = "退休"
            elif age <= 22:
                row["occupation"] = "學生"
            elif gender in ("女", "Female", "female") and _rng.random() < 0.28:
                row["occupation"] = "家管"
            else:
                # ~15% truly unemployed/not in labor force; rest get working occ
                if _rng.random() < 0.15:
                    row["occupation"] = "待業"
                else:
                    row["occupation"] = _assign_from_census()

    # 原住民 geographic re-sampling: 台灣原住民 ~580k (2.5%) 高度集中在
    # 花東 + 原鄉部落 + 都會移民聚落。如果 template 的 national marginal 讓
    # 原住民 agent 被分配到雲林/彰化/臺南/嘉義等 <1% 的縣市，persona 的地理
    # 敘事會完全失真（沒有部落、族語、傳統領域、豐年祭 context）。
    # 這裡針對原住民重新採樣 township，其他 ethnicity 不動。
    if row.get("ethnicity") == "原住民":
        _r_county = (row.get("county") or "").strip()
        # 原住民 meaningful counties（>3% 或有重要原鄉）
        _ind_ok_counties = {
            "臺東縣", "花蓮縣", "屏東縣", "南投縣",
            "新北市", "桃園市", "高雄市", "宜蘭縣",
            "新竹縣", "苗栗縣",
        }
        if _r_county not in _ind_ok_counties:
            # Weighted 原鄉 + 都會原民 pool. Weights roughly match 2024 原民會
            # 縣市人口分佈（臺東 35% / 花蓮 15% / 新北 12% / 桃園 10% / 屏東
            # 10% / 南投 8% / 高雄 7% / 宜蘭 3% / 新竹縣 3% / 苗栗 1%）。
            _ind_pool = [
                ("臺東縣|臺東市", 8), ("臺東縣|卑南鄉", 4), ("臺東縣|金峰鄉", 3),
                ("臺東縣|達仁鄉", 3), ("臺東縣|太麻里鄉", 3), ("臺東縣|延平鄉", 3),
                ("臺東縣|海端鄉", 3), ("臺東縣|蘭嶼鄉", 3), ("臺東縣|東河鄉", 3),
                ("花蓮縣|秀林鄉", 4), ("花蓮縣|萬榮鄉", 3), ("花蓮縣|卓溪鄉", 3),
                ("花蓮縣|光復鄉", 3), ("花蓮縣|瑞穗鄉", 2), ("花蓮縣|花蓮市", 3),
                ("屏東縣|三地門鄉", 3), ("屏東縣|霧台鄉", 2), ("屏東縣|瑪家鄉", 2),
                ("屏東縣|泰武鄉", 2), ("屏東縣|來義鄉", 2), ("屏東縣|屏東市", 3),
                ("南投縣|仁愛鄉", 4), ("南投縣|信義鄉", 4), ("南投縣|埔里鎮", 2),
                ("新北市|烏來區", 3), ("新北市|新店區", 3), ("新北市|三峽區", 2),
                ("新北市|汐止區", 2), ("新北市|板橋區", 2),
                ("桃園市|復興區", 3), ("桃園市|中壢區", 3), ("桃園市|平鎮區", 2),
                ("桃園市|八德區", 2),
                ("高雄市|那瑪夏區", 2), ("高雄市|桃源區", 2), ("高雄市|茂林區", 2),
                ("宜蘭縣|南澳鄉", 2), ("宜蘭縣|大同鄉", 2),
                ("新竹縣|尖石鄉", 2), ("新竹縣|五峰鄉", 2),
                ("苗栗縣|泰安鄉", 1),
            ]
            _new_key = _rng.choices(
                [k for k, _ in _ind_pool],
                weights=[w for _, w in _ind_pool], k=1,
            )[0]
            _new_county, _new_town = _new_key.split("|", 1)
            row["township"] = _new_key
            row["county"] = _new_county
            row["district"] = f"{_new_county}{_new_town}"

    # ── 原住民族別預分配（依鄉鎮推斷最可能族別）──
    if row.get("ethnicity") == "原住民" and not row.get("tribal_affiliation"):
        _township_key = row.get("township", "")
        _town_part = _township_key.split("|", 1)[1] if "|" in _township_key else ""

        # 原鄉部落 → 明確族別對照
        _TOWNSHIP_TRIBE: dict[str, str] = {
            # 臺東
            "蘭嶼鄉": "達悟族",
            "金峰鄉": "排灣族", "達仁鄉": "排灣族", "太麻里鄉": "排灣族",
            "延平鄉": "布農族", "海端鄉": "布農族",
            "東河鄉": "阿美族", "卑南鄉": "卑南族",
            # 花蓮
            "秀林鄉": "太魯閣族", "萬榮鄉": "太魯閣族",
            "卓溪鄉": "布農族",
            "光復鄉": "阿美族", "瑞穗鄉": "阿美族", "豐濱鄉": "阿美族",
            # 屏東
            "三地門鄉": "排灣族", "瑪家鄉": "排灣族", "泰武鄉": "排灣族",
            "來義鄉": "排灣族",
            "霧台鄉": "魯凱族",
            # 南投
            "仁愛鄉": "賽德克族", "信義鄉": "布農族",
            # 高雄
            "那瑪夏區": "布農族", "桃源區": "布農族", "茂林區": "魯凱族",
            # 宜蘭
            "南澳鄉": "泰雅族", "大同鄉": "泰雅族",
            # 新竹
            "尖石鄉": "泰雅族", "五峰鄉": "賽夏族",
            # 苗栗
            "泰安鄉": "泰雅族",
            # 嘉義
            "阿里山鄉": "鄒族",
            # 新北
            "烏來區": "泰雅族",
        }
        # 都會區原住民 — 依全國族群人口比例加權隨機
        _NATIONAL_TRIBE_WEIGHTS: list[tuple[str, int]] = [
            ("阿美族", 37), ("排灣族", 18), ("泰雅族", 16), ("布農族", 11),
            ("太魯閣族", 6), ("卑南族", 3), ("魯凱族", 3), ("賽夏族", 1),
            ("鄒族", 1), ("達悟族", 1), ("賽德克族", 2), ("噶瑪蘭族", 1),
            ("撒奇萊雅族", 1), ("邵族", 1), ("拉阿魯哇族", 1),
            ("卡那卡那富族", 1),
        ]

        tribe_match = _TOWNSHIP_TRIBE.get(_town_part)
        if isinstance(tribe_match, str):
            row["tribal_affiliation"] = tribe_match
        else:
            row["tribal_affiliation"] = _rng.choices(
                [t for t, _ in _NATIONAL_TRIBE_WEIGHTS],
                weights=[w for _, w in _NATIONAL_TRIBE_WEIGHTS], k=1,
            )[0]

    # ── 外省人祖籍預分配（依 1949 來台移民統計加權）──
    if row.get("ethnicity") == "外省" and not row.get("origin_province"):
        _PROVINCE_WEIGHTS: list[tuple[str, int]] = [
            ("山東", 18), ("江蘇", 12), ("浙江", 11), ("湖南", 10),
            ("四川", 8), ("廣東", 7), ("福建", 6), ("安徽", 5),
            ("河南", 5), ("湖北", 4), ("江西", 3), ("河北", 2),
            ("陝西", 2), ("貴州", 2), ("雲南", 2), ("遼寧", 1),
            ("山西", 1), ("廣西", 1),
        ]
        row["origin_province"] = _rng.choices(
            [p for p, _ in _PROVINCE_WEIGHTS],
            weights=[w for _, w in _PROVINCE_WEIGHTS], k=1,
        )[0]

    # cross_strait: 主權 / 經濟 / 民生 issue-priority axis (TW-specific).
    # Derived from party_lean + ethnicity when the template didn't sample it.
    # evolver.py reads this to seed per-agent attitudes.issue_priority so
    # agents within the same party_lean still have heterogeneous focus.
    if not row.get("cross_strait"):
        lean = (row.get("party_lean") or "").strip()
        ethnicity = (row.get("ethnicity") or "").strip()
        _lean_weights = {
            "深綠": (55, 15, 30),
            "偏綠": (35, 20, 45),
            "中間": (15, 25, 60),
            "偏藍": (10, 45, 45),
            "深藍": (5,  55, 40),
        }.get(lean, (20, 30, 50))  # fallback: 民生-heavy
        w_sov, w_econ, w_live = _lean_weights
        if ethnicity == "外省":
            w_sov = max(0, w_sov - 10); w_econ += 10
        elif ethnicity == "原住民":
            w_sov += 10; w_live = max(0, w_live - 10)
        elif ethnicity == "新住民":
            w_sov = max(0, w_sov - 5); w_econ = max(0, w_econ - 5); w_live += 10
        row["cross_strait"] = _rng.choices(
            ["主權", "經濟", "民生"],
            weights=[w_sov, w_econ, w_live], k=1,
        )[0]

    # ───── 黨員身份推導（Stage 9 加） ─────
    # 只推導一次：若 row 已有 *_member 欄位（由上游帶入）就不覆蓋
    if row.get("kmt_member") is None:
        _derive_party_member(row, _rng)
