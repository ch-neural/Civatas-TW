# Quick Start: 給使用者的啟動指南

**目的**：從現在到 Claude Code 開始執行 A1 之間，你需要做的所有事情。

---

## Step 1: 確認 API Keys 就緒

在 `.env` 或 secrets manager 裡準備好：

```bash
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AIza...           # Google AI Studio
XAI_API_KEY=xai-...              # Grok
DEEPSEEK_API_KEY=sk-...          # DeepSeek platform
MOONSHOT_API_KEY=sk-...          # Moonshot (國際版 platform.moonshot.ai, 不是 .cn)
SERPER_API_KEY=...               # 你已經有
```

**提醒**：Moonshot 走國際版（`.ai`）不走中國版（`.cn`），避開中國管轄。

---

## Step 2: 整合文件到 Civatas-TW repo

```bash
cd /path/to/Civatas-TW

# 文件放 docs/
mkdir -p docs/experiment_vendor_audit_2026
cp /path/to/civatas_tw_vendor_audit/docs/*.md docs/experiment_vendor_audit_2026/
cp /path/to/civatas_tw_vendor_audit/README.md docs/experiment_vendor_audit_2026/

# 資料放 experiments/
mkdir -p experiments/news_pool_2024_jan
mkdir -p experiments/refusal_calibration
mkdir -p experiments/persona_slates

# 把你已有的 Serper pilot 結果丟進去
mv ~/your-pilot-results/stage_a_output.jsonl experiments/news_pool_2024_jan/
mv ~/your-pilot-results/stage_b_output.jsonl experiments/news_pool_2024_jan/
mv ~/your-pilot-results/stage_c_output.jsonl experiments/news_pool_2024_jan/

# 確認結構
tree docs/experiment_vendor_audit_2026/
tree experiments/
```

---

## Step 3: 開新的 git branch

```bash
git checkout -b feat/ctw-va-2026-vendor-audit
git add docs/experiment_vendor_audit_2026/ experiments/
git commit -m "[CTW-VA-2026] setup: research plan and task docs"
```

---

## Step 4: 啟動 Claude Code

### Prompt 1（告訴 Claude Code 讀文件）

```
我正在啟動 Civatas-TW 的 Vendor Audit 研究實驗（project code: CTW-VA-2026）。

請先完整讀這三份文件：
1. docs/experiment_vendor_audit_2026/README.md
2. docs/experiment_vendor_audit_2026/00_RESEARCH_PLAN.md
3. docs/experiment_vendor_audit_2026/01_CLAUDE_CODE_TASKS.md

讀完後告訴我：
- 你理解的研究主旨是什麼（一句話）
- Phase A 的 5 個 task 依賴關係
- 你有什麼不清楚的地方需要我釐清
```

等 Claude Code 確認理解後，再發 Prompt 2。

### Prompt 2（開始執行 A1）

```
好，開始執行 A1：凍結新聞池並計算 SHA-256。

規則提醒：
- 這個 task 不用呼叫任何 LLM API
- 輸入檔案在 experiments/news_pool_2024_jan/stage_{a,b,c}_output.jsonl
- 輸出要包含 merged_pool.jsonl、merged_pool.sha256、README.md、ingestion_metadata.json
- 別忘了寫 unit test 並確認 pytest 通過

完成後 commit，message 格式按 01_CLAUDE_CODE_TASKS.md 規定。
然後停下來報告結果，等我確認才進 A2。
```

---

## Step 5: A5 特殊處理（標註拒答）

當 Claude Code 完成 A5 的第一步（產生 `unlabeled_200.jsonl`）後：

1. **找第二位 zh-TW reviewer**（朋友、配偶、同事都可，能讀繁中就行）
2. **你本人當 reviewer 1**，對方當 reviewer 2
3. **分別獨立標註**，別互相看，標註完才交換
4. **每筆標 4 類之一**：`compliance`、`soft_refusal`、`hard_refusal`、`propaganda_refusal`
5. **把兩人結果合併**成 `labeled_200.jsonl`
6. **讓 Claude Code 跑 `scripts/compute_kappa.py`**

**如果 κ < 0.7**：Claude Code 會停下來報告歧見最大的 case，你要：
- 重新看這些 case，和 reviewer 2 討論
- 若是 label schema 模糊，修改定義
- 若是單純標錯，修正後重跑

