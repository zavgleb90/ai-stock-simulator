# simulator/reporting.py
from __future__ import annotations

from typing import Dict, List, Tuple
import pandas as pd

from .portfolio import Portfolio

def build_positions_report(portfolios: List[Portfolio], close_prices: Dict[str, float], date: str) -> pd.DataFrame:
    rows = []
    for p in portfolios:
        nav = p.nav(close_prices)
        for sym, qty in p.positions.items():
            px = close_prices.get(sym, 0.0)
            mv = qty * px
            w = (mv / nav) if nav > 0 else 0.0
            avg = p.avg_cost.get(sym, 0.0)
            unreal = (px - avg) * qty
            rows.append({
                "date": date,
                "team": p.team,
                "ticker": sym,
                "qty": qty,
                "close": round(px, 4),
                "avg_cost": round(avg, 4),
                "market_value": round(mv, 2),
                "weight": round(w, 6),
                "unrealized_pnl": round(unreal, 2),
            })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values(["team", "market_value"], ascending=[True, False])

def build_pnl_report(portfolios: List[Portfolio], close_prices: Dict[str, float], date: str, initial_cash: float) -> pd.DataFrame:
    rows = []
    for p in portfolios:
        nav = p.nav(close_prices)
        unreal = 0.0
        for sym, qty in p.positions.items():
            px = close_prices.get(sym, 0.0)
            avg = p.avg_cost.get(sym, 0.0)
            unreal += (px - avg) * qty

        total_pnl = (nav - initial_cash)
        rows.append({
            "date": date,
            "team": p.team,
            "nav": round(nav, 2),
            "cash": round(p.cash, 2),
            "realized_pnl": round(p.realized_pnl, 2),
            "unrealized_pnl": round(unreal, 2),
            "total_pnl": round(total_pnl, 2),
            "total_return": round(total_pnl / initial_cash, 6),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("nav", ascending=False)
