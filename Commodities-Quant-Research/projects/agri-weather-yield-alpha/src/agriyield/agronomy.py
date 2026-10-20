"""Agro-meteorological building blocks (fully vectorised).

Every function works on numpy arrays whose LAST axis is "day of season".
Leading axes are free: (counties, days), (years, counties, days) or
(ensemble members, counties, days) all work the same way. Static per-location
inputs (latitude, soil water capacity, planting day...) must broadcast to the
leading axes.

The same functions are used by the synthetic world (to generate "true" yields)
and by the models (to build features). That mirrors reality: the agronomy is
public knowledge, the *mapping* from these quantities to yield is what each
desk estimates differently. The models never see the true coefficients.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Soybean phenology expressed as cumulative growing degree days (base 10 C,
# cap 30 C) after planting. Values are in the range used by extension
# services for mid-maturity-group soybean in the US Corn Belt.
SOY_STAGES_GDD = {
    "VE": 70.0,     # emergence
    "R1": 480.0,    # beginning bloom
    "R3": 650.0,    # beginning pod
    "R5": 850.0,    # beginning seed fill
    "R6": 1100.0,   # full seed
    "R7": 1400.0,   # physiological maturity
}


# --------------------------------------------------------------------------
# Temperature
# --------------------------------------------------------------------------
def degree_days_above(tmin: np.ndarray, tmax: np.ndarray, threshold: float) -> np.ndarray:
    """Daily degree days above `threshold` using the single-sine method.

    Daily temperature is assumed to follow a sine curve between tmin and tmax
    (Baskerville & Emin 1969). This is the standard way to approximate the
    hourly exposure used by Schlenker & Roberts (2009) from daily data.
    """
    tmin, tmax = np.broadcast_arrays(np.asarray(tmin, float), np.asarray(tmax, float))
    tmax = np.maximum(tmax, tmin)
    mean = 0.5 * (tmax + tmin)
    amp = 0.5 * (tmax - tmin)
    out = np.zeros_like(mean)

    full = tmin >= threshold                 # whole day above threshold
    out[full] = mean[full] - threshold

    part = (tmax > threshold) & ~full        # threshold crossed during the day
    if np.any(part):
        a = np.maximum(amp[part], 1e-9)
        m = mean[part]
        theta = np.arcsin(np.clip((threshold - m) / a, -1.0, 1.0))
        out[part] = ((m - threshold) * (np.pi / 2 - theta) + a * np.cos(theta)) / np.pi
    return out


def _dd_dense(mean, amp, threshold):
    """Single-sine degree days without boolean indexing (faster on big arrays)."""
    a = np.maximum(amp, 1e-9)
    theta = np.arcsin(np.clip((threshold - mean) / a, -1.0, 1.0))
    # theta = -pi/2 when the whole day is above, +pi/2 when entirely below:
    # the general formula then reduces to mean - threshold and 0 respectively.
    return np.maximum(((mean - threshold) * (np.pi / 2 - theta) + a * np.cos(theta)) / np.pi, 0.0)


def growing_degree_days(tmin, tmax, base: float = 10.0, cap: float = 30.0) -> np.ndarray:
    """Degree days between `base` and `cap` (beneficial heat)."""
    return degree_days_above(tmin, tmax, base) - degree_days_above(tmin, tmax, cap)


def killing_degree_days(tmin, tmax, threshold: float = 30.0) -> np.ndarray:
    """Degree days above the damaging threshold (~30 C for soybean)."""
    return degree_days_above(tmin, tmax, threshold)


def saturation_vapour_pressure(t: np.ndarray) -> np.ndarray:
    """Tetens formula, kPa."""
    return 0.6108 * np.exp(17.27 * t / (t + 237.3))


def vapour_pressure_deficit(tmin, tmax) -> np.ndarray:
    """Daytime VPD proxy (kPa), assuming dew point ~ tmin (FAO-56 practice)."""
    return np.maximum(saturation_vapour_pressure(tmax) - saturation_vapour_pressure(tmin), 0.0)


# --------------------------------------------------------------------------
# Radiation / evapotranspiration / soil water
# --------------------------------------------------------------------------
def extraterrestrial_radiation(lat_deg: np.ndarray, doy: np.ndarray) -> np.ndarray:
    """Ra in MJ m-2 day-1 (FAO-56 eq. 21). Broadcasts lat (...,1) with doy (D,)."""
    phi = np.deg2rad(lat_deg)
    dr = 1 + 0.033 * np.cos(2 * np.pi * doy / 365)
    delta = 0.409 * np.sin(2 * np.pi * doy / 365 - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(delta), -1, 1))
    return (24 * 60 / np.pi) * 0.0820 * dr * (
        ws * np.sin(phi) * np.sin(delta) + np.cos(phi) * np.cos(delta) * np.sin(ws)
    )


def hargreaves_et0(tmin, tmax, ra) -> np.ndarray:
    """Reference evapotranspiration (mm/day), Hargreaves-Samani."""
    tmean = 0.5 * (tmin + tmax)
    return np.maximum(0.0023 * 0.408 * ra * (tmean + 17.8) * np.sqrt(np.maximum(tmax - tmin, 0)), 0)


def crop_coefficient(n_days: int, plant_idx, r1_idx, r6_idx, r7_idx) -> np.ndarray:
    """Piecewise soybean Kc curve driven by the simulated stages."""
    d = np.arange(n_days)
    p, r1, r6, r7 = (np.asarray(x)[..., None] for x in (plant_idx, r1_idx, r6_idx, r7_idx))
    ramp = np.clip((d - p) / np.maximum(r1 - p, 1), 0, 1)
    kc = np.where(d < p, 0.25, 0.40 + 0.65 * ramp)          # bare soil -> canopy closure
    kc = np.where((d >= r1) & (d < r6), 1.05, kc)            # full canopy, reproductive
    kc = np.where((d >= r6) & (d < r7), 0.70, kc)            # senescence
    kc = np.where(d >= r7, 0.30, kc)
    return kc


def water_balance(prcp, et0, kc, awc, sm0) -> np.ndarray:
    """Single-bucket soil water model (mm). Daily loop, vectorised over space.

    Actual ET is reduced linearly once soil water falls below 50% of the
    available water capacity (FAO-56 'p' = 0.5).
    """
    n_days = prcp.shape[-1]
    awc = np.asarray(awc, float)
    sm = np.empty(np.broadcast_shapes(prcp.shape, et0.shape, kc.shape), dtype=float)
    cur = np.broadcast_to(np.asarray(sm0, float), sm.shape[:-1]).copy()
    inv_half = 1.0 / (0.5 * awc)
    awc_b = np.broadcast_to(awc, cur.shape)
    demand = kc * et0
    for d in range(n_days):  # np.minimum/maximum: ~3x faster than np.clip in a tight loop
        aet = demand[..., d] * np.minimum(cur * inv_half, 1.0)
        cur = np.minimum(np.maximum(cur + prcp[..., d] - aet, 0.0), awc_b)
        sm[..., d] = cur
    return sm


def water_stress(sm, awc) -> np.ndarray:
    """0 = no stress, 1 = soil at wilting point. Stress starts below 50% AWC."""
    awc = np.asarray(awc, float)[..., None]
    return np.clip(1.0 - sm / (0.5 * awc), 0.0, 1.0)


# --------------------------------------------------------------------------
# Phenology and stage-window aggregation
# --------------------------------------------------------------------------
def stage_indices(daily_gdd: np.ndarray, plant_idx, stages=SOY_STAGES_GDD) -> dict[str, np.ndarray]:
    """Index of the first day each stage is reached (n_days if never reached)."""
    n_days = daily_gdd.shape[-1]
    d = np.arange(n_days)
    g = np.where(d >= np.asarray(plant_idx)[..., None], daily_gdd, 0.0)
    cum = np.cumsum(g, axis=-1)
    out = {}
    for name, thr in stages.items():
        reached = cum >= thr
        out[name] = np.where(reached.any(axis=-1), reached.argmax(axis=-1), n_days)
    return out


def window_mask(start, end, n_days: int) -> np.ndarray:
    d = np.arange(n_days)
    return (d >= np.asarray(start)[..., None]) & (d < np.asarray(end)[..., None])


def window_sum(x, start, end):
    return np.sum(np.where(window_mask(start, end, x.shape[-1]), x, 0.0), axis=-1)


def window_mean(x, start, end):
    m = window_mask(start, end, x.shape[-1])
    return np.sum(np.where(m, x, 0.0), axis=-1) / np.maximum(m.sum(axis=-1), 1)


# --------------------------------------------------------------------------
# One call: weather -> season features
# --------------------------------------------------------------------------
FEATURES = [
    "plant_doy", "veg_days", "rep_days", "r6_doy",
    "kdd_veg", "kdd_rep",
    "prcp_veg", "prcp_rep",
    "wstress_fill", "dry_rep", "vpd_rep",
    "sm_start",
]


@dataclass
class SeasonOutput:
    features: dict[str, np.ndarray]
    daily: dict[str, np.ndarray] | None = None


def season_features(
    tmin: np.ndarray,
    tmax: np.ndarray,
    prcp: np.ndarray,
    *,
    lat: np.ndarray,
    awc: np.ndarray,
    sm0: np.ndarray,
    plant_idx: np.ndarray,
    doy0: int,
    keep_daily: bool = False,
) -> SeasonOutput:
    """Compute stage-aware soybean features from a full season of daily weather.

    Shapes: weather (..., D); lat/awc/sm0/plant_idx broadcast to (...).
    `doy0` is the day of year of index 0 (e.g. 91 = 1 April).

    Windows
    -------
    veg  : planting -> R1 (vegetative)
    rep  : R1 -> R6   (flowering, pod set, seed fill: the yield-critical window)
    fill : R3 -> R6   (pod + seed fill, most sensitive to water)
    """
    n_days = tmin.shape[-1]
    lead = np.broadcast_shapes(tmin.shape[:-1], np.shape(lat), np.shape(plant_idx))
    awc_b = np.broadcast_to(awc, lead)
    plant_b = np.broadcast_to(plant_idx, lead)

    doy = doy0 + np.arange(n_days)
    tmax_ = np.maximum(tmax, tmin)
    mean, amp = 0.5 * (tmax_ + tmin), 0.5 * (tmax_ - tmin)
    kdd = _dd_dense(mean, amp, 30.0)
    gdd = _dd_dense(mean, amp, 10.0) - kdd
    vpd = vapour_pressure_deficit(tmin, tmax)
    st = stage_indices(gdd, plant_b)

    # radiation depends only on location and date: compute on (location, D)
    ra = extraterrestrial_radiation(np.asarray(lat, float)[..., None], doy)
    et0 = hargreaves_et0(tmin, tmax, ra)
    kc = crop_coefficient(n_days, plant_b, st["R1"], st["R6"], st["R7"])
    sm = water_balance(prcp, et0, kc, awc_b, sm0)
    ws = water_stress(sm, awc_b)

    p, r1, r3, r6 = plant_b, st["R1"], st["R3"], st["R6"]
    feats = {
        "plant_doy": (doy0 + p).astype(float),
        "veg_days": (r1 - p).astype(float),
        "rep_days": (r6 - r1).astype(float),
        "r6_doy": (doy0 + r6).astype(float),
        "kdd_veg": window_sum(kdd, p, r1),
        "kdd_rep": window_sum(kdd, r1, r6),
        "prcp_veg": window_sum(prcp, p, r1),
        "prcp_rep": window_sum(prcp, r1, r6),
        "wstress_fill": window_mean(ws, r3, r6),
        "dry_rep": window_mean(ws, r1, r6),
        "vpd_rep": window_mean(vpd, r1, r6),
        "sm_start": np.broadcast_to(np.asarray(sm0, float) / awc_b, lead).copy(),
    }
    daily = None
    if keep_daily:
        rep_mask = window_mask(r1, r6, n_days)
        daily = {"kdd": kdd, "ws": ws, "rep_mask": rep_mask, "gdd": gdd}
    return SeasonOutput(features=feats, daily=daily)
