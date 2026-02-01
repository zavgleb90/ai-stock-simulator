# simulator/portfolio.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

@dataclass
class Portfolio:
    team: str
    cash: float
    positions: Dict[str, int] = field(default_factory=dict)  # shares
    avg_cost: Dict[str, float] = field(default_factory=dict) # average cost per share
    realized_pnl: float = 0.0

    @classmethod
    def initial(cls, cash: float = 100_000.0, team: str = "team") -> "Portfolio":
        return cls(team=team, cash=float(cash))


    def position_value(self, prices: Dict[str, float]) -> float:
        return sum(self.positions.get(sym, 0) * prices.get(sym, 0.0) for sym in self.positions)

    def nav(self, prices: Dict[str, float]) -> float:
        return self.cash + self.position_value(prices)

    def buy(self, sym: str, qty: int, price: float, fee: float = 0.0) -> None:
        if qty <= 0:
            return
        cost = qty * price + fee
        if cost > self.cash + 1e-9:
            raise ValueError(f"Insufficient cash for buy: need {cost:.2f}, have {self.cash:.2f}")

        prev_qty = self.positions.get(sym, 0)
        prev_cost = self.avg_cost.get(sym, 0.0)

        new_qty = prev_qty + qty
        # weighted average cost
        new_avg = ((prev_qty * prev_cost) + (qty * price)) / max(new_qty, 1)

        self.positions[sym] = new_qty
        self.avg_cost[sym] = new_avg
        self.cash -= cost

    def sell(self, sym: str, qty: int, price: float, fee: float = 0.0) -> None:
        if qty <= 0:
            return
        prev_qty = self.positions.get(sym, 0)
        if qty > prev_qty:
            raise ValueError(f"Insufficient shares to sell {sym}: sell {qty}, have {prev_qty}")

        cost_basis = self.avg_cost.get(sym, 0.0)
        proceeds = qty * price - fee
        pnl = (price - cost_basis) * qty

        self.realized_pnl += pnl
        self.cash += proceeds

        new_qty = prev_qty - qty
        if new_qty == 0:
            self.positions.pop(sym, None)
            self.avg_cost.pop(sym, None)
        else:
            self.positions[sym] = new_qty
