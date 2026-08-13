from __future__ import annotations

from pathlib import Path

import yaml

from .analytics import performance_summary
from .backtest import run_backtest
from .data import make_synthetic_market_data
from .spread import clean_spark_spread, rolling_zscore, trading_position


def main() -> None:
    config_path = Path(__file__).resolve().parents[2] / "config.yaml"
    with config_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    demo = cfg["synthetic_demo"]
    plant = cfg["plant"]
    signal_cfg = cfg["signal"]
    bt_cfg = cfg["backtest"]

    market = make_synthetic_market_data(periods=demo["periods"], seed=demo["seed"])
    css = clean_spark_spread(
        market["power"],
        market["gas"],
        market["carbon"],
        efficiency=plant["efficiency"],
        emissions_intensity=plant["emissions_intensity_tco2_per_mwh"],
    )
    z = rolling_zscore(css, lookback=signal_cfg["lookback"])
    pos = trading_position(z, entry_z=signal_cfg["entry_z"])
    bt = run_backtest(css, pos, transaction_cost_per_unit=bt_cfg["transaction_cost_per_unit"])
    stats = performance_summary(bt, annualization_factor=bt_cfg["annualization_factor"])

    print("Clean Spark Spread Trading — synthetic demo")
    for key, value in stats.items():
        print(f"{key:>20}: {value:,.4f}")


if __name__ == "__main__":
    main()
