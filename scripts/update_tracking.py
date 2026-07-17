#!/usr/bin/env python3
"""Fetch delayed market data and build data/tracking.json.

Data source: Yahoo Finance chart endpoints (unofficial, delayed, best-effort).
The script uses only Python's standard library so GitHub Actions needs no pip install.
"""

from __future__ import annotations

import json
import math
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

OUTPUT = Path(__file__).resolve().parents[1] / "data" / "tracking.json"

TICKERS = {
    "NDXTR_USD": "^XNDX",
    "QQQ": "QQQ",
    "00662": "00662.TW",
    "009800": "009800.TW",
    "USDTWD": "TWD=X",
}

BENCHMARK = {
    "QQQ": "NDXTR_USD",
    "00662": "NDXTR_TWD",
    "009800": "NDXTR_TWD",
}

PERIODS = ("1M", "3M", "YTD", "1Y", "3Y", "SI")
USER_AGENT = "Mozilla/5.0 (compatible; NDXL-Tracker/2.0; +https://github.com/)"


@dataclass(frozen=True)
class Point:
    date: str
    value: float


def fetch_chart(ticker: str, range_: str = "10y") -> list[Point]:
    encoded = urllib.parse.quote(ticker, safe="")
    errors: list[str] = []
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        url = (
            f"https://{host}/v8/finance/chart/{encoded}"
            f"?range={range_}&interval=1d&events=div%2Csplits&includeAdjustedClose=true"
        )
        for attempt in range(3):
            try:
                request = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": USER_AGENT,
                        "Accept": "application/json,text/plain,*/*",
                    },
                )
                with urllib.request.urlopen(request, timeout=25) as response:
                    payload = json.load(response)
                result = payload.get("chart", {}).get("result")
                if not result:
                    error = payload.get("chart", {}).get("error")
                    raise RuntimeError(f"No chart result: {error}")
                item = result[0]
                timestamps = item.get("timestamp") or []
                indicators = item.get("indicators") or {}
                adjusted = (
                    (indicators.get("adjclose") or [{}])[0].get("adjclose")
                    or (indicators.get("quote") or [{}])[0].get("close")
                    or []
                )
                points: list[Point] = []
                for ts, value in zip(timestamps, adjusted):
                    if value is None:
                        continue
                    number = float(value)
                    if not math.isfinite(number) or number <= 0:
                        continue
                    date = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
                    points.append(Point(date, number))
                deduped = {p.date: p for p in points}
                output = [deduped[d] for d in sorted(deduped)]
                if len(output) < 2:
                    raise RuntimeError("Insufficient valid observations")
                return output
            except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError, KeyError) as exc:
                errors.append(f"{host} attempt {attempt + 1}: {exc}")
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("; ".join(errors[-6:]))


def to_map(points: Iterable[Point]) -> dict[str, float]:
    return {p.date: p.value for p in points}


def combine_twd(index: list[Point], fx: list[Point]) -> list[Point]:
    imap, fmap = to_map(index), to_map(fx)
    dates = sorted(set(imap) & set(fmap))
    return [Point(date, imap[date] * fmap[date]) for date in dates]


def date_floor(code: str, end: str, first: str) -> str:
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    if code == "YTD":
        return f"{end_dt.year}-01-01"
    if code == "SI":
        return first
    months = {"1M": 1, "3M": 3, "1Y": 12, "3Y": 36}[code]
    year = end_dt.year
    month = end_dt.month - months
    while month <= 0:
        month += 12
        year -= 1
    day = min(end_dt.day, 28)
    return f"{year:04d}-{month:02d}-{day:02d}"


