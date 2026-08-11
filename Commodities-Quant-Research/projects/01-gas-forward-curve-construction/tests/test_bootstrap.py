"""Tests for the forward curve bootstrapper.

The headline property is reconstitution: averaging the fitted daily curve back
over each quoted window must return that quote. Everything else — smoothness,
seasonality — is a preference. Reconstitution is a no-arbitrage requirement,
so it is tested to machine precision rather than to a loose tolerance.
"""

import numpy as np
import pandas as pd
import pytest

from fwdcurve.bootstrap import (
    build_curve,
    check_quote_consistency,
    second_difference_matrix,
)
from fwdcurve.seasonality import seasonal_shape
from fwdcurve.synthetic import granularity_ladder, synthetic_quotes

# Exact quotes admit an exact fit; anything above this is a real bug.
EXACT = 1e-10


@pytest.fixture
def exact_quotes():
    """Consistent, unrounded quote set plus the truth it was built from."""
    return synthetic_quotes(round_to=None)


class TestSecondDifferenceMatrix:
    def test_shape_and_stencil(self):
        D = second_difference_matrix(5)
        assert D.shape == (3, 5)
        np.testing.assert_array_equal(D[0], [1, -2, 1, 0, 0])

    def test_annihilates_affine_curves(self):
        """Curvature of a straight line is zero, so trends are not penalised."""
        D = second_difference_matrix(40)
        line = 20.0 + 0.3 * np.arange(40)
        np.testing.assert_allclose(D @ line, 0.0, atol=1e-12)

    def test_degenerate_lengths(self):
        assert second_difference_matrix(2).shape == (0, 2)


class TestReconstitution:
    def test_monthly_quotes_reprice_exactly(self):
        quotes = {"Jan-27": 38.0, "Feb-27": 36.5, "Mar-27": 33.0}
        fit = build_curve(quotes)
        assert fit.max_abs_error < EXACT

    def test_full_ladder_reprices_exactly(self, exact_quotes):
        quotes, truth = exact_quotes
        fit = build_curve(quotes, shape_prior=seasonal_shape(truth.index))
        assert fit.max_abs_error < EXACT

    def test_redundant_nested_quotes_are_harmless(self):
        """Q1 quoted alongside Jan/Feb/Mar makes A rank-deficient by design."""
        months = {"Jan-27": 38.0, "Feb-27": 36.5, "Mar-27": 33.0}
        index = pd.date_range("2027-01-01", "2027-03-31", freq="D")
        n = np.array([31, 28, 31], dtype=float)
        q1 = float(np.dot(n, list(months.values())) / n.sum())

        with_q1 = build_curve({**months, "Q1-27": q1})
        without_q1 = build_curve(months)

        assert with_q1.max_abs_error < EXACT
        # The redundant row adds no information, so the curve must not move.
        np.testing.assert_allclose(
            with_q1.curve.to_numpy(), without_q1.curve.to_numpy(), atol=1e-8
        )

    def test_error_is_bounded_by_input_inconsistency(self):
        """Rounded screen quotes are mildly arbitrageable; the fit degrades
        gracefully rather than blowing up or silently ignoring a constraint."""
        for tick in (3, 2, 1):
            quotes, _ = synthetic_quotes(round_to=tick)
            worst = check_quote_consistency(quotes, tol=0.0)["difference"].abs().max()
            fit = build_curve(quotes)
            assert fit.max_abs_error <= worst + EXACT

    def test_single_quote_is_a_valid_problem(self):
        fit = build_curve({"Cal-27": 30.0})
        assert fit.max_abs_error < EXACT
        assert len(fit.curve) == 365

    def test_fully_determined_system_has_no_freedom(self):
        """One quote per delivery day leaves the null space empty."""
        quotes = {f"{m}-27": 30.0 + i for i, m in enumerate(["Jan"])}
        fit = build_curve(quotes)
        assert fit.max_abs_error < EXACT


