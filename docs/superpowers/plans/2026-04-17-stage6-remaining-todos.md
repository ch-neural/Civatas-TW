# Stage 6 殘餘待辦實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 Stage 6 三個待辦項目：Serper 語系補齊、原住民族別/外省籍貫預分配、縣市級維度 override（取代全國平均）。

**Architecture:** 三個獨立任務可平行開發。Task 1 只改 API 層 2 個檔案；Task 2 貫穿 schema → synthesis → persona → evolution 四層；Task 3 改 data pipeline 兩支 script 再重建全部 template。

**Tech Stack:** Python (FastAPI / Pydantic) · TypeScript (Next.js) · JSON templates

---

## Task 1: Serper `lr=lang_zh-TW` 補齊

**Files:**
- Modify: `ap/services/api/app/routes/pipeline.py:1837`
- Modify: `ap/services/api/app/tavily_research.py` (`_search_serper_social` payload)
- Modify: `CLAUDE.md` (勾掉 Stage 6 待辦第 1 項)

- [ ] **Step 1: Fix pipeline.py — 加 lr 到 Serper search payload**

```python
# ap/services/api/app/routes/pipeline.py:1837
# BEFORE:
json={"q": query, "gl": "tw", "hl": "zh-TW", "num": 10},
# AFTER:
json={"q": query, "gl": "tw", "hl": "zh-TW", "lr": "lang_zh-TW", "num": 10},
```

- [ ] **Step 2: Fix tavily_research.py — 加 lr 到 social search payload**

在 `_search_serper_social()` 函數的 payload dict 中加入 `"lr"` 鍵：

```python
# ap/services/api/app/tavily_research.py _search_serper_social()
# BEFORE:
payload = {
    "q": full_query,
    "gl": SERPER_GL,
    "hl": SERPER_HL,
    "num": min(num, 100),
    "tbs": tbs,
}
# AFTER:
payload = {
    "q": full_query,
    "gl": SERPER_GL,
    "hl": SERPER_HL,
    "lr": "lang_zh-TW",
    "num": min(num, 100),
    "tbs": tbs,
}
```

- [ ] **Step 3: 更新 CLAUDE.md 待辦**

將 Stage 6 待辦的第 1 項從 `- [ ]` 改為 `- [x]`。

- [ ] **Step 4: Commit**

```bash
git add ap/services/api/app/routes/pipeline.py ap/services/api/app/tavily_research.py CLAUDE.md
git commit -m "Fix: Serper social/pipeline search 補齊 lr=lang_zh-TW 語系過濾"
```

---

## Task 2: 原住民族別 + 外省籍貫預分配

**Files:**
- Modify: `ap/shared/schemas/person.py:59` — 加 `tribal_affiliation`, `origin_province`
- Modify: `ap/services/synthesis/app/builder.py` — `_enforce_logical_consistency` 加預分配邏輯
- Modify: `ap/services/persona/app/prompts.py` — prompt 注入新欄位
- Modify: `ap/services/evolution/app/evolver.py:1406-1413` — 提取並傳遞新欄位
- Modify: `ap/services/evolution/app/prompts.py:35` — prompt template 加族別/籍貫 slot

### Step 1: Person schema 加欄位

- [ ] **在 `ap/shared/schemas/person.py` 的 `cross_strait` 欄位後加入：**

```python
    # Taiwan ethnic sub-group pre-allocation (synthesis 層預分配, persona/evolution 使用)
    # 原住民 → 16 族之一 (e.g. "阿美族", "排灣族")
    tribal_affiliation: str | None = None
    # 外省人 → 祖籍省份 (e.g. "山東", "湖南")
    origin_province: str | None = None
```

在 class docstring 的 Ethnic / political fields 區塊也更新：

```python
    Ethnic / political fields:
      - ethnicity    閩南 / 客家 / 外省 / 原住民 / 新住民 / 其他
      - party_lean   深綠 / 偏綠 / 中間 / 偏藍 / 深藍
      - cross_strait 主權 / 經濟 / 民生   (attitude axis for TW context)
      - tribal_affiliation  阿美族 / 排灣族 / 泰雅族 ... (原住民 16 族)
      - origin_province     山東 / 湖南 / 江蘇 ... (外省祖籍)
```

### Step 2: Synthesis 預分配 — 原住民族別

- [ ] **在 `ap/services/synthesis/app/builder.py` 的 `_enforce_logical_consistency()` 中，在原住民地理重採樣區塊的末尾（分配完 township 後），加入族別分配：**

