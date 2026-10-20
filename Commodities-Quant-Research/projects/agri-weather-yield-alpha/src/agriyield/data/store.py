"""Point-in-time (PIT) data store.

Every record carries a `knowledge_time`: when it became public. A query made
"as of" time T returns only records with knowledge_time <= T, and for tables
with revisions (vintages) the latest vintage known at T.

This single rule is what makes a backtest honest. Typical traps it prevents:

* using final NASS county yields (published the following February) to train
  a model that is evaluated in August of the same year;
* using reanalysis weather (ERA5, ~3 months latency) where only preliminary
  observations (ERA5T / gridMET) existed;
* using a USDA report before its noon release on report day;
* using revised acreage instead of the June estimate.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


class LookAheadError(RuntimeError):
    """Raised when code asks for data that was not public yet."""


@dataclass
class PITStore:
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    keys: dict[str, list[str]] = field(default_factory=dict)

    def register(self, name: str, df: pd.DataFrame, key: list[str] | None = None) -> None:
        """Add a table. `key` identifies a record across vintages (optional)."""
        if "knowledge_time" not in df.columns:
            raise ValueError(f"table {name!r} has no knowledge_time column")
        df = df.copy()
        df["knowledge_time"] = pd.to_datetime(df["knowledge_time"])
        self.tables[name] = df.sort_values("knowledge_time").reset_index(drop=True)
        self.keys[name] = key or []

    def get(self, name: str, as_of, **filters) -> pd.DataFrame:
        """Records of `name` public at `as_of`, latest vintage per key."""
        as_of = pd.Timestamp(as_of)
        df = self.tables[name]
        df = df[df["knowledge_time"] <= as_of]
        for col, val in filters.items():
            df = df[df[col].isin(val)] if isinstance(val, (list, tuple, set)) else df[df[col] == val]
        if self.keys[name]:
            df = df.drop_duplicates(self.keys[name], keep="last")
        return df.reset_index(drop=True)

    def require(self, name: str, as_of, **filters) -> pd.DataFrame:
        """Like get() but raises if nothing is available (catches PIT bugs early)."""
        out = self.get(name, as_of, **filters)
        if out.empty:
            raise LookAheadError(f"{name} {filters} not available as of {pd.Timestamp(as_of)}")
        return out
