# 黨內初選 Template 系統設計

**日期**：2026-04-18
**狀態**：Design
**涉及服務**：`synthesis` / `evolution` / `api` / `web`，+ top-level `scripts/build_templates.py`
**相關先前工作**：Stage 2（template builder）、Stage 6.6（cross_strait 推導）、Stage 6.7（原住民重採樣）、Stage 8（英文 keyword 清除）

## 背景與問題

目前系統的 `election.type` 只支援 `presidential` / `mayoral` / `poll` 三種。台灣選舉實務中，黨內初選（primary）是頻繁、在地、多變的選舉單元：

- 每屆議員 / 立委 / 縣市長選舉，三大黨都要跑各自選區初選
- 初選的計票方法多元：互比式（黨內同室）、對比式（vs 對手黨）、黨員投票、三者混合
- 採樣方式（市話 / 手機 / 雙軌）、民調天數（單日 / 連 3 天 / 連 5 天）因黨而異
- 選區不一定等於單一行政區 —— 例如台北市松信區議員選區 = 松山區 + 信義區

需要一個可 parametric 產生、承載上述變數的 template 類型。

## 使用者故事

> 使用者想模擬「2026 國民黨台北市松山信義區議員初選」的結果：
> - 參選人 3 位：甲乙丙（都 KMT）
> - 採用方法：70% 對比式民調 + 30% 黨員投票
> - 連續 3 天市話民調，各天 600 樣本
> - 對手黨候選人：民進黨丁、民眾黨戊

系統應：

1. `build_templates.py --primary ...` 一鍵生成 3 個 template（intra/head2head/mixed）
2. Synthesis 階段把受測 agent 的 `kmt_member` / `dpp_member` / `tpp_member` 推導出來
3. Evolution 按初選 scoring profile 演化
4. Prediction 時做 rolling 3-day 採樣、mixed 公式合成，輸出各候選人支持率
5. Persona 生成後產出 report，記錄所用黨員統計資料的來源

## Scope

本 spec 涵蓋九節，全部在一個 implementation cycle 交付。

---

## 1. 交付物總覽

| 項目 | 檔案 | 新增或改動 |
|---|---|---|
| Template generator CLI | `scripts/build_templates.py` | `--primary` 子命令 |
| Person schema 衍生欄位 | `ap/shared/schemas/person.py` | +3 optional bool |
| Synthesis 推導 | `ap/services/synthesis/app/builder.py` `_enforce_logical_consistency` | 新增 `_derive_party_member()` helper |
| Evolver scoring 分支 | `ap/services/evolution/app/evolver.py` | `primary_method` 判讀 |
| Predictor sampling | `ap/services/evolution/app/predictor.py` | `_apply_sampling_frame()` + `_run_rolling_poll()` |
| API schema surface | `ap/services/api/app/routes/templates.py` | 把 primary 欄位 surface 給 web |
| Web type defs | `ap/services/web/src/lib/api.ts` | TemplateMeta.election 擴充 |
| Panel UI | `ap/services/web/src/components/panels/PredictionPanel.tsx` | 初選模式區塊 |
| Persona gen report | `ap/services/synthesis/app/builder.py`（末段） | 輸出 markdown 到 workspace |
| 黨員統計資料 | （新增）`ap/shared/tw_data/party_members_2026.json` | 機器可讀的來源 snapshot |
| 驗證 | `scripts/verify_primary_template.py`（新建） | 跑完整 pipeline smoke test |

---

## 2. Template Schema 擴充

新的 `election.type = "party_primary"`，`election` block 新增 7 個欄位。其餘舊欄位沿用（`candidates`、`party_palette`、`default_macro_context` 等）。

