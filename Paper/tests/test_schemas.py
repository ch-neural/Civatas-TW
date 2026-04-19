"""Basic schema instantiation tests."""
from __future__ import annotations

from ctw_va.data.schemas import Article, Person, VendorResponse


def test_person_instantiation():
    p = Person(
        person_id="p001",
        age=35,
        gender="女",
        county="臺北市",
        township="大安區",
        education="大學",
        occupation="工程師",
        ethnicity="閩南",
        household_income="5-7萬",
        party_lean="偏綠",
        media_habit="網路新聞",
    )
    assert p.person_id == "p001"
    assert p.party_lean == "偏綠"
    assert p.age == 35


def test_article_instantiation():
    a = Article(
        article_id="abc123def456",
        url="https://ltn.com.tw/news/123",
        title="賴清德支持率上升",
        snippet="根據最新民調...",
        source_domain="ltn.com.tw",
        source_tag="自由時報",
        source_leaning="偏綠",
        stage="A",
    )
    assert a.article_id == "abc123def456"
    assert a.excluded is False
    assert a.published_date is None


def test_article_with_optional_fields():
    a = Article(
        article_id="xyz",
        url="https://chinatimes.com/news/456",
        title="侯友宜表示...",
        snippet="國民黨候選人...",
        source_domain="chinatimes.com",
        source_tag="中時新聞網",
        source_leaning="偏藍",
        stage="B",
        excluded=True,
        published_date="2024-01-08",
    )
    assert a.excluded is True
    assert a.published_date == "2024-01-08"


def test_vendor_response_instantiation():
    vr = VendorResponse(
        vendor="openai",
        model_id="gpt-4o-mini",
        status="ok",
        raw_text='{"satisfaction": 52, "anxiety": 45}',
        input_tokens=1500,
        output_tokens=300,
    )
    assert vr.vendor == "openai"
    assert vr.cached_tokens == 0
    assert vr.cost_usd == 0.0
    assert vr.attempt == 1
    assert vr.system_fingerprint is None
    assert vr.error_detail is None


def test_vendor_response_with_all_fields():
    vr = VendorResponse(
        vendor="gemini",
        model_id="gemini-2.5-flash-lite",
        status="refusal_text",
        raw_text="I cannot simulate political opinions...",
        input_tokens=2000,
        output_tokens=50,
        cached_tokens=500,
        cost_usd=0.000325,
        latency_ms=1200,
        finish_reason="stop",
        system_fingerprint="fp_abc",
        error_detail=None,
        attempt=2,
    )
    assert vr.status == "refusal_text"
    assert vr.cached_tokens == 500
    assert vr.attempt == 2
