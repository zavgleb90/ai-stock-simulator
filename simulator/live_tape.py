# simulator/live_tape.py
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

import numpy as np
import pandas as pd

from .universe import TICKERS_87
from .security_master import SecurityMaster
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

# 7 class-friendly hourly ticks per business day
BAR_HOURS = [10, 11, 12, 13, 14, 15, 16]
BARS_PER_DAY = len(BAR_HOURS)

def _ensure_parent(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)

def _weighted_choice(rng: np.random.Generator, items: List[str], weights: List[float]) -> str:
    w = np.array(weights, dtype=float)
    w = w / w.sum()
    return items[int(rng.choice(len(items), p=w))]

def _next_regime(rng: np.random.Generator, current: str) -> str:
    probs = REGIME_TRANSITIONS[current]
    return _weighted_choice(rng, list(probs.keys()), list(probs.values()))

def _advance_to_next_business_day(date_str: str) -> str:
    d = pd.Timestamp(date_str)
    next_bd = pd.bdate_range(d + pd.Timedelta(days=1), periods=1)[0]
    return str(next_bd.date())

def _bar_timestamp(date_str: str, bar_index: int) -> str:
    hour = BAR_HOURS[bar_index]
    return f"{date_str} {hour:02d}:00:00"

def _normalize_sector_name(raw: str) -> str:
    s = (raw or "").strip().lower()
    mapping = {
        "technology": "Tech",
        "information technology": "Tech",
        "financial services": "Financials",
        "financial": "Financials",
        "consumer cyclical": "Consumer",
        "consumer defensive": "Consumer",
        "consumer discretionary": "Consumer",
        "consumer staples": "Consumer",
        "industrials": "Industrials",
        "energy": "Energy",
        "healthcare": "Healthcare",
        "communication services": "Comm",
        "real estate": "Industrials",
        "basic materials": "Industrials",
        "materials": "Industrials",
        "utilities": "Industrials",
    }
    return mapping.get(s, "Speculative")

def _load_security_master(path: str) -> Optional[SecurityMaster]:
    try:
        return SecurityMaster(path)
    except FileNotFoundError:
        return None

@dataclass(frozen=True)
class LiveTapeConfig:
    seed: int = 7
    universe: Optional[List[str]] = None

    security_master_csv: str = "data/reference/ticker_info.csv"

    prices_out: str = "data/market/prices_hourly.csv"
    news_out: str = "data/market/news_hourly.jsonl"
    state_path: str = "data/state/market_state.json"

    market_beta_mean: float = 1.00
    market_beta_sd: float = 0.20
    sector_beta_mean: float = 0.60
    sector_beta_sd: float = 0.25

    idio_sigma_min: float = 0.006
    idio_sigma_max: float = 0.028

    start_price_log_mu: float = 4.7
    start_price_log_sigma: float = 0.55

    base_volume_min: int = 2_000_000
    base_volume_max: int = 30_000_000

    # per-day news probability, converted to per-bar
    news_prob_per_day: float = 0.012
    news_prob_crisis_mult: float = 2.2
    news_prob_spec_mult: float = 1.8

    macro_news_prob: float = 0.18
    intrabar_range_mult: float = 1.10