```jsonc
{
  // ... 原 template 頂層欄位（name / region / dimensions / ...）不變 ...

  "election": {
    "type": "party_primary",           // 新 type
    "scope": "constituency",           // 新：標示「自訂選區」（對比 "national"/"county"）
    "cycle": 2026,

    // ===== 新增欄位 =====
    "primary_party": "KMT",            // DPP | KMT | TPP（誰辦初選）
    "primary_method": "intra",         // intra | head2head | mixed
    "primary_position": "councilor",   // councilor | legislator | mayor | magistrate | president
    "constituency_name": "松信區",     // 人類可讀選區名
    "constituency_townships": [        // 選區涵蓋的 township admin_key 清單
      "臺北市|松山區",
      "臺北市|信義區"
    ],
    "rival_candidates": [              // 只有 head2head/mixed 才有；使用者輸入
      {"id": "...", "name": "...", "party": "DPP", "party_label": "民進黨", "description": "..."},
      {"id": "...", "name": "...", "party": "TPP", "party_label": "民眾黨", "description": "..."}
    ],
    "primary_formula": {               // 只有 mixed 才有；預設取黨別歷史常用值
      "intra_poll_weight": 0.5,
      "head2head_poll_weight": 0.3,
      "party_member_weight": 0.2
    },
    "primary_sampling": {              // 所有 3 variant 都有
      "default_poll_days": 3,
      "default_sampling_frame": "dual",   // landline | mobile | dual
      "default_daily_n": 600,
      "frames": {
        "landline": {
          "age_weights": {"20-34": 0.3, "35-44": 0.6, "45-54": 1.1, "55-64": 1.7, "65+": 2.2},
          "description": "市話抽樣偏高齡"
        },
        "mobile": {
          "age_weights": {"20-34": 1.8, "35-44": 1.3, "45-54": 1.0, "55-64": 0.5, "65+": 0.2},
          "description": "手機抽樣偏年輕"
        },
        "dual": {
          "age_weights": {"20-34": 1.0, "35-44": 1.0, "45-54": 1.0, "55-64": 1.0, "65+": 1.0},
          "description": "市話手機各 50%"
        },
        "party_member": {
          "filter": {"<party>_member": true},
          "description": "只有黨員可投（黨員結構自有年齡/族群 profile）"
        }
      }
    },
    "party_member_stats": {            // 新增：metadata，記錄推導用的基準數字
      "as_of": "2026-04-18",
      "source_file": "ap/shared/tw_data/party_members_2026.json",
      "note": "這份 template 的 is_party_member 推導所引用的黨員總數與來源 URL；見 source_file"
    },

    // ===== 沿用舊欄位 =====
    "is_generic": false,
    "candidates": [
      {"id": "...", "name": "...", "party": "KMT", "is_incumbent": false, "description": "..."}
    ],
    "party_palette": { ... },
    "party_detection": { ... },
    "party_base_scores": {"KMT": 50},
    "default_age_range": [20, 85],
    "default_macro_context": { "zh-TW": "松信區議員國民黨黨內初選", "en": "..." },
    "default_search_keywords": { "local": [...], "national": [...] },
    "default_calibration_params": { ... },      // 見 §5 primary-specific profile
    "default_kol": { ... },
    "default_poll_groups": [...],
    "default_sampling_modality": "mixed_73",
    "default_evolution_window": ["2026-10-15", "2026-10-17"],
    "use_electoral_college": false
  }
}
```

### Template 命名慣例

```
data/templates/primary_<cycle>_<party>_<area_slug>_<position>_<method>.json
```

範例（松信 KMT 議員初選）：

```
primary_2026_kmt_songshan_xinyi_councilor_intra.json
primary_2026_kmt_songshan_xinyi_councilor_head2head.json
primary_2026_kmt_songshan_xinyi_councilor_mixed.json
```

`area_slug` 採 Pinyin（與既有 `presidential_county_kaohsiung.json` 一致），跨區聯合用下底線連接 `songshan_xinyi`。

---

## 3. Person schema + Synthesis 推導

### 3.1 Schema

`ap/shared/schemas/person.py`，`Person` class 新增 3 個 optional bool：

```python
kmt_member: Optional[bool] = None   # None = 未推導（舊 persona 向後相容）；True/False = 已推導
dpp_member: Optional[bool] = None
tpp_member: Optional[bool] = None
```

