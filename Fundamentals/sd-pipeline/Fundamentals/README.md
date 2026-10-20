# Fundamentals

Supply and demand analysis, cost curves and sector notes — the "why" behind the price.

## Scope
- **Balances** per commodity: production, consumption, stocks, stocks-to-use ratio
- **Cost curves**: marginal cost of production, breakeven by producer and region
- **Sector deep dives**: oil, natural gas & LNG, power, base metals, precious metals, grains, softs
- **Policy**: OPEC+ quotas, export bans, biofuel mandates, tariffs, strategic reserves
- **Structural themes**: energy transition, electrification, critical minerals, food security

## Suggested layout
```
Fundamentals/
├── energy/
├── metals/
├── agriculture/
└── policy/
```

## Key reports to track
EIA STEO & Weekly Petroleum Status Report · IEA OMR · OPEC MOMR · USDA WASDE ·
ICSG / IAI / WBMS for metals · IGC for grains · GIE AGSI+ for EU gas storage

## Automated S&D pipeline
The workbooks in `energy/` and `agriculture/` feed an automatic pipeline (GitHub Actions):
recalculation → tidy data → charts → report, every weekday and on every push.
Latest report: [`output/REPORT.md`](output/REPORT.md) · full version `output/report.html`.
How it works and how to add a commodity: [`PIPELINE.md`](PIPELINE.md).
