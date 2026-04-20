# Civatas-TW Vendor Audit: 研究計劃與實驗設計

**Project code**: CTW-VA-2026
**Author**: ch-neural (Tseng)
**Date**: 2026-04-19
**Status**: Ready for implementation (Phase A)

---

## 1. 論文主旨（一句話）

> 當五個不同 alignment 文化的 LLM vendor 扮演同一批台灣選民、接觸同一批真實新聞、跑同一組演化流程時，它們對 2024 年台灣總統大選真實投票結果的模擬準確度有多大差異？這些差異是否呈現系統性的 alignment 文化聚類？

## 2. 論文標題（草擬）

**Alignment-Induced Divergence in Multi-Vendor LLM Simulations of Taiwan Voters: A 2024 Presidential Election Backtest**

## 3. 研究貢獻（三點）

1. **第一個跨 alignment 文化（美國系 / 中國系 / xAI）的 LLM agent simulation 平行比較** — 在台灣政治情境、繁體中文、agent-based 動態演化的多維條件下
2. **提出 Ground-truth-anchored 的 vendor evaluation 方法論** — 以 CEC 2024 官方結果（賴 40.05% / 侯 33.49% / 柯 26.46%）為驗證標準，搭配 JSD / NEMD / 拒答率三指標
3. **揭示 Serper / Google News 索引在台灣政治新聞上的系統性偏誤，並提供三階段抓取 protocol 作為方法論補救**

## 4. 核心研究問題與假設

### RQ1：Vendor 對相同輸入是否產生系統性不同的模擬結果？

**H1**：固定 persona、新聞、template、seed 下，五個 vendor pair 之間的投票分布 JSD > 0 至少一對，經 Holm-Bonferroni 校正後仍顯著。

### RQ2：Alignment 文化是否造成聚類？

**H2a（拒答聚類）**：Chinese-aligned {DeepSeek, Kimi} 在高敏感度議題上的拒答率系統性高於 {OpenAI, Gemini, Grok}，用 Mann-Whitney U 檢定。

**H2b（立場聚類）**：五個 vendor 在 MDS 投影空間上形成可識別的 alignment cluster，用 silhouette score permutation test 驗證。

### RQ3：哪個 vendor 最接近真實選舉結果？

**H3（Ground truth alignment）**：至少一個 vendor 的最終投票分布與 CEC 2024 結果的 JSD 顯著低於其他 vendor（bootstrap CI 不重疊）。

### RQ4（探索性）：Vendor 差異是否因 persona 特徵而變化？

**H4**：Vendor × agent media_habit 交互作用顯著 — 例如 Kimi 對深綠 agent 的模擬誤差 vs 對深藍 agent 的誤差有系統性差異。

---

## 5. 實驗設計

### 5.1 實驗矩陣

| 因子 | 層級 | 數量 |
|---|---|---|
| **Vendor** | DeepSeek-V3.2, Grok 4.1 Fast, GPT-4o-mini, Gemini 2.5 Flash-Lite, Kimi K2 | 5 |
| **Scenario** | 2024 回測（賴 vs 侯 vs 柯）+ 2028 前瞻（secondary） | 2 |
| **Persona slate** | N=300 台灣 agents，census-stratified，seed 固定 | 1 批 |
| **Replication seed** | 20240113, 20280116, 20260101 | 3 |
| **News pool** | 2024/1/1-1/13 的 ~1,250 篇平衡新聞池（3 stage Serper 抓取） | 1 批 |

**總 LLM calls**：5 × 2 × 300 × 13 天 × 3 replications ≈ 117,000 次主實驗 calls
加上拒答分類（~25% 需 stage-2 judge）：~30,000 次 judge calls

**預算估算**：約 USD 200（主實驗 USD 150 + judge USD 30 + buffer USD 20），USD 300 buffer 留給意外和 sensitivity 分析。

### 5.2 Within-subject 設計（關鍵）

**每個 persona × 每一天 × 同一組新聞 → 分別餵給 5 個 vendor**，產生 5 組平行 diary / state update。這讓 vendor 差異可以乾淨歸因。

**社交層禁用**：實驗期間關閉 agent 間互動，保持 vendor 比較的 identifiability。在 paper limitations 明講。

### 5.3 新聞輸入協議

