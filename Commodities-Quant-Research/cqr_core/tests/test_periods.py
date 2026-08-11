"""Tests for delivery period parsing and the averaging matrix."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from cqr_core.periods import (
    DeliveryPeriod,
    daily_index,
    parse_product,
    period_weight_matrix,
)


class TestParseProduct:
    @pytest.mark.parametrize(
        "code,start,end",
        [
            ("Jan-27", date(2027, 1, 1), date(2027, 1, 31)),
            ("Feb-28", date(2028, 2, 1), date(2028, 2, 29)),  # leap year
            ("Q1-27", date(2027, 1, 1), date(2027, 3, 31)),
            ("Q4-27", date(2027, 10, 1), date(2027, 12, 31)),
            ("Cal-27", date(2027, 1, 1), date(2027, 12, 31)),
            ("Sum-27", date(2027, 4, 1), date(2027, 9, 30)),
            ("Win-27", date(2027, 10, 1), date(2028, 3, 31)),
        ],
    )
    def test_known_products(self, code, start, end):
        p = parse_product(code)
        assert (p.start, p.end) == (start, end)

    def test_winter_straddles_year_boundary(self):
        """The single most common off-by-one-year bug in gas systems."""
        assert parse_product("Win-26").end.year == 2027

    @pytest.mark.parametrize(
        "a,b", [("Jan-27", "jan-27"), ("Q1-27", "q127"), ("Cal-27", "CAL_2027")]
    )
    def test_formatting_is_forgiving(self, a, b):
        assert parse_product(a).start == parse_product(b).start
        assert parse_product(a).end == parse_product(b).end

    @pytest.mark.parametrize("bad", ["Q5-27", "Jaan-27", "27", "", "Jan-"])
    def test_rejects_garbage(self, bad):
        with pytest.raises(ValueError):
            parse_product(bad)

    def test_quarters_tile_the_year(self):
        cal = parse_product("Cal-27")
        quarters = [parse_product(f"Q{i}-27") for i in range(1, 5)]
        assert sum(q.n_days for q in quarters) == cal.n_days
        assert all(cal.contains(q) for q in quarters)

    def test_seasons_tile_the_gas_year(self):
        summer, winter = parse_product("Sum-27"), parse_product("Win-27")
        assert summer.end + timedelta(days=1) == winter.start


class TestDeliveryPeriod:
    def test_rejects_inverted_period(self):
        with pytest.raises(ValueError, match="ends"):
            DeliveryPeriod(date(2027, 3, 1), date(2027, 1, 1), "bad")

    def test_containment_is_not_overlap(self):
        jan = parse_product("Jan-27")
        q1 = parse_product("Q1-27")
        q2 = parse_product("Q2-27")
        assert q1.contains(jan) and not jan.contains(q1)
        assert q1.overlaps(jan) and not q1.overlaps(q2)


class TestWeightMatrix:
    def test_rows_are_averaging_weights(self):
        products = [parse_product(c) for c in ("Jan-27", "Feb-27")]
        index = daily_index(products)
        A = period_weight_matrix(products, index)
        assert A.shape == (2, 59)
        np.testing.assert_allclose(A.sum(axis=1), 1.0)
        # Flat weights: each January day carries 1/31.
        np.testing.assert_allclose(A[0, :31], 1 / 31)
        np.testing.assert_allclose(A[0, 31:], 0.0)

    def test_averaging_a_flat_curve_returns_the_level(self):
        products = [parse_product(c) for c in ("Q1-27", "Cal-27")]
        index = daily_index(products)
        A = period_weight_matrix(products, index)
        flat = np.full(len(index), 27.5)
        np.testing.assert_allclose(A @ flat, 27.5)

    def test_day_weights_change_the_average(self):
        """Non-flat weights matter: peak power is not baseload."""
        products = [parse_product("Jan-27")]
        index = daily_index(products)
        w = np.where(index.dayofweek < 5, 12.0, 0.0)  # weekday peak hours only
        A = period_weight_matrix(products, index, day_weights=w)
        assert A[0][index.dayofweek >= 5].sum() == pytest.approx(0.0)
        assert A.sum() == pytest.approx(1.0)

    def test_rejects_partial_coverage(self):
        index = pd.date_range("2027-01-01", "2027-01-20", freq="D")
        with pytest.raises(ValueError, match="partially covered"):
            period_weight_matrix([parse_product("Jan-27")], index)

    def test_rejects_bad_weight_shape(self):
        products = [parse_product("Jan-27")]
        index = daily_index(products)
        with pytest.raises(ValueError, match="shape"):
            period_weight_matrix(products, index, day_weights=np.ones(5))
