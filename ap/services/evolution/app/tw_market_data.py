"""Taiwan stock market (TAIEX, ^TWII) data fetcher for evolution macro context.

Each evolution round spans a virtual time slice (e.g. days 1-2 of the sim)
which maps to a real calendar date range (e.g. 2024-01-08~09). We fetch the
TAIEX daily OHLC for that range from Yahoo Finance and turn it into a
human-readable Traditional Chinese summary that gets injected into the
agent's `macro_context`. Agents with disposable income react via the diet-
specific income rules in prompts.py (3萬以下 barely reacts, 12-20萬 +2~4
anxiety, etc).

Design notes:
  - Yahoo Finance's unauthenticated chart API is used (needs only a
    browser-ish User-Agent).
  - Responses are cached to disk — the same virtual→real mapping hits the
    same cache entry, so re-running evolution with fixed dates doesn't
    spam Yahoo.
  - If the date range falls entirely on weekends/holidays (no trading
    days), we return a neutral "市場休市" summary instead of skewing the
    macro context with empty data.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_SYMBOL = "%5ETWII"   # ^TWII URL-encoded
_BASE_URL = f"https://query1.finance.yahoo.com/v8/finance/chart/{_SYMBOL}"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_DATA_DIR = os.environ.get("EVOLUTION_DATA_DIR", "/data/evolution")
_CACHE_FILE = Path(_DATA_DIR) / "market_cache.json"


def _load_cache() -> dict[str, Any]:
    if not _CACHE_FILE.exists():
        return {}
    try:
        return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache: dict[str, Any]) -> None:
    _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _date_to_ts(date_str: str, end_of_day: bool = False) -> int:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    if end_of_day:
        dt = dt + timedelta(days=1)
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


async def fetch_taiex_range(start_date: str, end_date: str) -> dict[str, dict[str, float]]:
    """Fetch TAIEX daily OHLC for the [start, end] range (inclusive).

    Returns {"YYYY-MM-DD": {"open": float, "close": float, "pct": float}, ...}
    Empty dict on failure (logged). Results are cached on disk.
    """
    cache_key = f"taiex|{start_date}|{end_date}"
    cache = _load_cache()
    if cache_key in cache:
        return cache[cache_key]

    params = {
        "period1": str(_date_to_ts(start_date)),
        "period2": str(_date_to_ts(end_date, end_of_day=True)),
        "interval": "1d",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(_BASE_URL, params=params, headers={"User-Agent": _UA})
            resp.raise_for_status()
            payload = resp.json()
    except Exception as e:
        logger.warning(f"TAIEX fetch failed for {start_date}~{end_date}: {e}")
        return {}

    try:
        result = payload["chart"]["result"][0]
        timestamps = result.get("timestamp") or []
        quote = (result.get("indicators") or {}).get("quote", [{}])[0]
        opens = quote.get("open") or []
        closes = quote.get("close") or []
    except Exception as e:
        logger.warning(f"TAIEX parse failed for {start_date}~{end_date}: {e}")
        return {}

    out: dict[str, dict[str, float]] = {}
    for ts, op, cl in zip(timestamps, opens, closes):
        if op is None or cl is None:
            continue
        day = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        pct = (cl - op) / op * 100 if op else 0.0
        out[day] = {"open": round(op, 2), "close": round(cl, 2), "pct": round(pct, 2)}

    cache[cache_key] = out
    _save_cache(cache)
    return out


def summarise(data: dict[str, dict[str, float]]) -> dict[str, Any]:
    """Turn the per-day data into range summary."""
    if not data:
        return {"trading_days": 0}
    dates = sorted(data.keys())
    first = data[dates[0]]
    last = data[dates[-1]]
    total_pct = (last["close"] - first["open"]) / first["open"] * 100 if first["open"] else 0.0
    biggest_day = max(dates, key=lambda d: abs(data[d]["pct"]))
    biggest_pct = data[biggest_day]["pct"]
    return {
        "trading_days": len(dates),
        "start_date": dates[0],
        "end_date": dates[-1],
        "range_open": first["open"],
        "range_close": last["close"],
        "total_pct": round(total_pct, 2),
        "biggest_day": biggest_day,
        "biggest_pct": round(biggest_pct, 2),
        "per_day": [(d, data[d]["pct"]) for d in dates],
    }


def format_zh(summary: dict[str, Any], virtual_start: str, virtual_end: str) -> str:
    """Render summary as Traditional Chinese macro-context paragraph."""
    tds = summary.get("trading_days", 0)
    if tds == 0:
        return (
            f"[台股市場狀況 — {virtual_start}~{virtual_end}]\n"
            f"此區間市場休市（週末／國定假日），無開盤資料。\n"
        )
    total = summary.get("total_pct", 0.0)
    open_ = summary.get("range_open", 0)
    close_ = summary.get("range_close", 0)
    big_day = summary.get("biggest_day", "")
    big_pct = summary.get("biggest_pct", 0.0)

    # Tone-word by magnitude
    if total >= 3:   trend = f"大漲 {total:+.2f}%"
    elif total >= 1: trend = f"收漲 {total:+.2f}%"
    elif total > -1: trend = f"小幅波動 {total:+.2f}%"
    elif total > -3: trend = f"收跌 {total:+.2f}%"
    else:            trend = f"重挫 {total:+.2f}%"

    lines = [
        f"[台股市場狀況 — {virtual_start}~{virtual_end}]",
        f"此區間共 {tds} 個交易日，加權指數 {trend}（{open_:.0f} → {close_:.0f}）。",
    ]
    if abs(big_pct) >= 1.5:
        lines.append(
            f"其中 {big_day} 單日{'上漲' if big_pct > 0 else '下跌'} {abs(big_pct):.2f}%。"
        )
    # Agent reaction cue
    if total <= -2:
        lines.append("中高所得族群（月薪 8 萬以上）對此影響敏感；低收入族群反應微弱。")
    elif total >= 2:
        lines.append("投資族群對此偏正面；一般民眾可能關注通膨／資產效應。")
    return "\n".join(lines) + "\n"


async def build_market_context(start_date: str, end_date: str) -> str:
    """Convenience: fetch + summarise + format in one call. Returns empty
    string on total failure so the caller can safely concat into macro_context.
    """
    data = await fetch_taiex_range(start_date, end_date)
    summary = summarise(data)
    return format_zh(summary, start_date, end_date)


# ── Filter: which agents actually pay attention to the stock market ──
#
# Reality check (台灣投資人口):
# - ~ 800 萬證券戶（~40% of 成年人口）
# - 主要集中在 中高所得 + 中壯年 + 白領/專業職 族群
# - 月薪 3 萬以下幾乎不投資（沒閒錢 / 也不看財經）
# - 長者退休族若高資產可能關注（存股、ETF）
# - 學生、低階服務業、基層農漁牧 對股市無感
#
# 我們用 income 為主要判準，age / occupation / media_habit 作為 bump：

_HIGH_INCOME = {"8-12萬", "12-20萬", "20萬以上"}
_MID_INCOME = {"5-8萬"}
_LOW_INCOME = {"3-5萬"}
_VERY_LOW_INCOME = {"3萬以下"}

_STOCK_AWARE_OCC = {"金融保險", "資訊科技", "公部門", "教育", "醫療照護"}
_STOCK_AWARE_MEDIA = {"網路新聞", "報紙", "廣播"}


def _should_see_market(agent: dict) -> bool:
    """Decide whether this agent sees the TAIEX summary in their macro_context.

    Gating logic (designed to mirror real TW investor demographics ~40% of adults):
      - 月薪 3 萬以下：完全跳過（生活線上，沒在看盤）
      - 月薪 3-5 萬：僅 40 歲以上且媒體/職業偏財經才看
      - 月薪 5-8 萬：30 歲以上，或 25+ 且職業／媒體偏財經
      - 月薪 8 萬以上：預設看（除非極年輕 < 22 或學生身份）
      - 年齡 < 22 或 > 80：通常跳過（除非高所得退休族）

    Returns True if agent should see the market macro-context snippet.
    """
    inc = str(agent.get("household_income") or agent.get("income_band") or "").strip()
    try:
        age = int(agent.get("age") or 0)
    except (TypeError, ValueError):
        age = 0
    occ = str(agent.get("occupation") or "")
    media = str(agent.get("media_habit") or "")

    # Hard filters
    if inc in _VERY_LOW_INCOME:
        return False
    if age and age < 22:
        return False
    if age > 80 and inc not in _HIGH_INCOME:
        return False
    if occ == "學生":
        return False

    # High-income → default yes (unless caught by hard filters above)
    if inc in _HIGH_INCOME:
        return True

    # Mid-income (5-8 萬) → age gate + optional bumps
    if inc in _MID_INCOME:
        if age >= 30:
            return True
        if age >= 25 and (occ in _STOCK_AWARE_OCC or any(m in media for m in _STOCK_AWARE_MEDIA)):
            return True
        return False

    # Low income (3-5 萬) → only older + finance-literate
    if inc in _LOW_INCOME:
        if age >= 40 and (occ in _STOCK_AWARE_OCC or any(m in media for m in _STOCK_AWARE_MEDIA)):
            return True
        return False

    # Unknown income: conservative — only older + finance-literate
    if age >= 40 and (occ in _STOCK_AWARE_OCC or any(m in media for m in _STOCK_AWARE_MEDIA)):
        return True
    return False
