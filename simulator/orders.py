# simulator/orders.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import pandas as pd

@dataclass(frozen=True)
class Order:
    date: str
    team: str
    ticker: str
    side: str   # BUY/SELL
    qty: int

def load_orders_csv(path: str) -> list[Order]:
    """
    Expected columns: date, team, ticker, side, qty
    """
    df = pd.read_csv(path)
    required = {"date", "team", "ticker", "side", "qty"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Orders CSV missing columns: {sorted(missing)}")

    orders: list[Order] = []
    for _, r in df.iterrows():
        orders.append(Order(
            date=str(r["date"]),
            team=str(r["team"]),
            ticker=str(r["ticker"]).upper().strip(),
            side=str(r["side"]).upper().strip(),
            qty=int(r["qty"]),
        ))
    return orders
