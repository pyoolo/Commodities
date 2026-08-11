# Commodities-Quant-Research

A portfolio of quantitative research projects in energy commodities — natural gas, power and LNG. Each project is self-contained, with its own code, tests and write-up.

The emphasis is on the problems that are specific to *delivered* commodities and have no equity or credit analogue: prices attach to a delivery window rather than a point in time, storage and flexibility create physical optionality, and weather is the dominant short-term driver. Models that ignore this — a GBM on a gas price, a VaR that assumes normality — fail in characteristic and expensive ways.

> **Educational, synthetic data only.** No licensed market data is redistributed here. Every dataset is generated from stylised models whose parameters loosely resemble European gas, so the results are illustrative rather than tradeable.

---

## Projects

| # | Project | Question | Status |
|---|---------|----------|--------|
| 01 | [Gas forward curve construction](projects/01-gas-forward-curve-construction) | How do you turn monthly, quarterly and Cal quotes into a daily curve that reprices every one of them exactly? | ✅ Complete |

Planned, in rough dependency order:

| # | Project | Question |
|---|---------|----------|
| 02 | Storage valuation | What is a gas storage asset worth — rolling intrinsic vs full extrinsic value via Least-Squares Monte Carlo? |
| 03 | Spread option pricing | How far apart are Kirk, Margrabe and Monte Carlo on a spark spread, and where does each break down? |
| 04 | Weather-driven demand | How much of day-ahead gas demand is explained by HDD, and what does an ensemble forecast imply for the price distribution? |
| 05 | Swing contract valuation | What is the optionality in a take-or-pay contract worth under volume constraints? |
| 06 | LNG netback arbitrage | When does a US cargo go to Europe rather than Asia, and what is the diversion option worth? |

---

## Structure

```
Commodities-Quant-Research/
├── cqr_core/                  shared infrastructure used by 2+ projects
│   ├── periods.py             delivery periods, averaging matrices
│   └── tests/
├── projects/
│   └── NN-project-name/
│       ├── README.md          the write-up: question, method, results, limits
│       ├── <package>/         project code (uniquely named, never "src")
│       ├── tests/
│       ├── outputs/           generated figures and tables
│       └── run_analysis.py    reproduces every figure in the README
└── docs/
    ├── CONTRIBUTING.md        conventions for adding a project
    └── _project_template/
```

Two rules keep the container from degenerating into a folder of scripts:

1. **A project earns its place by answering a question**, stated in its README as a question. Code that does not serve a stated question belongs in `cqr_core` or nowhere.
2. **Anything used by two projects moves to `cqr_core`** and gets its own tests. Duplicated utilities are how these repos rot.

---

## Getting started

```bash
git clone https://github.com/<you>/Commodities-Quant-Research.git
cd Commodities-Quant-Research
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

make test                                    # whole suite
cd projects/01-gas-forward-curve-construction
python run_analysis.py                       # regenerates figures
```

Requires Python 3.10+.

---

## Conventions

- **Reproducibility.** Every figure comes from a seeded `run_analysis.py`. No notebook-only results.
- **Tests are the argument.** A model claim that is not tested is an assertion. Numerical properties that follow from the maths — no-arbitrage reconstitution, invariances, limiting cases — are tested to machine precision, not to a loose tolerance chosen after the fact.
- **Negative results stay in.** Where a method underperforms, the write-up says so. A "Limitations" section is mandatory.
- **Comments explain the modelling choice, not the syntax.** Why a second-difference penalty rather than a first-difference one; why Black-76 rather than Black-Scholes.

See [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) for the full checklist.

---

## Licence

MIT — see [LICENSE](LICENSE).
