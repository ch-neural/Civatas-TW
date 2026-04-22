# arXiv Endorsement / Paper-Notification Email 草稿

## 狀態摘要（2026-04-22 更新）

- **A. 郭昱晨 教授**：已寄出 → 已回覆，accept endorsement、建議改 cs.CY
  primary（他有 cs.CY endorsement 權限、沒 cs.CL）→ 方案已調整，主類別改 cs.CY
  → 待寄 **A.2 回信確認改投 cs.CY**（草稿見下方 §A.2）
- **B. Ali Naseh**：**endorsement 不再需要**（Ko 一人足以 endorse cs.CY primary）。
  §B 已重新定位為 **paper-notification email**（zero ask），因為 §5.4 Hypothesis 3
  直接 cite 他的 R1dacted 工作。視個人判斷決定是否寄。

---

## A. 繁中版 — 郭昱晨 教授 / 立委 ✅ 已寄、已回覆

**收件人**：`juchunko@ntu.edu.tw`

**主旨**：`arXiv 論文 endorsement 請求 — 繁中 LLM 台灣政治審計研究（引用您的論文）`

---

郭教授您好，

我是曾澄勳，在新竹的凌陽創新科技工作。最近完成一篇研究，準備投稿到 arXiv 的 cs.CL 類別：

**「五家大型語言模型在台灣政治題上的拒答行為差異」**

研究做法：用 200 個繁中台灣政治題目（統獨、族群、228、縣市治理等），測試五家商業 LLM（OpenAI、Google Gemini、xAI Grok、DeepSeek、Kimi）怎麼回答。總共 1,000 筆回應，我全部人工分成四類（硬拒、軟拒、正常回答、API 層直接擋）。

幾個比較有趣的發現：

- **DeepSeek 其實跟美國廠商很像**，反而跟 Kimi 差最多。「中 vs 美」二分法不成立。
- **Kimi 的 API filter 不只擋敏感意見**，連「立法院幾席」「總統任期多久」這種維基百科查得到的事實題也擋。只要題目提到中華民國國家制度就擋。
- **DeepSeek 一碰到主權題，回答率從 54% 掉到 10%**，但其他議題跟美國廠商差不多。

我在論文第 2 節與第 5.1 節**兩次引用您 2026 年發表的那篇**（arXiv 2602.06371，17 家 LLM 中英文雙語比較 Taiwan 主權偏差），當作**最接近我這篇研究的前人工作**。您那篇看的是同一家 vendor 在中英文下的差異，我這篇看的是 5 家 vendor 在同一中文題目下的差異，方向不同但結論互補。

論文、200 題題庫、所有 vendor 回應、人工標註與 AI 輔助判讀紀錄都公開在：

- Repo：https://github.com/ch-neural/Civatas-TW
- 論文資料夾：https://github.com/ch-neural/Civatas-TW/tree/main/Paper
- 論文 PDF：https://github.com/ch-neural/Civatas-TW/blob/main/Paper/paper_source/main.pdf
- Zenodo DOI：https://doi.org/10.5281/zenodo.19691574

因為這是我第一次投 arXiv、工作單位不是學術機構，依 arXiv 規定需要請一位過去曾在 cs.CL 類別發表的研究者背書（endorse）。如果您看完論文後覺得合適，想請您協助背書我的 cs.CL 投稿。

流程很簡單：我開始送稿時 arXiv 會給一組 endorsement code，我寄給您，您登入 arxiv.org 到 endorsement 頁面（https://arxiv.org/auth/endorse）貼進去、按一下就完成，不會花您超過 2 分鐘。

不論最終您是否方便協助，都很感謝您撥冗考慮。

敬祝　研安

曾澄勳 Cheng-Hsun Tseng
凌陽創新科技 · 新竹
chtseng.neural@gmail.com

---

## A.2 繁中版 — 回信給郭教授（確認改投 cs.CY）⭐ **待寄**

**收件人**：`juchunko@ntu.edu.tw`

**主旨**：`Re: arXiv 論文 endorsement — 改投 cs.CY 確認`

---

郭教授您好，

謝謝您撥冗讀完論文並給予鼓勵，特別感謝您直接指出 endorsement 的技術限制。

關於分類的建議，我完全認同改投 cs.CY。回頭檢視這篇的核心貢獻（vendor 拒答行為稽核、東西方二分法的實證反駁、Taiwan-statehood blocking、alignment 的 topic × vendor × layer 三維 framework），實質上都是 AI governance / accountability 層面的問題，而不是 NLP 方法論本身。原本選 cs.CL 是考量 LLM 相關論文的慣性，但您的觀點讓我重新想清楚這篇的定位——cs.CY 確實是更貼近的讀者社群。

因此確認調整：

- **主類別**：cs.CY (Computers and Society)
- **Cross-list**：cs.CL、cs.AI、stat.AP（submission 時向 moderators 申請，是否獲准由對方決定）

想請您協助這個 cs.CY 的 endorsement。實際流程很簡單：

1. 我這邊開始 submission，arXiv 會產一組 endorsement code
2. 我把 code 寄給您
3. 您登入 https://arxiv.org/auth/endorse → 貼 code → 一鍵 endorse（應該不會超過 2 分鐘）

