"""End-to-end smoke test for party primary template system.

Steps:
1. Generate 3 primary templates (松信 KMT councilor) via CLI.
2. Verify schema via scripts/verify_primary_template_schema.py.
3. Run synthesis-style row generation for 500 agents, check kmt_member rate sane.

Run: python3 scripts/verify_primary_template.py
Exit 0 = pass.
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TPL = ROOT / "data" / "templates"
sys.path.insert(0, str(ROOT / "ap" / "services" / "synthesis" / "app"))
sys.path.insert(0, str(ROOT / "ap"))


def _generate() -> None:
    print("=== Step 1: Generate 3 primary templates ===")
    r = subprocess.run([
        sys.executable, "scripts/build_templates.py", "--primary",
        "--party", "KMT", "--cycle", "2026", "--position", "councilor",
        "--constituency-name", "松信區",
        "--constituency-slug", "songshan_xinyi",
        "--townships", "臺北市|松山區,臺北市|信義區",
        "--candidates", "scripts/sample_data/candidates_songshan_kmt.json",
        "--rivals", "scripts/sample_data/rivals_songshan.json",
        "--output-methods", "intra,head2head,mixed",
    ], cwd=ROOT, check=True, capture_output=True, text=True)
    print(r.stdout)


def _verify_schema() -> None:
    print("=== Step 2: Schema verification ===")
    subprocess.run([sys.executable, "scripts/verify_primary_template_schema.py"],
                    cwd=ROOT, check=True)


def _check_synthesis_party_members() -> None:
    print("=== Step 3: Synthesis + party member distribution ===")

    # Use subprocess to run the synthesis check in proper environment
    import os
    check_script = '''
import sys
import json
import random
from pathlib import Path

ROOT = Path(sys.argv[1])
TPL = ROOT / "data" / "templates"
sys.path.insert(0, str(ROOT / "ap" / "services" / "synthesis" / "app"))
sys.path.insert(0, str(ROOT / "ap"))

from builder import _enforce_logical_consistency

tmpl = json.loads((TPL / "primary_2026_kmt_songshan_xinyi_councilor_intra.json")
                  .read_text(encoding="utf-8"))

rng = random.Random(20260418)

leans = [(c["value"], c["weight"])
         for c in tmpl["dimensions"]["party_lean"]["categories"]
         if c["weight"] > 0]
eths = [(c["value"], c["weight"])
        for c in tmpl["dimensions"]["ethnicity"]["categories"]
        if c["weight"] > 0]

def _pick(pairs):
    if not pairs:
        return ""
    r = rng.random()
    acc = 0.0
    for v, w in pairs:
        acc += w
        if r <= acc:
            return v
    return pairs[-1][0]

rows = []
for _ in range(500):
    row = {
        "age": rng.randint(20, 85),
        "gender": "男" if rng.random() < 0.5 else "女",
        "district": "臺北市|松山區",
        "county": "臺北市",
        "township": "臺北市|松山區",
        "party_lean": _pick(leans),
        "ethnicity": _pick(eths),
    }
    _enforce_logical_consistency(row)
    rows.append(row)

kmt_n = sum(1 for r in rows if r.get("kmt_member"))
rate = kmt_n / 500 * 100
print(f"KMT member rate: {rate:.2f}% (n={kmt_n}/500)")
assert 1.0 <= rate <= 15.0, f"KMT rate {rate:.2f}% outside expected range [1, 15]"

unset = sum(1 for r in rows if r.get("kmt_member") is None)
assert unset == 0, f"{unset} rows have kmt_member=None"

print("✅ Synthesis checks passed")
'''

    r = subprocess.run([sys.executable, "-c", check_script, str(ROOT)],
                       capture_output=True, text=True, check=True)
    print(f"   {r.stdout.strip()}")


def main() -> int:
    _generate()
    _verify_schema()
    _check_synthesis_party_members()
    print()
    print("✅ Party primary template system e2e smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
