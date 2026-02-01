# simulator/limit_fill.py
from __future__ import annotations

from typing import Optional, Tuple

def limit_order_fills(side: str, limit_price: float, bar_high: float, bar_low: float) -> bool:
    """
    Simple touch logic:
      BUY  fills if low <= limit
      SELL fills if high >= limit
    """
    side = side.upper().strip()
    if side == "BUY":
        return bar_low <= limit_price
    if side == "SELL":
        return bar_high >= limit_price
    raise ValueError("side must be BUY or SELL")

def limit_fill_price(side: str, limit_price: float) -> float:
    """
    Use limit price as fill price (conservative and simple).
    """
    return float(limit_price)
