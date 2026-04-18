"""Verify 3 primary template variants are schema-valid + self-consistent."""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TPL = ROOT / "data" / "templates"


def _check_tmpl(path: Path, method: str) -> None:
    t = json.loads(path.read_text(encoding="utf-8"))
    e = t["election"]

    assert e["type"] == "party_primary", f"{path.name}: type"
    assert e["primary_method"] == method, f"{path.name}: method"
    assert e["primary_party"] == "KMT", f"{path.name}: party"
    assert e["constituency_townships"] == ["臺北市|松山區", "臺北市|信義區"], \
        f"{path.name}: townships"
    assert e["party_member_stats"]["source_file"].endswith("party_members_2026.json"), \
        f"{path.name}: stats ref"

    party_breakdown = {c["party"] for c in e["candidates"]}
    if method == "intra":
        assert party_breakdown == {"KMT"}, f"{path.name}: intra should be KMT-only"
        assert e["rival_candidates"] == [], f"{path.name}: intra has no rivals"
    else:
        assert "KMT" in party_breakdown, f"{path.name}: must contain KMT cands"
        assert len(e["rival_candidates"]) > 0, f"{path.name}: need rivals"

    if method == "mixed":
        f = e["primary_formula"]
        assert abs(sum(f.values()) - 1.0) < 0.01, f"{path.name}: formula sum != 1"
    else:
        assert e["primary_formula"] == {}, f"{path.name}: non-mixed has no formula"

    sc = e["primary_sampling"]
    assert sc["default_poll_days"] == 3
    assert "landline" in sc["frames"] and "mobile" in sc["frames"]
    assert "party_member" in sc["frames"]

    assert t["election"]["default_calibration_params"]["news_impact"] == 1.5

    assert t["target_count"] > 0
    assert t["dimensions"]["township"]["categories"][0]["value"].startswith("臺北市|")

    print(f"  ✅ {path.name}")


def main() -> int:
    for method in ("intra", "head2head", "mixed"):
        path = TPL / f"primary_2026_kmt_songshan_xinyi_councilor_{method}.json"
        assert path.exists(), f"missing: {path}"
        _check_tmpl(path, method)
    print("✅ All 3 primary templates schema-valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
