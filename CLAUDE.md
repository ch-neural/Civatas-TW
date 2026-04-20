# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 語言規則

- **思考過程**（thinking）可以使用英文。
- **所有最終回覆必須使用繁體中文**。

## Repository layout

This working directory holds **two distinct but related projects**:

1. **`/` (Civatas-TW data backbone)** — Taiwan-specific data (地圖、人口普查、
   選舉、藍綠 PVI 傾向指數) plus the Python fetch/transform scripts that produced
   it. No application code lives at the top level. See `README.md`.
2. **`ap/` (Civatas application)** — The 9-service Dockerized "Universal Social
   Simulation Agent Generation Platform", Taiwan edition. English is retained as
   a secondary locale; Traditional Chinese (zh-TW) is the default source of
   truth. See `ap/README.md`.

The `ap/` tree is **the live application**; the top-level scripts feed data into
it via 31 templates under `data/templates/`:
- 5 national 總統大選 (generic / 2024 回測 / 2028 賴 vs 盧 / 賴 vs 鄭 / 賴 vs 蔣)
- 1 民意調查 (`poll_2028_preferred_candidate` — 7 人)
- 3 2026 直轄市長 (台北 / 台中 / 高雄)
- 22 縣市版 presidential

`code/ap/` and `source/oasis` are vendored / reference trees — do not edit unless asked.

## Common commands

### Data pipeline (top-level Python scripts)

Run from the repo root. Scripts cache raw responses under each subdirectory's
`raw/`. Delete `raw/` to force a clean re-fetch.

```bash
python3 scripts/fetch_geo.py             # → data/geo/tw-{counties,townships}.geojson
python3 scripts/fetch_elections.py       # → data/elections/president_2024_township.csv
python3 scripts/fetch_census.py          # → data/census/{counties,townships}.json
python3 scripts/compute_pvi.py           # → data/elections/leaning_profile_tw.json
python3 scripts/build_templates.py --all # → data/templates/*.json  (31 templates)
python3 scripts/load_election_db.py      # → data/tw_election.db
```

`build_templates.py` supports selective generation via `--national`, `--poll`,
`--mayors`, `--counties` flags.

### Civatas application (`ap/`)

```bash
cd ap
cp .env.example .env
docker compose up --build                   # core: web + api + ingestion + synthesis + persona + adapter
docker compose --profile full up --build    # adds simulation + analytics
bash scripts/test_pipeline.sh               # end-to-end pipeline smoke test
```

- Web UI: http://localhost:3100 (override via `WEB_PORT` in `ap/.env`)  ·  API docs: http://localhost:8000/docs
- Each service is its own container in `ap/services/<name>/`.

### Convenience

`./start_claude_danger.sh` launches `claude --dangerously-skip-permissions` in this dir.

## Architecture

### Pipeline (`ap/`)

```
upload → ingestion(8001) → synthesis(8002) → persona(8003) → social(8004)
       → adapter(8005) → simulation(8006, OASIS) → analytics(8007)
              ↑                                              ↑
            api(8000) FastAPI gateway     web(3000) Next.js frontend
```

- **ingestion** parses CSV/JSON/Excel 人口統計到內部格式。
- **synthesis** 生成符合分佈的合成母體，欄位包含 `county / township / ethnicity /
  party_lean / cross_strait` 等。
- **persona** 把結構化 records 透過 LLM 轉成台灣住民 persona（繁體中文輸出），
  人格維度、認知偏誤、所得區間皆為中文 canonical。
- **social** (optional) 建立同質性偏好的 follow graph。
- **adapter** 輸出 OASIS-相容 CSV/JSON。
- **simulation** 跑 OASIS；**analytics** 解析 `.db` 結果。
- **evolution** (`ap/services/evolution/`)：台灣新聞爬蟲、5-bucket 藍綠傾向、
  每日 agent 演化；`tw_feed_sources.py` 是 ~60 家台灣媒體清單，快照到
  `ap/shared/tw_data/tw_feed_sources.json` 供 API gateway 直接 serve。
- **election-db** 有獨立的 `init/` 與 `importer/` 子服務。

Shared schemas 與 i18n locales 在 `ap/shared/`。改 schema 時需重建所有掛載它的 service。

### Data flow (top-level → `ap/`)

```
data/geo/        →  frontend map (tw-counties.geojson + tw-townships.geojson rendered by USMap.tsx / TaiwanMap alias)
data/census/     →  synthesis layer demographic distributions (12 維度：gender/age/education/employment/tenure/household_type/household_income/ethnicity/party_lean/media_habit/county/township)
data/elections/  →  party_lean dimension via 藍綠 PVI (5 buckets: 深綠 / 偏綠 / 中間 / 偏藍 / 深藍)
data/templates/presidential_national_generic.json   →  三黨 generic 模板
data/templates/presidential_2024.json                →  賴 vs 侯 vs 柯 (回測)
data/templates/presidential_2028_{lai_vs_lu,lai_vs_cheng,lai_vs_chiang}.json
data/templates/poll_2028_preferred_candidate.json   →  7 人民調
data/templates/mayor_2026_{taipei,taichung,kaohsiung}.json
data/templates/presidential_county_<slug>.json      →  22 縣市單一縣市 template
```

### 藍綠傾向指數（TW-PVI）

`scripts/compute_pvi.py` 讀取 2024 鄉鎮級總統資料（`ap/shared/builtin_modules/
president_2024.json`，來源：中選會）並計算藍綠兩黨偏差值：

```
share_G(township) = 綠 ÷ (綠 + 藍)             (民進黨 vs 國民黨兩黨)
delta_G(township) = share_G(township) − share_G(全國)
```

5-bucket 劃分：
- **深綠** pvi > +0.08
- **偏綠** +0.03 < pvi ≤ +0.08
- **中間** -0.03 ≤ pvi ≤ +0.03
- **偏藍** -0.08 ≤ pvi < -0.03
- **深藍** pvi < -0.08

柯文哲（白）獨立計算 `white_share`，不納入藍綠軸 —— 第三勢力不構成穩定 leaning。

全國兩黨得票率 2024：綠 54.46% / 藍 45.54%（兩黨分攤）；白 `white_share_all` = 26.46%。

## 從 Civatas-USA 改造為 Civatas-TW（2026-04-17）

本 repo 源自 Civatas-USA 複製，系統性地反向改造為台灣版。改造涵蓋 5 個階段：

### Stage 1 — 資料層重建
- 砍掉所有 US data（us-counties.geojson / ACS census / MEDSL elections / 54 個
  US template）。
- 重寫 6 支 scripts，用 g0v/ronnywang 的台灣 geojson（22 縣市 + 375 鄉鎮）、
  中選會 2024 鄉鎮級資料、主計總處普查 + 戶政司月報。
- 計算出的全國投票率驗證：**賴清德 40.05% / 侯友宜 33.49% / 柯文哲 26.46%**，有效票 13,947,506 —— 與 CEC 官方完全吻合。

### Stage 2 — Template Builder
- `scripts/build_templates.py` 單一腳本以 `--all/--national/--poll/--mayors/--counties`
  子命令產出 31 個 template。
- 維度 schema 用 ethnicity（閩南/客家/外省/原住民/新住民）取代 race/hispanic。
- 地理維度：22 縣市 + 368 鄉鎮市區 admin_key (`"臺北市|大安區"`)。
- Differentiated calibration profiles：`generic / 2024_backtest / 2028 / mayor / county`，每套有不同的 `news_impact`、`base_undecided`、`news_mix_candidate` 等。

### Stage 3 — Evolution / Persona / Crawler 引擎反向
- `ap/shared/schemas/person.py` 加 `ethnicity / county / township / cross_strait`
  欄位；保留 `race / hispanic_or_latino` 作舊資料 fallback。
- `ap/shared/leaning.py` 升級為 5-bucket 藍綠白系統（含 US→TW 字串 normaliser）。
- `evolver.py`：
  - 候選人別名表台灣化（賴 / 侯 / 柯 / 盧 / 蔣 / 沈 / 江 / 麥 / 柯志恩 / 賴瑞隆 等 20+）
  - `_augment_party_detection` 改為 DPP/KMT/TPP/IND buckets，用中文關鍵字分類
  - 頂端 `_tw_bucket()` 統一把舊 US bucket 字串 normalise 成 TW 5-tier
  - Leaning shift 訊息繁中、attitude 軸 `cross_strait`（取代 `national_identity`，
    保留 fallback）
  - `_BIAS_DESC` 7 個認知偏誤繁中（樂觀/悲觀/理性/從眾/陰謀論/替罪羊/冷感）
- `prompts.py`：整檔改寫為 6.4 KB 繁中 evolution prompt，含族群反應規則
  （閩南/客家/外省/原住民/新住民）、年齡口吻、月薪新台幣分級、新聞習慣、兩岸
  立場軸（主權派 ↔ 整合派）。
- `crawler.py` DEFAULT_SOURCES 12 家台灣媒體。
- 新建 `tw_feed_sources.py`（60+ 家媒體，5-bucket 分類，含政論節目 / PTT / LINE）。
- 新建 `tw_life_events.py`（27 台灣生活事件：媽祖繞境 / 客家義民節 / 原民祭典 /
  颱風 / 共軍軍演 / 電費漲 等）。
- `persona/prompts.py` 重寫為台灣 persona 設計 prompt：22 縣市地理錨點、TW 媒體
  清單、5-bucket 政治傾向、族群口吻範例。
- `synthesis/builder.py` 加 ethnicity / county / township 處理 + 台灣行政區
  衍生邏輯 + marital_status 繁中 fallback（未婚/已婚/離婚/喪偶）。

### Stage 4 — UI / i18n 反向
- `locale-store.ts` default → `"zh-TW"`（繁中為 source of truth，英文為 secondary）。
- `layout.tsx` 品牌改 "Civatas 台灣"。
- `USMap.tsx` 重寫為 Taiwan choropleth（equirectangular 投影 + aspect 校正），
  保留 `USMap` export name 向後相容；同時 export `TaiwanMap` alias。
- `tw-counties.geojson` + `tw-townships.geojson` 放到 `ap/services/web/public/`。
- `PopulationSetupPanel / SynthesisResultPanel / EvolutionDashboardPanel` 改用
  `region_code` 取代 FIPS；scope 從 `"state"` 改為 `"county"`（與 legacy "state"
  相容）。
- `template-defaults.ts` 全面 TW 化：macro context 繁中、local/national search
  keywords 台灣化、政黨偵測表 DPP/KMT/TPP/IND + 政黨色盤（綠 / 藍 / 青 / 灰）。
- `EvolutionQuickStartPanel` 新聞搜尋關鍵字與媒體池改台灣版本（12 家主流媒體
  + 5-bucket 光譜）。
- `PredictionPanel` 停用 Electoral College（台灣無選舉人團）。

### Stage 5 — 清理 + 文件
- 砍除無依賴的 US 資產：`ap/shared/us_data/{census,elections,geo,us_feed_sources.json}`、
  `leaning_profile_us.json`、`us_feed_sources.py`、`us_life_events.py`。
- 保留作 legacy fallback：`us_predictor_helpers.py`、`us_news_keywords.py`、
  `us_article_filters.py`、`us_leaning.py`、`us_admin.py`、`us_data/us_election.db`
  —— 這些仍被非 try-except import 引用，砍了會 module load 失敗。
- `ap/shared/tw_data/tw_feed_sources.json` 為 tw_feed_sources.py 的 JSON 快照,
  供 API gateway 在 `/api/runtime/news-sources` endpoint 直接 serve。

### Stage 6 — Persona 品質修正 + 時間壓縮 + age range（2026-04-17）