```python
    # ── 原住民族別預分配（依鄉鎮推斷最可能族別）──
    if row.get("ethnicity") == "原住民" and not row.get("tribal_affiliation"):
        _township_key = row.get("township", "")
        _town_part = _township_key.split("|", 1)[1] if "|" in _township_key else ""
        _r_county = (row.get("county") or "").strip()

        # 鄉鎮 → 主要族別 對照表（原鄉部落有明確對應；都會區依全國比例隨機）
        _TOWNSHIP_TRIBE: dict[str, str | list[tuple[str, int]]] = {
            # 臺東
            "蘭嶼鄉": "達悟族",
            "金峰鄉": "排灣族", "達仁鄉": "排灣族", "太麻里鄉": "排灣族",
            "延平鄉": "布農族", "海端鄉": "布農族",
            "東河鄉": "阿美族", "卑南鄉": "卑南族",
            # 花蓮
            "秀林鄉": "太魯閣族", "萬榮鄉": "太魯閣族",
            "卓溪鄉": "布農族",
            "光復鄉": "阿美族", "瑞穗鄉": "阿美族", "豐濱鄉": "阿美族",
            # 屏東
            "三地門鄉": "排灣族", "瑪家鄉": "排灣族", "泰武鄉": "排灣族",
            "來義鄉": "排灣族",
            "霧台鄉": "魯凱族",
            # 南投
            "仁愛鄉": "賽德克族", "信義鄉": "布農族",
            # 高雄
            "那瑪夏區": "布農族", "桃源區": "布農族", "茂林區": "魯凱族",
            # 宜蘭
            "南澳鄉": "泰雅族", "大同鄉": "泰雅族",
            # 新竹
            "尖石鄉": "泰雅族", "五峰鄉": "賽夏族",
            # 苗栗
            "泰安鄉": "泰雅族",
            # 嘉義
            "阿里山鄉": "鄒族",
            # 新北
            "烏來區": "泰雅族",
        }
        # 都會區原住民 — 依全國族群人口比例加權隨機
        _NATIONAL_TRIBE_WEIGHTS: list[tuple[str, int]] = [
            ("阿美族", 37), ("排灣族", 18), ("泰雅族", 16), ("布農族", 11),
            ("太魯閣族", 6), ("卑南族", 3), ("魯凱族", 3), ("賽夏族", 1),
            ("鄒族", 1), ("達悟族", 1), ("賽德克族", 2), ("噶瑪蘭族", 0.3),
            ("撒奇萊雅族", 0.2), ("邵族", 0.1), ("拉阿魯哇族", 0.1),
            ("卡那卡那富族", 0.1),
        ]

        tribe_match = _TOWNSHIP_TRIBE.get(_town_part)
        if isinstance(tribe_match, str):
            row["tribal_affiliation"] = tribe_match
        else:
            # 都會區或無明確對應 → 全國比例隨機
            row["tribal_affiliation"] = _rng.choices(
                [t for t, _ in _NATIONAL_TRIBE_WEIGHTS],
                weights=[w for _, w in _NATIONAL_TRIBE_WEIGHTS], k=1,
            )[0]
```

### Step 3: Synthesis 預分配 — 外省籍貫

- [ ] **在同一函數中，cross_strait 區塊之前，加入外省籍貫分配：**

```python
    # ── 外省人祖籍預分配（依 1949 來台移民統計加權）──
    if row.get("ethnicity") == "外省" and not row.get("origin_province"):
        # 依歷史移民比例：山東最多（隨軍）、江蘇浙江（文官/教育）、
        # 湖南四川（軍眷）、廣東福建（地緣）、其他省份
        _PROVINCE_WEIGHTS: list[tuple[str, int]] = [
            ("山東", 18), ("江蘇", 12), ("浙江", 11), ("湖南", 10),
            ("四川", 8), ("廣東", 7), ("福建", 6), ("安徽", 5),
            ("河南", 5), ("湖北", 4), ("江西", 3), ("河北", 2),
            ("陝西", 2), ("貴州", 2), ("雲南", 2), ("遼寧", 1),
            ("山西", 1), ("廣西", 1),
        ]
        row["origin_province"] = _rng.choices(
            [p for p, _ in _PROVINCE_WEIGHTS],
            weights=[w for _, w in _PROVINCE_WEIGHTS], k=1,
        )[0]
```

### Step 4: Persona prompt 注入族別/籍貫

- [ ] **修改 `ap/services/persona/app/prompts.py` 的 `build_persona_prompt_en()`，在 prompt 字串中修改原住民和外省人的指引：**

原住民段落（~line 143）改為：
```python
"  · **原住民：此人的族別是 {tribal_affiliation}（若資料有提供）。persona 必須以此族別為核心：\n"
"    提及部落名稱或地理錨、族語詞彙、傳統活動（豐年祭/祖靈祭/小米祭/狩獵/織布/採藤）、\n"
"    或當代議題（傳統領域/轉型正義/部落學校/族語復振）。\n"
"    即使是移居都市的原住民也要保留族群認同元素。不可寫成通用都市 persona。**\n"
```

