"""Extract Taiwan presidential election returns at township level.

Primary source (2024):
  ap/shared/builtin_modules/president_2024.json  — 368 townships, schema:
    "縣市|鄉鎮": {
        "國民黨_侯友宜_得票率": 0.xxxx,
        "民進黨_賴清德_得票率": 0.xxxx,
        "民眾黨_柯文哲_得票率": 0.xxxx,
        "投票率": 0.xxxx,
        "有效票數": int,
    }
  Verified national totals match CEC official numbers exactly:
    賴清德 40.05 % / 侯友宜 33.49 % / 柯文哲 26.46 %, 有效票 13,947,506.

2020 support (蔡英文 vs 韓國瑜 vs 宋楚瑜):
  — Public per-township CSV not yet wired up (CEC publishes ODS only; g0v/kiang
    datasets cover pre-2016 or partial data). Placeholder preserved for future
    integration. PVI computed from 2024 single-cycle baseline until then.

Output:
  data/elections/president_2024_township.csv
  data/elections/president_2024_county.csv     (aggregated weighted by 有效票數)
  data/elections/raw/<source-name>             (copies kept for reproducibility)
"""
from __future__ import annotations

import csv
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ELEC = ROOT / "data" / "elections"
RAW = ELEC / "raw"
BUILTIN_2024 = ROOT / "ap" / "shared" / "builtin_modules" / "president_2024.json"

# Candidate metadata for 2024
CANDIDATES_2024 = [
    {"party_zh": "民進黨", "party_code": "DPP", "name_zh": "賴清德", "rate_key": "民進黨_賴清德_得票率"},
    {"party_zh": "國民黨", "party_code": "KMT", "name_zh": "侯友宜", "rate_key": "國民黨_侯友宜_得票率"},
    {"party_zh": "民眾黨", "party_code": "TPP", "name_zh": "柯文哲", "rate_key": "民眾黨_柯文哲_得票率"},
]


def load_2024() -> dict:
    if not BUILTIN_2024.exists():
        raise FileNotFoundError(
            f"expected 2024 township data at {BUILTIN_2024.relative_to(ROOT)} "
            "(bundled with ap/shared/builtin_modules/). Did you delete it?"
        )
    return json.loads(BUILTIN_2024.read_text(encoding="utf-8"))


def write_township_csv_2024(data: dict) -> Path:
    """One row per (township × candidate) — mirrors MEDSL long-format convention."""
    out = ELEC / "president_2024_township.csv"
    rows = []
    for key, rec in data.items():
        parts = key.split("|")
        if len(parts) != 2:
            continue
        county, township = parts
        total_valid = int(rec.get("有效票數", 0) or 0)
        turnout = float(rec.get("投票率", 0.0) or 0.0)
        for c in CANDIDATES_2024:
            rate = float(rec.get(c["rate_key"], 0.0) or 0.0)
            votes = round(rate * total_valid) if total_valid else 0
            rows.append({
                "year": 2024,
                "county": county,
                "township": township,
                "admin_key": key,
                "party_zh": c["party_zh"],
                "party_code": c["party_code"],
                "candidate": c["name_zh"],
                "vote_rate": f"{rate:.6f}",
                "votes": votes,
                "total_valid": total_valid,
                "turnout": f"{turnout:.6f}",
            })

    fields = ["year", "county", "township", "admin_key", "party_zh", "party_code",
              "candidate", "vote_rate", "votes", "total_valid", "turnout"]
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return out


def write_county_csv_2024(township_csv: Path) -> Path:
    """County-level aggregation weighted by 有效票數 (each party's votes summed)."""
    out = ELEC / "president_2024_county.csv"
    agg: dict[tuple[str, str], dict] = {}  # (county, candidate) → {votes, total_valid}
    with township_csv.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            k = (r["county"], r["candidate"])
            bucket = agg.setdefault(k, {
                "year": 2024, "county": r["county"],
                "party_zh": r["party_zh"], "party_code": r["party_code"],
                "candidate": r["candidate"],
                "votes": 0, "total_valid": 0,
            })
            bucket["votes"] += int(r["votes"])
    # Total valid per county is shared across candidates — compute once
    total_per_county: dict[str, int] = {}
    with township_csv.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            c = r["county"]
            total_per_county[c] = total_per_county.get(c, 0) + (
                int(r["total_valid"]) if r["candidate"] == CANDIDATES_2024[0]["name_zh"] else 0
            )

    fields = ["year", "county", "party_zh", "party_code", "candidate",
              "votes", "total_valid", "vote_rate"]
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for (_county, _cand), bucket in sorted(agg.items()):
            tv = total_per_county.get(bucket["county"], 0)
            bucket["total_valid"] = tv
            bucket["vote_rate"] = f"{(bucket['votes'] / tv):.6f}" if tv else "0.000000"
            w.writerow(bucket)
    return out