預計這一兩天內會開始 submit，收到 code 後立刻轉寄給您。

再次感謝您的時間與指點。

敬祝　研安

曾澄勳 Cheng-Hsun Tseng
凌陽創新科技 · 新竹
chtseng.neural@gmail.com

---

## B. English — Ali Naseh（UMass Amherst）— **paper-notification, no endorsement ask**

**To**: `anaseh@cs.umass.edu`

**Subject**: `Taiwan-political LLM audit paper — R1dacted is our closest mechanistic analog`

---

Hi Ali,

I'm Cheng-Hsun Tseng, an independent researcher at Sunplus Innovation Technology in Hsinchu, Taiwan. Wanted to flag a paper I just posted (currently going through arXiv moderation under cs.CY; Zenodo DOI already live) — it cites your **R1dacted paper (arXiv:2505.12625)** as the closest published neighbor to one of our central puzzles, so it felt worth surfacing to you directly.

The paper audits five LLM vendors (OpenAI gpt-4o-mini, Gemini 2.5-flash-lite, Grok 4-fast, DeepSeek V3.2, Kimi k2) on 200 Traditional Chinese prompts probing Taiwan political sensitivity — 1,000 calls total, all hand-labeled. A few findings that may interest you:

- DeepSeek's overall refusal distribution looks almost identical to the U.S. vendors (JSD ~0.01). DeepSeek ↔ Kimi is actually the most distant pair in the matrix (JSD 0.200). The intuitive "East-West" clustering just doesn't hold.
- Kimi's API-level content filter blocks not only opinion prompts but also four factually neutral OT-expected prompts about RoC state institutions (legislature seats, constitutional amendments, presidential term length, flag design). I call it "Taiwan-statehood blocking" rather than "sovereignty-opinion blocking".
- **DeepSeek's on-task rate on sovereignty topics collapses to 10.3%** (CI [2.6, 23.3]) while staying at 54% on non-sovereignty prompts. No other vendor in the panel shows anything like this.

That last one is where your work comes in. In §5.4 I discuss three possible mechanisms for the DeepSeek sovereignty collapse. One hypothesis is that there's an API-level filter analog to what R1dacted documented on DeepSeek R1, but here it surfaces as RLHF-shaped soft refusal on V3.2's non-reasoning chat endpoint rather than the terminal redaction behavior you observed. My instrumentation (four-class surface-level classification) can't actually discriminate "internalized RLHF" from "hidden filter that suppresses + rewrites" — if you have intuition on whether the V3.2 sovereignty collapse is plausibly downstream of the same mechanism, or likely a separate RLHF artifact, I'd love to hear it.

Code, prompts, per-response logs, labels, and AI-judge audit trail are all public:

- Repo: https://github.com/ch-neural/Civatas-TW
- Paper PDF: https://github.com/ch-neural/Civatas-TW/blob/main/Paper/paper_source/main.pdf
- Zenodo DOI: https://doi.org/10.5281/zenodo.19691574

No ask — just making sure the paper reaches you given how directly §5.4 builds on R1dacted. Happy to dig further if any of this sparks a conversation.

Best,
Cheng-Hsun

Cheng-Hsun Tseng
Sunplus Innovation Technology · Hsinchu, Taiwan
chtseng.neural@gmail.com

---

## 寄送 tips（2026-04-22 更新）

### A.2（回 Ko 的信）

- 今天就寄，趁他還有 context。不用等週一。
- 寄出後立刻動手做 arXiv submission（§20.4 待辦 #4），產出 endorsement
  code 轉寄給 Ko → 他一鍵 endorse → moderation（1-2 天）→ 上線。

### B（Naseh paper notification）

- 這封**不是時間敏感**的（不再是 endorsement 路徑的依賴）。
- 建議時機：Zenodo v2 上傳完、arXiv ID 拿到後再寄（一次給他完整 URL 清單，
  比現在寄只有 GitHub + Zenodo DOI 更漂亮）。
- 寄 **週一至週三** UMass 當地早上（= 台灣 21:00-23:00），他隔天第一眼看到。
- 若他有回、願意討論 §5.4 的 R1dacted 關聯 → 是 v2 paper / second-rater
  / 未來 collaboration 的潛在起點。

### 備用路徑（萬一 Ko endorsement 出問題）

- 若 Ko 這邊因任何原因 endorsement 卡住（arXiv 系統延遲 / 誤會 / 他忙），
  備用 cs.CY endorser：Paul Röttger (Bocconi, XSTest)、Esin Durmus (Anthropic,
  OpinionQA)，兩位都有 cs.CY 發表紀錄。
- 目前機率不高，但若 5 天後還沒走完流程再啟動。

### 投稿流程

1. 寄 A.2 給 Ko 確認
2. 去 arxiv.org/submit → 上傳 source tarball (`bash scripts/make_arxiv_bundle.sh`)
3. arXiv 系統產 endorsement code → 轉寄給 Ko
4. Ko click → moderation → 上線
5. (可選) 寄 B 給 Naseh，通知 paper 已上 arXiv
