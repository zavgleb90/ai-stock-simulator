# simulator/security_master.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import pandas as pd


@dataclass(frozen=True)
class Security:
    symbol: str
    company_name: str
    sector: str
    industry: str
    country: str
    full_time_employees: Optional[int] = None
    description: Optional[str] = None


class SecurityMaster:
    """
    Loads a 'security master' CSV (like your FMP ticker info export) and provides
    metadata lookup by ticker symbol.

    Expected columns:
      symbol, companyName, industry, sector, description, fullTimeEmployees, country
    """

    def __init__(self, csv_path: str | Path):
        self.csv_path = Path(csv_path)
        if not self.csv_path.exists():
            raise FileNotFoundError(f"Security master CSV not found: {self.csv_path}")

        df = pd.read_csv(self.csv_path)

        required = {"symbol", "companyName", "industry", "sector", "country"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Security master missing required columns: {sorted(missing)}")

        # Normalize symbols
        df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()

        self._by_symbol: Dict[str, Security] = {}

        for _, row in df.iterrows():
            sym = str(row["symbol"]).upper().strip()
            if not sym:
                continue

            fte = None
            if "fullTimeEmployees" in df.columns:
                try:
                    v = row.get("fullTimeEmployees")
                    if pd.notna(v):
                        fte = int(v)
                except Exception:
                    fte = None

            desc = None
            if "description" in df.columns:
                v = row.get("description")
                if pd.notna(v):
                    desc = str(v)

            sec = Security(
                symbol=sym,
                company_name=str(row.get("companyName", "")) if pd.notna(row.get("companyName")) else "",
                sector=str(row.get("sector", "")) if pd.notna(row.get("sector")) else "Unknown",
                industry=str(row.get("industry", "")) if pd.notna(row.get("industry")) else "Unknown",
                country=str(row.get("country", "")) if pd.notna(row.get("country")) else "Unknown",
                full_time_employees=fte,
                description=desc,
            )
            self._by_symbol[sym] = sec

    def get(self, symbol: str) -> Optional[Security]:
        return self._by_symbol.get(symbol.upper().strip())

    def sector_of(self, symbol: str, default: str = "Unknown") -> str:
        sec = self.get(symbol)
        return sec.sector if sec and sec.sector else default

    def company_name_of(self, symbol: str, default: str = "") -> str:
        sec = self.get(symbol)
        return sec.company_name if sec and sec.company_name else default

    def as_dict(self) -> Dict[str, Security]:
        return dict(self._by_symbol)