在 Stage 1–5 完成 US→TW 反向後，針對實際跑出來的 persona / evolution 結果持續
做行為品質調校。以下列出已實作的修正，後續繼續開發時可以直接沿用。

#### 6.1 Hybrid diary（敘事 + 結構化 tag sidecar）
- `ap/services/evolution/app/prompts.py` 的 EVOLUTION_PROMPT_TEMPLATE 與
  DIARY_PROMPT_TEMPLATE 都加入 `diary_tags` JSON block：
  ```json
  "diary_tags": {
    "mentioned_topics": ["油價", "罷免", "颱風", ...],  // 3–8 實際出現的主題
    "mood_arc": "平→低",                                  // 8 字內情緒走向
    "life_event_triggered": "颱風停班" | null            // 事件觸發
  }
  ```
- `evolver.py` 有 `_norm_diary_tags()` 對 LLM 輸出做 defensive 正規化（list/str
  都吃，trim 長度，null 值過濾）。entry dict 會多一個 `diary_tags` 欄位。
- 保留自然敘事口吻（narrative 主體不變），但下游可以直接 query 結構化欄位。

#### 6.2 API key 統一由 UI 管理
- `.env` 與 `.env.example` 的 `LLM_API_KEY=` 改成空值（舊 placeholder 會讓
  evolver 產生意外 fallback 到「default」vendor）。
- 所有 LLM vendor config 以 `settings.json` + UI 為 single source of truth。

#### 6.3 市場資料整合（股/匯/油）進 evolver macro_context
- 新增 `ap/services/evolution/app/tw_market_data.py`：
  - TAIEX ^TWII (Yahoo Finance chart API)
  - USDTWD=X / JPYTWD=X (Yahoo Finance)
  - 中油 CPC XML WebService 油價 + 歷史月價 fallback
  - Per-persona gate 函式：`_should_see_market/forex/oil`（依所得/年齡/職業判定
    誰會看股市、匯率、油價）
- `start_evolution()` 在 job 啟動時一次撈完整 window 的市場 context，存進
  `job["_market_{taiex,forex,oil}_text"]`；`_run_agent_day()` 依 gate 組合進
  `macro_context`。

#### 6.4 時間壓縮自動調參
- `EvolutionQuickStartPanel.tsx` 新增時間壓縮自動縮放：
  - `computeCompression(startDate, endDate, simDays)` = 真實天數 / 模擬天數
  - 相對於 template 的 baseline compression 自動縮放進階參數：
    - `news_impact × √factor`
    - `shift_consecutive_days_req ÷ factor`（clamp 1–14）
    - `satisfaction_decay / anxiety_decay × factor`
    - `delta_cap_mult × √factor`
    - `forget_rate × factor`
    - `articles_per_agent × min(factor, 2)`
  - 以 `templateRefCompression` state 錨定 baseline，避免多次修改天數導致複合飄移。
  - 使用 `autoScaleReadyRef` 避免 mount 時立即觸發。
  - 使用者仍可在 auto-scale 之後再手動微調。
  - UI 有一條 banner 顯示目前壓縮比。

#### 6.5 Per-template 年齡範圍
- `scripts/build_templates.py._build_election_block()`：
  ```python
  default_age_range = [20, 85] if etype == "poll" else [20, 95]
  ```
  （TW 投票年齡 = 20；poll 收窄到 85 因為電話民調極少觸及 85+）
- `ap/services/api/app/routes/templates.py` 把 `default_age_range` 從 election
  block surface 到 `/api/templates` 回應。
- `ap/services/web/src/lib/api.ts` 的 `TemplateMeta.election` 型別加上
  `default_age_range?: [number, number] | null`。
- `PopulationSetupPanel.tsx`：
  - `ageMin` 預設從 18 改 20
  - `ageFromSavedRef` + `settingsLoaded` state 確保只在使用者「沒存過」時才
    套用 template default（不覆蓋自訂值）

#### 6.6 cross_strait 維度自動推導
原本 `Person.cross_strait` 欄位（主權 / 經濟 / 民生）100% empty，因為 template
沒有這個 dimension。改成在 synthesis 的 `_enforce_logical_consistency` 推導：

```python
# ap/services/synthesis/app/builder.py
_lean_weights = {
    "深綠": (55, 15, 30),  # (主權, 經濟, 民生)
    "偏綠": (35, 20, 45),
    "中間": (15, 25, 60),
    "偏藍": (10, 45, 45),
    "深藍": (5,  55, 40),
}
# ethnicity 調整：外省→+經濟、原住民→+主權、新住民→+民生
```

`evolver.py` 在初始化 `attitudes` 時讀 `agent.cross_strait`，用來 refine
`issue_priority` 並微調 `attitudes.cross_strait` 數值軸 ±15 點，讓同黨派的
agent 仍有異質性。

**驗證分佈**（100 agents, 2028 template）：
| party_lean | 主權 | 經濟 | 民生 | 目標 |
|---|---|---|---|---|
| 深綠 | 63% | 16% | 21% | 55/15/30 |
| 偏綠 | 30% | 30% | 39% | 35/20/45 |
| 中間 | 24% | 0%  | 76% | 15/25/60 |
| 偏藍 | 0%  | 63% | 38% | 10/45/45 |
| 深藍 | 6%  | 53% | 41% | 5/55/40 |

#### 6.7 原住民地理重新採樣
之前 100 agents 裡有原住民被分配到雲林斗六 / 嘉義 / 彰化（<1% 原民縣市），
因為 template 的 ethnicity 和 county dim 獨立採樣、不是 joint table。

修法（synthesis/builder.py `_enforce_logical_consistency`）：
```python
_ind_ok_counties = {"臺東縣","花蓮縣","屏東縣","南投縣","新北市",
                    "桃園市","高雄市","宜蘭縣","新竹縣","苗栗縣"}
if row.get("ethnicity") == "原住民" and row["county"] not in _ind_ok_counties:
    # 從加權池重新採樣 township（臺東 35% / 花蓮 15% / 新北 12% / 桃園 10% /
    # 屏東 10% / 南投 8% / 高雄 7% / 宜蘭 3% / 新竹縣 3% / 苗栗 1%），
    # 混合原鄉部落 + 都會原民聚落
    row["township"] = _new_key  # 例如 "臺東縣|金峰鄉"
    row["county"] = ...; row["district"] = ...
```

**驗證**：重新生成後 3/3 原住民 agent 都落在合理位置（新北土城 / 屏東瑪家 /
南投埔里），再無雲林/嘉義錯誤分配。

#### 6.8 persona prompt 族群文化元素強化
`ap/services/persona/app/prompts.py` 在 `[風格要求]` 區塊擴充族群細節指引：
- 閩南：台語（拍勢 / 阿祖 / 厝 / 甲意）、祭祖、粿/米粉湯
- 客家：客家庄、義民爺、擂茶、薑絲炒大腸、桐花季
- 外省：大陸老家、眷村菜、祖輩軍公教
- 原住民：**必須**提族別（16 族擇一）、部落名、族語（mama/ina/malikuda）、
  豐年祭/小米祭/狩獵、傳統領域/族語復振
- 新住民：娘家國家、母語夾雜、新二代

**驗證族群文化命中率**（100 agents）：
| 族群 | n | 文化關鍵字命中 | 評估 |
|---|---|---|---|
| 客家 | 16 | 13 (81%) | ✅ |
| 外省 | 8 | 0 (0%) | ⚠️ 已提 role 但無具體省籍 |
| 原住民 | 3 | 0 (0%) | ⚠️ 有通稱「我們原住民」但無族別 |
| 新住民 | 1 | 1 (keyword miss / 實際有提大陸媳婦) | ✅ |

LLM 對 metadata-heavy 的族群（需要族別 / 省籍 name）會省略具體 token。目前
接受現狀（Option A）。若未來要強化，可做 **tribal_affiliation / origin_province
預分配**（依 township / 父輩推 assign，顯式傳入 prompt）。

### Stage 6 待辦（開發到另一台 PC 前）
- [x] `Tavily/Serper` 新聞搜尋 `lr=lang_en` 改 `lr=lang_zh-TW`（CLAUDE.md
      最末提到，Stage 6 待驗證項目）
- [x] 原住民族別 + 外省籍貫預分配 → `tribal_affiliation` / `origin_province`
      欄位加入 Person schema，synthesis 預分配，persona/evolution prompt 注入
- [x] 縣市級維度 override（年齡/教育/就業/所得/住宅 tenure）取代全國平均
      — 22 縣市完整覆蓋，鄉鎮級差異（內湖 vs 萬華）仍為 future work
- [ ] 補 2020 鄉鎮級總統資料讓 PVI 兩屆平均、增強穩定性（非必要）

### Stage 7 — UI/UX 修正 + 演化穩定性（2026-04-17 ~ 04-18）

在 Stage 6 feature 完成後，實際跑 30 天演化（賴清德 vs 鄭麗文, 100 agents）
過程中發現並修正的問題：

#### 7.1 Evolver vendor fallback 修正
- `_call_llm()` 的 `else` 分支（agent 無 `llm_vendor`）會先嘗試 env-based
  default（空的 `LLM_API_KEY`）→ 必然 401 → 再 fallback。改為有 configured
  vendor 就直接使用，跳過 env-based default。

#### 7.2 UI 政治傾向標籤在地化
- i18n: 民主黨傾向→綠營傾向、共和黨傾向→藍營傾向、搖擺→中間
- 圖表顏色: 美式紅藍 → 台灣綠（#1B9431）藍（#0000C8）
- 新聞 bucket: Solid Dem→深綠、Lean Rep→偏藍 等 5-bucket
- EvolutionPanel 的 CNN/NPR 改為自由時報/三立/聯合報/中時
- export playback 同步更新

#### 7.3 候選人圖表自動黨派色盤
- `EvolutionDashboardPanel` 新增 `detectCandParty()` 函式：
  1. 優先查 job 的 `party_detection` 表（如「賴清德→DPP」）
  2. Fallback: 名稱/描述 regex（民進黨/DPP/綠營 等）
  3. 無匹配 → IND 灰色
- `LEAN_COLORS` 改為台灣綠藍 + 5-tier TW label 支援
- evolution dashboard API 新增回傳 `party_detection` + `candidate_descriptions`

#### 7.4 Template 切換候選人覆蓋 bug
- 問題：切換 template（如 generic 3 黨→2028 兩黨）時，workspace 持久化的
  `custom-candidates` 會覆蓋新 template 的候選人
- 修正：載入 custom candidates 時比對是否與當前 template 吻合；template
  候選人變動時自動 reset

#### 7.5 Dashboard 交叉分析 Unknown
- `agent_info`（age/gender/education/occupation/district 等）從未被 evolver
  儲存 → dashboard 全部顯示 "Unknown"
- 修正：`start_evolution()` 從 agents 提取人口統計並存入 job + 磁碟
  `agent_info.json`

#### 7.6 AI 分析 502 — o4-mini 相容
- `o4-mini` 是 reasoning model，不支援 `temperature` 和 `max_tokens`
- 修正：偵測 reasoning model（o1/o3/o4 prefix）→ 改用
  `max_completion_tokens`、合併 system/user message、加長 timeout

#### 7.7 演化中斷恢復
- 問題：container 重建導致演化中斷時，前端 `evolution-progress` 狀態為
  `"error"` → 不顯示 Resume 按鈕
- 修正：`"error"` 狀態也觸發 Resume UI，自動修正為 `"paused"`

#### 7.8 JSON 解析防護
- `_load_states()` / `_load_diaries()` 讀損壞 JSON 時直接 crash →
  dashboard API 500
