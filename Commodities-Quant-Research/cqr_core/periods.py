"""Delivery period abstractions for commodity forward products.

Commodity forwards deliver over a *period* (a month, a quarter, a season, a
calendar year), not at a single point in time. Almost every downstream model —
curve construction, storage valuation, spread options — needs a consistent way
to map a traded product onto the set of delivery days it covers.

This module provides that mapping. Everything is deliberately
delivery-day-based rather than tenor-based, because that is how physical gas
and power actually settle.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

__all__ = [
    "DeliveryPeriod",
    "parse_product",
    "daily_index",
    "period_weight_matrix",
]


# Gas seasons in the European convention: Summer = Apr-Sep, Winter = Oct-Mar.
# Note the winter season straddles a year boundary: "Win-26" runs Oct-2026
# through Mar-2027.
_SUMMER_MONTHS = (4, 9)
_WINTER_MONTHS = (10, 3)

_MONTH_ABBR = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}


@dataclass(frozen=True)
class DeliveryPeriod:
    """A contiguous delivery window, inclusive of both endpoints.

    Parameters
    ----------
    start, end
        First and last delivery day.
    label
        Human-readable product name, e.g. ``"Q1-27"``. Used for reporting only.
    """

    start: date
    end: date
    label: str = ""

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError(
                f"delivery period {self.label!r} ends ({self.end}) "
                f"before it starts ({self.start})"
            )

    @property
    def n_days(self) -> int:
        return (self.end - self.start).days + 1

    def days(self) -> pd.DatetimeIndex:
        return pd.date_range(self.start, self.end, freq="D")

    def contains(self, other: "DeliveryPeriod") -> bool:
        """True if ``other`` is fully nested inside this period."""
        return self.start <= other.start and other.end <= self.end

    def overlaps(self, other: "DeliveryPeriod") -> bool:
        return self.start <= other.end and other.start <= self.end

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        name = self.label or "period"
        return f"<{name} {self.start}..{self.end} ({self.n_days}d)>"


def _month_period(year: int, month: int, label: str) -> DeliveryPeriod:
    last = calendar.monthrange(year, month)[1]
    return DeliveryPeriod(date(year, month, 1), date(year, month, last), label)


def _span(start: date, end: date, label: str) -> DeliveryPeriod:
    return DeliveryPeriod(start, end, label)


def _resolve_year(yy: str) -> int:
    """Map a 2- or 4-digit year string to a full year.

    Two-digit years are read as 20xx, which is safe for the horizons these
    curves are built over.
    """
    y = int(yy)
    return y if y >= 1000 else 2000 + y


def parse_product(code: str) -> DeliveryPeriod:
    """Parse a market product code into its delivery period.

    Supported formats (case-insensitive, hyphen optional):

    ==================  ==========================================
    ``Jan-27``          single calendar month
    ``Q3-27``           calendar quarter
    ``Sum-27``          summer gas season (Apr-27 .. Sep-27)
    ``Win-27``          winter gas season (Oct-27 .. Mar-28)
    ``Cal-27``          calendar year
    ==================  ==========================================

    Examples
    --------
    >>> parse_product("Q1-27").n_days
    90
    >>> parse_product("Win-26").end
    datetime.date(2027, 3, 31)
    """
    raw = code.strip()
    token = raw.replace("_", "-").lower()
    # Accept "jan27" and "q127" as well as the hyphenated forms. The optional
    # digit in the first group is the quarter number, which belongs to the
    # product kind rather than to the year.
    token = re.sub(r"^([a-z]+\d?)[-\s]*(\d{2,4})$", r"\1-\2", token)

    m = re.fullmatch(r"([a-z]+\d*)-(\d{2,4})", token)
    if not m:
        raise ValueError(f"unrecognised product code: {code!r}")

    kind, yy = m.group(1), m.group(2)
    year = _resolve_year(yy)

    if kind in _MONTH_ABBR:
        return _month_period(year, _MONTH_ABBR[kind], raw)

    if kind == "cal":
        return _span(date(year, 1, 1), date(year, 12, 31), raw)

    if kind.startswith("q") and kind[1:].isdigit():
        q = int(kind[1:])
        if not 1 <= q <= 4:
            raise ValueError(f"quarter out of range in {code!r}")
        first_month = 3 * (q - 1) + 1
        last_month = first_month + 2
        last_day = calendar.monthrange(year, last_month)[1]
        return _span(date(year, first_month, 1), date(year, last_month, last_day), raw)

    if kind in ("sum", "summer"):
        a, b = _SUMMER_MONTHS
        last_day = calendar.monthrange(year, b)[1]
        return _span(date(year, a, 1), date(year, b, last_day), raw)

    if kind in ("win", "winter"):
        a, b = _WINTER_MONTHS
        last_day = calendar.monthrange(year + 1, b)[1]
        return _span(date(year, a, 1), date(year + 1, b, last_day), raw)

    raise ValueError(f"unrecognised product code: {code!r}")


def daily_index(periods: list[DeliveryPeriod]) -> pd.DatetimeIndex:
    """Daily index spanning the union of all supplied periods.

    The union is taken as ``[min(start), max(end)]``. Gaps between periods are
    filled: a curve with holes in it is not something downstream models can
    integrate over.
    """
    if not periods:
        raise ValueError("no delivery periods supplied")
    start = min(p.start for p in periods)
    end = max(p.end for p in periods)
    return pd.date_range(start, end, freq="D")


def period_weight_matrix(
    periods: list[DeliveryPeriod],
    index: pd.DatetimeIndex,
    day_weights: np.ndarray | None = None,
) -> np.ndarray:
    """Build the averaging matrix ``A`` mapping a daily curve onto quotes.

    For a daily forward curve ``f`` (one price per delivery day), the fair
    value of a period product is the volume-weighted average of the daily
    prices over its delivery window. Stacking one row per product gives
    ``A @ f = q``.

    Parameters
    ----------
    periods
        Products to build rows for.
    index
        Daily delivery index the curve is defined on.
    day_weights
        Per-day delivery volume. Defaults to flat (1.0 per day), which is the
        right convention for baseload gas. For power, pass the number of
        peak or off-peak hours per day instead.

    Returns
    -------
    ndarray, shape ``(len(periods), len(index))``
        Each row sums to 1.0 across the days of its delivery period.
    """
    n_p, n_d = len(periods), len(index)
    if day_weights is None:
        day_weights = np.ones(n_d)
    day_weights = np.asarray(day_weights, dtype=float)
    if day_weights.shape != (n_d,):
        raise ValueError(
            f"day_weights has shape {day_weights.shape}, expected {(n_d,)}"
        )
    if np.any(day_weights < 0):
        raise ValueError("day_weights must be non-negative")

    idx_dates = index.date
    A = np.zeros((n_p, n_d))
    for i, p in enumerate(periods):
        mask = (idx_dates >= p.start) & (idx_dates <= p.end)
        if not mask.any():
            raise ValueError(f"product {p.label!r} lies outside the curve index")
        covered = mask.sum()
        if covered != p.n_days:
            raise ValueError(
                f"product {p.label!r} is only partially covered by the curve "
                f"index ({covered}/{p.n_days} days)"
            )
        w = day_weights * mask
        total = w.sum()
        if total <= 0:
            raise ValueError(f"product {p.label!r} has zero total delivery weight")
        A[i] = w / total
    return A
