# Crypto door adapter — specification

**Status: Proposed (decision D33 in `docs/cloud/DECISIONS.md`).** Building it needs the owner's go-ahead and the small
mandate clause in §17. Until it ships, crypto venues are traded from the workspace under VISION §9.5.

---

## 1. Goal

Crypto exchanges become first-class venues of the execution door, exactly like MetaApi accounts: every order is
journaled, idempotent, reconciled with the exchange and never resent when its outcome is unknown (VISION §6). Agents
trade a connected exchange account through the same tools (`trade_execute`, `trade_close_positions`,
`positions_manage_all`), the same modes (Full/Ask, §4), the same cards (§10.3) and the same `lonora` CLI (§7.3).

VISION §9.5 already foresees this: "Another venue gets a door adapter when one is built."

**Non-goals in the first version** — the adapter contains no code path for any of these, and a test proves it (§12):
withdrawals, deposits, internal transfers between wallets or sub-accounts, conversions, earn/staking, margin
borrowing, options, copy trading, decentralised exchanges and on-chain transactions.

---

## 2. Why the door, not the workspace

| Guarantee (VISION §6) | Workspace trading today (§9.5) | Door adapter |
|---|---|---|
| One execution door | No: scripts call the exchange directly | Yes: `ExecutionService.execute` is the only caller |
| Journal and server-derived operation id | No | Yes, reserved before send |
| Never resend an uncertain order | Depends on the script | Yes: reconcile by client order id |
| Broker truth | Script's own reading | Exchange evidence only |
| Preflight (account, permission, existence, quote age, exchange filters) | No | Yes, at planning and at send |
| Per-account send serialization | No | Yes |
| Exact approval in Ask mode | No | Yes, Trade Approval card with fingerprint |
| Position ownership (§3.3.4) | No | Yes |
| Key never in the workspace (§7.2.3) | No: the key is a workspace secret | Yes: broker-destination secret |

---

## 3. First venues and products

| Order | Venue | Product | Why |
|---|---|---|---|
| 1 | Binance | Spot | The most requested; public testnet for certification |
| 2 | Binance | USDⓈ-M perpetual futures, one-way position mode | Positions, leverage and margin map closely to MT5 CFD semantics; public testnet |
| 3+ | Bybit, OKX, others | Spot, then perpetuals | Each only after passing the certification suite of §12 |

Hedge position mode, coin-margined futures and isolated-margin spot are later decisions (§16).

**Library (decision X1).** Recommended: **CCXT** (MIT) for transport and per-exchange signing, behind Lonora's own
adapter, with mutations never retried by the library, every URL checked against the venue's host allowlist (the way
`configure_sdk_transport` / `validate_sdk_url` guard the MetaApi SDK), and each venue enabled only after certification.
Alternative: one hand-written client per venue (more control, much more work per venue).

---

## 4. Where it fits in the code

| Piece | Change |
|---|---|
| `packages/contracts/src/lonora_contracts/broker.py` | `BrokerConnection.provider`: `Literal["metaapi", "simulation"]` gains `"exchange"`, with `venue` (for example `binance`), `product` (`spot` or `usdm_perp`) and `environment` (`live` or `testnet`). |
| `packages/adapters/src/lonora_adapters/brokers/exchange.py` (new) | `ExchangeBroker`, implementing `lonora_adapter_kit.broker.BrokerAdapter` (`instrument`, `quote`, `account`, `positions`, `orders`, `symbols`, `instruments`, `stream_quotes`, `stream_candles`, `candles`, `history`, `execute(request, before_send)`, `reconcile(operation_id, request, submitted_at=…)`, `close`) and `TradingHoursReader`. |
| `packages/adapters/src/lonora_adapters/brokers/base.py` | `BrokerManager.connect` gains the `"exchange"` branch, like `simulation` and MetaApi. In the API process the existing `RelayedBroker` path is used, so the Gateway alone holds each exchange connection and stream. |
| `packages/core/src/lonora_core/broker_endpoints.py` | Per venue: the hosts the adapter may call, and the trading hosts added to `BROKER_DOMAINS` so the workspace cannot reach them (VISION §7.1.4). Public market-data hosts that never accept credentials may stay reachable, per venue, after certification. |
| Secrets | API key, secret (and passphrase where the venue has one) as broker-destination values (§7.2.3), read only by `BrokerManager` and the connect check. |
| `packages/tools/src/lonora_tools/broker_connect.py` | Connect-from-chat flow for exchanges (§9). |
| `packages/trading/src/lonora_trading/admission.py` | `risk_reducing` learns spot and perpetual semantics (§8). |
| `packages/trading/src/lonora_trading/execution.py` | Unchanged in structure. The door already calls `broker.execute(request, before_send)` after its checks and journal reservation; the adapter calls `before_send` immediately before the mutation, as `MetaApiBroker` does. |
| CLI (`packages/cli/lonora`, `apps/api/src/lonora_api/cli/app.py`) | The order commands of §7.3 (prerequisite E0, §15), with crypto units (§10). |
| Clients | Trade Approval card, Execution Receipt and the account picture show base quantity, quote notional and fees (§11). |

