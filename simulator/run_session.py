# simulator/run_session.py
from __future__ import annotations
from .reporting import build_positions_report, build_pnl_report
from .risk import RiskConfig, check_order_weight_limit

import argparse
import os
from typing import Dict

import pandas as pd

from .execution import ExecConfig, apply_slippage, get_execution_price
from .orders import load_orders_csv
from .state_io import load_portfolio, save_portfolio
from .market_data import load_prices, load_news_jsonl, get_day_prices, get_day_news


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run one simulated trading day for a given date (daily tape).")
    p.add_argument("--date", required=True, help="Trading date YYYY-MM-DD (must exist in prices.csv)")
    p.add_argument("--prices", default="data/market/prices.csv", help="Path to generated prices.csv")
    p.add_argument("--news", default="data/market/news.jsonl", help="Path to generated news.jsonl")
    p.add_argument("--orders", default="students/orders.csv", help="Orders CSV (date,team,ticker,side,qty)")
    p.add_argument("--state_dir", default="data/state", help="Where portfolios are stored")
    p.add_argument("--initial_cash", type=float, default=100000.0, help="Starting cash per team")
    p.add_argument("--exec_price", default="close", choices=["open", "close"], help="Execute at open or close")
    p.add_argument("--fee", type=float, default=1.0, help="Fee per trade ($)")
    p.add_argument("--slippage_bps", type=float, default=5.0, help="Slippage in basis points")
    p.add_argument("--out_dir", default="data/leaderboards", help="Output folder for leaderboard + trades")
    p.add_argument("--print_news", action="store_true", help="Print today's news headlines")
    p.add_argument("--reports_dir", default="data/reports", help="Output folder for positions/pnl reports")
    p.add_argument("--max_pos_w", type=float, default=0.20, help="Max position weight (e.g., 0.20 = 20%)")

    return p


def main() -> None:
    args = build_parser().parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    os.makedirs(args.reports_dir, exist_ok=True)
    risk_cfg = RiskConfig(max_position_weight=float(args.max_pos_w))


    exec_cfg = ExecConfig(
        fee_per_trade=float(args.fee),
        slippage_bps=float(args.slippage_bps),
        execution_price=str(args.exec_price),
    )

    prices_df = load_prices(args.prices)
    news_rows = load_news_jsonl(args.news)

    day_px = get_day_prices(prices_df, args.date)
    day_news = get_day_news(news_rows, args.date)

    if args.print_news:
        print(f"\n=== NEWS for {args.date} ({len(day_news)} items) ===")
        for n in day_news[:30]:
            ticker = n.get("ticker")
            name = (n.get("company_name") or "").strip()
            label = f"{ticker} ({name})" if name else str(ticker)
            print(f"- [{label}] {n.get('headline')} (type={n.get('event_type')})")

        if len(day_news) > 30:
            print(f"... ({len(day_news)-30} more)")
        print("=== END NEWS ===\n")

    # Price lookup for the day
    px_by_ticker: Dict[str, Dict] = {r["ticker"]: r for _, r in day_px.iterrows()}
    close_prices: Dict[str, float] = {t: float(px_by_ticker[t]["close"]) for t in px_by_ticker}

    orders_all = load_orders_csv(args.orders)
    orders = [o for o in orders_all if o.date == args.date]

    if not orders:
        print(f"No orders for {args.date}. (Looked in {args.orders})")

    teams = sorted(set(o.team for o in orders)) if orders else []

    trade_log_rows = []

    for team in teams:
        p = load_portfolio(args.state_dir, team, args.initial_cash)

        team_orders = [o for o in orders if o.team == team]
        for o in team_orders:
            if o.ticker not in px_by_ticker:
                trade_log_rows.append({
                    "date": args.date, "team": team, "ticker": o.ticker, "side": o.side, "qty": o.qty,
                    "status": "REJECT_NO_PRICE"
                })
                continue

            px_row = px_by_ticker[o.ticker]
            raw_px = get_execution_price(px_row, exec_cfg.execution_price)
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
                trade_log_rows.append({
                    "date": args.date, "team": team, "ticker": o.ticker, "side": o.side, "qty": o.qty,
                    "status": f"REJECT_{reason}"
                })
                continue

            try:
                if o.side == "BUY":
                    p.buy(o.ticker, o.qty, exec_px, fee=exec_cfg.fee_per_trade)
                elif o.side == "SELL":
                    p.sell(o.ticker, o.qty, exec_px, fee=exec_cfg.fee_per_trade)
                else:
                    raise ValueError("side must be BUY or SELL")

                trade_log_rows.append({
                    "date": args.date, "team": team, "ticker": o.ticker, "side": o.side, "qty": o.qty,
                    "price": round(exec_px, 4), "fee": exec_cfg.fee_per_trade,
                    "status": "FILLED"
                })
            except Exception as e:
                trade_log_rows.append({
                    "date": args.date, "team": team, "ticker": o.ticker, "side": o.side, "qty": o.qty,
                    "status": f"REJECT_{type(e).__name__}"
                })

        save_portfolio(args.state_dir, p)

    # Leaderboard from saved portfolios
    leaderboard_rows = []
    for fn in os.listdir(args.state_dir) if os.path.isdir(args.state_dir) else []:
        if not (fn.startswith("portfolio_") and fn.endswith(".json")):
            continue
        team = fn[len("portfolio_"):-len(".json")]
        p = load_portfolio(args.state_dir, team, args.initial_cash)
        nav = p.nav(close_prices)
        leaderboard_rows.append({
            "date": args.date,
            "team": team,
            "nav": round(nav, 2),
            "cash": round(p.cash, 2),
            "realized_pnl": round(p.realized_pnl, 2),
        })

    # Load portfolios (again) for reporting
    portfolios = []
    for fn in os.listdir(args.state_dir) if os.path.isdir(args.state_dir) else []:
        if fn.startswith("portfolio_") and fn.endswith(".json"):
            team = fn[len("portfolio_"):-len(".json")]
            portfolios.append(load_portfolio(args.state_dir, team, args.initial_cash))

    pos_df = build_positions_report(portfolios, close_prices, args.date)
    pnl_df = build_pnl_report(portfolios, close_prices, args.date, args.initial_cash)

    pos_path = os.path.join(args.reports_dir, f"positions_{args.date}.csv")
    pnl_path = os.path.join(args.reports_dir, f"pnl_{args.date}.csv")
    pos_df.to_csv(pos_path, index=False)
    pnl_df.to_csv(pnl_path, index=False)
    print(f"Positions report: {pos_path}")
    print(f"PnL report:       {pnl_path}")

    lb = pd.DataFrame(leaderboard_rows).sort_values("nav", ascending=False)

    lb_path = os.path.join(args.out_dir, "leaderboard.csv")
    lb.to_csv(lb_path, index=False)

    if trade_log_rows:
        trade_log = pd.DataFrame(trade_log_rows)
        trade_path = os.path.join(args.out_dir, f"trades_{args.date}.csv")
        trade_log.to_csv(trade_path, index=False)
        print(f"Trades saved: {trade_path}")

    print(f"Leaderboard saved: {lb_path}")
    if not lb.empty:
        print(lb.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
