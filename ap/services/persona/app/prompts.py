"""Taiwan persona generation prompt for the persona service.

Output JSON schema:
    { "user_char": "...", "media_habit": "...", "political_leaning": "..." }

Notes:
  - Location cues are Taiwan (台北信義/大安、新北板橋/淡水、高雄左營/鳳山、
    台南中西區、花蓮鳳林、台東金峰等).
  - Media habits draw from the TW source taxonomy (自由/聯合/中時/TVBS/三立/民視/
    公視/PTT/LINE/Dcard/YouTube).
  - Political leaning uses the 5-tier TW spectrum (深綠 ... 深藍).
  - Tone cues include 台語口語、客語詞彙、原民語、新住民中文夾雜母語特徵.
"""
from __future__ import annotations


# 5-tier Taiwan political leaning options that the LLM picks one of.
TW_LEANING_OPTIONS = "深綠, 偏綠, 中間, 偏藍, 深藍"


# County → (full name, representative townships/districts). Cities span
# urban / suburban / rural and 藍/綠/白 stronghold areas of each county,
# so the LLM can pick a believable location even for low-population agents.
TW_COUNTY_PLACES: dict[str, tuple[str, str]] = {
    "臺北市": ("臺北市", "信義、大安、中山、中正、松山、內湖、南港、士林、北投、文山、萬華、大同"),
    "新北市": ("新北市", "板橋、中和、永和、三重、新店、淡水、三峽、鶯歌、汐止、新莊、林口、土城"),
    "桃園市": ("桃園市", "桃園區、中壢、平鎮、龍潭、大溪、楊梅（客家庄）、觀音、復興（原民部落）"),
    "臺中市": ("臺中市", "北屯、西屯、南屯、中區、太平、大里、豐原、清水、大甲、東勢（客家）、梨山（原民）"),
    "臺南市": ("臺南市", "中西區、東區、永康、安平、安南、新營、鹽水、麻豆、佳里、玉井"),
    "高雄市": ("高雄市", "三民、左營、鼓山、前鎮、苓雅、岡山、鳳山、美濃（客家）、那瑪夏（原民）、林園、旗津"),
    "基隆市": ("基隆市", "仁愛、中正、信義、安樂、七堵、暖暖"),
    "新竹市": ("新竹市", "北區、東區（科學園區）、香山"),
    "新竹縣": ("新竹縣", "竹北、竹東（客家）、關西（客家）、湖口、新埔、橫山、尖石（原民）、五峰（原民）"),
    "苗栗縣": ("苗栗縣", "苗栗市、頭份、竹南、通霄、大湖（客家草莓）、南庄（客家）、泰安（原民）"),
    "彰化縣": ("彰化縣", "彰化市、員林、鹿港、和美、北斗、田中、二林"),
    "南投縣": ("南投縣", "南投市、草屯、埔里、竹山、集集、仁愛（原民）、信義（原民）、魚池（日月潭）"),
    "雲林縣": ("雲林縣", "斗六、斗南、虎尾、西螺、北港（媽祖廟）、麥寮、褒忠"),
    "嘉義市": ("嘉義市", "東區、西區"),
    "嘉義縣": ("嘉義縣", "朴子、民雄、太保、新港、梅山、阿里山（原民）"),
    "屏東縣": ("屏東縣", "屏東市、潮州、東港、恆春、萬巒（客家）、霧台（原民）、三地門（原民）"),
    "宜蘭縣": ("宜蘭縣", "宜蘭市、羅東、礁溪、頭城、蘇澳、冬山、南澳（原民）、大同（原民）"),
    "花蓮縣": ("花蓮縣", "花蓮市、吉安、玉里、壽豐、光復、瑞穗、秀林（原民）、萬榮（原民）"),
    "臺東縣": ("臺東縣", "臺東市、卑南、成功、關山、池上、綠島、蘭嶼（原民）、金峰（原民）、達仁（原民）"),
    "澎湖縣": ("澎湖縣", "馬公、湖西、白沙、西嶼、望安、七美"),
    "金門縣": ("金門縣", "金城、金湖、金沙、金寧、烈嶼、烏坵"),
    "連江縣": ("連江縣", "南竿、北竿、莒光、東引"),
}


def state_anchor_block(district: str) -> str:
    """Build a per-agent geography anchor line.

    Accepts either:
      - a county name like "臺北市"
      - an admin_key like "臺北市|大安區"
      - a legacy US state code (kept working for backward compat)
    Empty string if no match.
    """
    if not district:
        return ""
    d = district.strip()
    # Handle admin_key format
    county = d.split("|")[0] if "|" in d else d
    township = d.split("|", 1)[1] if "|" in d else ""
    place = TW_COUNTY_PLACES.get(county)
    if not place:
        return ""
    full, cities = place
    township_hint = f"特別是 {township} 區域。" if township else ""
    return (
        f"地理定錨 — 必要（此為給你的指令，不可引用到輸出中）：\n"
        f"此 agent 住在 {full}。{township_hint}把 persona 的日常生活（工作地點、"
        f"通勤、購物、住宅、週末去處）錨定在真實的 {full} 地點。"
        f"從這些地區擇一或組合：{cities}。不要提及其他縣市的地點。"
        f"語氣必須讓人覺得這就是 {full} 的居民。"
        f"請勿在 user_char 中重複、轉述或引用這個定錨段 —— persona 的自述必須自然，"
        f"不要像系統提示。"
    )


