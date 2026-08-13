from __future__ import annotations

import numpy as np
import pandas as pd


def make_synthetic_market_data(periods: int = 500, seed: int = 42) -> pd.DataFrame:
    """Generate reproducible synthetic power, gas and EUA prices for demos/tests."""
    if periods < 60:
        raise ValueError("periods should be at least 60 for rolling research")

    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=periods, freq="D")

    gas = 32 + np.cumsum(rng.normal(0, 0.35, periods))
    carbon = 70 + np.cumsum(rng.normal(0, 0.45, periods))

    seasonal = 7 * np.sin(np.arange(periods) * 2 * np.pi / 365)
    power = 25 + gas / 0.50 + carbon * 0.36 + seasonal + rng.normal(0, 5.5, periods)

    return pd.DataFrame(
        {"power": power, "gas": gas, "carbon": carbon},
        index=idx,
    )