設計理由：台灣選民可跨黨登記（KMT + TPP 都入黨者雖少但存在），用三個 bool 比單一 enum 精確；None 預設讓舊 `synthesis_result.json` 無痛升級。

### 3.2 黨員統計資料（基準率）

新增 `ap/shared/tw_data/party_members_2026.json`：

```json
{
  "as_of": "2026-04-18",
  "adult_pop_20plus": 19500000,
  "parties": {
    "KMT": {
      "count": 331410,
      "voting_eligible": 331410,
      "as_of_date": "2025-09-10",
      "label": "繳費黨員（2025 主席黨代表投票人數）",
      "sources": [
        {"url": "https://www.kmt.org.tw/2025/09/blog-post_25.html", "fetched": "2026-04-18"},
        {"url": "https://zh.wikipedia.org/wiki/%E4%B8%AD%E5%9C%8B%E5%9C%8B%E6%B0%91%E9%BB%A8", "fetched": "2026-04-18", "note": "維基 2025 年資訊框 331,145，與 KMT 官網相符（± rounding）"}
      ]
    },
    "DPP": {
      "count": 240000,
      "voting_eligible": 240000,
      "as_of_date": "2023-01-01",
      "label": "具完整黨權黨員（2023 年維基百科引用，2024-25 官方未公開更新）",
      "sources": [
        {"url": "https://zh.wikipedia.org/wiki/%E6%B0%91%E4%B8%BB%E9%80%B2%E6%AD%A5%E9%BB%A8", "fetched": "2026-04-18"}
      ],
      "estimate_note": "以 2023 年公布值為基準，假設 ±10% 年波動，當前估計區間 [216k, 264k]"
    },
    "TPP": {
      "count": 32546,
      "voting_eligible": 32546,
      "as_of_date": "2025-08-10",
      "label": "有效黨員（6 週年黨慶黃國昌公布）",
      "sources": [
        {"url": "https://www.cna.com.tw/news/aipl/202508100030.aspx", "fetched": "2026-04-18"}
      ]
    }
  }
}
```

### 3.3 推導公式

`ap/services/synthesis/app/builder.py:_enforce_logical_consistency` 新增段落：

```python
# 基準機率 = 黨員總數 / 成人人口
_base_rates = {"KMT": 331410 / 19_500_000,    # ~1.70%
               "DPP": 240000 / 19_500_000,    # ~1.23%
               "TPP":  32546 / 19_500_000}    # ~0.17%

_lean_boost = {
    # (KMT_×, DPP_×, TPP_×)
    # 校準於 2025 實際黨員數集中度；初版 6.0× 會過推，實證降至 2.5×
    "深藍":  (2.5, 0.05, 0.8),
    "偏藍":  (1.8, 0.20, 1.2),
    "中間":  (0.5, 0.5,  1.2),
    "偏綠":  (0.15, 1.8, 0.7),
    "深綠":  (0.08, 2.5, 0.3),
}

_age_boost = {  # KMT 黨員偏 55+；DPP 偏 45-64；TPP 偏 25-44
    "20-24": (0.3, 0.6, 2.0),
    "25-34": (0.6, 0.9, 2.2),
    "35-44": (0.8, 1.2, 1.8),
    "45-54": (1.2, 1.5, 1.0),
    "55-64": (1.8, 1.4, 0.5),
    "65+":   (2.2, 0.9, 0.2),
}

_ethnicity_boost = {  # KMT 外省+軍公教強；DPP 閩南客家；TPP 中性偏都會
    "閩南":   (0.9, 1.2, 1.0),
    "客家":   (1.1, 1.1, 0.9),
    "外省":   (3.5, 0.3, 1.0),
    "原住民": (1.8, 0.8, 0.5),
    "新住民": (1.0, 0.8, 0.7),
    "其他":   (1.0, 1.0, 1.0),
}

# 縣市黨員濃度（簡化，僅做大原則 override）
_county_boost = {
    "臺北市":  (1.5, 0.8, 1.4),
    "新北市":  (1.2, 1.0, 1.1),
    "臺中市":  (1.3, 1.0, 1.0),
    "臺南市":  (0.6, 1.8, 0.9),
    "高雄市":  (0.6, 1.7, 0.9),
    "花蓮縣":  (1.6, 0.4, 0.7),
    "臺東縣":  (1.5, 0.5, 0.7),
    "金門縣":  (3.0, 0.2, 0.5),
    "連江縣":  (3.0, 0.2, 0.5),
    # 其它縣市用 (1.0, 1.0, 1.0)
}

def _derive_party_member(row, rng):
    for i, party in enumerate(("KMT", "DPP", "TPP")):
        p = _base_rates[party]
        p *= _lean_boost.get(row.get("party_lean", "中間"), (1,1,1))[i]
        p *= _age_boost.get(row.get("age_bucket", "45-54"), (1,1,1))[i]
        p *= _ethnicity_boost.get(row.get("ethnicity", "其他"), (1,1,1))[i]
        p *= _county_boost.get(row.get("county", ""), (1,1,1))[i]
        p = min(p, 0.6)   # cap: 再怎麼堆權重也不給超過 60%
        row[f"{party.lower()}_member"] = rng.random() < p
```

