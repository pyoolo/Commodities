"""Turn "what we know today" into full-season weather scenarios.

    days [0, obs_end)                 -> observed weather (same for all members)
    days [obs_end, obs_end + h)       -> ensemble forecast member m
    days [obs_end + h, end of season) -> weather of analog year a(m)

Running a yield model on every scenario gives a *distribution* of end-of-season
yield, updated every time a new forecast run lands. This is the core object the
trading signals are built on.
"""
from __future__ import annotations

import numpy as np

from ..synthetic.weather import WeatherArrays


def choose_analogs(candidate_years: list[int], n_members: int, rng: np.random.Generator) -> np.ndarray:
    """Analog year for each member (without replacement while possible)."""
    cand = np.asarray(candidate_years)
    if len(cand) == 0:
        raise ValueError("need at least one analog year")
    if len(cand) >= n_members:
        return rng.choice(cand, n_members, replace=False)
    return rng.choice(cand, n_members, replace=True)


def build_scenarios(
    observed: WeatherArrays,
    obs_end: int,
    forecast: WeatherArrays,
    analog_weather: WeatherArrays,
) -> WeatherArrays:
    """Assemble (M, C, D) scenario arrays.

    observed:       (C, D); values at or after `obs_end` are ignored (may be NaN)
    forecast:       (M, C, h) starting at obs_end
    analog_weather: (M, C, D) analog-year weather, one per member
    """
    M, _, D = analog_weather.tmax.shape
    obs_end = int(np.clip(obs_end, 0, D))
    out = {}
    for var in ("tmax", "tmin", "prcp"):
        # float32 halves memory and roughly doubles the speed of the agronomy
        # code; precision is irrelevant at this scale.
        arr = getattr(analog_weather, var).astype(np.float32)
        arr[:, :, :obs_end] = getattr(observed, var)[None, :, :obs_end]
        fc = getattr(forecast, var)
        h = min(fc.shape[-1], D - obs_end)
        if h > 0:
            arr[:, :, obs_end:obs_end + h] = fc[:, :, :h]
        out[var] = arr
    if np.isnan(out["tmax"]).any():
        raise ValueError("scenario contains NaN: observed data requested beyond what is available")
    return WeatherArrays(**out)
