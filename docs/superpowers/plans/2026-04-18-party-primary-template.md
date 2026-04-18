# 黨內初選 Template 系統 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Civatas-TW 平台加上「黨內初選」template 類型，支援互比式/對比式/混合三種初選方式、市話/手機/雙軌/黨員四種採樣框、連續 N 天滾動民調，並自動推導 agent 的黨員身份。

**Architecture:** 新的 `election.type = "party_primary"` variant，Person schema +3 bool 衍生欄位（kmt/dpp/tpp_member），synthesis 層依 party_lean × age × ethnicity × county 乘數推導，`build_templates.py` 加 `--primary` 子命令產 3 method variant JSON 檔，evolver/predictor 依 method 走不同 scoring+sampling 分支，PredictionPanel 加初選模式 section。

**Tech Stack:** Python 3.11（synthesis/evolution/api/scripts）、FastAPI、Pydantic、TypeScript/Next.js React（web）、Docker Compose（runtime）。**既有 codebase 無 pytest** —— 本 plan 沿用 `ap/scripts/test_pipeline.sh` 風格，用 `scripts/verify_*.py` 直接 assert 的方式做驗證。所有 verify script 皆以 `python3 scripts/verify_xxx.py` 執行，exit 0 = pass，non-zero = fail。

**Spec 參照：** `docs/superpowers/specs/2026-04-18-party-primary-template-design.md`

---

## 檔案結構

### 新增檔案

| 路徑 | 責任 |
|---|---|
| `ap/shared/tw_data/party_members_2026.json` | 各黨黨員數 snapshot + 來源 URL，機器可讀 |
| `scripts/refresh_party_members.py` | 手動刷新黨員數（WebFetch + regex） |
| `scripts/verify_party_member_derivation.py` | 驗證 synthesis 黨員推導分佈 |
| `scripts/verify_primary_template.py` | 松信 KMT 初選 end-to-end smoke test |
| `scripts/sample_data/candidates_songshan_kmt.json` | 範例黨內參選人 JSON |
| `scripts/sample_data/rivals_songshan.json` | 範例對手黨候選人 JSON |
| `data/templates/primary_2026_kmt_songshan_xinyi_councilor_intra.json` | 產出：互比式 |
| `data/templates/primary_2026_kmt_songshan_xinyi_councilor_head2head.json` | 產出：對比式 |
| `data/templates/primary_2026_kmt_songshan_xinyi_councilor_mixed.json` | 產出：混合式 |

### 修改檔案

| 路徑 | 改動概述 |
|---|---|
| `ap/shared/schemas/person.py` | +3 optional bool: kmt_member / dpp_member / tpp_member |
| `ap/services/synthesis/app/builder.py` | 新增 `_derive_party_member()` + `_write_generation_report()`；接入 `_enforce_logical_consistency` |
| `scripts/build_templates.py` | 新增 `--primary` argparse、`_build_primary_election_block`、`_generate_primary_templates`、`primary` calibration profile |
| `ap/services/evolution/app/evolver.py` | Scoring loop 偵測 `election.type == "party_primary"`，依 `primary_method` 走 intra/head2head/mixed 分支 |
| `ap/services/evolution/app/predictor.py` | `_apply_sampling_frame` / `_tally_intra` / `_tally_head2head` / `_run_rolling_poll` / `_compose_mixed_result` |
| `ap/services/api/app/routes/templates.py` | Surface primary 欄位給 web |
| `ap/services/web/src/lib/api.ts` | `TemplateMeta.election` TypeScript 介面擴充 |
| `ap/services/web/src/components/panels/PredictionPanel.tsx` | 新增初選模式 section（只在 party_primary template 顯示） |
| `ap/services/web/src/lib/template-defaults.ts` | 新增 primary method 預設值 helper |

---

## Task 1: 建立黨員統計資料 snapshot

**Files:**
- Create: `ap/shared/tw_data/party_members_2026.json`
- Test: `scripts/verify_party_member_snapshot.py`

- [ ] **Step 1: 建立 snapshot JSON**

建立 `ap/shared/tw_data/party_members_2026.json`：

```json
{
  "as_of": "2026-04-18",
  "adult_pop_20plus": 19500000,
  "adult_pop_source": "國發會 2026 人口推估中位估計",
  "parties": {
    "KMT": {
      "count": 331410,
      "voting_eligible": 331410,
      "as_of_date": "2025-09-10",
      "label": "繳費黨員（2025 第 11 屆主席及黨代表投票人數）",
      "sources": [
        {"url": "https://www.kmt.org.tw/2025/09/blog-post_25.html", "fetched": "2026-04-18", "note": "KMT 中央黨部公告"},
        {"url": "https://zh.wikipedia.org/wiki/%E4%B8%AD%E5%9C%8B%E5%9C%8B%E6%B0%91%E9%BB%A8", "fetched": "2026-04-18", "note": "維基 2025 資訊框 331145，與官網相符"}
      ]
    },
    "DPP": {
      "count": 240000,
      "voting_eligible": 240000,
      "as_of_date": "2023-01-01",
      "label": "具完整黨權黨員（2023 年維基百科引用）",
      "sources": [
        {"url": "https://zh.wikipedia.org/wiki/%E6%B0%91%E4%B8%BB%E9%80%B2%E6%AD%A5%E9%BB%A8", "fetched": "2026-04-18"}
      ],
      "estimate_note": "2024-25 官方未公開更新；以 2023 年值為基準，假設 ±10% 年波動（區間 [216000, 264000]）"
    },
    "TPP": {
      "count": 32546,
      "voting_eligible": 32546,
      "as_of_date": "2025-08-10",
      "label": "有效黨員（黃國昌 6 週年黨慶公布）",
      "sources": [
        {"url": "https://www.cna.com.tw/news/aipl/202508100030.aspx", "fetched": "2026-04-18", "note": "中央社報導"}
      ]
    }
  }
}
```

- [ ] **Step 2: 建立 verify script**

Create `scripts/verify_party_member_snapshot.py`：

```python
"""Verify party_members snapshot schema and sanity.

Run: python3 scripts/verify_party_member_snapshot.py
Exit 0 = pass.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from datetime import date, datetime

ROOT = Path(__file__).resolve().parent.parent
SNAP = ROOT / "ap" / "shared" / "tw_data" / "party_members_2026.json"


def main() -> int:
    data = json.loads(SNAP.read_text(encoding="utf-8"))

    # Required top-level keys
    for k in ("as_of", "adult_pop_20plus", "parties"):
        assert k in data, f"missing top-level key: {k}"

    # adult_pop_20plus sane range (18-22M)
    assert 18_000_000 <= data["adult_pop_20plus"] <= 22_000_000, "adult pop out of range"

    # Each party has count + sources
    for party_code in ("KMT", "DPP", "TPP"):
        p = data["parties"][party_code]
        assert p["count"] > 0, f"{party_code} count must be positive"
        assert p["count"] < 1_000_000, f"{party_code} count unreasonably large"
        assert isinstance(p["sources"], list) and len(p["sources"]) >= 1, \
            f"{party_code} must have at least 1 source"
        for s in p["sources"]:
            assert s["url"].startswith("http"), f"{party_code} source url invalid"

    # as_of within reasonable window
    as_of = date.fromisoformat(data["as_of"])
    assert as_of.year >= 2024, "as_of too old"

    print(f"✅ party_members snapshot OK ({SNAP})")
    print(f"   KMT: {data['parties']['KMT']['count']:,}")
    print(f"   DPP: {data['parties']['DPP']['count']:,}")
    print(f"   TPP: {data['parties']['TPP']['count']:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Run verify**

```bash
python3 scripts/verify_party_member_snapshot.py
```

Expected output:
```
✅ party_members snapshot OK (...)
   KMT: 331,410
   DPP: 240,000
   TPP: 32,546
```

- [ ] **Step 4: Commit**

```bash
git add ap/shared/tw_data/party_members_2026.json scripts/verify_party_member_snapshot.py
git commit -m "feat(primary): 黨員統計 snapshot + 驗證 script

KMT 331,410 / DPP 240,000 (估) / TPP 32,546，附來源 URL 與 fetch 日期。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Person schema 新增黨員 bool 欄位

**Files:**
- Modify: `ap/shared/schemas/person.py`

- [ ] **Step 1: 加 3 個 optional bool**

Edit `ap/shared/schemas/person.py`，在 `origin_province` 之後、`custom_fields` 之前插入：

```python
    # Taiwan party membership (derived by synthesis _derive_party_member)
    # None = 未推導（舊 persona backward compat）；True/False = 推導結果
    # 台灣選民可跨黨登記，所以三個欄位各自獨立 bool（非互斥）
    kmt_member: bool | None = None
    dpp_member: bool | None = None
    tpp_member: bool | None = None
```

- [ ] **Step 2: Docstring 補說明**

在 class Person 的 docstring（line 17-27 附近），在 "- origin_province" 那行後面加：

```python
      - kmt_member / dpp_member / tpp_member
                     黨員身份（synthesis 推導，新 workspace 才有；None = 未推導）
```

- [ ] **Step 3: 驗證 import 不壞**

```bash
cd ap && python3 -c "from shared.schemas.person import Person; p = Person(person_id=1, age=30, gender='男', district='測試'); print('kmt_member:', p.kmt_member); print('dpp_member:', p.dpp_member); print('tpp_member:', p.tpp_member)"
```

Expected output:
```
kmt_member: None
dpp_member: None
tpp_member: None
```

- [ ] **Step 4: 驗證 backward compat（舊資料可 load）**

```bash
cd ap && python3 -c "
from shared.schemas.person import Person
# 模擬舊 persona 沒有新欄位
old_data = {'person_id': 1, 'age': 30, 'gender': '男', 'district': '臺北市|大安區', 'ethnicity': '閩南', 'party_lean': '偏綠'}
p = Person(**old_data)
assert p.kmt_member is None
assert p.dpp_member is None
assert p.tpp_member is None
print('✅ backward compat OK')
"
```

- [ ] **Step 5: Commit**