**數值校準原則**：全人口跑完後，`kmt_member=True` 的 agent 比例應 ≈ 1.7%（= KMT total / 成人數），其它黨同理。設計會在 synthesis 產出時計算並 log，若 ±20% 以外會 warn。

### 3.4 Backward compat

- 舊 `synthesis_result.json` 沒有這三個欄位 → Pydantic 預設 None → evolver / predictor 看到 None 當 False
- 若 workspace 原本 100 agents 都是 None，跑 primary template 時 UI 跳 warning：「這批 persona 未推導黨員資訊，建議重跑 synthesis」

---

## 4. `build_templates.py --primary` CLI

### 4.1 參數設計

```bash
python3 scripts/build_templates.py --primary \
    --party KMT \
    --cycle 2026 \
    --position councilor \
    --constituency-name "松信區" \
    --constituency-slug songshan_xinyi \
    --townships "臺北市|松山區,臺北市|信義區" \
    --candidates candidates_songshan_kmt.json \
    --rivals rivals_songshan.json \
    --formula "intra=0.5,head2head=0.3,member=0.2" \
    --poll-days 3 \
    --sampling-frame dual \
    --output-methods intra,head2head,mixed
```

### 4.2 候選人 JSON 檔案格式

`candidates_songshan_kmt.json`（黨內參選人）：

```json
[
  {"id": "cand_a", "name": "王某某", "party": "KMT",
   "is_incumbent": true,
   "description": "國民黨籍，時任松山信義區議員連任，主打治安與交通；支持者為地方鄰里長、年長選民。"},
  {"id": "cand_b", "name": "李某某", "party": "KMT", ...},
  {"id": "cand_c", "name": "張某某", "party": "KMT", ...}
]
```

`rivals_songshan.json`（對手黨候選人，僅 head2head/mixed 使用）：

```json
[
  {"id": "rival_d", "name": "吳某某", "party": "DPP", ...},
  {"id": "rival_e", "name": "陳某某", "party": "TPP", ...}
]
```

設計理由：候選人名單太長不適合塞 CLI，JSON 檔容許完整 `description`（這段文字會被 evolver 讀來算 `party_align_bonus` / `charisma`）。

### 4.3 CLI 輸出

```
[primary] Generating 3 templates for 2026 KMT 松信 councilor primary...
  → data/templates/primary_2026_kmt_songshan_xinyi_councilor_intra.json
  → data/templates/primary_2026_kmt_songshan_xinyi_councilor_head2head.json
  → data/templates/primary_2026_kmt_songshan_xinyi_councilor_mixed.json

[dimensions] Aggregating 臺北市|松山區 + 臺北市|信義區 ...
  population_total: 397,482 (18+ voter pool)
  township_count: 2

[party_member_stats] Loaded from ap/shared/tw_data/party_members_2026.json:
  KMT: 331,410 (as of 2025-09-10)
  DPP: 240,000 (as of 2023-01-01)
  TPP: 32,546  (as of 2025-08-10)

Done.
```

