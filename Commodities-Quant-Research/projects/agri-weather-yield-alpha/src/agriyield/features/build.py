"""Feature tables for training (county-year) and in-season scenarios.

Everything is read through the PIT store and the WeatherSource, with an
explicit `as_of`, so a feature table can never contain information that was
not public at that time.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import agronomy
from ..data.sources import WeatherSource
from ..data.store import PITStore

MODEL_FEATURES = agronomy.FEATURES + ["awc_mm", "lat"]


def county_static(store: PITStore) -> pd.DataFrame:
    return store.get("county_static", "2100-01-01").sort_values("county_id").reset_index(drop=True)


def _season_inputs(store: PITStore, year: int, as_of, doy0: int, n_counties: int):
    """Start-of-season soil water and planting index known at `as_of`."""
    sm = store.require("soil_moisture_start", as_of, year=year).sort_values("county_id")
    sm0 = sm["sm0_mm"].to_numpy()
    # counties not yet planted at as_of are assumed to plant on as_of
    plant = store.get("planting", as_of, year=year).set_index("county_id")["plant_doy"]
    as_of_doy = pd.Timestamp(as_of).dayofyear if pd.Timestamp(as_of).year == year else 366
    plant_doy = np.full(n_counties, min(as_of_doy, doy0 + 400), dtype=float)
    plant_doy[plant.index.to_numpy()] = plant.to_numpy()
    plant_idx = np.clip(plant_doy - doy0, 0, None).astype(int)
    return sm0, plant_idx


def training_frame(store: PITStore, wsrc: WeatherSource, as_of) -> pd.DataFrame:
    """County-year table of features + log yield for every season known at `as_of`."""
    as_of = pd.Timestamp(as_of)
    yields = store.get("county_yields", as_of)
    years = sorted(yields["year"].unique())
    if not years:
        raise ValueError(f"no county yields known as of {as_of.date()}")
    static = county_static(store)
    wx = wsrc.archive(years, as_of)
    sm0 = np.stack([_season_inputs(store, y, as_of, wsrc.doy0, len(static))[0] for y in years])
    plant = np.stack([_season_inputs(store, y, as_of, wsrc.doy0, len(static))[1] for y in years])
    f = agronomy.season_features(
        wx.tmin, wx.tmax, wx.prcp, lat=static["lat"].to_numpy(), awc=static["awc_mm"].to_numpy(),
        sm0=sm0, plant_idx=plant, doy0=wsrc.doy0,
    ).features
    n_c = len(static)
    df = pd.DataFrame({k: v.ravel() for k, v in f.items()})
    df["year"] = np.repeat(years, n_c)
    df["county_id"] = np.tile(static["county_id"].to_numpy(), len(years))
    df = df.merge(static[["county_id", "state", "lat", "awc_mm"]], on="county_id")
    df = df.merge(yields[["year", "county_id", "yield_bu_ac"]], on=["year", "county_id"])
    df["log_yield"] = np.log(df["yield_bu_ac"])
    return df


def scenario_frame(features: dict[str, np.ndarray], static: pd.DataFrame, year: int) -> pd.DataFrame:
    """Flatten (M, C) scenario features into a model-ready frame."""
    M, C = next(iter(features.values())).shape
    df = pd.DataFrame({k: np.asarray(v, float).ravel() for k, v in features.items()})
    df["member"] = np.repeat(np.arange(M), C)
    df["county_id"] = np.tile(static["county_id"].to_numpy(), M)
    df["state"] = np.tile(static["state"].to_numpy(), M)
    df["lat"] = np.tile(static["lat"].to_numpy(), M)
    df["awc_mm"] = np.tile(static["awc_mm"].to_numpy(), M)
    df["year"] = year
    return df


def season_inputs(store: PITStore, year: int, as_of, doy0: int, n_counties: int):
    return _season_inputs(store, year, as_of, doy0, n_counties)