```bash
git add ap/shared/schemas/person.py
git commit -m "feat(primary): Person schema +3 黨員 bool 欄位

kmt_member / dpp_member / tpp_member 為 optional，None 代表未推導
（舊 persona backward compat）；synthesis _derive_party_member 會填值。
跨黨員登記（台灣選民可同時為多黨黨員）用三個獨立 bool 表達。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Synthesis `_derive_party_member` helper

**Files:**
- Modify: `ap/services/synthesis/app/builder.py`
- Test: `scripts/verify_party_member_derivation.py`

- [ ] **Step 1: 定位插入點**

讀取 `ap/services/synthesis/app/builder.py` line 660-900 區段（包含 `_enforce_logical_consistency`），確認 cross_strait 推導 block 結束位置（約 line 895）。`_derive_party_member` 要加在同一個函式內部，cross_strait 之後。

- [ ] **Step 2: 寫 verify script 先定義預期行為**

Create `scripts/verify_party_member_derivation.py`：

```python
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
```

- [ ] **Step 3: Run verify to confirm it fails**

```bash
python3 scripts/verify_party_member_derivation.py
```

Expected: `ImportError: cannot import name '_derive_party_member'` — 這是對的，我們還沒寫。

- [ ] **Step 4: 實作 `_derive_party_member`**

在 `ap/services/synthesis/app/builder.py` 頂端 imports 附近（現有 imports block 之後）加：

```python
# 黨員基準率 (count / adult_pop_20plus)；從 ap/shared/tw_data/party_members_2026.json 同步
_PARTY_MEMBER_BASE_RATES = {
    "KMT": 331_410 / 19_500_000,   # ~1.70%
    "DPP": 240_000 / 19_500_000,   # ~1.23%
    "TPP":  32_546 / 19_500_000,   # ~0.17%
}

