"""Load Taiwan election results + PVI + census dimensions into a SQLite database.

Builds data/tw_election.db for the election-db service to serve via API.

Source files (run fetch_*.py / compute_pvi.py first):
  data/elections/president_2024_township.csv   — 2024 township vote rows
  data/elections/president_2024_county.csv     — 2024 county aggregates
  data/elections/leaning_profile_tw.json       — Blue-Green PVI
  data/census/townships.json                   — township demographics
  data/census/counties.json                    — county demographics
  data/geo/tw-townships.geojson                — township admin-key truth

Schema (all kept in one SQLite file for simplicity):
  tw_counties   (county PK, population, pvi, bucket, …)
  tw_townships  (admin_key PK, county FK, township, population, pvi, bucket, …)
  tw_candidates (id, year, party_zh, party_code, name_zh)
  tw_results    (admin_key, year, candidate_id, votes, vote_rate, total_valid, turnout)

Design note: Postgres backend was dropped during the US→TW conversion because
the election-db service is the only consumer and it can load the same SQLite
file via a mount. If a Postgres deployment is required later, re-add DSN
support and use the SQLite DDL here as the reference schema.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DEFAULT_DB = DATA / "tw_election.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS tw_counties (
    county              TEXT PRIMARY KEY,
    population_total    INTEGER,
    township_count      INTEGER,
    pvi                 REAL,
    pvi_label           TEXT,
    bucket              TEXT,
    white_share         REAL,
    green_votes         INTEGER,
    kmt_votes           INTEGER,
    white_votes         INTEGER,
    total_valid         INTEGER
);

CREATE TABLE IF NOT EXISTS tw_townships (
    admin_key           TEXT PRIMARY KEY,
    county              TEXT NOT NULL REFERENCES tw_counties(county),
    township            TEXT NOT NULL,
    population_total    INTEGER,
    voters_18plus       INTEGER,
    pvi                 REAL,
    pvi_label           TEXT,
    bucket              TEXT,
    white_share         REAL
);
CREATE INDEX IF NOT EXISTS idx_townships_county ON tw_townships(county);
CREATE INDEX IF NOT EXISTS idx_townships_bucket ON tw_townships(bucket);

CREATE TABLE IF NOT EXISTS tw_candidates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    year        INTEGER NOT NULL,
    party_zh    TEXT NOT NULL,
    party_code  TEXT NOT NULL,
    name_zh     TEXT NOT NULL,
    UNIQUE (year, name_zh)
);

CREATE TABLE IF NOT EXISTS tw_results (
    admin_key       TEXT NOT NULL REFERENCES tw_townships(admin_key),
    year            INTEGER NOT NULL,
    candidate_id    INTEGER NOT NULL REFERENCES tw_candidates(id),
    votes           INTEGER NOT NULL,
    vote_rate       REAL NOT NULL,
    total_valid     INTEGER NOT NULL,
    turnout         REAL,
    PRIMARY KEY (admin_key, year, candidate_id)
);
CREATE INDEX IF NOT EXISTS idx_results_year ON tw_results(year);
"""