- 修正：加 try/except 降級回傳空值

### Stage 8 — 英文-only keyword bug 系統性清除（2026-04-18）

跑 30 天 2028（賴 vs 鄭, 100 agents）演化發現賴清德支持率單調下滑
（43→34，−8.7pts）。深掘 root cause 是 **`evolver.py:is_incumbent`
只認英文 keyword**（`"incumbent"`/`"sitting president"`/`"vice president"`），
template 的繁中描述「時任總統尋求連任」完全 match 不到 → 賴清德沒拿到
incumbency_bonus + 沒進入現任 anxiety branch → 鄭麗文（is_rep）獨享
challenger 焦慮加分，每 agent-day 多拿 ~20 分。

順著這條線索做了**全 codebase 系統審計**，找出並修掉同一 bug class（英文
keyword 在繁中模板下沉默失效）的所有場景。

#### 8.1 Backend 評分核心修正（`evolver.py`）

- **`is_incumbent` 三層偵測**（最致命）：
  1. 從 job 讀 `_candidate_incumbent_map[cname]`（template `is_incumbent`
     欄位的權威來源）
  2. 英文 keyword（向後相容）
  3. 繁中 keyword 限定`"尋求連任"`/`"現任總統"`/`"現任副總統"`
     —— 刻意不用 bare`"時任"`/`"現任"`，因為「時任新北市長」（侯友宜）
     等非總統現任者也會誤 match
- **`_party_detection` key mismatch**：scoring loop 原本用 `_pd.get("D"/"R"/"I")`
  查 augmented map，但 `_augment_party_detection` 寫的是 `DPP/KMT/TPP/IND`
  —— **整個 `party_align_bonus=15` 對 TW 模板靜默失效**。改用
  `_pd_match("DPP")` 等 modern key + 保留 D/R/I legacy fallback
- **候選人 party 第一道偵測**（`is_dem`/`is_rep`/`is_ind`）加繁中 keyword：
  `民進黨`/`綠營`/`國民黨`/`藍營`/`民眾黨`/`白營`/`無黨籍` + 簡寫碼
  `DPP`/`KMT`/`TPP`
- **`_resolve_base()` fallback**：英文 only 全部 fallback 到 30.0 → 加
  TW 路徑（民進黨/國民黨→50, 民眾黨→30, 無黨籍→5）
- **`cand_party` 推導**：TW 候選人名通常沒括號黨派標籤 → cand_party=""
  → `_resolve_base(desc)` 退回 30。改為從 `_party_detection` bucket lookup
  自動補 `cand_party = "DPP"/"KMT"/...`
- **`candidate_awareness` seed**：沒 poll_groups 的 template（即所有 TW
  template）下，state 為空時 cand_awareness 永遠空 → dashboard awareness
  圖表斷線成 None。改為從 `candidate_names` seed 0.3
- **Reasoning model token budget**：o4-mini 在完整 evolution prompt 下
  reasoning 吃 3.7k token、content 還沒寫完就被 4096 截斷 → JSON 空 →
  fallback 到 openai-1。`max_completion_tokens` 4096→**16384**

#### 8.2 News 處理繁中化（`feed_engine.py`）

- **`_categorize_article()`**：5 類 keyword 全英文（inflation/china/abortion）
  → TW 文章 100% 落入 `"General"` → demographic affinity 失效。加繁中 keyword
  池（通膨/股市/中共/兩岸/同婚/罷免/藍綠 等，每類 20+ 詞）
- **`_demographic_affinity()`**：
  - leaning 檢查只認 `Solid Dem`/`Lean Rep` → TW 5-bucket（深綠/偏綠/...）
    完全不 match。改為接受兩種 label
  - occupation 檢查只認英文（`business`/`finance`）→ 加繁中（商/業務/金融/
    服務業/主管 等）
  - gender `f`-prefix 加繁中`"女"`
- **`_IRRELEVANT_BOARD_PATTERNS` 等**：原本只過濾 joke/sports/marvel 等
  英文 → 新增 `_IRRELEVANT_BOARD_PATTERNS_ZH`（八卦/棒球/影劇/3C/旅遊）
  及繁中 title/content 黑名單

#### 8.3 News 注入分類（`news_pool.inject_article`）

- 原本 `inject_article(..., source_leaning="中間")` 預設 → 822 篇都掛
  `中間`，自由時報/中時/中天 leaning 全壓平 → media_habit filter 失效
- 改為 `source_leaning: str | None = None`，未指定時自動查
  `tw_feed_sources.DEFAULT_SOURCE_LEANINGS[source_tag]`（自由時報→偏綠、
  中時→偏藍、中天→深藍 …）
- `InjectArticleRequest` 新增 optional `source_leaning` 讓前端可顯式覆寫

#### 8.4 Dashboard 缺日 bug（`main.py`）

- `_global_offset += sj.get("total_days", 0)` → 中斷的 job（current_day
  < total_days）會霸佔不存在的 timeline slot → candidate_trends 永久缺
  day 15 / day 18
- 改用 `len(sj.get("daily_summary", []))` 推進 offset，與 `evolver._load_history()`
  的 `len(history)` 邏輯對齊

#### 8.5 民調 survey endpoint（`main.py`）

- `person_party` 比對只認 `republican`/`democrat`/`independent` → 用戶
  輸入「民進黨」時 alignment bonus 全空。加 TW 黨名 + DPP/KMT/TPP 簡寫碼
- 初始化 leaning 效果 line 2042 漏 `Solid Rep`/`Lean Rep` → 補上

#### 8.6 Predictor incumbent flag（`predictor.py`）

- 原本只讀 `group_cands[ci].get("isIncumbent", False)`（camelCase）
  → 直接 load raw template JSON（snake_case `is_incumbent`）時永遠 False
- 改為同時讀 `isIncumbent` + `is_incumbent` + 繁中 fallback
  `"現任"`/`"尋求連任"`，line 1689 + line 3420 兩處皆修

#### 8.7 News intelligence 社群源 leaning（`news_intelligence.py`）

- `_SOCIAL_SOURCE_MAP` 把 PTT/Dcard 標 `偏左派`/`中立`（3-tier legacy
  label）→ feed_engine 的 `_leaning_index` 找不到 → 預設 Tossup → 5-bucket
  affinity 算錯
- 全部改成 TW 5-bucket（PTT 政黑→偏綠、八卦→偏綠、其它→中間）

#### 8.8 Evolution 設定（`EvolutionQuickStartPanel.tsx`）

- 原本 enabled_vendors 包含 `system_vendor_id`（system-llm = o4-mini）
  → 50% agents 走 reasoning model → token 浪費 + latency 加倍
- 改為排除 system_vendor + 尊重 `active_vendors` whitelist

#### 8.9 PredictionPanel 全面繁中化

- `getPartyDefault()`：加 DPP/KMT/TPP/IND + 繁中黨名（原本 TW 候選人都拿
  default 30 分）
- `computeSmartBaseScore()`：partyId 收 DPP/KMT/TPP/IND；角色 bonus 加
  繁中（總統/縣長/直轄市長/市長/立委/議員/候選人）；`isIncumbent` 接受
  `is_incumbent` snake_case + 「尋求連任/現任總統」
- `autoTuneParams()`：同黨對決偵測加 DPP/KMT/TPP 三方陣營分流
- 五個 panel 的 `LEAN_COLORS` 加 TW 5-bucket（PopulationSetup /
  SynthesisResult / Persona / AgentExplorer / PredictionEvolutionDashboard）
- `EvolutionPanel.tsx` Diet tab spectrum 自動偵測 TW 標籤

#### 8.10 Macro context endpoint 繁中化（`pipeline.py`）

`/api/pipeline/generate-macro-context` 與 `/api/pipeline/suggest-keywords`
原本 **完全 hardcode 美國政治**（"You are a senior US political analyst…"、
查詢 `"United States" president`/`Congress`、example output 提到 Trump +
Josh Shapiro）。

修法：
- `_looks_like_tw()` helper：偵測 county/candidates 含 CJK 即視為 TW
- 兩個 endpoint 加 `country` 參數（前端從 `activeTemplate.country` 顯式傳）
- TW 路徑用繁中 prompt + 繁中 search query：涵蓋 中央/立法院/經濟/縣市治理/
  兩岸/國防/歸責心理 8 面向
- 搭配 8.1 的 `max_completion_tokens` 修正讓 o4-mini 系統 vendor 也能跑

#### 8.11 PredictionPanel 跨地區 stale 偵測

`PredictionPanel.tsx` 開頭原本只有 `looksLikeTwSeed()` —— 用來在 US
workspace 切回時清掉殘留 TW 內容。但**反方向**沒人管：TW workspace 載到
之前存的「Federal: ... Congress is narrowly divided ...」美國 fallback
英文，每次 reload 都復活。

修法：
- 新增 `looksLikeUsSeed()`（偵測 Federal/Congress/Governor/sitting
  President/President's party 等）
- restore-from-saved 邏輯（line 935）改為依 `activeTemplate.country` 雙向
  判斷 stale
- 兩處 macro 自動 seed effect 都改為 locale 跟著 template country 走
  （TW→`zh-TW`、US→`en`）
- 第二處 useEffect 的硬編碼美國 fallback 整段改為 TW 繁中
- 同時清掉 `1adedb2a/meta.json` 的舊 US 內容

#### 8.12 Macro context runtime fallback enrichment

所有 31 個 template 的 `default_macro_context` 都偏短（23–61 字一句話），
不夠 LLM 理解環境。

`getDefaultMacroContext(template, locale)` 加邏輯：
- 若 template 自帶 macro `< 80` 字 → 自動補：
  ```
  [模擬情境]
  {template 那句話}

  [台灣政治經濟現況]
  {完整 TW 環境段落}
  ```
- 81 字以上原樣顯示
- 31/31 template 全部走 enrichment（最長的 poll = 61 字也涵蓋）
- **不修改 template JSON**，避免 31 檔重 build + 維護成本

#### 8.13 Workspace meta.json 清理（`1adedb2a`）

只有此 workspace 有 stale 預測設定（`f2511641` 為空）：
- `predictionMacroContext` 4 行美國 hardcoded 英文 → 清空（reload 後重 seed）
- `predCounty: "苗栗縣"` → `""`（全國總統大選不該鎖縣市）
- `pollGroups[0].name`「Likely Voters」→「可能投票者」
- 候選人 `localVisibility/nationalVisibility` 50/50 → 賴 90/95、鄭 70/80
  + `originDistricts` 加上 臺南/臺北
- `predFetchNationalQuery` 6 行裡 3 行專搜「賴清德 政績/民進黨 執政 成果」
  → 改 10 行藍綠平衡
- `predLocalKeywords` / `predNationalKeywords` 城市名+泛詞 → 加上議題詞

### Stage 8 設計決策：runtime fallback > 改 template 檔

考量過直接編輯 31 個 template JSON 加長 macro_context、補豐富 keyword，
最終選擇 **runtime 動態補強**：
- ✅ 改一個 helper 套全部 31 template
- ✅ AI 即時抓的內容比 template 寫死的更新鮮
- ✅ 不增加 template 維護成本（每改一句要重 build）
- ✅ 用戶按「AI 生成」按鈕得到 8 面向、含當期民調/事件的完整繁中簡報

只有兩種情況才改 template JSON：
1. 候選人陣容變動（換人/退選）→ 改 `candidates` 區塊
2. AI 一直被某 template 的「[模擬情境]」誤導 → 改該 template 的
   `default_macro_context`

### Stage 8 — 英文 keyword 殘留盤查工具

未來新增功能時，用以下 grep 確保不再引入同類 bug：

