"""Daily forward curve construction from period-delivery quotes.

The market quotes months, quarters, seasons and calendar years. Every model
downstream — storage optimisation, swing valuation, spark spreads, PnL
attribution — needs a price for each individual *delivery day*. Turning the
former into the latter is the bootstrapping problem solved here.

Two requirements pull against each other:

1. **Reconstitution (hard).** Averaging the fitted daily curve back over any
   quoted delivery window must return that window's quote. If it does not, the
   curve is arbitrageable against the instruments it was built from, and any
   hedge ratio derived from it is wrong.
2. **Plausible shape (soft).** Infinitely many daily curves satisfy (1). The
   naive choice — a flat price within each product, stepping at period
   boundaries — is smooth nowhere and puts artificial jumps exactly at the
   month ends where storage and swing optionality is valued.

The standard resolution, following Fleten & Lemming (2003), is to impose (1)
as an equality constraint and pick among the feasible curves the one that best
trades off roughness against a prior seasonal shape:

.. math::

    \\min_f \\; w_s \\lVert f - s \\rVert^2
             + w_r \\lVert D_2 f \\rVert^2
    \\quad \\text{s.t.} \\quad A f = q

where :math:`D_2` is the second-difference operator, :math:`s` the prior shape
(see :mod:`fwdcurve.seasonality`), :math:`A` the averaging matrix and :math:`q` the
quote vector.

This is a quadratic program with linear equality constraints, so it has a
closed-form solution via its KKT system — no iterative solver, no convergence
tolerance to tune.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from cqr_core.periods import (
    DeliveryPeriod,
    daily_index,
    parse_product,
    period_weight_matrix,
)

__all__ = [
    "CurveFit",
    "build_curve",
    "check_quote_consistency",
    "second_difference_matrix",
]


def second_difference_matrix(n: int) -> np.ndarray:
    """Second-difference operator ``D2`` of shape ``(n - 2, n)``.

    ``(D2 @ f)[i] = f[i] - 2 f[i+1] + f[i+2]``, the discrete curvature.
    Penalising its norm penalises kinks, not slope, so a genuine seasonal
    trend passes through unsmoothed while spurious month-boundary steps do not.
    """
    if n < 3:
        return np.zeros((0, n))
    D = np.zeros((n - 2, n))
    rows = np.arange(n - 2)
    D[rows, rows] = 1.0
    D[rows, rows + 1] = -2.0
    D[rows, rows + 2] = 1.0
    return D


@dataclass
class CurveFit:
    """Result of a curve build, with the diagnostics needed to trust it."""

    curve: pd.Series
    """Daily forward curve, indexed by delivery date."""

    products: list[DeliveryPeriod]
    quotes: np.ndarray
    reconstituted: np.ndarray
    """Quotes recovered by averaging the fitted curve. Should equal ``quotes``."""

    roughness: float
    """``||D2 f||^2`` — lower is smoother. Useful for comparing weightings."""

    shape_prior: pd.Series = field(repr=False, default=None)

    @property
    def reconstitution_error(self) -> pd.Series:
        """Per-product pricing error, in the curve's price units."""
        return pd.Series(
            self.reconstituted - self.quotes,
            index=[p.label for p in self.products],
            name="error",
        )

    @property
    def max_abs_error(self) -> float:
        return float(np.abs(self.reconstituted - self.quotes).max())

    def summary(self) -> pd.DataFrame:
        """Per-product comparison of quoted vs reconstituted price."""
        return pd.DataFrame(
            {
                "start": [p.start for p in self.products],
                "end": [p.end for p in self.products],
                "days": [p.n_days for p in self.products],
                "quote": self.quotes,
                "reconstituted": self.reconstituted,
                "error": self.reconstituted - self.quotes,
            },
            index=[p.label for p in self.products],
        )


def check_quote_consistency(
    quotes: dict[str, float],
    day_weights: np.ndarray | None = None,
    tol: float = 1e-6,
) -> pd.DataFrame:
    """Detect internally arbitrageable input quotes.

    If Jan, Feb and Mar are all quoted, Q1 is not free: it must equal their
    day-weighted average. When the market genuinely disagrees, that is a
    calendar arbitrage — but far more often it is a stale quote or a bad feed,
    and feeding it to the solver produces an infeasible constraint set that
    silently degrades into a least-squares compromise.

    Returns one row per nested relationship found, empty if the quote set is
    consistent. Checking before fitting is cheaper than debugging after.
    """
    periods = {code: parse_product(code) for code in quotes}
    index = daily_index(list(periods.values()))

    rows = []
    for outer_code, outer in periods.items():
        children = [
            c
            for c, p in periods.items()
            if c != outer_code and outer.contains(p) and p.n_days < outer.n_days
        ]
        # Keep only maximal children, so Q1 is checked against Jan/Feb/Mar and
        # not against a mixture of Jan/Feb/Mar and a nested sub-period.
        maximal = [
            c
            for c in children
            if not any(
                other != c and periods[other].contains(periods[c])
                for other in children
            )
        ]
        if not maximal:
            continue
        covered = sum(periods[c].n_days for c in maximal)
        if covered != outer.n_days:
            continue  # partial cover implies nothing

        A = period_weight_matrix(
            [periods[c] for c in maximal], index, day_weights
        )
        outer_row = period_weight_matrix([outer], index, day_weights)[0]
        # Weight each child by its share of the parent's total delivery weight.
        shares = np.array(
            [outer_row[A[i] > 0].sum() for i in range(len(maximal))]
        )
        implied = float(
            np.dot(shares, [quotes[c] for c in maximal]) / shares.sum()
        )
        diff = quotes[outer_code] - implied
        if abs(diff) > tol:
            rows.append(
                {
                    "product": outer_code,
                    "quoted": quotes[outer_code],
                    "implied_by_children": implied,
                    "difference": diff,
                    "children": ", ".join(maximal),
                }
            )
    return pd.DataFrame(rows)