**新聞池（已完成 pilot，共 ~1,250 篇）**：
- 深綠 ~205（民視、三立）
- 偏綠 ~260（自由、Newtalk、關鍵評論網）
- 中間 ~380（Yahoo、中央社、報導者、公視、天下）
- 偏藍 ~460（中時、聯合、TVBS、東森、風傳媒）
- 深藍 0 → fallback 到偏藍 top-partisan（chinatimes / tvbs / udn）

**每日選文邏輯**：`resolve_feed_for_agent(agent, pool, day, seed)` 按 `MEDIA_HABIT_EXPOSURE_MIX` 分層採樣，deterministic seed `hash((agent.id, day, seed))`。

**凍結要求**：新聞池在實驗開始前 SHA-256 固定，實驗期間不可變動。

### 5.4 拒答偵測

兩階段管線：
- **Stage 1**：regex + hedge ratio（英文 / 繁中 / 簡中 / CCP 宣傳 四個 bank）
- **Stage 2**：Gemini 2.5 Flash 第三方 judge（不是受測 vendor）
- 校準門檻：Cohen's κ ≥ 0.7 vs 200 筆人工標註

### 5.5 評估指標

| 指標 | 用途 | 計算方式 |
|---|---|---|
| **JSD** | vendor 間分布差異、vs 真實結果 | Jensen-Shannon divergence (log base 2) |
| **NEMD** | 5-bucket 政黨傾向的 ordinal 差異 | Normalized Earth Mover's Distance |
| **Refusal rate** | 拒答率 | (hard + soft + propaganda + filter) / total |
| **Cramér's V** | 5×K 列聯表關聯強度 | with bias correction |
| **Bootstrap CI** | 所有指標的信賴區間 | B=10,000, BCa, paired on persona id |

### 5.6 統計檢定

- 10 個 vendor pair → Holm-Bonferroni 校正
- 60 個細分類 → Benjamini-Hochberg FDR
- H2b silhouette score → permutation test, 10,000 次
- Pre-register 全部假設和檢定方法於 OSF

---

## 6. 系統架構

### 6.1 Civatas 現有 9-service 改動摘要

```
ingestion(8001)    → 加 topic_class 分類 + Serper 3-stage 抓取
synthesis(8002)    → 加 --export-slate 輸出固定 SHA-256 persona slate
persona(8003)      → 讀取並驗證 persona_slate_id（無功能變更）
social(8004)       → 實驗模式禁用（config flag）
adapter(8005)      → 【核心改動】加 VendorRouter + 5 個 VendorClient + multivendor fan-out
simulation(8006)   → 實驗模式下呼叫 multivendor 並維護 per-vendor state
evolution          → 加 resolve_feed_for_agent + per-vendor logging
analytics(8007)    → 加 JSD / NEMD / Refusal pipelines + Bootstrap CI
api(8000) + web    → 加 Experiment Dashboard + 即時 cost burn
```

### 6.2 新增資料 schema

```sql
CREATE TABLE experiment_run (
    experiment_id       TEXT PRIMARY KEY,
    persona_slate_id    TEXT NOT NULL,       -- SHA-256
    news_pool_id        TEXT NOT NULL,       -- SHA-256
    scenario            TEXT NOT NULL,
    replication_seed    BIGINT NOT NULL,
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    pipeline_version    TEXT NOT NULL        -- git SHA
);

CREATE TABLE vendor_call_log (
    call_id             UUID PRIMARY KEY,
    experiment_id       TEXT REFERENCES experiment_run,
    persona_id          TEXT,
    sim_day             INT,
    vendor              TEXT,
    model_id            TEXT,
    articles_shown      JSONB,               -- 3 篇 article IDs
    prompt_hash         TEXT,                -- 驗證 vendor 間 prompt 一致
    response_raw        TEXT,
    refusal_status      TEXT,
    refusal_confidence  NUMERIC,
    latency_ms          INT,
    tokens_in           INT,
    tokens_out          INT,
    cost_usd            NUMERIC,
    status              TEXT                 -- 'ok'|'refusal_text'|'refusal_filter'|'error'
);

CREATE TABLE agent_day_vendor (
    experiment_id       TEXT REFERENCES experiment_run,
    persona_id          TEXT,
    sim_day             INT,
    vendor              TEXT,
    satisfaction        NUMERIC,
    anxiety             NUMERIC,
    candidate_awareness JSONB,
    candidate_sentiment JSONB,
    candidate_support   JSONB,
    party_choice        TEXT,
    party_lean_5        TEXT,
    diary_text          TEXT,
    diary_tags          JSONB,
    PRIMARY KEY (experiment_id, persona_id, sim_day, vendor)
);
```

