# simulator/cli_generate_tape.py
from __future__ import annotations

import argparse
from pathlib import Path
import yaml

from .market_tape import TapeConfig, generate_market_tape, save_market_tape
from .universe import TICKERS_87

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate synthetic daily prices + news for the AI sim market.")
    p.add_argument("--config", type=str, default="simulator/configs/full_87.yaml", help="YAML config path")
    return p.parse_args()

def main() -> None:
    args = parse_args()
    with open(args.config, "r", encoding="utf-8") as f:
        cfg_y = yaml.safe_load(f) or {}

    # Merge YAML into TapeConfig with sensible defaults
    tape_cfg = TapeConfig(
        start_date=cfg_y.get("start_date", "2025-01-01"),
        end_date=cfg_y.get("end_date", "2025-12-31"),
        seed=int(cfg_y.get("seed", 7)),
        initial_regime=cfg_y.get("initial_regime", "sideways"),
        universe=cfg_y.get("universe", list(TICKERS_87)),
    )

    out_dir = cfg_y.get("output_dir", "data/market")
    df, news = generate_market_tape(tape_cfg)
    prices_path, news_path = save_market_tape(df, news, out_dir)

    print("✅ Market tape generated")
    print(f"Prices: {prices_path} (rows={len(df)})")
    print(f"News:   {news_path} (items={len(news)})")

if __name__ == "__main__":
    main()
