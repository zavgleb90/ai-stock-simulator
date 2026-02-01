# news_generator/synthetic_news.py
from __future__ import annotations

from typing import Dict, List, Tuple
import numpy as np

NEWS_EVENT_TYPES: Dict[str, Dict[str, object]] = {
    "earnings_beat":   {"sentiment": "positive", "jump_range": (0.015, 0.060), "vol_mult": 1.4},
    "earnings_miss":   {"sentiment": "negative", "jump_range": (-0.060, -0.015), "vol_mult": 1.5},
    "upgrade":         {"sentiment": "positive", "jump_range": (0.008, 0.030), "vol_mult": 1.2},
    "downgrade":       {"sentiment": "negative", "jump_range": (-0.030, -0.008), "vol_mult": 1.25},
    "product_launch":  {"sentiment": "positive", "jump_range": (0.005, 0.025), "vol_mult": 1.15},
    "lawsuit":         {"sentiment": "negative", "jump_range": (-0.035, -0.010), "vol_mult": 1.35},
    "regulatory_risk": {"sentiment": "negative", "jump_range": (-0.040, -0.010), "vol_mult": 1.40},
    "macro_tailwind":  {"sentiment": "positive", "jump_range": (0.003, 0.012), "vol_mult": 1.10},
    "macro_headwind":  {"sentiment": "negative", "jump_range": (-0.012, -0.003), "vol_mult": 1.10},
    "meme_spike":      {"sentiment": "positive", "jump_range": (0.020, 0.120), "vol_mult": 1.8},
    "meme_crash":      {"sentiment": "negative", "jump_range": (-0.120, -0.020), "vol_mult": 2.0},
}

HEADLINE_TEMPLATES: Dict[str, List[str]] = {
    "earnings_beat": [
        "{ticker} surges after earnings beat and upbeat guidance",
        "{ticker} rallies as quarterly results top expectations",
    ],
    "earnings_miss": [
        "{ticker} slides after earnings miss; guidance disappoints",
        "{ticker} drops as margins compress and outlook weakens",
    ],
    "upgrade": [
        "Analyst upgrades {ticker}; shares climb on valuation call",
        "{ticker} rises after major broker issues upgrade",
    ],
    "downgrade": [
        "Analyst downgrades {ticker} citing slowing growth",
        "{ticker} falls after downgrade and target cut",
    ],
    "product_launch": [
        "{ticker} jumps on new product launch buzz",
        "{ticker} gains as investors react to product announcement",
    ],
    "lawsuit": [
        "{ticker} pressured after lawsuit headlines emerge",
        "{ticker} dips as legal risks move to the foreground",
    ],
    "regulatory_risk": [
        "{ticker} hit by regulatory concerns and policy uncertainty",
        "{ticker} weakens amid new regulatory scrutiny",
    ],
    "macro_tailwind": [
        "Macro data boosts risk appetite; {ticker} benefits",
        "Risk-on session lifts {ticker} alongside broader market",
    ],
    "macro_headwind": [
        "Macro worries weigh on stocks; {ticker} under pressure",
        "{ticker} slips as investors turn cautious on growth",
    ],
    "meme_spike": [
        "{ticker} spikes as social chatter surges",
        "{ticker} rockets amid retail-driven momentum",
    ],
    "meme_crash": [
        "{ticker} tumbles as meme momentum reverses",
        "{ticker} plunges as speculative interest evaporates",
    ],
}

def random_headline(rng: np.random.Generator, event_type: str, ticker: str) -> str:
    templates = HEADLINE_TEMPLATES.get(event_type, ["{ticker} moves on fresh headlines"])
    template = templates[int(rng.integers(0, len(templates)))]
    return template.format(ticker=ticker)
