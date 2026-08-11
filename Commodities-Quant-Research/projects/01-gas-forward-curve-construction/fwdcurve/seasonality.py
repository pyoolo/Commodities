"""Prior seasonal shape for the daily gas curve.

The bootstrapper needs something to pull towards inside long delivery windows.
Given only a Cal-28 quote, a pure smoothness objective returns a nearly
straight line through the year — which is a defensible mathematical answer and
an indefensible commercial one, since January gas is not worth the same as
July gas.

The shape prior encodes what we know about within-year structure before
looking at any quote:

* **Temperature.** Space heating dominates European gas demand, so the annual
  pattern tracks heating degree days closely. Modelled here as a sinusoid
  peaking in mid-January, plus a second harmonic that steepens the winter peak
  relative to the summer trough — real HDD profiles are not symmetric.
* **Day of week.** Industrial offtake falls at weekends, so weekend delivery
  days price at a small discount. Small in gas, much larger in power.

This is deliberately a *stylised* prior, not a demand model. Its job is to
break the degeneracy of the optimisation in a sensible direction; the quotes
still bind exactly. A production desk would replace it with a shape fitted to
historical settlement data or to a normalised HDD forecast.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = ["seasonal_shape", "hdd_proxy"]

# Day of the year on which heating demand peaks. Mid-January: the coldest part
# of the NW European winter lags the solstice by a few weeks.
_PEAK_DOY = 15.0


def hdd_proxy(
    index: pd.DatetimeIndex,
    amplitude: float = 1.0,
    asymmetry: float = 0.25,
) -> np.ndarray:
    """Stylised heating-degree-day profile, normalised to zero mean.

    Parameters
    ----------
    index
        Delivery days to evaluate on.
    amplitude
        Peak-to-mean height of the fundamental annual cycle.
    asymmetry
        Weight on the second harmonic. Positive values sharpen the winter peak
        and flatten the summer trough, which is what observed HDD profiles do.

    Returns
    -------
    ndarray
        Zero-mean seasonal factor, one value per delivery day.
    """
    doy = index.dayofyear.to_numpy(dtype=float)
    # Length-of-year normalisation so leap years do not drift the phase.
    year_len = np.where(index.is_leap_year, 366.0, 365.0)
    phase = 2.0 * np.pi * (doy - _PEAK_DOY) / year_len

    fundamental = np.cos(phase)
    second = np.cos(2.0 * phase)
    shape = amplitude * (fundamental + asymmetry * second)
    return shape - shape.mean()


def seasonal_shape(
    index: pd.DatetimeIndex,
    level: float = 30.0,
    winter_premium: float = 6.0,
    weekend_discount: float = 0.30,
    asymmetry: float = 0.25,
) -> pd.Series:
    """Build the daily shape prior passed to :func:`fwdcurve.bootstrap.build_curve`.

    Parameters
    ----------
    level
        Reference price level. Immaterial to the fitted curve — the builder
        rescales the prior to the quote level — but keeps the series readable
        when plotted on its own.
    winter_premium
        Price uplift, in currency units, of the January peak over the annual
        mean. Sets how much seasonality the prior asserts.
    weekend_discount
        Saturday and Sunday discount to the weekday price.
    asymmetry
        Passed through to :func:`hdd_proxy`.

    Returns
    -------
    pd.Series
        Shape prior indexed by delivery date.
    """
    if winter_premium < 0:
        raise ValueError("winter_premium must be non-negative")

    seasonal = hdd_proxy(index, amplitude=1.0, asymmetry=asymmetry)
    # Scale so the annual maximum sits `winter_premium` above the mean.
    peak = np.abs(seasonal).max()
    if peak > 0:
        seasonal = seasonal * (winter_premium / peak)

    is_weekend = index.dayofweek.to_numpy() >= 5
    dow = np.where(is_weekend, -weekend_discount, 0.0)
    # Re-centre so the day-of-week effect redistributes value rather than
    # shifting the overall level.
    dow = dow - dow.mean()

    return pd.Series(level + seasonal + dow, index=index, name="shape_prior")
