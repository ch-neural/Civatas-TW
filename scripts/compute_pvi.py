"""Compute Taiwan Blue–Green Partisan Voting Index (PVI) per township and county.

Methodology (analogous to Cook PVI):
  share_G(township, year) = 綠 / (綠 + 藍)            [兩黨 share, 民進黨 vs 國民黨]
  share_G(nation,   year) = sum(綠) / sum(綠 + 藍)
  delta_G(township, year) = share_G(township) − share_G(nation)
  pvi(township)           = mean(delta_G) over available cycles   (single cycle 為 2024 baseline)

  Third-force (柯文哲 2024) 記錄 white_share 但不納入 PVI 計算；
  第三勢力在台灣地方層級主要反映浮動選民，不構成穩定 leaning 軸。

5-bucket label (analogous to Cook 5 buckets):
  深綠  (Solid Dem)  pvi > +0.08
  偏綠  (Lean Dem)   +0.03 < pvi ≤ +0.08
  中間  (Tossup)     -0.03 ≤ pvi ≤ +0.03
  偏藍  (Lean KMT)   -0.08 ≤ pvi < -0.03
  深藍  (Solid KMT)  pvi < -0.08

Output:
  data/elections/leaning_profile_tw.json
  {
    "schema_version": 1,
    "methodology": "…",
    "national": {"2024": {"green_share": …, "green_votes": …, "kmt_votes": …}},
    "townships": { "縣市|鄉鎮": {county, township, pvi, pvi_label, white_share, bucket, cycles: …} },
    "counties":   { "縣市":     {…} }
  }
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ELEC = ROOT / "data" / "elections"
DEFAULT_YEARS = (2024,)

# Auto-detect which cycles have township-level CSVs present and use whatever's
# available. To add 2020 (or 2016) data later: drop a CSV named
# president_<YEAR>_township.csv into data/elections/ (schema must match
# president_2024_township.csv) and re-run this script — it'll automatically
# switch to multi-cycle averaging.

def _auto_detect_years() -> tuple[int, ...]:
    avail: list[int] = []
    for path in ELEC.glob("president_*_township.csv"):
        try:
            yr = int(path.stem.split("_")[1])
            avail.append(yr)
        except (ValueError, IndexError):
            continue
    return tuple(sorted(avail))


# Party → which candidate column in our CSV maps to which two-party side.
PARTY_TO_SIDE = {
    "民進黨": "green", "國民黨": "kmt", "民眾黨": "white",
    # 2016/2020 legacy parties — map to the same two-party side
    "親民黨": "kmt",     # 宋楚瑜 2016/2020 歷史上與藍營關係較近
    "新黨": "kmt",
    "時代力量": "green",
    "台灣基進": "green",
    # For 2016 Soong (PFP) / 2020 Soong (PFP) rows appearing in data —
    # they were independent-leaning Blue; mapping to kmt side keeps the
    # two-party Green/Blue split consistent.
}

BUCKET_THRESHOLDS = [
    (0.08,  "深綠"),   # 深綠 if pvi > +0.08
    (0.03,  "偏綠"),   # 偏綠 if +0.03 < pvi ≤ +0.08
    (-0.03, "中間"),   # 中間 if -0.03 ≤ pvi ≤ +0.03
    (-0.08, "偏藍"),   # 偏藍 if -0.08 ≤ pvi < -0.03
]  # anything below -0.08 → 深藍


def bucket_from_pvi(pvi: float) -> str:
    for thr, label in BUCKET_THRESHOLDS:
        if label in ("深綠",):
            if pvi > thr:
                return label
        elif label == "偏綠":
            if pvi > thr:
                return label
        elif label == "中間":
            if pvi >= thr:
                return label
        elif label == "偏藍":
            if pvi >= thr:
                return label
    return "深藍"


def label_from_pvi(pvi: float) -> str:
    """Short human-readable label like G+8 / B+3 / EVEN."""
    n = round(pvi * 100)
    if n > 0:
        return f"G+{n}"
    if n < 0:
        return f"B+{abs(n)}"
    return "EVEN"


def load_year(year: int) -> dict[str, dict]:
    """Return {admin_key: {green, kmt, white, total_valid, county, township}}."""
    path = ELEC / f"president_{year}_township.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path.relative_to(ROOT)} not found — run scripts/fetch_elections.py first"
        )

    raw: dict[str, dict] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            admin_key = r["admin_key"]
            party = r["party_zh"]
            side = PARTY_TO_SIDE.get(party)
            if not side:
                continue
            votes = int(r["votes"])
            entry = raw.setdefault(admin_key, {
                "county": r["county"],
                "township": r["township"],
                "green": 0, "kmt": 0, "white": 0,
                "total_valid": int(r["total_valid"]),
            })
            entry[side] = votes
    return raw


def compute(years: tuple[int, ...] = DEFAULT_YEARS, output_suffix: str = "") -> int:
    cycles: dict[int, dict[str, dict]] = {}
    for y in years:
        cycles[y] = load_year(y)
        print(f"  {y}: loaded {len(cycles[y])} townships")

    # National two-party + third-party share
    national = {}
    for y, data in cycles.items():
        g = sum(d["green"] for d in data.values())
        k = sum(d["kmt"] for d in data.values())
        w = sum(d["white"] for d in data.values())
        total_valid = sum(d["total_valid"] for d in data.values())
        two_party = g + k
        national[y] = {
            "green_votes": g, "kmt_votes": k, "white_votes": w,
            "total_valid": total_valid,
            "green_share_two_party": round(g / two_party, 6) if two_party else 0.0,
            "kmt_share_two_party":   round(k / two_party, 6) if two_party else 0.0,
            "green_share_all":       round(g / total_valid, 6) if total_valid else 0.0,
            "kmt_share_all":         round(k / total_valid, 6) if total_valid else 0.0,
            "white_share_all":       round(w / total_valid, 6) if total_valid else 0.0,
        }
        print(f"  {y} 全國 綠/藍兩黨分額: 綠 {g/two_party:.4f}  藍 {k/two_party:.4f}   白三分額: {w/total_valid:.4f}")

    # Per-township PVI
    townships_out: dict[str, dict] = {}
    for admin_key in sorted(set().union(*[cycles[y].keys() for y in years])):
        per_cycle = {}
        deltas = []
        meta = {"county": "", "township": ""}
        ok = True
        white_shares = []
        for y in years:
            e = cycles[y].get(admin_key)
            if not e:
                ok = False
                break
            two_party = e["green"] + e["kmt"]
            if two_party == 0:
                ok = False
                break
            share_g = e["green"] / two_party
            delta = share_g - national[y]["green_share_two_party"]
            per_cycle[str(y)] = {
                "green": e["green"], "kmt": e["kmt"], "white": e["white"],
                "total_valid": e["total_valid"],
                "green_share_two_party": round(share_g, 6),
                "white_share_all": round(e["white"] / e["total_valid"], 6) if e["total_valid"] else 0.0,
                "delta": round(delta, 6),
            }
            deltas.append(delta)
            white_shares.append(e["white"] / e["total_valid"] if e["total_valid"] else 0.0)
            meta = {"county": e["county"], "township": e["township"]}
        if not ok:
            continue

        pvi = sum(deltas) / len(deltas)
        townships_out[admin_key] = {
            **meta,
            "admin_key": admin_key,
            "pvi": round(pvi, 6),
            "pvi_label": label_from_pvi(pvi),
            "bucket": bucket_from_pvi(pvi),
            "white_share_avg": round(sum(white_shares) / len(white_shares), 6),
            "cycles": per_cycle,
        }

    # County-level aggregation (sum votes, re-compute share + delta)
    counties_out: dict[str, dict] = {}
    per_county_votes: dict[str, dict] = {}
    for admin_key, row in townships_out.items():
        county = row["county"]
        cbucket = per_county_votes.setdefault(county, {
            "green": 0, "kmt": 0, "white": 0, "total_valid": 0,
            "township_count": 0,
        })
        # Use the last (usually only) cycle for county aggregation
        y = years[-1]
        c = row["cycles"][str(y)]
        cbucket["green"] += c["green"]
        cbucket["kmt"] += c["kmt"]
        cbucket["white"] += c["white"]
        cbucket["total_valid"] += c["total_valid"]
        cbucket["township_count"] += 1

    for county, b in per_county_votes.items():
        two_party = b["green"] + b["kmt"]
        if two_party == 0:
            continue
        share_g = b["green"] / two_party
        delta = share_g - national[years[-1]]["green_share_two_party"]
        counties_out[county] = {
            "county": county,
            "township_count": b["township_count"],
            "pvi": round(delta, 6),
            "pvi_label": label_from_pvi(delta),
            "bucket": bucket_from_pvi(delta),
            "white_share": round(b["white"] / b["total_valid"], 6) if b["total_valid"] else 0.0,
            "totals": {
                "green": b["green"], "kmt": b["kmt"], "white": b["white"],
                "total_valid": b["total_valid"],
                "green_share_two_party": round(share_g, 6),
            },
        }

    out = {
        "schema_version": 1,
        "methodology": (
            "Taiwan Blue-Green PVI = 鄉鎮/縣市 綠營 (民進黨) 兩黨得票率 "
            "減去全國綠營兩黨得票率。多屆計算取平均。"
            "5-bucket label: 深綠 (>+8%) / 偏綠 (+3~+8%) / 中間 (-3~+3%) / 偏藍 (-8~-3%) / 深藍 (<-8%). "
            f"當前基於 {','.join(str(y) for y in years)} 單屆資料計算；補 2020 可增強穩定性。"
        ),
        "source": "中選會 2024 總統大選鄉鎮級開票資料 (via ap/shared/builtin_modules/president_2024.json)",
        "years": list(years),
        "national": {str(k): v for k, v in national.items()},
        "townships": townships_out,
        "counties": counties_out,
    }
    dest = ELEC / f"leaning_profile_tw{output_suffix}.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2))

    # Distribution check
    pvis = [t["pvi"] for t in townships_out.values()]
    pvis_sorted = sorted(pvis)
    median = pvis_sorted[len(pvis_sorted) // 2]
    buckets: dict[str, int] = {}
    for t in townships_out.values():
        buckets[t["bucket"]] = buckets.get(t["bucket"], 0) + 1
    print(f"  wrote {len(townships_out)} townships, {len(counties_out)} counties")
    print(f"  PVI range: min={min(pvis):.3f}  median={median:.3f}  max={max(pvis):.3f}")
    print(f"  bucket distribution: " + ", ".join(f"{b}={buckets.get(b,0)}" for b in ("深綠","偏綠","中間","偏藍","深藍")))
    print(f"  -> {dest.relative_to(ROOT)}")

    # Sanity: top 5 綠/藍 townships
    print()
    print("Top 5 深綠 townships:")
    for t in sorted(townships_out.values(), key=lambda x: -x["pvi"])[:5]:
        print(f"  {t['admin_key']:<15}  pvi {t['pvi']:+.3f}  ({t['pvi_label']})")
    print("Top 5 深藍 townships:")
    for t in sorted(townships_out.values(), key=lambda x: x["pvi"])[:5]:
        print(f"  {t['admin_key']:<15}  pvi {t['pvi']:+.3f}  ({t['pvi_label']})")
    print("County PVI summary:")
    for c in sorted(counties_out.values(), key=lambda x: -x["pvi"]):
        print(f"  {c['county']:<6}  pvi {c['pvi']:+.3f}  ({c['pvi_label']:<5}) bucket={c['bucket']}  白={c['white_share']:.3f}")

    return 0


def main() -> int:
    # Auto-detect available cycles; fall back to DEFAULT_YEARS if none found.
    years = _auto_detect_years() or DEFAULT_YEARS
    if len(years) > 1:
        print(f"  auto-detected cycles: {years} → multi-cycle averaging")
    else:
        print(f"  single cycle: {years[0]} → 單屆 baseline (補 2020 CSV 可增強穩定性)")
    return compute(years)


if __name__ == "__main__":
    sys.exit(main())
