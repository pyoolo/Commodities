# Physical-and-Logistics

The physical layer: where the commodity actually is, and what it costs to move or store it.

## Scope
- **Freight**: Baltic Dry Index, dirty/clean tanker rates (Worldscale), LNG shipping rates
- **Storage economics**: when contango pays for a storage trade, tank and warehouse capacity, floating storage
- **Refining**: configurations, yields, crack economics, turnaround seasonality
- **Trade flows**: exporter/importer maps, tracking via Kpler and Vortexa
- **Chokepoints**: Hormuz, Suez, Panama, Bosphorus, Malacca
- **Quality & grades**: API gravity, sulphur content, LME warrant brands, wheat protein specs
- **Contracts**: Incoterms (FOB, CIF, DES), assay, demurrage

## Why it matters for quant work
Location and quality spreads, storage capacity and freight costs are the real economic constraints
that anchor the futures curve. A carry signal without a storage-capacity check will eventually
trade a spread that physically cannot converge.