def open_db(path: Path) -> sqlite3.Connection:
    if path.exists():
        path.unlink()  # always rebuild from source
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def load_counties(conn: sqlite3.Connection) -> None:
    census = json.loads((DATA / "census" / "counties.json").read_text(encoding="utf-8"))
    pvi = json.loads((DATA / "elections" / "leaning_profile_tw.json").read_text(encoding="utf-8"))
    pvi_counties = pvi["counties"]

    rows = []
    for county, c in census.items():
        p = pvi_counties.get(county, {})
        totals = p.get("totals", {})
        rows.append((
            county,
            c["population_total"],
            c["township_count"],
            p.get("pvi"),
            p.get("pvi_label"),
            p.get("bucket"),
            p.get("white_share"),
            totals.get("green"),
            totals.get("kmt"),
            totals.get("white"),
            totals.get("total_valid"),
        ))
    conn.executemany(
        "INSERT INTO tw_counties(county, population_total, township_count, pvi, pvi_label, bucket, white_share, green_votes, kmt_votes, white_votes, total_valid) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    print(f"  tw_counties: {len(rows)} rows")


def load_townships(conn: sqlite3.Connection) -> None:
    census = json.loads((DATA / "census" / "townships.json").read_text(encoding="utf-8"))
    pvi = json.loads((DATA / "elections" / "leaning_profile_tw.json").read_text(encoding="utf-8"))
    pvi_towns = pvi["townships"]

    rows = []
    for admin_key, t in census.items():
        p = pvi_towns.get(admin_key, {})
        rows.append((
            admin_key,
            t["county"],
            t["township"],
            t["population_total"],
            t["voters_18plus"],
            p.get("pvi"),
            p.get("pvi_label"),
            p.get("bucket"),
            p.get("white_share_avg"),
        ))
    conn.executemany(
        "INSERT INTO tw_townships(admin_key, county, township, population_total, voters_18plus, pvi, pvi_label, bucket, white_share) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        rows,
    )
    print(f"  tw_townships: {len(rows)} rows")


def load_candidates_and_results(conn: sqlite3.Connection) -> None:
    """Register candidates from the 2024 CSV and bulk-insert per-township rows."""
    src = DATA / "elections" / "president_2024_township.csv"
    # Candidates from unique (year, party_zh, party_code, name_zh)
    cands: dict[tuple, tuple] = {}
    with src.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            key = (int(r["year"]), r["party_zh"], r["party_code"], r["candidate"])
            cands[key] = key
    cur = conn.cursor()
    cand_id: dict[tuple, int] = {}
    for key in cands.values():
        cur.execute(
            "INSERT INTO tw_candidates(year, party_zh, party_code, name_zh) VALUES (?,?,?,?)",
            key,
        )
        cand_id[key] = cur.lastrowid
    print(f"  tw_candidates: {len(cand_id)} rows")

    rows = []
    with src.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            key = (int(r["year"]), r["party_zh"], r["party_code"], r["candidate"])
            rows.append((
                r["admin_key"],
                int(r["year"]),
                cand_id[key],
                int(r["votes"]),
                float(r["vote_rate"]),
                int(r["total_valid"]),
                float(r["turnout"]),
            ))
    conn.executemany(
        "INSERT INTO tw_results(admin_key, year, candidate_id, votes, vote_rate, total_valid, turnout) "
        "VALUES (?,?,?,?,?,?,?)",
        rows,
    )
    print(f"  tw_results: {len(rows)} rows")


def verify(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    for table in ("tw_counties", "tw_townships", "tw_candidates", "tw_results"):
        n = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {n}")

    # National vote totals reproduced from DB
    print("  national re-check from DB:")
    for row in cur.execute("""
        SELECT c.party_zh, c.name_zh, SUM(r.votes) as v,
               (SELECT SUM(total_valid) FROM tw_results WHERE year=2024 AND candidate_id=c.id) as tv
        FROM tw_candidates c JOIN tw_results r ON r.candidate_id=c.id
        WHERE c.year=2024
        GROUP BY c.id
        ORDER BY v DESC
    """):
        party, name, v, tv = row
        print(f"    {party:<6}{name:<6} {v:>10,}  ({v/tv:.4f})")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--sqlite", default=str(DEFAULT_DB),
                   help="Output SQLite file (default: data/tw_election.db)")
    args = p.parse_args()

    out = Path(args.sqlite)
    out.parent.mkdir(parents=True, exist_ok=True)

    print(f"Building {out.relative_to(ROOT)} …")
    conn = open_db(out)
    print("[1/3] Loading counties …")
    load_counties(conn)
    print("[2/3] Loading townships …")
    load_townships(conn)
    print("[3/3] Loading candidates + results …")
    load_candidates_and_results(conn)
    conn.commit()

    print()
    print("Verification:")
    verify(conn)
    conn.close()
    print("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
