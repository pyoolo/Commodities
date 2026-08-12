# 🛢️ Commodities

> A personal research repository on commodity markets — energy, metals, agriculture and softs. Theory, data, code and quantitative research in one place.

The goal is to build a structured knowledge base that goes from market fundamentals to systematic trading and hedging models.

---

## 📁 Repository structure

```
Commodities/
├── Commodities-Quant-Research/   # Systematic strategies, factor research, backtests
├── Fundamentals/                 # Supply & demand balances, sector notes, theory
├── Market-Data/                  # Ingestion, cleaning and storage of time series
├── Derivatives-Pricing/          # Futures, options, swaps and structured products
├── Risk-Management/              # VaR, stress testing, hedging, margining
├── Macro-and-Cross-Asset/        # Cycle, inflation, USD, rates vs commodities
├── Physical-and-Logistics/       # Freight, storage, refining, trade flows
├── Notebooks/                    # Exploratory analysis and visualisation
└── Resources/                    # Papers, books, glossary, links
```

| Folder | What goes in it | Status |
|---|---|---|
| [`Commodities-Quant-Research/`](./Commodities-Quant-Research) | Signals, factor models, backtesting engine, results | ✅ Active |
| [`Fundamentals/`](./Fundamentals) | Balance sheets per commodity, production costs, sector deep dives | 🔜 |
| [`Market-Data/`](./Market-Data) | Download scripts, continuous contract builders, data catalogue | 🔜 |
| [`Derivatives-Pricing/`](./Derivatives-Pricing) | Black-76, spread options, term-structure models, vol surfaces | 🔜 |
| [`Risk-Management/`](./Risk-Management) | VaR/ES, scenario analysis, hedge ratios, margin simulation | 🔜 |
| [`Macro-and-Cross-Asset/`](./Macro-and-Cross-Asset) | Inflation hedging, dollar beta, correlation regimes | 🔜 |
| [`Physical-and-Logistics/`](./Physical-and-Logistics) | Freight rates, storage economics, chokepoints, trade flows | 🔜 |
| [`Notebooks/`](./Notebooks) | Jupyter notebooks, charts, quick studies | 🔜 |
| [`Resources/`](./Resources) | Reading list, glossary, useful links | 🔜 |

---

## 🌍 Commodity taxonomy

### ⚡ Energy
| Commodity | Main benchmarks | Exchange |
|---|---|---|
| Crude oil | Brent, WTI, Dubai/Oman, Urals | ICE, NYMEX |
| Refined products | Gasoil, RBOB, Jet Fuel, HSFO | ICE, NYMEX |
| Natural gas | Henry Hub (US), TTF (EU), JKM (Asia LNG) | NYMEX, ICE Endex |
| Power | German Power, PUN, PJM, ERCOT | EEX, GME, ICE |
| Coal | API2 (ARA), Newcastle | ICE |
| Carbon | EUA (EU ETS), UKA, CCA | ICE, EEX |

### 🥇 Precious metals
Gold, Silver, Platinum, Palladium — LBMA benchmarks, futures on COMEX and NYMEX.
**Drivers:** real rates, USD, central bank buying, industrial demand (Ag, Pt, Pd), risk aversion.

### 🔩 Base / industrial metals
Copper, Aluminium, Zinc, Nickel, Lead, Tin — mostly **LME** (3-month contracts, prompt-date system) plus SHFE and COMEX.
**Drivers:** Chinese manufacturing cycle, construction, energy transition, exchange inventories.

### 🔋 Battery & critical materials
Lithium, Cobalt, Rare earths, Uranium, Iron ore. Thinner markets, often priced off assessments (Fastmarkets, Platts) rather than liquid futures.

### 🌾 Grains & oilseeds
Corn, Wheat (SRW/HRW/Milling), Soybeans + complex (meal, oil), Rice, Rapeseed.
**Drivers:** weather, planting/harvest cycles, WASDE, export policy, biofuel mandates.

