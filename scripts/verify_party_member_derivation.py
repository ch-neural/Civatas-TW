"""Verify _derive_party_member distribution on 10,000 synthetic rows.

Run: python3 scripts/verify_party_member_derivation.py
Exit 0 = pass.
"""
from __future__ import annotations
import json
import sys
import random
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ap" / "services" / "synthesis" / "app"))
sys.path.insert(0, str(ROOT / "ap"))

from builder import _derive_party_member  # noqa: E402


def _mk_row(lean: str, age_bucket: str, ethnicity: str, county: str) -> dict:
    return {"party_lean": lean, "age_bucket": age_bucket,
            "ethnicity": ethnicity, "county": county}


def main() -> int:
    rng = random.Random(20260418)

    # 產生符合全台灣分佈的 10,000 rows
    leans = [("深綠", 0.24), ("偏綠", 0.16), ("中間", 0.21),
             ("偏藍", 0.13), ("深藍", 0.26)]
    ages = [("20-24", 0.10), ("25-34", 0.15), ("35-44", 0.18),
            ("45-54", 0.17), ("55-64", 0.17), ("65+", 0.23)]
    eths = [("閩南", 0.70), ("客家", 0.13), ("外省", 0.10),
            ("原住民", 0.03), ("新住民", 0.03), ("其他", 0.01)]
    cnts = [("臺北市", 0.11), ("新北市", 0.17), ("臺中市", 0.12),
            ("臺南市", 0.08), ("高雄市", 0.12), ("其它", 0.40)]

    def _sample(pairs):
        r = rng.random()
        acc = 0.0
        for v, w in pairs:
            acc += w
            if r <= acc:
                return v
        return pairs[-1][0]

    rows = [_mk_row(_sample(leans), _sample(ages), _sample(eths), _sample(cnts))
            for _ in range(10_000)]
    for row in rows:
        _derive_party_member(row, rng)

    kmt_n = sum(1 for r in rows if r["kmt_member"])
    dpp_n = sum(1 for r in rows if r["dpp_member"])
    tpp_n = sum(1 for r in rows if r["tpp_member"])

    # Expected: KMT 1.7% ±50% (大 span 因為 10k sample 雜訊 + 乘數變異)
    # 下限是 0.5% (人為太嚴下限)，上限 4% (乘數最高 deep-blue 外省老兵不可能全押)
    assert 50 <= kmt_n <= 400, f"KMT rate {kmt_n/100:.2f}% outside 0.5-4.0%"
    assert 50 <= dpp_n <= 300, f"DPP rate {dpp_n/100:.2f}% outside 0.5-3.0%"
    assert 5 <= tpp_n <= 100, f"TPP rate {tpp_n/100:.2f}% outside 0.05-1.0%"

    # 深藍 agent 的 KMT 比例應顯著高於深綠
    deep_blue_rows = [r for r in rows if r["party_lean"] == "深藍"]
    deep_green_rows = [r for r in rows if r["party_lean"] == "深綠"]
    db_kmt_rate = sum(1 for r in deep_blue_rows if r["kmt_member"]) / max(1, len(deep_blue_rows))
    dg_kmt_rate = sum(1 for r in deep_green_rows if r["kmt_member"]) / max(1, len(deep_green_rows))
    assert db_kmt_rate > dg_kmt_rate * 5, \
        f"深藍 KMT 比例 {db_kmt_rate:.3f} 應 >> 深綠 {dg_kmt_rate:.3f}"

    # 深綠 agent 的 DPP 比例應顯著高於深藍
    db_dpp_rate = sum(1 for r in deep_blue_rows if r["dpp_member"]) / max(1, len(deep_blue_rows))
    dg_dpp_rate = sum(1 for r in deep_green_rows if r["dpp_member"]) / max(1, len(deep_green_rows))
    assert dg_dpp_rate > db_dpp_rate * 5, \
        f"深綠 DPP 比例 {dg_dpp_rate:.3f} 應 >> 深藍 {db_dpp_rate:.3f}"

    print(f"✅ _derive_party_member distribution OK")
    print(f"   Overall: KMT {kmt_n/100:.2f}% / DPP {dpp_n/100:.2f}% / TPP {tpp_n/100:.2f}%")
    print(f"   深藍 KMT rate: {db_kmt_rate*100:.2f}% (vs 深綠 {dg_kmt_rate*100:.3f}%)")
    print(f"   深綠 DPP rate: {dg_dpp_rate*100:.2f}% (vs 深藍 {db_dpp_rate*100:.3f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
