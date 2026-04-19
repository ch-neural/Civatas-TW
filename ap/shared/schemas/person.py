"""Civatas shared schema: intermediate person record (Taiwan)."""
from __future__ import annotations

from pydantic import BaseModel


class Person(BaseModel):
    """Intermediate person record produced by the synthesis layer.

    Geographic fields mirror the Taiwan admin hierarchy ("縣市|鄉鎮市區"):
      - county    e.g. "臺北市"
      - township  e.g. "臺北市|大安區"  (matches ap.shared.tw_admin admin_key)
      - district  free-form legacy string — present for backward compat with
                  pre-TW conversion personas; synthesis now also writes
                  county+township explicitly.

    Ethnic / political fields:
      - ethnicity    閩南 / 客家 / 外省 / 原住民 / 新住民 / 其他
      - party_lean   深綠 / 偏綠 / 中間 / 偏藍 / 深藍
      - cross_strait 主權 / 經濟 / 民生   (attitude axis for TW context)
      - tribal_affiliation  阿美族 / 排灣族 / 泰雅族 ... (原住民 16 族)
      - origin_province     山東 / 湖南 / 江蘇 ... (外省祖籍)
      - kmt_member / dpp_member / tpp_member
                     黨員身份（synthesis 推導，新 workspace 才有；None = 未推導）

    Legacy US fields (race / hispanic_or_latino) are kept for backward
    compatibility with the US-era snapshots stored on disk; new personas
    leave them None and use `ethnicity` instead.
    """
    person_id: int
    age: int
    gender: str
    district: str

    # Taiwan admin hierarchy (new; preferred over free-form district)
    county: str | None = None
    township: str | None = None

    education: str | None = None
    occupation: str | None = None

    # Taiwan ethnicity (primary field)
    ethnicity: str | None = None

    # US-era fields (legacy — kept nullable for backward compat)
    race: str | None = None
    hispanic_or_latino: str | None = None

    household_income: str | None = None
    income_band: str | None = None
    household_type: str | None = None
    household_tenure: str | None = None
    marital_status: str | None = None
    party_lean: str | None = None
    issue_1: str | None = None
    issue_2: str | None = None
    media_habit: str | None = None
    mbti: str | None = None
    vote_probability: float | None = None

    # Taiwan attitude axis — kept in snake_case for consistency with DB fields.
    # Values are Chinese tokens: 主權 / 經濟 / 民生.
    cross_strait: str | None = None

    # Taiwan ethnic sub-group pre-allocation (synthesis 層預分配, persona/evolution 使用)
    # 原住民 → 16 族之一 (e.g. "阿美族", "排灣族")
    tribal_affiliation: str | None = None
    # 外省人 → 祖籍省份 (e.g. "山東", "湖南")
    origin_province: str | None = None

    # Taiwan party membership (derived by synthesis _derive_party_member)
    # None = 未推導（舊 persona backward compat）；True/False = 推導結果
    # 台灣選民可跨黨登記，所以三個欄位各自獨立 bool（非互斥）
    #
    # 使用時注意 None 語義：None 在 Python `if` 中會當 falsy，但語意上是「未知」不是 False。
    # 建議下游檢查用顯式 `is True` 比對：
    #   if p.kmt_member is True:  ✅ agent 確定是 KMT 黨員
    #   if p.kmt_member:          ⚠️ None 會誤判為非黨員
    # 或在過濾時用 `bool(getattr(p, col, None) or False)` 安全包裹（Task 12 predictor 即採此法）
    kmt_member: bool | None = None
    dpp_member: bool | None = None
    tpp_member: bool | None = None

    custom_fields: dict[str, str] = {}
