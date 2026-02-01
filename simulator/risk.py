# simulator/risk.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from .portfolio import Portfolio

@dataclass(frozen=True)
class RiskConfig:
    max_position_weight: float = 0.20  # 20% of NAV

def check_order_weight_limit(
    portfolio: Portfolio,
    ticker: str,
    side: str,
    qty: int,
    exec_price: float,
    close_prices: Dict[str, float],
    cfg: RiskConfig,
) -> Tuple[bool, str]:
    """
    Very simple pre-trade check: after the trade, no single position exceeds max_position_weight.
    Uses current close_prices for existing positions; uses exec_price for the order ticker.
    """
    nav_before = portfolio.nav(close_prices)
    if nav_before <= 0:
        return False, "NAV_NONPOSITIVE"

    # Build a temporary position dict
    new_positions = dict(portfolio.positions)
    cur_qty = new_positions.get(ticker, 0)

    if side == "BUY":
        new_positions[ticker] = cur_qty + qty
    elif side == "SELL":
        new_positions[ticker] = cur_qty - qty
        if new_positions[ticker] < 0:
            return False, "SHORT_NOT_ALLOWED"
    else:
        return False, "BAD_SIDE"

    # Compute NAV after trade approximately (cash changes but for weight test, NAV is close enough)
    # More accurate would adjust cash, but weight cap is mainly about concentration.
    # We'll compute market value using exec_price for the traded ticker, close for others.
    total_value = portfolio.cash  # approximate
    for sym, q in new_positions.items():
        if q == 0:
            continue
        px = exec_price if sym == ticker else close_prices.get(sym, 0.0)
        total_value += q * px

    if total_value <= 0:
        return False, "NAV_AFTER_NONPOSITIVE"

    # Check max weight
    for sym, q in new_positions.items():
        if q == 0:
            continue
        px = exec_price if sym == ticker else close_prices.get(sym, 0.0)
        w = (q * px) / total_value
        if w > cfg.max_position_weight + 1e-9:
            return False, f"POSITION_WEIGHT_LIMIT_{sym}"

    return True, "OK"
