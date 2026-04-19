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


# ════════════════════════════════════════════════════════════════════
# 匯率 — USD/TWD、JPY/TWD（與 TAIEX 同 Yahoo Finance API）
# ════════════════════════════════════════════════════════════════════

async def fetch_forex_range(symbol: str, start_date: str, end_date: str) -> dict[str, dict[str, float]]:
    """Fetch a currency pair's daily close for [start, end].
    symbol: e.g. 'USDTWD=X' or 'JPYTWD=X'.
    Returns {"YYYY-MM-DD": {"close": float, "pct": float-vs-open}, ...}
    """
    cache_key = f"forex|{symbol}|{start_date}|{end_date}"
    cache = _load_cache()
    if cache_key in cache:
        return cache[cache_key]

    from urllib.parse import quote
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}"
    params = {
        "period1": str(_date_to_ts(start_date)),
        "period2": str(_date_to_ts(end_date, end_of_day=True)),
        "interval": "1d",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params, headers={"User-Agent": _UA})
            resp.raise_for_status()
            payload = resp.json()
        result = payload["chart"]["result"][0]
        timestamps = result.get("timestamp") or []
        quote_ = (result.get("indicators") or {}).get("quote", [{}])[0]
        opens = quote_.get("open") or []
        closes = quote_.get("close") or []
    except Exception as e:
        logger.warning(f"Forex {symbol} fetch failed: {e}")
        return {}

    out: dict[str, dict[str, float]] = {}
    for ts, op, cl in zip(timestamps, opens, closes):
        if op is None or cl is None:
            continue
        day = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        pct = (cl - op) / op * 100 if op else 0.0
        out[day] = {"open": round(op, 4), "close": round(cl, 4), "pct": round(pct, 3)}

    cache[cache_key] = out
    _save_cache(cache)
    return out


def summarise_forex(data: dict[str, dict[str, float]], label: str) -> dict[str, Any]:
    if not data:
        return {"label": label, "trading_days": 0}
    dates = sorted(data.keys())
    first = data[dates[0]]
    last = data[dates[-1]]
    total_pct = (last["close"] - first["open"]) / first["open"] * 100 if first["open"] else 0.0
    return {
        "label": label,
        "trading_days": len(dates),
        "range_open": first["open"],
        "range_close": last["close"],
        "total_pct": round(total_pct, 3),
    }


def format_forex_zh(usd: dict, jpy: dict) -> str:
    """Render USD+JPY forex summaries as one Chinese line."""
    parts = []
    for s in (usd, jpy):
        if s.get("trading_days", 0) == 0: continue
        total = s.get("total_pct", 0.0)
        if abs(total) < 0.3:
            trend = f"持平 ({total:+.2f}%)"
        elif total > 0:
            trend = f"升值 {total:+.2f}%"
        else:
            trend = f"貶值 {total:+.2f}%"
        parts.append(f"{s['label']} {s['range_close']:.3f} / {trend}")
    if not parts:
        return ""
    return "[匯率] " + " | ".join(parts) + "\n"


# ════════════════════════════════════════════════════════════════════
# 油價 — CPC current API + historical seed table
# ════════════════════════════════════════════════════════════════════

# Monthly average 95 無鉛汽油 price (NT$/L). Used for historical dates where
# the CPC current-price API can't help (it only returns today's price).
# Numbers are approximate historical averages from public CPC archives —
# precise enough for simulation macro_context. Update when you have better
# data or when 2026-Q3+ happens.
_OIL_95_MONTHLY = {
    "2024-01": 30.9, "2024-02": 30.5, "2024-03": 31.1, "2024-04": 32.2,
    "2024-05": 32.8, "2024-06": 32.3, "2024-07": 32.5, "2024-08": 31.9,
    "2024-09": 31.1, "2024-10": 31.3, "2024-11": 30.8, "2024-12": 30.2,
    "2025-01": 30.6, "2025-02": 30.8, "2025-03": 31.1, "2025-04": 30.9,
    "2025-05": 30.5, "2025-06": 31.0, "2025-07": 31.5, "2025-08": 31.8,
    "2025-09": 32.0, "2025-10": 32.4, "2025-11": 32.9, "2025-12": 33.2,
    "2026-01": 33.3, "2026-02": 33.5, "2026-03": 33.7, "2026-04": 33.9,
}

_OIL_CPC_XML = "https://vipmbr.cpc.com.tw/CPCSTN/ListPriceWebService.asmx/getCPCMainProdListPrice_XML"


async def fetch_current_oil() -> dict[str, float]:
    """Fetch today's CPC retail oil prices. Returns {'95':, '92':, '98':, '柴油':, 'date':}."""
    cache = _load_cache()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cache_key = f"oil_current|{today}"
    if cache_key in cache:
        return cache[cache_key]
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(_OIL_CPC_XML, headers={"User-Agent": _UA})
            resp.raise_for_status()
            xml = resp.text
    except Exception as e:
        logger.warning(f"CPC oil fetch failed: {e}")
        return {}

    # Minimal XML parse — we just need <產品名稱> + <參考牌價_金額>
    import re
    blocks = re.findall(r"<Table>(.*?)</Table>", xml, re.DOTALL)
    out: dict[str, float] = {}
    for b in blocks:
        m_name = re.search(r"<產品名稱>(.*?)</產品名稱>", b)
        m_price = re.search(r"<參考牌價_金額>(.*?)</參考牌價_金額>", b)
        if not (m_name and m_price): continue
        name = m_name.group(1).strip()
        try: price = float(m_price.group(1).strip())
        except ValueError: continue
        if "98無鉛" in name: out["98"] = price
        elif "95無鉛" in name: out["95"] = price
        elif "92無鉛" in name: out["92"] = price
        elif "超級柴油" in name or "柴油" in name: out["柴油"] = price
    if out:
        out["date"] = today
        cache[cache_key] = out
        _save_cache(cache)
    return out