---

## 5. Domain mapping

The contracts are MT5-shaped (`lonora_contracts.account`, `market`, `trading`). The adapter maps the exchange onto them
and adds only what the contracts cannot express.

| Contract | Spot | USDⓈ-M perpetual (one-way) |
|---|---|---|
| `AccountState.currency` | The valuation currency chosen at connect (default USDT) | Margin asset (USDT) |
| `balance` / `equity` | Sum of asset balances valued at current prices | Wallet balance / margin balance |
| `margin` / `free_margin` | 0 / free quote balance | Used margin / available balance |
| `trade_allowed` | Account can trade and the key has trade permission | Same, for futures |
| `Position` | A synthetic holding per non-valuation asset with a non-dust balance; `id` = `spot:<ASSET>`; `volume` = quantity; `open_price` = Lonora's journaled average cost, or null when acquired outside Lonora | The exchange position per symbol; `id` = `perp:<SYMBOL>`; volume, entry price, unrealised PnL |
| `Position.stop_loss` / `take_profit` | From the protective orders Lonora placed for that holding (§6) | From reduce-only conditional orders Lonora placed (§6) |
| `Order` | Open orders; `operation_id` recovered from the client order id | Same, including conditional orders |
| `Instrument` | `tick_size` from the price filter, `volume_step` / `volume_min` / `volume_max` from the quantity filter, `contract_size` = 1, `base_currency`, `profit_currency` = quote | Same, plus leverage brackets |
| `Quote` | Best bid/ask with the exchange's own timestamp | Same |
| `TradingHours` | 24/7, with the venue's announced maintenance | Same |

**Contract additions** (additive, defaults keep MetaApi unchanged): `Instrument.volume_unit: Literal["lots","base"]`,
`Instrument.min_notional`, `Instrument.product`; `TradeResult.details` carries fills and fees; `Position.source`
(`exchange` or `synthetic`).

---

## 6. Actions

| `AuthorityAction` | Spot | Perpetual |
|---|---|---|
| `buy` / `sell` | Market order (sell limited to the holding's free quantity) | Market order |
| `buy_limit` / `sell_limit` | Limit order | Limit order |
| `buy_stop` / `sell_stop` | Stop-limit or stop-market where the venue offers it | Stop-market |
| `close_position` | Market sell of the holding quantity (full or partial) | Reduce-only market order |
| `modify_position` (SL/TP) | Replace the holding's protective orders (OCO where offered) | Replace the reduce-only stop/take-profit orders |
| `cancel_order` | Cancel | Cancel |
| `modify_order` | The venue's amend or cancel-replace call where offered; otherwise two journaled operations, the new order sent only after the cancel is exchange-confirmed | Amend where offered; otherwise as spot |

**Stop loss and take profit at entry.** An entry with `stop_loss`/`take_profit` is one operation for the agent; the
door journals the entry, and only after the exchange confirms the fill places each protective order as its own journaled
child operation with its own client order id. If a protective order is refused, the agent is told at once in its run,
with the position shown as unprotected.

**Leverage and margin mode (perpetuals).** Changing them is a risk-increasing journaled operation through the door
(decision X4), never a hidden side effect of an order.

---

## 7. Safety core, item by item (VISION §6)

1. **One door.** Only `ExecutionService.execute` calls `ExchangeBroker.execute`. The workspace never holds the key and
   cannot reach the venue's trading hosts.
2. **Journal and idempotency.** The operation id is server-derived as today. The adapter sends a **client order id
   derived deterministically from it** (`broker_operation_tag` in `packages/session/src/lonora_session/idempotency.py`,
   the function MetaApi's `clientId` uses), shortened or
   encoded to fit each venue's length and character rules (Binance: up to 36 characters; confirm against current docs
   in certification). Child operations (protective orders, cancel-replace legs) get their own derived ids.
3. **Never resend.** Mutations are never retried, by Lonora or the library. A lost or ambiguous answer is reconciled by
   querying the order **by client order id**. Some venues enforce client id uniqueness only among open orders, so a
   resend after a fill could duplicate: reconciliation, never resubmission, is the guarantee.
4. **Exchange truth.** Confirmed only from the venue's order status, executed quantity and fills (REST answer, order
   query or user-data stream). A missing order is not "not executed" until the venue's query says so after the
   consistency window; otherwise the row stays `ambiguous` and goes to owner settlement (item 8).
