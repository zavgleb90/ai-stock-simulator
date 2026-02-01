# simulator/state_io.py
from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import Dict

from .portfolio import Portfolio

def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def portfolio_path(state_dir: str, team: str) -> str:
    return os.path.join(state_dir, f"portfolio_{team}.json")

def save_portfolio(state_dir: str, p: Portfolio) -> None:
    ensure_dir(state_dir)
    with open(portfolio_path(state_dir, p.team), "w", encoding="utf-8") as f:
        json.dump(asdict(p), f, indent=2)

def load_portfolio(state_dir: str, team: str, initial_cash: float) -> Portfolio:
    path = portfolio_path(state_dir, team)
    if not os.path.exists(path):
        return Portfolio(team=team, cash=float(initial_cash))

    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    return Portfolio(
        team=d["team"],
        cash=float(d["cash"]),
        positions={k: int(v) for k, v in d.get("positions", {}).items()},
        avg_cost={k: float(v) for k, v in d.get("avg_cost", {}).items()},
        realized_pnl=float(d.get("realized_pnl", 0.0)),
    )
