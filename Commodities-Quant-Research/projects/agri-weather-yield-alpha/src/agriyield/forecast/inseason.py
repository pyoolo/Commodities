"""In-season national yield distribution from weather scenarios."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import agronomy
from ..data.sources import WeatherSource
from ..data.store import PITStore
from ..features.build import county_static, scenario_frame, season_inputs
from ..models.condition import ConditionModel
from ..synthetic.weather import WeatherArrays
from .scenarios import build_scenarios, choose_analogs


def evaluation_date(day: pd.Timestamp) -> pd.Timestamp:
    """Information set actually recomputed for a trading day.

    Daily from 1 June to 30 September (the weather market), weekly in October,
    then frozen. Mirrors the cadence a desk would run the full scenario engine.
    """
    day = pd.Timestamp(day)
    jun1, sep30 = pd.Timestamp(f"{day.year}-06-01"), pd.Timestamp(f"{day.year}-09-30")
    if day < jun1:
        return jun1
    if day <= sep30:
        return day
    nov1 = pd.Timestamp(f"{day.year}-11-01")
    if day < nov1:
        return sep30 + pd.Timedelta(days=7 * ((day - sep30).days // 7))
    return nov1


class InSeasonForecaster:
    """Run fitted county models over weather scenarios and aggregate nationally."""

    def __init__(self, cfg: dict, store: PITStore, wsrc: WeatherSource, models: dict,
                 cond_model: ConditionModel, year: int):
        self.cfg, self.store, self.wsrc, self.models, self.cond = cfg, store, wsrc, models, cond_model
        self.year = year
        self.static = county_static(store)
        season_start = pd.Timestamp(f"{year}-01-01") + pd.Timedelta(days=wsrc.doy0 - 1)
        known = sorted(store.get("county_yields", season_start)["year"].unique())
        # analog candidates: completed seasons with final reanalysis
        self.analog_years = [int(y) for y in known if y < year]
        self.archive = wsrc.archive(self.analog_years, season_start)
        self._pos = {y: i for i, y in enumerate(self.analog_years)}

    def _acres(self, as_of) -> np.ndarray:
        a = self.store.get("county_acres", as_of, year=self.year)
        if a.empty:  # before the June Acreage report: last year's footprint
            a = self.store.get("county_acres", as_of, year=self.year - 1)
        return a.sort_values("county_id")["planted_kac"].to_numpy()

    def forecast(self, as_of) -> dict[str, np.ndarray]:
        """National yield per ensemble member for each model, as of `as_of`."""
        as_of = pd.Timestamp(as_of)
        wsrc, M = self.wsrc, self.wsrc.members
        end = wsrc.obs_end(as_of)
        obs = wsrc.observed(self.year, as_of)
        if end < wsrc.n_days:
            fc = wsrc.forecast(self.year, as_of)
        else:
            z = np.zeros((M, len(self.static), 0))
            fc = WeatherArrays(z, z, z)
        # one analog year per member for the whole season (see world.py): day-to-day
        # changes must come from new information, not from redrawing climatology
        rng = np.random.default_rng([self.cfg["seed"], 3, self.year])
        an = choose_analogs(self.analog_years, M, rng)
        ai = [self._pos[a] for a in an]
        analog = WeatherArrays(self.archive.tmax[ai], self.archive.tmin[ai], self.archive.prcp[ai])
        scen = build_scenarios(obs, end, fc, analog)

        sm0, plant = season_inputs(self.store, self.year, as_of, wsrc.doy0, len(self.static))
        feats = agronomy.season_features(
            scen.tmin, scen.tmax, scen.prcp, lat=self.static["lat"].to_numpy(),
            awc=self.static["awc_mm"].to_numpy(), sm0=sm0, plant_idx=plant, doy0=wsrc.doy0,
        ).features
        frame = scenario_frame(feats, self.static, self.year)
        acres = self._acres(as_of)
        out = {}
        for name, model in self.models.items():
            logy = model.predict(frame).reshape(M, -1) + 0.5 * model.resid_var_
            out[name] = (np.exp(logy) * acres).sum(axis=1) / acres.sum()
        out["conditions"] = np.full(M, self.cond.predict(self.store, self.year, as_of))
        return out