這一步不能省，也不能讓 Claude Code 代勞。κ < 0.7 的話實驗結果不可信。

---

## Step 6: B2 之後的 smoke test

Claude Code 完成 B2（5 個 VendorClient）後，會請你做一次**真實 API 的 smoke test**。

這時候：

1. **確認 API keys 都已生效**
2. **Claude Code 會跑一個 5-vendor simultaneous call**（約 USD 0.001）
3. **檢查 5 個 vendor 都有回應**（或記錄失敗 vendor）
4. **特別注意 Kimi**：國際版 `platform.moonshot.ai` 的 rate limit 可能較低，首次呼叫可能要 throttle

---

## Step 7: C5 主實驗啟動前的最終檢查

主實驗要燒 USD 35，Claude Code 會停下來請你確認：

- [ ] OSF pre-registration 已提交（C10 必須在 C5 前完成）
- [ ] News pool SHA-256 和 metadata 文件都就位
- [ ] Persona slate SHA-256 也就位
- [ ] Refusal classifier κ ≥ 0.7 已驗證
- [ ] Cost burn dashboard 可用
- [ ] 你個人確認今天可以跑（不是在忙其他事時開跑）
- [ ] 你**已再次確認**政治敏感度風險可承受

**別偷懶**，這六項檢查每一項都救過人。

---

## 預估時程（理想狀況）

| Week | 工作 | 你親自動手 |
|---|---|---|
| **Week 1** | Phase A 基礎建設 | ~4 hr（A3 TEDS 比例、A5 標註 2-3 hr） |
| **Week 2** | Phase B Vendor Router | ~2 hr（smoke test + review code） |
| **Week 3** | C1-C3 simulation 整合 | ~3 hr（dry run review） |
| **Week 4** | C4 dry run + C5 replication 1 | ~2 hr（監看 dashboard + 10 sample review） |
| **Week 5** | C6 replications 2/3 | ~1 hr（三個時段各啟動一次） |
| **Week 6** | C7 analytics | ~2 hr（跑圖檢查） |
| **Week 7** | C8 sensitivity + C9 figures | ~4 hr（圖精修） |
| **Week 8** | 寫 paper + 投稿 | ~15-20 hr（paper 寫作） |

**你實際介入時間約 30-40 hr，分散在 8 週**。其他時間 Claude Code 在跑。

---

## 常見問題

### Q1: 如果我中間遇到 Claude Code 卡住？

看它停在哪個 task，回頭看 `01_CLAUDE_CODE_TASKS.md` 對應 section，它的 acceptance criteria 是什麼，哪一條沒達成。通常卡在：

- **資料不符預期**：回去確認你的 pilot output 是否完整
- **設計決策**：它會明確問你，你給答案就好
- **API 行為異常**：檢查 API key、rate limit、billing

### Q2: 如果 Kimi 在 dry run 就 100% 拒答？

這是可能的。處理方式：

1. **不要 panic**——這本身就是可發表的結果
2. 看 refusal 的具體模式：是 `hard_refusal` 還是 `propaganda_refusal`？
3. 調整 paper framing：從「vendor comparison」改成「Kimi's systematic refusal in Taiwan political simulation: a case study」
4. 預算也可能因此降低（Kimi 花費少）

### Q3: 如果 Serper pilot 資料有問題要重抓？

在 A1 前發現：沒問題，重抓就好
在 A1 後發現：要 invalidate A1 產生的 SHA，整個 pipeline 回到起點
**建議**：A1 之前再把三個 pilot JSONL 快速 sanity check 一次

### Q4: 如果論文投不上怎麼辦？

你會有：
- 完整的 Civatas-TW vendor audit 系統（可以分成 demo paper 投 ACL Demo）
- 3 個完整 replication 的資料（可以釋出 dataset，投 NeurIPS D&B）
- 三階段新聞抓取協議（可以獨立寫成 methodology 短文）

**一份研究至少可切出 3 個可發表產品**，別把希望押在單一 venue 上。

### Q5: 寫完之後要不要找政治學共同作者？

**強烈建議**。方法論你自己就能搞定，但要投 Political Analysis / ICWSM main 這類更高 venue，掛一位政治學者作者會大幅提升 acceptance 率，而且對你的政治敏感風險是分擔。

候選：中研院政治所、政大選研中心、台大政治系的助理教授。主動發信問有沒有興趣合作，附上你的 draft。

---

## 祝你順利！🎯
