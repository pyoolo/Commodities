"""Synthetic daily weather (truth) and ensemble forecasts.

Real-world counterparts
-----------------------
* Observed daily weather  -> ERA5-Land (Copernicus CDS), gridMET or PRISM
                             (US, ~1 day latency); ERA5T for near-real time
* Ensemble forecasts      -> NOAA GEFS (31 members, 4x/day, AWS open data),
                             ECMWF ENS (51 members, 2x/day), AI ensembles
                             such as ECMWF AIFS-ENS
* Climatological tail     -> analog years drawn from the observed archive

Design
------
Temperature and moisture anomalies are driven by a few latent factors with
spatial loadings (see geography.py) and three time scales:
  * a whole-season persistent component  (drought / cool summers),
  * a slow sub-seasonal AR(1)            (multi-week heat domes),
  * a fast synoptic AR(1)                (fronts).
Moisture is negatively correlated with heat, so hot-dry summers cluster, which
is what makes crop-weather risk non-linear and regional.

Forecast errors grow with lead time and are spatially coherent and shared
across members (ensemble-mean error), so the ensemble can be confidently
wrong, exactly the situation in which forecast-driven trading gets hurt.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .geography import Geography


@dataclass
class WeatherArrays:
    tmax: np.ndarray   # (..., C, D) deg C
    tmin: np.ndarray
    prcp: np.ndarray   # mm/day

    def slice_days(self, start: int, end: int) -> "WeatherArrays":
        return WeatherArrays(self.tmax[..., start:end], self.tmin[..., start:end], self.prcp[..., start:end])


def _ar1(rng, n_series, n_days, phi, sd):
    """Stationary AR(1) paths, shape (n_series, n_days)."""
    out = np.empty((n_series, n_days))
    innov_sd = sd * np.sqrt(1 - phi**2)
    out[:, 0] = rng.normal(0, sd, n_series)
    eps = rng.normal(0, innov_sd, (n_series, n_days))
    for d in range(1, n_days):
        out[:, d] = phi * out[:, d - 1] + eps[:, d]
    return out


def tmax_climatology(lat: np.ndarray, doy: np.ndarray) -> np.ndarray:
    """Mean daily max temperature, (C, D)."""
    return 19.0 - 0.6 * (lat[:, None] - 37.0) + 12.0 * np.cos(2 * np.pi * (doy[None, :] - 200) / 365)


def rain_probability_climatology(doy: np.ndarray) -> np.ndarray:
    return 0.34 + 0.05 * np.sin(2 * np.pi * (doy - 80) / 365)


def generate_season(geo: Geography, doy: np.ndarray, rng: np.random.Generator) -> WeatherArrays:
    """One growing season of daily weather for every county, (C, D)."""
    W = geo.loadings
    K, D = W.shape[1], len(doy)

    # temperature factors
    persist_t = rng.normal(0, 0.9, K)[:, None]
    slow_t = _ar1(rng, K, D, 0.96, 1.0)
    fast_t = _ar1(rng, K, D, 0.70, 1.6)
    temp_anom = W @ (persist_t + slow_t + fast_t)

    # moisture factors, negatively correlated with heat
    persist_m = -0.5 * persist_t + np.sqrt(0.75) * rng.normal(0, 0.9, K)[:, None]
    slow_m = -0.5 * slow_t + np.sqrt(0.75) * _ar1(rng, K, D, 0.96, 1.0)
    moist = W @ (persist_m + slow_m) / 1.35

    p_clim = rain_probability_climatology(doy)[None, :]
    logit = np.log(p_clim / (1 - p_clim)) + 0.9 * moist - 0.12 * temp_anom
    rain = rng.random((geo.n_counties, D)) < 1 / (1 + np.exp(-logit))
    amount = rng.gamma(0.75, 11.0 * np.exp(0.3 * moist))
    prcp = np.where(rain, amount, 0.0)

    tmax = tmax_climatology(geo.lat, doy) + temp_anom - 1.8 * rain + rng.normal(0, 1.0, (geo.n_counties, D))
    dtr = np.clip(12.0 - 3.0 * rain + rng.normal(0, 1.5, (geo.n_counties, D)), 3, 20)
    tmin = tmax - dtr
    return WeatherArrays(tmax=tmax, tmin=tmin, prcp=prcp)


@dataclass
class ForecastErrorField:
    """Season-long forecast-error innovations, indexed by (lead, county, VALID day).

    The error of a forecast for valid day v issued with lead L is the SUM of the
    innovations for leads 1..L. Moving from lead L to L-1 (the next run) removes
    one independent innovation, so successive forecasts of the same day form a
    martingale: each new run is pure news, unpredictable from previous runs,
    and the error shrinks like sqrt(lead). That is the property real, calibrated
    ensembles approximately have, and it is what a fair efficient-market null
    requires (no predictable run-to-run reversal or drift).
    """
    temp_cum: np.ndarray    # (H, C, D) cumulative standardised innovations
    precip_cum: np.ndarray  # (H, C, D)
    flip_u: np.ndarray      # (C, D) uniforms for rain/no-rain timing errors
    spurious: np.ndarray    # (C, D) rain amounts when a dry day is forecast wet


def make_error_field(geo: Geography, n_days: int, horizon: int, rng: np.random.Generator) -> ForecastErrorField:
    W, K = geo.loadings, geo.loadings.shape[1]

    def innovations():
        inc = np.stack([W @ _ar1(rng, K, n_days, 0.7, 1.0) for _ in range(horizon)])   # (H, C, D)
        return np.cumsum(inc / inc.std(), axis=0)

    return ForecastErrorField(
        temp_cum=innovations(), precip_cum=innovations(),
        flip_u=rng.random((geo.n_counties, n_days)),
        spurious=rng.gamma(0.75, 8.0, (geo.n_counties, n_days)),
    )


def generate_forecast(
    truth: WeatherArrays,
    geo: Geography,
    issue_idx: int,
    horizon: int,
    members: int,
    rng: np.random.Generator,
    field: ForecastErrorField,
) -> WeatherArrays:
    """Ensemble forecast issued at `issue_idx`, covering [issue_idx, issue_idx+horizon).

    Returns (members, C, h) arrays (h may be shorter at the end of the season).
    Ensemble mean = truth + accumulated innovations (sd ~0.9 C * sqrt(lead) for
    temperature); members add zero-mean spread around it.
    """
    D = truth.tmax.shape[-1]
    end = min(issue_idx + horizon, D)
    h = end - issue_idx
    if h <= 0:
        z = np.zeros((members, geo.n_counties, 0))
        return WeatherArrays(z, z.copy(), z.copy())
    W = geo.loadings
    K = W.shape[1]
    lead = np.arange(1, h + 1)
    valid = np.arange(issue_idx, end)

    # Ensemble mean error: accumulated innovations (martingale across runs).
    sd_t, sd_p = 0.9 * np.sqrt(lead), 0.10 * np.sqrt(lead)
    mean_err_t = 0.9 * field.temp_cum[lead - 1, :, valid].T          # (C, h), sd = sd_t
    mean_err_p = 0.10 * field.precip_cum[lead - 1, :, valid].T

    def spread(scale):
        raw = np.einsum("ck,mkh->mch", W, rng.normal(0, 1, (members, K, h)))
        raw = (raw - raw.mean(axis=0, keepdims=True)) / raw.std(axis=(0, 1), keepdims=True).clip(1e-9)
        return raw * scale[None, None, :]

    # Calibrated ensemble: member spread equals the actual error sd, so the
    # members describe the real uncertainty about the truth. Under-dispersion
    # would bias expected heat damage (KDD is convex) at long leads and create
    # a predictable drift as lead time shrinks. Precipitation multipliers are
    # mean-corrected (E[exp(x - s^2/2)] = 1) for the same reason.
    t_err = mean_err_t[None] + spread(sd_t)
    log_p = mean_err_p[None] + spread(sd_p) - sd_p[None, None, :] ** 2   # two lognormal terms
    sl = slice(issue_idx, end)
    tmax = truth.tmax[None, :, sl] + t_err
    tmin = truth.tmin[None, :, sl] + 0.8 * t_err
    prcp = truth.prcp[None, :, sl] * np.exp(log_p)
    return WeatherArrays(tmax=tmax, tmin=tmin, prcp=prcp)
