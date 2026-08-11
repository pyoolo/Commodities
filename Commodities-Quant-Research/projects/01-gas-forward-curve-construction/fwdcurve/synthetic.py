"""Synthetic market quotes for a TTF-like gas curve.

No licensed market data is stored in this repository. Every figure here is
generated from a stylised model whose parameters loosely resemble European gas
around a normal winter, so the plots look plausible without any vendor data
being redistributed.

The generator deliberately produces an *internally consistent* quote set:
coarse products are derived by averaging the fine ones rather than being drawn
independently. That gives the test suite a known ground truth to check the
bootstrapper against, and lets inconsistency be injected on purpose when
testing :func:`fwdcurve.bootstrap.check_quote_consistency`.
"""

from __future__ import annotations

import calendar
from datetime import date

import numpy as np
import pandas as pd

from cqr_core.periods import daily_index, parse_product, period_weight_matrix

__all__ = ["synthetic_daily_truth", "synthetic_quotes", "granularity_ladder"]

_MONTHS = [m.capitalize() for m in calendar.month_abbr if m]


def synthetic_daily_truth(
    start_year: int = 2027,
    n_years: int = 2,
    level: float = 31.0,
    winter_premium: float = 7.5,
    contango_per_year: float = -1.2,
    weekend_discount: float = 0.35,
    noise: float = 0.15,
    seed: int = 20270101,
) -> pd.Series:
    """Generate the 'true' daily curve the quotes will be built from.

    Combines an annual heating cycle, a mild backwardation along the curve
    (negative ``contango_per_year``), a weekend effect, and a small amount of
    idiosyncratic daily noise so the curve is not exactly reproducible by a
    smooth fit — the bootstrapper should recover the structure, not the noise.
    """
    rng = np.random.default_rng(seed)
    index = pd.date_range(
        date(start_year, 1, 1), date(start_year + n_years - 1, 12, 31), freq="D"
    )

    doy = index.dayofyear.to_numpy(dtype=float)
    year_len = np.where(index.is_leap_year, 366.0, 365.0)
    phase = 2.0 * np.pi * (doy - 15.0) / year_len
    seasonal = winter_premium * (np.cos(phase) + 0.25 * np.cos(2.0 * phase)) / 1.25

    t = (index - index[0]).days.to_numpy(dtype=float) / 365.25
    trend = contango_per_year * t

    weekend = np.where(index.dayofweek.to_numpy() >= 5, -weekend_discount, 0.0)
    weekend = weekend - weekend.mean()

    eps = rng.normal(0.0, noise, size=len(index))

    return pd.Series(level + seasonal + trend + weekend + eps, index=index, name="truth")


def granularity_ladder(start_year: int = 2027, n_years: int = 2) -> list[str]:
    """Product codes at the granularity a real gas curve is quoted with.

    Liquidity thins out along the curve, so the front year is quoted monthly
    while later years trade as quarters, seasons and a calendar strip. That
    uneven granularity is precisely what makes bootstrapping non-trivial:
    the fit has to invent daily structure where the market gives none.
    """
    codes = [f"{m}-{start_year % 100:02d}" for m in _MONTHS]
    for k in range(1, n_years):
        y = (start_year + k) % 100
        codes += [f"Q{i}-{y:02d}" for i in range(1, 5)]
        codes.append(f"Cal-{y:02d}")
    return codes


def synthetic_quotes(
    start_year: int = 2027,
    n_years: int = 2,
    codes: list[str] | None = None,
    round_to: int | None = 3,
    **truth_kwargs,
) -> tuple[dict[str, float], pd.Series]:
    """Produce a consistent quote set together with the truth it came from.

    Returns
    -------
    quotes
        Mapping of product code to price.
    truth
        The daily curve the quotes were averaged from, for benchmarking.

    Notes
    -----
    ``round_to`` mimics the tick size a screen actually shows. Rounding breaks
    exact internal consistency by up to half a tick, which is realistic — and a
    good reminder that ``check_quote_consistency`` needs a tolerance scaled to
    the tick, not to machine epsilon.
    """
    truth = synthetic_daily_truth(
        start_year=start_year, n_years=n_years, **truth_kwargs
    )
    if codes is None:
        codes = granularity_ladder(start_year, n_years)

    products = [parse_product(c) for c in codes]
    index = daily_index(products)
    truth = truth.reindex(index)
    if truth.isna().any():
        raise ValueError("requested products extend beyond the generated truth curve")

    A = period_weight_matrix(products, index)
    prices = A @ truth.to_numpy()
    if round_to is not None:
        prices = np.round(prices, round_to)

    return {c: float(p) for c, p in zip(codes, prices)}, truth
