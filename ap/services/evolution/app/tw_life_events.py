"""台灣生活事件目錄 — Taiwan life events for evolution simulation.

Each day, ~8% of agents may experience a life event based on their
demographics. Events affect satisfaction and anxiety, and inject
a prompt_hint (in 繁體中文) into the LLM diary generation.

Replaces the US-era ``us_life_events.py``. Schema is identical so
``life_events.py`` (eligibility checker) and ``evolver.py`` consume
it without changes.

Eligibility filters used:
  age_min, age_max
  gender  (男 / 女)
  ethnicity  (閩南 / 客家 / 外省 / 原住民 / 新住民)
  ethnicity_not  (list to exclude)
  occupation_exclude  (set)
  tenure  (自有住宅 / 租屋)
"""
from __future__ import annotations

from typing import Any

# ── 職業分組 ──────────────────────────────────────────────────────
_WHITE_COLLAR = {
    "就業",  # generic employed (fallback)
    "工程師", "軟體工程師", "教師", "教授", "醫師", "護理師",
    "律師", "會計師", "分析師", "行銷", "業務", "經理", "主管",
    "設計師", "建築師", "公務員",
}
_BLUE_COLLAR = {
    "作業員", "技師", "司機", "外送", "零售", "服務業",
    "餐飲", "保全", "清潔", "建築工", "水電", "農夫", "漁民", "廠工",
}
_STUDENT = {"學生"}
_RETIRED = {"退休", "非勞動力"}
_HOMEMAKER = {"家管"}

# ── Taiwan Event Catalog ──────────────────────────────────────────