def get_oil_snapshot(simulation_date: str) -> dict[str, Any]:
    """Return oil-price snapshot for the simulation's effective date.

    Logic: if the simulation date is within 14 days of today, use the live
    CPC API (via cache). Otherwise fall back to the historical monthly seed
    table. Returns {'95_current': float, '95_3mo_ago': float, 'trend': str}.
    """
    try:
        sim_dt = datetime.strptime(simulation_date, "%Y-%m-%d").date()
    except ValueError:
        return {}
    sim_key = f"{sim_dt.year:04d}-{sim_dt.month:02d}"
    current = _OIL_95_MONTHLY.get(sim_key)
    if current is None:
        return {}

    # 3 months earlier
    m = sim_dt.month - 3
    y = sim_dt.year
    while m <= 0:
        m += 12
        y -= 1
    prev_key = f"{y:04d}-{m:02d}"
    prev = _OIL_95_MONTHLY.get(prev_key, current)
    diff = round(current - prev, 2)
    if diff >= 0.5:   trend = f"3 個月漲 +{diff} 元/公升"
    elif diff <= -0.5:trend = f"3 個月跌 {diff} 元/公升"
    else:             trend = f"3 個月持平（{diff:+} 元）"

    return {
        "95_current": current,
        "95_3mo_ago": prev,
        "diff": diff,
        "trend": trend,
        "sim_month": sim_key,
    }


def format_oil_zh(oil: dict) -> str:
    if not oil or "95_current" not in oil:
        return ""
    return (
        f"[油價] 95 無鉛汽油 {oil['95_current']} 元/公升，{oil['trend']}。"
        f" 有車／機車族每次加油可感受到。\n"
    )


# ════════════════════════════════════════════════════════════════════
# Full macro-context builder — 整合 TAIEX + Forex + 油價
# ════════════════════════════════════════════════════════════════════

async def build_full_market_context(start_date: str, end_date: str) -> dict[str, str]:
    """Build three separate market-context strings (taiex / forex / oil) so
    evolver can selectively attach each to the right persona gate."""
    out = {"taiex": "", "forex": "", "oil": ""}
    # 1) TAIEX (existing)
    try:
        out["taiex"] = await build_market_context(start_date, end_date)
    except Exception as e:
        logger.warning(f"TAIEX context failed: {e}")
    # 2) Forex — USD/TWD + JPY/TWD
    try:
        usd_raw = await fetch_forex_range("USDTWD=X", start_date, end_date)
        jpy_raw = await fetch_forex_range("JPYTWD=X", start_date, end_date)
        usd_sum = summarise_forex(usd_raw, "美元")
        jpy_sum = summarise_forex(jpy_raw, "日圓")
        out["forex"] = format_forex_zh(usd_sum, jpy_sum)
    except Exception as e:
        logger.warning(f"Forex context failed: {e}")
    # 3) Oil — snapshot based on start_date month
    try:
        oil = get_oil_snapshot(start_date)
        out["oil"] = format_oil_zh(oil)
    except Exception as e:
        logger.warning(f"Oil context failed: {e}")
    return out


# ════════════════════════════════════════════════════════════════════
# Per-persona filters — 誰會注意哪個指標
# ════════════════════════════════════════════════════════════════════

_TRAVEL_OCC = {"資訊科技", "金融保險", "公部門", "教育", "醫療照護"}
_VEHICLE_AGE_MIN = 22
_VEHICLE_AGE_MAX = 72


def _should_see_forex(agent: dict) -> bool:
    """Forex matters mainly to travellers / import-export professionals /
    overseas-student families / international investors. TW population
    that notices forex day-to-day is ~20%."""
    inc = str(agent.get("household_income") or agent.get("income_band") or "")
    try:
        age = int(agent.get("age") or 0)
    except (TypeError, ValueError):
        age = 0
    occ = str(agent.get("occupation") or "")
    # Lowest income / students / very young / very old — skip
    if inc == "3萬以下": return False
    if occ == "學生": return False
    if age < 25 or age > 70: return False
    # Mid-to-high income → yes
    if inc in _HIGH_INCOME or inc == "5-8萬":
        return True
    # Finance-aware occupation → yes
    if occ in _TRAVEL_OCC:
        return True
    return False


def _should_see_oil(agent: dict) -> bool:
    """Oil price hits anyone who drives / rides a scooter to work / school.
    In Taiwan that's most working-age adults (~75%). Skip only children,
    very elderly, and urban young who don't drive (simplified: everyone
    age 22-72 sees it; students in urban counties are the main exception)."""
    try:
        age = int(agent.get("age") or 0)
    except (TypeError, ValueError):
        age = 0
    if age < _VEHICLE_AGE_MIN or age > _VEHICLE_AGE_MAX:
        return False
    # Young urban students probably take MRT — skip them
    occ = str(agent.get("occupation") or "")
    county = str(agent.get("county") or "")
    if age < 25 and occ == "學生" and county in {"臺北市", "新北市", "高雄市"}:
        return False
    return True


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
