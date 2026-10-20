# Data sources: synthetic stand-ins and their real counterparts

Every synthetic table in this repo imitates a real dataset, including its
**release time**. The `knowledge_time` column is the part that matters most:
the backtest only ever sees a record once its `knowledge_time` has passed.
When wiring real data, archive every vintage as it is published. Re-downloading
history later gives revised data and silently breaks point-in-time integrity.

Adapters to implement live in `src/agriyield/data/sources.py` (`NassCountyYields`,
`NassCropProgress`, `UsdaCropProduction`, `CmeSoybeanFutures`, `Era5LandWeather`, ...).
Nothing downstream changes when they are swapped in.

## Core inputs (used by the current pipeline)

| Synthetic table | Real source | Access | Cadence and release (`knowledge_time`) | Notes and pitfalls |
|---|---|---|---|---|
| `county_yields` | USDA NASS county soybean yield (Quick Stats: `commodity_desc=SOYBEANS`, `statisticcat_desc=YIELD`, `agg_level_desc=COUNTY`) | Free API key, quickstats.nass.usda.gov/api | Annual; County Estimates release in **February of y+1** | Coverage gaps (suppressed counties) are growing; revisions happen. Keep vintages. |
| `county_acres` | NASS **June Acreage** report (state), Cropland Data Layer for county shares | Quick Stats; CropScape (nassgeodata.gmu.edu) | Acreage: end of June. CDL: annual, early in y+1 | Before June use **Prospective Plantings** (end of March) or last year's footprint. |
| `planting` | NASS **Crop Progress** (% planted, by state) | Quick Stats | Weekly, **Mondays 4pm ET**, Apr-Jun | County-level dates need remote sensing (e.g. Sentinel-1/2 emergence detection). |
| `conditions` | NASS Crop Progress & **Condition** (% Good/Excellent, by state) | Quick Stats | Weekly, **Mondays 4pm ET**, Jun-Oct | Ratings drift over decades (observer and practice changes); use as benchmark, de-bias before use. |
| `soil_moisture_start` | NASA **SMAP L4** root-zone soil moisture, or ERA5-Land `swvl1-3` | NSIDC / Copernicus CDS | Daily, ~2-3 days latency | Convert to fraction of available water capacity with gSSURGO. |
| `county_static.awc_mm` | USDA NRCS **gSSURGO** available water storage 0-150 cm | Free download | Static | Aggregate with CDL soybean-pixel weights. |
| weather (observed) | **ERA5-Land** hourly (0.1°) via Copernicus CDS (`cdsapi`, dataset `reanalysis-era5-land`); US alternatives **gridMET** or **PRISM** (~1 day latency) | Free | ERA5T preliminary ~5 days; ERA5 final ~2-3 months | Train on final reanalysis only for seasons that were final at the time; use preliminary data in-season. Aggregate grid to county with crop-mask weights. |
| weather (forecasts) | **NOAA GEFS** (31 members, 00/06/12/18Z, to 16 days; AWS Open Data bucket `noaa-gefs-pds`); **ECMWF ENS** (51 members, 00/12Z; open data subset or licensed); AI ensembles such as **ECMWF AIFS-ENS** | Free (GEFS), open/licensed (ECMWF) | Every run, ~4-6 h after cycle time | Archive each run on arrival. Calibrate (bias-correct, check spread vs error): an under-dispersed ensemble biases convex damage functions (KDD). |
| `wasde_trend` | USDA **WASDE** May projection (trend yield, also discussed at the February Ag Outlook Forum) | usda.library.cornell.edu (ESMIS) | Monthly, ~10th-12th, **12:00 ET** | Defines the "no weather" reference for deviations. |
| `usda_reports` | USDA NASS **Crop Production** report (national + state yield, Aug-Nov; final in the January Annual Summary) | ESMIS archive | Monthly, **12:00 ET** on report day | The August report is mostly farmer surveys; objective field counts enter from September. |
| `consensus` | **Reuters / Bloomberg** pre-report analyst surveys | Licensed (terminal / data feed) | 2-4 business days before each report | The average, range and number of analysts are all useful features. |
| `futures` | CME **soybean futures (ZS)**, November contract (`ZSX`) | CME DataMine, Bloomberg, Databento, Refinitiv | Daily settlement, ~1:15-1:20 pm CT | Use the new-crop November contract; roll and liquidity before September need care. |

## Extensions (natural next datasets)

| Use | Source |
|---|---|
| Seasonal regime information beyond 15 days | ECMWF **SEAS5**, NOAA **CFSv2**, ENSO/MJO indices (NOAA CPC) |
| Vegetation state, ahead of condition ratings | **MODIS** MOD13Q1 / VIIRS NDVI-EVI; **Sentinel-2** (10 m); **TROPOMI SIF** (photosynthesis directly) |
| Crop water stress | **ECOSTRESS** evapotranspiration, **SMAP** root-zone moisture |
| Cloud-free crop mapping in the tropics | **Sentinel-1** SAR (Brazil safrinha, Argentina) |
| South America production | **CONAB** and **IBGE** (Brazil), **Bolsa de Cereales de Buenos Aires** and **Rosario** (Argentina) |
| Demand side for price models | USDA FAS export sales (weekly, Thursdays), NOPA crush (monthly), CFTC Commitments of Traders (Fridays) |

## Aggregation recipe (gridded to county)

1. Reproject the crop mask (CDL, previous year) to the weather grid; compute the
   soybean area fraction per grid cell.
2. For each county polygon, weight grid cells by intersected area x soybean fraction.
3. Compute daily tmax, tmin, precipitation from hourly data in **local** time.
4. Keep hourly temperatures if available: degree days from hourly data are more
   accurate than the single-sine approximation used here.
