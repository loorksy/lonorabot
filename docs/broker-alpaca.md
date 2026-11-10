# Alpaca paper broker

`lonora_adapters.brokers.alpaca.AlpacaBroker` is the second real broker adapter behind
the single executor (`ExecutionService.execute`, see `financial-execution-recovery.md`).
It trades **Alpaca paper accounts only**. Live trading is refused and needs a later owner
decision.

## Hosts and credentials

- Trading: `https://paper-api.alpaca.markets` (v2). Market data: `https://data.alpaca.markets`
  (stocks v2 on the free `iex` feed, crypto v1beta3 `us`). Both are module constants, and
  `request()` refuses any other base with `broker_endpoint_forbidden`. A connection has no
  field that can name a host. Live keys fail on the paper host with
  `broker_credentials_rejected`.
- The connection form takes the server's own fields, from `GET /api/trading/providers`:
  `key_id` and `secret_key`. Both are write-only. `POST /api/trading/connections`
  `{"provider": "alpaca", "key_id", "secret_key", "enabled"}` first reads `GET /v2/account`
  (read-only). It then stores the account number as `account_id` and the observed
  identity (`broker` Alpaca, `platform` alpaca, `server` the paper host), and saves both
  keys as one encrypted secret (`credentials_secret`). As with MetaApi, a connection
  without a verified identity is refused (`VERIFIED_PROVIDERS`).
- The keys live only in the HTTP client's headers. Diagnostics go through
  `safe_exception_message` with both keys redacted. No result, event or log line carries
  them; `tests/check_alpaca_paper.py` scans for this.

## Reads

| Contract | Alpaca source | Notes |
| --- | --- | --- |
| `account()` | `GET /v2/account` | `balance` = cash, `margin` = initial margin, `free_margin` = equity − margin; `trade_allowed` false when blocked or not ACTIVE |
| `symbols()` / `instruments()` | `GET /v2/assets?status=active` for `us_equity` and `crypto`, tradable only, cached 10 min | Stocks: tick 0.01, whole shares (step 1). Crypto: `price_increment`, `min_order_size`, `min_trade_increment`. `volume_max` is a sizing bound (1,000,000), not an Alpaca limit |
| `quote()` | latest quote (`bp`/`ap`/`t`) | An empty side or a crossed book is `quote_unavailable`. Tick value = tick size per unit, claimed only when the quote currency is the account currency (so not for `ETH/BTC`) |
| `candles()` | bars, newest first from a bounded look-back, then time-ordered | Every Lonora timeframe maps to Alpaca's (`1m`→`1Min`, `1h`→`1Hour`, `1mn`→`1Month`) |
| `stream_quotes()` / `stream_candles()` | REST polling (2 s / 10 s) | Only reported values; nothing is interpolated |
| `positions()` | `GET /v2/positions` | Netting by asset: `id` = `asset_id`. Crypto symbols are restored to the catalog spelling (`BTCUSD` → `BTC/USD`) |
| `orders()` | `GET /v2/orders?status=open` | Exit legs are not pending orders, they are protection (below). A queued market order is valued at the current side price, never at zero. A full page (500) is refused as `broker_snapshot_limit` |
| `history()` | `GET /v2/account/activities/FILL` | |

**Protection.** Alpaca has no stop-loss or take-profit on a position. Protection is exit
orders that hold the position's quantity: the legs a bracket or OTO entry leaves
(`group_role` `stop_loss` / `take_profit`), or an OCO, stop or limit Lonora placed (client
order id prefix `LNP_`). These are never pending entries. A position reads them as its
`stop_loss` / `take_profit` only when one group on the exit side covers the whole quantity;
anything else reads as unprotected.

## Execution

`execute()` does every lookup before the boundary: the asset class, the market clock for
stock market orders and closes, the target position or order, the protection leg. Then it
awaits `before_send` and sends **one** HTTP mutation:

| Action | Mutation |
| --- | --- |
| `buy` / `sell` | `POST /v2/orders` market (stocks `day`, crypto `gtc`). With SL and/or TP: `bracket` / `oto` (stocks only) |
| `buy_limit` / `sell_limit` / `buy_stop` / `sell_stop` | `POST /v2/orders` limit / stop, `gtc` |
| `close_position` | `DELETE /v2/positions/{asset_id}[?qty=]`: closes only what is held, so it can never reverse a position. A protected position closes in steps (below) |
| `modify_position` | On an unprotected position, `POST /v2/orders`: an OCO for both levels, otherwise a stop or a limit, `gtc`, for the whole quantity, tagged `LNP_`. On a protected one, `PATCH /v2/orders/{leg}` with the new `stop_price` or `limit_price` of one leg (a replaced `LNP_` order keeps the prefix) |
| `modify_order` | `PATCH /v2/orders/{id}` with the new `limit_price` / `stop_price` (Alpaca answers with a new order id) |
| `cancel_order` | `DELETE /v2/orders/{id}` |

The `client_order_id` is `broker_operation_tag(operation_id)`, the same tag MetaApi carries.

Refused before the boundary, so recorded `failed` / `not_sent`:

