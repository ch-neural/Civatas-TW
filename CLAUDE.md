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
- `ap/shared/tw_data/tw_feed_sources.json` 為 tw_feed_sources.py 的 JSON 快照，
  供 API gateway 在 `/api/runtime/news-sources` endpoint 直接 serve。

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

- **鄉鎮內維度均用全國平均**。鄉鎮級真實差異（例如內湖所得遠高於萬華）需未來補資料
  精煉。族群維度已有縣市級 override 反映地理現實。
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
- Tavily/Serper 新聞搜尋會以 `lr=lang_en` 過濾，**但在 TW 環境下需要改為 `lr=lang_zh-TW`**
  —— 這是 Stage 6 驗證時要確認的項目。
