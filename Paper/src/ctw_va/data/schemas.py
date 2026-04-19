"""Minimal standalone schemas for CTW-VA-2026."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Person:
    """Simplified Taiwan voter persona for vendor audit experiment.

    Reduced from Civatas Person schema: drops legacy US fields (race,
    hispanic_or_latino) and unused columns; keeps 5-bucket party_lean
    and media_habit required by the experiment.
    """
    person_id: str
    age: int
    gender: str
    county: str
    township: str
    education: str
    occupation: str
    ethnicity: str
    household_income: str
    party_lean: str        # 深綠 / 偏綠 / 中間 / 偏藍 / 深藍
    media_habit: str       # 網路新聞 / 電視新聞 / 社群媒體 / 報紙 / 廣播 / PTT/論壇


@dataclass
class Article:
    article_id: str
    url: str
    title: str
    snippet: str
    source_domain: str
    source_tag: str
    source_leaning: str
    stage: str            # A / B / C
    excluded: bool = False
    published_date: Optional[str] = None


@dataclass
class VendorResponse:
    vendor: str
    model_id: str
    status: str           # ok / refusal_text / refusal_filter / error
    raw_text: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    finish_reason: str = ""
    system_fingerprint: Optional[str] = None
    error_detail: Optional[str] = None
    attempt: int = 1
