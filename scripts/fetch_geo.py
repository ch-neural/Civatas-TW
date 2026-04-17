"""Download Taiwan county + township boundaries from ronnywang/twgeojson and normalise.

Source: https://github.com/ronnywang/twgeojson (MIT), based on MOI segis data.
  - twcounty2010.5.json  (simplified to level 5 — ~6 MB,  22 counties + outlying islands)
  - twtown2010.5.json    (simplified to level 5 — ~17 MB, 368 townships/districts)

We use the "2010" variant because it reflects the post-五都升格 administrative boundaries
(Taipei/New Taipei/Taichung/Tainan/Kaohsiung as municipalities; Taoyuan still 桃園縣 here,
upgraded 2014 — but township boundaries themselves are unchanged by the upgrade, so we
patch the county name to 桃園市 on the fly).

Output:
  data/geo/tw-counties.geojson       normalised: properties = {name, id}
  data/geo/tw-townships.geojson      normalised: properties = {name, id, county}
  data/geo/raw/twcounty2010.5.json   raw cache
  data/geo/raw/twtown2010.5.json     raw cache
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GEO = ROOT / "data" / "geo"
RAW = GEO / "raw"

BASE = "https://raw.githubusercontent.com/ronnywang/twgeojson/master"
SOURCES = {
    "twcounty2010.5.json": f"{BASE}/twcounty2010.5.json",
    "twtown2010.5.json": f"{BASE}/twtown2010.5.json",
}

# Counties upgraded to 直轄市 after the 2010/2011 data snapshot.
# Township boundaries are unchanged; we just rewrite the county name.
COUNTY_RENAME = {
    "桃園縣": "桃園市",  # upgraded 2014/12/25
}

# Expected count ranges (guard against silent data regression)
EXPECTED_COUNTIES = (22, 23)       # 22 counties/cities (6 直轄市 + 3 市 + 13 縣)
EXPECTED_TOWNSHIPS = (360, 375)    # 368 鄉鎮市區 (range tolerates minor data variance)


def download(url: str, dest: Path) -> None:
    if dest.exists():
        print(f"  CACHED {dest.relative_to(ROOT)} ({dest.stat().st_size:,} bytes)")
        return
    print(f"  GET {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "civatas-tw-fetch/0.1"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        dest.write_bytes(resp.read())
    print(f"      -> {dest.relative_to(ROOT)} ({dest.stat().st_size:,} bytes)")


def rename_county(name: str) -> str:
    return COUNTY_RENAME.get(name, name)


def normalise_counties(raw: dict) -> dict:
    """Normalise county-level properties → {name, id}. Preserve geometry."""
    out_feats = []
    for f in raw["features"]:
        p = f.get("properties", {}) or {}
        name = rename_county(p.get("county", "")).strip()
        fid = p.get("county_id", "")
        if not name:
            continue
        out_feats.append({
            "type": "Feature",
            "id": fid,
            "properties": {"name": name, "id": fid},
            "geometry": f["geometry"],
        })
    return {"type": "FeatureCollection", "features": out_feats}


def normalise_townships(raw: dict) -> dict:
    """Normalise township-level properties → {name, id, county}."""
    out_feats = []
    for f in raw["features"]:
        p = f.get("properties", {}) or {}
        town = (p.get("town") or "").strip()
        county = rename_county((p.get("county") or "").strip())
        tid = p.get("town_id", "")
        if not town or not county:
            continue
        out_feats.append({
            "type": "Feature",
            "id": tid,
            "properties": {
                "name": town,
                "id": tid,
                "county": county,
                # composite key matches ap/shared/tw_admin.py format ("縣市|鄉鎮市區")
                "admin_key": f"{county}|{town}",
            },
            "geometry": f["geometry"],
        })
    return {"type": "FeatureCollection", "features": out_feats}


def main() -> int:
    GEO.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)

    print("[1/2] Downloading raw GeoJSON …")
    for name, url in SOURCES.items():
        download(url, RAW / name)

    print("[2/2] Normalising …")
    counties_raw = json.loads((RAW / "twcounty2010.5.json").read_text())
    towns_raw = json.loads((RAW / "twtown2010.5.json").read_text())

    counties = normalise_counties(counties_raw)
    towns = normalise_townships(towns_raw)

    (GEO / "tw-counties.geojson").write_text(
        json.dumps(counties, ensure_ascii=False, separators=(",", ":"))
    )
    (GEO / "tw-townships.geojson").write_text(
        json.dumps(towns, ensure_ascii=False, separators=(",", ":"))
    )

    nc = len(counties["features"])
    nt = len(towns["features"])
    print(f"  counties:   {nc} features  ({', '.join(sorted({f['properties']['name'] for f in counties['features']}))})")
    print(f"  townships:  {nt} features")

    ok = True
    if not (EXPECTED_COUNTIES[0] <= nc <= EXPECTED_COUNTIES[1]):
        print(f"  WARNING: expected ~22 counties, got {nc}", file=sys.stderr)
        ok = False
    if not (EXPECTED_TOWNSHIPS[0] <= nt <= EXPECTED_TOWNSHIPS[1]):
        print(f"  WARNING: expected ~368 townships, got {nt}", file=sys.stderr)
        ok = False

    print("done." if ok else "done (with warnings).")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
