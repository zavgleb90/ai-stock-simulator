# simulator/market_data.py
from __future__ import annotations

import json
from typing import Dict, List

import pandas as pd


def load_prices(prices_path: str) -> pd.DataFrame:
    df = pd.read_csv(prices_path)
    required = {"date", "ticker", "open", "close", "high", "low", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"prices.csv missing columns: {sorted(missing)}")

    df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
    df["date"] = df["date"].astype(str)
    return df


def load_news_jsonl(news_path: str) -> List[Dict]:
    rows: List[Dict] = []
    try:
        with open(news_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
    except FileNotFoundError:
        return []
    return rows


def get_day_prices(prices_df: pd.DataFrame, date: str) -> pd.DataFrame:
    day = prices_df[prices_df["date"] == date].copy()
    if day.empty:
        raise ValueError(f"No prices found for date={date}.")
    return day


def get_day_news(news_rows: List[Dict], date: str) -> List[Dict]:
    return [r for r in news_rows if str(r.get("date")) == str(date)]