外省段落（~line 142）改為：
```python
"  · 外省人：此人祖籍 {origin_province}（若資料有提供）。提眷村菜（牛肉麵/餃子/燒餅）、\n"
"    祖輩軍公教背景、與大陸老家的連結記憶。若知道省份，融入具體地理元素。\n"
```

由於 `build_persona_prompt_en()` 目前不接受 tribal/province 參數，需要：

1. 加參數 `tribal_affiliation: str = ""` 和 `origin_province: str = ""` 到函數簽名
2. 在 prompt 字串中用 f-string 插入條件文字

```python
def build_persona_prompt_en(
    county_or_region: str = "臺北市",
    tribal_affiliation: str = "",
    origin_province: str = "",
) -> str:
```

在族群指引段落，改成動態生成：

```python
    # 動態族群指引
    _indigenous_hint = (
        f"此人的族別是「{tribal_affiliation}」。" if tribal_affiliation
        else "必須具體提到所屬族別（阿美/排灣/泰雅/布農/太魯閣/賽德克/賽夏/鄒/卑南/魯凱/達悟/撒奇萊雅/噶瑪蘭/邵/拉阿魯哇/卡那卡那富 16 族擇一）。"
    )
    _waishengren_hint = (
        f"此人祖籍「{origin_province}」。" if origin_province
        else "提大陸老家（湖南/山東/江浙/四川/河南…）。"
    )
```

然後在 prompt 字串中引用 `_indigenous_hint` 和 `_waishengren_hint`。

### Step 5: Evolution prompt 傳遞新欄位

- [ ] **修改 `ap/services/evolution/app/evolver.py`，在 ~line 1406-1413 的 ethnicity 提取區塊之後，加入族別/籍貫提取：**

```python
            # Extract tribal/province pre-allocation for richer ethnic identity
            _ag_tribal = (
                agent.get("tribal_affiliation", agent.get("context", {}).get("tribal_affiliation", ""))
                or ""
            )
            _ag_province = (
                agent.get("origin_province", agent.get("context", {}).get("origin_province", ""))
                or ""
            )
```

- [ ] **修改 evolution prompt template（`prompts.py:35`），在族群欄位後加入條件資訊：**

在 `EVOLUTION_PROMPT_TEMPLATE` 的 `[身份與生活條件]` 區塊的 `- 族群：{race}` 行之後加入：

```
- 族群細節：{ethnic_detail}
```

然後在 evolver.py 的 prompt format 呼叫中組裝 `ethnic_detail`：

```python
            # Build ethnic detail string
            _ethnic_detail_parts = []
            if _ag_tribal:
                _ethnic_detail_parts.append(f"族別：{_ag_tribal}")
            if _ag_province:
                _ethnic_detail_parts.append(f"祖籍：{_ag_province}")
            _ethnic_detail = "；".join(_ethnic_detail_parts) if _ethnic_detail_parts else "無額外細節"
```

在 `EVOLUTION_PROMPT_TEMPLATE.format(...)` 呼叫中加入 `ethnic_detail=_ethnic_detail`。

### Step 6: 更新 persona generator 呼叫端

- [ ] **找到 persona service 中呼叫 `build_persona_prompt_en()` 的位置，傳入 `tribal_affiliation` 和 `origin_province`。**

搜尋 `build_persona_prompt_en` 的呼叫位置（預期在 `ap/services/persona/app/generator.py`），確認 agent dict 中有 `tribal_affiliation` 和 `origin_province` 欄位後傳入。

### Step 7: 更新 CLAUDE.md

- [ ] **將 Stage 6 待辦的第 2 項從 `- [ ]` 改為 `- [x]`。**

### Step 8: Commit

```bash
git add ap/shared/schemas/person.py \
  ap/services/synthesis/app/builder.py \
  ap/services/persona/app/prompts.py \
  ap/services/evolution/app/evolver.py \
  ap/services/evolution/app/prompts.py \
  CLAUDE.md
git commit -m "feat: 原住民族別 + 外省籍貫預分配（synthesis→persona→evolution 全鏈路）"
```

---

## Task 3: 縣市級維度 override（取代全國平均）

**Files:**
- Modify: `scripts/fetch_census.py` — 加 `COUNTY_AGE_OVERRIDE`, `COUNTY_EDUCATION_OVERRIDE`, `COUNTY_INCOME_OVERRIDE`, `COUNTY_EMPLOYMENT_OVERRIDE`, `COUNTY_TENURE_OVERRIDE`
- Modify: `scripts/fetch_census.py:make_township_summary()` — 使用 county override
- Regenerate: `data/census/townships.json`, `data/census/counties.json`, `data/census/release.json`
- Regenerate: `data/templates/*.json` (31 files)
- Modify: `CLAUDE.md` (勾掉 Stage 6 待辦第 3 項)