def save_state(cfg: LiveTapeConfig, state: Dict) -> None:
    _ensure_parent(cfg.state_path)
    with open(cfg.state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def load_or_create_state(cfg: LiveTapeConfig, start_date: Optional[str] = None, start_regime: str = "sideways") -> Dict:
    _ensure_parent(cfg.state_path)

    if os.path.exists(cfg.state_path):
        with open(cfg.state_path, "r", encoding="utf-8") as f:
            return json.load(f)

    rng = np.random.default_rng(cfg.seed)
    universe = cfg.universe or list(TICKERS_87)

    sm = _load_security_master(cfg.security_master_csv)
    sector_name_by_ticker = {}
    company_name_by_ticker = {}
    for t in universe:
        if sm:
            sector_name_by_ticker[t] = _normalize_sector_name(sm.sector_of(t, default="Speculative"))
            company_name_by_ticker[t] = sm.company_name_of(t, default="")
        else:
            sector_name_by_ticker[t] = "Speculative"
            company_name_by_ticker[t] = ""

    market_beta = {t: float(np.clip(rng.normal(cfg.market_beta_mean, cfg.market_beta_sd), 0.2, 2.2)) for t in universe}
    sector_beta = {t: float(np.clip(rng.normal(cfg.sector_beta_mean, cfg.sector_beta_sd), 0.0, 1.5)) for t in universe}
    idio_sigma  = {t: float(rng.uniform(cfg.idio_sigma_min, cfg.idio_sigma_max)) for t in universe}
    base_vol    = {t: int(rng.integers(cfg.base_volume_min, cfg.base_volume_max + 1)) for t in universe}

    start_prices = np.exp(rng.normal(cfg.start_price_log_mu, cfg.start_price_log_sigma, size=len(universe)))
    last_close = {t: float(max(2.0, p)) for t, p in zip(universe, start_prices)}

    if start_date is None:
        start_date = str(pd.bdate_range(pd.Timestamp.today().normalize(), periods=1)[0].date())

    state = {
        "universe": universe,
        "rng_state": rng.bit_generator.state,
        "sector_name_by_ticker": sector_name_by_ticker,
        "company_name_by_ticker": company_name_by_ticker,
        "market_beta": market_beta,
        "sector_beta": sector_beta,
        "idio_sigma": idio_sigma,
        "base_vol": base_vol,
        "last_close": last_close,
        "current_regime": start_regime,
        "current_date": start_date,
        "current_bar_index": 0,
        "current_macro_headline": None,
    }
    save_state(cfg, state)
    return state

def _maybe_new_day_context(cfg: LiveTapeConfig, rng: np.random.Generator, state: Dict) -> None:
    if int(state["current_bar_index"]) != 0:
        return

    state["current_regime"] = _next_regime(rng, state["current_regime"])

    if rng.random() < cfg.macro_news_prob:
        state["current_macro_headline"] = _weighted_choice(
            rng,
            ["Inflation cools", "Inflation spikes", "Jobs surprise", "Rates repriced", "Geopolitical tension", "Soft landing talk"],
            [0.16, 0.14, 0.18, 0.20, 0.16, 0.16],
        )
    else:
        state["current_macro_headline"] = None

def step_one_bar(cfg: LiveTapeConfig, state: Dict) -> Tuple[str, pd.DataFrame, List[Dict]]:
    rng = np.random.default_rng()
    rng.bit_generator.state = state["rng_state"]

    universe: List[str] = state["universe"]
    date_str: str = state["current_date"]
    bar_i: int = int(state["current_bar_index"])

    _maybe_new_day_context(cfg, rng, state)
    regime: str = state["current_regime"]
    macro_headline = state["current_macro_headline"]

    # daily -> hourly scaling
    mu_d = REGIMES[regime]["mu"]
    sig_d = REGIMES[regime]["sigma"]
    mu_h = mu_d / BARS_PER_DAY
    sig_h = sig_d / np.sqrt(BARS_PER_DAY)

    r_mkt = float(rng.normal(mu_h, sig_h))
    sector_r = {i: float(rng.normal(0.0, 0.65 * sig_h)) for i in range(len(SECTORS))}

    p_news_base = 1.0 - (1.0 - cfg.news_prob_per_day) ** (1.0 / BARS_PER_DAY)

    ts = _bar_timestamp(date_str, bar_i)
    rows: List[Dict] = []
    news_rows: List[Dict] = []

    for t in universe:
        sector_name = state["sector_name_by_ticker"].get(t, "Speculative")
        if sector_name not in SECTORS:
            sector_name = "Speculative"
        sec_idx = SECTORS.index(sector_name)
        company = (state.get("company_name_by_ticker", {}) or {}).get(t, "")

        id_sig = float(state["idio_sigma"][t])
        beta_m = float(state["market_beta"][t])
        beta_s = float(state["sector_beta"][t])

        p_news = p_news_base
        if regime == "crisis":
            p_news *= cfg.news_prob_crisis_mult
        if sector_name == "Speculative":
            p_news *= cfg.news_prob_spec_mult

        shock_ret = 0.0
        vol_mult = 1.0

        if rng.random() < p_news:
            event_types = list(NEWS_EVENT_TYPES.keys())
            weights = np.ones(len(event_types), dtype=float)

            if sector_name == "Speculative":
                for i, et in enumerate(event_types):
                    if "meme" in et:
                        weights[i] *= 2.2
            if sector_name == "Energy":
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
            shock_ret = float(rng.uniform(lo, hi)) / 2.0  # smaller per hour
            vol_mult = float(spec["vol_mult"])  # type: ignore

            news_rows.append({
                "timestamp": ts,
                "date": date_str,
                "ticker": t,
                "company_name": company,
                "event_type": etype,
                "sentiment": spec["sentiment"],
                "headline": random_headline(rng, etype, t),
                "shock_return": shock_ret,
                "macro_context": macro_headline,
                "regime": regime,
            })

        r_sector = sector_r[sec_idx]
        r_idio = float(rng.normal(0.0, (id_sig * vol_mult) / np.sqrt(BARS_PER_DAY)))
        r_total = (beta_m * r_mkt) + (beta_s * r_sector) + r_idio + shock_ret
        r_total = float(np.clip(r_total, -0.20, 0.20))

        prev_close = float(state["last_close"][t])
        open_px = prev_close
        close_px = open_px * (1.0 + r_total)

        intr_sig = (abs(r_total) + id_sig / np.sqrt(BARS_PER_DAY)) * cfg.intrabar_range_mult
        hi_spread = abs(float(rng.normal(0.0, intr_sig)))
        lo_spread = abs(float(rng.normal(0.0, intr_sig)))
        high_px = max(open_px, close_px) * (1.0 + hi_spread)
        low_px = min(open_px, close_px) * (1.0 - lo_spread)

        base_v = int(state["base_vol"][t])
        vol_bump = 1.0 + 8.0 * min(0.06, abs(r_total))
        if shock_ret != 0.0:
            vol_bump *= 1.3
        volume = int(max(1000, base_v * vol_bump * float(rng.uniform(0.85, 1.15)) / BARS_PER_DAY))

        state["last_close"][t] = float(max(0.5, close_px))

        rows.append({
            "timestamp": ts,
            "date": date_str,
            "bar_index": bar_i,
            "ticker": t,
            "sector": sector_name,
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

    # advance cursor
    bar_i += 1
    if bar_i >= BARS_PER_DAY:
        bar_i = 0
        state["current_date"] = _advance_to_next_business_day(date_str)
    state["current_bar_index"] = bar_i

    state["rng_state"] = rng.bit_generator.state
    return ts, pd.DataFrame(rows), news_rows

def append_outputs(cfg: LiveTapeConfig, bar_df: pd.DataFrame, news_rows: List[Dict]) -> None:
    _ensure_parent(cfg.prices_out)
    _ensure_parent(cfg.news_out)

    write_header = not os.path.exists(cfg.prices_out)
    bar_df.to_csv(cfg.prices_out, mode="a", index=False, header=write_header)

    with open(cfg.news_out, "a", encoding="utf-8") as f:
        for item in news_rows:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