### 6.3 Canonical 生成設定（vendor 一致性契約）

```python
CANONICAL_GEN_CONFIG = {
    "temperature": 0.0,
    "top_p": 1.0,
    "max_tokens": 512,
    "frequency_penalty": 0.0,
    "presence_penalty": 0.0,
    "seed": <replication_seed>,
    # Vendor 特定 reasoning-disable：
    #   gemini: thinkingBudget=0
    #   kimi: extra_body={"thinking":{"type":"disabled"}}
    #   grok: 用 grok-4.1-fast (非 reasoning 版)
    #   deepseek: 用 deepseek-chat (V3.2, 非 R1)
    #   openai: 用 gpt-4o-mini (無 reasoning token)
}
```

---

## 7. 時程（8 週 sprint）

| Week | 主要工作 | Gate |
|---|---|---|
| **W1** | News pool freeze + OSF pre-register + refusal calibration (κ≥0.7) | 新聞池 SHA 鎖定 |
| **W2** | Adapter v2：VendorRouter + 5 個 VendorClient + multivendor endpoint | 5 個 vendor smoke test 通過 |
| **W3** | Refusal pipeline + Persona slate freeze + Simulation wiring | Dry run 20 agents × 3 天通過 |
| **W4** | Main experiment Replication 1（300 × 13 × 5 × 2 = 39,000 calls） | ~USD 35 燒掉，資料完整 |
| **W5** | Replications 2 & 3 | ~USD 70 累計 |
| **W6** | Analytics pipeline：JSD / NEMD / Refusal / Bootstrap CI | 所有 metric endpoint 可用 |
| **W7** | Sensitivity analysis + 2028 scenario + Figures | Paper figures finalized |
| **W8** | Paper draft + 內部 review + 投稿 | Submit |

---

## 8. 投稿目標（優先序）

1. **IC2S2 2027** — Computational Social Science 主戰場
2. **ICWSM 2027 Workshop / Main** — 資訊科學 + 社會模擬
3. **ACL 2026 System Demo** — Civatas-TW 系統展示（單獨 demo paper）
4. **EMNLP 2026 Findings / NLP+CSS workshop** — 備案

---

## 9. 主要風險

| 風險 | 機率 | 影響 | 緩解 |
|---|---|---|---|
| Kimi 拒答率 >90% → H2a trivially true | 高 | 中 | 分別報告「含拒答」和「排除拒答」的 analysis |
| Vendor API 突然變更 / 下線 | 中 | 高 | Pin model_id，W1 完成後不再更換 |
| 新聞池偏誤被審稿人質疑 | 低 | 中 | 三階段抓取 protocol 寫進 methodology 當 contribution |
| 政治敏感輿論反應 | 中 | 中 | 用中性語言 framing（"divergence" 不用 "censorship"），考慮共同作者分攤 |
| 成本爆表 | 低 | 中 | Dashboard 即時監控，USD 400 自動 kill switch |

---

## 10. 結論的三種可能情境

### 情境 A：大差異（預期機率 ~60%）

OpenAI 最低 JSD（0.042）vs Kimi 最高（0.198），Kimi 拒答率 71%，MDS silhouette 0.68。結論：「Vendor choice is a first-class experimental variable」。

### 情境 B：中等差異（預期機率 ~30%）

Vote 預測差異 < 2pp 但拒答率差異明顯。結論：「vendor alignment primarily affects what LLMs decline to simulate rather than what they do simulate」。

### 情境 C：微弱差異（預期機率 ~10%）

五 vendor 結果相近。Null result 仍可發表 — 「for aggregate political prediction tasks, vendor alignment may matter less than community folklore suggests」。

**無論哪個情境，核心 claim 都成立**：
> "Vendor choice in LLM social simulation is not an implementation detail — it's an experimental variable with systematic, measurable, alignment-culture-clustered effects."

---

## 11. Paper 核心 Figure 預覽

- **Figure 1**：新聞池三階段建構流程
- **Figure 2**：Vendor 支持度軌跡 line chart（5 vendor × 3 candidate over 13 days）
- **Figure 3**：Pairwise JSD heatmap（5×5 with alignment clustering）
- **Figure 4**：Refusal rate × topic sensitivity bar chart
- **Figure 5**：MDS alignment cluster scatter
- **Figure 6**：vs CEC ground truth 比較表