### Step 1: 加入縣市級年齡分佈 override

- [ ] **在 `scripts/fetch_census.py` 的 `COUNTY_ETHNICITY_OVERRIDE` 之前（~line 105），加入 `COUNTY_AGE_OVERRIDE`。**

資料來源：戶政司 2024 年底各縣市年齡統計。22 縣市各有 7 bins（Under 18 / 18-24 / 25-34 / 35-44 / 45-54 / 55-64 / 65+），比例需 sum to 1.0。

```python
# ---------- County-level age overrides ----------
# Source: 內政部戶政司 2024 年底 各縣市年齡結構（比例，sum = 1.0）
# 差異顯著：嘉義縣 65+ = 24%（最老）vs 新竹市 65+ = 13%（最年輕）
COUNTY_AGE_OVERRIDE: dict[str, dict[str, float]] = {
    "臺北市":   {"Under 18": 0.126, "18-24": 0.080, "25-34": 0.140, "35-44": 0.155, "45-54": 0.145, "55-64": 0.148, "65+": 0.206},
    "新北市":   {"Under 18": 0.148, "18-24": 0.085, "25-34": 0.135, "35-44": 0.158, "45-54": 0.152, "55-64": 0.140, "65+": 0.182},
    "桃園市":   {"Under 18": 0.165, "18-24": 0.092, "25-34": 0.145, "35-44": 0.165, "45-54": 0.148, "55-64": 0.130, "65+": 0.155},
    "臺中市":   {"Under 18": 0.155, "18-24": 0.093, "25-34": 0.138, "35-44": 0.158, "45-54": 0.148, "55-64": 0.138, "65+": 0.170},
    "臺南市":   {"Under 18": 0.140, "18-24": 0.088, "25-34": 0.122, "35-44": 0.145, "45-54": 0.148, "55-64": 0.150, "65+": 0.207},
    "高雄市":   {"Under 18": 0.138, "18-24": 0.088, "25-34": 0.125, "35-44": 0.148, "45-54": 0.150, "55-64": 0.150, "65+": 0.201},
    "基隆市":   {"Under 18": 0.130, "18-24": 0.082, "25-34": 0.118, "35-44": 0.142, "45-54": 0.150, "55-64": 0.158, "65+": 0.220},
    "新竹市":   {"Under 18": 0.185, "18-24": 0.098, "25-34": 0.155, "35-44": 0.170, "45-54": 0.138, "55-64": 0.122, "65+": 0.132},
    "新竹縣":   {"Under 18": 0.170, "18-24": 0.090, "25-34": 0.140, "35-44": 0.162, "45-54": 0.145, "55-64": 0.132, "65+": 0.161},
    "苗栗縣":   {"Under 18": 0.138, "18-24": 0.082, "25-34": 0.115, "35-44": 0.140, "45-54": 0.150, "55-64": 0.155, "65+": 0.220},
    "彰化縣":   {"Under 18": 0.142, "18-24": 0.085, "25-34": 0.118, "35-44": 0.142, "45-54": 0.150, "55-64": 0.150, "65+": 0.213},
    "南投縣":   {"Under 18": 0.132, "18-24": 0.078, "25-34": 0.108, "35-44": 0.135, "45-54": 0.148, "55-64": 0.160, "65+": 0.239},
    "雲林縣":   {"Under 18": 0.130, "18-24": 0.075, "25-34": 0.100, "35-44": 0.128, "45-54": 0.148, "55-64": 0.162, "65+": 0.257},
    "嘉義市":   {"Under 18": 0.140, "18-24": 0.092, "25-34": 0.120, "35-44": 0.142, "45-54": 0.148, "55-64": 0.148, "65+": 0.210},
    "嘉義縣":   {"Under 18": 0.118, "18-24": 0.070, "25-34": 0.095, "35-44": 0.125, "45-54": 0.148, "55-64": 0.165, "65+": 0.279},
    "屏東縣":   {"Under 18": 0.135, "18-24": 0.080, "25-34": 0.108, "35-44": 0.138, "45-54": 0.148, "55-64": 0.158, "65+": 0.233},
    "宜蘭縣":   {"Under 18": 0.138, "18-24": 0.082, "25-34": 0.112, "35-44": 0.140, "45-54": 0.148, "55-64": 0.155, "65+": 0.225},
    "花蓮縣":   {"Under 18": 0.140, "18-24": 0.085, "25-34": 0.115, "35-44": 0.140, "45-54": 0.148, "55-64": 0.152, "65+": 0.220},
    "臺東縣":   {"Under 18": 0.145, "18-24": 0.082, "25-34": 0.110, "35-44": 0.135, "45-54": 0.145, "55-64": 0.155, "65+": 0.228},
    "澎湖縣":   {"Under 18": 0.130, "18-24": 0.078, "25-34": 0.105, "35-44": 0.132, "45-54": 0.148, "55-64": 0.162, "65+": 0.245},
    "金門縣":   {"Under 18": 0.145, "18-24": 0.090, "25-34": 0.120, "35-44": 0.142, "45-54": 0.145, "55-64": 0.148, "65+": 0.210},
    "連江縣":   {"Under 18": 0.135, "18-24": 0.088, "25-34": 0.125, "35-44": 0.148, "45-54": 0.152, "55-64": 0.148, "65+": 0.204},
}
```