```bash
# 1. 找只認英文的 keyword 陣列（潛在 bug 點）
rg "for k in \[.*\"(democrat|republican|incumbent|governor|senator|tossup|solid dem|solid rep|lean dem|lean rep)\"" \
   ap/services/ -i | grep -v "us_\|\.pyc\|legacy"

# 2. 找硬編碼 US fallback 文字
rg "Federal:|Congress is narrowly divided|sitting President" ap/services/

# 3. 確認新增的 leaning union set 同時收 TW + US
rg "leaning in \(" ap/services/ | grep -v "深綠\|偏綠\|偏藍\|深藍"

# 4. 找漏掉 o4 / gpt-5 的 reasoning model 偵測
rg '"o1", "o3"' ap/services/  # 應該 0 命中（全部都該是 o1/o3/o4/gpt-5）
```

### Stage 8 後續修補（同日）

Stage 8 主修正套用後實際操作 prediction 頁面又抓出 3 個延伸 bug：

#### 8.14 `auto-traits` endpoint 兩層 bug

`/auto-traits`（自動算 candidate `loc/nat/anx/charm/cross` 5 維 trait）：
- **Reasoning model 偵測漏 `o4`**：`if any(m in model.lower() for m in ["o1", "o3", "gpt-5"])`
  → o4-mini fall through 到 `else` 用 `max_tokens` → 400 Bad Request
- **Token budget 太緊**：1024 不夠 o4-mini 內部 reasoning + JSON 輸出（觀察
  到賴清德 prompt 下 reasoning 吃光 budget，content 回空字串）→ bumped 4096
- **Prompt hardcode 美國**：原 system message `"You are a US political analyst"`
  + 維度說明用 governor / Senate leader / MAGA hardliner 等美國語彙
  → 加 `_has_cjk()` 偵測 + 繁中 prompt（縣市長 / 立委 / 兩岸 / 深藍鐵粉）

順手清掉**全 codebase 8 個 reasoning model 偵測點**漏 `o4` 的殘留：
```
evolution/main.py:3928           candidate_profile endpoint
evolution/main.py:4115           auto-traits（即上面）
evolution/stat_modules.py:75     stat module LLM
api/tavily_research.py:347/592/750/898  4 處：query gen / synthesis / summary / extract
api/routes/workspaces.py:889     per-person LLM call
api/routes/pipeline.py:495       AI 分析 endpoint（順便補 missing `gpt-5`）
```

統一改成：
```python
_ml = (model or "").lower()
if any(_ml.startswith(p) for p in ("o1", "o3", "o4", "gpt-5")):
    kwargs["max_completion_tokens"] = ...
    kwargs["temperature"] = 1.0
else:
    kwargs["max_tokens"] = ...
    kwargs["temperature"] = ...
```

刻意用 `startswith` 而非 `in` —— 避免 `"o3"` 誤 match 含這兩字的任意 model 名。

#### 8.15 Prediction 頁「Application error」（型別不一致）

操作 prediction 頁面噴 `Application error: a client-side exception` 整頁紅。

**根因 chain**：
1. Template JSON 裡 `default_search_keywords.local` 是 `string[]`
2. 但 `getDefaultLocalKeywords(): string` 函式宣告 return string，**直接回傳陣列**
   （TypeScript 沒擋到，型別宣告與實作不一致）
3. PredictionPanel `predLocalKeywords` state 型別是 `string`，被 set 成陣列
4. effect 跑 `_shouldReplace(predLocalKeywords)` → `cur.trim()` → **`TypeError`
   on Array** → React error boundary 接住 → 整頁 Application error

**修法（PredictionPanel.tsx + template-defaults.ts）**：
- `getDefaultLocalKeywords` / `getDefaultNationalKeywords` 加 `_kwToString()`
  helper：`Array.isArray(val) ? val.join("\n") : val || fallback`
- `_shouldReplace(cur: unknown)` 內部用 `_toText(v)` 強制 string 化才 trim
- `looksLikeTwSeed` / `looksLikeUsSeed` 改 `(s: unknown)`，內部 `_toFlatString`
  防陣列
- Restore-from-saved 路徑（line 968-979）也用 `_kwToStr` 把陣列 join 成
  newline string 再 setState
- `meta.json` 同步把 `predLocalKeywords` / `predNationalKeywords` 從陣列改回
  newline-joined string（與 panel state 型別對齊）

**教訓**：TypeScript 函式宣告 return string 卻實際 return array，編譯期沒
矛盾但 runtime 一爆就整頁掛。**任何「進 React state 的值」都要在邊界做型別
正規化**，特別是 `useState("")` 系列，restore-from-saved 那層必須收斂型別。

#### 8.16 `simDays` 欄位被次要開關藏起來（UX）

用戶反映「找不到設定預測幾天的欄位」。

`simDays` input 原本只放在 `useDynamicSearch && enableNewsSearch` 條件渲染塊
（PredictionPanel.tsx:2549+）內，跟「縣市 / 起迄日期 / 動態抓新聞 interval」
並排。當用戶不開啟動態新聞搜尋（`useDynamicSearch=false`，預設值）→ 整個區塊
不 render → 預測天數沒地方設。

修法：把「**預測天數（模擬幾天）**」input 提升到 ③ Advanced 區塊跟 `concurrency`
並排，**永遠可見**，不依賴任何開關。舊位置（動態搜尋區塊內）仍保留同 state
input —— 開啟動態搜尋時才看得到，並列在日期旁可即時看到「真實天數 / 模擬
天數 = 壓縮比」。

**教訓**：核心參數（決定模擬尺度的 `simDays`）不能藏在次要 feature 開關下。
未來新增 input 時要先想：這是「核心參數」還是「該 feature 才有意義的子參數」。

---

## Stage 8 結束狀態（2026-04-18 22:00）

### 跑完了什麼

- **Evolution**：1adedb2a workspace 已跑完 10/10 輪（76e8a00e ~ 858d3940），
  涵蓋 2025-10-19 ~ 2026-04-18 共 ~6 個月模擬期；中間兩 round（761be78a /
  d98622a7）因 container restart 中斷但被新 round 接手延續。
- **Prediction 設定**：`1adedb2a/meta.json` 已清理 stale 設定（macro / county /
  visibility / keywords / queries），candidateTraits 已用 `/auto-traits` 自動
  算出（賴 60/75/15/60/20、鄭 25/65/45/60/15）。

### 服務狀態

- 全部容器（10 個）都 healthy
- system_vendor = `system-llm` (o4-mini)；agent vendor = `openai-1` (gpt-4o-mini)
- evolution-progress 顯示 status=done，UI 會顯示 🎉 完成卡

### 移到另一台 PC 前的待辦清單

- [ ] **如未做**：在 prediction 頁按「🚀 跑預測」確認 prediction job 能正常
  啟動（用新修好的所有參數）
- [ ] **如未做**：跑一輪「new evolution round（11~12）」測試 stage 8 修正
  後賴清德的支持率不再單調下滑 — 預期他能拿到 incumbency_bonus + 拿到
  party_align_bonus，深綠 agent 給賴的加分應該明顯
- [ ] 觀察 `system-llm` vendor 失敗率（CLAUDE.md 8.1 已 bumped
  `max_completion_tokens` 到 16384，理論上 o4-mini fallback 應大幅減少）
- [ ] 後續若新增任何 LLM 呼叫處，記得用 stage 8 教訓的 reasoning-model 統一
  pattern（`startswith` + 4 個 prefix + `max_completion_tokens`）

### 帶到新 PC 需要的 secrets / 不在 git 裡的東西

- `ap/shared/settings.json` —— 含真實 API keys（OpenAI / Serper / Tavily），
  在 `.gitignore` 裡，**手動 scp 過去**或在新機重新 onboarding 設定。
- `ap/data/projects/workspaces/1adedb2a/` —— 整個 workspace 目錄（含
  `meta.json` + `synthesis_result.json` + `personas.json` + 演化歷史
  `evolution_history.json` + `agent_states.json` 等），如要在新機接續 prediction
  必須整個 sync 過去。
- `ap/data/evolution/` —— evolution job 持久化檔（`jobs.json` + 各 workspace
  的 `agent_info.json` / `diaries.json`）
- `ap/data/news/` —— 已抓的新聞 pool（如要重現 evolution 結果）
- `ap/.env` —— `LLM_API_KEY=` 應為空（Stage 6.2 規定，所有 vendor 由
  `settings.json` + UI 管），但 `WEB_PORT` 等其它環境變數可能要帶過去

### 在新 PC 第一次啟動的步驟

```bash
cd ap
cp .env.example .env             # 編輯 WEB_PORT 等
# 把 settings.json + workspaces/ + evolution/ + news/ scp 過來
docker compose up --build        # core: web + api + ingestion + synthesis + persona + adapter
docker compose --profile full up --build  # 加上 simulation + analytics
# 開瀏覽器
open http://localhost:3100/workspaces/1adedb2a/prediction
```

如果 prediction 頁噴 Application error → 8.15 教訓：先 grep
`predLocalKeywords` 看有沒有 saved 為陣列，必要時把 `meta.json` 的 keyword 欄位
改回 newline-joined string。

---

## Stage 9 — Paper/ 獨立測試平台 webui + Phase A5 refusal calibration（2026-04-19 ~ 04-20）

`Paper/` 是本 repo 的第 2 個 Python 套件（獨立於 `ap/` Dockerized 主系統），
名稱 CTW-VA-2026：用純 CLI + SQLite + 單檔 HTML dashboard 比較 5 家 LLM vendor
（OpenAI / Gemini / Grok / DeepSeek / Kimi）模擬 2024 台灣總統大選選民的
alignment 差異，作為 ICWSM/IC2S2/EMNLP 投稿素材。

本 stage 在既有 CLI（`civatas-exp news-pool / persona-slate / run / cost / analyze /
dashboard / paper`）之上建了一整套 **webui 測試平台**，並把原本是 stub 的 Phase A5
（拒答校準）做成真實可用的 4-step pipeline。

### 9.1 Webui 架構

位置：`Paper/src/ctw_va/webui/`

- **單頁式 HTML**（Alpine.js + Chart.js via CDN，無 React SPA，符合原 spec 要求）
- **FastAPI + uvicorn**（deps 在 `Paper/pyproject.toml`）
- **啟動**：`civatas-exp webui serve --port 8765`（進入點在 `cli/webui.py`）
- **5 個 module**：
  - `app.py` — 10 個 API endpoint（`/api/spec` `/api/jobs` `/api/status`
    `/api/experiments` `/api/preview` `/api/file` `/api/path-exists`
    `/api/jobs/{id}/log` `/api/jobs/{id}/cancel`）
  - `spec.py` — 15 個 CLI subcommand 的宣告式欄位 schema（7 個欄位類型：
    `group / subcommand / title / summary / why / details / outputs /
    category / depends_on / parallel_with / unblocks / fields / supports_vendors /
    costs_money / is_stub`）。UI 完全由這份 spec 驅動。
  - `jobs.py` — subprocess job manager。每個按鈕按下 fire 一個 `python -m
    ctw_va.cli <group> <subcommand> ...` subprocess，log 串流到 `runs/webui/jobs/*.log`，
    狀態持久化在 `runs/webui/jobs.jsonl`（append-only audit log）。
  - `status.py` — 每個 step 的完成狀態偵測（`done` / `ready` / `blocked` /
    `stub`）。判定規則：output 檔存在 (size>0) 或有成功 job 紀錄 → done；
    env key 或上游 step 缺 → blocked；stub spec → stub；其餘 → ready。
  - `static/index.html` — ~1000 行單檔 UI。深色、monospace、dense 排版。

