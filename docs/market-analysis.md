# Market analysis evidence tools

Mandate section 5 leaves market interpretation to the model. These tools give it
better evidence without choosing for it: every result is measured from broker data,
configured sources or the IANA time-zone database, carries timestamps, and reports
`execution_authorized: false` or no authority at all. None of them produces a
signal, a ranking or an order. They live in `packages/tools/src/lonora_tools/market_analysis.py`
(policy domain `market`); the pure logic is in `lonora_market.snapshot`,
`lonora_market.sessions` and `lonora_market.economic_calendar`.

| Tool | Effect | Purpose |
| --- | --- | --- |
| `market_snapshot` | read-only | Compact multi-timeframe facts for one instrument on one account |
| `market_sessions` | read-only | DST-correct FX session clock plus broker trading hours |
| `economic_calendar_read` | read-only | Events from the owner's configured calendar sources |
| `market_candles_to_workspace` | workspace write, receipt-replayed | Bars as CSV in the Agent's analytical workspace |

## market_snapshot

One call reads the quote, the requested timeframes (default `15m`, `1h`, `4h`,
`1d`; up to six; `bars` per timeframe, default 200), daily bars for levels and the
last weekly bars, concurrently and each with its own timeout. A timeframe that
cannot be read is reported as `available: false` with its error code; the rest of
the snapshot still returns.

Closed-bar rigor: the time at which the reads begin is the cutoff. Only a bar whose
close time is at or before the cutoff is closed; a bar that closed while the read was
in flight may hold partial data and is treated as forming. The forming bar is shown
separately (`forming_bar`, `unfinished: true`) and excluded from every calculation.
Invalid series (mixed symbol, duplicate or out-of-order timestamps, future bars) are
unavailable; a stale series is still measured but marked `freshness: stale`, and the
top-level `data_freshness` is the worst state of the quote and every timeframe.

Per timeframe, from closed bars only:

- `trend`: least-squares regression change over `trend_bars` (default 20), in price
  and in ATR units, labelled `rising` / `falling` (at least one ATR) or `flat`.
- `structure`: the last two confirmed swing highs and lows from the strict
  `market_structure` rule (`lonora_market.structure.swing_points`, `swing_bars` each
  side; equal extrema rejected; each swing has its confirmation time), labelled
  e.g. `higher_high_higher_low`, plus whether the last close is beyond the last swing.
- `range`: high/low over the same window, size in ATR units and the last close's
  position inside it.
- `volatility`: ATR (simple mean of true range, the existing `chart_indicator`
  method), its mid-rank percentile over up to 100 prior ATR values and a regime label
  (`low` at or below the 20th percentile, `high` at or above the 80th,
  `insufficient_history` with fewer than 20 values).
- `rsi`: the existing Wilder RSI.