### ☕ Softs
Coffee (Arabica/Robusta), Cocoa, Sugar (#11 raw / #5 white), Cotton, Orange juice.

### 🐄 Livestock
Live Cattle, Feeder Cattle, Lean Hogs.

---

## 🧠 Core concepts

### Term structure

- **Contango** — deferred futures trade above spot. Typical of well-supplied markets; rolling produces **negative roll yield**.
- **Backwardation** — deferred futures trade below spot. Signals physical tightness; rolling produces **positive roll yield**.

### Cost of carry

$$F_{t,T} = S_t \cdot e^{(r + u - y)(T-t)}$$

where `r` = risk-free rate, `u` = storage and insurance cost, `y` = **convenience yield** — the implicit benefit of holding the physical commodity.

Convenience yield is what separates commodities from financial assets: **you cannot short the physical indefinitely**, which breaks the arbitrage in one direction only.

### Total return of a futures position

```
Total Return = Spot Return + Roll Yield + Collateral Return
```

Over long horizons roll yield explains most of the gap between commodity index performance and spot prices.

### Basis and spreads

- **Basis** = local cash price − futures price. Captures quality, logistics and timing.
- **Calendar spread** — long/short different maturities of the same underlying.
- **Crack spread** — refining margin (e.g. 3-2-1: 3 crude → 2 gasoline + 1 distillate).
- **Spark spread** — gas-fired power margin (power − gas × heat rate). Add carbon and it becomes the **clean spark spread**.
- **Dark spread** — the coal equivalent.
- **Crush spread** — soybeans → meal + oil.
- **Location spread** — same commodity, different hubs (WTI vs Brent, TTF vs Henry Hub).

### Market-specific behaviour

- Structural **seasonality** (heating demand, harvests, driving season).
- **Physical delivery**: watch first notice date and last trading date.
- **Limit up / limit down** on agricultural contracts.
- **Non-Gaussian volatility**: fat tails, jumps, mean reversion toward marginal cost of production.
- **Storage constraints**: when storage saturates, prices can go negative (WTI, April 2020).

---

## 🏛️ Key exchanges

| Exchange | Focus |
|---|---|
| **CME Group** (NYMEX, COMEX, CBOT) | US energy, precious metals, grains |
| **ICE** | Brent, gasoil, softs, TTF, EUA |
| **LME** | Base metals, physical delivery, warrants |
| **SHFE / INE / DCE / ZCE** | Chinese markets, increasingly price-setting |
| **Euronext / MATIF** | Milling wheat, rapeseed |
| **EEX / GME** | European power and gas |
| **MCX** | India |

---

## 📊 Data sources

**Official and free**
- **EIA** — US inventories and production (Weekly Petroleum Status Report)
- **IEA** — Oil Market Report, World Energy Outlook
- **OPEC** — Monthly Oil Market Report
- **USDA** — WASDE, Crop Progress, Export Sales
- **CFTC** — Commitments of Traders (speculative positioning)
- **GIE AGSI+ / ALSI** — European gas and LNG storage
- **Baker Hughes** — rig count
- **LME / CME / ICE** — warehouse stocks, open interest, settlements

**Commercial**
LSEG (Refinitiv), Bloomberg, Platts, Argus, Fastmarkets, Kpler, Vortexa, Wood Mackenzie.

**Retail / prototyping**
Nasdaq Data Link, Yahoo Finance, Barchart, Investing.com, `yfinance`, `pandas-datareader`.

---

## 🛠️ Toolkit

```python
# Core
pandas, numpy, scipy, statsmodels, polars

# Quant / backtesting
scikit-learn, vectorbt, backtrader, zipline-reloaded, quantstats

# Pricing and stochastic modelling
QuantLib-Python, arch, pymc

# Data & viz
yfinance, requests, plotly, matplotlib, seaborn
```

---

## 🔬 Research themes

Covered (or to be covered) in `Commodities-Quant-Research/`:

- **Commodity factors**: momentum, carry (basis), value, hedging pressure, inventory, seasonality
- **Continuous series construction**: roll methodologies (calendar, open interest, volume) and adjustment (panama, ratio, none) — a choice that materially changes backtest results
- **Term-structure models**: Schwartz-Smith two-factor, stochastic convenience yield
- **Storage models** and the theory of storage
- **Volatility**: implied surfaces, GARCH family, seasonal vol
- **Spread trading** and cointegration across related commodities
- **Weather and fundamentals** as predictive features
- **Commodities and inflation**: hedging properties, conditional correlation with traditional assets

### ⚠️ Common backtest pitfalls

1. Using front-month prices without modelling the roll → wildly unrealistic performance.
2. Ignoring transaction costs and slippage on illiquid contracts.
3. Survivorship bias from delisted contracts.
4. Look-ahead bias on fundamental data (WASDE and EIA are released with a lag and **get revised**).
5. Underestimating margin requirements and margin-call risk on futures.

---

## 📚 Reading list

**Books**
- *Commodity Option Pricing* — Iain Clark
- *Energy and Power Risk Management* — Eydeland & Wolyniec
- *The Economics of Commodity Markets* — Chevallier & Ielpo
- *Trading and Investing in Commodity Markets* — Radoslav Radev
- *Expected Returns* — Antti Ilmanen (commodities chapter)

**Foundational papers**
- Keynes (1930) — *Theory of Normal Backwardation*
- Working (1949) — *Theory of the Inverse Carrying Charge*
- Gorton & Rouwenhorst (2006) — *Facts and Fantasies about Commodity Futures*
- Erb & Harvey (2006) — *The Strategic and Tactical Value of Commodity Futures*
- Schwartz (1997) — *The Stochastic Behavior of Commodity Prices*

---

## 🤝 Contributing

Personal repository, but suggestions, issues and pull requests are welcome.

## ⚖️ Disclaimer

Everything here is for **educational and research purposes only**. Nothing in this repository constitutes financial advice, an investment recommendation, or a solicitation to buy or sell any financial instrument. Trading commodity derivatives carries a high risk of capital loss.

## 📄 License

[MIT](LICENSE) *(to be added)*