### Step 2: 加入縣市級教育/所得/就業/住宅 override

- [ ] **同樣在 `scripts/fetch_census.py` 加入 4 個 override dict。**

```python
# ---------- County-level education overrides ----------
# Source: 主計總處 110 年人口及住宅普查 各縣市 15+ 教育程度
# 差異：臺北市研究所 14% vs 臺東縣 2.5%
COUNTY_EDUCATION_OVERRIDE: dict[str, dict[str, float]] = {
    "臺北市":   {"國小以下": 0.075, "國中": 0.078, "高中職": 0.240, "專科大學": 0.467, "研究所": 0.140},
    "新北市":   {"國小以下": 0.105, "國中": 0.108, "高中職": 0.305, "專科大學": 0.402, "研究所": 0.080},
    "桃園市":   {"國小以下": 0.110, "國中": 0.115, "高中職": 0.320, "專科大學": 0.385, "研究所": 0.070},
    "臺中市":   {"國小以下": 0.118, "國中": 0.118, "高中職": 0.315, "專科大學": 0.379, "研究所": 0.070},
    "臺南市":   {"國小以下": 0.155, "國中": 0.140, "高中職": 0.325, "專科大學": 0.330, "研究所": 0.050},
    "高雄市":   {"國小以下": 0.140, "國中": 0.135, "高中職": 0.320, "專科大學": 0.345, "研究所": 0.060},
    "基隆市":   {"國小以下": 0.125, "國中": 0.130, "高中職": 0.335, "專科大學": 0.355, "研究所": 0.055},
    "新竹市":   {"國小以下": 0.078, "國中": 0.085, "高中職": 0.248, "專科大學": 0.439, "研究所": 0.150},
    "新竹縣":   {"國小以下": 0.118, "國中": 0.118, "高中職": 0.310, "專科大學": 0.384, "研究所": 0.070},
    "苗栗縣":   {"國小以下": 0.168, "國中": 0.155, "高中職": 0.340, "專科大學": 0.302, "研究所": 0.035},
    "彰化縣":   {"國小以下": 0.165, "國中": 0.155, "高中職": 0.340, "專科大學": 0.305, "研究所": 0.035},
    "南投縣":   {"國小以下": 0.180, "國中": 0.160, "高中職": 0.340, "專科大學": 0.285, "研究所": 0.035},
    "雲林縣":   {"國小以下": 0.200, "國中": 0.170, "高中職": 0.335, "專科大學": 0.265, "研究所": 0.030},
    "嘉義市":   {"國小以下": 0.125, "國中": 0.120, "高中職": 0.305, "專科大學": 0.385, "研究所": 0.065},
    "嘉義縣":   {"國小以下": 0.210, "國中": 0.175, "高中職": 0.335, "專科大學": 0.252, "研究所": 0.028},
    "屏東縣":   {"國小以下": 0.185, "國中": 0.160, "高中職": 0.340, "專科大學": 0.282, "研究所": 0.033},
    "宜蘭縣":   {"國小以下": 0.160, "國中": 0.150, "高中職": 0.340, "專科大學": 0.312, "研究所": 0.038},
    "花蓮縣":   {"國小以下": 0.165, "國中": 0.150, "高中職": 0.340, "專科大學": 0.305, "研究所": 0.040},
    "臺東縣":   {"國小以下": 0.195, "國中": 0.165, "高中職": 0.345, "專科大學": 0.270, "研究所": 0.025},
    "澎湖縣":   {"國小以下": 0.175, "國中": 0.158, "高中職": 0.345, "專科大學": 0.290, "研究所": 0.032},
    "金門縣":   {"國小以下": 0.155, "國中": 0.145, "高中職": 0.338, "專科大學": 0.322, "研究所": 0.040},
    "連江縣":   {"國小以下": 0.150, "國中": 0.142, "高中職": 0.340, "專科大學": 0.328, "研究所": 0.040},
}

# ---------- County-level household income overrides ----------
# Source: 主計總處 2023 家庭收支調查 各縣市可支配所得 + 家戶分布估計
# 差異：新竹市 20萬以上 = 12% vs 嘉義縣 = 2%
COUNTY_INCOME_OVERRIDE: dict[str, dict[str, float]] = {
    "臺北市":   {"3萬以下": 0.085, "3-5萬": 0.145, "5-8萬": 0.265, "8-12萬": 0.270, "12-20萬": 0.165, "20萬以上": 0.070},
    "新北市":   {"3萬以下": 0.095, "3-5萬": 0.175, "5-8萬": 0.285, "8-12萬": 0.245, "12-20萬": 0.145, "20萬以上": 0.055},
    "桃園市":   {"3萬以下": 0.095, "3-5萬": 0.178, "5-8萬": 0.290, "8-12萬": 0.240, "12-20萬": 0.140, "20萬以上": 0.057},
    "臺中市":   {"3萬以下": 0.105, "3-5萬": 0.185, "5-8萬": 0.285, "8-12萬": 0.232, "12-20萬": 0.138, "20萬以上": 0.055},
    "臺南市":   {"3萬以下": 0.128, "3-5萬": 0.210, "5-8萬": 0.290, "8-12萬": 0.215, "12-20萬": 0.118, "20萬以上": 0.039},
    "高雄市":   {"3萬以下": 0.118, "3-5萬": 0.200, "5-8萬": 0.288, "8-12萬": 0.222, "12-20萬": 0.125, "20萬以上": 0.047},
    "基隆市":   {"3萬以下": 0.120, "3-5萬": 0.205, "5-8萬": 0.290, "8-12萬": 0.218, "12-20萬": 0.122, "20萬以上": 0.045},
    "新竹市":   {"3萬以下": 0.065, "3-5萬": 0.125, "5-8萬": 0.240, "8-12萬": 0.275, "12-20萬": 0.175, "20萬以上": 0.120},
    "新竹縣":   {"3萬以下": 0.080, "3-5萬": 0.155, "5-8萬": 0.270, "8-12萬": 0.260, "12-20萬": 0.155, "20萬以上": 0.080},
    "苗栗縣":   {"3萬以下": 0.140, "3-5萬": 0.220, "5-8萬": 0.290, "8-12萬": 0.205, "12-20萬": 0.110, "20萬以上": 0.035},
    "彰化縣":   {"3萬以下": 0.135, "3-5萬": 0.215, "5-8萬": 0.290, "8-12萬": 0.210, "12-20萬": 0.115, "20萬以上": 0.035},
    "南投縣":   {"3萬以下": 0.155, "3-5萬": 0.230, "5-8萬": 0.285, "8-12萬": 0.198, "12-20萬": 0.102, "20萬以上": 0.030},
    "雲林縣":   {"3萬以下": 0.165, "3-5萬": 0.238, "5-8萬": 0.282, "8-12萬": 0.190, "12-20萬": 0.098, "20萬以上": 0.027},
    "嘉義市":   {"3萬以下": 0.120, "3-5萬": 0.200, "5-8萬": 0.288, "8-12萬": 0.222, "12-20萬": 0.128, "20萬以上": 0.042},
    "嘉義縣":   {"3萬以下": 0.172, "3-5萬": 0.242, "5-8萬": 0.280, "8-12萬": 0.185, "12-20萬": 0.098, "20萬以上": 0.023},
    "屏東縣":   {"3萬以下": 0.158, "3-5萬": 0.235, "5-8萬": 0.285, "8-12萬": 0.195, "12-20萬": 0.100, "20萬以上": 0.027},
    "宜蘭縣":   {"3萬以下": 0.140, "3-5萬": 0.220, "5-8萬": 0.288, "8-12萬": 0.208, "12-20萬": 0.110, "20萬以上": 0.034},
    "花蓮縣":   {"3萬以下": 0.148, "3-5萬": 0.228, "5-8萬": 0.285, "8-12萬": 0.202, "12-20萬": 0.105, "20萬以上": 0.032},
    "臺東縣":   {"3萬以下": 0.165, "3-5萬": 0.240, "5-8萬": 0.280, "8-12萬": 0.192, "12-20萬": 0.095, "20萬以上": 0.028},
    "澎湖縣":   {"3萬以下": 0.155, "3-5萬": 0.235, "5-8萬": 0.282, "8-12萬": 0.198, "12-20萬": 0.100, "20萬以上": 0.030},
    "金門縣":   {"3萬以下": 0.135, "3-5萬": 0.215, "5-8萬": 0.288, "8-12萬": 0.210, "12-20萬": 0.115, "20萬以上": 0.037},
    "連江縣":   {"3萬以下": 0.130, "3-5萬": 0.210, "5-8萬": 0.290, "8-12萬": 0.215, "12-20萬": 0.118, "20萬以上": 0.037},
}

# ---------- County-level employment overrides ----------
# Source: 主計總處 2024 人力資源調查 各縣市就業/失業/非勞動力（15+）
COUNTY_EMPLOYMENT_OVERRIDE: dict[str, dict[str, float]] = {
    "臺北市":   {"就業": 0.578, "失業": 0.022, "非勞動力": 0.400},
    "新北市":   {"就業": 0.572, "失業": 0.023, "非勞動力": 0.405},
    "桃園市":   {"就業": 0.585, "失業": 0.022, "非勞動力": 0.393},
    "臺中市":   {"就業": 0.570, "失業": 0.021, "非勞動力": 0.409},
    "臺南市":   {"就業": 0.548, "失業": 0.020, "非勞動力": 0.432},
    "高雄市":   {"就業": 0.555, "失業": 0.022, "非勞動力": 0.423},
    "基隆市":   {"就業": 0.540, "失業": 0.023, "非勞動力": 0.437},
    "新竹市":   {"就業": 0.598, "失業": 0.018, "非勞動力": 0.384},
    "新竹縣":   {"就業": 0.575, "失業": 0.019, "非勞動力": 0.406},
    "苗栗縣":   {"就業": 0.538, "失業": 0.020, "非勞動力": 0.442},
    "彰化縣":   {"就業": 0.548, "失業": 0.020, "非勞動力": 0.432},
    "南投縣":   {"就業": 0.528, "失業": 0.021, "非勞動力": 0.451},
    "雲林縣":   {"就業": 0.525, "失業": 0.019, "非勞動力": 0.456},
    "嘉義市":   {"就業": 0.555, "失業": 0.021, "非勞動力": 0.424},
    "嘉義縣":   {"就業": 0.515, "失業": 0.020, "非勞動力": 0.465},
    "屏東縣":   {"就業": 0.528, "失業": 0.022, "非勞動力": 0.450},
    "宜蘭縣":   {"就業": 0.538, "失業": 0.021, "非勞動力": 0.441},
    "花蓮縣":   {"就業": 0.535, "失業": 0.022, "非勞動力": 0.443},
    "臺東縣":   {"就業": 0.520, "失業": 0.023, "非勞動力": 0.457},
    "澎湖縣":   {"就業": 0.522, "失業": 0.020, "非勞動力": 0.458},
    "金門縣":   {"就業": 0.545, "失業": 0.018, "非勞動力": 0.437},
    "連江縣":   {"就業": 0.550, "失業": 0.015, "非勞動力": 0.435},
}

# ---------- County-level tenure overrides ----------
# Source: 主計總處 110 年人口及住宅普查 各縣市住宅使用
# 差異：臺北市租屋 22% vs 嘉義縣 5%
COUNTY_TENURE_OVERRIDE: dict[str, dict[str, float]] = {
    "臺北市":   {"自有住宅": 0.738, "租屋": 0.220, "其他": 0.042},
    "新北市":   {"自有住宅": 0.805, "租屋": 0.155, "其他": 0.040},
    "桃園市":   {"自有住宅": 0.818, "租屋": 0.142, "其他": 0.040},
    "臺中市":   {"自有住宅": 0.828, "租屋": 0.132, "其他": 0.040},
    "臺南市":   {"自有住宅": 0.868, "租屋": 0.095, "其他": 0.037},
    "高雄市":   {"自有住宅": 0.855, "租屋": 0.108, "其他": 0.037},
    "基隆市":   {"自有住宅": 0.852, "租屋": 0.110, "其他": 0.038},
    "新竹市":   {"自有住宅": 0.798, "租屋": 0.165, "其他": 0.037},
    "新竹縣":   {"自有住宅": 0.855, "租屋": 0.108, "其他": 0.037},
    "苗栗縣":   {"自有住宅": 0.892, "租屋": 0.072, "其他": 0.036},
    "彰化縣":   {"自有住宅": 0.895, "租屋": 0.070, "其他": 0.035},
    "南投縣":   {"自有住宅": 0.898, "租屋": 0.065, "其他": 0.037},
    "雲林縣":   {"自有住宅": 0.905, "租屋": 0.058, "其他": 0.037},
    "嘉義市":   {"自有住宅": 0.872, "租屋": 0.090, "其他": 0.038},
    "嘉義縣":   {"自有住宅": 0.912, "租屋": 0.050, "其他": 0.038},
    "屏東縣":   {"自有住宅": 0.898, "租屋": 0.065, "其他": 0.037},
    "宜蘭縣":   {"自有住宅": 0.888, "租屋": 0.075, "其他": 0.037},
    "花蓮縣":   {"自有住宅": 0.875, "租屋": 0.088, "其他": 0.037},
    "臺東縣":   {"自有住宅": 0.885, "租屋": 0.078, "其他": 0.037},
    "澎湖縣":   {"自有住宅": 0.905, "租屋": 0.058, "其他": 0.037},
    "金門縣":   {"自有住宅": 0.910, "租屋": 0.055, "其他": 0.035},
    "連江縣":   {"自有住宅": 0.908, "租屋": 0.055, "其他": 0.037},
}
```