Levels: previous day and previous week high/low (last closed `1d`/`1w` bars on the
broker's day boundary) and the current day's high/low so far, each with the distance
from the reference price in price and in daily-ATR units. The reference is the quote
mid when a quote is available (`stale_quote_mid` if it is stale), otherwise the last
closed close of the first available timeframe.

## market_sessions

Sydney 07:00-16:00, Tokyo 09:00-18:00, London 08:00-17:00 and New York 08:00-17:00
local time, Monday to Friday, converted through `zoneinfo` on each actual date, so
every centre follows its own daylight-saving rules (for example the five-hour
London/New York overlap between the US and UK clock changes in March, and Sydney's
April change). The FX week is Sunday 17:00 to Friday 17:00 New York time; session
windows are clipped to it, so Monday Sydney opens with the FX week. The result
lists each session's state, opening or closing time and minutes to it, the active
sessions and overlaps, the next overlaps and the FX market state (`fx_weekend` when
closed). An optional `at` evaluates another instant within 31 days. Holidays and
liquidity are not modelled, and the conventional hours are not exchange schedules.

With `account_id` and `symbol` (a fixed-market agent gets its binding by default) the
tool adds `broker_trading_hours`. Adapters may implement the optional
`TradingHoursReader` protocol (`lonora_adapter_kit.broker`). MetaApi reports trade
sessions per weekday on the broker server clock; the adapter measures the server's
UTC offset from a broker-timestamped quote (`brokerTime` against `time`, rounded to
15 minutes) and reads the free synchronized specification before any paid RPC. The
simulation broker returns sessions only when the imported snapshot has a
`trading_hours` entry. When the adapter has no such capability, the symbol has no
reported sessions, or the server offset cannot be measured, the state is `unknown`
with a reason; it is never guessed. The session clock never depends on the broker: a
disabled, unreachable or failing broker connection, an unreadable symbol catalog or a
timeout also leaves only `broker_trading_hours` unknown with the error code as reason
(an unexpected exception is `broker_hours_failed`, logged by type only). Only an
unknown or ambiguous symbol (`symbol_not_found`, `symbol_ambiguous`) fails the call,
so the model can correct it. Sessions are evaluated over a horizon of more than a
week; when the active session runs past it (an instrument trading 24/7, such as
crypto CFDs on many MT5 brokers) the reported week has no gap, so `closes_at` and
`minutes_to_close` are `null` with `continuous: true` and reason
`no_close_within_horizon` rather than an invented close at the horizon edge.
`SYMBOL_TRADE_MODE_DISABLED` and `CLOSEONLY` are surfaced as a trade restriction.

## economic_calendar_read

Reads every enabled `economic_calendar` integration of the owner through the existing
`EconomicCalendarAdapter` (public URL validation, no redirects), each source with its
own timeout. Filters: currencies, impact labels (as the source names them) and a
window of `hours_back` / `hours_ahead`. Events are time-ordered and carry
`minutes_from_now`, a status (`upcoming`, `released`, `due_without_actual`) and the
`integration_id` that a calendar watch can reference. With no configured source the
result is `configured: false` with `economic_calendar_not_configured`. A failing source
is reported per source as `unavailable` with a reason and without its URL, while the
other sources' events are still returned: the adapter turns transport failures into
`calendar_source_unavailable`, timeouts into `calendar_source_timeout` and a non-JSON
body, a non-list payload, a malformed event or a body over 2 MiB (streamed and refused
at the cap, before it is buffered or parsed) into `calendar_response_invalid`; any
other exception from a source is `calendar_source_failed` and is logged by type only,
because exception text can carry the configured URL. Calendar watches and the owner
calendar route get the same codes from the adapter. Events whose timestamps carry no
time zone are rejected and counted rather than guessed.

## market_candles_to_workspace

Writes the bars of one symbol and timeframe (latest `limit` bars, optional `start` /
`end`, closed bars only unless `include_forming`) as CSV into the Agent's analytical
workspace at the given revision (`workspace_inspect` gives it) and returns only the
path, row counts, time range, freshness and the new revision for `workspace_execute`.
Columns: `time, close_time, open, high, low, close, volume, closed`, with exact
broker decimals. The default path is `market/<symbol>_<timeframe>.csv`.

`RunWorkspaceAccess.write_generated` performs the write with the existing workspace
rules: the current owned Agent, Thread, Run and lease fence; paused Agents and
helper (subagent) runs refused; path validation; per-file, total-size and file-count
quotas; optimistic revision. No database lock is held while the broker is read. The
receipt identity is the request (account, symbol, timeframe, window, path and base
revision), not the bytes, so a replay of an interrupted call returns the original
write even if new bars have arrived since.

## Readable and executable scope of fixed-market agents

Mandate section 4 separates the default instrument (focus), readable scope and
executable scope; correction 1 opens reading. A fixed-market (bound) agent reads every
owned account and symbol like any other agent: every read-only tool in the registry
(`guard_market_tool(..., read=tool.read_only)` in `lonora_tools/market_binding.py`),
plus `market_candles_to_workspace`, which copies market reads into the agent's own
workspace. `list_accounts`, `account_read`, `account_history` and `account_activity`
are no longer filtered to the bound account or symbol; trade records, decision
history, opportunity reads, performance reads, position sizing and
relationship reads drop their binding checks. `list_accounts` marks each account and
`account_read` each position and order with `in_execution_scope`, and the catalog and
account reads carry an `execution_scope` note, so the agent still sees what it may
execute. Omitted arguments default to the focus account and symbol, but the focus
symbol is never copied onto another explicitly named account (`fill_bound_fields`),
so `trade_record_history(account_id=<other>)` returns that account's records for every
symbol, as for flexible agents. `BINDING_POLICY` reads: focus pair; reading is open;
executing follows your grant.

Mutations keep the binding (`agent_trading_account_mismatch` and
`agent_trading_symbol_mismatch` now come only from mutation paths). Charts, watches
(including watches on a foreign position ticket), goals, decisions, opportunity
records, relationship records and every financial `trade_` tool
keep the bound account and symbol through the guard and their own handler checks.
The financial executor independently asserts the binding of every leased request,
and preflight requires a position's or order's symbol to equal the request's symbol,
so reading another account or symbol cannot widen execution. Signed grants,
approvals, restrictions and risk limits are untouched.

## Instrument resolution

The owner says «الذهب», the model says `XAUUSD`, and the account lists `XAUUSDm`. Which
symbol a request names is decided by code, never by the model:

- `lonora_market.instruments.catalogue_matches` is the one rule. A request is a broker
  symbol, a canonical code or a common name (`lonora_contracts.instrument_names`, English
  and Arabic). A catalogue name matches when it is the exact name, the same name in
  another letter case, or the code wrapped in a broker affix: a separator on either
  side (`XAUUSD.r`, `XAUUSD.pro`, `XAUUSD#`, `XAUUSD_i`, `#XAUUSD`, `m.XAUUSD`) or a short
  lowercase suffix (`XAUUSDm`, `XAUUSDc`). Letters or digits that extend the code
  (`XAUUSDT`, `US300`) are another instrument. A broker that lists gold as `GOLD` is
  found by the English word when the code is not listed. There is no per-broker list.
- `contradicts` is the broker's own check: a match whose reported base and quote
  currency are not the pair the code names is dropped.
- **Reads** (`market_instrument`, `market_quote`, `market_candles`, `market_snapshot`,
  `market_structure`, `market_sessions`, `market_candles_to_workspace`,
  `chart_indicator`) call `lonora_tools.symbols.read_symbol`. They use the account's
  symbol and state it: the result carries `symbol_resolution` (`requested`, `symbol`)
  whenever the request named it another way. When several contracts match, the read
  uses the first (shortest name) and lists the others with a note that an order needs
  the owner's choice. The catalogue is cached per account (per broker adapter, five
  minutes) and read again on a miss.