def build_curve(
    quotes: dict[str, float],
    shape_prior: pd.Series | None = None,
    smoothness_weight: float = 1.0,
    shape_weight: float = 1e-4,
    day_weights: np.ndarray | None = None,
) -> CurveFit:
    """Fit a daily forward curve that exactly reprices the quoted products.

    Parameters
    ----------
    quotes
        Product code to price, e.g. ``{"Jan-27": 34.10, "Q2-27": 28.55}``.
        Codes are parsed by :func:`cqr_core.periods.parse_product`.
    shape_prior
        Daily seasonal shape to pull towards, in price units. Re-centred
        internally on the average quote, so only its deviations matter and its
        absolute level is ignored. Defaults to flat.
    smoothness_weight, shape_weight
        Relative weight on curvature vs deviation from the prior. The default
        ratio (1 : 1e-4) lets the prior set the seasonal pattern where quotes
        are sparse while keeping the curve smooth where they are dense.
    day_weights
        Per-day delivery volume; flat by default (baseload gas convention).

    Returns
    -------
    CurveFit
        Always check ``max_abs_error`` before using the curve. It should be at
        machine-precision level; anything larger means the constraints were
        inconsistent or rank-deficient in an unexpected way.

    Notes
    -----
    Redundant constraints (Q1 quoted alongside Jan, Feb and Mar) are handled
    gracefully: the KKT system is solved in the least-squares sense, so a
    consistent-but-redundant row costs nothing. An *inconsistent* redundant row
    is a different matter — run :func:`check_quote_consistency` first.
    """
    if not quotes:
        raise ValueError("no quotes supplied")
    if smoothness_weight < 0 or shape_weight < 0:
        raise ValueError("weights must be non-negative")
    if smoothness_weight == 0 and shape_weight == 0:
        raise ValueError("at least one of the two weights must be positive")

    codes = list(quotes)
    products = [parse_product(c) for c in codes]
    index = daily_index(products)
    n = len(index)

    q = np.array([quotes[c] for c in codes], dtype=float)
    A = period_weight_matrix(products, index, day_weights)

    # Prior shape, rescaled to the quote level. Only the *shape* enters the
    # solution in any material way, because A f = q pins down the level.
    if shape_prior is None:
        s = np.full(n, q.mean())
    else:
        aligned = shape_prior.reindex(index)
        if aligned.isna().any():
            raise ValueError(
                "shape_prior does not cover the full delivery index "
                f"({int(aligned.isna().sum())} missing days)"
            )
        vals = aligned.to_numpy(dtype=float)
        if not np.isfinite(vals).all():
            raise ValueError("shape_prior contains non-finite values")
        # Re-centre *additively*, not multiplicatively. A prior saying
        # "January is 6 EUR above the annual mean" must mean the same thing
        # whether it was written around a level of 5 or 500; scaling it
        # proportionally would make its arbitrary level control how much
        # seasonality the fit ends up with.
        s = vals - vals.mean() + q.mean()

    D2 = second_difference_matrix(n)

    # Objective: w_s ||f - s||^2 + w_r ||D2 f||^2
    #   -> H = 2 (w_s I + w_r D2' D2),  g = 2 w_s s
    H = 2.0 * (shape_weight * np.eye(n) + smoothness_weight * (D2.T @ D2))
    g = 2.0 * shape_weight * s

    # A tiny ridge keeps H positive definite when shape_weight is set to zero;
    # it is far below the scale of any economically meaningful price move.
    H += 1e-12 * np.eye(n)

    # --- Null-space reduction -------------------------------------------
    # Assembling the KKT system directly and solving it in one shot mixes two
    # very differently scaled blocks: the curvature block has entries of order
    # w_r, while the averaging rows of A have entries of order 1/31. On a
    # two-year curve that costs several digits of accuracy, and the whole point
    # of the exercise is that the constraints hold to machine precision.
    #
    # Instead, split the problem. Take any particular solution of A f = q, then
    # search over the null space of A, where the constraints hold by
    # construction and only the (well-conditioned) objective remains:
    #
    #     f = f_p + Z y,   A Z = 0   ->   (Z' H Z) y = Z' (g - H f_p)
    f_p, *_ = np.linalg.lstsq(A, q, rcond=None)

    _, sv, vt = np.linalg.svd(A, full_matrices=True)
    rank = int((sv > max(A.shape) * np.finfo(float).eps * sv[0]).sum())
    Z = vt[rank:].T  # (n, n - rank) orthonormal basis of null(A)

    if Z.shape[1] > 0:
        reduced = Z.T @ H @ Z
        rhs = Z.T @ (g - H @ f_p)
        y, *_ = np.linalg.lstsq(reduced, rhs, rcond=None)
        f = f_p + Z @ y
    else:
        # Quotes pin down every delivery day; nothing left to optimise.
        f = f_p

    curve = pd.Series(f, index=index, name="forward")
    return CurveFit(
        curve=curve,
        products=products,
        quotes=q,
        reconstituted=A @ f,
        roughness=float(np.sum((D2 @ f) ** 2)) if D2.size else 0.0,
        shape_prior=pd.Series(s, index=index, name="shape_prior"),
    )
