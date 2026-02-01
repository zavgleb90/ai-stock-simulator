# simulator/market_tape.py
from __future__ import annotations
from .security_master import SecurityMaster

import json
import os
from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from .universe import TICKERS_87
from news_generator.synthetic_news import NEWS_EVENT_TYPES, random_headline

SECTORS = ["Tech", "Financials", "Consumer", "Industrials", "Energy", "Healthcare", "Comm", "Speculative"]

REGIMES = {
    "bull":     {"mu": 0.0006, "sigma": 0.010},
    "sideways": {"mu": 0.0001, "sigma": 0.008},
    "bear":     {"mu": -0.0006, "sigma": 0.012},
    "crisis":   {"mu": -0.0012, "sigma": 0.025},
}

REGIME_TRANSITIONS = {
    "bull":     {"bull": 0.92, "sideways": 0.06, "bear": 0.015, "crisis": 0.005},
    "sideways": {"bull": 0.10, "sideways": 0.82, "bear": 0.06, "crisis": 0.02},
    "bear":     {"bull": 0.06, "sideways": 0.18, "bear": 0.70, "crisis": 0.06},
    "crisis":   {"bull": 0.05, "sideways": 0.15, "bear": 0.35, "crisis": 0.45},
}

def _stable_sector(sym: str) -> int:
    return sum(ord(c) for c in sym) % len(SECTORS)

def _normalize_sector_name(raw: str) -> str:
    """
    Map real sector labels into the simulator's sector buckets.
    You can expand/refine this as you like.
    """
    s = (raw or "").strip().lower()

    mapping = {
        "technology": "Tech",
        "financial services": "Financials",
        "financial": "Financials",
        "consumer cyclical": "Consumer",
        "consumer defensive": "Consumer",
        "industrials": "Industrials",
        "energy": "Energy",
        "healthcare": "Healthcare",
        "communication services": "Comm",
        "real estate": "Industrials",
        "basic materials": "Industrials",
        "utilities": "Industrials",
    }
    return mapping.get(s, "Speculative")  # default bucket

def _weighted_choice(rng: np.random.Generator, items: List[str], weights: List[float]) -> str:
    w = np.array(weights, dtype=float)
    w = w / w.sum()
    return items[int(rng.choice(len(items), p=w))]

def _next_regime(rng: np.random.Generator, current: str) -> str:
    probs = REGIME_TRANSITIONS[current]
    return _weighted_choice(rng, list(probs.keys()), list(probs.values()))

@dataclass(frozen=True)
class TapeConfig:
    start_date: str = "2025-01-01"
    end_date: str = "2025-12-31"
    seed: int = 7
    initial_regime: str = "sideways"
    universe: List[str] = None  # filled in __post_init__ style below

    # Factor structure
    market_beta_mean: float = 1.00
    market_beta_sd: float = 0.20
    sector_beta_mean: float = 0.60
    sector_beta_sd: float = 0.25

    # Idiosyncratic vol per ticker (daily)
    idio_sigma_min: float = 0.006
    idio_sigma_max: float = 0.028

    # Starting price distribution
    start_price_log_mu: float = 4.7
    start_price_log_sigma: float = 0.55

    # News frequency
    news_prob_base: float = 0.012
    news_prob_crisis_mult: float = 2.2
    news_prob_spec_mult: float = 1.8

    # Macro headlines
    macro_news_prob: float = 0.18

    # OHLC construction
    overnight_sigma_mult: float = 0.35
    intraday_range_mult: float = 1.10

    # Volume model
    base_volume_min: int = 2_000_000
    base_volume_max: int = 30_000_000

def _company_name(sm: SecurityMaster | None, ticker: str) -> str:
    if sm is None:
        return ""
    return sm.company_name_of(ticker, default="")