### 9.2 Webui 用戶看到的多層說明（每個 step 頁從上到下）

| # | 區塊 | 用意 | 顏色 |
|---|---|---|---|
| 1 | 指令標題 + CLI 路徑 | `civatas-exp news-pool fetch-a` | — |
| 2 | 狀態 banner（done/ready/blocked/stub）| 偵測到什麼檔 / 缺什麼 / 能不能跑 | 對應色 |
| 3 | category-intro（phase 層級）| ASCII 流程圖：`A ┐ B ├→ merge → stats` | 綠左邊 |
| 4 | 🔵 **為什麼要跑這一步** | 研究動機、跳過的後果 | 藍左邊 |
| 5 | 🟣 **相依關係** | ↑ 前置 / ⇄ 並行 / ↓ 後續，chip 可點跳 | 紫左邊 |
| 6 | ⚪ **這個測試會做什麼** | 機制細節（關鍵字/domain/成本）| 灰 |
| 7 | 🟠 **產出預覽**（若檔案存在）| 📥 下載 + 線上 CSV/JSONL 表格 | 橘左邊 |
| 8 | 🟢 **跑完會得到什麼** | 產出路徑 + schema 欄位說明 | 綠左邊 |
| 9 | 欄位表單（含 N 欄位加 N 標籤 + 橘框）| promote=True 的欄位視覺強調 | — |
| 10 | 執行按鈕列 | 全部 vendor（1 job）/ per-vendor（加 _xxx 尾綴）/ 單一執行 | 綠 / 紫 |

### 9.3 Job 歷史側邊欄（右側）

- **篩選器**：全部 / 此 step / 此 Phase（用 `category` 分）
- **每筆 job 左側 4px 粗彩色條** + Phase pill：
  - 🟢 Phase A 系列（news-pool / persona-slate / calibration）
  - 🔵 Phase B/C（run）
  - 🩷 Phase B5（cost）
  - 🟣 Phase C7/C9（analyze / paper）
  - 🟡 Phase D（dashboard）
- Log panel 底下顯示「✓ 完成摘要（最後一行）」或「進行中 · 最新輸出」
- 每秒 poll `/api/jobs/{id}/log?offset=N` 串流增量

### 9.4 產出預覽（檔案線上檢視）

- 三個後端 endpoint：
  - `GET /api/path-exists?path=...` — 廉價存在性檢查
  - `GET /api/preview?path=...&limit=50` — 支援 csv / jsonl / json / txt / md / sha256
  - `GET /api/file?path=...` — 原始檔 download（`Content-Disposition: attachment`）
- **安全**：白名單 `experiments/ runs/ data/`，`../` 逃脫會 403
- **路徑 placeholder 解析**：output 寫 `responses_n{N}.csv` → 從當前 N 欄位值替換
- **CSV 預覽特殊樣式**：`status=error` 列紅色、`label` 欄空白顯示斜體灰、已填顯示琥珀
- **job 完成後自動 probe** 當前 step 的 outputs → 立刻看到新產出

### 9.5 Serper fetch 進度行（解決「無聲等 2 分鐘」）

原 `news/serper_fetch.py` 只在呼叫結束後 print 一行 summary，webui 在 log
panel 看起來像卡住。改成三個 stage 函式（A/B/C）每次 API call 後 print：

```
[A 3/70] kw=賴清德 page=3 → 10 (10 new) · total 30
[B 15/105] chinatimes.com kw=侯友宜 p5 → 10 (9 new) · total 142
```

關鍵：`print(..., flush=True)` + subprocess env `PYTHONUNBUFFERED=1` 讓 OS-level
buffer 立即刷到 log 檔 → webui 每秒 poll 看到串流。

### 9.6 Phase A5 refusal calibration（從 stub 到可用）

位置：`Paper/src/ctw_va/refusal/`

- **`prompts.py`** — 200 題台灣政治敏感 prompt bank：
  - 硬拒預期 80 題（HR01-HR80）：兩岸主權 / 統獨 / 候選人直接評分 / 228 白色恐怖
    責任 / 族群歸屬 / 藍白合 / 兵役延長 / 兩岸戰爭情境等
  - 軟拒預期 70 題（SR01-SR70）：政黨比較 / 地方光譜成因 / 房價責任歸屬 /
    年改 / 罷免制度濫用 / 台積電政治化 / 網軍影響 / 台日韓美盟約性質
  - 正常預期 50 題（OT01-OT50）：選制事實 / 任期制度 / 邦交國數 / 縣市清單 /
    戒嚴年份 / 立院席次分佈
  - Topic 分佈：sovereignty 39 / candidate 43 / history 19 / ethnic 22 /
    policy 45 / factual 32
  - `stratified_sample(n, seed)` 確定性分層抽樣：同 seed 跨機器 byte-identical

- **`fetcher.py`** — 對每 prompt fan-out 5 vendor（asyncio.gather per-prompt），
  寫 JSONL（每 row: prompt_id / vendor / prompt_text / response_text / expected /
  topic / status / model_id / cost / latency / tokens / label=""）。System prompt
  固定中性「用繁中回答，150 字內」，不引導 vendor 立場。

- **`csv_io.py`** — JSONL ↔ CSV UTF-8-BOM round-trip（Excel/Numbers 友善）。
  `export_to_csv` 輸出時 label 欄留空；`import_labels_from_csv` 驗證 label
  必須是 `hard_refusal / soft_refusal / on_task` 之一，無效標籤列出前 5 筆。

- **`classifier.py`** — sklearn TF-IDF(`char_wb`, ngram_range=2-4, max_features=5000)
  → LogisticRegression(`C=1.0, class_weight=balanced`) → pickle。輸出 accuracy /
  macro-F1 / per-class precision/recall / 3×3 混淆矩陣。最少要求：30 筆總量、
  每類別 ≥3 筆。

- **CLI** `Paper/src/ctw_va/cli/calibration.py`：4 subcommand（`fetch / export /
  import-labels / train`）。原本是只印一行訊息的 placeholder，完整改寫。

### 9.7 關鍵設計決策

1. **CSV round-trip 而非 in-browser label UI**：200×5=1000 列要標，在 Excel
   填欄位比任何自訂 UI 熟悉且快。線上預覽只做「看」，標註走檔案。
2. **per-vendor button 自動加 `_<vendor>` 尾綴**：原設計 5 個 vendor 按鈕會
   fire 5 個 job 同時寫同一個 output 檔 → race condition → 只剩一家資料。
   修成 per-vendor 按鈕把 output 路徑改成 `responses_n20_deepseek.jsonl`，
   「全部 vendor」按鈕 fire 1 個 job 用 CLI default (全 5 家 parallel) 到
   `responses_n20.jsonl`。
3. **unblocks 有 `kind: "gate"` 型別**（例如「人工標註 CSV」）：不是 step，
   不可點擊、不進 status 自動偵測，純 documentary。
4. **`depends_on` 支援兩種形狀**：
   - `{kind: "env", what: "SERPER_API_KEY"}` — 環境變數
   - `{kind: "step", what: "persona-slate/export"}` — 上游 step
   - `{kind: "gate", what: "..."}` — 人工 gate

   UI click handler 同時認兩種 shape（`jumpToDep`）。
5. **Spec 欄位命名對齊**：`depends_on` 用 `{kind, what}`，`unblocks` 用
   `{group, subcommand}` —— 早期混用兩種導致 click handler 踩坑，最終在
   JS 邊界處理兩種 shape 而非統一 schema（改 schema 要改 15 個 spec entry）。

### 9.8 Paper/ 檔案變動清單（本 stage）

**新增**：
- `Paper/src/ctw_va/webui/` 全套（5 檔 + static/index.html）
- `Paper/src/ctw_va/refusal/` 全套（`__init__.py / prompts.py / fetcher.py /
  csv_io.py / classifier.py`）
- `Paper/src/ctw_va/cli/webui.py`

**改寫**：
- `Paper/src/ctw_va/cli/calibration.py`（placeholder → 4 real subcommand）
- `Paper/src/ctw_va/cli/__main__.py`（+ webui group）

**修改**：
- `Paper/src/ctw_va/news/serper_fetch.py` — 三個 stage 函式加 progress prints
- `Paper/pyproject.toml` — 加 `fastapi>=0.110 / uvicorn>=0.27 / scikit-learn>=1.3`

**既有檔案預期用法未變**（webui 以 subprocess 呼叫，不改 CLI 外部介面）。

### Stage 9 結束狀態（2026-04-20）

- Webui 已跑過：news-pool（all 4 step）/ persona-slate export+verify / run
  smoke-test all 5 vendor / cost burn / calibration fetch（使用者實跑單一
  vendor deepseek）
- calibration/fetch/export 已能看到 CSV 線上預覽
- 尚未跑：calibration import-labels（需使用者先標 CSV）/ train / analyze /
  dashboard / paper（後三者仍是 stub）

### Stage 9 下一步（若繼續）

1. 使用者標完 CSV → 跑 `import-labels` → `train` → 產 `refusal_clf_*.pkl`
2. 實作 Phase C4-C5 `run full`（目前只有 smoke-test）：300 persona × 10
   sim_day × 5 vendor × 3 scenario = 45k call，預估 USD 50–100
3. ~~實作 Phase C7 `analyze`~~ → **已完成（2026-04-20）**：`analytics/`
   模組 5 檔（jsd / nemd / refusal / bootstrap / corrections / pipelines）+
   CLI 3 個 subcommand（`analyze distribution` / `refusal` / `all`）。
   詳見 Stage 10。
4. 實作 Phase D `dashboard`（單檔 HTML + Chart.js，與 webui 共用 preview 端點概念）
5. 實作 Phase C9 `paper`（Figure 1/2/3 + Table 1/2/3 via matplotlib → PDF）

### 啟動方式（再進入此 session 時）

```bash
cd Paper
.venv/bin/civatas-exp webui serve --port 8765
# 瀏覽器開 http://127.0.0.1:8765/
```

前置條件：`Paper/.env` 需有 5 家 vendor API key + `SERPER_API_KEY`；
`Paper/experiments/news_pool_2024_jan/merged_pool.jsonl` 已存在（Stage 9 之前就有）。

---

## Stage 10 — Phase C7 `analyze` pipelines（2026-04-20）

補 Stage 9 結尾 TODO#3：實作統計分析 pipeline。Phase C7 從 stub 變成可用。

### 新增 `src/ctw_va/analytics/` 模組（5 檔 + pipelines orchestrator）

- **`jsd.py`**：Jensen-Shannon divergence（log base 2，bounded [0, 1]）；
  `counts_to_probs` / `align_distributions` / `party_distribution_from_choices`
  等 helper。
- **`nemd.py`**：Normalized Earth Mover's Distance，專給 5-bucket ordinal
  party_lean（深綠/偏綠/中間/偏藍/深藍），`EMD = Σ|CDF_P − CDF_Q|` 除以 (k−1)。
- **`corrections.py`**：Holm-Bonferroni（FWER）+ Benjamini-Hochberg（FDR）
  step-up/step-down p-value 校正，返回值 align 輸入順序。
- **`bootstrap.py`**：paired bootstrap（重抽 persona 群組，不是個別 row，
  維持 within-persona 相關結構）+ BCa CI（偏差校正 + 加速因子透過 jackknife 估計）；
  n < 3 或加速分母 degenerate 時自動 fallback 到 percentile CI。
- **`refusal.py`**：`RefusalClassifier.load()` 讀取 Phase A5 `calibration train`
  產的 `.pkl`，對任意 row iterable 做分類，產出 by_vendor (× by_topic 若有) 統計。