def summarise_2024(township_csv: Path) -> None:
    totals = {c["name_zh"]: 0 for c in CANDIDATES_2024}
    grand_total = 0
    n_townships = set()
    n_counties = set()
    with township_csv.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            totals[r["candidate"]] = totals.get(r["candidate"], 0) + int(r["votes"])
            n_townships.add(r["admin_key"])
            n_counties.add(r["county"])
            if r["candidate"] == CANDIDATES_2024[0]["name_zh"]:
                grand_total += int(r["total_valid"])
    print(f"  townships: {len(n_townships)}  counties: {len(n_counties)}  total valid votes: {grand_total:,}")
    for c in CANDIDATES_2024:
        v = totals.get(c["name_zh"], 0)
        print(f"    {c['party_zh']:<6}{c['name_zh']:<6} {v:>10,} ({v/grand_total:.4f})")


def import_external_year(year: int, src_path: Path, schema_hint: dict | None = None) -> Path:
    """Import a user-provided township-level CSV for a given year (e.g. 2020).

    The external file must be a row-per-(township × candidate) CSV containing at
    minimum these columns:
        admin_key  ("縣市|鄉鎮", e.g. "臺北市|大安區")
        county     (縣市名稱)
        township   (鄉鎮市區名稱)
        party_zh   (e.g. "民進黨", "國民黨", "親民黨")
        candidate  (中文姓名)
        votes      (int)
        vote_rate  (float 0.0–1.0)
        total_valid (int, 鄉鎮有效票總數 — 所有候選人相同)
        turnout    (float 0.0–1.0, optional)

    If the user's CSV uses different column names, rename them first, or pass
    schema_hint={"old_name": "canonical_name", ...}.

    The import writes to data/elections/president_<YEAR>_township.csv so
    compute_pvi.py will auto-pick it up next run.
    """
    dest = ELEC / f"president_{year}_township.csv"
    fields = ["year", "county", "township", "admin_key", "party_zh", "party_code",
              "candidate", "vote_rate", "votes", "total_valid", "turnout"]
    rename = schema_hint or {}

    n = 0
    with src_path.open(newline="", encoding="utf-8") as f_in, \
         dest.open("w", newline="", encoding="utf-8") as f_out:
        reader = csv.DictReader(f_in)
        writer = csv.DictWriter(f_out, fieldnames=fields)
        writer.writeheader()
        for row in reader:
            row = {rename.get(k, k): v for k, v in row.items()}
            out = {
                "year": year,
                "county": row.get("county", ""),
                "township": row.get("township", ""),
                "admin_key": row.get("admin_key") or f"{row.get('county','')}|{row.get('township','')}",
                "party_zh": row.get("party_zh", ""),
                "party_code": row.get("party_code") or {
                    "民進黨": "DPP", "國民黨": "KMT", "民眾黨": "TPP",
                    "親民黨": "PFP", "時代力量": "NPP", "台灣基進": "TSP",
                    "新黨": "NP",
                }.get(row.get("party_zh", ""), "OTH"),
                "candidate": row.get("candidate", ""),
                "vote_rate": row.get("vote_rate", "0.0"),
                "votes": row.get("votes", "0"),
                "total_valid": row.get("total_valid", "0"),
                "turnout": row.get("turnout", "0.0"),
            }
            writer.writerow(out)
            n += 1
    print(f"  imported {n} rows into {dest.relative_to(ROOT)}")
    return dest


def main() -> int:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--import-year", type=int, default=None,
                   help="Import a user-provided township CSV for a given cycle "
                        "(e.g. 2020 or 2016). Use with --from-csv.")
    p.add_argument("--from-csv", type=str, default=None,
                   help="Path to the external township CSV to import.")
    args = p.parse_args()

    ELEC.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)

    if args.import_year and args.from_csv:
        src_path = Path(args.from_csv).expanduser().resolve()
        if not src_path.exists():
            print(f"ERROR: {src_path} not found", file=sys.stderr)
            return 1
        print(f"Importing {args.import_year} township CSV from {src_path} …")
        import_external_year(args.import_year, src_path)
        print("done. Re-run scripts/compute_pvi.py to re-compute PVI with the new cycle.")
        return 0

    # Default flow: rebuild 2024 CSV from the bundled builtin_modules JSON.
    # Snapshot the source JSON into raw/ for reproducibility
    raw_copy = RAW / "president_2024_builtin.json"
    shutil.copy2(BUILTIN_2024, raw_copy)
    print(f"[1/3] Cached source → {raw_copy.relative_to(ROOT)} ({raw_copy.stat().st_size:,} bytes)")

    print("[2/3] Writing 2024 township-level CSV …")
    data24 = load_2024()
    tw_csv = write_township_csv_2024(data24)
    print(f"  -> {tw_csv.relative_to(ROOT)}")

    print("[3/3] Aggregating to county level …")
    cty_csv = write_county_csv_2024(tw_csv)
    print(f"  -> {cty_csv.relative_to(ROOT)}")

    print()
    print("National verification (expected: 賴 0.4005 / 侯 0.3349 / 柯 0.2646, 有效票 13,947,506):")
    summarise_2024(tw_csv)

    print()
    print("NOTE: 2020 鄉鎮級資料 (蔡/韓/宋) 未內建 — 中選會僅釋出 ODS 格式，公開 CSV mirror 稀少。")
    print("      PVI 目前用 2024 單屆 baseline 計算。")
    print("      補 2020：python3 scripts/fetch_elections.py --import-year 2020 --from-csv /path/to/your.csv")
    print("      然後重跑 scripts/compute_pvi.py —— 會自動切換為多屆平均。")
    print("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