- a stock market order or close while the market is closed: `market_closed`;
- crypto stop orders: `broker_order_type_unsupported`;
- SL/TP on crypto: `broker_protection_unsupported`;
- SL/TP edits on a pending order: `broker_protection_edit_unsupported`;
- clearing protection (it widens risk): `broker_protection_clear_unsupported`;
- protection split over several groups, or covering part of the position: `broker_protection_split`;
- adding the missing level to a group that has only the other one: `broker_protection_leg_missing`;
- changing both legs in one request: `broker_protection_edit_one_at_a_time`;
- an unknown symbol, position or order: `symbol_not_found`, `position_not_found`, `order_not_found`.

Received answers after the boundary:

- **2xx.** `confirmed`; an order whose status is `rejected` is `failed` with `broker_order_rejected`.
- **401.** `broker_credentials_rejected`.
- **404.** `order_not_found` or `position_not_found`.
- **429.** `broker_rate_limited`.
- **Other 4xx** (buying power, held quantity, shorting, validation). `broker_request_rejected`; the details keep `http_status`, the broker's `broker_code` and the redacted description.
- **5xx, a duplicate `client_order_id`, a transport error, a timeout or an unreadable receipt.** `ambiguous` (`broker_result_ambiguous`). It is never resent.

## Closing a protected position

Exits stay possible whatever protects the position, including with Trading OFF, under
restrictions and during the owner's Stop. Alpaca refuses a close while exit orders hold the
quantity, so a protected close is **one executor operation in ordered steps**, after the
single `before_send`. Every step is recorded in `details.protection.steps` under the same
operation id:

1. Cancel every exit order of the position (`DELETE /v2/orders/{id}`).
2. Wait, bounded (20 × 0.5 s), until none of them is in the open book. Alpaca releases a
   cancelled order's quantity asynchronously (`pending_cancel`).
3. Close (`DELETE /v2/positions/{asset_id}[?qty=]`) and follow the closing order until it is
   final (same bound).
4. Re-arm protection for what is still held, at the same levels (`LNP_` orders). A smaller
   position keeps protection only for what it holds, taken from the last group first.

When a step does not go through:

- **A cancel refused, or the quantity never released.** The close is **not sent**. Any
  group no longer intact is cleared and placed again. Result `failed`,
  `broker_protection_cancel_failed`.
- **The close refused, or the closing order rejected.** Protection is restored for the whole
  position. Result `failed` with the broker's code.
- **The close outcome unknown** (lost response, server fault, or the order still working at
  the bound). Nothing is re-armed: an exit order with nothing held would open the opposite
  position. Result `ambiguous`.

`details.protection.restored` is false whenever the position may be left less protected
than before. The executor then raises the owner's **`position_unprotected`** item
(`action_required`, one per operation, `lonora_trading/protection.py`). The gateway's
verification step reads the broker each pass and withdraws the item only when that
position is protected again or closed. The operation settling does not clear it.
`details.protection.attention` also marks a failed close after cancelled legs, as a record.

## Recovery

`reconcile()` looks entries up with `GET /v2/orders:by_client_order_id`. A rejected order,
or a market order that ended without any fill, is `failed`. Any other found order is
`confirmed` with `reconciled: true`. A missing order stays `ambiguous`
(`execution_not_observed`). Closes, edits and cancels carry no client id at Alpaca, so
they return `execution_not_observed` / `mutation_evidence_required` and the executor's
target-state recovery settles them (`lonora_trading/target_state.py`). The exception is
protection added to an unprotected position: it is found by its own `LNP_` client order id.

## Verification

- `tests/test_alpaca_adapter.py`: the adapter against the local fake server
  (`tests/alpaca_fake.py`, payloads in `tests/fixtures/alpaca`).
- `tests/test_alpaca_protection.py`: covers each protected-close path (full, partial
  re-arm, delayed release, release never comes, refused cancel, refused close, protection
  not restorable, unknown close outcome), added stop and OCO protection, and widening edits
  refused.
- `tests/test_broker_contract.py`: one contract against simulation, MetaApi fixtures and Alpaca.
- `tests/check_alpaca_paper.py`: the API and executor journey on PostgreSQL. With Trading
  OFF it covers a protected partial and full close, an unprotected exit, an added stop, and
  `position_unprotected` raised and then withdrawn.

The fixtures follow the payload shapes of Alpaca's official `alpaca-py` SDK models. They
were not recorded from a live account, because this environment cannot reach Alpaca.

## Live paper check (not yet run)

It needs the hosts `paper-api.alpaca.markets` and `data.alpaca.markets` allowed (HTTPS),
plus one paper key pair (key id and secret) from the owner's Alpaca paper dashboard,
entered through the connection form. It confirms against the real service:

- crypto symbol spelling on positions and fills;
- `group_role` on bracket legs;
- that `DELETE /v2/positions/{id}` is refused while legs hold the quantity, and how long a
  cancel takes to release it;
- whether cancelling one OCO leg cancels its sibling;
- whether a replaced order keeps its `client_order_id`;
- the 403/422 error bodies.
