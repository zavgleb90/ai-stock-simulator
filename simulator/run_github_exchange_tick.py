# simulator/run_github_exchange_tick.py
from __future__ import annotations

import argparse
import json
import os
from typing import Dict, List, Any, Optional

import pandas as pd

from .live_tape import LiveTapeConfig, load_or_create_state, save_state, step_one_bar, append_outputs
from .execution import ExecConfig, apply_slippage
from .state_io import load_portfolio, save_portfolio
from .risk import RiskConfig, check_order_weight_limit
from .reporting import build_positions_report, build_pnl_report
from .limit_fill import limit_order_fills, limit_fill_price
from .dashboard_snapshot import build_latest_prices_snapshot, build_latest_news_snapshot

from .github_issue_parser import parse_order_from_issue_body, ParsedOrder


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="GitHub Exchange Tick: hourly bar + execute orders + publish snapshots.")
    p.add_argument("--orders_json", required=True, help="Path to JSON file containing GitHub issues (orders).")
    p.add_argument("--initial_cash", type=float, default=100000.0)
    p.add_argument("--fee", type=float, default=1.0)
    p.add_argument("--slippage_bps", type=float, default=5.0)
    p.add_argument("--max_pos_w", type=float, default=0.20)

    p.add_argument("--state_dir", default="data/state")
    p.add_argument("--reports_dir", default="data/reports")
    p.add_argument("--leaderboards_dir", default="data/leaderboards")

    p.add_argument("--prices_out", default="data/market/prices_hourly.csv")
    p.add_argument("--news_out", default="data/market/news_hourly.jsonl")
    p.add_argument("--market_state", default="data/state/market_state.json")
    p.add_argument("--security_master", default="data/reference/ticker_info.csv")

    # dashboard output
    p.add_argument("--site_data_dir", default="site/data")
    return p


def _load_issues(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)
    # expected: {"issues":[...]}
    return obj.get("issues", obj)


