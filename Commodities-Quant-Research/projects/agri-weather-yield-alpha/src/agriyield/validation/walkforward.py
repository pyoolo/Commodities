"""Walk-forward evaluation: retrain every year on data public at the time.

For each forecast year y:
  1. as_of = 31 May y. Training data = every season whose NASS county yields
     and final reanalysis are public by then (i.e. years < y).
  2. Fit trend / panel / GBM / blend + the crop-condition benchmark.
  3. Score end-of-season county predictions (weather fully observed, yields
     still unknown: as_of = 1 Dec y).
  4. Run the in-season scenario engine on every trading day 1 Jun - 31 Oct.

Nothing from year y (or later) can leak: the PIT store and the WeatherSource
both refuse to serve it.
"""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from .. import agronomy
from ..data.sources import WeatherSource
from ..data.store import PITStore
from ..features.build import county_static, scenario_frame, season_inputs, training_frame
from ..forecast.inseason import InSeasonForecaster, evaluation_date
from ..models.condition import ConditionModel
from ..models.yield_models import build_models, fit_models

MODELS = ["trend", "conditions", "panel", "gbm", "blend"]


def end_of_season_county(store, wsrc, models, year) -> pd.DataFrame:
    as_of = pd.Timestamp(f"{year}-12-01")
    static = county_static(store)
    obs = wsrc.observed(year, as_of)
    sm0, plant = season_inputs(store, year, as_of, wsrc.doy0, len(static))
    f = agronomy.season_features(
        obs.tmin[None], obs.tmax[None], obs.prcp[None], lat=static["lat"].to_numpy(),
        awc=static["awc_mm"].to_numpy(), sm0=sm0, plant_idx=plant, doy0=wsrc.doy0,
    ).features
    frame = scenario_frame(f, static, year)
    out = frame[["year", "county_id", "state"]].copy()
    for name in ("trend", "panel", "gbm", "blend"):
        out[name] = models[name].predict(frame)
    return out


def run_walkforward(cfg: dict, store: PITStore, wsrc: WeatherSource, verbose: bool = True) -> dict:
    log = print if verbose else (lambda *a, **k: None)
    bt = cfg["backtest"]
    years = range(bt["first_forecast_year"], cfg["world"]["last_year"] + 1)
    inseason, county_rows, coef_rows = [], [], []
    for year in years:
        t0 = time.time()
        as_of_train = pd.Timestamp(f"{year}-05-31")
        train = training_frame(store, wsrc, as_of_train)
        assert train["year"].max() < year, "look-ahead in training data"
        models = fit_models(build_models(cfg), train)
        cond = ConditionModel().fit(store, as_of_train)

        county_rows.append(end_of_season_county(store, wsrc, models, year))
        coef_rows.append(models["panel"].coefficients().rename(year))

        fcr = InSeasonForecaster(cfg, store, wsrc, models, cond, year)
        days = pd.bdate_range(f"{year}-06-01", f"{year}-10-31")
        cache: dict[pd.Timestamp, dict] = {}
        for d in days:
            key = evaluation_date(d)
            if key not in cache:
                cache[key] = fcr.forecast(key)
            res = cache[key]
            for m in MODELS:
                v = res[m]
                inseason.append((year, d, m, v.mean(), *np.percentile(v, [10, 50, 90])))
        log(f"[walk-forward] {year}: trained on {train['year'].min()}-{train['year'].max()} "
            f"({len(train):,} county-years), {len(cache)} scenario runs, {time.time() - t0:.0f}s")

    ins = pd.DataFrame(inseason, columns=["year", "date", "model", "mean", "p10", "p50", "p90"])
    return {
        "inseason": ins,
        "county_eos": pd.concat(county_rows, ignore_index=True),
        "panel_coefs": pd.DataFrame(coef_rows),
    }
