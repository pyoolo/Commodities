# 02 — Clean Spark Spread Trading

A compact quantitative research project on European power generation margins and systematic trading signals.

## Research question

Can information embedded in power, gas and carbon prices be transformed into a robust clean-spark-spread signal, and does that signal retain value after realistic trading frictions?

## Why this project matters

A gas-fired power plant earns a gross generation margin when the electricity price exceeds the fuel and carbon cost required to produce one MWh of power. The clean spark spread (CSS) is a simple way to represent this economics.

For power price `P`, gas price `G`, EUA price `C`, plant efficiency `eta`, and emissions intensity `e`:

```text
CSS = P - G / eta - C * e
```

The project turns this market relationship into a reproducible research pipeline:

```text
market data -> clean spark spread -> signal -> position -> P&L -> risk
```

## Project structure

```text
02-clean-spark-spread-trading/
├── config.yaml
├── data/
├── figures/
├── notebooks/
│   └── 01_clean_spark_research.ipynb
├── src/
│   └── clean_spark/
│       ├── __init__.py
│       ├── analytics.py
│       ├── backtest.py
│       ├── cli.py
│       ├── data.py
│       └── spread.py
├── tests/
│   ├── test_backtest.py
│   └── test_spread.py
└── README.md
```

## What is implemented

- clean spark spread calculation;
- configurable efficiency and emissions intensity;
- rolling z-score trading signal;
- long / flat / short position generation;
- transaction-cost-aware backtest;
- P&L, Sharpe, max drawdown, hit rate and turnover;
- synthetic demo dataset so the project runs without proprietary data;
- unit tests for the economic formula and backtest mechanics.

## Quick start

From this project directory:

```bash
python -m pip install pandas numpy pyyaml pytest
export PYTHONPATH=src
python -m clean_spark.cli
pytest -q
```

The CLI runs a synthetic end-to-end example and prints the final performance metrics.

## Suggested real data mapping

The same pipeline can later be connected to real European energy data:

| Variable | Example market series |
|---|---|
| Power | DE/LU day-ahead or forward power price |
| Gas | TTF day-ahead / front-month / forward |
| Carbon | EUA futures |
| Fundamentals | load, wind, solar, outages, temperature |

The research code deliberately keeps the data adapter separate from the pricing and backtesting logic so public or proprietary feeds can be swapped in later.

## Signal definition

The baseline signal uses the rolling z-score of CSS:

```text
z_t = (CSS_t - rolling_mean_t) / rolling_std_t
```

Contrarian baseline:

- `z > entry_z` -> short CSS;
- `z < -entry_z` -> long CSS;
- otherwise -> flat.

This is intentionally simple. A later iteration can compare mean reversion against momentum, percentile thresholds, regime filters and fundamental residual models.

## Research extensions

1. Replace synthetic data with TTF, EUA and European power prices.
2. Add load, wind, solar and temperature features.
3. Compare spot CSS with forward CSS across maturities.
4. Add plant-specific heat rates and emissions factors.
5. Add regime detection for scarcity / negative-price periods.
6. Attribute P&L to power, gas and carbon legs.
7. Move generic risk and backtesting components into `cqr_core`.

## Portfolio narrative

This project is designed as the second building block after a gas forward-curve project:

```text
01 Gas Forward Curve Construction
             |
             v
02 Clean Spark Spread Trading
             |
             v
03 Power Fundamentals Model
             |
             v
04 Battery Arbitrage
             |
             v
05 Cross-Border Power Spreads
```

The goal is not only to forecast prices, but to connect market economics to an executable and measurable trading decision.