TW_EVENT_CATALOG: list[dict[str, Any]] = [
    # ════════════ 經濟 ════════════
    {
        "id": "eco_layoff",
        "name": "被裁員",
        "category": "economic",
        "description": "公司縮編，今天收到資遣通知書",
        "probability": 0.10,
        "eligibility": {"age_min": 22, "age_max": 62,
                        "occupation_exclude": _STUDENT | _RETIRED},
        "effects": {"satisfaction_delta": -12, "anxiety_delta": 18},
        "cooldown_days": 90,
        "prompt_hint": "你剛剛被公司資遣了，對帳單、房租、找工作都很焦慮。",
    },
    {
        "id": "eco_raise",
        "name": "加薪了",
        "category": "economic",
        "description": "主管宣布下個月起加薪",
        "probability": 0.08,
        "eligibility": {"age_min": 23, "age_max": 62,
                        "occupation_exclude": _STUDENT | _RETIRED},
        "effects": {"satisfaction_delta": 8, "anxiety_delta": -6},
        "cooldown_days": 180,
        "prompt_hint": "你剛剛加薪了，對財務狀況感到樂觀。",
    },
    {
        "id": "eco_promotion",
        "name": "升遷",
        "category": "economic",
        "description": "升上主管職，責任加重",
        "probability": 0.04,
        "eligibility": {"age_min": 28, "age_max": 55,
                        "occupation_exclude": _STUDENT | _RETIRED},
        "effects": {"satisfaction_delta": 10, "anxiety_delta": -4},
        "cooldown_days": 365,
        "prompt_hint": "你剛升職，興奮但也感到新職責的壓力。",
    },
    {
        "id": "eco_medical_bill",
        "name": "意外醫療費",
        "category": "economic",
        "description": "跑急診意外收到 3 萬元醫療費帳單",
        "probability": 0.08,
        "eligibility": {"age_min": 25},
        "effects": {"satisfaction_delta": -6, "anxiety_delta": 10},
        "cooldown_days": 180,
        "prompt_hint": "今天收到一筆意外醫療費帳單，錢包吃緊讓你煩躁。",
    },
    {
        "id": "eco_rent_hike",
        "name": "房租要漲",
        "category": "economic",
        "description": "房東通知下個月房租調漲 15%",
        "probability": 0.10,
        "eligibility": {"age_min": 22, "age_max": 50, "tenure": "租屋"},
        "effects": {"satisfaction_delta": -8, "anxiety_delta": 12},
        "cooldown_days": 180,
        "prompt_hint": "房東今天 LINE 通知房租要漲，你考慮要不要搬家。",
    },
    {
        "id": "eco_mortgage_pressure",
        "name": "房貸壓力",
        "category": "economic",
        "description": "央行升息，房貸月繳增加",
        "probability": 0.09,
        "eligibility": {"age_min": 30, "age_max": 60, "tenure": "自有住宅"},
        "effects": {"satisfaction_delta": -6, "anxiety_delta": 10},
        "cooldown_days": 120,
        "prompt_hint": "央行升息，你的房貸月繳多了幾千塊，家計更緊了。",
    },
    {
        "id": "eco_electric_bill",
        "name": "電費漲",
        "category": "economic",
        "description": "夏季電費帳單飆高",
        "probability": 0.12,
        "eligibility": {},
        "effects": {"satisfaction_delta": -3, "anxiety_delta": 5},
        "cooldown_days": 60,
        "prompt_hint": "今天收到夏季電費帳單，金額比去年多很多，心情很差。",
    },

    # ════════════ 家庭 ════════════
    {
        "id": "fam_wedding",
        "name": "結婚",
        "category": "family",
        "description": "訂了明年春天的婚期",
        "probability": 0.03,
        "eligibility": {"age_min": 24, "age_max": 45},
        "effects": {"satisfaction_delta": 12, "anxiety_delta": -2},
        "cooldown_days": 720,
        "prompt_hint": "你剛訂了婚期，心情很雀躍但也緊張準備事宜。",
    },
    {
        "id": "fam_newborn",
        "name": "新生兒",
        "category": "family",
        "description": "太太（或自己）懷了寶寶",
        "probability": 0.03,
        "eligibility": {"age_min": 25, "age_max": 42},
        "effects": {"satisfaction_delta": 10, "anxiety_delta": 5},
        "cooldown_days": 720,
        "prompt_hint": "家裡要有新生兒了，你又期待又擔心經濟壓力。",
    },
    {
        "id": "fam_elder_sick",
        "name": "長輩住院",
        "category": "family",
        "description": "爸媽其中一位突然住院",
        "probability": 0.08,
        "eligibility": {"age_min": 30, "age_max": 70},
        "effects": {"satisfaction_delta": -5, "anxiety_delta": 12},
        "cooldown_days": 150,
        "prompt_hint": "爸/媽突然住院了，你今天都在醫院陪伴，擔心健保給付、長照安排。",
    },
    {
        "id": "fam_kid_exam",
        "name": "孩子考試",
        "category": "family",
        "description": "孩子面臨會考/統測/學測",
        "probability": 0.06,
        "eligibility": {"age_min": 35, "age_max": 55},
        "effects": {"satisfaction_delta": -2, "anxiety_delta": 7},
        "cooldown_days": 180,
        "prompt_hint": "孩子最近要面臨重要考試，家裡氣氛緊繃。",
    },

    # ════════════ 健康 ════════════
    {
        "id": "health_cold_flu",
        "name": "感冒生病",
        "category": "health",
        "description": "感冒發燒好幾天",
        "probability": 0.10,
        "eligibility": {},
        "effects": {"satisfaction_delta": -3, "anxiety_delta": 4},
        "cooldown_days": 45,
        "prompt_hint": "你感冒好幾天，去診所看病排了一小時，心情很差。",
    },
    {
        "id": "health_injury",
        "name": "意外受傷",
        "category": "health",
        "description": "騎車/走路意外跌倒",
        "probability": 0.05,
        "eligibility": {"age_min": 20},
        "effects": {"satisfaction_delta": -5, "anxiety_delta": 8},
        "cooldown_days": 120,
        "prompt_hint": "今天騎車意外跌倒，到急診處理了傷口，心情很差。",
    },

    # ════════════ 社區 / 政治 ════════════
    {
        "id": "pol_rally",
        "name": "參加造勢",
        "category": "political",
        "description": "參加了政黨的造勢大會",
        "probability": 0.04,
        "eligibility": {"age_min": 25, "age_max": 80},
        "effects": {"satisfaction_delta": 5, "anxiety_delta": -3},
        "cooldown_days": 60,
        "prompt_hint": "你今晚跑去參加造勢大會，被現場氣氛激勵，感覺很有力。",
    },
    {
        "id": "pol_vote_day",
        "name": "投票日",
        "category": "political",
        "description": "參加選舉投票",
        "probability": 0.03,  # only triggered near election days via scheduler
        "eligibility": {"age_min": 20},
        "effects": {"satisfaction_delta": 2, "anxiety_delta": 3},
        "cooldown_days": 30,
        "prompt_hint": "今天是投票日，你一早就去里民中心投了票，心情夾雜期待與焦慮。",
    },
    {
        "id": "community_dispute",
        "name": "社區糾紛",
        "category": "community",
        "description": "社區管委會吵架或鄰居糾紛",
        "probability": 0.06,
        "eligibility": {},
        "effects": {"satisfaction_delta": -4, "anxiety_delta": 5},
        "cooldown_days": 120,
        "prompt_hint": "社區今天又在吵管理費/停車/噪音問題，你很無奈。",
    },

    # ════════════ 兩岸 / 國安 ════════════
    {
        "id": "cs_military_drill",
        "name": "共軍軍演",
        "category": "cross_strait",
        "description": "中國解放軍在台海周圍大規模軍演",
        "probability": 0.04,
        "eligibility": {"age_min": 25},
        "effects": {"satisfaction_delta": -3, "anxiety_delta": 10},
        "cooldown_days": 90,
        "prompt_hint": "今天新聞播報共軍軍演，飛彈軌跡靠近台灣，你有點不安。",
    },

    # ════════════ 天然災害 ════════════
    {
        "id": "natural_typhoon",
        "name": "颱風過境",
        "category": "natural",
        "description": "強颱過境，停班停課",
        "probability": 0.05,
        "eligibility": {},
        "effects": {"satisfaction_delta": -3, "anxiety_delta": 6},
        "cooldown_days": 60,
        "prompt_hint": "強颱過境，你今天在家躲颱風，擔心家裡漏水、停電。",
    },
    {
        "id": "natural_earthquake",
        "name": "地震",
        "category": "natural",
        "description": "規模 6 以上的地震",
        "probability": 0.03,
        "eligibility": {},
        "effects": {"satisfaction_delta": -2, "anxiety_delta": 8},
        "cooldown_days": 60,
        "prompt_hint": "今天半夜大地震，你被嚇醒。擔心家裡、親人。",
    },

    # ════════════ 族群特定事件 ════════════
    {
        "id": "eth_mazu_pilgrimage",
        "name": "媽祖繞境",
        "category": "culture",
        "description": "大甲媽 / 白沙屯媽祖繞境",
        "probability": 0.06,
        "eligibility": {"age_min": 30, "ethnicity": "閩南"},
        "effects": {"satisfaction_delta": 6, "anxiety_delta": -4},
        "cooldown_days": 300,
        "prompt_hint": "媽祖繞境經過你們庄頭，你感受到傳統信仰的力量，心情平和。",
    },
    {
        "id": "eth_hakka_festival",
        "name": "客家義民節",
        "category": "culture",
        "description": "參加客家義民祭",
        "probability": 0.06,
        "eligibility": {"ethnicity": "客家"},
        "effects": {"satisfaction_delta": 5, "anxiety_delta": -3},
        "cooldown_days": 300,
        "prompt_hint": "今天是義民節，你參加了客家庄的祭典，族群認同感油然而生。",
    },
    {
        "id": "eth_indigenous_festival",
        "name": "原住民祭典",
        "category": "culture",
        "description": "參加部落祭典（豐年祭/小米祭等）",
        "probability": 0.07,
        "eligibility": {"ethnicity": "原住民"},
        "effects": {"satisfaction_delta": 8, "anxiety_delta": -4},
        "cooldown_days": 300,
        "prompt_hint": "今天參加族裡的祭典，族人都回來了，感到與土地和族人深深連結。",
    },
    {
        "id": "eth_immigration_call",
        "name": "回鄉視訊",
        "category": "culture",
        "description": "與娘家/父母視訊",
        "probability": 0.08,
        "eligibility": {"ethnicity": "新住民"},
        "effects": {"satisfaction_delta": 4, "anxiety_delta": 2},
        "cooldown_days": 30,
        "prompt_hint": "今天跟娘家（越南/印尼/中國等）視訊，看到父母健康但又想家。",
    },
    {
        "id": "eth_waishengren_memorial",
        "name": "祖墳清明",
        "category": "culture",
        "description": "清明掃墓 / 思念大陸老家",
        "probability": 0.05,
        "eligibility": {"age_min": 40, "ethnicity": "外省"},
        "effects": {"satisfaction_delta": 2, "anxiety_delta": 3},
        "cooldown_days": 365,
        "prompt_hint": "清明時節，你想起大陸老家的祖墳，感慨兩岸關係。",
    },

    # ════════════ 教育 ════════════
    {
        "id": "edu_graduation",
        "name": "畢業",
        "category": "education",
        "description": "大學 / 研究所畢業",
        "probability": 0.04,
        "eligibility": {"age_min": 22, "age_max": 28},
        "effects": {"satisfaction_delta": 6, "anxiety_delta": 4},
        "cooldown_days": 720,
        "prompt_hint": "你今天畢業了，興奮但也擔心找工作。",
    },
    {
        "id": "edu_tuition_hike",
        "name": "學費漲",
        "category": "education",
        "description": "學校宣布學費調漲",
        "probability": 0.05,
        "eligibility": {"age_min": 35, "age_max": 55},
        "effects": {"satisfaction_delta": -4, "anxiety_delta": 7},
        "cooldown_days": 180,
        "prompt_hint": "孩子念的學校宣布學費漲，你在計算預算。",
    },
]
