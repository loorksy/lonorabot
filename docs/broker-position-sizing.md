# Broker-unit position sizing

`market_position_size` is a read-only calculation using the existing owner-scoped
broker reader. It fetches one account, exact instrument and current quote. The
account ID and broker-native currency must match; cent account labels remain cent
units. A specialist retains its immutable symbol/account binding. There is no
default instrument, currency, volume or stop.

The pinned MetaApi SDK 29.1.1 calculates position P&L as price distance divided by
`tickSize`, multiplied by `profitTickValue` or `lossTickValue`, then volume. Its
terminal-state equity calculation adds this P&L directly to the account balance.
These tick values therefore use account money per one lot and one tick.
`accountCurrencyExchangeRate` is separate reporting metadata; multiplying it into
tick values would convert the same money again. `contractSize`, `baseCurrency`
and `profitCurrency` are retained as metadata and never substitute for tick money.
See SDK `metaapi/terminal_state.py`, `_update_position_profits` and account equity
updates, and `metaapi/models.py` account/price contracts.

The shared broker normalizer preserves optional economics for streaming,
synchronized and RPC quotes. Missing, non-finite or non-positive optional tick
values remain unavailable without breaking valid bid/ask prices or chart data.
Legacy simulation records remain valid; a simulation must explicitly supply
economics and their basis to enable money sizing. No migration is required.

Sizing requires fresh account and quote evidence under the existing health policy.
For a market buy the modeled entry is ask; for a sell it is bid. Stop validity uses
the closing side of the spread and existing broker point/stops-level constraints.
Entry-to-stop ticks round adversely. Decimal arithmetic rounds volume down on the
actual lattice anchored at `volume_min`, respecting minimum, maximum and step.
The resulting estimate must not exceed the requested budget at the assumed stop
fill. Too little budget for minimum volume is a clear failure, not a larger trade.

The result includes exact account/currency/symbol, tick basis, source timestamps,
instrument, entry, stop, volume and estimated loss. It explicitly grants no
execution authority. It excludes gaps, slippage, commission, swap and margin
validation: it is not a guaranteed maximum loss. Current quote economics are not
historical backtest costs or a valuation of the entire portfolio.

The existing immutable proposal, approval or signed authority, final preflight,
controls, journal and independent broker verification still govern every actual
order. This calculation does not silently add signed per-trade monetary ceilings
or daily-loss enforcement to older volume-only account grants. Complete monetary
authorization additionally needs signed currency-qualified limits and final
revaluation. Daily-loss policy requires complete account-wide deal coverage,
cost/cash-flow semantics and an explicit day boundary; current bounded history
cannot prove those facts. Those requirements remain open in the matrix.

Verification uses deterministic numerical tests and disposable PostgreSQL with
the simulation adapter, never live funds. The integration check verifies real
tool admission, symbol isolation, currency mismatch, absent economics and no
financial journal/approval effects. Production acceptance may inspect current
read-only broker metadata; an estimate must not be described as a submitted order.