def generate_market_tape(cfg: TapeConfig) -> Tuple[pd.DataFrame, List[Dict]]:
    rng = np.random.default_rng(cfg.seed)
    universe = cfg.universe or list(TICKERS_87)
    sm = None
    csv_path = "data/reference/ticker_info.csv"
    try:
        sm = SecurityMaster(csv_path)
    except FileNotFoundError:
        sm = None  # fallback if user didn't copy file yet

    sector_name_by_ticker = {}
    for t in universe:
        if sm:
            raw_sector = sm.sector_of(t, default="Speculative")
            sector_name_by_ticker[t] = _normalize_sector_name(raw_sector)
        else:
            # fallback to old hashing if CSV isn't present
            sector_name_by_ticker[t] = SECTORS[_stable_sector(t)]

    # Per-ticker parameters
    market_beta = {t: float(np.clip(rng.normal(cfg.market_beta_mean, cfg.market_beta_sd), 0.2, 2.2)) for t in universe}
    sector_beta = {t: float(np.clip(rng.normal(cfg.sector_beta_mean, cfg.sector_beta_sd), 0.0, 1.5)) for t in universe}
    idio_sigma  = {t: float(rng.uniform(cfg.idio_sigma_min, cfg.idio_sigma_max)) for t in universe}
    base_vol    = {t: int(rng.integers(cfg.base_volume_min, cfg.base_volume_max + 1)) for t in universe}

    start_prices = np.exp(rng.normal(cfg.start_price_log_mu, cfg.start_price_log_sigma, size=len(universe)))
    prices = {t: float(max(2.0, p)) for t, p in zip(universe, start_prices)}

    dates = pd.bdate_range(cfg.start_date, cfg.end_date)
    regime = cfg.initial_regime

    rows: List[Dict] = []
    news: List[Dict] = []

    for d in dates:
        date_str = d.strftime("%Y-%m-%d")
        regime = _next_regime(rng, regime)
        mu_mkt = REGIMES[regime]["mu"]
        sig_mkt = REGIMES[regime]["sigma"]

        r_mkt = float(rng.normal(mu_mkt, sig_mkt))
        sector_r = {s: float(rng.normal(0.0, 0.65 * sig_mkt)) for s in range(len(SECTORS))}

        macro_headline = None
        if rng.random() < cfg.macro_news_prob:
            macro_headline = _weighted_choice(
                rng,
                ["Inflation cools", "Inflation spikes", "Jobs surprise", "Rates repriced", "Geopolitical tension", "Soft landing talk"],
                [0.16, 0.14, 0.18, 0.20, 0.16, 0.16],
            )

        for t in universe:
            sector_name = sector_name_by_ticker.get(t, "Speculative")
            sec = SECTORS.index(sector_name) if sector_name in SECTORS else SECTORS.index("Speculative")
            id_sig = idio_sigma[t]

            # News probability adjustments
            p_news = cfg.news_prob_base
            if regime == "crisis":
                p_news *= cfg.news_prob_crisis_mult
            if SECTORS[sec] == "Speculative":
                p_news *= cfg.news_prob_spec_mult

            shock_ret = 0.0
            vol_mult = 1.0

            # Optional ticker-level event
            if rng.random() < p_news:
                event_types = list(NEWS_EVENT_TYPES.keys())
                weights = np.ones(len(event_types), dtype=float)

                if SECTORS[sec] == "Speculative":
                    for i, et in enumerate(event_types):
                        if "meme" in et:
                            weights[i] *= 2.2
                if SECTORS[sec] == "Energy":
                    for i, et in enumerate(event_types):
                        if "macro_" in et:
                            weights[i] *= 1.6
                if regime == "crisis":
                    for i, et in enumerate(event_types):
                        if et in {"macro_headwind", "regulatory_risk", "lawsuit", "earnings_miss"}:
                            weights[i] *= 1.5

                etype = _weighted_choice(rng, event_types, weights.tolist())
                spec = NEWS_EVENT_TYPES[etype]
                lo, hi = spec["jump_range"]  # type: ignore
                shock_ret = float(rng.uniform(lo, hi))
                vol_mult = float(spec["vol_mult"])  # type: ignore

                news.append({
                    "date": date_str,
                    "ticker": t,
                    "company_name": _company_name(sm, t),
                    "event_type": etype,
                    "sentiment": spec["sentiment"],
                    "headline": random_headline(rng, etype, t),
                    "shock_return": shock_ret,
                    "macro_context": macro_headline,
                    "regime": regime,
                })

            r_sector = sector_r[sec]
            r_idio = float(rng.normal(0.0, id_sig * vol_mult))
            r_total = (market_beta[t] * r_mkt) + (sector_beta[t] * r_sector) + r_idio + shock_ret
            r_total = float(np.clip(r_total, -0.35, 0.35))

            prev_close = prices[t]

            overnight = float(rng.normal(0.0, id_sig * cfg.overnight_sigma_mult))
            open_px = prev_close * (1.0 + overnight)
            close_px = open_px * (1.0 + r_total)

            intraday_sig = (abs(r_total) + id_sig) * cfg.intraday_range_mult
            hi_spread = abs(float(rng.normal(0.0, intraday_sig)))
            lo_spread = abs(float(rng.normal(0.0, intraday_sig)))
            high_px = max(open_px, close_px) * (1.0 + hi_spread)
            low_px = min(open_px, close_px) * (1.0 - lo_spread)

            vol_bump = 1.0 + 8.0 * min(0.08, abs(r_total))
            if shock_ret != 0.0:
                vol_bump *= 1.4
            volume = int(max(1000, base_vol[t] * vol_bump * float(rng.uniform(0.75, 1.25))))

            prices[t] = float(max(0.5, close_px))

            rows.append({
                "date": date_str,
                "ticker": t,
                "company_name": _company_name(sm, t),
                "sector": SECTORS[sec],
                "regime": regime,
                "macro_headline": macro_headline,
                "open": round(float(open_px), 4),
                "high": round(float(high_px), 4),
                "low": round(float(low_px), 4),
                "close": round(float(close_px), 4),
                "volume": volume,
                "ret": round(float(r_total), 6),
                "market_ret": round(float(r_mkt), 6),
                "sector_ret": round(float(r_sector), 6),
                "shock_ret": round(float(shock_ret), 6),
                "has_news": int(shock_ret != 0.0),
            })

    df = pd.DataFrame(rows).sort_values(["date", "ticker"])
    return df, news

def save_market_tape(df: pd.DataFrame, news: List[Dict], out_dir: str) -> Tuple[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    prices_path = os.path.join(out_dir, "prices.csv")
    news_path = os.path.join(out_dir, "news.jsonl")

    df.to_csv(prices_path, index=False)

    with open(news_path, "w", encoding="utf-8") as f:
        for item in news:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    return prices_path, news_path