# 乘數表：tuple = (KMT_×, DPP_×, TPP_×)
_PARTY_MEMBER_LEAN_BOOST = {
    "深藍":  (6.0, 0.05, 0.8),
    "偏藍":  (3.0, 0.20, 1.5),
    "中間":  (0.3, 0.3,  1.5),
    "偏綠":  (0.1, 3.0,  0.5),
    "深綠":  (0.05, 6.0, 0.2),
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
```

- [ ] **Step 5: Run verify to confirm it passes**

```bash
python3 scripts/verify_party_member_derivation.py
```

Expected:
```
✅ _derive_party_member distribution OK
   Overall: KMT 1.xx% / DPP 1.xx% / TPP 0.xx%
   深藍 KMT rate: ~10% (vs 深綠 ~0.0x%)
   深綠 DPP rate: ~7% (vs 深藍 ~0.0x%)
```

- [ ] **Step 6: Commit**

```bash
git add ap/services/synthesis/app/builder.py scripts/verify_party_member_derivation.py
git commit -m "feat(primary): _derive_party_member 黨員機率推導

基準率 × lean × age × ethnicity × county 四層乘數，cap 0.6。
驗證 10k rows：深藍 KMT ~10%、深綠 DPP ~7%，與實況相符。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: 接入 `_enforce_logical_consistency`

**Files:**
- Modify: `ap/services/synthesis/app/builder.py` (_enforce_logical_consistency 末段)

- [ ] **Step 1: 定位呼叫點**

在 `_enforce_logical_consistency` 內部，cross_strait 推導 block 結束之後（現檔約 line 895 之後），加入：

```python
    # ───── 黨員身份推導（Stage 9 加） ─────
    # 只推導一次：若 row 已有 *_member 欄位（由上游帶入）就不覆蓋
    if row.get("kmt_member") is None:
        _derive_party_member(row, _rng)
```

注意 `_rng` 變數名需與該函式內既有 rng 變數一致（既有 cross_strait 區段也用 `_rng`，延用）。

- [ ] **Step 2: 驗證舊 persona 不被破壞**

Create tmp verify：

```bash
cd ap && python3 -c "
import sys
sys.path.insert(0, 'services/synthesis/app')
from builder import _enforce_logical_consistency

# 模擬舊 persona 無 age_bucket/party_lean（degenerate case）
row1 = {'age': 30, 'gender': '男', 'district': '臺北市|大安區'}
_enforce_logical_consistency(row1)
assert 'kmt_member' in row1
assert isinstance(row1['kmt_member'], bool)

# 模擬有既存 kmt_member 的 row（不該覆蓋）
row2 = {'age': 30, 'gender': '男', 'district': '...', 'kmt_member': True}
_enforce_logical_consistency(row2)
assert row2['kmt_member'] is True  # preserved

print('✅ _enforce_logical_consistency integration OK')
"
```

Expected: `✅ _enforce_logical_consistency integration OK`

- [ ] **Step 3: Commit**

```bash
git add ap/services/synthesis/app/builder.py
git commit -m "feat(primary): _enforce_logical_consistency 接入黨員推導

cross_strait 推導後呼叫 _derive_party_member；已有 kmt_member 值的
row 不覆蓋（供外部 pipeline 覆寫）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: `build_templates.py` 加 `primary` calibration profile

**Files:**
- Modify: `scripts/build_templates.py` (`_calibration_defaults` 函式)

- [ ] **Step 1: 定位**

在 `_calibration_defaults()` 內部（現檔約 line 300-326），`if profile == "county":` 之後、`return base` 之前，加：

```python
    if profile == "primary":
        # 黨內初選：新聞短期影響較低（選民黨員投票傾向不易撼動），
        # 本地議題主導（選區型），現任優勢明顯。
        return {**base, "news_impact": 1.5, "base_undecided": 0.15,
                "shift_consecutive_days_req": 3,
                "incumbency_bonus": 10,
                "news_mix_candidate": 40, "news_mix_national": 10,
                "news_mix_local": 45, "news_mix_international": 5}
```

- [ ] **Step 2: 驗證**

```bash
python3 -c "
import sys; sys.path.insert(0, 'scripts')
from build_templates import _calibration_defaults
p = _calibration_defaults('primary')
assert p['news_impact'] == 1.5
assert p['incumbency_bonus'] == 10
assert p['news_mix_local'] == 45
print('✅ primary calibration profile OK:', p)
"
```

- [ ] **Step 3: Commit**

```bash
git add scripts/build_templates.py
git commit -m "feat(primary): 新增 primary calibration profile

news_impact 1.5（短期不易動搖）、base_undecided 0.15、
shift_consecutive_days_req 3、incumbency_bonus 10（初選現任強）、
news_mix_local 45% 主導。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: `build_templates.py` 擴充 election block builder

**Files:**
- Modify: `scripts/build_templates.py` (`_build_election_block` 函式 signature + body)

- [ ] **Step 1: 擴充 `_build_election_block` signature**

找到 `def _build_election_block(` (line ~329)，在既有 kwargs 之後新增 primary-specific kwargs（全部 optional）：

```python
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
    use_electoral: bool = False,
    # Primary-specific (optional; only populated for etype == "party_primary")
    primary_party: str | None = None,
    primary_method: str | None = None,
    primary_position: str | None = None,
    constituency_name: str | None = None,
    constituency_townships: list[str] | None = None,
    rival_candidates: list[dict] | None = None,
    primary_formula: dict | None = None,
    primary_sampling: dict | None = None,
    party_member_stats_ref: dict | None = None,
) -> dict:
```

- [ ] **Step 2: 在回傳 dict 加欄位**

`_build_election_block` 末段 `return { ... }` 的 dict literal 裡，在 `"use_electoral_college": use_electoral,` 之後加：

```python
        # Primary-specific fields (None for non-primary templates)
        "primary_party": primary_party,
        "primary_method": primary_method,
        "primary_position": primary_position,
        "constituency_name": constituency_name,
        "constituency_townships": constituency_townships or [],
        "rival_candidates": rival_candidates or [],
        "primary_formula": primary_formula or {},
        "primary_sampling": primary_sampling or {},
        "party_member_stats": party_member_stats_ref or {},
```

- [ ] **Step 3: 驗證 既有 call site 不壞（backward compat）**

```bash
python3 -c "
import sys; sys.path.insert(0, 'scripts')
from build_templates import _build_election_block
block = _build_election_block(
    etype='presidential', scope='national', cycle=2028, is_generic=False,
    candidates=[{'id': 'lai', 'name': '賴', 'party': 'DPP'}],
    calib_profile='2028', macro_en='x', macro_zh='x',
    local_keywords=[], national_keywords=[],
)
assert block['type'] == 'presidential'
assert block['primary_party'] is None
assert block['constituency_townships'] == []
assert block['rival_candidates'] == []
print('✅ backward compat OK, new fields defaulted')
"
```

- [ ] **Step 4: Commit**

```bash
git add scripts/build_templates.py
git commit -m "feat(primary): _build_election_block +9 primary-specific kwargs

新增 optional primary_party / primary_method / primary_position /
constituency_name / constituency_townships / rival_candidates /
primary_formula / primary_sampling / party_member_stats_ref，
既有 call site (presidential/mayoral/poll/county) 不受影響。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: `build_templates.py` 加 `_build_primary_dimensions` + CLI argparse

**Files:**
- Modify: `scripts/build_templates.py`

- [ ] **Step 1: 新增 primary sampling frames 常數**

在 `_calibration_defaults` 前後合適位置加：

```python
PRIMARY_SAMPLING_FRAMES_DEFAULT = {
    "landline": {
        "age_weights": {"20-24": 0.3, "25-34": 0.3, "35-44": 0.6,
                         "45-54": 1.1, "55-64": 1.7, "65+": 2.2},
        "description": "市話抽樣偏高齡"
    },
    "mobile": {
        "age_weights": {"20-24": 1.8, "25-34": 1.8, "35-44": 1.3,
                         "45-54": 1.0, "55-64": 0.5, "65+": 0.2},
        "description": "手機抽樣偏年輕"
    },
    "dual": {
        "age_weights": {"20-24": 1.0, "25-34": 1.0, "35-44": 1.0,
                         "45-54": 1.0, "55-64": 1.0, "65+": 1.0},
        "description": "市話手機各 50%"
    },
    "party_member": {
        "filter": "is_party_member=true",  # predictor 層解析成 {party}_member=True
        "description": "只有黨員可投"
    },
}

PRIMARY_FORMULA_DEFAULTS = {
    # KMT 歷次初選常見：5 互比 / 3 對比 / 2 黨員
    "KMT": {"intra_poll_weight": 0.5, "head2head_poll_weight": 0.3, "party_member_weight": 0.2},
    # DPP 近年偏 100% 對比
    "DPP": {"intra_poll_weight": 0.2, "head2head_poll_weight": 0.8, "party_member_weight": 0.0},
    # TPP 新黨無固定 formula，均分
    "TPP": {"intra_poll_weight": 0.4, "head2head_poll_weight": 0.4, "party_member_weight": 0.2},
}
```

- [ ] **Step 2: 新增 `_build_primary_dimensions` helper**

加在 `_calibration_defaults` 附近：

```python
def _build_primary_dimensions(township_admin_keys: list[str]) -> tuple[dict, dict]:
    """Aggregate dimensions from specified townships into a constituency-scope block.

    township_admin_keys: ["臺北市|松山區", "臺北市|信義區"]
    回傳 (dims_dict, summary_dict)
    """
    townships_data = json.loads((CENSUS / "townships.json").read_text(encoding="utf-8"))

    # townships.json is a list of per-township summaries
    matched = [t for t in townships_data
               if f"{t.get('county')}|{t.get('township')}" in township_admin_keys]
    if not matched:
        raise ValueError(f"No townships matched: {township_admin_keys}")

    # Sum each dimension bucket across matched townships
    gender = sum_dim(matched, "gender")
    age = sum_dim(matched, "age")
    education = sum_dim(matched, "education")
    employment = sum_dim(matched, "employment")
    tenure = sum_dim(matched, "tenure")
    household_type = sum_dim(matched, "household_type")
    household_income = sum_dim(matched, "household_income")
    ethnicity = sum_dim(matched, "ethnicity")
    party_lean = sum_dim(matched, "party_lean")

    population_total = sum(t.get("population_18plus", 0) for t in matched)

    dims = {
        "gender": {"type": "categorical",
                   "categories": round_weights([(k, v) for k, v in gender.items()])},
        "age": {"type": "range",
                "bins": [{"range": v, "weight": w["weight"]}
                         for v, w in zip(AGE_VALUES,
                                          round_weights([(v, age.get(v, 0)) for v in AGE_VALUES]))]},
        # ...（其餘維度同 pattern）
        # 為精簡：用 helper loop 一次處理
    }

    # Simpler: loop every dim
    dims = {}
    for dim_name, values, raw_counts in [
        ("gender", [v for v, _ in GENDER_VALUES], gender),
        ("education", EDU_VALUES, education),
        ("employment", EMPLOY_VALUES, employment),
        ("tenure", TENURE_VALUES, tenure),
        ("household_type", HOUSEHOLD_TYPE_VALUES, household_type),
        ("household_income", INCOME_VALUES, household_income),
        ("ethnicity", ETHNICITY_VALUES, ethnicity),
        ("party_lean", PARTY_LEAN_VALUES, party_lean),
    ]:
        dims[dim_name] = {"type": "categorical",
                          "categories": round_weights([(v, raw_counts.get(v, 0)) for v in values])}
    dims["age"] = {"type": "range",
                   "bins": [{"range": v, "weight": w["weight"]}
                            for v, w in zip(AGE_VALUES,
                                             round_weights([(v, age.get(v, 0)) for v in AGE_VALUES]))]}

    # county/township 維度收斂：只有選區內的 township
    townships_block = round_weights([
        (k, sum(t.get("population_18plus", 0) for t in matched
                if f"{t.get('county')}|{t.get('township')}" == k))
        for k in township_admin_keys
    ])
    counties_in = list({k.split("|")[0] for k in township_admin_keys})
    dims["county"] = {"type": "categorical",
                      "categories": [{"value": c, "weight": round(1.0 / len(counties_in), 4)}
                                      for c in counties_in]}
    dims["township"] = {"type": "categorical", "categories": townships_block}

    bucket_counts = {k: party_lean.get(k, 0) for k in PARTY_LEAN_VALUES}
    summary = {
        "population_total": population_total,
        "township_count": len(matched),
        "county_count": len(counties_in),
        "bucket_counts": bucket_counts,
    }
    return dims, summary
```

- [ ] **Step 3: 新增 argparse `--primary` 支援**

找到 `main()` (檔案末段 argparse) 的 ArgumentParser，加：

```python
    ap.add_argument("--primary", action="store_true",
                    help="Generate party primary templates (3 variants: intra/head2head/mixed)")
    ap.add_argument("--party", choices=["KMT", "DPP", "TPP"],
                    help="Primary party (required with --primary)")
    ap.add_argument("--cycle", type=int, default=2026, help="Election year")
    ap.add_argument("--position", default="councilor",
                    choices=["councilor", "legislator", "mayor", "magistrate", "president"])
    ap.add_argument("--constituency-name", help="Human-readable constituency name, e.g. 松信區")
    ap.add_argument("--constituency-slug",
                    help="Slug for filename (Pinyin), e.g. songshan_xinyi")
    ap.add_argument("--townships",
                    help='Comma-separated admin_keys, e.g. "臺北市|松山區,臺北市|信義區"')
    ap.add_argument("--candidates",
                    help="Path to JSON file with intra-party candidates list")
    ap.add_argument("--rivals",
                    help="Path to JSON file with rival-party candidates (for head2head/mixed)")
    ap.add_argument("--formula",
                    help='Mixed formula override, e.g. "intra=0.5,head2head=0.3,member=0.2"')
    ap.add_argument("--poll-days", type=int, default=3)
    ap.add_argument("--sampling-frame", default="dual",
                    choices=["landline", "mobile", "dual"])
    ap.add_argument("--output-methods", default="intra,head2head,mixed",
                    help="Comma list of method variants to output")
```

- [ ] **Step 4: 驗證 argparse 不壞既有 flags**

```bash
python3 scripts/build_templates.py --help 2>&1 | head -40
```

Expected: 正常印出 help，包含新 `--primary` flag。

- [ ] **Step 5: Commit**

```bash
git add scripts/build_templates.py
git commit -m "feat(primary): _build_primary_dimensions + CLI flags

聚合多 township 成 constituency 維度；新增 --primary 系列 argparse
flags 控制黨/選區/參選人/方法等參數。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: `build_templates.py` 產出 3 method variants

**Files:**
- Modify: `scripts/build_templates.py` (main + new `_generate_primary_templates`)

- [ ] **Step 1: 讀取 party_members_2026.json helper**

在檔案頂部 imports 下面加：

```python
SHARED_TW = ROOT / "ap" / "shared" / "tw_data"


def _load_party_member_stats() -> dict:
    path = SHARED_TW / "party_members_2026.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
```

- [ ] **Step 2: 新增 `_generate_primary_templates`**

加在 `_build_primary_dimensions` 之後：

```python
def _generate_primary_templates(args) -> None:
    """Generate 3 template variants for a party primary (intra/head2head/mixed)."""
    if not args.party:
        raise SystemExit("--primary requires --party")
    if not args.townships:
        raise SystemExit("--primary requires --townships")
    if not args.candidates:
        raise SystemExit("--primary requires --candidates JSON path")
    if not args.constituency_slug:
        raise SystemExit("--primary requires --constituency-slug")

    # Load candidates / rivals
    cands = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
    rivals = (json.loads(Path(args.rivals).read_text(encoding="utf-8"))
              if args.rivals else [])

    # Parse townships
    township_keys = [t.strip() for t in args.townships.split(",") if t.strip()]

    # Formula
    formula = PRIMARY_FORMULA_DEFAULTS.get(args.party, PRIMARY_FORMULA_DEFAULTS["KMT"]).copy()
    if args.formula:
        for part in args.formula.split(","):
            k, v = part.split("=")
            k = k.strip()
            v = float(v.strip())
            if k in ("intra", "intra_poll"): formula["intra_poll_weight"] = v
            elif k in ("head2head", "h2h"): formula["head2head_poll_weight"] = v
            elif k in ("member", "party_member"): formula["party_member_weight"] = v
        # Normalize
        s = sum(formula.values())
        if s > 0:
            formula = {k: round(v / s, 4) for k, v in formula.items()}

    # Sampling config
    sampling_cfg = {
        "default_poll_days": args.poll_days,
        "default_sampling_frame": args.sampling_frame,
        "default_daily_n": 600,
        "frames": PRIMARY_SAMPLING_FRAMES_DEFAULT,
    }

    # Party member stats ref
    stats = _load_party_member_stats()
    stats_ref = {
        "as_of": stats.get("as_of"),
        "source_file": "ap/shared/tw_data/party_members_2026.json",
        "note": "推導 is_party_member 使用的黨員數與來源見 source_file",
    }

    # Aggregate dimensions
    dims, summary = _build_primary_dimensions(township_keys)

    methods = [m.strip() for m in args.output_methods.split(",") if m.strip()]

    for method in methods:
        if method not in ("intra", "head2head", "mixed"):
            print(f"[skip] unknown method: {method}")
            continue

        # Candidates for this variant
        if method == "intra":
            vcands = cands
        elif method == "head2head":
            vcands = cands + rivals    # prediction 時計算時分離，evolver 全部 feed
        else:  # mixed
            vcands = cands + rivals

        macro_zh = (f"{args.cycle} 年 {args.party} "
                    f"{args.constituency_name or args.constituency_slug} "
                    f"{args.position} 黨內初選（{method}）")
        macro_en = (f"{args.cycle} {args.party} primary for {args.position} "
                    f"in {args.constituency_name or args.constituency_slug} ({method})")

        election = _build_election_block(
            etype="party_primary",
            scope="constituency",
            cycle=args.cycle,
            is_generic=False,
            candidates=vcands,
            calib_profile="primary",
            macro_en=macro_en,
            macro_zh=macro_zh,
            local_keywords=[],      # 使用者 UI 填
            national_keywords=[],
            primary_party=args.party,
            primary_method=method,
            primary_position=args.position,
            constituency_name=args.constituency_name,
            constituency_townships=township_keys,
            rival_candidates=rivals if method != "intra" else [],
            primary_formula=formula if method == "mixed" else {},
            primary_sampling=sampling_cfg,
            party_member_stats_ref=stats_ref,
        )

        tmpl = compose(
            name_en=f"{args.cycle} {args.party} {args.constituency_slug} {args.position} primary {method}",
            name_zh=f"{args.cycle} {args.party} {args.constituency_name} {args.position} 黨內初選（{method}）",
            region=args.constituency_name or args.constituency_slug,
            region_code=args.constituency_slug,
            target_count=500,
            dims=dims,
            summary=summary,
            metadata_extra={"note": f"party_primary {method} variant"},
            election=election,
        )

        fname = (f"primary_{args.cycle}_{args.party.lower()}_{args.constituency_slug}"
                 f"_{args.position}_{method}.json")
        out_path = TPL / fname
        out_path.write_text(json.dumps(tmpl, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  → {out_path}")
```

- [ ] **Step 3: 主 entry point 接上**

找到 main() 裡 `args = ap.parse_args()` 之後的 dispatch 區塊，加：

```python
    if args.primary:
        print(f"[primary] Generating templates for {args.cycle} {args.party} "
              f"{args.constituency_name or args.constituency_slug} {args.position}...")
        _generate_primary_templates(args)
        print("Done.")
        return
```

放在既有 `if args.all:` / `if args.national:` 等 dispatch 之前。

- [ ] **Step 4: Commit**

```bash
git add scripts/build_templates.py
git commit -m "feat(primary): _generate_primary_templates 3-variant generator

依 --output-methods 產出 intra/head2head/mixed 3 JSON 檔。
intra 只有黨內參選人、head2head/mixed 含對手 candidates。
Party member stats 從 party_members_2026.json 載入，stats_ref 寫入 template。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: 產出松信 KMT 範例 template + schema 驗證

**Files:**
- Create: `scripts/sample_data/candidates_songshan_kmt.json`
- Create: `scripts/sample_data/rivals_songshan.json`
- Create: `scripts/verify_primary_template_schema.py`

- [ ] **Step 1: 建立 sample candidates**

Create `scripts/sample_data/candidates_songshan_kmt.json`：

```json
[
  {
    "id": "kmt_cand_a",
    "name": "李彥秀",
    "name_en": "Alicia Lee",
    "party": "KMT",
    "party_label": "國民黨",
    "is_incumbent": true,
    "color": "#000095",
    "description": "國民黨籍，時任松信選區議員尋求連任，深耕地方三屆；支持者為松信鄰里長、年長公教族群。"
  },
  {
    "id": "kmt_cand_b",
    "name": "王鴻薇",
    "name_en": "Wang Hung-wei",
    "party": "KMT",
    "party_label": "國民黨",
    "is_incumbent": false,
    "color": "#0000C8",
    "description": "國民黨籍，媒體戰鬥力強，主打反貪腐議題；支持者為深藍中堅、政論節目觀眾。"
  },
  {
    "id": "kmt_cand_c",
    "name": "徐巧芯",
    "name_en": "Hsu Chiao-hsin",
    "party": "KMT",
    "party_label": "國民黨",
    "is_incumbent": false,
    "color": "#1B40A4",
    "description": "國民黨籍，年輕新生代，善用社群媒體；支持者為年輕藍營、白領專業族群。"
  }
]
```

（註：以上為示範人選；實際 2026 候選人可能不同。此檔僅供測試流程，使用者可用自己的 list 覆寫。）

- [ ] **Step 2: 建立 sample rivals**

Create `scripts/sample_data/rivals_songshan.json`：

```json
[
  {
    "id": "dpp_rival_a",
    "name": "吳沛憶",
    "name_en": "Wu Pei-i",
    "party": "DPP",
    "party_label": "民進黨",
    "is_incumbent": false,
    "color": "#1B9431",
    "description": "民進黨籍，松信選區耕耘中，主打青年政策；支持者為年輕綠營、進步派。"
  },
  {
    "id": "tpp_rival_a",
    "name": "林珍羽",
    "name_en": "Lin Chen-yu",
    "party": "TPP",
    "party_label": "民眾黨",
    "is_incumbent": false,
    "color": "#28C8C8",
    "description": "民眾黨籍，地方樁腳經營佳；支持者為白色力量、中間選民。"
  }
]
```

- [ ] **Step 3: 跑 generator 產出 3 templates**

```bash
python3 scripts/build_templates.py --primary \
    --party KMT \
    --cycle 2026 \
    --position councilor \
    --constituency-name "松信區" \
    --constituency-slug songshan_xinyi \
    --townships "臺北市|松山區,臺北市|信義區" \
    --candidates scripts/sample_data/candidates_songshan_kmt.json \
    --rivals scripts/sample_data/rivals_songshan.json \
    --output-methods intra,head2head,mixed
```

Expected output:
```
[primary] Generating templates for 2026 KMT 松信區 councilor...
  → data/templates/primary_2026_kmt_songshan_xinyi_councilor_intra.json
  → data/templates/primary_2026_kmt_songshan_xinyi_councilor_head2head.json
  → data/templates/primary_2026_kmt_songshan_xinyi_councilor_mixed.json
Done.
```

- [ ] **Step 4: 建立 schema verify**

Create `scripts/verify_primary_template_schema.py`：

```python
"""Verify 3 primary template variants are schema-valid + self-consistent.

Run: python3 scripts/verify_primary_template_schema.py
"""
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

    # Candidates / rivals
    party_breakdown = {c["party"] for c in e["candidates"]}
    if method == "intra":
        assert party_breakdown == {"KMT"}, f"{path.name}: intra should be KMT-only"
        assert e["rival_candidates"] == [], f"{path.name}: intra has no rivals"
    else:
        assert "KMT" in party_breakdown, f"{path.name}: must contain KMT cands"
        assert len(e["rival_candidates"]) > 0, f"{path.name}: need rivals"

    # Formula
    if method == "mixed":
        f = e["primary_formula"]
        assert abs(sum(f.values()) - 1.0) < 0.01, f"{path.name}: formula sum != 1"
    else:
        assert e["primary_formula"] == {}, f"{path.name}: non-mixed has no formula"

    # Sampling cfg
    sc = e["primary_sampling"]
    assert sc["default_poll_days"] == 3
    assert "landline" in sc["frames"] and "mobile" in sc["frames"]
    assert "party_member" in sc["frames"]

    # Calibration
    assert t["election"]["default_calibration_params"]["news_impact"] == 1.5

    # Dimensions aggregated
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
```

- [ ] **Step 5: Run verify**

```bash
python3 scripts/verify_primary_template_schema.py
```

Expected:
```
  ✅ primary_2026_kmt_songshan_xinyi_councilor_intra.json
  ✅ primary_2026_kmt_songshan_xinyi_councilor_head2head.json
  ✅ primary_2026_kmt_songshan_xinyi_councilor_mixed.json
✅ All 3 primary templates schema-valid
```

- [ ] **Step 6: Commit**

```bash
git add scripts/sample_data/ scripts/verify_primary_template_schema.py \
        data/templates/primary_2026_kmt_songshan_xinyi_councilor_*.json
git commit -m "feat(primary): 松信 KMT 初選範例 + schema 驗證 script

Sample candidates/rivals JSON + 3 variant 產出 + verify script，
通過後即可作為 UI / evolver / predictor 的 test fixture。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Evolver 偵測 party_primary + intra 分支

**Files:**
- Modify: `ap/services/evolution/app/evolver.py`

- [ ] **Step 1: 定位 scoring loop**

在 evolver.py 搜尋 scoring loop 主入口（通常是 `_score_candidate_for_agent` 或類似，檔內 search `party_align_bonus` 找到關鍵點）。確認 scoring 函式簽名後，在該函式開頭（讀取 agent/cand 之後、計算 base score 之前）加：

```bash
grep -n "party_align_bonus\|def _score_candidate\|def _compute_candidate_score" ap/services/evolution/app/evolver.py | head -20
```

- [ ] **Step 2: 加入 primary_method 偵測 helper**

在 evolver.py 靠近檔案頂部（其它 module-level helper 附近）加：

```python
def _is_primary_election(job: dict) -> bool:
    """True if this job runs a party_primary template."""
    etype = (job.get("election") or {}).get("type", "")
    return etype == "party_primary"


def _get_primary_method(job: dict) -> str | None:
    """Return 'intra' | 'head2head' | 'mixed' or None."""
    return (job.get("election") or {}).get("primary_method")


def _get_primary_party(job: dict) -> str | None:
    """Return 'KMT' | 'DPP' | 'TPP' or None."""
    return (job.get("election") or {}).get("primary_party")
```

- [ ] **Step 3: Scoring loop 分支 — intra method**

在 scoring loop 內（具體 code line 依 grep 結果），當計算 `party_align_bonus` 之前加：

```python
        _primary_method = _get_primary_method(job)
        _is_primary = _is_primary_election(job)

        if _is_primary and _primary_method == "intra":
            # 互比式：同黨內比較，關閉 party_align_bonus（都同黨）
            party_align_bonus = 0
            # 強化 candidate charisma +50%
            charisma_boost_mult = 1.5
            # 強化 local visibility +30%
            local_visibility_mult = 1.3
            # 現任優勢在黨內初選尤其明顯
            if is_incumbent:
                incumbency_bonus = 15
        else:
            charisma_boost_mult = 1.0
            local_visibility_mult = 1.0
```

註：原有 `charisma` / `local_visibility` 相關計算的 call site 要乘上這兩個 mult。若 evolver 現況沒有分離「charisma_boost」這個變數名，實作時用 grep 定位實際變數（如 `attractiveness_score` 或類似），把 `× 1.0` 改成 `× charisma_boost_mult`。

- [ ] **Step 4: 驗證 evolver import 不壞**

```bash
cd ap && python3 -c "
import sys
sys.path.insert(0, 'services/evolution/app')
from evolver import _is_primary_election, _get_primary_method, _get_primary_party
job1 = {'election': {'type': 'party_primary', 'primary_method': 'intra', 'primary_party': 'KMT'}}
assert _is_primary_election(job1) is True
assert _get_primary_method(job1) == 'intra'
assert _get_primary_party(job1) == 'KMT'

job2 = {'election': {'type': 'presidential'}}
assert _is_primary_election(job2) is False
assert _get_primary_method(job2) is None

print('✅ primary detection helpers OK')
"
```

- [ ] **Step 5: Commit**

```bash
git add ap/services/evolution/app/evolver.py
git commit -m "feat(primary): evolver intra-method scoring branch

_is_primary_election / _get_primary_method / _get_primary_party helpers；
intra 分支關閉 party_align_bonus、charisma/visibility +50%/+30%、
現任 bonus 15（初選現任優勢強）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Evolver head2head + mixed 分支

**Files:**
- Modify: `ap/services/evolution/app/evolver.py`

- [ ] **Step 1: head2head 分支（沿用既有 presidential scoring）**

在 Task 10 的分支 block 內加 elif：

```python
        elif _is_primary and _primary_method == "head2head":
            # 對比式：黨內參選人 vs 對手黨，沿用既有跨黨 scoring
            # party_align_bonus 正常計算（rival candidates 屬不同黨）
            # incumbency_bonus 保持預設
            charisma_boost_mult = 1.0
            local_visibility_mult = 1.0
```

- [ ] **Step 2: mixed 分支**

同一 if/elif 鏈：

```python
        elif _is_primary and _primary_method == "mixed":
            # 混合：同時記兩組 score（intra + head2head）供 predictor 合成
            # Scoring loop 跑兩次：intra 模式 score 存 "_intra_score"、
            # head2head 模式 score 存 "_h2h_score"；最終保留 head2head 作為主 score
            # (intra 在 post-process 另外算)
            charisma_boost_mult = 1.0
            local_visibility_mult = 1.0
            # 注意：mixed 的完整 dual-scoring 在 post-process 做；
            # 這裡的主迴圈先跑 head2head（rival candidates 已在 candidates list）
```

- [ ] **Step 3: Post-process：mixed 專屬 intra score 計算**

在 scoring loop 結束、`return result` 之前加：

```python
    if _is_primary and _primary_method == "mixed":
        # 對黨內參選人再跑一次 intra-only scoring（剔除 rivals）
        _rival_ids = {c["id"] for c in (job.get("election") or {}).get("rival_candidates", [])}
        _intra_cands = [c for c in candidates if c["id"] not in _rival_ids]
        intra_scores = _run_intra_scoring(agent, _intra_cands, job)  # extract subroutine
        for cid, s in intra_scores.items():
            if cid in result.get("candidate_scores", {}):
                result["candidate_scores"][cid]["_intra_score"] = s
```

若 `_run_intra_scoring` 目前不存在（evolver 沒把主 loop 抽成 subroutine），這題變成：「先 refactor 主 scoring loop 抽成 `_run_scoring(agent, candidates, job, *, force_intra=False)` helper，再呼叫兩次」。可先跳過、留到 Task 14（predictor 合成）時視需要 refactor。

如果完整 refactor 太大，簡化版本：mixed 分支先只存 head2head score，intra score 在 predictor 階段用 agent state 直接重算。這個取捨要在實作時決定；**建議先走簡化版（mixed 只存 h2h score）**，intra 合成交給 predictor。

- [ ] **Step 4: Commit**

```bash
git add ap/services/evolution/app/evolver.py
git commit -m "feat(primary): evolver head2head + mixed scoring branches

head2head 沿用既有跨黨 scoring（rival cands 屬不同黨）；
mixed 主 loop 跑 head2head score，intra score 由 predictor 合成時
直接從 agent state 重算（避免 evolver 大 refactor）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Predictor `_apply_sampling_frame` helper

**Files:**
- Modify: `ap/services/evolution/app/predictor.py`

- [ ] **Step 1: 加 helper function**

在 predictor.py 檔案適當位置（其它 module-level helper 附近）加：

```python
def _apply_sampling_frame(agents: list, frame_cfg: dict, primary_party: str | None):
    """Filter & weight agents according to a sampling frame.

    Returns (filtered_agents, weights_list).

    frame_cfg can have:
      - "filter": "is_party_member=true" -> keep only agents where
        {primary_party.lower()}_member == True
      - "age_weights": {"20-24": 0.3, ...} -> weight multiplier by age bucket
    """
    pool = agents

    # Party member filter
    filter_spec = frame_cfg.get("filter", "")
    if filter_spec == "is_party_member=true":
        if not primary_party:
            raise ValueError("party_member frame needs primary_party")
        col = f"{primary_party.lower()}_member"
        pool = [a for a in pool if bool(getattr(a, col, None) or
                                         (a.get(col) if isinstance(a, dict) else False))]
        if not pool:
            raise ValueError(
                f"No agents have {col}=True. "
                "Re-run synthesis to derive party member flags."
            )

    # Age weights (default 1.0)
    aw = frame_cfg.get("age_weights") or {}
    weights = []
    for a in pool:
        if isinstance(a, dict):
            age = a.get("age", 45)
        else:
            age = getattr(a, "age", 45)
        bucket = _age_to_bucket(age)
        weights.append(aw.get(bucket, 1.0))

    return pool, weights


def _age_to_bucket(age: int) -> str:
    if age < 25: return "20-24"
    if age < 35: return "25-34"
    if age < 45: return "35-44"
    if age < 55: return "45-54"
    if age < 65: return "55-64"
    return "65+"
```

- [ ] **Step 2: 驗證 helper**

```bash
cd ap && python3 -c "
import sys
sys.path.insert(0, 'services/evolution/app')
from predictor import _apply_sampling_frame, _age_to_bucket

# Fake agents
class FakeAgent:
    def __init__(self, age, kmt, dpp, tpp):
        self.age = age
        self.kmt_member = kmt
        self.dpp_member = dpp
        self.tpp_member = tpp

agents = [FakeAgent(30, False, False, True),
          FakeAgent(65, True, False, False),
          FakeAgent(45, False, True, False),
          FakeAgent(25, False, False, False)]

# Landline frame (favor 55+)
landline = {'age_weights': {'20-24': 0.3, '25-34': 0.3, '35-44': 0.6,
                              '45-54': 1.1, '55-64': 1.7, '65+': 2.2}}
pool, weights = _apply_sampling_frame(agents, landline, 'KMT')
assert len(pool) == 4
# age 65 最重 (2.2)，age 25 最輕 (0.3)
assert weights[1] > weights[3], f'expected 65 > 25, got {weights}'

# Party member filter (KMT)
pm = {'filter': 'is_party_member=true'}
pool, weights = _apply_sampling_frame(agents, pm, 'KMT')
assert len(pool) == 1  # 只有 age 65 的 KMT
assert pool[0].age == 65

print('✅ _apply_sampling_frame OK')
"
```

- [ ] **Step 3: Commit**

```bash
git add ap/services/evolution/app/predictor.py
git commit -m "feat(primary): predictor _apply_sampling_frame helper

支援 landline/mobile/dual age weights + party_member filter；
agent 可為 dict 或 object（duck-typed）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: Predictor tallies + rolling poll

**Files:**
- Modify: `ap/services/evolution/app/predictor.py`

- [ ] **Step 1: 加 tally helpers**

```python
def _tally_intra(agent_scores: dict, intra_cand_ids: list[str]) -> dict:
    """Given per-agent candidate_scores dict, tally preference across intra candidates only.

    agent_scores: {cand_id: score_float, ...} 每 agent 的打分結果
    Returns: {cand_id: preference_pct (0-100)} (pick-the-max counting)
    """
    if not intra_cand_ids:
        return {}
    # 此函式預設 agent_scores 已篩過僅 intra cands；若呼叫者未篩，做防呆
    valid = {c: agent_scores.get(c, 0.0) for c in intra_cand_ids}
    if not valid:
        return {c: 0.0 for c in intra_cand_ids}
    top = max(valid.values())
    if top <= 0:
        return {c: 100.0 / len(intra_cand_ids) for c in intra_cand_ids}  # 都 0 → 均分
    winners = [c for c, v in valid.items() if v == top]
    return {c: (100.0 / len(winners) if c in winners else 0.0) for c in intra_cand_ids}


def _tally_head2head(agent_scores: dict, intra_cand_ids: list[str],
                     rival_cand_ids: list[str]) -> dict:
    """For each intra cand, compute %wins against all rivals (round-robin mean).

    Returns {intra_cand_id: avg_win_pct (0-100)}
    """
    result = {}
    for cid in intra_cand_ids:
        wins = 0
        total = 0
        for rid in rival_cand_ids:
            s_i = agent_scores.get(cid, 0.0)
            s_r = agent_scores.get(rid, 0.0)
            total += 1
            if s_i > s_r: wins += 1
        result[cid] = (wins / total * 100.0) if total else 0.0
    return result
```

- [ ] **Step 2: 加 rolling poll helper**

```python
def _run_rolling_poll(agents: list, method: str, days: int, daily_n: int,
                      frame_cfg: dict, primary_party: str,
                      intra_cand_ids: list[str], rival_cand_ids: list[str],
                      rng) -> dict:
    """Run N-day rolling poll. Returns {cand_id: mean_pct_over_days}.

    Each day: sample daily_n agents with frame weights, tally their preference,
    then average across days.
    """
    import random
    if not isinstance(rng, random.Random):
        rng = random.Random()

    pool, weights = _apply_sampling_frame(agents, frame_cfg, primary_party)
    if not pool:
        raise ValueError(f"sampling frame yielded empty pool for method={method}")

    daily_tallies = []
    for _ in range(days):
        # weighted sample without replacement would be more realistic but expensive;
        # use weighted choice with replacement for simplicity.
        sample_idx = rng.choices(range(len(pool)), weights=weights,
                                  k=min(daily_n, len(pool) * 3))
        sample = [pool[i] for i in sample_idx]

        # Aggregate per-agent scores into tally
        # agent.candidate_scores should exist after evolution; fallback to 0
        agg = {c: 0.0 for c in intra_cand_ids + rival_cand_ids}
        for a in sample:
            scores = (getattr(a, "candidate_scores", None)
                      or (a.get("candidate_scores") if isinstance(a, dict) else {}))
            for cid in agg:
                agg[cid] += scores.get(cid, 0.0)
        if sample:
            agg = {c: v / len(sample) for c, v in agg.items()}

        if method == "intra":
            tally = _tally_intra(agg, intra_cand_ids)
        elif method == "head2head":
            tally = _tally_head2head(agg, intra_cand_ids, rival_cand_ids)
        else:
            raise ValueError(f"rolling poll method must be intra|head2head, got {method}")
        daily_tallies.append(tally)

    # Average across days
    avg = {c: 0.0 for c in intra_cand_ids}
    for t in daily_tallies:
        for c in intra_cand_ids:
            avg[c] += t.get(c, 0.0)
    avg = {c: v / days for c, v in avg.items()}
    return avg
```

- [ ] **Step 3: 驗證 rolling poll**

```bash
cd ap && python3 -c "
import sys, random
sys.path.insert(0, 'services/evolution/app')
from predictor import _run_rolling_poll

# Fake 50 agents, all KMT members, all prefer cand_A
class FA:
    def __init__(self, age, kmt, scores):
        self.age = age
        self.kmt_member = kmt
        self.dpp_member = False
        self.tpp_member = False
        self.candidate_scores = scores

agents = [FA(50, True, {'A': 80, 'B': 40, 'R': 30}) for _ in range(50)]
dual = {'age_weights': {'45-54': 1.0}}

result = _run_rolling_poll(
    agents, 'intra', days=3, daily_n=30, frame_cfg=dual,
    primary_party='KMT',
    intra_cand_ids=['A', 'B'], rival_cand_ids=['R'],
    rng=random.Random(42))
assert result['A'] == 100.0, f'expected A=100%, got {result}'
assert result['B'] == 0.0

# head2head: A (80) beats R (30) 100%
result = _run_rolling_poll(
    agents, 'head2head', days=3, daily_n=30, frame_cfg=dual,
    primary_party='KMT',
    intra_cand_ids=['A', 'B'], rival_cand_ids=['R'],
    rng=random.Random(42))
assert result['A'] == 100.0
assert result['B'] == 100.0  # B (40) > R (30)
print('✅ rolling poll tallies OK')
"
```

- [ ] **Step 4: Commit**

```bash
git add ap/services/evolution/app/predictor.py
git commit -m "feat(primary): _tally_intra / _tally_head2head / _run_rolling_poll

Intra = pick-the-max across intra candidates; head2head = per-intra-cand
round-robin vs rivals; rolling = N-day average with per-day weighted sample.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 14: Predictor mixed 合成 + 整合入 run_prediction

**Files:**
- Modify: `ap/services/evolution/app/predictor.py`

- [ ] **Step 1: 加 `_compose_mixed_result` helper**

```python
def _compose_mixed_result(intra: dict, h2h: dict, member: dict,
                          formula: dict) -> dict:
    """Combine intra + h2h + party_member polls by weights.

    formula: {"intra_poll_weight": 0.5, "head2head_poll_weight": 0.3,
              "party_member_weight": 0.2}
    All inputs: {cand_id: pct}
    """
    w_i = formula.get("intra_poll_weight", 0.0)
    w_h = formula.get("head2head_poll_weight", 0.0)
    w_m = formula.get("party_member_weight", 0.0)
    total = w_i + w_h + w_m
    if total > 0:
        w_i, w_h, w_m = w_i / total, w_h / total, w_m / total

    all_cands = set(intra) | set(h2h) | set(member)
    return {c: intra.get(c, 0.0) * w_i +
               h2h.get(c, 0.0) * w_h +
               member.get(c, 0.0) * w_m
            for c in all_cands}
```

- [ ] **Step 2: 整合入 run_prediction 主流程**

在 predictor.py 主 `run_prediction` / `_compute_prediction` 函式內（grep `def run_prediction` 或 `def _compute_prediction` 找），在既有 scoring logic 結束、回傳結果之前，加：

```python
    # Primary election branch
    election = job.get("election", {}) or {}
    if election.get("type") == "party_primary":
        primary_method = election.get("primary_method")
        primary_party = election.get("primary_party")
        sampling = election.get("primary_sampling") or {}
        frame_name = sampling.get("default_sampling_frame", "dual")
        frame_cfg = sampling.get("frames", {}).get(frame_name, {})
        poll_days = sampling.get("default_poll_days", 3)
        daily_n = sampling.get("default_daily_n", 600)

        rival_ids = [c["id"] for c in election.get("rival_candidates", [])]
        intra_ids = [c["id"] for c in election.get("candidates", [])
                     if c["id"] not in rival_ids]

        import random
        rng = random.Random(hash(job.get("job_id", "")) & 0xFFFFFFFF)

        if primary_method == "intra":
            result = _run_rolling_poll(
                agents, "intra", poll_days, daily_n, frame_cfg,
                primary_party, intra_ids, rival_ids, rng)
        elif primary_method == "head2head":
            result = _run_rolling_poll(
                agents, "head2head", poll_days, daily_n, frame_cfg,
                primary_party, intra_ids, rival_ids, rng)
        elif primary_method == "mixed":
            intra_res = _run_rolling_poll(
                agents, "intra", poll_days, daily_n, frame_cfg,
                primary_party, intra_ids, rival_ids, rng)
            h2h_res = _run_rolling_poll(
                agents, "head2head", poll_days, daily_n, frame_cfg,
                primary_party, intra_ids, rival_ids, rng)
            member_frame = sampling.get("frames", {}).get("party_member", {})
            try:
                member_res = _run_rolling_poll(
                    agents, "intra", poll_days, daily_n, member_frame,
                    primary_party, intra_ids, rival_ids, rng)
            except ValueError as ex:
                # No party members → 0% weight for party_member component
                print(f"[primary/mixed] party_member frame empty: {ex}; "
                      "using intra_res as fallback for member component")
                member_res = intra_res
            formula = election.get("primary_formula", {})
            result = _compose_mixed_result(intra_res, h2h_res, member_res, formula)
        else:
            raise ValueError(f"unknown primary_method: {primary_method}")

        # Return primary result in expected shape (mimic presidential/mayoral output)
        return {"primary_result": result,
                "primary_method": primary_method,
                "primary_party": primary_party,
                "sampling_frame": frame_name,
                "poll_days": poll_days}
```

- [ ] **Step 3: Commit**

```bash
git add ap/services/evolution/app/predictor.py
git commit -m "feat(primary): predictor mixed 合成 + run_prediction 整合

_compose_mixed_result 依 formula 加權合成 3 個 sub-poll；
run_prediction 偵測 election.type==party_primary 時走新分支，
intra/head2head/mixed 各自 sampling + tally。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 15: API routes surface 新欄位

**Files:**
- Modify: `ap/services/api/app/routes/templates.py`

- [ ] **Step 1: 定位 election block 透出**

```bash
grep -n "default_age_range\|election\[" ap/services/api/app/routes/templates.py | head -10
```

- [ ] **Step 2: 擴充 election dict**

在 templates.py 的 `_serialize_template` / 類似 function 內，election 欄位透出 block 加：

```python
        "election": {
            # ...既有欄位保留...
            "type": e.get("type"),
            "scope": e.get("scope"),
            "cycle": e.get("cycle"),
            "candidates": e.get("candidates", []),
            "party_palette": e.get("party_palette", {}),
            "party_detection": e.get("party_detection", {}),
            "default_macro_context": e.get("default_macro_context", {}),
            "default_search_keywords": e.get("default_search_keywords", {}),
            "default_calibration_params": e.get("default_calibration_params", {}),
            "default_age_range": e.get("default_age_range"),
            "use_electoral_college": e.get("use_electoral_college", False),
            # ─── Primary-specific fields ───
            "primary_party": e.get("primary_party"),
            "primary_method": e.get("primary_method"),
            "primary_position": e.get("primary_position"),
            "constituency_name": e.get("constituency_name"),
            "constituency_townships": e.get("constituency_townships", []),
            "rival_candidates": e.get("rival_candidates", []),
            "primary_formula": e.get("primary_formula", {}),
            "primary_sampling": e.get("primary_sampling", {}),
            "party_member_stats": e.get("party_member_stats", {}),
        }
```

- [ ] **Step 3: Commit**

```bash
git add ap/services/api/app/routes/templates.py
git commit -m "feat(primary): API surface primary election fields to web

9 新欄位透出：primary_party/method/position, constituency_name/townships,
rival_candidates, primary_formula/sampling, party_member_stats.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 16: Web TypeScript types 擴充

**Files:**
- Modify: `ap/services/web/src/lib/api.ts`

- [ ] **Step 1: 定位 TemplateMeta.election**

```bash
grep -n "election\?:\|election:" ap/services/web/src/lib/api.ts | head -10
```

- [ ] **Step 2: 擴充 TemplateMeta interface**

找到 `TemplateMeta` type 的 `election` 欄位，加：

```typescript
export type PrimaryMethod = "intra" | "head2head" | "mixed";
export type SamplingFrame = "landline" | "mobile" | "dual" | "party_member";

export interface RivalCandidate {
  id: string;
  name: string;
  party: string;
  party_label?: string;
  description?: string;
  color?: string;
}

export interface PrimaryFormula {
  intra_poll_weight: number;
  head2head_poll_weight: number;
  party_member_weight: number;
}

export interface PrimarySamplingFrameCfg {
  age_weights?: Record<string, number>;
  filter?: string;
  description?: string;
}

export interface PrimarySamplingCfg {
  default_poll_days: number;
  default_sampling_frame: SamplingFrame;
  default_daily_n: number;
  frames: Partial<Record<SamplingFrame, PrimarySamplingFrameCfg>>;
}

// In TemplateMeta.election:
  primary_party?: "KMT" | "DPP" | "TPP" | null;
  primary_method?: PrimaryMethod | null;
  primary_position?: string | null;
  constituency_name?: string | null;
  constituency_townships?: string[];
  rival_candidates?: RivalCandidate[];
  primary_formula?: PrimaryFormula | Record<string, never>;
  primary_sampling?: PrimarySamplingCfg | Record<string, never>;
  party_member_stats?: {
    as_of?: string;
    source_file?: string;
    note?: string;
  } | Record<string, never>;
```

- [ ] **Step 3: 驗證 TS 編譯**

```bash
cd ap/services/web && npx tsc --noEmit 2>&1 | head -30
```

Expected: 無新錯誤（舊既有 error 可接受）。

- [ ] **Step 4: Commit**

```bash
git add ap/services/web/src/lib/api.ts
git commit -m "feat(primary): TS types for primary election fields

PrimaryMethod / SamplingFrame / RivalCandidate / PrimaryFormula /
PrimarySamplingCfg interfaces + TemplateMeta.election 擴充。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 17: PredictionPanel 初選模式 UI section

**Files:**
- Modify: `ap/services/web/src/components/panels/PredictionPanel.tsx`

- [ ] **Step 1: 加 state + helpers**

在 PredictionPanel component 內，既有 state hooks 附近加：

```typescript
  const isPrimary = activeTemplate?.election?.type === "party_primary";
  const primaryMethodDefault = activeTemplate?.election?.primary_method ?? "intra";

  const [primaryMethod, setPrimaryMethod] =
    useState<PrimaryMethod>(primaryMethodDefault);
  const [samplingFrame, setSamplingFrame] = useState<SamplingFrame>(
    activeTemplate?.election?.primary_sampling?.default_sampling_frame ?? "dual"
  );
  const [pollDays, setPollDays] = useState<number>(
    activeTemplate?.election?.primary_sampling?.default_poll_days ?? 3
  );
  const [formulaWeights, setFormulaWeights] = useState<PrimaryFormula>(
    (activeTemplate?.election?.primary_formula as PrimaryFormula) ?? {
      intra_poll_weight: 0.5, head2head_poll_weight: 0.3, party_member_weight: 0.2,
    }
  );
  const [rivalCandidates, setRivalCandidates] = useState<RivalCandidate[]>(
    activeTemplate?.election?.rival_candidates ?? []
  );

  // Restore from saved meta.json (with type guards per Stage 8.15)
  useEffect(() => {
    if (!saved) return;
    if (typeof saved.primaryMethod === "string")
      setPrimaryMethod(saved.primaryMethod as PrimaryMethod);
    if (typeof saved.primarySamplingFrame === "string")
      setSamplingFrame(saved.primarySamplingFrame as SamplingFrame);
    if (typeof saved.primaryPollDays === "number")
      setPollDays(saved.primaryPollDays);
    if (saved.primaryFormulaWeights && typeof saved.primaryFormulaWeights === "object")
      setFormulaWeights(saved.primaryFormulaWeights as PrimaryFormula);
    if (Array.isArray(saved.primaryRivalCandidates))
      setRivalCandidates(saved.primaryRivalCandidates);
  }, [saved, activeTemplate?.election?.type]);
```

- [ ] **Step 2: 加 UI section**

在既有 section 之間（預測參數區塊上方或下方合適位置）插入：

```tsx
      {isPrimary && (
        <section className="bg-amber-50 dark:bg-amber-900/20 p-4 rounded-md my-4">
          <h3 className="font-semibold mb-3">🗳️ 初選模式設定</h3>

          <div className="mb-3">
            <label className="block text-sm font-medium mb-1">初選方法</label>
            <div className="flex gap-2">
              {(["intra", "head2head", "mixed"] as PrimaryMethod[]).map(m => (
                <button key={m}
                  onClick={() => setPrimaryMethod(m)}
                  className={`px-3 py-1 rounded ${primaryMethod === m
                    ? "bg-amber-600 text-white"
                    : "bg-white dark:bg-gray-700 border"}`}>
                  {m === "intra" ? "互比式（黨內同室）"
                    : m === "head2head" ? "對比式（vs 對手黨）"
                    : "混合式"}
                </button>
              ))}
            </div>
          </div>

          <div className="mb-3 grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium mb-1">採樣方式</label>
              <select value={samplingFrame}
                onChange={e => setSamplingFrame(e.target.value as SamplingFrame)}
                className="w-full border rounded p-1">
                <option value="landline">市話（偏高齡）</option>
                <option value="mobile">手機（偏年輕）</option>
                <option value="dual">雙軌 50/50</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">連續天數</label>
              <input type="number" min={1} max={7}
                value={pollDays}
                onChange={e => setPollDays(Math.max(1, Math.min(7, Number(e.target.value) || 1)))}
                className="w-full border rounded p-1" />
            </div>
          </div>

          {primaryMethod === "mixed" && (
            <div className="mb-3 bg-white dark:bg-gray-800 p-3 rounded border">
              <div className="text-sm font-medium mb-2">混合公式（三者自動 normalize 到 100%）</div>
              {(["intra_poll_weight", "head2head_poll_weight", "party_member_weight"] as const).map(k => (
                <div key={k} className="flex items-center gap-2 mb-1">
                  <span className="text-xs w-32">
                    {k === "intra_poll_weight" ? "互比式民調 %"
                      : k === "head2head_poll_weight" ? "對比式民調 %"
                      : "黨員投票 %"}
                  </span>
                  <input type="range" min={0} max={100} step={5}
                    value={formulaWeights[k] * 100}
                    onChange={e => setFormulaWeights(prev => ({
                      ...prev, [k]: Number(e.target.value) / 100
                    }))}
                    className="flex-1" />
                  <span className="text-xs w-10">{Math.round(formulaWeights[k] * 100)}%</span>
                </div>
              ))}
            </div>
          )}

          {(primaryMethod === "head2head" || primaryMethod === "mixed") && (
            <RivalCandidatesEditor
              value={rivalCandidates}
              onChange={setRivalCandidates} />
          )}
        </section>
      )}
```

- [ ] **Step 3: 加 RivalCandidatesEditor 小元件**

在 PredictionPanel.tsx 檔尾（或靠近其它 local components）加：

```tsx
function RivalCandidatesEditor({
  value, onChange,
}: {
  value: RivalCandidate[];
  onChange: (v: RivalCandidate[]) => void;
}) {
  const add = () => onChange([...value, { id: `rival_${value.length + 1}`,
                                          name: "", party: "DPP", description: "" }]);
  const update = (idx: number, patch: Partial<RivalCandidate>) => {
    const next = value.map((c, i) => i === idx ? { ...c, ...patch } : c);
    onChange(next);
  };
  const remove = (idx: number) => onChange(value.filter((_, i) => i !== idx));

  return (
    <div className="mb-2 bg-white dark:bg-gray-800 p-3 rounded border">
      <div className="text-sm font-medium mb-2">對手黨候選人（對比式/混合式使用）</div>
      {value.map((c, idx) => (
        <div key={idx} className="grid grid-cols-12 gap-1 mb-1">
          <input className="col-span-3 border rounded p-1 text-xs"
            placeholder="姓名" value={c.name}
            onChange={e => update(idx, { name: e.target.value })} />
          <select className="col-span-2 border rounded p-1 text-xs"
            value={c.party}
            onChange={e => update(idx, { party: e.target.value })}>
            <option value="DPP">民進黨</option>
            <option value="KMT">國民黨</option>
            <option value="TPP">民眾黨</option>
            <option value="IND">無黨籍</option>
          </select>
          <input className="col-span-6 border rounded p-1 text-xs"
            placeholder="描述（例：民進黨籍，深耕青年族群…）"
            value={c.description ?? ""}
            onChange={e => update(idx, { description: e.target.value })} />
          <button className="col-span-1 text-red-500 text-xs"
            onClick={() => remove(idx)}>✕</button>
        </div>
      ))}
      <button onClick={add}
        className="text-xs text-amber-700 hover:underline mt-1">
        + 新增對手
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add ap/services/web/src/components/panels/PredictionPanel.tsx
git commit -m "feat(primary): PredictionPanel 初選模式 section

只在 election.type==party_primary 顯示：method 切換 / 採樣方式 /
連續天數 / 混合公式 sliders / rival candidates editor。
State 恢復用型別守門（Stage 8.15 教訓）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 18: Meta.json 持久化 + 送到 API

**Files:**
- Modify: `ap/services/web/src/components/panels/PredictionPanel.tsx`

- [ ] **Step 1: 擴充 meta save payload**

找到 PredictionPanel 內 `saveMeta` / 類似函式（每次變更自動存 meta.json），payload 加：

```typescript
  const metaPayload = {
    // ... 既有欄位 ...
    primaryMethod,
    primarySamplingFrame: samplingFrame,
    primaryPollDays: pollDays,
    primaryFormulaWeights: formulaWeights,
    primaryRivalCandidates: rivalCandidates,
  };
```

- [ ] **Step 2: 擴充 run-prediction API request**

找到 `runPrediction` / `submitPrediction` 函式，在送出的 body 加：

```typescript
  const body = {
    // ... 既有欄位 ...
    primary_method: primaryMethod,
    primary_sampling_frame: samplingFrame,
    primary_poll_days: pollDays,
    primary_formula: formulaWeights,
    primary_rival_candidates: rivalCandidates,
  };
```

這些欄位讓 predictor 可以 override template 預設（Task 14 的 run_prediction 優先讀 request body、無則 fallback 到 election.primary_* 欄位）。

註：Task 14 的 predictor 需配合加讀取 request override 的 merge 邏輯。若 Task 14 未包含（上述 code snippet 只從 election 讀），這裡要在 predictor.py `run_prediction` 入口把 request.json body 的 primary_* 欄位 merge 進 `election` dict：

```python
    # Merge user overrides from request body
    request_overrides = job.get("request_body") or {}
    if request_overrides.get("primary_method"):
        election["primary_method"] = request_overrides["primary_method"]
    if request_overrides.get("primary_sampling_frame"):
        election.setdefault("primary_sampling", {}).setdefault("frames", {})
        election["primary_sampling"]["default_sampling_frame"] = \
            request_overrides["primary_sampling_frame"]
    # ... etc for days/formula/rivals
```

- [ ] **Step 3: Commit**

```bash
git add ap/services/web/src/components/panels/PredictionPanel.tsx \
        ap/services/evolution/app/predictor.py
git commit -m "feat(primary): meta.json 持久化 + API request override 合併

UI 變更即時存 meta.json（5 新欄位，type-guarded），跑 prediction 時
傳給 predictor override template 預設。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 19: Persona generation report writer

**Files:**
- Modify: `ap/services/synthesis/app/builder.py`

- [ ] **Step 1: 加 `_write_generation_report` helper**

在 builder.py 末段（module level function 區）加：

```python
def _write_generation_report(
    workspace_path: Path | None,
    template: dict,
    persons: list[dict],
    party_member_stats: dict | None = None,
) -> None:
    """Write persona_generation_report.md to workspace dir.

    Skip silently if workspace_path is None (legacy callers / tests).
    """
    if not workspace_path:
        return
    report_path = Path(workspace_path) / "persona_generation_report.md"

    n = len(persons)
    if n == 0:
        return

    # Party member stats reference
    stats_section = ""
    if party_member_stats and party_member_stats.get("parties"):
        lines = ["## 黨員統計資料來源",
                 "",
                 "本次 persona 生成依據以下公開資料推導 `kmt_member` / `dpp_member` / `tpp_member`：",
                 "",
                 "| 黨 | 黨員數 | 截止日 | 來源 |",
                 "|---|---|---|---|"]
        for pc, meta in party_member_stats["parties"].items():
            srcs = ", ".join(f"[{i+1}]({s['url']})"
                              for i, s in enumerate(meta.get("sources", [])))
            lines.append(f"| {pc} | {meta['count']:,} | {meta['as_of_date']} | {srcs} |")
        lines.append("")
        lines.append(f"成人人口（20+）基準：{party_member_stats.get('adult_pop_20plus', 'N/A'):,}")
        stats_section = "\n".join(lines)

    # Actual distribution
    kmt_n = sum(1 for p in persons if p.get("kmt_member"))
    dpp_n = sum(1 for p in persons if p.get("dpp_member"))
    tpp_n = sum(1 for p in persons if p.get("tpp_member"))
    expected_kmt = int(n * 331410 / 19_500_000)
    expected_dpp = int(n * 240000 / 19_500_000)
    expected_tpp = int(n * 32546 / 19_500_000)

    def _dev(actual, expected):
        if expected == 0:
            return "n/a (expected 0)"
        d = (actual - expected) / expected * 100
        return f"{d:+.1f}%"

    dist_section = f"""## 產出黨員分佈

| 欄位 | True | 預期 | 偏差 |
|---|---|---|---|
| kmt_member | {kmt_n} ({kmt_n / n * 100:.2f}%) | {expected_kmt} | {_dev(kmt_n, expected_kmt)} |
| dpp_member | {dpp_n} ({dpp_n / n * 100:.2f}%) | {expected_dpp} | {_dev(dpp_n, expected_dpp)} |
| tpp_member | {tpp_n} ({tpp_n / n * 100:.2f}%) | {expected_tpp} | {_dev(tpp_n, expected_tpp)} |

（若偏差 > ±30% 表示乘數配置或樣本數有異常，需檢視）
"""

    from datetime import datetime
    report = f"""# Persona Generation Report

**Workspace**: {workspace_path.name}
**Generated**: {datetime.utcnow().isoformat()}Z
**Template**: {template.get('name_zh') or template.get('name')}
**Target count**: {n}

{stats_section}

## 推導公式

基準率：`KMT 1.70% / DPP 1.23% / TPP 0.17%`
乘數：`party_lean × age × ethnicity × county`
實作：`ap/services/synthesis/app/builder.py:_derive_party_member`

{dist_section}

## 已知限制

- DPP 黨員數引用 2023 年公開資料（官方 2024-25 未更新），精度受限
- 鄉鎮級黨員濃度未反映（只有縣市級 override）
- 跨黨員登記（同時為多黨黨員者）各自獨立抽樣，可能略高於實際
"""
    report_path.write_text(report, encoding="utf-8")
    print(f"[persona-report] wrote {report_path}")
```

- [ ] **Step 2: Hook 到 build_personas 出口**

grep `def build_personas` 找到主函式，最末端（return 前）加：

```python
    # Write generation report (best-effort; failures don't block synthesis)
    try:
        stats_path = (Path(__file__).resolve().parents[3]
                      / "shared" / "tw_data" / "party_members_2026.json")
        if stats_path.exists():
            stats = json.loads(stats_path.read_text(encoding="utf-8"))
        else:
            stats = None
        _write_generation_report(workspace_path, template, persons, stats)
    except Exception as ex:  # noqa: BLE001
        print(f"[persona-report] skipped: {ex}")
```

註：`workspace_path` 參數需由 caller 傳入；如現況 `build_personas` 不收這個參數，在 signature 加 `workspace_path: Path | None = None` 並在 API layer / main.py 呼叫時帶入。

- [ ] **Step 3: Commit**

```bash
git add ap/services/synthesis/app/builder.py
git commit -m "feat(primary): persona_generation_report.md writer

記錄黨員統計來源、推導公式、產出分佈與偏差。Best-effort 寫入，
失敗不阻擋 synthesis 完成。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 20: End-to-End integration smoke test

**Files:**
- Create: `scripts/verify_primary_template.py`

- [ ] **Step 1: 建立 e2e verify**

Create `scripts/verify_primary_template.py`：

```python
"""End-to-end smoke test for party primary template system.

Steps:
1. Generate 3 primary templates (松信 KMT councilor).
2. Verify schema via verify_primary_template_schema.py.
3. Build 500 agents via synthesis (in-process), check kmt_member rate 2-5%.
4. (Optional) Fire predictor for each method variant, confirm results differ.

Run: python3 scripts/verify_primary_template.py
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TPL = ROOT / "data" / "templates"
sys.path.insert(0, str(ROOT / "ap" / "services" / "synthesis" / "app"))


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
    # Load intra template, run synthesis logic in-process
    from builder import _enforce_logical_consistency
    import random

    tmpl = json.loads((TPL / "primary_2026_kmt_songshan_xinyi_councilor_intra.json")
                      .read_text(encoding="utf-8"))

    rng = random.Random(20260418)
    rows = []
    # Sample 500 agents by template weights (simplified: just uniform over buckets)
    leans = [(c["value"], c["weight"])
             for c in tmpl["dimensions"]["party_lean"]["categories"]]
    ages = [(b["range"], b["weight"])
            for b in tmpl["dimensions"]["age"]["bins"] if b["weight"] > 0]
    eths = [(c["value"], c["weight"])
            for c in tmpl["dimensions"]["ethnicity"]["categories"]]

    def _pick(pairs):
        r = rng.random()
        acc = 0.0
        for v, w in pairs:
            acc += w
            if r <= acc:
                return v
        return pairs[-1][0]

    for i in range(500):
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
    # 松信區深藍偏多 → 預期 KMT 率 3-8%
    print(f"   KMT member rate: {rate:.2f}% (n={kmt_n}/500)")
    assert 1.0 <= rate <= 12.0, f"KMT rate {rate:.2f}% outside expected range"

    # All rows have flags set (not None)
    unset = sum(1 for r in rows if r.get("kmt_member") is None)
    assert unset == 0, f"{unset} rows have kmt_member=None"


def main() -> int:
    _generate()
    _verify_schema()
    _check_synthesis_party_members()
    print()
    print("✅ Party primary template system e2e smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run e2e**

```bash
python3 scripts/verify_primary_template.py
```

Expected output:
```
=== Step 1: Generate 3 primary templates ===
  → data/templates/primary_2026_kmt_songshan_xinyi_councilor_intra.json
  → ...
=== Step 2: Schema verification ===
  ✅ ...intra.json
  ✅ ...head2head.json
  ✅ ...mixed.json
✅ All 3 primary templates schema-valid
=== Step 3: Synthesis + party member distribution ===
   KMT member rate: 4.20% (n=21/500)
✅ Party primary template system e2e smoke test passed
```

- [ ] **Step 3: Commit**

```bash
git add scripts/verify_primary_template.py
git commit -m "feat(primary): end-to-end smoke test

Generates 3 templates → schema verify → 500-agent synthesis →
assert KMT member rate 1-12%（松信區偏深藍，預期中段 3-5%）.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 21: Docker rebuild + live smoke

**Files:** 無（container operations only）

- [ ] **Step 1: 重建 schema-sensitive services**

```bash
cd ap && docker compose up --build -d synthesis evolution api web
```

Expected: 4 containers 成 healthy。

- [ ] **Step 2: Curl API 確認 primary template 出現在列表**

```bash
curl -s http://localhost:8000/api/templates | python3 -c "
import sys, json
d = json.load(sys.stdin)
primary = [t for t in d if t.get('election', {}).get('type') == 'party_primary']
print(f'Found {len(primary)} primary templates:')
for t in primary:
    print(f\"  - {t['name_zh']} ({t['election']['primary_method']})\")
assert len(primary) == 3, 'expected 3 variants'
"
```

- [ ] **Step 3: 建立測試 workspace → 跑 synthesis → 驗證 agents 有黨員欄位**

使用 Web UI（http://localhost:3100）：
1. 建立新 workspace，選 `primary_2026_kmt_songshan_xinyi_councilor_intra.json` template
2. 跑 synthesis（target_count=100）
3. 開 Agent Explorer panel
4. 人工目視：隨機 10 個 agent 應有 `kmt_member=true/false` 欄位（不應全為 null）

或用 API：
```bash
WORKSPACE_ID=<剛建好的 id>
curl -s http://localhost:8000/api/workspaces/$WORKSPACE_ID/synthesis_result | \
  python3 -c "
import json, sys
d = json.load(sys.stdin)
persons = d.get('persons') or d.get('data', {}).get('persons', [])
has_member = sum(1 for p in persons if p.get('kmt_member') is not None)
print(f'{has_member}/{len(persons)} persons have kmt_member set')
assert has_member == len(persons), 'some persons missing kmt_member flag'
"
```

- [ ] **Step 4: 開 PredictionPanel，確認初選 UI section 顯示**

在 workspace prediction 頁，確認：
- `🗳️ 初選模式設定` section 可見
- 切換 method 三選一 OK
- sampling frame 下拉三選一 OK
- 連續天數 input 可變更
- mixed 模式下 sliders 顯示

- [ ] **Step 5: Commit（此 task 無 code change）**

無 commit 需要。記錄結果於 session 結束的 manual test log。

---

## Self-Review

### Spec Coverage

| Spec section | Tasks | Status |
|---|---|---|
| §1 交付物 | 1-20 | ✅ |
| §2 Template schema 擴充 | 6, 7, 8 | ✅ |
| §3 Person schema + synthesis | 2, 3, 4 | ✅ |
| §4 build_templates.py CLI | 5, 6, 7, 8, 9 | ✅ |
| §5 Evolution / Predictor 分支 | 10, 11, 12, 13, 14 | ✅ |
| §6 Persona generation report | 19 | ✅ |
| §7 PredictionPanel UI | 15, 16, 17, 18 | ✅ |
| §8 黨員資料 fetch | 1 | ✅（手動 snapshot；refresh script 未做，列為 future） |
| §9 驗證計畫 | 20, 21 | ✅ |

### Placeholder scan
- 全部 steps 都有具體 code 或 command
- 無 TBD / TODO / "implement later"
- Task 11 Step 3 標註「簡化版：mixed evolver 只跑 h2h score，intra score 由 predictor 合成時重算」—— 這是設計決策紀錄，不是 placeholder
- Task 19 Step 2 有條件性：「如果 workspace_path 不在 signature 就加」—— implementation 時根據實際 code 決定

### Type consistency
- `PrimaryMethod` = `"intra" | "head2head" | "mixed"` 在 Task 16 定義，後續 Task 17-18 沿用
- `SamplingFrame` 同上
- `_apply_sampling_frame` 簽名在 Task 12 定義，Task 13 呼叫一致
- `_derive_party_member` 簽名 `(row: dict, rng)` 在 Task 3 + Task 4 一致
- 黨員欄位名 `kmt_member` / `dpp_member` / `tpp_member` 全 plan 一致

### Scope check
20 tasks + 1 docker verify，合適單一 implementation cycle；每 task 2-4 commits，總 commit 數 ~22；每 milestone 獨立可回退（§10 風險方案）。

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-18-party-primary-template.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
