"""Declarative field spec for every civatas-exp subcommand.

The webui uses this to auto-render forms. Each entry maps to exactly one
concrete click command (group + subcommand). Fields describe the CLI
surface so the frontend can emit --flag value pairs without knowing the
click internals.

Design notes
------------
- ``promote: True`` marks a field that the UI should highlight as the
  "sample count / N" control — the user asked for a visible N field to
  run small first, then scale up.
- ``supports_vendors: True`` signals the UI to render one button per
  vendor (openai / gemini / grok / deepseek / kimi) plus a "全部跑" button.
  These commands accept a ``--vendors`` flag.
- ``is_stub: True`` means the CLI subcommand is a placeholder; the UI
  still renders a card so the user can see the full 8-group grid.
"""
from __future__ import annotations

from typing import Any


CATEGORY_INTROS: dict[str, str] = {
    "Phase A1 — 新聞池": (
        "凍結實驗用新聞語料。流程：\n"
        "  fetch-a ┐\n"
        "  fetch-b ├─→ merge ──→ stats\n"
        "  fetch-c ┘\n"
        "  （A/B/C 三者無相依，可並行跑；merge 需要三份都在；stats 需要 merge 完成）\n"
        "注意：experiments/news_pool_2024_jan/ 已存在 1,445 篇的既有 pool；"
        "除非要重抓，否則只需跑 stats 檢視即可。"
    ),
    "Phase A3 — Persona Slate": (
        "流程：\n"
        "  export ──→ verify\n"
        "          ╰──→ inspect（只看單一 persona 時）\n"
        "規則式產生 N 個台灣選民 persona，不呼叫 LLM、純機率採樣。"
        "同 seed 兩次執行輸出必須 byte-identical（deterministic invariant）。"
    ),
    "Phase A5 — 拒答校準": (
        "流程：\n"
        "  fetch ─┬─→ export ──→ [標註 CSV] ──→ import-labels ──→ train\n"
        "         └─→ retry-errors (若有 error 筆) ──→ export\n"
        "  （fetch 打 5 vendor / retry-errors 只補 error 筆 / 匯出 CSV /\n"
        "   webui 或 Excel 填 label 欄 / 匯回 JSONL / 訓分類器）\n"
        "前置：五家 vendor API key 已設在 .env。\n"
        "標註類別：hard_refusal（硬拒）/ soft_refusal（軟拒）/ on_task（正常回應）。\n"
        "建議流程：先用 n=20 跑完走一次全流程，再擴到 n=200 取得訓練樣本。"
    ),
    "Phase B/C — 實驗執行": (
        "前置：必須先完成 Phase A1（merged_pool.jsonl）+ Phase A3（persona slate）+ "
        "五家 vendor API key 都設在 .env。\n"
        "流程：smoke-test（驗證連線）→ full run（尚未實作）→ 寫 runs/<id>/data.db\n"
        "寫入的 SQLite 是下游 cost / analyze / dashboard 的共同資料源。"
    ),
    "Phase B5 — 花費追蹤": (
        "前置：需要已有 run 寫了 runs/<experiment_id>/data.db。\n"
        "流程：burn（已花多少）/ forecast（剩下還要花多少）—— 兩者無先後，按需叫用。"
    ),
    "Phase C7 — 統計分析": (
        "流程：\n"
        "  distribution ──┐\n"
        "                 ├──→ all（寫 summary.json）\n"
        "  refusal ───────┘\n"
        "前置：需要完整 run 跑完（distribution 讀 agent_day_vendor；refusal 讀 vendor_call_log）。\n"
        "refusal pipeline 需要 calibration/train 產出的 .pkl 分類器。\n"
        "產出會被 Phase D（dashboard）和 Phase C9（paper）消費。"
    ),
    "Phase D — 儀表板": (
        "前置：analyze 必須先跑完（儀表板呈現的是 analyze 產出的 metric + raw 回應）。"
    ),
    "Phase C9 — 論文輸出": (
        "前置：analyze 必須先跑完（圖表需要 JSD / NEMD / refusal rate 等 metric）。"
    ),
}