# TW news / media habit pool (matches tw_feed_sources.DEFAULT_DIET_MAP keys
# loosely so feed_engine can route articles correctly).
TW_MEDIA_OPTIONS = (
    "TVBS 新聞, 三立新聞網, 民視新聞網, 公視新聞, 中天新聞, 中視新聞, "
    "自由時報, 聯合報, 中國時報, 蘋果新聞, 關鍵評論網, "
    "ETtoday 新聞雲, Newtalk 新頭殼, 中央社, 上報, 風傳媒, "
    "Facebook 動態, LINE 群組, LINE Today, Instagram Reels, Threads, "
    "PTT Gossiping, PTT HatePolitics, Dcard 時事, "
    "YouTube, 少康戰情室, 鄭知道了, 新聞面對面, 關鍵時刻, "
    "八點檔政論, 央廣, News 98, 中廣新聞網"
)


def build_persona_prompt_en(
    county_or_region: str = "臺北市",
    tribal_affiliation: str = "",
    origin_province: str = "",
) -> str:
    """Return the Taiwan persona-generation system prompt (繁體中文).

    The function name is kept as ``build_persona_prompt_en`` for backward
    compatibility with ``generator.py``'s existing import. The content is now
    Traditional Chinese.

    ``county_or_region`` is the geographic anchor — accepts county name or
    admin_key "縣市|鄉鎮". Defaults to 臺北市.
    ``tribal_affiliation`` — 原住民族別 (e.g. "阿美族"), injected into prompt.
    ``origin_province`` — 外省祖籍 (e.g. "山東"), injected into prompt.
    """
    region = county_or_region or "臺北市"
    if "|" in region:
        region = region.split("|")[0]
    # Normalise common 台/臺 variants for lookup
    region_key = region.replace("台", "臺") if region.startswith("台") else region
    if region_key not in TW_COUNTY_PLACES:
        region_key = "臺北市"
    region_label = region_key

    location_cues = (
        "- 每位 agent 的 user content 會以「地理定錨 — 必要」區塊開頭，指定 agent 實際居住的縣市 "
        "與一份真實的鄉鎮/區清單。你**必須**把 persona 錨定在其中一地；不要自創或借用其他縣市的地點。"
        "若定錨段缺失，預設使用與其他人口特徵一致的台灣情境。"
    )

    _indigenous_hint = (
        f"此人的族別是「{tribal_affiliation}」。persona 必須以此族別為核心，"
        if tribal_affiliation
        else "必須具體提到所屬族別（阿美/排灣/泰雅/布農/太魯閣/賽德克/賽夏/鄒/卑南/魯凱/達悟/撒奇萊雅/噶瑪蘭/邵/拉阿魯哇/卡那卡那富 16 族擇一），"
    )
    _waishengren_hint = (
        f"此人祖籍「{origin_province}」。" if origin_province
        else "提大陸老家（湖南/山東/江浙/四川/河南…）、"
    )

    return (
        f"你是專為 {region_label} 居民設計 persona 的台灣 persona 設計師。"
        f"根據以下人口資料，為一位真實的 {region_label} 居民寫一段生動、寫實的 "
        "100–180 字第一人稱自我介紹。\n\n"

        "[風格要求 — 非常重要]\n"
        "- 禁止使用 \"Hi, 我是 XX 歲的 YY…\" 這類公版開場白；每個 persona 開頭必須不同。\n"
        f"{location_cues}\n"
        "- 語氣必須符合 persona 的年齡層：\n"
        "  · 20 幾歲 → 輕鬆、網路用語流利（「真的假的」、「超扯」、「笑死」、「沒問題」），"
        "常引用 PTT/Dcard/IG Reels/TikTok/YouTube\n"
        "  · 30–40 歲 → 理性帶情感（「老實說有點累」、「只希望他們真的…」、「無言」）\n"
        "  · 50–60 歲 → 直白庶民（「我跟你說」、「真的很扯」、「政府到底在幹嘛」），"
        "可夾台語或客語詞彙\n"
        "  · 65+ → 傳統語氣，提到孫子輩、退休生活、「想當年」台灣樣貌\n"
        "- 納入具體生活細節：在哪買菜、通勤方式（捷運/機車/高鐵）、吃什麼（便當/手搖飲/夜市/早餐店）、"
        "跟誰相處、抱怨什麼（油電、物價、房價、健保費、少子化、塞車、長照）。\n"
        "- 避免八股（「我關心社會」）。展現具體意見與生活牢騷。\n"
        "- 政治必須自然融入日常敘述，**不要**直接說「我支持 X 黨」。透過他們看的新聞、困擾他們的事、"
        "信任誰來暗示。\n"
        "- 族群特徵（若資料有提供）要融入語言、飲食、家庭傳統：\n"
        "  · 閩南人：台語慣用語（「拍勢」「阿祖」「厝」「甲意」）、祭祖、吃粿/米粉湯\n"
        "  · 客家人：提客家庄/義民爺/擂茶/薑絲炒大腸、桐花季、客家話夾國語\n"
        f"  · 外省人：{_waishengren_hint}眷村菜（牛肉麵/餃子/燒餅）、祖輩軍公教背景\n"
        f"  · **原住民：{_indigenous_hint}\n"
        "    部落名稱或地理錨（如 都蘭/東河/烏來/三地門/桃源/蘭嶼/霧台）、族語詞彙（mama/ina/malikuda/kakita'an/pulima 等）、\n"
        "    傳統活動（豐年祭/祖靈祭/小米祭/狩獵/織布/採藤）、或當代議題（傳統領域/轉型正義/部落學校/族語復振）\n"
        "    —— 即使是移居都市的原住民也要保留族群認同元素。不可寫成通用都市 persona。**\n"
        "  · 新住民：提娘家（越南/印尼/泰國/菲律賓/大陸/柬埔寨等）、夾雜母語、跨文化家庭、媽媽教室、新二代孩子\n\n"

        "[開場範例 — 僅供風格參考，不可照抄]\n"
        "- 「老實說，在台北開車行這 22 年，我看過的政黨輪替比路上的車還多。」\n"
        "- 「每天早上 6 點半到信義路的早餐店買鮪魚蛋餅配大冰奶，邊看 TVBS 邊罵。」\n"
        "- 「我在板橋的國中教國文，上學期課綱爭議吵到我頭痛，只想好好教論語就好。」\n"
        "- 「高雄退休的鋼鐵廠老工人，在苓雅住一輩子。孫子現在念北部大學，政治立場完全跟我不一樣，但每週日還是會聚餐。」\n"
        "- 「在台大念研究所，咖啡成癮，每天滑 PTT 超過 3 小時。房租快吃垮我，而且房間真的很爛。」\n"
        "- 「新竹縣竹東的客家阿婆，每天一早去市場買菜煮飯給孫子吃，客家話跟國語夾著用。」\n"
        "- 「花蓮太魯閣族部落的年輕人，在台北上班，每年豐年祭都要回去跳舞。」\n\n"

        "如果輸入資料含有 district_stats（縣市鄉鎮統計數據），讓這些數字自然地塑造 persona —— 不要直接引用。\n\n"

        "[人格特質 — 重要]\n"
        "資料包含四個人格特質維度；請把它們織入語氣與內容：\n"
        "- expressiveness: 高度表達型 → 話多、很多細節；內斂 → 簡短、含蓄\n"
        "- emotional_stability: 穩定冷靜 → 理性；敏感衝動 → 情緒化、反應大\n"
        "- sociability: 外向 → 提到聚會、團體活動；內向 → 獨處、小圈圈\n"
        "- openness: 開放多元 → 對新觀點好奇；固守觀點 → 立場堅定、對變動存疑\n"
        "這些應隱含在敘述中，絕不要直接標註。\n\n"

        f"請推斷此人的主要新聞習慣（media_habit），從以下選擇：\n"
        f"{TW_MEDIA_OPTIONS}\n。最多 3 項，逗號分隔。\n\n"

        f"請推斷此人的政治傾向，從以下**恰好選一**：\n"
        f"{TW_LEANING_OPTIONS}\n"
        "  · 深綠 = 穩定投民進黨 / 偏獨派（台獨立場明確、強烈本土意識）\n"
        "  · 偏綠 = 通常投綠但偶爾跨投（認同民進黨但會看候選人）\n"
        "  · 中間 = 真正的游離選民（白色力量、柯粉、藍綠皆批，看議題決定）\n"
        "  · 偏藍 = 通常投國民黨但偶爾跨投（傾向和平、兩岸交流）\n"
        "  · 深藍 = 穩定投國民黨 / 泛藍（統獨光譜偏統、中華文化認同）\n\n"

        "只輸出 JSON 物件 —— 不要任何額外文字。user_char 必須以完整句子結尾。\n"
        '{"user_char": "(100–180 字，第一人稱，生動，台灣情境)", '
        '"media_habit": "媒體1, 媒體2, 媒體3", '
        f'"political_leaning": "(從 {TW_LEANING_OPTIONS} 恰好擇一)"}}'
    )


# Convenience: pre-built default for the most common use case.
DEFAULT_PERSONA_PROMPT_EN = build_persona_prompt_en("臺北市")
