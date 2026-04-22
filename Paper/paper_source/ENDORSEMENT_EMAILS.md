# arXiv Endorsement Email 草稿

兩封準備好的 endorsement request email，等你寄。

---

## A. 繁中版 — 郭昱晨 教授 / 立委

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

## B. English — Ali Naseh（UMass Amherst）

**To**: `anaseh@cs.umass.edu`

**Subject**: `arXiv cs.CL endorsement request — Taiwan-political LLM audit (your R1dacted is our closest mechanistic analog)`

---

Hi Ali,

I'm Cheng-Hsun Tseng, working at Sunplus Innovation Technology in Hsinchu, Taiwan. I've just finished a paper I'd like to put on arXiv cs.CL, and I'm writing to ask whether you'd be willing to endorse me as a first-time submitter. My short pitch for why you, specifically:

The paper audits five LLM vendors (OpenAI gpt-4o-mini, Gemini 2.5-flash-lite, Grok 4-fast, DeepSeek V3.2, Kimi k2) on 200 Traditional Chinese prompts probing Taiwan political sensitivity — 1,000 calls total, all hand-labeled. A few findings that surprised me:

- DeepSeek's overall refusal distribution looks almost identical to the U.S. vendors (JSD ~0.01). DeepSeek ↔ Kimi is actually the most distant pair in the matrix (JSD 0.200). The intuitive "East-West" clustering just doesn't hold.
- Kimi's API-level content filter blocks not only opinion prompts but also four factually neutral OT-expected prompts about RoC state institutions (legislature seats, constitutional amendments, presidential term length, flag design). I call it "Taiwan-statehood blocking" rather than "sovereignty-opinion blocking".
- **DeepSeek's on-task rate on sovereignty topics collapses to 10.3%** (CI [2.6, 23.3]) while staying at 54% on non-sovereignty prompts. No other vendor in the panel shows anything like this.

That last one is where your work comes in. In §5.4 I discuss three possible mechanisms for the DeepSeek sovereignty collapse. One hypothesis is that there's an API-level filter analog that surfaces as RLHF-shaped soft refusal rather than terminal errors. I cite your **R1dacted paper (arXiv:2505.12625)** as the directly-observed precedent on DeepSeek R1, and note that whether the same mechanism is at work in the non-reasoning V3.2 endpoint is an open question my instrumentation can't answer. Your paper is basically the closest published neighbor to one of my central puzzles.

Code, prompts, per-response logs, labels, and the AI-judge audit trail are all public:

- https://github.com/ch-neural/Civatas-TW
- Paper PDF: https://github.com/ch-neural/Civatas-TW/blob/main/Paper/paper_source/main.pdf
- Zenodo DOI: https://doi.org/10.5281/zenodo.19691574

Since my email is gmail and I haven't submitted to arXiv before, I need an endorsement. If you're willing, the flow is: I start the submission, arXiv gives me a code, I send it to you, you paste it at https://arxiv.org/auth/endorse and click endorse. Should take under two minutes.

No pressure if this doesn't fit your schedule — happy to reach out to someone else. Thanks for considering it either way.

Best,
Cheng-Hsun

Cheng-Hsun Tseng
Sunplus Innovation Technology · Hsinchu, Taiwan
chtseng.neural@gmail.com

---

## 寄送 tips

- 兩封**同一天寄**（不要等一位回才寄另一位；各自 7 天冗餘）
- **週一至週三 台灣早上 9-11 AM**（對 Naseh 是他的前晚 / 週末，但他隔天進公司第一眼看到）
- 若 7 天都沒回，考慮備用 endorser：Paul Röttger (Bocconi)、Esin Durmus (Anthropic)
- 收到 endorser 同意後：去 arxiv.org/submit → 上傳 source tarball → arXiv 系統產 code → 轉寄給 endorser → 對方 click → 可 submit