def metric(product: list[Point], benchmark: list[Point], code: str) -> dict | None:
    pmap, bmap = to_map(product), to_map(benchmark)
    common = sorted(set(pmap) & set(bmap))
    if len(common) < 2:
        return None
    end = common[-1]
    floor = date_floor(code, end, common[0])
    dates = [d for d in common if d >= floor]
    if len(dates) < 2:
        return None
    first, last = dates[0], dates[-1]
    product_return = (pmap[last] / pmap[first] - 1) * 100
    benchmark_return = (bmap[last] / bmap[first] - 1) * 100
    excess_daily: list[float] = []
    for previous, current in zip(dates, dates[1:]):
        product_daily = pmap[current] / pmap[previous] - 1
        benchmark_daily = bmap[current] / bmap[previous] - 1
        excess_daily.append(product_daily - benchmark_daily)
    tracking_error = None
    if len(excess_daily) >= 2:
        tracking_error = statistics.stdev(excess_daily) * math.sqrt(252) * 100
    difference = product_return - benchmark_return
    score = 100 - abs(difference) * 5
    score -= (tracking_error if tracking_error is not None else 2) * 4
    score = max(0, min(100, round(score)))
    return {
        "from": first,
        "to": last,
        "days": len(dates),
        "return": round(product_return, 4),
        "benchmarkReturn": round(benchmark_return, 4),
        "difference": round(difference, 4),
        "trackingError": None if tracking_error is None else round(tracking_error, 4),
        "score": score,
    }


def normalized_chart(series: dict[str, list[Point]], max_points: int = 260) -> dict[str, list[dict]]:
    output: dict[str, list[dict]] = {}
    for symbol, points in series.items():
        selected = points[-max_points:]
        if not selected:
            output[symbol] = []
            continue
        base = selected[0].value
        output[symbol] = [
            {"date": point.date, "value": round(point.value / base * 100, 4)}
            for point in selected
        ]
    return output


def main() -> None:
    fetched: dict[str, list[Point]] = {}
    errors: dict[str, str] = {}
    for symbol, ticker in TICKERS.items():
        try:
            fetched[symbol] = fetch_chart(ticker)
            print(f"Fetched {symbol}: {len(fetched[symbol])} rows")
        except Exception as exc:  # noqa: BLE001 - preserve partial output
            errors[symbol] = str(exc)
            print(f"Failed {symbol}: {exc}")

    if "NDXTR_USD" in fetched and "USDTWD" in fetched:
        fetched["NDXTR_TWD"] = combine_twd(fetched["NDXTR_USD"], fetched["USDTWD"])
    else:
        errors["NDXTR_TWD"] = "Requires both NDXTR_USD and USDTWD"

    period_output: dict[str, dict] = {}
    for code in PERIODS:
        rows: list[dict] = []
        for symbol, benchmark_symbol in BENCHMARK.items():
            if symbol not in fetched or benchmark_symbol not in fetched:
                continue
            value = metric(fetched[symbol], fetched[benchmark_symbol], code)
            if value:
                rows.append({"symbol": symbol, "benchmark": benchmark_symbol, **value})
        rows.sort(key=lambda row: (-row["score"], abs(row["difference"])))
        period_output[code] = {"rows": rows}

    available_dates = [points[-1].date for symbol, points in fetched.items() if symbol != "USDTWD" and points]
    as_of = min(available_dates) if available_dates else None
    status = "ok" if len(period_output.get("1Y", {}).get("rows", [])) == 3 else "partial"
    payload = {
        "status": status,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "asOf": as_of,
        "source": {
            "name": "Yahoo Finance chart endpoint",
            "official": False,
            "note": "非官方延遲資料；Adjusted Close 作為含息總報酬代理。",
        },
        "methodology": {
            "trackingDifference": "產品期間報酬－對應幣別基準期間報酬",
            "trackingError": "每日超額報酬樣本標準差×√252",
            "currency": "QQQ 對美元 NDXTR；00662、009800 對換算新台幣的 NDXTR。",
        },
        "periods": period_output,
        "chart": normalized_chart(
            {key: value for key, value in fetched.items() if key in {"NDXTR_USD", "NDXTR_TWD", "QQQ", "00662", "009800"}}
        ),
        "errors": errors,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT}")

    if not period_output.get("1M", {}).get("rows"):
        raise SystemExit("No comparable product/benchmark pairs were produced")


if __name__ == "__main__":
    main()