### 4.4 Dimension 聚合邏輯

Constituency = 多 township 時，從 `data/census/townships.json` 讀取對應 township 的各維度 raw count，sum 後重新 normalize 成 weight。這部分沿用既有 `sum_dim()` helper，只需把輸入從「單一縣市所有 township」換成「指定 township 清單」。

### 4.5 Calibration profile

新增 `primary` profile 到 `_calibration_defaults()`：

```python
if profile == "primary":
    # 初選：選民只在同黨 / vs 對手黨，本地議題主導，新聞影響較低（短期不會改變黨員投票傾向）
    return {**base, "news_impact": 1.5, "base_undecided": 0.15,
            "shift_consecutive_days_req": 3,
            "incumbency_bonus": 10,   # 現任優勢明顯
            "news_mix_candidate": 40, "news_mix_national": 10,
            "news_mix_local": 45, "news_mix_international": 5}
```

---

## 5. Evolution / Predictor 分支

### 5.1 Evolver：`primary_method` 判讀

`evolver.py` 在 scoring loop 開頭讀：

```python
_primary_method = job.get("primary_method") or election.get("primary_method")
_is_primary = election.get("type") == "party_primary"
_primary_party = election.get("primary_party")
```

三個分支：

**intra** (黨內同室)：
- 關閉 `party_align_bonus`（所有候選人同黨，無法用政黨對齊加分）
- 強化 `candidate_charisma` 權重 +50%（選民投給誰基於個人魅力）
- 強化 `local_visibility` 權重 +30%（基層鄰里曝光）
- `is_incumbent` 加成 +15（現任優勢在黨內初選尤其明顯）

**head2head** (vs 對手黨)：
- 沿用既有 presidential/mayoral scoring（`party_align_bonus=15`、`is_incumbent=8`）
- `candidates` pool = 黨內參選人 + `rival_candidates`
- 每個黨內參選人獨立 vs 對手計算，取平均作為該參選人「外部競爭力」

**mixed** (混合)：
- evolver 同時保留 intra & head2head 兩組 score（存入 `agent_state.primary_scores` dict）
- 給 predictor 做最後加權合成

### 5.2 Predictor：Rolling poll + sampling frame

`predictor.py` 新增模組級別 helper：

```python
def _apply_sampling_frame(agents, frame_cfg, primary_party):
    """依 frame 配置過濾 + 加權 agent 抽樣母體。"""
    if frame_cfg.get("filter"):   # party_member frame
        _col = f"{primary_party.lower()}_member"
        agents = [a for a in agents if getattr(a, _col, False)]
    if frame_cfg.get("age_weights"):
        # 依 age bucket 決定抽樣時的 weight（不是過濾，是 biased sampling）
        return agents, [frame_cfg["age_weights"].get(a.age_bucket, 1.0) for a in agents]
    return agents, [1.0] * len(agents)


def _run_rolling_poll(agents, method, days, daily_n, frame_cfg,
                      primary_party, rival_candidates, rng):
    """跑 N 天 rolling poll，回傳每日結果 + 平均。"""
    daily = []
    for d in range(days):
        pool, weights = _apply_sampling_frame(agents, frame_cfg, primary_party)
        sample = rng.choices(pool, weights=weights, k=min(daily_n, len(pool)))
        if method == "intra":
            tally = _tally_intra(sample)
        elif method == "head2head":
            tally = _tally_head2head(sample, rival_candidates)
        daily.append(tally)
    return _rolling_average(daily)
```

### 5.3 Mixed 合成

