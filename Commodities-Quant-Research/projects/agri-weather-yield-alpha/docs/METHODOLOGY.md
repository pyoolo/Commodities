# Methodology

## 1. Why a synthetic world

Real crop and price data are partly licensed, and a research repo should be
runnable by anyone in minutes. More importantly, a synthetic world has a
**known truth**. That allows three tests real data cannot provide:

* does the model recover the true weather response (including interactions)?
* does the pipeline capture an edge that exists by construction?
* does that edge **vanish** when the market is made efficient (null market)?

The third test is the one that protects against self-deception. A strategy that
"works" on the null market has a bug or a leak.

## 2. The world (`src/agriyield/synthetic/`)

**Geography.** 5 states x 40 counties on a Corn-Belt-like domain (37-45.5° N),
each with soil available water capacity and soybean acreage.

**Weather.** Daily tmax, tmin and precipitation, 1 Apr - 31 Oct, 1995-2025.
Anomalies come from a few spatial factors at three time scales: a
season-long persistent regime, a slow sub-seasonal AR(1) (heat domes) and a
fast synoptic AR(1). Moisture is negatively correlated with heat, so hot-dry
spells cluster as they do in reality.

**Phenology and water.** Soybean stages from growing degree days after planting
(VE ... R7), a single-bucket soil-water model with Hargreaves ET0 and a stage-
dependent crop coefficient. Planting is delayed by wet springs.

**Hidden yield function** (`truth.py`, never imported by models):

```
log yield = county effect + 1.35%/yr trend
          + 0.0025 (reproductive days - 45)
          - 0.0045 KDD_R1-R6 x (1 + 1.5 x drought_R1-R6)   # heat hurts more when dry
          - 0.0010 KDD_veg - 0.22 waterstress_R3-R6^1.5
          - late planting, late maturity (frost), VPD and waterlogging thresholds
          + state and county shocks weather cannot explain
```

Calibrated to a national yield deviation of ~7% (sd) and county ~11%.

**Forecasts.** Ensembles (15 members, 15 days) built so that successive runs
are **martingales**: the error for a target day is a sum of independent
innovations, one removed with each new run. Members are calibrated (spread =
error sd). Both properties matter: without them the "efficient" expectation
drifts predictably, and a momentum strategy earns money even in an efficient
market. That bug showed up during development, which is the point of having a null.

**USDA.** Report r = trend x exp(lambda_r x true deviation + noise_r), with
lambda = 0.60, 0.75, 0.88, 0.95 for Aug-Nov: early reports lean toward trend.

**Consensus.** The analyst survey moves only part of the way (kappa = 0.5) from
the previous USDA number toward what public information implies. Analysts
cannot anticipate USDA's own sampling noise.

**Market.** Price = P0 x exp(-2 x E_t + noise), where E_t is the market's
expected yield deviation. The efficient benchmark is

```
E*_t = D*_t + s_hat_t
```

* `D*_t`: the true yield function run on observed weather + forecast scenarios,
  plus a drift correction (the regime information that keeps arriving as new
  days enter the forecast window). Its daily changes have ~0 autocorrelation.
* `s_hat_t`: a precision-weighted (Bayesian) estimate of the non-weather
  component, updated by each USDA report.

The traded market deviates from E* in three ways, all set in the config:
gradual pricing of news (`adjustment_speed` 0.35/day), anchoring on the USDA
headline (`usda_anchor` 0.6), and drifting to the consensus before reports.
The **null market** uses the same world and the same noise draws, with
`adjustment_speed = 1` and `usda_anchor = 0`.

## 3. Point-in-time data (`data/store.py`, `data/sources.py`)

Every table has a `knowledge_time`. The store only returns rows public at the
query time, and the weather source masks unobserved days and refuses
reanalysis for seasons that are not final. Tests in `tests/test_point_in_time.py`
try to cheat in the common ways and must fail.

| Information | Public from |
|---|---|
| County yields, year y | 20 Feb y+1 |
| Final reanalysis, season y | ~31 Jan y+1 |
| Observed weather, day d | day d+1 (gridMET-like latency) |
| Forecast run | issue day |
| Crop conditions | Monday 16:00 |
| USDA report | report day 12:00 |
| Consensus | 3 business days before the report, 17:00 |
| Futures settle | 14:20 (ET) |

## 4. Models (`models/`)

All county-level, predicting log yield:

* **Trend + county fixed effects** (no weather): the May baseline.
* **Panel regression**: fixed effects + state trends + degree days, quadratic
  precipitation, late planting, starting soil moisture (Schlenker-Roberts style).
* **Gradient boosting** on the residual of the trend/FE baseline, using all
  stage-window features plus soil and latitude, so it can learn interactions
  such as heat x drought without having to extrapolate the trend.
* **Blend**: 50/50 panel + GBM.
* **Crop-condition benchmark**: national yield on trend + national Good/
  Excellent %, per week (Irwin & Good / farmdoc style).

## 5. In-season scenario engine (`forecast/`)

On each trading day from 1 June to 30 September (weekly in October):

```
observed weather to date  +  ensemble member m (15 days)  +  analog year a(m)
        -> season features -> county model -> acreage-weighted national yield
```

This gives a 15-member distribution of national yield. Each member's analog
year is fixed for the whole season, so day-to-day changes come from new
information and not from redrawing climatology.

## 6. Walk-forward protocol (`validation/walkforward.py`)

For each forecast year y (2003-2025): set as_of = 31 May y, train on every
season public by then, fit all models, then run the scenario engine through
the season. 2003-2007 forecasts only calibrate the USDA-mimic layer; trading
P&L is counted from 2008. No hyper-parameter was tuned on the test world: the
momentum settings were picked on the separate small `--quick` world.

## 7. Signals (`signals/strategies.py`)

**USDA surprise.** Prices react to USDA minus consensus. A ridge "USDA-mimic"
layer (past years only, shrunk toward "USDA prints our number") maps our
forecast and the previous USDA number to a predicted print. Then
`pos = -clip(log(predicted USDA / consensus) / 1%, -1, 1)`, entered at the close
before the report and exited at the report-day close.

**Weather momentum.** `z_t = log E_t[yield] - log E_{t-3}[yield]`;
`pos = -clip(z_t / 1%, -1, 1)`, held one day. Flat the day before a report.

Costs: 3 bp per unit of turnover. P&L is in log-return units per unit notional.

## 8. Checks against self-deception

* **Null market.** Same world and noise, efficient pricing: Sharpe should be ~0.
* **Placebos.** Random trade directions (surprise) and circular shifts of the
  position series (momentum): p-value = share of placebos beating the strategy.
* **Benchmark.** The same surprise strategy driven by the crop-condition model.
* **Martingale test.** The null market's expectation must have unpredictable
  daily changes (`tests/test_world.py`).

## 9. Limitations (and what changes with real data)

* The size of the edge is set by the market parameters. The synthetic results
  show the pipeline *can capture* such an edge and does not invent one when
  it is absent. They say nothing about how big the edge is in CBOT soybeans.
* Real USDA behaviour is richer: objective yield surveys from September, state
  level estimates, a methodology that changes over time.
* Real markets also price South American supply, demand, the dollar and fund
  positioning. The `daily_vol_pct` noise stands in for all of that.
* Hourly temperatures, irrigation, maturity groups and satellite vegetation
  indices are left out for clarity. See `docs/DATA_SOURCES.md` for extensions.