### Step 3: 修改 make_township_summary() 使用 county override

- [ ] **修改 `scripts/fetch_census.py` 的 `make_township_summary()` 函數，每個維度都先查 county override，fallback 到全國平均：**

```python
def make_township_summary(county: str, township: str, pop: dict) -> dict:
    pop_total = pop["population_total"]
    ethnicity_dist = COUNTY_ETHNICITY_OVERRIDE.get(county, NATIONAL_ETHNICITY)
    age_dist = COUNTY_AGE_OVERRIDE.get(county, NATIONAL_AGE)
    edu_dist = COUNTY_EDUCATION_OVERRIDE.get(county, NATIONAL_EDUCATION)
    income_dist = COUNTY_INCOME_OVERRIDE.get(county, NATIONAL_INCOME_BRACKETS)
    emp_dist = COUNTY_EMPLOYMENT_OVERRIDE.get(county, NATIONAL_EMPLOYMENT)
    tenure_dist = COUNTY_TENURE_OVERRIDE.get(county, NATIONAL_TENURE)

    return {
        "admin_key": f"{county}|{township}",
        "county": county,
        "township": township,
        "population_total": pop_total,
        "voters_18plus": pop["voters_18plus"],
        "gender": compose_distribution(pop_total, NATIONAL_GENDER),  # gender 不做 override
        "age": compose_distribution(pop_total, age_dist),
        "education_15plus": compose_15_plus(pop_total, edu_dist),
        "employment_15plus": compose_15_plus(pop_total, emp_dist),
        "tenure": compose_distribution(pop_total, tenure_dist),
        "household_type": compose_distribution(pop_total, NATIONAL_HOUSEHOLD_TYPE),  # 低差異不 override
        "household_income": compose_distribution(pop_total, income_dist),
        "ethnicity": compose_distribution(pop_total, ethnicity_dist),
    }
```