class TestShapeAndSmoothness:
    def test_flat_quotes_give_a_flat_curve_without_a_prior(self):
        quotes = {"Q1-27": 30.0, "Q2-27": 30.0, "Q3-27": 30.0, "Q4-27": 30.0}
        fit = build_curve(quotes)
        assert fit.curve.std() < 1e-6

    def test_prior_creates_seasonality_the_quotes_do_not_pin_down(self):
        """A lone Cal quote says nothing about within-year shape. The prior is
        what stops the answer being a commercially absurd flat line."""
        quotes = {"Cal-27": 30.0}
        index = pd.date_range("2027-01-01", "2027-12-31", freq="D")

        flat = build_curve(quotes)
        shaped = build_curve(quotes, shape_prior=seasonal_shape(index))

        assert flat.curve.std() < 1e-6
        assert shaped.curve.std() > 1.0
        # January should price above July.
        assert shaped.curve["2027-01"].mean() > shaped.curve["2027-07"].mean()
        # ...but the annual average is still exactly the quote.
        assert shaped.max_abs_error < EXACT

    def test_prior_level_is_irrelevant(self):
        """Only the prior's shape should matter; the quotes set the level."""
        quotes, truth = synthetic_quotes(round_to=None)
        low = seasonal_shape(truth.index, level=5.0)
        high = seasonal_shape(truth.index, level=500.0)
        a = build_curve(quotes, shape_prior=low).curve
        b = build_curve(quotes, shape_prior=high).curve
        np.testing.assert_allclose(a.to_numpy(), b.to_numpy(), atol=1e-6)

    def test_more_smoothing_lowers_roughness(self):
        quotes, truth = synthetic_quotes(round_to=None)
        shape = seasonal_shape(truth.index)
        rough = build_curve(quotes, shape_prior=shape, smoothness_weight=1e-2)
        smooth = build_curve(quotes, shape_prior=shape, smoothness_weight=1e3)
        assert smooth.roughness < rough.roughness
        assert smooth.max_abs_error < EXACT

    def test_beats_the_naive_step_curve(self):
        """The baseline a desk would otherwise use: flat within each product.
        The fit should be both smoother and closer to the truth."""
        quotes, truth = synthetic_quotes(round_to=None)
        index = truth.index

        step = pd.Series(np.nan, index=index)
        for code, price in quotes.items():
            from cqr_core.periods import parse_product

            p = parse_product(code)
            mask = (index.date >= p.start) & (index.date <= p.end)
            # Finest granularity wins where products are nested.
            step.loc[mask & step.isna()] = price
        step = step.ffill().bfill()

        fit = build_curve(quotes, shape_prior=seasonal_shape(index))
        rmse = lambda x: float(np.sqrt(((x - truth) ** 2).mean()))
        assert rmse(fit.curve) < rmse(step)


class TestQuoteConsistency:
    def test_consistent_ladder_is_clean(self, exact_quotes):
        quotes, _ = exact_quotes
        assert check_quote_consistency(quotes, tol=1e-9).empty

    def test_detects_a_stale_cal_quote(self):
        quotes, _ = synthetic_quotes(round_to=None)
        quotes["Cal-28"] += 2.0
        report = check_quote_consistency(quotes, tol=1e-6)
        assert "Cal-28" in set(report["product"])
        assert report.set_index("product").loc["Cal-28", "difference"] == pytest.approx(
            2.0, abs=1e-6
        )

    def test_ignores_partial_cover(self):
        """Jan alone does not determine Q1, so nothing should be flagged."""
        assert check_quote_consistency({"Q1-27": 35.0, "Jan-27": 38.0}).empty


class TestValidation:
    def test_rejects_empty_quotes(self):
        with pytest.raises(ValueError, match="no quotes"):
            build_curve({})

    def test_rejects_zero_weights(self):
        with pytest.raises(ValueError, match="positive"):
            build_curve({"Jan-27": 30.0}, smoothness_weight=0.0, shape_weight=0.0)

    def test_rejects_negative_weights(self):
        with pytest.raises(ValueError, match="non-negative"):
            build_curve({"Jan-27": 30.0}, smoothness_weight=-1.0)

    def test_rejects_prior_with_gaps(self):
        index = pd.date_range("2027-01-01", "2027-01-20", freq="D")
        short = pd.Series(30.0, index=index)
        with pytest.raises(ValueError, match="does not cover"):
            build_curve({"Jan-27": 30.0}, shape_prior=short)

    def test_summary_is_reportable(self, exact_quotes):
        quotes, truth = exact_quotes
        summary = build_curve(quotes).summary()
        assert list(summary.index) == list(quotes)
        assert {"quote", "reconstituted", "error"} <= set(summary.columns)