```python
if primary_method == "mixed":
    intra_result  = _run_rolling_poll(..., method="intra", frame=dual/landline/mobile)
    h2h_result    = _run_rolling_poll(..., method="head2head", frame=dual/landline/mobile)
    member_result = _run_rolling_poll(..., method="intra", frame=party_member)

    w = primary_formula   # {"intra_poll_weight":0.5, ...}
    final = {cand: intra_result[cand]  * w["intra_poll_weight"]
                 + h2h_result[cand]    * w["head2head_poll_weight"]
                 + member_result[cand] * w["party_member_weight"]
             for cand in candidate_ids}
```

### 5.4 Fallback / Error handling

- 若 `sampling_frame == "party_member"`（或 `primary_method=="mixed"` 需用到 party_member frame）但 agents 的 `*_member` 欄位全是 None → raise `MissingPartyMemberDataError`，predictor 回 422 給 UI，UI 顯示「請重跑 synthesis 以推導黨員資訊」
- `rival_candidates` 空但 `primary_method` 是 `head2head` / `mixed` → raise `MissingRivalCandidatesError`
- 若 frame_cfg 引用不存在的 age bucket → fallback weight = 1.0，log warning
- 若 row 有 `age` 整數但無 `age_bucket` 欄位 → `_bucket_from_age(age)` helper 回推（implementation 時統一處理）

---

## 6. Persona Generation Report

### 6.1 輸出位置與格式

每次 synthesis 完成，除了既有 `synthesis_result.json`，額外在 workspace 寫 `persona_generation_report.md`：

```markdown
# Persona Generation Report
Workspace: 1adedb2a
Generated: 2026-04-18T15:23:10Z
Template: primary_2026_kmt_songshan_xinyi_councilor_mixed
Target count: 1000

## 黨員統計資料來源

本次 persona 生成依據以下公開資料推導 `kmt_member` / `dpp_member` / `tpp_member`：

| 黨 | 黨員數 | 截止日 | 來源 |
|---|---|---|---|
| KMT | 331,410 | 2025-09-10 | [KMT 中央黨部 2025-09 公告](https://www.kmt.org.tw/2025/09/blog-post_25.html)（fetched 2026-04-18） |
| DPP | 240,000 (估) | 2023-01-01 | [維基百科](https://zh.wikipedia.org/wiki/民主進步黨)（fetched 2026-04-18）—— 官方 2024-25 未更新 |
| TPP | 32,546 | 2025-08-10 | [中央社 6 週年黨慶報導](https://www.cna.com.tw/news/aipl/202508100030.aspx)（fetched 2026-04-18） |

成人人口（20+）基準：19,500,000（國發會 2026 推估）

## 推導公式

基準率：`KMT 1.70%、DPP 1.23%、TPP 0.17%`
乘數：`party_lean × age × ethnicity × county`（見 `ap/services/synthesis/app/builder.py:_derive_party_member`）

## 產出黨員分佈

| 欄位 | True | 預期 | 偏差 |
|---|---|---|---|
| kmt_member | 17 (1.7%) | 17 | 0% |
| dpp_member | 13 (1.3%) | 12 | +8% |
| tpp_member | 1  (0.1%) | 2  | -50%*|

*樣本數 1000 下 TPP 期望值 2，單筆波動屬正常 Poisson 雜訊。

## 族群 / 縣市 cross-check

| party_lean | kmt_member rate | 論證合理性 |
|---|---|---|
| 深藍 | 9.8% | ✅ 基準 1.70% × 深藍 boost 6x ≈ 10.2%，吻合 |
| 偏藍 | 5.2% | ✅ 1.70% × 3x = 5.1% |
| 中間 | 0.5% | ✅ |
| 偏綠 | 0.2% | ✅ |
| 深綠 | 0.1% | ✅ |

（若偏差 > ±30% 則以 ⚠️ 標示供使用者檢視）

## 已知限制

- DPP 黨員數引用 2023 年資料，官方未更新，精度受限於 ±10% 估值
- 鄉鎮級黨員濃度資料缺（只有縣市級 override），松信區 vs 萬華區的 KMT 黨員密度差異未反映
- 跨黨員登記（同時為 KMT + TPP 黨員者）各自獨立抽樣，可能略高於實際
```