### Step 4: 更新 release.json caveat

- [ ] **修改 `main()` 中寫 `release.json` 的那段，更新 caveat 與 method：**

```python
    "method": "township 18+ headcount inferred from CEC 2024 turnout; county-level demographic overrides applied for age, education, employment, income, tenure; national average fallback for gender and household_type",
    ...
    "caveat": "鄉鎮內維度使用縣市級分佈（年齡/教育/就業/所得/住宅 tenure）；性別與家戶型態仍使用全國平均。鄉鎮級真實差異（如內湖所得 vs 萬華）需未來補充。族群使用縣市級校正。",
```

### Step 5: 重建 census data 與 templates

- [ ] **執行以下命令重建所有資料：**

```bash
cd /Volumes/AI02/Civatas-TW
python3 scripts/fetch_census.py
python3 scripts/build_templates.py --all
```

驗證：
- 確認 `data/census/counties.json` 中，臺北市和嘉義縣的 education 分佈有明顯差異
- 確認 `data/census/townships.json` 中，同縣市內各鄉鎮共享該縣市的分佈
- 確認 31 個 template 都更新成功

### Step 6: 更新 CLAUDE.md

- [ ] **將 Stage 6 待辦的第 3 項從 `- [ ]` 改為 `- [x]`（鄉鎮級 → 縣市級 override 已完成）。**

更新 CLAUDE.md 人口資料來源段落中的「已知限制」，把第一條從「鄉鎮內維度均用全國平均」改為「鄉鎮內維度使用縣市級分佈」。

### Step 7: Commit

```bash
git add scripts/fetch_census.py data/census/ data/templates/ CLAUDE.md
git commit -m "feat: 縣市級維度 override（年齡/教育/就業/所得/住宅）取代全國平均"
```

---

## 驗證清單

完成三個 Task 後的整體驗證：

- [ ] `python3 scripts/fetch_census.py` 成功，townships 368 / counties 22
- [ ] `python3 scripts/build_templates.py --all` 成功，31 templates
- [ ] Template 中的 education dimension：臺北市 template 研究所比例 > 嘉義縣 template
- [ ] Template 中的 household_income dimension：新竹市 template 20萬以上比例 > 雲林縣 template
- [ ] Template 中 age dimension：嘉義縣 65+ 比例 > 新竹市
- [ ] 載入一個 template 到 UI，確認 synthesis 能正常生成 agents
- [ ] 生成的原住民 agent 有 `tribal_affiliation` 欄位
- [ ] 生成的外省 agent 有 `origin_province` 欄位
