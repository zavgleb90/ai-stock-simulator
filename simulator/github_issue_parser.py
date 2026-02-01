# simulator/github_issue_parser.py
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, List

from .universe import TICKERS_87


@dataclass(frozen=True)
class ParsedOrder:
    team: str
    side: str          # BUY/SELL
    ticker: str
    qty: int
    order_type: str    # MARKET/LIMIT
    limit_price: Optional[float]
    notes: str = ""


_SECTION_RE = re.compile(r"^###\s+(?P<key>.+?)\s*$", re.MULTILINE)

def _extract_sections(body: str) -> Dict[str, str]:
    """
    GitHub Issue Forms render as markdown with headings like:

    ### Team name
    team1

    We'll parse into a dict: {"Team name": "team1", ...}
    """
    matches = list(_SECTION_RE.finditer(body))
    sections: Dict[str, str] = {}

    for i, m in enumerate(matches):
        key = m.group("key").strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        value = body[start:end].strip()

        # normalize common blank markers
        value = value.replace("\r\n", "\n").strip()
        sections[key] = value

    return sections


def parse_order_from_issue_body(body: str) -> ParsedOrder:
    sections = _extract_sections(body)

    # keys must match the labels in the form above
    team = (sections.get("Team name") or "").strip()
    side = (sections.get("Side") or "").strip().upper()
    ticker = (sections.get("Ticker") or "").strip().upper()
    qty_raw = (sections.get("Quantity (shares)") or "").strip()
    order_type = (sections.get("Order type") or "").strip().upper()
    limit_raw = (sections.get("Limit price (only if LIMIT)") or "").strip()
    notes = (sections.get("Notes (optional)") or "").strip()

    if not team:
        raise ValueError("Missing team name.")

    if side not in {"BUY", "SELL"}:
        raise ValueError(f"Invalid side: {side}")

    allowed = set(TICKERS_87)
    if ticker not in allowed:
        raise ValueError(f"Ticker not in universe: {ticker}")

    try:
        qty = int(qty_raw)
    except Exception:
        raise ValueError(f"Quantity must be an integer, got: {qty_raw}")
    if qty <= 0:
        raise ValueError("Quantity must be > 0.")

    if order_type not in {"MARKET", "LIMIT"}:
        raise ValueError(f"Invalid order_type: {order_type}")

    limit_price: Optional[float] = None
    if order_type == "LIMIT":
        if not limit_raw:
            raise ValueError("LIMIT order requires a limit price.")
        try:
            limit_price = float(limit_raw)
        except Exception:
            raise ValueError(f"Limit price must be a number, got: {limit_raw}")
        if limit_price <= 0:
            raise ValueError("Limit price must be > 0.")
    else:
        # MARKET ignores limit_price even if student typed one
        limit_price = None

    return ParsedOrder(
        team=team,
        side=side,
        ticker=ticker,
        qty=qty,
        order_type=order_type,
        limit_price=limit_price,
        notes=notes,
    )