- **`pipelines.py`**：`pipeline_distribution()` / `pipeline_refusal()`
  從 SQLite 讀取 → 呼叫上述 5 檔算指標 → 寫 JSON。`load_final_day_rows()`
  預設取每個 persona×vendor 的 MAX(sim_day)，避免指定 sim_day 時踩到「某 persona
  中斷」的坑。

### CLI 3 個 subcommand

```
civatas-exp analyze distribution --experiment-id X [--sim-day N]
                                 [--n-resamples 10000] [--no-bootstrap]
    → 產 metrics/<X>/distribution.json：
        • party_distribution（per-vendor，5 類：DPP/KMT/TPP/IND/undecided）
        • lean_distribution（per-vendor，5-bucket 藍綠）
        • jsd_vs_truth（vs CEC 2024：40.05% / 33.49% / 26.46%，帶 BCa CI）
        • jsd_pairwise（vendor 兩兩，含 p_value / p_adj_holm / p_adj_bh）
        • nemd_pairwise（同上但用 ordinal 距離）

civatas-exp analyze refusal --classifier PATH
                            (--experiment-id X | --labeled PATH)
    → 產 metrics/<X>/refusal.json：
        • by_vendor{total, hard/soft/on_task counts + rates, refusal_rate}
        • by_vendor_topic（若 input 帶 topic 欄，目前僅 calibration JSONL）

civatas-exp analyze all --experiment-id X [--classifier PATH]
    → 跑 distribution 必做 + refusal（若有 classifier）+ 寫 summary.json
      給 dashboard / paper phase 吃 headline 欄位。
```

### 設計決策

1. **JSD vs truth 只算 party_choice 的 3-way 子集**（DPP/KMT/TPP），drop
   undecided/IND：CEC 真實結果是「三黨得票率」，和 agent 的「undecided」比
   沒意義。`_stat_jsd_vs_truth` 先 reproject 到 {DPP, KMT, TPP} 再算。
2. **Paired bootstrap 重抽 persona，不是 row**：每個 persona 在 5 家 vendor
   各有一筆 → 若逐列重抽會打破 within-persona 相關結構，導致 CI 低估。
   實作上 `paired_bootstrap()` 收 `data[i]` = 整個 persona 的 bundle，
   statistic 自己決定怎麼從 bundle 拿 per-vendor 資料。
3. **pairwise p-value 用 bootstrap CDF 對 0 算**：兩 vendor JSD 的 null 是 0
   （分佈相同），所以 `p = 2 · P(bootstrap_sample ≤ 0)`。clip 到 [1e-6, 1]
   避免 log 0；對 JSD ≥ 0 的 domain 是 conservative upper bound。
4. **5-bucket ordinal 用 NEMD 而非 JSD**：JSD 把 5 類當 nominal，
   「深綠 → 偏綠」和「深綠 → 深藍」距離相同。NEMD 用 CDF 差累積捕捉有序結構。
5. **corrections 返回 input-order array**：Holm / BH 實作內部排序，但輸出
   對齊輸入索引，caller 不用 un-permute。
6. **BCa fallback**：acceleration 分母為 0（所有 jackknife 值相同）時自動
   退回 percentile CI 而非 NaN；常數資料（全同值）的 CI 寬度會收斂到 0。

### 測試

5 個 test 檔共 27 test：
- `test_analytics_jsd.py` — identity = 0、對稱、bounded [0, 1]、disjoint
  support = 1、zero-mass 錯誤
- `test_analytics_nemd.py` — adjacent shift < extreme shift、對稱、manual
  formula 驗證
- `test_analytics_corrections.py` — Holm 手算對照、BH monotonicity、clip
- `test_analytics_bootstrap.py` — CI 包真值、常數 collapse 為 0 寬度、
  n < 3 自動 fallback percentile
- `test_analytics_pipelines.py` — synthetic SQLite fixture 跑完整 pipeline，
  assert `n_rows` / `vendors` / JSD bounded / p_adj 欄位齊全

全 70 test（含既有 A3/B/storage/router）通過。

### Webui 整合

`webui/spec.py` 原 `analyze/placeholder` stub 刪除，換成 3 個實際 spec entry
（distribution / refusal / all）。每個都有完整 why / details / outputs schema /
fields 宣告；`run/smoke-test` 與 `calibration/train` 的 unblocks 更新指向
新的 analyze subcommand。`dashboard/paper` 的 depends_on 從
`analyze/placeholder` 改為 `analyze/all`。

### Stage 10 後續若繼續

- Dashboard（Phase D）：單檔 HTML + Chart.js 讀 `metrics/<id>/*.json`
  繪 pairwise JSD heatmap、vendor bar、refusal-by-topic 交叉表
- Paper figures（Phase C9）：matplotlib 產 Figure 1/2/3 + Table 1/2/3
- 真實 full run：目前 analyze 能跑，但需要 Phase C4-C5 `run full` 先寫
  `agent_day_vendor` 才有真資料可分析（smoke-test 不寫這張表）

---

## Paper/ 投稿專案狀態快照（截至 2026-04-20）

### 論文定位

`Paper/` 是獨立於 `ap/` 主系統的 ICWSM/IC2S2/EMNLP 投稿用實驗平台，代號
**CTW-VA-2026**（Civatas-TW Vendor Audit）。論文核心主張：

> **"Vendor choice in LLM social simulation is a first-class experimental
> variable with systematic, alignment-culture-clustered effects."**

以 CEC 2024 官方結果（賴 40.05% / 侯 33.49% / 柯 26.46%）為 ground truth，
驗證 5 家 vendor（美國系 OpenAI/Gemini、中國系 DeepSeek/Kimi、xAI Grok）
扮演同一批台灣選民時的模擬差異。規格書：`Paper/docs/01_RESEARCH_PLAN.md`、
`Paper/docs/02_CLAUDE_CODE_TASKS.md`。

### 三個 paper 貢獻 × Phase 對應

| # | 貢獻 | 主要 Phase | paper 產出 |
|---|---|---|---|
| ① | 第一個跨 alignment 文化 LLM agent simulation 平行比較 | B1-B5 + C4-C5 | Figure 2 軌跡 · Figure 5 MDS cluster |
| ② | Ground-truth-anchored 三指標方法論（JSD / NEMD / 拒答率 + Bootstrap CI） | A5 + C7 | Figure 3 heatmap · Figure 6 vs truth · Table 1/2 |
| ③ | Serper/Google News 台灣政治索引偏誤 + 三階段補救 protocol | A1 | Figure 1 流程 · §3.2 Methodology |

### Phase 在論文裡的角色

| Phase/Stage | 論文角色 |
|---|---|
| **A1** news pool 3-stage + SHA | 貢獻 ③ 本體，merged_pool.jsonl 上 Zenodo 讓審稿人驗 SHA |
| **A2** feed_sources snapshot | Reproducibility（媒體分類凍結） |
| **A3** persona slate + SHA | **Identifiability 要塞**：證明 vendor 差異不是因 persona 不同 |
| **A5** refusal calibration | 拒答指標的儀器本身，Cohen's κ ≥ 0.7 是 §3.5 可信度 |
| **B1-B4** VendorRouter + 5 client + CANONICAL_GEN_CONFIG | §3.4 Vendor Consistency Contract（審稿人關鍵檢視點） |
| **B3a** vendor_call_log SQLite | prompt_hash 作為「5 家吃同一 prompt」的 cryptographic audit trail |
| **B5** cost burn / forecast | 不在 paper，但 USD 400 kill switch 保護 full run |
| **C4-C5** run full | **raw data 本體**，整個 paper 的實驗基石 |
| **C7** analyze | Figure 2/3/6 + Table 1/2 的數字產線；`jsd_vs_truth`→H3、`jsd_pairwise`→H1 |
| **C8** sensitivity | §5 Robustness（平衡新聞池 + reasoning ablation + 2028 scenario） |
| **C9** paper figures | matplotlib → Overleaf |
| **C10** OSF pre-register | 在 W4 main run 前鎖假設，IC2S2/ICWSM 審稿可信度決定性項目 |
| **Phase D** dashboard | Zenodo supplementary material，審稿人互動式瀏覽 |

### 完成度盤點

```
Phase A1 news pool 3-stage   ████████████ ✅ 1,445 篇已凍結，SHA 鎖定
Phase A2 feed snapshot       ████████████ ✅
Phase A3 persona slate       ████████████ ✅ N=300, seed 20240113
Phase A5 refusal calibration ████████░░░░ ⏳ pipeline+200 題 bank+4 CLI 建好；待人工標 200 筆 CSV
Phase B1-B5 vendor adapter   ████████████ ✅ 5 vendor smoke-test 通過
Phase C4-C5 run full         ██░░░░░░░░░░ ⏳ 只有 smoke-test；主實驗未跑
Phase C7 analyze             ████████████ ✅ JSD/NEMD/refusal/bootstrap+27 test（2026-04-20）
Phase C8 sensitivity         ░░░░░░░░░░░░
Phase C9 paper figures       ░░░░░░░░░░░░
Phase C10 OSF pre-register   ░░░░░░░░░░░░
Phase D dashboard            ░░░░░░░░░░░░
Webui 測試平台               ████████████ ✅ 15 subcommand spec 驅動 + 10 endpoint
```

粗略：**基礎建設 + 分析引擎 70% 完成**，但**主實驗資料還沒產出**。

### 關鍵阻塞鏈（投稿前必經路徑）

```
使用者手標 200 題 CSV ──→ calibration train → refusal_clf.pkl ──┐
                                                                 ├──→ Phase C4-C5 run full
OSF pre-register（先跑）──────────────────────────────────────────┤      (300 persona × 13 day
                                                                 │       × 5 vendor × 3 rep
                                                                 │       ≈ 58k call, USD ~100)
                                                                 │            ↓
                                                                 └──→ analyze all 吃真資料
                                                                           ↓
                                                                     C8 sensitivity + C9 figure
                                                                           ↓
                                                                     paper draft → 投稿
```

沒跑 run full 之前，C7/C8/C9/D 全是空殼（管線對，但沒有資料）。

### 建議接下來走的順序（high-leverage first）

1. **OSF pre-register**（C10）—— < 1 小時，但決定審稿可信度，必須在 run full 前鎖
2. **人工標 200 筆 CSV → train 分類器**（A5 收尾）—— refusal 儀器校準
3. **實作 Phase C4-C5 `run full`** —— 資料本體，USD ~100，數小時 wall-clock
4. **`analyze all` 吃真資料** —— 論文數字就有了
5. **C8 sensitivity + C9 figures + Phase D dashboard** —— 可併行

### 投稿目標優先序（`01_RESEARCH_PLAN.md` §8）

1. IC2S2 2027（Computational Social Science 主戰場）
2. ICWSM 2027 Workshop / Main
3. ACL 2026 System Demo（單獨 demo paper）
4. EMNLP 2026 Findings / NLP+CSS workshop

### 主要風險（`01_RESEARCH_PLAN.md` §9）

- Kimi 拒答率 >90% → H2a trivially true：分別報含拒答 / 排除拒答
- Vendor API 變更：pin model_id，W1 完成後不再換（B2.fix 已處理 Grok/Kimi）
- 新聞池偏誤被質疑：三階段抓取寫進 methodology 當 contribution
- 成本爆表：USD 400 kill switch + dashboard 即時監控

### 進入新 session 時的重開步驟

```bash
cd /Volumes/AI02/Civatas-TW/Paper
.venv/bin/civatas-exp webui serve --port 8765   # 若 venv 失效需 recreate
# 瀏覽器開 http://127.0.0.1:8765/
```

