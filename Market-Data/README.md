# Market-Data

Ingestion, cleaning and storage of commodity time series. Everything downstream depends on this being correct.

## Scope
- Download scripts per source (EIA, USDA, CFTC, exchanges, vendor APIs)
- **Continuous contract construction** — the single most important piece here
- Data validation: gaps, stale prints, outliers, timezone and settlement alignment
- Local storage: Parquet or DuckDB, partitioned by commodity and date

## Continuous contracts
Document, for every series produced:
- **Roll rule** — fixed calendar day, N days before expiry, open-interest crossover, or volume crossover
- **Adjustment** — none (raw), panama/difference, or ratio
- **Which leg** — front month, second month, or a constant-maturity blend

Unadjusted series give correct price levels but broken returns. Adjusted series give correct returns but meaningless levels. Keep both.

## Suggested layout
```
Market-Data/
├── loaders/        # One module per source
├── continuous/     # Roll logic and builders
├── validation/     # Quality checks
└── catalogue.md    # What series exist, from where, updated when
```