- **Orders, closes, sizing, grants and restrictions** (`trade_execute`,
  `trade_close_positions`, `market_position_size`, grant drafts,
  `trade_restriction_create`) name a symbol the catalogue lists exactly, letter case
  aside (`order_symbol`, `canonical_broker_symbol`, `restriction_symbol`). They are
  never resolved to another symbol, so resolution cannot move an order to another
  instrument or widen what a grant, a restriction or an agent's binding covers: those
  still compare the exact symbol.
- **A request that is not listed** fails with `symbol_not_found` (no match, or exactly
  one: `next` names it and tells the model to repeat the call) or `symbol_ambiguous`
  (several contracts: `next` tells the model to ask the owner which, in plain words).
  The result carries `requested_symbol`, `candidates` (each with the broker's
  description, category path, contract size, currencies and minimum volume),
  `similar_symbols` when nothing matches, and `next`. `tool_dispatch` forwards these
  beside the code, so the model continues in the same run.
- The approval card's data carries `contracts` (the broker's specification of each
  requested symbol, read when the card is made) and the grant card's facts carry
  `grant.contracts` (kept in the account's state when the grant is drafted). Both are
  additive fields.
- MetaApi: a 404 from a symbol read on a connected account is `symbol_not_found`; only
  a message about the account itself is `broker_account_not_found`.

`tests/test_instrument_resolution.py`, `tests/test_market_symbol_resolution.py`,
`tests/test_metaapi_unknown_symbol.py` and the behaviour case
`tests/check_gold_journey.py` («كيف وضع الذهب؟» on a suffixed account) cover it.

## Verification

- `tests/test_market_sessions.py`: winter, summer and both March/October gaps between
  US and UK clock changes, the spring-forward weekend, Sydney's April change and
  clipping to the FX week, Friday close and Sunday open boundaries in EST and EDT,
  broker hours on a GMT+2 server clock (rollover, weekend, overnight and 24-hour
  windows, unknown offset, close-only), a 24/7 instrument with no invented close,
  MetaApi specification normalization, and the tool keeping its session clock when
  the broker is disabled, unreachable, times out or raises (symbol errors still fail).
- `tests/test_economic_calendar_read.py`: per-source isolation of raw transport,
  decode and unexpected errors from injected sources, and the real adapter (mock HTTP
  transport) mapping connection refused, read timeout, HTML, non-list, malformed-event
  and HTTP 503 responses to codes beside a healthy source's events.
- `tests/test_market_snapshot.py`: forming-bar exclusion and the read cutoff, swing
  structure labels, mid-rank volatility regime, unavailable/invalid/stale/future
  inputs, level distances, quote fallback, CSV encoding and calendar filtering.
- `tests/check_market_analysis.py` (disposable PostgreSQL, real registry, simulation
  broker): all four tools end to end, receipt replay after the bars changed, revision
  conflict, path rejection, file-count quota, observe-only refusal, and a bound gold
  agent reading a related symbol and account-wide exposure while trades, closes,
  watches, charts, sizing and central execution stay refused for that symbol with no
  journal row created; the bound agent's default `market_sessions` call still returns
  the clock with broker hours `unknown` / `broker_disabled` while its broker is
  disabled.
- `tests/check_agent_binding.py`, `tests/check_market_structure.py` and
  `tests/check_flexible_agents.py` were updated from "cross-symbol reads are refused" to
  "related reads on the bound account are allowed; cross-account reads and every
  mutation remain refused", and in Wave 1.5 (W15-7) to "every owned account and symbol
  is readable; every mutation stays on the pair" (`tests/check_agent_binding.py`,
  `tests/check_market_analysis.py`, `tests/check_position_sizing.py`,
  `tests/check_decision_replay.py`, `tests/test_proactive_wakes.py`).

## Limitations

- Session hours are conventions; no holiday calendar, early closes or liquidity data.
- The broker clock offset is measured at call time; a broker DST change inside the
  evaluated horizon is not modelled.
- No live MetaApi account was available, so the MetaApi trading-hours path is
  verified only through its normalizer with SDK-shaped fixtures.
- There is still no built-in calendar provider or news feed; calendar evidence is
  only what the owner's configured sources return.
- The workspace bridge writes one symbol/timeframe per call and at most the latest
  1000 broker bars.
