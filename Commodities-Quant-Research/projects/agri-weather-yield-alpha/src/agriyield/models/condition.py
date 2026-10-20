"""Crop-condition benchmark (Irwin & Good / farmdoc style).

National yield regressed on a linear trend and the acreage-weighted share of
the crop rated Good/Excellent in the same week of the year. Every desk has
this model; it is the benchmark a new signal has to beat.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..data.store import PITStore


def national_yield_history(store: PITStore, as_of) -> pd.Series:
    y = store.get("county_yields", as_of)
    a = store.get("county_acres", as_of)
    m = y.merge(a[["year", "county_id", "planted_kac"]], on=["year", "county_id"])
    return m.groupby("year").apply(
        lambda g: np.average(g["yield_bu_ac"], weights=g["planted_kac"]), include_groups=False)


def national_ge(store: PITStore, as_of, year: int | None = None) -> pd.DataFrame:
    """Acre-weighted national Good/Excellent % by week (only weeks public at as_of)."""
    c = store.get("conditions", as_of) if year is None else store.get("conditions", as_of, year=year)
    if c.empty:
        return pd.DataFrame(columns=["year", "week", "ge"])
    a = store.get("county_acres", as_of)
    st = store.get("county_static", as_of)[["county_id", "state"]]
    w = a.merge(st, on="county_id").groupby(["year", "state"])["planted_kac"].sum().unstack()
    # state weights: that year's acreage if public, else the latest year that is
    w = w.reindex(range(int(w.index.min()), int(c["year"].max()) + 1)).ffill()
    c = c.copy()
    c["w"] = w.stack().reindex(pd.MultiIndex.from_arrays([c["year"], c["state"]])).to_numpy()
    c["week"] = c["week_date"].dt.isocalendar().week.astype(int)
    c["wge"] = c["w"] * c["good_excellent_pct"]
    g = c.groupby(["year", "week"])[["wge", "w"]].sum()
    return (g["wge"] / g["w"]).rename("ge").reset_index()


class ConditionModel:
    name = "conditions"

    def fit(self, store: PITStore, as_of) -> "ConditionModel":
        nat = national_yield_history(store, as_of)
        self.years_ = nat.index.to_numpy()
        self.log_nat_ = np.log(nat.to_numpy())
        self.trend_ = np.polyfit(self.years_, self.log_nat_, 1)
        ge = national_ge(store, as_of)
        self.coefs_ = {}
        for week, g in ge.groupby("week"):
            g = g[g["year"].isin(self.years_)]
            if len(g) < 6:
                continue
            idx = np.searchsorted(self.years_, g["year"].to_numpy())
            X = np.column_stack([np.ones(len(g)), g["year"] - 2000, g["ge"]])
            self.coefs_[week] = np.linalg.lstsq(X, self.log_nat_[idx], rcond=None)[0]
        return self

    def predict(self, store: PITStore, year: int, as_of) -> float:
        """National yield forecast (bu/ac) using the latest rating public at as_of."""
        ge = national_ge(store, as_of, year=year)
        if not ge.empty:
            last = ge.sort_values("week").iloc[-1]
            if int(last["week"]) in self.coefs_:
                b = self.coefs_[int(last["week"])]
                return float(np.exp(b[0] + b[1] * (year - 2000) + b[2] * last["ge"]))
        return float(np.exp(np.polyval(self.trend_, year)))
