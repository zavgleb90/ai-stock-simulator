# simulator/execution.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

@dataclass(frozen=True)
class ExecConfig:
    fee_per_trade: float = 1.00            # flat $ fee
    slippage_bps: float = 5.0              # 5 bps = 0.05%
    execution_price: str = "close"         # "open" or "close"

def apply_slippage(price: float, side: str, slippage_bps: float) -> float:
    """
    Buy pays up, sell receives less.
    """
    bps = slippage_bps / 10_000.0
    if side.lower() == "buy":
        return price * (1.0 + bps)
    if side.lower() == "sell":
        return price * (1.0 - bps)
    raise ValueError("side must be BUY or SELL")

def get_execution_price(px_row: Dict, which: str) -> float:
    if which == "open":
        return float(px_row["open"])
    if which == "close":
        return float(px_row["close"])
    raise ValueError("execution_price must be 'open' or 'close'")
