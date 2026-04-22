# 🗳️ Civatas 台灣

> 選舉版的 SimCity — 用台灣人口資料建構上千位合成選民，每天餵真實新聞，觀察他們的政治意見如何演化。

從 **Civatas-USA** 反向改造為台灣情境（2026-04-17）。完全替換資料層、政治光譜、族群、地理粒度與 UI 文案。

---

## 📄 Paper: CTW-VA-2026

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19691574.svg)](https://doi.org/10.5281/zenodo.19691574)
[![License: CC BY 4.0](https://img.shields.io/badge/License-CC_BY_4.0-lightgrey.svg)](https://creativecommons.org/licenses/by/4.0/)

本 repo 同時包含研究論文 **"Vendor-Specific Refusal Patterns in LLM Responses
to Taiwan-Political Prompts: Evidence Against a Monolithic East-West Alignment
Dichotomy"** 的全部材料。該研究審計 OpenAI / Gemini / Grok / DeepSeek / Kimi
五家商業 LLM 在 200 題繁中台灣政治議題上的拒答行為，帶 paired-bootstrap 95%
BCa 置信區間、4-class refusal taxonomy、topic × vendor × layer 三維分解。

**正式引用**：
```
Tseng, C.-H. (2026). Vendor-Specific Refusal Patterns in LLM Responses to
Taiwan-Political Prompts: Evidence Against a Monolithic East-West Alignment
Dichotomy. Zenodo. https://doi.org/10.5281/zenodo.19691574
```

- 📄 [`Paper/paper_source/main.pdf`](Paper/paper_source/main.pdf) — 論文 PDF（27 頁）
- 📂 [`Paper/paper_source/`](Paper/paper_source/) — LaTeX 源碼（`make` 可重新編譯）
- 📂 [`Paper/`](Paper/) — 完整子目錄（實驗資料、分析腳本、文件）
- 📊 [`Paper/experiments/refusal_calibration/`](Paper/experiments/refusal_calibration/)
  — 1,000 筆 vendor call log + 986 筆人工標註 + AI-judge audit trail
- 📘 [`Paper/docs/04_REFUSAL_LABELING_RULES.md`](Paper/docs/04_REFUSAL_LABELING_RULES.md)
  — 標註 decision tree（Cases A-J + Traps 1-11）

### 主要發現（見 paper §4）

1. **Finding 1**：DeepSeek 的 refusal 分佈跟 Western 幾乎一樣（JSD 0.010-0.017），
   跟 Kimi 差最遠（JSD 0.200）。「中 vs 西」二分法被資料打臉。
2. **Finding 2**：Kimi 的 API filter 不只擋敏感意見，連「立法院席次」「總統任期」
   等 RoC 制度事實題也擋 → **Taiwan-statehood blocking** 而非 opinion blocking。
3. **Finding 5**（核心）：DeepSeek 在 sovereignty 題上 on-task rate 崩到 **10.3%**
   （CI `[2.6, 23.3]`），非 sovereignty 題卻是 54%（Western 水準）——
   整個資料集最強的單一 signal。
4. 其餘 4 個 findings（api_blocked/on_task/elasticity 等）見 [論文 PDF](Paper/paper_source/main.pdf) §4 Results。

### 本 repo 的雙重定位

```
github.com/ch-neural/Civatas-TW
├── ap/                    ← Civatas 模擬平台（9-service Dockerized, 下半部介紹）
├── data/                  ← 台灣地理 / 人口普查 / 選舉 / PVI 資料
├── scripts/               ← 頂層資料抓取 + 建 templates 腳本
└── Paper/                 ← CTW-VA-2026 論文（獨立子專案）
    ├── paper_source/      ← LaTeX 源碼 + 中文版
    ├── experiments/       ← 實驗資料 + 標註
    ├── docs/              ← 標註 rulebook + 研究計劃
    ├── src/               ← Python 套件（5-vendor client adapter、refusal classifier 等）
    └── scripts/           ← 繪圖 + 分析 + bootstrap CI 腳本
```

---

## 特色

- **9 個 Docker 服務**：Next.js 前端 + FastAPI 後端 + OASIS simulation 核心
- **22 縣市 × 368 鄉鎮市區** 的細粒度地理建模
- **藍綠白三黨** 政治光譜，5 桶 PVI 分類：深綠 / 偏綠 / 中間 / 偏藍 / 深藍
- **5 族群** 差異化反應：閩南 / 客家 / 外省 / 原住民 / 新住民
- **三軸政治態度**：經濟立場 × 社會價值 × **兩岸立場**
- **31 個預設 Template**：5 總統選舉 + 1 民調 + 3 直轄市長 + 22 縣市版

## 預設 Template

| 類型 | 內容 |
|---|---|
| 2024 總統回測 | 賴清德 / 侯友宜 / 柯文哲 |
| 2028 總統推測（3 組對決） | 賴清德 vs 盧秀燕 / 鄭麗文 / 蔣萬安 |
| 2028 民調（7 人）| 賴 / 蕭美琴 / 黃國昌 / 盧 / 蔣 / 韓國瑜 / 鄭 |
| 2026 直轄市長 | 台北（蔣萬安 vs 沈伯洋）／ 台中（江啟臣 vs 何欣純 vs 麥玉珍）／ 高雄（柯志恩 vs 賴瑞隆）|
| 22 縣市版 | 每縣市單一 2024 總統回測 |

## 快速開始

### 資料層

```bash
python3 scripts/fetch_geo.py             # 22 縣市 + 375 鄉鎮 geojson
python3 scripts/fetch_elections.py       # 中選會 2024 鄉鎮級開票
python3 scripts/fetch_census.py          # 主計總處普查 + 戶政司月報
python3 scripts/compute_pvi.py           # 藍綠傾向指數（自動偵測年份）
python3 scripts/build_templates.py --all # 31 個 template
python3 scripts/load_election_db.py      # SQLite
```

驗證：2024 全國得票率 **賴 40.05% / 侯 33.49% / 柯 26.46%**，有效票 13,947,506（與中選會官方完全一致）。

### 應用

```bash
cd ap
cp .env.example .env   # 填入 API keys (OpenAI / DeepSeek / Serper...)
docker compose up --build
```

- Web UI：http://localhost:3100
- API 文件：http://localhost:8000/docs

## 資料來源

| 項目 | 來源 |
|---|---|
| 縣市 / 鄉鎮 geojson | [g0v/ronnywang twgeojson](https://github.com/ronnywang/twgeojson)（內政部 MOI segis 2011）|
| 2024 總統開票 | 中選會公開資料（368 鄉鎮完整） |
| 人口（性別/年齡）| 戶政司月報 2024 年底 |
| 教育 / 家戶 / 居住 | 主計總處 110 年人口及住宅普查 |
| 家戶所得 | 主計總處 2023 家庭收支調查 |
| 就業 / 失業 | 主計總處 2024 人力資源調查年報 |
| 族群（全國） | 客委會 2021 全國客家人口調查 + 原民會 2024 原住民族人口概況 |

## 架構

```
upload → ingestion(8001) → synthesis(8002) → persona(8003) → social(8004)
       → adapter(8005) → simulation(8006, OASIS) → analytics(8007)
              ↑                                              ↑
            api(8000) FastAPI gateway     web(3000) Next.js frontend
```

詳細架構與開發規則見 `CLAUDE.md`，應用端設定見 `ap/README.md`。

## 已知限制

- **鄉鎮內維度**（性別 / 年齡 / 教育 / 所得等）目前使用全國平均，僅**族群**在縣市層級有地理 override。鄉鎮級真實差異（如內湖所得遠高於萬華）需未來補資料。
- **2020 鄉鎮級總統資料** 未內建（中選會僅公開 ODS）。PVI 目前基於 2024 單屆計算；提供了 `--import-year 2020 --from-csv` 指令，使用者可手動提供 CSV，系統會自動切換為雙屆平均。
- **375 vs 368 鄉鎮市區**：g0v 2011 版 geojson 有 375 個 feature，中選會 2024 資料 368 個；差異在 tolerance 內。

## 授權

MIT License。選舉資料來自中選會公開資料；geojson 為 g0v/ronnywang twgeojson（MIT）。

---

_專案由 Civatas-USA 改造而來；所有 US 特定資料（MEDSL、ACS、Cook PVI、50 州 geojson）已替換為台灣對應資料集。改造細節見 `CLAUDE.md`。_
