# Risk-Management

Measuring and controlling exposure on commodity positions.

## Scope
- **VaR and Expected Shortfall**: historical, parametric, Monte Carlo
- **Stress testing**: 2008, 2014-16 oil crash, April 2020 negative WTI, 2021-22 European gas, LME nickel March 2022
- **Hedging**: optimal hedge ratio (OLS and dynamic), minimum-variance hedging, cross-hedging with a proxy commodity
- **Basis risk** — the main reason hedges fail in practice
- **Margining**: initial and variation margin, SPAN, margin-call simulation and liquidity buffers
- **Exposure limits**: per commodity, per sector, per maturity bucket

## Reminders
- Fat tails mean Gaussian VaR understates risk. Use ES and stress scenarios alongside it.
- A futures hedge that is right on price can still bankrupt you on cash flow if margin calls arrive before the physical settles.
- Correlations across commodity sectors break down exactly when you need them.
