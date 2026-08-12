# Derivatives-Pricing

Pricing and calibration for commodity derivatives.

## Scope
- **Futures & forwards**: cost of carry, convenience yield extraction from the curve
- **Options**: Black-76 on futures, American options on physicals, Asian options (very common in commodities, since settlement is usually against a monthly average)
- **Spread options**: Margrabe, Kirk's approximation, Bachelier for spreads that can go negative
- **Swaps**: fixed-for-floating on a monthly index average
- **Term-structure models**: Gibson-Schwartz, Schwartz-Smith two-factor, seasonal extensions
- **Volatility**: implied surfaces, the Samuelson effect (vol rises approaching expiry), seasonal vol in gas and power

## Notes specific to commodities
- Use **Black-76**, not Black-Scholes — the underlying is a futures contract.
- Many payoffs are **average-price (Asian)**; do not price them as European.
- Spreads and some outright prices can be **negative** → normal (Bachelier) rather than lognormal dynamics.
- Power and gas need **spikes and mean reversion**, not GBM.