5. **Preflight at planning and at send:**
   - account match: the account identity the venue reports (UID or equivalent) equals the connected one;
   - trading allowed: account status and the key's trade permission;
   - existence: the order, holding or position the request targets exists now;
   - quote freshness: `ExecutionPolicy.quote_max_age_seconds` and `account_max_age_seconds` unchanged;
   - exchange filters in place of MT5 stop levels: price tick, quantity step, minimum and maximum quantity, minimum
     notional, price bands; a request that would break one is refused before send with the filter named.
6. **Send serialization** per connected account; the single stale-target door check runs for every close/modify.
7. **Exact approval** unchanged: `operation_id` + `trade_fingerprint` against an approved Trade Approval row; the
   fingerprint covers venue, product, symbol, side, type, quantity, price and protective levels.
8. **Owner settlement** of unknown outcomes through the fixed card, showing the venue's own order query result.
9. **Run integrity** unchanged.
10. **Provenance** unchanged: exchange announcements, websocket payloads and workspace output reach the model as data.

---

## 8. Ownership and risk classification

- **Ownership (§3.3.4).** Perpetual one-way positions follow the netting rule: the agent whose journaled order opened
  the symbol's position from flat owns it. Spot holdings follow the same rule per asset: the agent whose journaled buy
  took the asset from zero (or dust) owns the holding; a holding that existed before connection, or was bought outside
  Lonora, belongs to the owner. Orders belong to the agent whose journaled order placed them.
- **Risk-reducing (§4.0),** added to `risk_reducing` against the exchange's current state: a full or partial sell of a
  spot holding or reduce-only close of a perpetual position; cancelling an order whose fill would add exposure; adding a
  stop to an unprotected holding or position; moving an existing stop strictly toward the market with the take profit
  unchanged. Everything else, including leverage increases and margin-mode changes, is risk-increasing.

---

## 9. Connecting from chat (as VISION §9.2 does for MetaApi)

1. The owner: «اربط حساب باينانس» (connect my Binance).
2. The agent asks for the product (spot or futures) and live or testnet, and shows the broker-destination **Secret
   card** with the fields the venue needs (API key, secret, passphrase if any).
3. The connect check reads, with the new key: account identity, trade permission, whether **withdrawal permission is
   enabled** where the venue reports it, and whether the key is **restricted to an IP**. The agent tells the owner, in
   one message: the account, the balances, and any of: "this key can withdraw: create one without withdrawal",
   "restrict this key to <instance IP>". These are warnings, not refusals (the owner decides).
4. The instance IP comes from the host (self-hosted: the server's address; Lonora Cloud: the fixed IP of D34).
5. Managing from chat: list, disconnect, rotate the key (a new Secret card), enable/disable — like §9.3.
6. Proactive health (§9.4): rejected key, expired key, IP restriction mismatch, lost user-data stream.

---

## 10. CLI (VISION §7.3)

`lonora trade|close|modify|cancel` work on exchange accounts with the same exit codes (0, 10, 20, 30, 77) and `--key`
idempotency. Volume: `--volume` is interpreted in the instrument's `volume_unit` (lots for MetaApi, base quantity for
crypto); `lonora positions|orders` print the unit. **This needs the mandate clause of §17**, because §7.3.2 says
"Volume is in lots". The order commands themselves are not built yet (§15, E0).

---

## 11. What the owner sees

- Trade Approval card: venue and product, quantity in base asset, notional in quote, price, protective levels,
  estimated fee, reason and tolerance.
- Execution Receipt: fills, average price, fees and fee asset, from exchange evidence only.
- Account picture on every wake (§5.4): valuation, holdings and positions with owners, open orders, exposure.
- Morning brief and reports include crypto accounts with the same rules.
- Arabic first, no raw ids or JSON in normal views (§17 of VISION).

---

## 12. Testing and certification