def main() -> None:
    args = build_parser().parse_args()

    os.makedirs(args.state_dir, exist_ok=True)
    os.makedirs(args.reports_dir, exist_ok=True)
    os.makedirs(args.leaderboards_dir, exist_ok=True)
    os.makedirs(args.site_data_dir, exist_ok=True)

    # 1) Generate next hourly bar
    live_cfg = LiveTapeConfig(
        state_path=args.market_state,
        prices_out=args.prices_out,
        news_out=args.news_out,
        security_master_csv=args.security_master,
    )
    market_state = load_or_create_state(live_cfg)
    ts, bar_df, news_rows = step_one_bar(live_cfg, market_state)
    append_outputs(live_cfg, bar_df, news_rows)
    save_state(live_cfg, market_state)

    # Lookups for this bar (execution at this bar close)
    px_by_ticker: Dict[str, Dict] = {r["ticker"]: r for _, r in bar_df.iterrows()}
    close_prices: Dict[str, float] = {t: float(px_by_ticker[t]["close"]) for t in px_by_ticker}

    exec_cfg = ExecConfig(fee_per_trade=float(args.fee), slippage_bps=float(args.slippage_bps), execution_price="close")
    risk_cfg = RiskConfig(max_position_weight=float(args.max_pos_w))

    # 2) Load issues (orders)
    issues = _load_issues(args.orders_json)

    # Parse orders
    parsed: List[Dict[str, Any]] = []
    for it in issues:
        body = (it.get("body") or "").strip()
        number = it.get("number")
        created_at = it.get("created_at")
        user = (it.get("user") or {}).get("login")

        try:
            order: ParsedOrder = parse_order_from_issue_body(body)
            parsed.append({
                "issue_number": number,
                "created_at": created_at,
                "user": user,
                "order": order,
            })
        except Exception as e:
            parsed.append({
                "issue_number": number,
                "created_at": created_at,
                "user": user,
                "error": str(e),
            })

    # Keep only valid orders
    valid = [x for x in parsed if "order" in x]
    # Execute all orders for THIS tick timestamp (ts)
    # In Step 3B, the rule is:
    #   - any order submitted since last tick is executed at THIS tick close
    teams = sorted(set(x["order"].team for x in valid))
    trade_log_rows = []

    for team in teams:
        p = load_portfolio(args.state_dir, team, args.initial_cash)

        team_orders = [x for x in valid if x["order"].team == team]
        for x in team_orders:
            o: ParsedOrder = x["order"]
            issue_no = x["issue_number"]

            if o.ticker not in px_by_ticker:
                trade_log_rows.append({"timestamp": ts, "team": team, "ticker": o.ticker, "side": o.side, "qty": o.qty,
                                       "issue": issue_no, "status": "REJECT_NO_PRICE"})
                continue

            bar_high = float(px_by_ticker[o.ticker]["high"])
            bar_low = float(px_by_ticker[o.ticker]["low"])
            bar_close = float(px_by_ticker[o.ticker]["close"])

            if o.order_type == "LIMIT":
                assert o.limit_price is not None
                if not limit_order_fills(o.side, o.limit_price, bar_high, bar_low):
                    trade_log_rows.append({"timestamp": ts, "team": team, "ticker": o.ticker, "side": o.side, "qty": o.qty,
                                           "issue": issue_no, "status": "UNFILLED_LIMIT"})
                    continue
                raw_px = limit_fill_price(o.side, o.limit_price)
            else:
                raw_px = bar_close  # MARKET executes at this tick close

            exec_px = apply_slippage(raw_px, o.side, exec_cfg.slippage_bps)

            ok, reason = check_order_weight_limit(
                portfolio=p,
                ticker=o.ticker,
                side=o.side,
                qty=o.qty,
                exec_price=exec_px,
                close_prices=close_prices,
                cfg=risk_cfg,
            )
            if not ok:
                trade_log_rows.append({"timestamp": ts, "team": team, "ticker": o.ticker, "side": o.side, "qty": o.qty,
                                       "issue": issue_no, "status": f"REJECT_{reason}"})
                continue

            try:
                if o.side == "BUY":
                    p.buy(o.ticker, o.qty, exec_px, fee=exec_cfg.fee_per_trade)
                else:
                    p.sell(o.ticker, o.qty, exec_px, fee=exec_cfg.fee_per_trade)

                trade_log_rows.append({
                    "timestamp": ts, "team": team, "ticker": o.ticker, "side": o.side, "qty": o.qty,
                    "price": round(exec_px, 4), "fee": exec_cfg.fee_per_trade, "issue": issue_no,
                    "status": "FILLED", "order_type": o.order_type, "limit_price": o.limit_price
                })
            except Exception as e:
                trade_log_rows.append({"timestamp": ts, "team": team, "ticker": o.ticker, "side": o.side, "qty": o.qty,
                                       "issue": issue_no, "status": f"REJECT_{type(e).__name__}"})

        save_portfolio(args.state_dir, p)

    # 3) Reporting
    portfolios: List = []
    for fn in os.listdir(args.state_dir):
        if fn.startswith("portfolio_") and fn.endswith(".json"):
            team = fn[len("portfolio_"):-len(".json")]
            portfolios.append(load_portfolio(args.state_dir, team, args.initial_cash))

    date_only = ts.split(" ")[0]
    pos_df = build_positions_report(portfolios, close_prices, date_only)
    pnl_df = build_pnl_report(portfolios, close_prices, date_only, args.initial_cash)

    pos_path = os.path.join(args.reports_dir, f"positions_{ts.replace(':','-').replace(' ','_')}.csv")
    pnl_path = os.path.join(args.reports_dir, f"pnl_{ts.replace(':','-').replace(' ','_')}.csv")
    pos_df.to_csv(pos_path, index=False)
    pnl_df.to_csv(pnl_path, index=False)

    # leaderboard
    lb_path = os.path.join(args.leaderboards_dir, "leaderboard.csv")
    pnl_df.to_csv(lb_path, index=False)

    # trades
    if trade_log_rows:
        trade_log = pd.DataFrame(trade_log_rows)
        trade_path = os.path.join(args.leaderboards_dir, f"trades_{ts.replace(':','-').replace(' ','_')}.csv")
        trade_log.to_csv(trade_path, index=False)

    # 4) Dashboard snapshots
    latest_prices_json = os.path.join(args.site_data_dir, "latest_prices.json")
    latest_news_json = os.path.join(args.site_data_dir, "latest_news.json")
    leaderboard_json = os.path.join(args.site_data_dir, "leaderboard.json")

    build_latest_prices_snapshot(args.prices_out, latest_prices_json)
    build_latest_news_snapshot(args.news_out, latest_news_json)

    # leaderboard json
    with open(leaderboard_json, "w", encoding="utf-8") as f:
        json.dump({"timestamp": ts, "rows": pnl_df.to_dict(orient="records")}, f, indent=2)

    print(f"✅ Exchange tick complete: {ts}")
    print(f"Orders processed: {len(valid)} (issues parsed from {len(issues)})")
    print(f"Trades logged: {len(trade_log_rows)}")
    print(f"Snapshots: {args.site_data_dir}")


if __name__ == "__main__":
    main()
