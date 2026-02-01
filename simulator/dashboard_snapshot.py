# simulator/dashboard_snapshot.py
from __future__ import annotations

import json
import os
from typing import Dict, List

import pandas as pd

def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def write_json(path: str, obj) -> None:
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def build_latest_prices_snapshot(prices_hourly_csv: str, out_path: str, max_rows: int = 87) -> None:
    df = pd.read_csv(prices_hourly_csv)
    if df.empty:
        write_json(out_path, {"timestamp": None, "rows": []})
        return

    # latest timestamp rows for all tickers
    latest_ts = df["timestamp"].iloc[-1]
    last = df[df["timestamp"] == latest_ts].copy()

    # compute change vs previous tick for each ticker
    df_sorted = df.sort_values(["ticker", "timestamp"])
    df_sorted["prev_close"] = df_sorted.groupby("ticker")["close"].shift(1)
    df_sorted["chg"] = df_sorted["close"] - df_sorted["prev_close"]
    df_sorted["chg_pct"] = df_sorted["chg"] / df_sorted["prev_close"]
    last2 = df_sorted[df_sorted["timestamp"] == latest_ts].copy()

    keep_cols = ["ticker", "sector", "close", "volume", "chg", "chg_pct"]
    rows = last2[keep_cols].fillna(0.0).to_dict(orient="records")

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