**Certification suite per venue and product, on the venue's testnet, required before a venue is enabled:**
- every action of §6, including partial fills and filter refusals;
- lost answer after send (the harness drops the response): reconciled by client order id, never resent, one order;
- duplicate request with the same `--key`: one operation;
- protective orders after fill; refusal of a protective order reported;
- rate-limit answers (HTTP 429 and venue bans) honoured without resend;
- clock skew beyond the signing window refused cleanly;
- user-data stream drop and resume; Gateway restart mid-operation;
- the adapter's HTTP client refuses any host outside the venue allowlist;
- **no withdrawal/transfer path:** a static test that the adapter references no endpoint outside the allowlisted set
  of read, order and cancel endpoints.

**Safety-core tests** (the core tests of VISION §14.1) extended with an exchange venue next to MetaApi and simulation.
**Acceptance scenario** in the manner of VISION §16 on Binance testnet: connect, a Full agent opens a spot position
with protective orders, an Ask agent's request waits as a card, a dropped answer during a close is reconciled without
resend, the morning brief reports it.

A `certified_venues` list (venue, product, environment, suite version, date) gates which venues the connect flow offers.

---

## 13. Network and hosting

- The adapter talks only to its venue's allowlisted hosts; the venue's trading hosts join `BROKER_DOMAINS` (workspace
  denial, §7.1.4).
- Signed requests need accurate time: the host keeps NTP; the adapter refuses to send when the measured offset exceeds
  the venue's window.
- Exchanges rate-limit by key and by IP; the Gateway owns each connection, so one place counts weights.
- Exchanges restrict access by server location; Lonora Cloud checks each venue against its regions (cloud PLAN §3.9).
- Lonora Cloud gives each customer a fixed IP for key allowlists (D34).

---

## 14. Security

- Keys are broker-destination secrets; never in the workspace, model context, chat, logs or memory (§7.2).
- The connect check warns about withdrawal permission and missing IP restriction; the help centre explains how to
  create a trading-only, IP-restricted key.
- The adapter has no withdrawal, transfer or conversion code (§1, §12).

---

## 15. Delivery stages

| Stage | Content | Done when |
|---|---|---|
| E0 | Prerequisites: the CLI order commands of VISION §7.3 (`trade`, `close`, `modify`, `cancel`) for MetaApi; the contract additions of §5 with MetaApi defaults | CLI orders journaled and verified like tool orders (VISION phase 4 "done when") |
| E1 | Read-only Binance spot: connect from chat, account, holdings, orders, instruments, quotes, candles, streams, history | Account picture correct on testnet and live (read-only key) |
| E2 | Spot orders through the door: market, limit, cancel, reconciliation, ownership, risk classification, cards, receipts | Certification suite green for spot |
| E3 | Protective orders and modify (OCO/stop, cancel-replace) | Suite green including protective cases |
| E4 | USDⓈ-M perpetuals one-way: positions, reduce-only, conditional SL/TP, leverage/margin as door operations | Suite green for perpetuals |
| E5 | More venues through certification | Each venue listed in `certified_venues` |

---

## 16. Decisions for the owner

| ID | Decision | Recommendation |
|---|---|---|
| X1 | Library | CCXT behind Lonora's adapter, per-venue certification |
| X2 | First venue and products | Binance spot, then Binance USDⓈ-M one-way |
| X3 | Hedge position mode | Not in the first version |
| X4 | Leverage and margin mode | Agent-controlled, as risk-increasing door operations |
| X5 | Spot valuation currency | USDT by default, owner may choose another stablecoin |
| X6 | Workspace access to a door venue's public market-data hosts | Allowed per venue when certified credential-free |

---

## 17. Mandate clause needed

A short owner amendment so the mandate matches the adapter:

> **§7.3.2:** "Volume is in lots" becomes "Volume is in the instrument's unit: lots for MetaApi accounts, base-asset
> quantity for crypto venues." **§9.5:** "A crypto venue with a certified door adapter is traded only through the door;
> its trading hosts are added to 7.1.4." **§4.0** gains the spot and perpetual cases of risk reduction in §8 of this
> specification.

---

## 18. Risks

| Risk | Mitigation |
|---|---|
| Duplicate order after a lost answer | Client order id + reconciliation, never resend; dedicated certification case |
| Venue-specific quirks behind a unified library | Certification per venue and product; venue-specific tests |
| Regulatory exposure of crypto trading per market | Counsel review (cloud D20, PLAN §16) |
| Venue restricts the server's region | Region checks (cloud PLAN §3.9) |
| Key with withdrawal permission is stolen | No withdrawal code; warnings; IP restriction; key never in workspace |