### 6.2 實作位置

- `ap/services/synthesis/app/builder.py`：`build_personas()` 最末加 `_write_generation_report(workspace_path, template, stats, persons)`
- 若 template 不是 primary（無需黨員欄位），報告仍寫但不包含黨員章節

---

## 7. PredictionPanel UI

### 7.1 新增區塊

在 `PredictionPanel.tsx` 加一個 `<section>`，只在 `activeTemplate.election.type === "party_primary"` 時 render：

```tsx
{election?.type === "party_primary" && (
  <section>
    <h3>🗳️ 初選模式設定</h3>

    {/* Method family selector */}
    <RadioGroup value={primaryMethod} onChange={setPrimaryMethod}>
      <Option value="intra">互比式民調（黨內同室比較）</Option>
      <Option value="head2head">對比式民調（vs 對手黨）</Option>
      <Option value="mixed">混合式（民調 + 黨員投票）</Option>
    </RadioGroup>

    {/* Sampling frame */}
    <Select label="採樣方式" value={samplingFrame} onChange={setSamplingFrame}>
      <Option value="landline">市話（偏高齡）</Option>
      <Option value="mobile">手機（偏年輕）</Option>
      <Option value="dual">雙軌 50/50</Option>
    </Select>

    {/* Rolling days */}
    <NumberInput label="連續天數" min={1} max={7} value={pollDays} onChange={setPollDays}/>

    {/* Mixed-only: weight sliders */}
    {primaryMethod === "mixed" && (
      <>
        <Slider label="互比式民調 %" value={w.intra}  onChange={...}/>
        <Slider label="對比式民調 %" value={w.h2h}    onChange={...}/>
        <Slider label="黨員投票 %"   value={w.member} onChange={...}/>
        <Note>三者總和自動 normalize 到 100%</Note>
      </>
    )}

    {/* Rival candidates editor (head2head / mixed) */}
    {(primaryMethod === "head2head" || primaryMethod === "mixed") && (
      <RivalCandidatesEditor
        value={rivalCandidates}
        onChange={setRivalCandidates}
        defaultFromTemplate={election.rival_candidates ?? []}
      />
    )}

    {/* 黨員資料健康檢查 */}
    {hasSynthesisWithoutPartyMembers() && (
      <Warning>⚠️ 目前 persona 未推導黨員資訊，建議重跑 synthesis</Warning>
    )}
  </section>
)}
```

### 7.2 State 持久化

新增 meta.json 欄位：
- `primaryMethod`
- `primarySamplingFrame`
- `primaryPollDays`
- `primaryFormulaWeights`
- `primaryRivalCandidates`（允許使用者 override template 預設）

Type 規範（避免 Stage 8.15 同類錯誤）：
- weights 一律 `number` 且 `>= 0 && <= 1`
- `pollDays` 一律 `number`，<1 時 fallback 1
- `rivalCandidates` 一律 array，restore-from-saved 用 `Array.isArray` 守門

### 7.3 API 欄位 surface

`ap/services/api/app/routes/templates.py` 的 template response 新增 primary 欄位透出：

