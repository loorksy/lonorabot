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

**Protection.** Alpaca has no stop-loss or take-profit on a position. A bracket or OTO
entry leaves exit legs (`group_role` `stop_loss` / `take_profit`) as open orders. A
position reads one leg per role as its `stop_loss` / `take_profit`, and only when exactly
one leg on the exit side covers the whole quantity. Anything else reads as unprotected.

## Execution

`execute()` does every lookup before the boundary: the asset class, the market clock for
stock market orders and closes, the target position or order, the protection leg. Then it
awaits `before_send` and sends **one** HTTP mutation:

| Action | Mutation |
| --- | --- |
| `buy` / `sell` | `POST /v2/orders` market (stocks `day`, crypto `gtc`). With SL and/or TP: `bracket` / `oto` (stocks only) |
| `buy_limit` / `sell_limit` / `buy_stop` / `sell_stop` | `POST /v2/orders` limit / stop, `gtc` |
| `close_position` | `DELETE /v2/positions/{asset_id}[?qty=]`: closes only what is held, so it can never reverse a position |
| `modify_position` | `PATCH /v2/orders/{leg}` with the new `stop_price` or `limit_price` of one leg |
| `modify_order` | `PATCH /v2/orders/{id}` with the new `limit_price` / `stop_price` (Alpaca answers with a new order id) |
| `cancel_order` | `DELETE /v2/orders/{id}` |

The `client_order_id` is `broker_operation_tag(operation_id)`, the same tag MetaApi carries.

Refused before the boundary, so recorded `failed` / `not_sent`:

- a stock market order or close while the market is closed: `market_closed`;
- crypto stop orders: `broker_order_type_unsupported`;
- SL/TP on crypto: `broker_protection_unsupported`;
- SL/TP edits on a pending order: `broker_protection_edit_unsupported`;
- clearing protection: `broker_protection_clear_unsupported`;
- protecting a position that has no leg: `broker_protection_leg_missing`;
- changing both legs in one request: `broker_protection_edit_one_at_a_time`;
- an unknown symbol, position or order: `symbol_not_found`, `position_not_found`, `order_not_found`.

Received answers after the boundary:

- **2xx.** `confirmed`; an order whose status is `rejected` is `failed` with `broker_order_rejected`.
- **401.** `broker_credentials_rejected`.
- **404.** `order_not_found` or `position_not_found`.
- **429.** `broker_rate_limited`.
- **Other 4xx** (buying power, held quantity, shorting, validation). `broker_request_rejected`; the details keep `http_status`, the broker's `broker_code` and the redacted description.
- **5xx, a duplicate `client_order_id`, a transport error, a timeout or an unreadable receipt.** `ambiguous` (`broker_result_ambiguous`). It is never resent.

## Recovery

`reconcile()` looks entries up with `GET /v2/orders:by_client_order_id`. A rejected order,
or a market order that ended without any fill, is `failed`. Any other found order is
`confirmed` with `reconciled: true`. A missing order stays `ambiguous`
(`execution_not_observed`). Closes, edits and cancels carry no client id at Alpaca, so
they return `execution_not_observed` / `mutation_evidence_required` and the executor's
target-state recovery settles them (`lonora_trading/target_state.py`).

## Verification

- `tests/test_alpaca_adapter.py`: the adapter against the local fake server
  (`tests/alpaca_fake.py`, payloads in `tests/fixtures/alpaca`).
- `tests/test_broker_contract.py`: one contract against simulation, MetaApi fixtures and Alpaca.
- `tests/check_alpaca_paper.py`: the API and executor journey on PostgreSQL.

The fixtures follow the payload shapes of Alpaca's official `alpaca-py` SDK models. They
were not recorded from a live account, because this environment cannot reach Alpaca.

## Live paper check (not yet run)

It needs the hosts `paper-api.alpaca.markets` and `data.alpaca.markets` allowed (HTTPS),
plus one paper key pair (key id and secret) from the owner's Alpaca paper dashboard,
entered through the connection form. It confirms against the real service:

- crypto symbol spelling on positions and fills;
- `group_role` on bracket legs;
- that `DELETE /v2/positions/{id}` is refused while legs hold the quantity;
- the 403/422 error bodies.