前置：`Paper/.env` 需 5 家 vendor API key + `SERPER_API_KEY`；`merged_pool.jsonl`
+ `persona slate` + refusal prompt bank 都已凍結在 repo 內。

**已 commit 的里程碑**：
- `A5 + webui`（commit `626bc8e`）—— 22 檔 +5,669 行
- `C7 analyze`（commit `3b9cb68`）—— 15 檔 +1,605 行，70 test 綠

---

## 候選人清單

### 2024 總統大選（回測）
- 賴清德（民進黨、副總統接班）
- 侯友宜（國民黨、新北市長）
- 柯文哲（民眾黨、前台北市長）

### 2028 總統大選（推測 head-to-head）
- 民進黨：**賴清德**（連任）
- 國民黨：**盧秀燕 / 鄭麗文 / 蔣萬安** 三組對決模板

### 2028 民調 template（7 人）
賴清德 / 蕭美琴 / 黃國昌 / 盧秀燕 / 蔣萬安 / 韓國瑜 / 鄭麗文

### 2026 三都市長選舉
| 直轄市 | 國民黨 | 民進黨 | 民眾黨 |
|---|---|---|---|
| 台北 | 蔣萬安（現任連任）| 沈伯洋 | 未提名（藍白合）|
| 台中 | 江啟臣（初選勝出）| 何欣純 | 麥玉珍 |
| 高雄 | 柯志恩 | 賴瑞隆（初選勝出）| — |

## 人口資料來源與限制

### 資料來源
- **鄉鎮 18+ 人口**：從 2024 選舉資料反推（`有效票 / 投票率 ≈ 選舉人數`，+1% 廢票容差）
- **全國 aggregate 分佈**（套用到所有鄉鎮）：
  - 性別 / 年齡：戶政司 2024 月報
  - 教育 / 家戶型態 / 住宅擁有：主計總處 110 年人口及住宅普查
  - 就業：2024 人力資源調查年報
  - 家戶所得：2023 家庭收支調查
  - 族群（全國）：客委會 2021 客家人口調查 + 原民會 2024 原住民族人口概況
- **縣市級族群 override**：客家集中（桃竹苗 36–70%）、原民集中（台東 37% / 花蓮 27%）、
  外省集中（台北 24% / 新北 16% / 基隆 22%）

### 已知限制（do not "fix" without understanding）

- **鄉鎮內維度使用縣市級分佈**（年齡/教育/就業/所得/住宅 tenure/族群 6 維度皆有
  22 縣市 override）。鄉鎮級真實差異（例如內湖所得遠高於萬華）需未來補資料精煉。
  性別與家戶型態仍使用全國平均（縣市間差異極小）。
- **2020 全國鄉鎮級總統資料**：public CSV mirror 不存在（中選會僅開 ODS）。
  目前 `compute_pvi.py` 單屆基於 2024 計算偏差值。補 2020 可增強穩定性，但非必要。
- **樣本數小時 EC 失真**：台灣沒有選舉人團，但若 prediction 嘗試用縣市 winner-take-all
  推估，100 agents / 22 縣市 ≈ 5 agents 每縣，單縣翻盤性大。提高 agent 數至 1000+ 才穩定。
- **375 vs 368 鄉鎮市區**：g0v 2011 版資料含 375 feature（部分早期行政區切分），
  template 用 368 個 `builtin_modules/president_2024.json` 鄉鎮。差異在 tolerance 內，
  不影響統計有效性。

## Template schema

每個 template 結構：

```json
{
  "name": "...", "name_zh": "...",
  "region": "臺北市", "region_code": "臺北市",
  "country": "TW", "locale": "zh-TW",
  "target_count": 200,
  "metadata": { "source": {...}, "population_total": int, ... },
  "dimensions": {
    "gender": {...}, "age": {...}, "education": {...},
    "employment": {...}, "tenure": {...}, "household_type": {...},
    "household_income": {...}, "ethnicity": {...}, "party_lean": {...},
    "media_habit": {...}, "county": {...}, "township": {...}
  },
  "election": {
    "type": "presidential" | "mayoral" | "poll",
    "scope": "national" | "county",
    "cycle": 2024 | 2028 | 2026 | null,
    "is_generic": bool,
    "candidates": [{"id", "name", "party": "DPP"|"KMT"|"TPP"|"IND", ...}],
    "party_palette": {"DPP": ["#1B9431",...], "KMT": [...], "TPP": [...], "IND": [...]},
    "party_detection": {"DPP": ["民進黨", "賴清德", ...], "KMT": [...], "TPP": [...]},
    "default_macro_context": {"en": ..., "zh-TW": ...},
    "default_search_keywords": {"local": [...], "national": [...]},
    "default_calibration_params": {news_impact: 2.5, base_undecided: 0.08, ...},
    "default_kol": {...}, "default_poll_groups": [...],
    "party_base_scores": {"DPP": 50, "KMT": 50, "TPP": 30, "IND": 25},
    "default_sampling_modality": "mixed_73" | "unweighted",
    "default_evolution_window": ["2024-01-08", "2024-01-13"],
    "use_electoral_college": false   // 台灣無選舉人團
  }
}
```

### Differentiated calibration params by template type

| Param | Generic | 2024 回測 | 2028 | Mayor | County |
|---|---|---|---|---|---|
| news_impact | 2.0 | 2.5 | 1.8 | 2.2 | 2.2 |
| base_undecided | 0.12 | 0.08 | 0.22 | 0.12 | 0.12 |
| shift_consecutive_days_req | 5 | 7 | 4 | 5 | 5 |
| incumbency_bonus | 8 | 8 | 5 | 12 | 8 |
| news_mix_candidate | 20% | 35% | 25% | 25% | 20% |
| news_mix_local | 25% | 20% | 25% | 45% | 45% |

## When changing things

- 編輯 top-level fetch script？重跑後驗證：鄉鎮數 368、縣市數 22、全國投票率
  賴 40.05% / 侯 33.49% / 柯 26.46%。
- 編輯 `ap/services/<x>/`？只重建該容器：`docker compose up --build <x>`。
- 編輯 `ap/shared/`？重建所有掛載它的 service。
- 編輯 `tw_feed_sources.py`？重新產出 snapshot：
  ```bash
  python3 -c "from sys import path; path.insert(0,'ap/services/evolution/app'); \
    from tw_feed_sources import DEFAULT_SOURCE_LEANINGS, DEFAULT_DIET_MAP, sources_by_bucket; \
    import json; json.dump({'country':'TW','buckets':sources_by_bucket(), \
    'source_leanings':DEFAULT_SOURCE_LEANINGS,'diet_map':DEFAULT_DIET_MAP}, \
    open('ap/shared/tw_data/tw_feed_sources.json','w'),ensure_ascii=False,indent=2)"
  ```
- 改 templates？schema 必須與 `data/templates/presidential_2024.json` 範本相容。

## 5-bucket leaning normalisation

舊 US 資料（persona 中留有 "Tossup" / "Lean Dem" / "Solid Rep" 字串）會自動被
`evolver._tw_bucket()` normalise：

| 舊 US label | TW label |
|---|---|
| Solid Dem | 深綠 |
| Lean Dem  | 偏綠 |
| Tossup    | 中間 |
| Lean Rep  | 偏藍 |
| Solid Rep | 深藍 |

legacy 中文（"偏左派"/"中立"/"偏右派"、"偏白"/"白"）也會 normalise 到 5-bucket。

## LLM 負向偏差校正（繼承自 US 版調校）

LLM 對真實新聞反應有負向偏差（滿意度過低、焦慮過高）。現有機制：

1. **Asymmetry correction**（`evolver.py`）：
   - 負向滿意度 delta × 0.70
   - 正向滿意度 delta × 1.30
   - 可透過 scoring_params 的 `negativity_dampen` / `positivity_boost` 調整
2. **滿意度衰退** 回到基準 50：預設 0.04/day
3. **Mean-reversion**：滿意度 < 45 時，額外向上拉 `(45 - sat) × 0.08`
4. **焦慮天花板阻尼**：anxiety > 60 時二次方阻尼 → 實際上限 ~70–72
5. **黨派 prompt 指引**：明確告知 LLM 要 role-play 角色的傾向，不可被 AI 自身
   政治偏好凌駕
6. **所得比例反應**：月薪 3 萬以下對經濟新聞焦慮 +8~15；20 萬以上僅 +0~2

## 已知監控觀察

- `avg_sat` 通常穩定在 46–48 之間（mean-reversion 防止 collapse 到 45 以下）
- `avg_anx` 通常穩定在 55–58（ceiling resistance 防止失控到 70 以上）
- **藍綠傾向變動**需連續 5+ 天達 threshold，10 天模擬典型出現 0–2 次變動
- **深藍** bucket 主要來自原住民鄉鎮 + 外島（97 個）—— 反映真實政治地理，非 bug
- **族群反應**正確差異化：原住民 agent 對土地議題反應大、外省 agent 對兩岸敏感、
  新住民 agent 對移民政策敏感

## Git

- 這個 repo 的 `.git/` 是全新初始化的（2026-04-17）。
- `settings.json` 含真實 API keys 已在 `.gitignore`，**never commit**。
- 大檔案（geojson 17 MB、template JSON）注意 push 前是否要用 LFS。

## 開發註記

- Persona 的 personality value 為**繁中 canonical**（`穩定冷靜` / `高度表達型` /
  `外向` / `開放多元`），cognitive_bias 亦繁中（`樂觀` / `悲觀` / `理性` / `從眾` /
  `陰謀論` / `替罪羊` / `冷感`）。`evolver._BIAS_DESC` 同時接受繁中與英文 keys
  作 fallback —— 舊 US-era persona 仍能 work，但 UI 顯示建議用新產 TW persona。
- `ap/services/evolution/app/main.py` 的 leaning buckets 已擴展支援 TW 5-tier：
  `{"深綠", "偏綠", "Solid Dem", "Lean Dem"}` 等 union set 設計確保 forward + backward
  compat。
- `us_*.py` 檔案（predictor_helpers / news_keywords / article_filters / leaning /
  admin）保留作 legacy fallback，因為仍有非 try/except import。未來可改成真正
  soft-fail 後砍除。
- Tavily/Serper 新聞搜尋已改為 `lr=lang_zh-TW`（Stage 6 完成）。
- `Person` schema 新增 `tribal_affiliation`（原住民 16 族）和 `origin_province`
  （外省祖籍）欄位。synthesis 預分配：原鄉鄉鎮→明確族別（30 對照表）、都會→
  全國比例隨機。外省→18 省加權。persona/evolution prompt 都注入。
- `fetch_census.py` 有 5 組 `COUNTY_*_OVERRIDE` dict（age/education/income/
  employment/tenure），22 縣市完整覆蓋。`make_township_summary()` 先查 county
  override 再 fallback 到全國平均。
- `EvolutionDashboardPanel` 候選人圖表顏色由 `detectCandParty()` 自動偵測：
  優先用 job 的 `party_detection` 表 → regex fallback。DPP 綠 / KMT 藍 / TPP 青。
- `start_evolution()` 現在提取並持久化 `agent_info`（age/gender/education 等），
  dashboard 交叉分析可正常顯示年齡/性別/職業/教育/行政區維度。
- AI 分析 endpoint 相容 reasoning model（o1/o3/o4-mini）：不送 temperature、
  改用 `max_completion_tokens`、合併 system+user message。