```python
"election": {
    ...,
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

`ap/services/web/src/lib/api.ts` 的 `TemplateMeta.election` TypeScript 介面同步擴充。

---

## 8. 黨員統計資料 Fetch 流程

每次 `build_templates.py --primary` 執行時：

1. 讀取 `ap/shared/tw_data/party_members_2026.json`（如存在且 `as_of` < 180 天）→ 直接使用
2. 否則 warn：「黨員資料超過 180 天未更新，請執行 `python3 scripts/refresh_party_members.py`」
3. 新腳本 `scripts/refresh_party_members.py`：
   - WebFetch KMT / DPP / TPP 官網 + 維基 + 中央社
   - 以簡單 regex 抓出最新數字（容許 LLM fallback）
   - 更新 `party_members_2026.json` 並顯示 diff
   - 手動 commit

此腳本與 Stage 8 的 `refresh_news_sources` 模式一致。

---

## 9. 驗證計畫

### 9.1 Unit test

- `tests/test_derive_party_member.py`：feed 10,000 fake rows，assert 各黨員比例在預期 ±20% 內
- `tests/test_primary_template_generator.py`：跑 `build_templates.py --primary` 對固定 fixture，assert 產出 3 個 JSON 且 schema 合法
- `tests/test_sampling_frame.py`：
  - landline frame → age 55+ 佔比 > 60%
  - mobile frame → age 20-44 佔比 > 60%
  - party_member frame → 所有 sample 的 `*_member` 都是 True

### 9.2 Integration：松信 KMT 初選 smoke test

`scripts/verify_primary_template.py`：

```
1. build_templates.py --primary --party KMT --townships "臺北市|松山區,臺北市|信義區" ...
2. ingestion + synthesis 跑出 500 agents（使用產出的 intra template）
3. 檢查 agent_info：kmt_member=True 比例 ≈ 1.7% × 深藍 boost（松信深藍比例偏高，預期 2-4%）
4. evolution 跑 3 天（小 sim 驗證 pipeline）
5. prediction 跑 intra / head2head / mixed 三套，輸出支持率
6. 確認三套結果不同（若相同就是 scoring 分支沒 kick in）
7. 輸出 persona_generation_report.md，檢查黨員統計章節正確
```

### 9.3 Regression：舊 template 不受影響

跑一次既有 `presidential_2028_lai_vs_cheng` 的 prediction，確認結果與 Stage 8 結束時記錄一致（±2% 波動以內）。

---

## 10. 風險與回退

| 風險 | 影響 | 緩解 |
|---|---|---|
| DPP 黨員數為 2023 估值，誤差可能大 | 黨員投票模擬偏離實況 | `party_member_stats.estimate_note` 標註；report 顯式標 ⚠️ |
| `primary_formula` 任意權重 → prediction 結果可 cherry-pick | 使用者可能調出想要的答案 | 預設值鎖在歷史常見比例（KMT 5:3:2）；UI 不藏預設 |
| 跨黨員登記未處理 | TPP 黨員可能同時是 KMT 黨員，被重複計票 | 文件標註限制；未來 enhancement 可加 joint table |
| UI 新增欄位與舊 workspace `meta.json` 不相容 | reload 報錯 | 所有新欄位 optional + Array.isArray 守門（Stage 8.15 教訓） |
| 黨員 bucket 數過小（TPP 1000 agents 只 1-2 個）→ prediction 雜訊大 | 小樣本失真 | UI 在黨員比例 < 5 時顯示「樣本過小」warning |

### 回退方案

任一 milestone 後若發現結構問題：

1. Schema 層：新欄位全為 optional → 可直接 revert Person schema 而不影響既有資料
2. Template 層：新 primary template JSON 檔獨立於既有 31 檔 → 刪 primary_ 系列即可
3. Predictor 層：`_run_rolling_poll` 獨立函式 → 可 guard 在 `if election.type == "party_primary"` 內
4. UI 層：整個 section 依 `type === "party_primary"` render → 非 primary template 完全看不到新 UI

---

## 11. 實作順序（for writing-plans）

建議 milestone 切法：

1. **Milestone 1**：黨員統計資料抓取 → `party_members_2026.json` 落地
2. **Milestone 2**：Person schema + synthesis 推導 → 跑通 100 agents 看黨員分佈
3. **Milestone 3**：`build_templates.py --primary` CLI → 產出松信 KMT 3 個 template 檔
4. **Milestone 4**：Evolver primary_method 分支 → 跑 3 天 sim 看各 method 分數差異
5. **Milestone 5**：Predictor sampling frame + rolling poll → 驗證 mixed 合成
6. **Milestone 6**：API / Web type 擴充 → PredictionPanel UI
7. **Milestone 7**：Persona generation report → 驗證輸出格式
8. **Milestone 8**：Integration smoke test + commit

每 milestone 結束可獨立 commit，失敗時可逐步 rollback。
