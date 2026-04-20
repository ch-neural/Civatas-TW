# Civatas-TW Vendor Audit (CTW-VA-2026)

**跨 vendor LLM 台灣選民模擬比較研究**

---

## 📁 檔案說明

| 檔案 | 用途 | 給誰看 |
|---|---|---|
| `docs/00_RESEARCH_PLAN.md` | 研究主旨、假設、實驗設計、統計方法、時程、風險 | 使用者、論文合作者、審稿人 |
| `docs/01_CLAUDE_CODE_TASKS.md` | 20 個開發 task 的詳細規格 | Claude Code（直接執行） |
| `docs/02_QUICK_START.md` | 使用者快速啟動指南 | 使用者 |

---

## 🚀 快速啟動（給使用者）

### 步驟 1：把這整個資料夾放進你的 Civatas-TW repo

```bash
cd /path/to/Civatas-TW
cp -r civatas_tw_vendor_audit/docs docs/experiment_vendor_audit_2026
cp -r civatas_tw_vendor_audit/experiments experiments
```

### 步驟 2：把你已完成的 Serper pilot 結果放到對應位置

```bash
# 你之前 pilot 抓的三批新聞
mv stage_a_output.jsonl experiments/news_pool_2024_jan/
mv stage_b_output.jsonl experiments/news_pool_2024_jan/
mv stage_c_output.jsonl experiments/news_pool_2024_jan/
```

### 步驟 3：開 Claude Code 並貼這段 prompt

```
讀 docs/experiment_vendor_audit_2026/01_CLAUDE_CODE_TASKS.md，從 Phase A 的 A1 開始執行。

規則：
1. 依序執行 A1 → A2 → ... → A5，做完 Phase A 才進 Phase B
2. 每個 task 完成後 commit，message 格式按文件規定
3. 每個 task 都要寫 unit test 且通過
4. 遇到 acceptance criteria 無法達成、需要設計決策、預算 > USD 5 的情況，停下來問我
5. 不要真的呼叫 LLM API 除非 task 明說（A5 和 Phase C 才燒錢）

現在開始 A1。
```

---

## 📊 研究核心數字

- **論文主旨**：5 個 LLM vendor 模擬台灣 2024 總統大選，誰最接近真實結果？alignment 文化如何造成差異？
- **實驗規模**：300 personas × 13 天 × 5 vendors × 2 scenarios × 3 replications ≈ 117,000 LLM calls
- **預算**：USD 200 主實驗 + USD 300 buffer，總 USD 500
- **時程**：8 週 sprint
- **目標 venue**：ICWSM 2027 / IC2S2 2027 / EMNLP Findings 2026

## 🎯 核心 claim（無論結果如何都成立）

> **"Vendor choice in LLM social simulation is not an implementation detail — it's an experimental variable with systematic, measurable, alignment-culture-clustered effects."**

---

## 🛠️ 五個 Vendor

| Vendor | Model | Alignment 文化 |
|---|---|---|
| OpenAI | gpt-4o-mini | 美國系 |
| Google | gemini-2.5-flash-lite | 美國系 |
| xAI | grok-4.1-fast | 美國系（右傾）|
| DeepSeek | deepseek-chat (V3.2) | 中國系 |
| Moonshot | kimi-k2-0905 | 中國系 |

---

## 📝 Pre-pilot 進度（使用者已完成）

- ✅ Stage A: 7 關鍵字通用搜尋 → 524 unique articles
- ✅ Stage B: 5 藍營 media + site: 限定 → 552 unique articles（中時 108 / 聯合 110 / TVBS 91 / 東森 47 / 風傳 102）
- ✅ Stage C: 深綠補強（民視 92 / 自由 124 / Newtalk 83）+ 深藍嘗試失敗 → 436 unique articles
- ✅ 合併去重後約 **1,250 篇**，分布：深綠 24% / 偏綠 28% / 中間 30% / 偏藍 37% / 深藍 0%（fallback）

---

## ⚠️ 重要限制

1. **深藍結構性真空**：台灣網路深藍媒體不存在（中天撤照後轉 YouTube），深藍 agent 用偏藍 top-partisan（中時/TVBS/聯合）fallback
2. **社交層禁用**：實驗模式下 agent 間不互動，以控制 vendor 比較 identifiability
3. **政治敏感度**：使用者已知悉中國落地風險、網路輿論壓力等，決定繼續推進

---

## 📞 決策點

Claude Code 會在以下幾個點停下來問你：

1. **A3**：TEDS 2024 權重檔案是否存在？（如無則先用預設）
2. **A5**：200 筆拒答標註要你本人 + 一位 reviewer 完成
3. **B2**：5 個 vendor 的 API key 是否都已就緒？
4. **C5**：Main experiment 要燒 USD 35，開跑前最後確認
5. **C10**：OSF pre-registration 提交

---

## 🔗 參考資料

- CEC 2024 官方結果：賴清德 40.05% / 侯友宜 33.49% / 柯文哲 26.46%
- Ko 2026 台灣主權 Benchmark：arXiv 2602.06371
- Civatas-USA（原始 repo）：https://github.com/ch-neural/Civatas-USA