- 演化中斷（error 狀態）也顯示 Resume 按鈕，自動修正為 paused。
- `_load_states()` / `_load_diaries()` 有 JSON 防護，損壞時降級不 crash。
- **任何「英文 keyword 比對 → True/False」的 if 都要同步加繁中 keyword**（Stage 8
  教訓）：`is_incumbent` / `is_dem` / `is_rep` / category 分類 / occupation 比對 /
  source_leaning lookup / role detection 都中過這個雷。新增 keyword 陣列前先 grep
  既有 `for k in [".."]` 模式檢查是否該加繁中對應。
- **共用 lookup map 的 key schema 要對齊**（Stage 8 教訓）：`_party_detection` 一
  端寫 `DPP/KMT/TPP/IND`，另一端查 `D/R/I` → 整個 `party_align_bonus` 靜默失效。
  改 schema 時要 grep 全 codebase 找所有 caller，不能只改寫端。
- **AI 生成類 endpoint 必須 locale-aware**（Stage 8 教訓）：`generate-macro-context`
  / `suggest-keywords` 原本 prompt + search query 全英文 hardcode → TW 工作區得到
  美國政治分析。新增類似 endpoint 時要先想：prompt language、search query language、
  example output 都要跟著 locale 切換。
- **跨地區 stale 偵測要雙向**（Stage 8 教訓）：`looksLikeTwSeed` 只擋一個方向
  （US 工作區掉 TW 殘留），反方向（TW 工作區掉 US 殘留）需要 `looksLikeUsSeed`。
  存檔還原邏輯（restore from `meta.json`）一定要根據 `activeTemplate.country` 決定
  哪邊是 stale，不能寫死方向。
- **Macro context runtime fallback**（Stage 8）：所有 31 個 template 的
  `default_macro_context` 都偏短（23–61 字一句話），由 `getDefaultMacroContext()`
  在 < 80 字時自動補完整 TW 環境段落。原則：**不改 template JSON**，避免 31 檔重
  build。新 template 的 macro 寫一句話即可。
- **Reasoning model（o-series）token budget**：full evolution prompt 下 reasoning
  tokens 會吃 3.7k+，`max_completion_tokens` 設 4096 會在 content 還沒寫完就截斷。
  evolver 已調到 16384；新增 reasoning model 呼叫處要記得用 `max_completion_tokens`
  而非 `max_tokens`，數值要 >= 8192。

---

## Stage 11 — 投稿目標改為 arXiv-only（2026-04-20）

使用者明確決定：`Paper/` CTW-VA-2026 **只投 arXiv**，不再瞄準 IC2S2 / ICWSM /
EMNLP peer-review venue。此決定讓 8 週計劃大幅簡化，但同時把某些項目的重要性
往上推。**跨機器繼續工作前必讀本節**。

### 11.1 被砍除 / 放寬的工作

| 項目 | 原計劃 | arXiv 版 |
|---|---|---|
| Literature review | 40–60 hr 深度精讀（Campbell / Zaller / Rigger / 吳乃德）| 10–15 hr 足夠寫 2–3 頁 Related Work |
| 政治學術語腔調 | 讀 3–5 篇 paper 學 "pan-green" / "electoral cleavage" 等 jargon | 直白準確即可，arXiv 讀者以 AI 圈為主 |
| 共同作者 | 1–2 週 email 政治學者、附計劃等回覆 | 單人署名，Acknowledgements 感謝看過的朋友 |
| **OSF pre-registration（C10）** | 必做，ICWSM / IC2S2 審稿可信度決定項 | **完全刪除** — arXiv 不要求 |
| Sensitivity analysis（C8）| 平衡新聞池 + reasoning ablation + 2028 三組 | **僅主實驗 + 2028 scenario** — 省 USD 30–40、3–5 天 |
| Paper 格式 | EMNLP / ICWSM 8 頁、特定 section 結構、anonymized | 自由（tech report 格式、彩圖、15 頁或 8 頁皆可）|
| 拒答 κ 標準 | Cohen's κ ≥ 0.7、需第二標註者 | **κ ≥ 0.6 即可、單人標註 + 揭露限制** |

### 11.2 重要性被推上來的工作

沒有 peer-review 把關，**GitHub repo 品質 = 論文可信度**；**arXiv 列表頁前
兩行 = 是否有人點開**。

**Title / Abstract SEO**（投稿前一週再做，但先記在這）
- 原標題範例：`Alignment-Induced Divergence in Multi-Vendor LLM Simulations of Taiwan Voters: A 2024 Presidential Election Backtest`
- 優化版：`When Kimi Refuses and OpenAI Doesn't: A Multi-Vendor Audit of LLM Agent Simulations on the 2024 Taiwan Election`
  - vendor 名字 → 觸發搜尋
  - 衝突張力 → 吸引點擊
  - 具體地域 + 時間 → SEO 精確命中
- Abstract 前兩句必須抓人（arXiv 列表頁只顯示前幾行）
- 發表時機：**週一 / 週二 EST**（arXiv announcements 週一多人看）

**GitHub repo production-grade**（C4-C5 run full 之後，C9 figures 之前）
- [ ] README 加 architecture diagram + reproduction instructions + demo GIF
- [ ] LICENSE（MIT 或 Apache-2.0）
- [ ] Code 補 docstrings / type hints / tests
- [ ] Issues / Discussions 開啟
- [ ] 可選：Gradio / Streamlit interactive demo

### 11.3 新版阻塞鏈（arXiv）

```
舊：OSF pre-register → A5 label → run full → analyze → C8 → C9 → D → 投稿
新：A5 label → run full → analyze → C8(簡化) + C9 + D + repo polish → 投稿
       (skip C10)                                              (新增)
```

1. **A5 收尾** — 標 `responses_n20.csv`（deepseek 20 筆，label 欄目前全空）
   熱身，或直接 `calibration fetch --n 200` 拿完整 1000 筆（200 prompt × 5
   vendor）批次標 → `import-labels` → `train` → `refusal_clf.pkl`
   - **Webui 標註 UI 已完成（2026-04-21）**：在 preview 區塊點 `✏️ 進入標註模式`
     進入全頁 modal，有鍵盤快捷鍵（`1`/`2`/`3`/`u`/`←`/`→`/`n`/`ESC`）、
     confirmatory reveal（標完才顯示 expected，不一致黃色警示）、「只看未標」
     toggle、mini list 跳題、完成後一鍵跑 `import-labels`。CSV in-place 寫入 +
     `mtime` optimistic lock。詳見 `docs/superpowers/specs/2026-04-20-calibration-inline-labeling-design.md`。
2. **C4-C5 run full**（~USD 100，~6 hr wall-clock）— 仍是最大 blocker
3. **`analyze all`** 吃真資料（C7 分析引擎 + 27 test 已備好）
4. **C8（僅主+2028）+ C9 figures + Phase D dashboard + GitHub repo 打磨**（可併行）
5. **Draft paper → upload arXiv**

### 11.4 跨機器 handoff（2026-04-20 晚間結束狀態）

**當前 uncommitted 檔案**（`git status`）：
```
 M CLAUDE.md                                          ← 本節加的內容
 M Paper/experiments/news_pool_2024_jan/stage_a_output.jsonl  ← 微動
 M Paper/experiments/news_pool_2024_jan/stage_b_output.jsonl  ← 微動
?? Paper/experiments/refusal_calibration/             ← 新增目錄
    ├─ responses_n20.csv    (2776 bytes, deepseek 20 筆，label 全空)
    └─ responses_n20.jsonl  (3693 bytes, 原始 LLM 回應)
```

**建議今晚的收尾動作**（離開機器前）：
```bash
# 1. commit 本次 CLAUDE.md 變更 + 熱身測試資料
git add CLAUDE.md Paper/experiments/refusal_calibration/
git commit -m "[CTW-VA-2026] Stage 11: arXiv-only pivot + A5 n=20 warmup"

# 2. 兩個 news pool jsonl 的微動先看是否有意義再決定是否 commit
git diff Paper/experiments/news_pool_2024_jan/stage_a_output.jsonl | head -20

# 3. push 到 GitHub（另一台 PC 要 pull）
git push
```

**另一台 PC 第一次開工步驟**：
```bash
# 1. clone / pull 最新
cd /path/to/Civatas-TW
git pull

# 2. 設定 Paper venv + 安裝
cd Paper
python3 -m venv .venv
.venv/bin/pip install -e .

# 3. 建立 .env（不在 git）
cp .env.example .env   # 若有範例
# 手動填入 5 家 vendor key + SERPER_API_KEY：
#   OPENAI_API_KEY / GOOGLE_API_KEY / GROK_API_KEY / DEEPSEEK_API_KEY / KIMI_API_KEY
#   SERPER_API_KEY

# 4. 驗證工具鏈
.venv/bin/civatas-exp --help
.venv/bin/civatas-exp webui serve --port 8765
# 瀏覽器開 http://127.0.0.1:8765/

# 5. 前置確認
ls Paper/experiments/news_pool_2024_jan/merged_pool.jsonl  # 應存在 (1,445 篇)
ls Paper/experiments/persona_slate_n300/slate.jsonl        # 應存在 (N=300)
ls Paper/experiments/refusal_calibration/responses_n20.*   # 應存在 (今晚測試)
```

**需要手動 scp / sync 過去的檔案**（不在 git 裡的）：
- `Paper/.env` — 5 家 vendor API key + Serper key（`.gitignore` 擋住）
- 無其他必要檔（所有 experiment artifact 都在 git 裡）

### 11.5 明天第一件事的建議

**選項 A：先標 n=20 熱身**（20 分鐘）
- **建議用 webui 標註 UI**（2026-04-21 起可用）：`cd Paper && .venv/bin/civatas-exp
  webui serve --port 8765` → 開 http://127.0.0.1:8765/ → 點 calibration/fetch
  這一頁 → preview 區塊 `✏️ 進入標註模式`。鍵盤 `1`/`2`/`3` 標 3 類，`u` 清除，
  `←`/`→` 切換，全頁 modal、ESC 離開、label 直接寫回 CSV（git pull 即跨 PC 續標）
- 舊 Excel 流程仍可用（backward-compat）：用 Excel/Numbers 開 CSV → 填 label
  欄 → 存檔保持 UTF-8-BOM → 跑 `calibration import-labels`

**選項 B：直接拉 n=200 全家**（~15 分鐘抓 + ~3 hr 標）
```bash
.venv/bin/civatas-exp calibration fetch --n 200
# 產出 responses_n200.jsonl → export → CSV → 批次標 1000 筆
```
優點：一次標完；缺點：若發現 label schema 不順要重標，時間浪費大。**建議先
走選項 A 熱身確認流程**。

**選項 C：略過 A5，先實作 C4-C5 run full 骨架**
- A5 分類器可後期補
- 但 `analyze refusal` 會空轉，拖到論文寫作期才發現會很痛
- **不建議**

### 11.6 arXiv 時程粗估（從 2026-04-21 起）

| 週 | 工作 | 累計成本 |
|---|---|---|
| W1 (4/21-4/27) | A5 標註 + train 分類器；C4-C5 `run full` 骨架 | USD 5 |
| W2 (4/28-5/4) | Run full 執行 + 監控 | USD 105 |
| W3 (5/5-5/11) | analyze all + C8 2028 scenario + C9 figures | USD 120 |
| W4 (5/12-5/18) | Phase D dashboard + GitHub repo 打磨 + demo | USD 120 |
| W5 (5/19-5/25) | Paper draft (Introduction / Related Work / Methodology) | USD 120 |
| W6 (5/26-6/1) | Paper draft (Results / Discussion / Limitations) + title SEO | USD 120 |
| W7 (6/2-6/8) | 朋友 review + 修正 + arXiv 投稿（週一 EST）| USD 125 |

總預算控制在 **USD 150 以內**（USD 400 kill switch 遠低於上限）。