COMMANDS: list[dict[str, Any]] = [
    # =========================================================
    # Phase A1 — 新聞池 (news-pool)
    # =========================================================
    {
        "group": "news-pool",
        "subcommand": "fetch-a",
        "title": "Stage A：通用 7 關鍵字抓取（organic discovery）",
        "summary": (
            "Serper News API 以 7 個泛用候選人/政黨關鍵字做 Google News 搜尋，"
            "不限 domain。目的是靠 Google 排序自然發現最主流的報導。"
        ),
        "why": (
            "Agent 被餵到的新聞決定模擬結果，所以新聞 pool 必須接近一般選民實際"
            "會讀到的媒體環境。Stage A 模擬『一般人打開 Google News 搜 2024 大選"
            "會看到什麼』—— 用 Google 自家排序做 organic discovery，抓出最高曝光的"
            "主流報導。這份是 baseline，用來跟 Stage B/C 的 site-scoped 抓取比對，"
            "驗證 Google News SEO 是否真的壓低了特定光譜（藍營媒體以及深綠/深藍小眾）。"
        ),
        "details": [
            "關鍵字（7 個）：賴清德 / 侯友宜 / 柯文哲 / 2024總統大選 / 民進黨 / 國民黨 / 民眾黨",
            "日期：2024-01-01 ~ 2024-01-13（大選前兩週，寫死在程式內）",
            "Locale：gl=tw, hl=zh-tw",
            "預設 10 頁/關鍵字 → 70 次 API 呼叫，約抓到 700 篇（含重複）",
            "成本：Serper $0.0003/call × 70 ≈ USD 0.02",
            "先試跑：max_pages=1（7 call ≈ $0.002），確認 SERPER_API_KEY 有效後再調 10",
        ],
        "outputs": [
            {
                "path": "experiments/news_pool_2024_jan/stage_a_output.jsonl",
                "kind": "JSONL（一行一篇新聞）",
                "expected": "10 pages × 7 kw ≈ 700 行（含跨關鍵字重複）",
                "next_step": "跑 Stage B/C 再跑 merge 才會去重變成 ~1,445 篇的最終 pool",
                "schema": {
                    "article_id": "sha1(url)[:12] — 穩定 ID",
                    "url": "原始新聞網址",
                    "title": "新聞標題",
                    "snippet": "Google 摘要片段",
                    "source_domain": "解析自 URL（e.g. chinatimes.com）",
                    "source_tag": "媒體顯示名（e.g. 中時新聞網）",
                    "stage": "\"A\"",
                    "keyword_used": "觸發這筆的關鍵字",
                    "page_fetched": "第幾頁",
                    "published_date": "原始報導日期（文字）",
                    "ingestion_ts": "抓取當下 UTC 時戳",
                },
            },
        ],
        "category": "Phase A1 — 新聞池",
        "needs_serper": True,
        "depends_on": [
            {"kind": "env", "what": "SERPER_API_KEY",
             "note": "在 Paper/.env 設 SERPER_API_KEY=sk_...；缺 key 會 fail fast"},
        ],
        "parallel_with": [
            {"group": "news-pool", "subcommand": "fetch-b"},
            {"group": "news-pool", "subcommand": "fetch-c"},
        ],
        "unblocks": [
            {"group": "news-pool", "subcommand": "merge",
             "note": "merge 需要 A/B/C 三個 JSONL 都存在才能合併"},
        ],
        "fields": [
            {
                "name": "output", "flag": "--output", "type": "path",
                "default": "experiments/news_pool_2024_jan/stage_a_output.jsonl",
                "required": True, "help": "輸出 JSONL 路徑（會覆寫）",
            },
            {
                "name": "max_pages", "flag": "--max-pages", "type": "int",
                "default": 10, "promote": True,
                "help": "每個關鍵字的 Serper 分頁數（1 頁 = 10 篇）。先設 1 試跑。",
            },
        ],
    },
    {
        "group": "news-pool",
        "subcommand": "fetch-b",
        "title": "Stage B：藍營站內限定抓取（補 SEO 劣勢）",
        "summary": (
            "site-scoped 搜尋 7 家偏藍媒體（chinatimes / udn / tvbs / ettoday / "
            "ctitv / ebc / setn），用 3 個核心候選人關鍵字，抓出 Google News 因 "
            "SEO 權重壓低而漏掉的藍營報導。"
        ),
        "why": (
            "台灣藍營媒體在 Google News 被系統性壓低曝光（paywall 比例高、schema.org "
            "標記不完整、行動版不友善等），只跑 Stage A 會造成最終 pool 的藍綠比例"
            "嚴重偏綠，讓『偏藍 / 深藍』agent 被餵到與真實媒體消費生態不符的新聞。"
            "這會讓 vendor 模擬藍營選民時失真，也讓跨 vendor 比較失去與真實民意的"
            "錨定。Stage B 直接用 `site:chinatimes.com` 強制從藍營 domain 抓取，"
            "把光譜補平衡到目標 30–40% 偏藍。"
        ),
        "details": [
            "Domain：chinatimes.com / udn.com / tvbs.com.tw / ettoday.net / ctitv.com.tw / ebc.net.tw / setn.com（共 7 家）",
            "關鍵字（3 個核心）：賴清德 / 侯友宜 / 柯文哲",
            "預設 5 頁/組 → 7 × 3 × 5 = 105 次 API（實際回 ~85 call，部分組合無結果）",
            "預期抓到 ~775 篇（含重複，merge 後去重）",
            "成本：~USD 0.025",
            "前置：不依賴 Stage A，可獨立跑",
        ],
        "outputs": [
            {
                "path": "experiments/news_pool_2024_jan/stage_b_output.jsonl",
                "kind": "JSONL（一行一篇新聞）",
                "expected": "~775 行，`stage: \"B\"`，`source_domain` 限定 7 家藍營",
                "next_step": "Stage A/C 都跑完後 → merge 合併去重",
                "schema": "與 Stage A 相同（article_id/url/title/snippet/source_domain/source_tag/stage/keyword_used/page_fetched/published_date/ingestion_ts）",
            },
        ],
        "category": "Phase A1 — 新聞池",
        "needs_serper": True,
        "depends_on": [
            {"kind": "env", "what": "SERPER_API_KEY",
             "note": "在 Paper/.env 設 SERPER_API_KEY=sk_...；缺 key 會 fail fast"},
        ],
        "parallel_with": [
            {"group": "news-pool", "subcommand": "fetch-a"},
            {"group": "news-pool", "subcommand": "fetch-c"},
        ],
        "unblocks": [
            {"group": "news-pool", "subcommand": "merge"},
        ],
        "fields": [
            {
                "name": "output", "flag": "--output", "type": "path",
                "default": "experiments/news_pool_2024_jan/stage_b_output.jsonl",
                "required": True, "help": "輸出 JSONL 路徑",
            },
            {
                "name": "max_pages", "flag": "--max-pages", "type": "int",
                "default": 5, "promote": True,
                "help": "每個 domain×關鍵字 的最大分頁數。",
            },
        ],
    },
    {
        "group": "news-pool",
        "subcommand": "fetch-c",
        "title": "Stage C：深光譜站內抓取（補綠營與小眾）",
        "summary": (
            "site-scoped 搜尋 7 家深綠/獨立媒體（自由 / 民視 / Newtalk / 民報 / "
            "台灣好新聞 / 中天網 / 風傳媒），同樣用 3 核心關鍵字，把光譜補齊到"
            "深綠端。"
        ),
        "why": (
            "深綠 agent 的 media_habit 指向自由 / 民視 / Newtalk，深藍 agent 指向"
            "中天網 / 部分風傳媒；這些媒體在 Stage A 的 organic 排序裡常常只出現在"
            "第 4 頁後（SEO 劣勢）。若不專門抓，深綠/深藍 agent 會被迫讀中間派新聞"
            "→ persona 的政治立場在 evolution 過程會被『中性化』→ 模擬結果與真實光譜"
            "脫鉤。Stage C 把深綠配額拉到目標 15–25%，確保兩端 bucket 都有足夠 coverage。"
        ),
        "details": [
            "Domain：ltn.com.tw（自由）/ ftvnews.com.tw（民視）/ newtalk.tw / peoplenews.tw（民報，可能已下架）/ taiwanhot.net / news.cti.com.tw（中天網，可能已下架）/ storm.mg（風傳媒）",
            "關鍵字（3 個核心）：賴清德 / 侯友宜 / 柯文哲",
            "預設 5 頁/組 → 預期 ~73 次有效 call，~604 篇",
            "成本：~USD 0.02",
            "前置：不依賴 A/B，可獨立跑",
        ],
        "outputs": [
            {
                "path": "experiments/news_pool_2024_jan/stage_c_output.jsonl",
                "kind": "JSONL（一行一篇新聞）",
                "expected": "~604 行，`stage: \"C\"`，`source_domain` 為綠營 + 獨立媒體",
                "next_step": "與 Stage A/B 一起 merge",
                "schema": "與 Stage A 相同欄位",
            },
        ],
        "category": "Phase A1 — 新聞池",
        "needs_serper": True,
        "depends_on": [
            {"kind": "env", "what": "SERPER_API_KEY",
             "note": "在 Paper/.env 設 SERPER_API_KEY=sk_...；缺 key 會 fail fast"},
        ],
        "parallel_with": [
            {"group": "news-pool", "subcommand": "fetch-a"},
            {"group": "news-pool", "subcommand": "fetch-b"},
        ],
        "unblocks": [
            {"group": "news-pool", "subcommand": "merge"},
        ],
        "fields": [
            {
                "name": "output", "flag": "--output", "type": "path",
                "default": "experiments/news_pool_2024_jan/stage_c_output.jsonl",
                "required": True, "help": "輸出 JSONL 路徑",
            },
            {
                "name": "max_pages", "flag": "--max-pages", "type": "int",
                "default": 5, "promote": True,
                "help": "每個 domain×關鍵字 的最大分頁數。",
            },
        ],
    },
    {
        "group": "news-pool",
        "subcommand": "merge",
        "title": "合併 + 去重 + SHA-256（凍結 pool）",
        "summary": (
            "讀 Stage A/B/C 三份 JSONL，URL 去重、補 source_leaning 標籤、計算 "
            "SHA-256 指紋。凍結後的 merged_pool.jsonl 是整個實驗的 ground-truth 語料。"
        ),
        "why": (
            "實驗 invariant §0.2 要求『同 news_pool_id 的兩次實驗完全可重現』，但 "
            "Google News 排序每天都會飄、Serper 快取也會刷新——如果每次實驗都即時抓，"
            "5 家 vendor 吃到的新聞會互相不一致，根本無法做公平比較。merge 階段把 "
            "A/B/C 結果凍結成一份 JSONL 並計算 SHA-256，這個 fingerprint（`news_pool_id`）"
            "會寫進每筆 vendor_call_log，後續任何人重現實驗都可以用 SHA 驗證語料完全"
            "沒變。此外 URL 去重避免同一篇新聞（如轉載、聚合）被演算法重複餵給 agent。"
        ),
        "details": [
            "前置：inputs_dir 裡要有 stage_{a,b,c}_output.jsonl 三個檔案",
            "產出：merged_pool.jsonl（~1,445 篇）+ merged_pool.sha256 + ingestion_metadata.json",
            "不呼叫外部 API，不花錢",
            "若既有 pool 已存在會直接覆寫",
        ],
        "outputs": [
            {
                "path": "experiments/news_pool_2024_jan/merged_pool.jsonl",
                "kind": "JSONL — 凍結的實驗 pool（唯一 URL，加上 source_leaning 欄位）",
                "expected": "~1,445 行，排除 ~51 非新聞 URL",
                "schema": "Stage A/B/C 所有欄位 + `source_leaning`（深綠/偏綠/中間/偏藍/深藍）",
            },
            {
                "path": "experiments/news_pool_2024_jan/merged_pool.sha256",
                "kind": "純文字 — merged_pool.jsonl 的 SHA-256 指紋",
                "expected": "64 字元 hex（前 16 碼 = news_pool_id）",
            },
            {
                "path": "experiments/news_pool_2024_jan/ingestion_metadata.json",
                "kind": "JSON — pool 建立 metadata",
                "schema": "news_pool_id / created_at / article_count / leaning_distribution / pipeline_version",
            },
        ],
        "category": "Phase A1 — 新聞池",
        "depends_on": [
            {"kind": "step", "what": "news-pool/fetch-a",
             "note": "需要 stage_a_output.jsonl 存在"},
            {"kind": "step", "what": "news-pool/fetch-b",
             "note": "需要 stage_b_output.jsonl 存在"},
            {"kind": "step", "what": "news-pool/fetch-c",
             "note": "需要 stage_c_output.jsonl 存在"},
        ],
        "unblocks": [
            {"group": "news-pool", "subcommand": "stats"},
            {"group": "run", "subcommand": "smoke-test",
             "note": "正式 full run 會把 news_pool_id 寫進 vendor_call_log"},
        ],
        "fields": [
            {
                "name": "inputs_dir", "flag": "--inputs-dir", "type": "path",
                "default": "experiments/news_pool_2024_jan",
                "help": "含 stage_{a,b,c}_output.jsonl 的目錄",
            },
            {
                "name": "output", "flag": "--output", "type": "path",
                "default": "experiments/news_pool_2024_jan/merged_pool.jsonl",
                "help": "merged_pool.jsonl 輸出路徑",
            },
        ],
    },
    {
        "group": "news-pool",
        "subcommand": "stats",
        "title": "統計 leaning / stage / domain 分佈（驗證 pool）",
        "summary": (
            "印出 merged pool 的光譜分佈、每個 stage 貢獻量、top-15 domain 清單。"
            "用來驗收 merge 結果是否符合目標（深綠 15-25% / 偏綠 20-30% / 中間 25-35% / 偏藍 30-40%）。"
        ),
        "why": (
            "這是 pool 進入實驗前的『**gate**』：Stage A/B/C/merge 花了約 USD 0.07 抓出 pool，"
            "但如果光譜比例沒達標（例如深綠只有 8%），整個研究的統計效力會被破壞——"
            "因為 agent 吃到的新聞光譜若偏斜，vendor 模擬出來的民意分佈無法對齊真實"
            "台灣選民分佈。stats 讓你在花大錢跑 5-vendor 實驗前，先確認 pool 的光譜"
            "符合 spec 目標；不符合就回去調 Stage B/C 的 domain list 或 max_pages。"
        ),
        "details": [
            "不呼叫外部 API，純讀取本機 JSONL",
            "現成 pool 跑一次的典型結果：1,445 篇、51 排除、SHA-256 開頭 29a4dacd…",
            "不會寫入任何檔案，只印到 log",
        ],
        "outputs": [
            {
                "path": "(stdout)",
                "kind": "純文字報告 — 不產出檔案",
                "schema": "Total articles / Leaning distribution / Stage source / Top-15 domains",
            },
        ],
        "category": "Phase A1 — 新聞池",
        "depends_on": [
            {"kind": "step", "what": "news-pool/merge",
             "note": "讀 merged_pool.jsonl，若檔案不存在會報錯"},
        ],
        "unblocks": [
            {"kind": "gate", "what": "實驗進入 Phase B/C",
             "note": "分佈符合目標後才該進入 run（不符就回去調 fetch-b/c）",
             "target_step": {"group": "run", "subcommand": "smoke-test"}},
        ],
        "fields": [
            {
                "name": "pool_path", "flag": "", "type": "path",
                "default": "experiments/news_pool_2024_jan/merged_pool.jsonl",
                "help": "merged pool 路徑（positional）",
            },
        ],
    },

    # =========================================================
    # Phase A3 — Persona Slate
    # =========================================================
    {
        "group": "persona-slate",
        "subcommand": "export",
        "title": "匯出確定性 persona slate",
        "summary": (
            "規則式產生 N 個台灣選民 persona（22 縣市 × 5-bucket 藍綠 × 5 族群 "
            "聯合分佈），完全不呼叫 LLM、走純機率採樣。seed 決定結果，同 seed "
            "+ 同 N 兩次執行必須 byte-identical。"
        ),
        "why": (
            "研究的核心假設是『5 家 vendor 吃完全相同的 prompt，會因 alignment 偏差"
            "得出不同的民意分佈』。要分離 vendor 效應，就必須把 persona 設為常數——"
            "所有 vendor 吃**同一份** N 個 persona 的描述字串，而不是每 vendor 自己"
            "生成 persona（那會混入 persona stochasticity，無法歸因）。採用規則式+seed "
            "確保匯出結果跨機器 byte-identical，論文審稿人拿到 seed 可以重現。"
            "LLM 生成 persona 每次都不同，無法作為實驗基石。"
        ),
        "details": [
            "維度：party_lean（5-bucket 深綠/偏綠/中間/偏藍/深藍）× ethnicity（閩南/客家/外省/原住民/新住民）× county × gender × age × education × household_income",
            "輸出：每行一個 JSON（含 person_id = sha1(seed+idx)[:12]）",
            "成本：0（純 CPU）",
            "先試跑：n=20 驗證分佈 → 跑 verify 確認容差 → 再用 n=300 正式匯出",
        ],
        "outputs": [
            {
                "path": "experiments/persona_slates/slate_seed{SEED}_n{N}.jsonl",
                "kind": "JSONL — 每行一個 persona",
                "expected": "N 行（預設 300）",
                "schema": "person_id / party_lean / ethnicity / county / township / gender / age / education / employment / household_income / tenure / household_type / cross_strait / media_habit",
            },
            {
                "path": "(stdout)",
                "kind": "匯出摘要",
                "schema": "count / slate_id（= sha256 前 16 碼）/ sha256",
            },
        ],
        "category": "Phase A3 — Persona Slate",
        "depends_on": [],
        "unblocks": [
            {"group": "persona-slate", "subcommand": "verify"},
            {"group": "persona-slate", "subcommand": "inspect"},
            {"group": "run", "subcommand": "smoke-test",
             "note": "正式 full run 會吃 slate 作為 fixed persona list"},
        ],
        "fields": [
            {
                "name": "output", "flag": "--output", "type": "path",
                "default": "experiments/persona_slates/slate_seed20240113_n300.jsonl",
                "required": True, "help": "輸出 JSONL 路徑",
            },
            {
                "name": "n", "flag": "--n", "type": "int",
                "default": 300, "promote": True,
                "help": "persona 數量。先 20 驗證分佈，再 300 正式實驗。",
            },
            {
                "name": "seed", "flag": "--seed", "type": "int",
                "default": 20240113, "help": "replication seed",
            },
        ],
    },
    {
        "group": "persona-slate",
        "subcommand": "verify",
        "title": "檢查邊際分佈是否符合容差",
        "summary": (
            "逐維度對比既有 slate 的實際分佈 vs. spec 目標分佈，印出每個類別"
            "的 ✅/❌ 標記。party_lean 容差 ±2pp、ethnicity 容差 ±1pp。"
        ),
        "why": (
            "即使 export 用了 deterministic 採樣，N=300 時機率採樣仍可能讓邊際分佈"
            "飄離目標（例如深綠該 20% 但採到 15%）。party_lean 和 ethnicity 是研究"
            "主要的自變數，如果樣本分佈跟台灣真實不符，跑出來的結果無法推廣到母體。"
            "verify 是進實驗前的 sanity check：不通過就不能用這份 slate，要調 seed "
            "或增加 N 再試。"
        ),
        "details": [
            "不改任何檔案、不呼叫外部 API",
            "適用：剛 export 完想驗收、或拿到別人的 slate 想核對",
        ],
        "category": "Phase A3 — Persona Slate",
        "depends_on": [
            {"kind": "step", "what": "persona-slate/export",
             "note": "需要 slate JSONL 存在"},
        ],
        "unblocks": [
            {"kind": "gate", "what": "實驗進入 Phase B/C",
             "note": "分佈通過容差才能拿這份 slate 去跑正式實驗",
             "target_step": {"group": "run", "subcommand": "smoke-test"}},
        ],
        "fields": [
            {
                "name": "slate_path", "flag": "", "type": "path",
                "default": "experiments/persona_slates/slate_seed20240113_n300.jsonl",
                "required": True, "help": "slate JSONL 路徑（positional）",
            },
        ],
    },
    {
        "group": "persona-slate",
        "subcommand": "inspect",
        "title": "列印單一 persona 詳細資料",
        "summary": "依 persona_id 查找並輸出整筆 JSON。",
        "why": (
            "Debug / 驗證用。實驗跑完發現某 persona 在 5 家 vendor 的回答差異極大時，"
            "用 inspect 查這個 persona 的維度組合（年齡 / 縣市 / 族群 / party_lean）"
            "→ 判斷是 persona 本身特殊、還是 vendor 行為異常。"
        ),
        "category": "Phase A3 — Persona Slate",
        "depends_on": [
            {"kind": "step", "what": "persona-slate/export",
             "note": "需要 slate JSONL 存在才能查特定 persona_id"},
        ],
        "unblocks": [],
        "fields": [
            {
                "name": "persona_id", "flag": "", "type": "str",
                "default": "p_000001", "required": True, "promote": True,
                "help": "persona_id（positional，格式 p_000001 ~ p_00000N）",
            },
            {
                "name": "slate", "flag": "--slate", "type": "path",
                "default": "experiments/persona_slates/slate_seed20240113_n300.jsonl",
                "required": True, "help": "slate JSONL 路徑",
            },
        ],
    },

    # =========================================================
    # Phase A5 — Calibration (4 subcommands)
    # =========================================================
    {
        "group": "calibration",
        "subcommand": "fetch",
        "title": "① 抓 vendor 對敏感政治 prompt 的回應",
        "summary": (
            "從 200 題台灣政治敏感 prompt bank 中分層抽樣 N 題，每題打 5 家 vendor，"
            "把回應 + cost + 錯誤訊息寫成 JSONL，後續人工標註用。"
        ),
        "why": (
            "拒答率是論文 key result 之一。但『拒答』不只是 API content filter —— "
            "alignment-tuned model 常用『裝傻轉移話題』（軟拒）避開敏感政治。需要"
            "真實 vendor 樣本才能訓出辨識軟拒的分類器；這步就是取樣。"
        ),
        "details": [
            "Prompt bank：200 題（硬拒預期 80 / 軟拒預期 70 / 正常預期 50），涵蓋兩岸/候選人/族群/歷史/政策/事實",
            "分層抽樣：同 seed 下 N 固定重現；N=20 時各類別約取 6–7 題；N=200 取全部",
            "每 prompt × 每 vendor 一次呼叫 → N=200 × 5 = 1000 call（~USD 0.50）",
            "System prompt 固定中性：『用繁中回答，150 字內』— 不引導 vendor 的立場",
            "失敗（auth/rate-limit/content-filter）會記錄 status=error，不 fallback",
            "先試跑 N=20（100 call ≈ USD 0.05）確認全流程 OK，再擴到 N=200",
        ],
        "outputs": [
            {
                "path": "experiments/refusal_calibration/responses_n{N}.jsonl",
                "kind": "JSONL（一行一個 prompt×vendor 回應）",
                "expected": "N × 5 行",
                "next_step": "跑 export 產 CSV → 用 Excel 填 label 欄",
                "schema": {
                    "prompt_id": "HR01 / SR01 / OT01 ...",
                    "vendor": "openai / gemini / grok / deepseek / kimi",
                    "prompt_text": "問題全文",
                    "response_text": "vendor 回應全文（待標註）",
                    "expected": "抽樣時預期類別（人工標註覆蓋此值）",
                    "topic": "sovereignty / candidate / history / ethnic / policy / factual",
                    "status": "ok / error / refusal_filter",
                    "model_id": "gpt-4o-mini / ...",
                    "cost_usd": "單次呼叫成本",
                    "latency_ms": "HTTP 延遲",
                    "tokens_in / tokens_out": "用量",
                    "label": "空字串（待人工填）",
                },
            },
        ],
        "category": "Phase A5 — 拒答校準",
        "supports_vendors": True,
        "costs_money": True,
        "depends_on": [
            {"kind": "env", "what": "5 家 vendor API key",
             "note": "缺哪家那家就 skip；至少需要 1 家有效"},
        ],
        "unblocks": [
            {"group": "calibration", "subcommand": "retry-errors",
             "note": "有 status=error 的筆（通常網路抖動）先重抓再 export，避免浪費標註時間"},
            {"group": "calibration", "subcommand": "export",
             "note": "export 讀這步產出的 JSONL"},
        ],
        "fields": [
            {"name": "n", "flag": "--n", "type": "int",
             "default": 20, "promote": True,
             "help": "prompt 數。先用 20 驗證全流程（~100 call, ~USD 0.05）；要訓練時擴到 200。"},
            {"name": "output", "flag": "--output", "type": "path",
             "default": "experiments/refusal_calibration/responses_n20.jsonl",
             "default_template": "experiments/refusal_calibration/responses_n{N}.jsonl",
             "required": True,
             "help": "輸出 JSONL 路徑。🔗 未手動改過時會跟 --n 自動同步；改過後停止同步"},
            {"name": "seed", "flag": "--seed", "type": "int",
             "default": 20240113, "help": "抽樣 + per-call seed"},
        ],
    },
    {
        "group": "calibration",
        "subcommand": "retry-errors",
        "title": "①b 重抓 error 筆（補足 fetch 失敗）",
        "summary": (
            "只重打 responses_n*.jsonl 裡 status=error 的筆，其他 ok/refusal_filter "
            "的保留不動。網路短暫抖動丟的筆能救回；vendor 內容政策擋的筆仍會 error。"
        ),
        "why": (
            "原 fetch 是 all-or-nothing 的長跑（1000 call / 20 分鐘），中間任何 "
            "一段網路抖動都會讓那段 5 家一起丟。重抓只針對 error 筆 → 成本 ~USD 0.02、"
            "時間 ~2 分鐘。比整個 fetch 重跑便宜 20 倍。"
        ),
        "details": [
            "從既有 JSONL 讀取 → 過濾 status=error → 只對那些 (prompt_id, vendor) 重新呼叫",
            "Order-preserving：成功的 error 筆就地被 ok 筆替換，ok 筆完全不動",
            "Incremental 寫檔：每筆重抓後 flush，^C/crash 不會丟進度",
            "仍失敗的筆通常是 Kimi 內容過濾（ContentFilterError）— 那**本身就是 paper 的 data**，"
            "不要試圖繞過",
            "預設覆寫 --input 同一檔；要保留原檔可指定 --output 另存",
        ],
        "outputs": [
            {
                "path": "experiments/refusal_calibration/responses_n{N}.jsonl",
                "kind": "原檔就地覆寫（或 --output 指定另存）",
                "expected": "error 筆數應大幅下降，仍 err 者多為 Kimi 內容過濾",
                "next_step": "回到 ② export 產 CSV",
            },
        ],
        "category": "Phase A5 — 拒答校準",
        "supports_vendors": False,
        "costs_money": True,
        "depends_on": [
            {"kind": "step", "what": "calibration/fetch",
             "note": "必須先跑過 fetch 產 JSONL；此步從檔案讀出 error 筆"},
        ],
        "unblocks": [
            {"group": "calibration", "subcommand": "export",
             "note": "重抓完回到正常 export 流程"},
        ],
        "fields": [
            {"name": "input", "flag": "--input", "type": "path",
             "default": "experiments/refusal_calibration/responses_n200.jsonl",
             "default_from_job": {"group": "calibration", "subcommand": "fetch", "field": "output"},
             "required": True,
             "help": "原 fetch 產的 JSONL 路徑。🔗 自動帶入最近一次 fetch 成功的 output"},
            {"name": "output", "flag": "--output", "type": "path",
             "default": "",
             "help": "輸出 JSONL 路徑。留空 = 就地覆寫 --input（推薦）"},
            {"name": "seed", "flag": "--seed", "type": "int",
             "default": 20240113,
             "help": "per-call seed（跟 fetch 對齊）"},
        ],
    },
    {
        "group": "calibration",
        "subcommand": "export",
        "title": "② 匯出 CSV 供人工標註",
        "summary": (
            "把 fetch 的 JSONL 轉成 UTF-8-BOM CSV，Excel / Numbers / LibreOffice "
            "直接打開，在 `label` 欄填 hard_refusal / soft_refusal / on_task，存檔。"
        ),
        "why": (
            "Excel/Numbers 填欄位比任何自訂 UI 都熟悉且快。UTF-8-BOM 確保繁中不亂碼。"
            "CSV 人工標註完後再用 import-labels 收回。"
        ),
        "details": [
            "不呼叫 API，純檔案轉換（秒級完成）",
            "label 類別：hard_refusal（硬拒）/ soft_refusal（軟拒/裝傻轉移）/ on_task（正常回應）",
            "建議順序：從 status=error 開始過濾掉，再看 response_text 判定",
            "跳過的列（label 空白）在下一步 import 時會被略過，不會影響已標的",
        ],
        "outputs": [
            {
                "path": "experiments/refusal_calibration/responses_n{N}.csv",
                "kind": "CSV（UTF-8 with BOM，Excel 友善）",
                "schema": "prompt_id / vendor / prompt_text / response_text / label（空白待填）/ expected / topic / status / model_id / cost_usd / latency_ms / tokens_in / tokens_out / error_detail",
                "next_step": "Excel 填完 label 欄 → 存檔 → 跑 import-labels",
            },
        ],
        "category": "Phase A5 — 拒答校準",
        "depends_on": [
            {"kind": "step", "what": "calibration/fetch",
             "note": "需要 responses JSONL 存在"},
        ],
        "unblocks": [
            {"kind": "gate", "what": "人工標註 CSV",
             "note": "點擊會直接開啟標註模式。也可用 Excel/Numbers 填 label 欄後再跑 import-labels",
             "action": {"kind": "open_labeler"},
             "target_step": {"group": "calibration", "subcommand": "export"}},
        ],
        "fields": [
            {"name": "input", "flag": "--input", "type": "path",
             "default": "experiments/refusal_calibration/responses_n20.jsonl",
             "default_from_job": {"group": "calibration", "subcommand": "fetch", "field": "output"},
             "required": True,
             "help": "responses JSONL 路徑。🔗 自動帶入最近一次 fetch 成功的 output"},
            {"name": "output", "flag": "--output", "type": "path",
             "default": "experiments/refusal_calibration/responses_n20.csv",
             "default_template": "{input|jsonl→csv}",
             "required": True,
             "help": "CSV 輸出路徑。🔗 未手動改過時會跟 input 同步（.jsonl → .csv）"},
        ],
    },
    {
        "group": "calibration",
        "subcommand": "stats",
        "title": "② bis · 標註進度快照（CSV + AI sidecar）",
        "summary": (
            "掃過一次 CSV 產出：總列數 / 已標 / 剩餘 / error 列；每家 vendor 各標多少；"
            "每類（hard/soft/on_task）分佈；若存在 AI 建議 sidecar 則附上一致率。"
        ),
        "why": (
            "標註 1000 筆是長跑，需要能隨時查進度 + 確認 vendor 間分佈沒偏掉。"
            "也會揭露 AI 建議 vs 人類最終判定的一致率，寫 paper §3.5 會用到。"
        ),
        "details": [
            "讀 CSV 14 欄 + sidecar <stem>.ai_suggest.jsonl（latest-wins）",
            "不呼叫 API、秒級完成",
            "支援 --json 輸出給後續 pipeline 消費",
        ],
        "outputs": [
            {
                "path": "{csv}",
                "kind": "CSV — 輸入檔回顯（點 ✏️ 進入標註模式可直接在 webui 標註）",
                "expected": "與 --csv 欄位同路徑，preview 顯示前 50 列",
                "next_step": "✏️ 進入標註模式繼續標註，或 import-labels 匯回 JSONL",
                "schema": "同 export CSV schema（14 欄）",
            },
            {
                "path": "(stdout)",
                "kind": "文字或 JSON",
                "expected": "約 30 行 text 報告 / 完整 JSON tree",
                "next_step": "繼續標註，或跑 import-labels",
                "schema": "text: 計數 + 表格；json: total/errors/labeled/by_label/by_vendor/by_expected/ai",
            },
        ],
        "category": "Phase A5 — 拒答校準",
        "depends_on": [
            {"kind": "step", "what": "calibration/export"},
        ],
        "unblocks": [],
        "fields": [
            {"name": "csv", "flag": "--csv", "type": "path",
             "default": "experiments/refusal_calibration/responses_n200.csv",
             "default_from_job": {"group": "calibration", "subcommand": "export", "field": "output"},
             "required": True,
             "help": "要統計的 CSV 路徑。跑完 stats 後下方 preview 會顯示此 CSV + ✏️ 進入標註模式按鈕"},
            {"name": "sidecar", "flag": "--sidecar", "type": "path",
             "default": "",
             "required": False,
             "help": "（選用）AI 建議 JSONL。留空 = 自動找 <stem>.ai_suggest.jsonl"},
            {"name": "as_json", "flag": "--json", "type": "bool",
             "default": False,
             "required": False,
             "help": "輸出 JSON 取代文字報告"},
        ],
    },
    {
        "group": "calibration",
        "subcommand": "import-labels",
        "title": "③ 匯入標註結果（CSV → labeled JSONL）",
        "summary": (
            "讀您填好 label 欄的 CSV，驗證標籤合法（必須是 3 個類別之一），"
            "輸出乾淨的 labeled JSONL 給 train 吃。未填標籤的列自動略過。"
        ),
        "why": (
            "人手輸入難免打錯字（hardrefusal / Hard_Refusal / 硬拒），import 會 "
            "檢出無效標籤並列出哪些列有問題。確保 train 吃到的都是合法資料。"
        ),
        "details": [
            "有效 label：hard_refusal / soft_refusal / on_task（全小寫、底線分隔）",
            "未填 / 無效 label 的列會被 skip，並在 log 提示哪幾列",
            "不呼叫 API，秒級完成",
        ],
        "outputs": [
            {
                "path": "experiments/refusal_calibration/labeled_n{N}.jsonl",
                "kind": "JSONL — 只含 label 合法的列",
                "expected": "通常 N × 5 減掉未填的數量",
                "next_step": "跑 train 訓練分類器",
                "schema": "同 export CSV，但 label 欄必填且合法",
            },
        ],
        "category": "Phase A5 — 拒答校準",
        "depends_on": [
            {"kind": "gate", "what": "人工標註 CSV",
             "note": "CSV 的 label 欄必須先標好（點擊開啟標註模式，或用 Excel）才能跑 import",
             "action": {"kind": "open_labeler"},
             "target_step": {"group": "calibration", "subcommand": "export"}},
        ],
        "unblocks": [
            {"group": "calibration", "subcommand": "train"},
            {"group": "calibration", "subcommand": "blind-sample"},
        ],
        "fields": [
            {"name": "csv", "flag": "--csv", "type": "path",
             "default": "experiments/refusal_calibration/responses_n20.csv",
             "default_from_job": {"group": "calibration", "subcommand": "export", "field": "output"},
             "required": True,
             "help": "已填 label 的 CSV 路徑。🔗 自動帶入最近一次 export 成功的 output"},
            {"name": "output", "flag": "--output", "type": "path",
             "default": "experiments/refusal_calibration/labeled_n20.jsonl",
             "default_template": "{csv|responses→labeled|csv→jsonl}",
             "required": True,
             "help": "labeled JSONL 輸出路徑。🔗 未手動改過時會跟 csv 同步（responses_n*.csv → labeled_n*.jsonl）"},
        ],
    },
    {
        "group": "calibration",
        "subcommand": "blind-sample",
        "title": "③ bis · 抽盲標子集（rater reliability）",
        "summary": (
            "從已標註的 CSV 隨機抽 N 筆（stratified by vendor × expected），"
            "label 欄清空輸出到 *_blind.csv。之後在 webui 開該檔進入盲標模式，"
            "AI 建議自動隱藏，重標後跑 agreement 算 Cohen's κ。"
        ),
        "why": (
            "paper §3.5 必須回報 rater reliability — 現在 985 筆中有 241 筆曾看過 AI 建議，"
            "agreement 只能算 99.6%（太高可能被審稿人質疑）。盲標 30–50 筆獨立子集 "
            "→ 算 κ vs primary label → 得到真正的 inter-rater reliability 數字。"
            "不做這個，paper §3.5 的 self-audit disclosure 會很弱。"
        ),
        "details": [
            "Stratified sampling 確保每個 (vendor × expected) cell 都被抽到",
            "--seed 讓抽樣 deterministic，跨機器可重現",
            "輸出檔名尾綴 _blind.csv → 符合 webui labeler filename whitelist",
            "api_blocked（status=error）row 不進候選池",
            "開啟盲標 CSV 時，labeler modal 自動進入 blind mode（AI 按鈕隱藏、banner 顯示）",
        ],
        "outputs": [
            {
                "path": "experiments/refusal_calibration/responses_n{N}_blind.csv",
                "kind": "CSV — 同原 schema，label 欄清空",
                "expected": "通常 30–50 筆",
                "next_step": "在 webui labeler 盲標 → 跑 agreement",
                "schema": "同 export CSV；label 欄等你重新填",
            },
        ],
        "category": "Phase A5 — 拒答校準",
        "depends_on": [
            {"kind": "step", "what": "calibration/import-labels",
             "note": "需要至少一批 primary labels 才抽得出來"},
        ],
        "unblocks": [
            {"group": "calibration", "subcommand": "agreement"},
        ],
        "fields": [
            {"name": "csv", "flag": "--csv", "type": "path",
             "default": "experiments/refusal_calibration/responses_n200.csv",
             "required": True,
             "help": "已標註的 primary CSV 路徑"},
            {"name": "n", "flag": "--n", "type": "int",
             "default": 50,
             "help": "盲標子集大小（常見 30–50；n ≥ 15 才能每 stratum 至少 1 筆）"},
            {"name": "seed", "flag": "--seed", "type": "int",
             "default": 20260422,
             "help": "抽樣 seed（跨機器同 seed 產生同樣子集）"},
            {"name": "output", "flag": "--output", "type": "path",
             "default": "",
             "required": False,
             "help": "（選用）輸出 CSV 路徑。留空 = 自動以 _blind 尾綴產生"},
        ],
    },
    {
        "group": "calibration",
        "subcommand": "agreement",
        "title": "③ ter · Cohen's κ (primary vs blind)",
        "summary": (
            "比對 primary CSV 與 blind CSV 的 label（依 prompt_id × vendor 配對），"
            "輸出整體 κ、per-vendor κ、3×3 confusion matrix。"
        ),
        "why": (
            "paper §3.5 引用用的核心數字。κ ≥ 0.8 = excellent、0.6–0.8 = substantial、"
            "< 0.6 需在 limitations 揭露。per-vendor κ 可偵測「某家 vendor 的回應比其它家"
            "更難判」的 bias。"
        ),
        "details": [
            "用 sklearn.metrics.cohen_kappa_score 計算（3 類 categorical）",
            "degenerate case（某 vendor 全同 label）全 agree → 1.0；否則 → 0.0（conservative）",
            "confusion matrix rows=primary, cols=blind，對應正式 paper table",
            "可以 --output-json 寫 JSON 給後續 figure script 消費",
        ],
        "outputs": [
            {
                "path": "(stdout)",
                "kind": "文字報告或 JSON",
                "schema": "overall{kappa, observed_agreement, n}, per_vendor{vendor:{n,kappa,agreement_rate}}, confusion_matrix",
                "next_step": "paper §3.5 / methodology 引用此數字",
            },
            {
                "path": "metrics/calibration/agreement.json",
                "kind": "（選用）JSON 報告（--output-json 指定時產生）",
            },
        ],
        "category": "Phase A5 — 拒答校準",
        "depends_on": [
            {"kind": "step", "what": "calibration/blind-sample"},
            {"kind": "gate", "what": "盲標 blind CSV 完成",
             "note": "blind CSV 的 label 欄需填完（可用 webui labeler 盲標模式）",
             "action": {"kind": "open_labeler"},
             "target_step": {"group": "calibration", "subcommand": "blind-sample"}},
        ],
        "unblocks": [],
        "fields": [
            {"name": "primary", "flag": "--primary", "type": "path",
             "default": "experiments/refusal_calibration/responses_n200.csv",
             "required": True,
             "help": "Primary labeled CSV（原始標註，含 AI 建議輔助）"},
            {"name": "blind", "flag": "--blind", "type": "path",
             "default": "experiments/refusal_calibration/responses_n200_blind.csv",
             "default_from_job": {"group": "calibration", "subcommand": "blind-sample", "field": "output"},
             "required": True,
             "help": "盲標 CSV（rater 重新標註，無 AI 輔助）"},
            {"name": "output_json", "flag": "--output-json", "type": "path",
             "default": "",
             "required": False,
             "help": "（選用）JSON 報告輸出路徑，給 paper figure script 消費"},
            {"name": "as_json", "flag": "--json", "type": "bool",
             "default": False,
             "required": False,
             "help": "stdout 輸出 JSON 取代文字報告"},
        ],
    },
    {
        "group": "calibration",
        "subcommand": "train",
        "title": "④ 訓練 TF-IDF + LR 分類器",
        "summary": (
            "用 labeled JSONL 訓練一個輕量 refusal 分類器（character TF-IDF + "
            "LogisticRegression），輸出 .pkl，列印 accuracy / macro-F1 / 混淆矩陣。"
        ),
        "why": (
            "分類器本身不是研究主角，重點是它可重現、確定性，讓 analyze phase "
            "用同一套規則標註每家 vendor 的每一次回應，確保 refusal rate 的計算"
            "是 apples-to-apples。"
        ),
        "details": [
            "Features：character n-gram (2–4) TF-IDF，max 5000 維",
            "Model：LogisticRegression，C=1.0，class_weight=balanced",
            "需要每類別至少 3 筆樣本、總計至少 30 筆",
            "切 80/20 做 train/test，stratified split",
            "印 per-class precision/recall/F1 + 混淆矩陣",
            "模型大小 < 100 KB，直接 commit 進 repo 沒問題",
        ],
        "outputs": [
            {
                "path": "experiments/refusal_calibration/refusal_clf_n{N}.pkl",
                "kind": "Python pickle — {pipeline, labels, train_size, test_accuracy, test_macro_f1}",
                "next_step": "analyze phase 會 load 並對 vendor_call_log 每列做 refusal 分類",
            },
            {
                "path": "(stdout)",
                "kind": "訓練報告",
                "schema": "accuracy / macro-F1 / per-class precision/recall/F1 / 3×3 confusion matrix",
            },
        ],
        "category": "Phase A5 — 拒答校準",
        "depends_on": [
            {"kind": "step", "what": "calibration/import-labels",
             "note": "需要 labeled JSONL 且至少 30 筆、每類別 ≥3 筆"},
        ],
        "unblocks": [
            {"group": "analyze", "subcommand": "refusal",
             "note": "analyze refusal 會載入這顆 classifier"},
        ],
        "fields": [
            {"name": "input", "flag": "--input", "type": "path",
             "default": "experiments/refusal_calibration/labeled_n20.jsonl",
             "default_from_job": {"group": "calibration", "subcommand": "import-labels", "field": "output"},
             "required": True,
             "help": "labeled JSONL 路徑。🔗 自動帶入最近一次 import-labels 成功的 output"},
            {"name": "output", "flag": "--output", "type": "path",
             "default": "experiments/refusal_calibration/refusal_clf_n20.pkl",
             "default_template": "{input|labeled→refusal_clf|.jsonl→.pkl}",
             "required": True,
             "help": "classifier pickle 輸出路徑。🔗 未手動改過時跟 input 同步"},
            {"name": "test_ratio", "flag": "--test-ratio", "type": "str",
             "default": "0.2", "help": "test split 比例（float 0–1）"},
            {"name": "seed", "flag": "--seed", "type": "int",
             "default": 20240113, "help": "random seed"},
        ],
    },

    # =========================================================
    # Phase C4-C5 — Run
    # =========================================================
    {
        "group": "run",
        "subcommand": "smoke-test",
        "title": "五家 vendor × 1 call（驗證連線與成本計算）",
        "summary": (
            "對選定 vendor 各發出一次極小呼叫（prompt = 30 token），確認 API key / "
            "base_url / model_id / pricing 表都對得起來。寫入 runs/<experiment_id>/data.db 的 "
            "vendor_call_log，後續可用 cost burn 查花費。"
        ),
        "why": (
            "正式實驗預估花 USD 50–100（300 persona × 10 sim_day × 5 vendor ≈ 15k calls）。"
            "動工前必須確認每家 vendor 的 endpoint / model_id / pricing / retry / SQLite "
            "logging 全鏈路都通——不然跑到一半才發現 Moonshot 改了 model 名字、Grok "
            "endpoint 搬家，前面燒的錢就白費。smoke-test 花 USD 0.001 換一次全鏈路"
            "驗證，還順便讓你現在按每個 vendor 的按鈕確認 API key 有沒有設對。"
        ),
        "details": [
            "每 vendor 的呼叫成本：OpenAI $0.00001、其它 ≤ $0.00005，五家加總 ~USD 0.001",
            "右側每個 vendor 按鈕 → 只呼叫那家；紫色「全部 vendor」按鈕 → 依序跑 5 家",
            "失敗不會 fallback 到其它 vendor（spec §0.2 invariant），會記錄 status=error",
            "重跑會在同個 experiment_id 下累加 call 紀錄（SQLite INSERT）",
        ],
        "outputs": [
            {
                "path": "runs/{experiment_id}/data.db",
                "kind": "SQLite — vendor_call_log 每 vendor 寫一列",
                "schema": "call_id / experiment_id / persona_id=\"smoke\" / vendor / model_id / status(ok|error|refusal_filter) / cost_usd / latency_ms / tokens_in / tokens_out / response_raw",
            },
            {
                "path": "(stdout)",
                "kind": "逐 vendor 結果行",
                "schema": "[OK|FAIL] {vendor}: status=..., cost=$..., reply='...' （失敗時多一行 error: ...）",
            },
            {
                "path": "(webui 右側「實驗統計」卡片)",
                "kind": "自動聚合 — 按 vendor 分拆 cost / calls / avg latency",
            },
        ],
        "category": "Phase B/C — 實驗執行",
        "supports_vendors": True,
        "costs_money": True,
        "depends_on": [
            {"kind": "env", "what": "5 家 vendor API key",
             "note": "OPENAI_API_KEY / GEMINI_API_KEY / XAI_API_KEY / DEEPSEEK_API_KEY / MOONSHOT_API_KEY；缺一家則該 vendor 按鈕灰掉"},
            {"kind": "step", "what": "news-pool/merge",
             "note": "嚴格講 smoke-test 不吃 pool（只打一個 hello 訊息）；但正式 full run 需要 merged_pool.jsonl + SHA-256"},
            {"kind": "step", "what": "persona-slate/export",
             "note": "同上：smoke-test 不吃 slate；full run 需要"},
        ],
        "unblocks": [
            {"group": "cost", "subcommand": "burn"},
            {"group": "cost", "subcommand": "forecast"},
            {"group": "analyze", "subcommand": "distribution"},
            {"group": "analyze", "subcommand": "refusal"},
        ],
        "fields": [
            {
                "name": "experiment_id", "flag": "--experiment-id", "type": "str",
                "default": "smoke-test",
                "help": "experiment_id（會建 runs/<id>/data.db）",
            },
        ],
    },

    # =========================================================
    # Phase B5 — Cost
    # =========================================================
    {
        "group": "cost",
        "subcommand": "burn",
        "title": "實驗已花費與預算剩餘",
        "summary": "讀 runs/<id>/data.db 統計各 vendor 花費。",
        "why": (
            "研究的硬上限是 USD 400（VendorRouter.HARD_BUDGET_USD）；超過就主動拒絕"
            "呼叫、避免意外燒爆信用卡。burn 讓你隨時看『目前花到哪、剩多少額度、"
            "哪一家 vendor 最貴』，特別是混用 OpenAI（便宜）和 Grok（貴）時，"
            "可以即時判斷是否該調整 vendor mix 或縮小 N。"
        ),
        "category": "Phase B5 — 花費追蹤",
        "depends_on": [
            {"kind": "step", "what": "run/smoke-test",
             "note": "需要 runs/<experiment_id>/data.db 已存在（至少跑過一次 run）"},
        ],
        "parallel_with": [
            {"group": "cost", "subcommand": "forecast"},
        ],
        "unblocks": [],
        "fields": [
            {
                "name": "experiment_id", "flag": "--experiment-id", "type": "str",
                "default": "smoke-test", "required": True,
                "help": "experiment_id（需存在對應的 data.db）",
            },
            {
                "name": "db", "flag": "--db", "type": "path",
                "default": "", "help": "可選：SQLite DB 路徑覆寫",
            },
        ],
    },
    {
        "group": "cost",
        "subcommand": "forecast",
        "title": "依既有均價推估剩餘花費",
        "summary": "average-so-far × 剩餘 call 數 = 預估。",
        "why": (
            "Pricing 表是估計值，真實花費受 prompt/response token 長度、快取命中率"
            "影響，可能比紙上估計多 30%。forecast 用『已跑完部分的實際均價』外推"
            "剩餘花費，在跑到 30% 進度時就能看出是否會超支；若預估超 USD 400，"
            "就該提早中止、降 persona 數，而不是讓 HARD_BUDGET_USD 在燒到一半時"
            "把實驗切斷（中斷的 run 很難乾淨地接回去）。"
        ),
        "category": "Phase B5 — 花費追蹤",
        "depends_on": [
            {"kind": "step", "what": "run/smoke-test",
             "note": "需要至少幾筆 vendor_call_log 才算得出均價；越多越準"},
        ],
        "parallel_with": [
            {"group": "cost", "subcommand": "burn"},
        ],
        "unblocks": [],
        "fields": [
            {
                "name": "experiment_id", "flag": "--experiment-id", "type": "str",
                "default": "smoke-test", "required": True,
                "help": "experiment_id",
            },
            {
                "name": "total_calls_planned", "flag": "--total-calls-planned",
                "type": "int", "default": 15000, "required": True, "promote": True,
                "help": "計畫總 call 數（5 vendor × N personas × sim_days）",
            },
        ],
    },

    # =========================================================
    # Phase C7 — Analyze
    # =========================================================
    {
        "group": "analyze",
        "subcommand": "distribution",
        "title": "① 黨派分佈：JSD vs CEC + pairwise JSD + NEMD",
        "summary": (
            "讀 agent_day_vendor 的最終日 party_choice / party_lean_5，per-vendor 聚合成"
            "機率分佈，算 vendor→CEC 2024 真實結果的 Jensen-Shannon divergence、"
            "vendor 兩兩之間的 JSD（名目類別）+ NEMD（5-bucket 有序）、10k 次"
            "paired bootstrap 的 BCa 95% CI，以及 Holm-Bonferroni + Benjamini-Hochberg 校正後的 p-value。"
        ),
        "why": (
            "JSD 是論文的 main result —— 量化『5 家 vendor 餵同一 persona + 同一新聞後，"
            "民意分佈差多少』。低 JSD 表示該 vendor 與 CEC 2024 官方結果（賴 40.05% / "
            "侯 33.49% / 柯 26.46%）對齊良好；高 JSD 表示該 vendor 有系統性偏差。"
            "NEMD 進一步用 ordinal 距離檢查 5-bucket 藍綠分佈（深綠→深藍 的 shift 比"
            "深綠→偏綠 更大）。paired bootstrap 重抽 persona（而非個別 row）維持"
            "within-persona 相關結構，避免 CI 過窄。"
        ),
        "details": [
            "Ground truth（CEC 2024 三黨得票率）：DPP 0.4005 / KMT 0.3349 / TPP 0.2646",
            "JSD 用 log base 2，bounded [0, 1]",
            "NEMD = EMD / (k-1)，k=5 buckets，bounded [0, 1]",
            "Bootstrap：paired-on-persona，10k 次，BCa CI",
            "n_personas < 3 時自動 fallback 到 percentile CI",
            "多重檢定校正：Holm-Bonferroni（FWER）+ Benjamini-Hochberg（FDR）",
            "不呼叫外部 API；100 persona × 5 vendor 的 10k bootstrap 大約 30–60 秒",
        ],
        "outputs": [
            {
                "path": "metrics/{experiment_id}/distribution.json",
                "kind": "JSON — 完整 metric 結果",
                "schema": (
                    "experiment_id / computed_at / n_rows / n_personas / vendors[] / "
                    "party_categories[] / lean_categories[] / party_distribution / "
                    "lean_distribution / ground_truth / jsd_vs_truth{vendor: {value, ci_low, ci_high, ci_method}} / "
                    "jsd_pairwise{v1|v2: {value, ci, p_value, p_adj_holm, p_adj_bh}} / "
                    "nemd_pairwise{...} / config"
                ),
                "next_step": "Phase D dashboard + Phase C9 paper 都讀這個 JSON",
            },
        ],
        "category": "Phase C7 — 統計分析",
        "depends_on": [
            {"kind": "step", "what": "run/smoke-test",
             "note": "需要 runs/<id>/data.db 的 agent_day_vendor 有資料；smoke-test 不會寫這張表，得等 full run"},
        ],
        "parallel_with": [
            {"group": "analyze", "subcommand": "refusal"},
        ],
        "unblocks": [
            {"group": "analyze", "subcommand": "all"},
            {"group": "dashboard", "subcommand": "placeholder"},
            {"group": "paper", "subcommand": "placeholder"},
        ],
        "fields": [
            {"name": "experiment_id", "flag": "--experiment-id", "type": "str",
             "default": "", "required": True,
             "help": "experiment_id（需存在對應的 runs/<id>/data.db）"},
            {"name": "db", "flag": "--db", "type": "path",
             "default": "", "help": "可選：覆寫 SQLite 路徑"},
            {"name": "sim_day", "flag": "--sim-day", "type": "int",
             "default": 0, "help": "0 或空白 = 每個 persona×vendor 取最後一天"},
            {"name": "output", "flag": "--output", "type": "path",
             "default": "", "help": "預設 metrics/<experiment_id>/distribution.json"},
            {"name": "n_resamples", "flag": "--n-resamples", "type": "int",
             "default": 10000, "promote": True,
             "help": "bootstrap 次數；小 run 可設 1000 加速"},
            {"name": "confidence", "flag": "--confidence", "type": "str",
             "default": "0.95", "help": "CI 置信水準 (0–1)"},
            {"name": "seed", "flag": "--seed", "type": "int",
             "default": 20240113, "help": "bootstrap RNG seed"},
        ],
    },
    {
        "group": "analyze",
        "subcommand": "refusal",
        "title": "② 拒答率：classifier 套到 vendor 回應",
        "summary": (
            "載入 calibration/train 產出的 .pkl 分類器，對 vendor_call_log 的 response_raw "
            "（或 calibration labeled JSONL）做 hard_refusal / soft_refusal / on_task 分類，"
            "per-vendor 統計比例。"
        ),
        "why": (
            "拒答率是論文的次要 key result。『拒答』包含 API content filter（hard）+ "
            "alignment-tuned 模型的『裝傻轉移話題』（soft）。用同一顆分類器對五家 vendor "
            "apples-to-apples 比較：Kimi / DeepSeek（中國 vendor）對兩岸題預期 refusal rate 高；"
            "OpenAI / Grok 預期低。"
        ),
        "details": [
            "分類器：TF-IDF(char_wb, 2–4 gram) + LogisticRegression，~< 100 KB pickle",
            "若 input 帶 topic 欄（calibration JSONL 才有）會額外產出 by_vendor_topic 交叉表",
            "vendor_call_log 沒有 topic → 只產 by_vendor 聚合",
            "純 CPU，秒級完成",
        ],
        "outputs": [
            {
                "path": "metrics/{experiment_id}/refusal.json",
                "kind": "JSON — per-vendor refusal 統計",
                "schema": (
                    "source / classifier_path / classifier_meta{train_size, test_accuracy, test_macro_f1} / "
                    "n_rows / by_vendor{vendor: {total, hard_refusal, soft_refusal, on_task, "
                    "hard_rate, soft_rate, on_task_rate, refusal_rate}} / by_vendor_topic(nullable)"
                ),
            },
        ],
        "category": "Phase C7 — 統計分析",
        "depends_on": [
            {"kind": "step", "what": "calibration/train",
             "note": "需要 refusal_clf_n*.pkl"},
            {"kind": "step", "what": "run/smoke-test",
             "note": "若走 --experiment-id 需要 vendor_call_log 有資料；或改用 --labeled 指向 calibration JSONL"},
        ],
        "parallel_with": [
            {"group": "analyze", "subcommand": "distribution"},
        ],
        "unblocks": [
            {"group": "analyze", "subcommand": "all"},
            {"group": "dashboard", "subcommand": "placeholder"},
        ],
        "fields": [
            {"name": "classifier", "flag": "--classifier", "type": "path",
             "default": "experiments/refusal_calibration/refusal_clf_n20.pkl",
             "required": True, "help": "train 產出的 .pkl 路徑"},
            {"name": "experiment_id", "flag": "--experiment-id", "type": "str",
             "default": "", "help": "走 vendor_call_log 路徑時必填"},
            {"name": "db", "flag": "--db", "type": "path",
             "default": "", "help": "可選：SQLite 路徑覆寫"},
            {"name": "labeled", "flag": "--labeled", "type": "path",
             "default": "", "help": "改為分析 labeled/responses JSONL；與 --experiment-id 擇一"},
            {"name": "output", "flag": "--output", "type": "path",
             "default": "", "help": "metric JSON 輸出"},
        ],
    },
    {
        "group": "analyze",
        "subcommand": "all",
        "title": "③ distribution + refusal 一次跑完 + summary",
        "summary": (
            "便利 wrapper：distribution pipeline 必跑；若給 --classifier 就順便跑 refusal；"
            "最後寫一份 summary.json（headline JSD / refusal_rate 給 dashboard 吃）。"
        ),
        "why": (
            "論文與 dashboard 需要一份統一入口的 summary，這個指令把 metric 產線整合成"
            "單一檔，避免下游零散讀 distribution.json + refusal.json 各自 parse。"
        ),
        "details": [
            "產出固定在 metrics/<experiment_id>/{distribution.json, refusal.json?, summary.json}",
            "--classifier 空 → 只跑 distribution，summary 的 refusal 欄位為 null",
            "bootstrap 預設 10k；dev 迭代時可 --n-resamples 1000 加速",
        ],
        "outputs": [
            {
                "path": "metrics/{experiment_id}/distribution.json",
                "kind": "同 analyze distribution 產出",
            },
            {
                "path": "metrics/{experiment_id}/refusal.json",
                "kind": "同 analyze refusal 產出（若給 --classifier 才有）",
            },
            {
                "path": "metrics/{experiment_id}/summary.json",
                "kind": "JSON — headline 欄位（dashboard / paper 讀這個）",
                "schema": "experiment_id / computed_at / vendors / n_personas / headline{jsd_vs_truth, refusal_rate}",
            },
        ],
        "category": "Phase C7 — 統計分析",
        "depends_on": [
            {"kind": "step", "what": "run/smoke-test",
             "note": "需要 full run 的 data.db"},
        ],
        "unblocks": [
            {"group": "dashboard", "subcommand": "placeholder"},
            {"group": "paper", "subcommand": "placeholder"},
        ],
        "fields": [
            {"name": "experiment_id", "flag": "--experiment-id", "type": "str",
             "default": "", "required": True, "help": "experiment_id"},
            {"name": "db", "flag": "--db", "type": "path",
             "default": "", "help": "SQLite 路徑覆寫"},
            {"name": "classifier", "flag": "--classifier", "type": "path",
             "default": "experiments/refusal_calibration/refusal_clf_n20.pkl",
             "help": "若空則只跑 distribution"},
            {"name": "sim_day", "flag": "--sim-day", "type": "int",
             "default": 0, "help": "0 / 空白 = 取每個 persona-vendor 的最後一天"},
            {"name": "output_dir", "flag": "--output-dir", "type": "path",
             "default": "", "help": "預設 metrics/<experiment_id>/"},
            {"name": "n_resamples", "flag": "--n-resamples", "type": "int",
             "default": 10000, "promote": True, "help": "bootstrap 次數"},
            {"name": "confidence", "flag": "--confidence", "type": "str",
             "default": "0.95", "help": "CI 水準"},
            {"name": "seed", "flag": "--seed", "type": "int",
             "default": 20240113, "help": "RNG seed"},
        ],
    },

    # =========================================================
    # Phase D — Dashboard (stub)
    # =========================================================
    {
        "group": "dashboard",
        "subcommand": "placeholder",
        "title": "單檔 HTML dashboard（未實作）",
        "summary": "Phase D stub。",
        "why": (
            "論文附錄要給審稿人互動式結果瀏覽：哪個 persona 在哪家 vendor 說了什麼、"
            "在 sim_day 7 哪個 agent 被哪篇新聞影響。產 static HTML + Chart.js "
            "（不開 server）方便存 Zenodo / 附 supplementary material。"
        ),
        "category": "Phase D — 儀表板",
        "depends_on": [
            {"kind": "step", "what": "analyze/all",
             "note": "儀表板讀 metrics/<experiment_id>/summary.json + distribution.json + refusal.json"},
        ],
        "unblocks": [],
        "is_stub": True,
        "fields": [],
    },

    # =========================================================
    # Phase C9 — Paper figures (stub)
    # =========================================================
    {
        "group": "paper",
        "subcommand": "placeholder",
        "title": "論文圖表與表格（未實作）",
        "summary": "Phase C9 stub。",
        "why": (
            "把 analyze 算出來的 metric 轉成論文 camera-ready 的 Figure 1/2/3 "
            "（JSD heatmap / refusal 對比 bar / persona dispersion scatter）和 "
            "Table 1/2/3（vendor × metric 對照、CI）。直接輸出 pdf / tex 片段，"
            "避免手動剪貼到 Overleaf 而失真或版本不一致。"
        ),
        "category": "Phase C9 — 論文輸出",
        "depends_on": [
            {"kind": "step", "what": "analyze/all",
             "note": "論文圖表讀 metrics/<experiment_id>/ 下的三份 JSON"},
        ],
        "parallel_with": [
            {"group": "dashboard", "subcommand": "placeholder",
             "note": "與 dashboard 同樣依賴 analyze，彼此無先後"},
        ],
        "unblocks": [],
        "is_stub": True,
        "fields": [],
    },
]


def commands_by_category() -> dict[str, list[dict]]:
    """Group command specs by their category label for UI rendering."""
    out: dict[str, list[dict]] = {}
    for c in COMMANDS:
        out.setdefault(c["category"], []).append(c)
    return out


def category_intros() -> dict[str, str]:
    return dict(CATEGORY_INTROS)
