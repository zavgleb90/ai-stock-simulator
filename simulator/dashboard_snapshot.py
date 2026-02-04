# simulator/dashboard_snapshot.py
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Any

import pandas as pd


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def write_json(path: str, obj: Any) -> None:
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _load_company_map(ticker_info_csv: Optional[str]) -> Dict[str, str]:
    """
    Best-effort mapping ticker -> company name.
    Works with typical column names like:
      - ticker / symbol
      - company_name / name / companyName
    """
    if not ticker_info_csv or not os.path.exists(ticker_info_csv):
        return {}

    try:
        info = pd.read_csv(ticker_info_csv)
    except Exception:
        return {}

    cols = {c.lower(): c for c in info.columns}

    ticker_col = cols.get("ticker") or cols.get("symbol")
    if not ticker_col:
        return {}

    name_col = (
        cols.get("company_name")
        or cols.get("companyname")
        or cols.get("name")
        or cols.get("company")
    )
    if not name_col:
        return {}

    m: Dict[str, str] = {}
    for _, r in info.iterrows():
        t = str(r.get(ticker_col, "")).strip().upper()
        nm = str(r.get(name_col, "")).strip()
        if t:
            m[t] = nm
    return m


def build_latest_prices_snapshot(
    prices_hourly_csv: str,
    out_path: str,
    max_rows: int = 87,
    lookback: int = 60,
    ticker_info_csv: Optional[str] = None,
) -> None:
    """
    Writes site/data/latest_prices.json with:
      - one row per ticker at the latest timestamp
      - chg/chg_pct vs previous bar
      - series (last `lookback` closes) + series_ts for charts
    """
    df = pd.read_csv(prices_hourly_csv)
    if df.empty:
        write_json(out_path, {"timestamp": None, "rows": []})
        return

    # Defensive: ensure required columns exist
    required = {"timestamp", "ticker", "close"}
    missing = required - set(df.columns)
    if missing:
        write_json(out_path, {"timestamp": None, "rows": [], "error": f"Missing columns: {sorted(missing)}"})
        return

    df_sorted = df.sort_values(["ticker", "timestamp"]).copy()
    df_sorted["prev_close"] = df_sorted.groupby("ticker")["close"].shift(1)
    df_sorted["chg"] = df_sorted["close"] - df_sorted["prev_close"]
    df_sorted["chg_pct"] = df_sorted["chg"] / df_sorted["prev_close"]

    latest_ts = df_sorted["timestamp"].iloc[-1]
    last = df_sorted[df_sorted["timestamp"] == latest_ts].copy()

    company_map = _load_company_map(ticker_info_csv)

    rows: List[Dict[str, Any]] = []
    # Keep stable ordering
    last = last.sort_values("ticker")

    for _, r in last.iterrows():
        t = str(r["ticker"]).upper()

        hist = df_sorted[df_sorted["ticker"] == t].tail(int(lookback))
        series = [round(float(x), 4) for x in hist["close"].tolist()]
        series_ts = [str(x) for x in hist["timestamp"].tolist()]

        rows.append({
            "ticker": t,
            "company_name": company_map.get(t, ""),
            "sector": str(r.get("sector", "")),
            "close": round(float(r["close"]), 4),
            "volume": int(r.get("volume", 0)) if pd.notna(r.get("volume", 0)) else 0,
            "chg": round(float(r["chg"]), 4) if pd.notna(r.get("chg")) else 0.0,
            "chg_pct": float(r["chg_pct"]) if pd.notna(r.get("chg_pct")) else 0.0,
            "series": series,
            "series_ts": series_ts,
        })

    write_json(out_path, {"timestamp": str(latest_ts), "rows": rows[:max_rows]})


def build_latest_news_snapshot(news_jsonl: str, out_path: str, limit: int = 50) -> None:
    if not os.path.exists(news_jsonl):
        write_json(out_path, {"timestamp": None, "items": []})
        return

    items = []
    with open(news_jsonl, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))

    items = items[-limit:]
    latest_ts = items[-1]["timestamp"] if items else None
    write_json(out_path, {"timestamp": latest_ts, "items": items})
