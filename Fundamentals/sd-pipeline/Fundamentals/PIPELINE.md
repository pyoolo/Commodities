# S&D pipeline: workbooks → analysis → charts → report

Every weekday morning (and whenever a workbook is pushed) GitHub Actions:

1. **updates** the input cells of the workbooks from public sources (optional)
2. **recalculates** every formula with LibreOffice (headless): Python alone only sees the values Excel cached at the last save
3. **extracts** the balances into tidy CSV files (`output/data/`)
4. **compares** them with the previous run (git history) → "what changed" table
5. **draws** the charts (`output/charts/`)
6. **writes** the report: `output/report.html` (self-contained, can be emailed), `output/REPORT.md` (readable directly on GitHub), `output/index.html` (GitHub Pages), plus a dated copy in `output/archive/`
7. **commits** everything back to the repo

```
Fundamentals/
├── energy/oil/Oil_SD.xlsx                 # S&D workbooks: keep the file names STABLE
├── agriculture/soybeans/Soybean_SD.xlsx   # (no dates: git keeps the versions)
├── pipeline/
│   ├── config.yaml        # commodities, thresholds, data-source mappings
│   ├── run.py             # entry point
│   ├── recalc.py          # LibreOffice recalculation
│   ├── extractors/        # one file per workbook: reads sheets by ROW LABEL, not row number
│   ├── analysis.py        # KPIs, rule-based commentary, revisions
│   ├── charts.py
│   ├── report.py + templates/report.html.j2
│   └── updaters/          # eia_steo.py (EIA API), futures.py (Yahoo Finance)
└── output/                # generated – do not edit by hand
```

## Run it on your laptop

```bash
cd Fundamentals
pip install -r requirements.txt
python -m pipeline.run              # report from the workbooks as they are
python -m pipeline.run --update     # pull fresh data first (needs EIA_API_KEY for the EIA part)
open output/report.html
```
LibreOffice is optional locally (without it the pipeline uses Excel's cached values, which is fine for files you saved in Excel).

## One-time setup on GitHub

1. **EIA key** (free): register at https://www.eia.gov/opendata/register.php, then
   *Settings → Secrets and variables → Actions → New repository secret* → name `EIA_API_KEY`.
2. **Actions write access**: *Settings → Actions → General → Workflow permissions* → "Read and write permissions".
3. **GitHub Pages** (optional, gives the team a fixed URL): *Settings → Pages → Source: GitHub Actions*.
   On a private repo this needs a paid plan; without it, read `output/REPORT.md` in the repo or download the `report.html` artifact from the run.
4. Run it once by hand: *Actions → S&D report → Run workflow*.

## Day-to-day

| You do | What happens |
|---|---|
| Edit a workbook in Excel and push it | Report rebuilt within ~3 min; the "what changed" table shows your revisions |
| Nothing | Weekday 07:00 UTC: data refreshed, report rebuilt, committed |
| Change the scenario / levers in Excel | The report follows the workbook (it reports the *active* scenario + the comparison table) |

**Rules that keep it working**
- Do not rename sheets or the row labels in column A that the extractors use (e.g. `Scenario balance`, `ENDING STOCKS`). You *can* insert rows and columns freely.
- Updaters only write blue input cells, never formulas. A value that moves more than `max_change_pct` is **not** written and is flagged at the top of the report.
- Pull before you edit (`git pull`): the bot commits to the workbooks too. Excel files cannot be merged.
- Futures tickers in `config.yaml` (ZSX26.CBT, …) must be rolled by hand together with the row labels in the Inputs sheet.
- EIA series ids in `config.yaml` are a starting mapping: verify them once in the EIA API browser (https://www.eia.gov/opendata/browser/steo). A wrong id is reported, never written.

## Add a new commodity (e.g. copper)

1. Put `metals/copper/Copper_SD.xlsx` in the repo.
2. Copy `pipeline/extractors/oil.py` → `copper.py`, adapt the sheet names and labels. Return a `long` table (`item, unit, period, value`) so revisions work.
3. Add `analyse_copper` in `analysis.py` and `copper_charts` in `charts.py` (or start with a minimal version).
4. Add the entry in `config.yaml`. Push.
