Superseded by VISION.md

# Trading safety: one line

Wave 1.5 slice W15-1. The owner and every agent can always tell, in one line, whether an
agent can trade right now and what is stopping it. No owner click can create a second
financial operation. Lonora has no Stop control (owner amendment 1 to VISION.md); the
owner's brake is the pause of an agent or of one piece of its work.

Nothing here changes what the financial boundary admits. The single executor
(`lonora_trading.execution`) still re-reads the grant, money limits and unresolved
operations at the moment of sending.

## Trading readiness (presentation only)

`lonora_db.trading_readiness.trading_readiness` builds one bounded block from the records
the executor reads. It is returned as `trading_readiness` by the owner's live state
endpoint (`GET /agents/{id}/state`, `agent_live_state(..., readiness=True)`), and never by
the model's routing frame or the voice context: the permission frame already carries the
same facts every turn. Enforcement code must never import it
(`tests/test_trading_readiness.py` checks the trading and tools packages).

| Field | Source |
| --- | --- |
| `level` | `permission_state` effective level: `analysis` (No trading), `supervised` (Ask me), `autonomous` (On its own, signed) |
| `grants` | active, verified `AccountAuthority` rows: account, markets, actions, manual positions, until |
| `money_limits` | each readable account's `ExecutionPolicy.risk`, configured or not |
| `unresolved_operations` | live `submitted`/`ambiguous` journal rows on readable accounts (a market-bound agent: its own market), with the scoped block `new_risk_on_this_symbol_or_ticket` and whether this agent sent it |

`state` is the one line, chosen in this order: `no_trading` (the agent never trades),
`agent_paused`, `uncertain` (unresolved operations), then `ask_me` or `on_its_own`.
`params` carry the values the line needs (time, symbol, the grant's account, count,
whether a money limit is set).

The line speaks only for the accounts the agent acts on: its bound account, its signed
grants when it trades on its own, otherwise every account it may ask to trade on. An
uncertain operation on another account does not change the line of an agent that trades
on its own on account A; the sheet still lists it, with its account named.

The line and every sheet label come from one shared table in
`packages/core/src/trading-readiness.ts` (English and Arabic, tickers and times isolated
with U+2068/U+2069 so they keep their order in Arabic text). Examples: "Trades on its own · XAUUSD ·
until you stop it · Daily loss 200.00 USD" / «يتداول باستقلال · XAUUSD · حتى توقفه ·
الخسارة اليومية 200.00 USD» when the grant's account has a daily loss limit, and "… · No
money limit set" when it has no money limit at all.

## Header safety pill

Every agent thread header shows the line as a pill (Web `SafetyPill`, Mobile
`components/safety-pill.tsx` under the thread title). Tapping it opens a sheet with:
the ladder level and signed grants, money limits per
account ("No money limit set" when none) and operations awaiting broker confirmation
(never resent; new risk on that market is held, exits stay allowed). No ids, codes or
JSON are shown; account names appear only when several accounts are involved, and then
on every grant, money limit and operation.

Web reads `GET /agents/{id}/state` through the shared request layer, which coalesces the
pill's and the background-status strip's concurrent reads of the same path into one
request per refresh. Mobile polls it once per thread screen (`lib/agent-live-state.ts`,
every 15 seconds while focused and active) and passes the result to both the pill and the
strip.

## Grant summaries report money limits

`authority_summary` (owner account-authority routes) and the live state's
`account_authorities` carry the account's `money_limits` in place of the former
`monetary_stop_risk: "unavailable"`. The grant review on Web and Mobile shows them, or "No
money limit set". The grant copy no longer claims daily loss limits do not exist.

## Owner close and cancel keep one operation id

The Web Positions and Orders buttons (`useTicketAction`, `lib/held-operation.ts`) mint one
`operation_id` per ticket action, store it in `sessionStorage` before sending and reuse it
for every retry, double click and reload. The executor answers a repeated id from its
journal (`idempotency`), so a timeout followed by a retry never sends a second close. The
id stays held while the journal row is `reserved`, `submitted` or `ambiguous`, and is
released as soon as the row settles (`confirmed`, `failed` or `resolved`, the contract's
`TERMINAL_STATUSES`). The settled outcome stays on the row and the next click is a new
operation: a position or order that is still open (an uncertain close the owner attested
as not executed, a target changed by another action, a failed close) can be closed again,
and one that is already gone fails the executor's preflight against fresh broker state, so
nothing reaches the broker twice. While the identity is held the button reads "Check close
result" / "Check cancel result", and the row shows the journal state ("Outcome uncertain —
it will not be sent again").

## Owner text for boundary codes

The shared financial-boundary table (`packages/core/src/financial-boundary.ts`) holds
every `risk_*` code, in English and Arabic. Web `userError`, Mobile
`errorText`, and both approval cards resolve codes through it first.

## Verification

- `tests/test_trading_readiness.py`: no grant, Ask me, signed grant with and without a
  money limit, ambiguous and submitted operations with their
  scoped block, a paused and a market-bound agent, the owner-only live state and grant
  money limits, and the presentation-only import guard.
- `tests/web/trading-readiness.test.ts` (tsx): every state's line in both languages, the
  money-limit line, label key parity, and Web/Mobile parity for the `risk_*` codes.
- Playwright `tests/web/safety-truth.spec.mjs`: a close retried after a simulated timeout
  and a double-clicked close each produce exactly one journal row and one operation id;
  the pill and sheet. `tests/mobile/safety-pill.spec.mjs`: the
  native pill and sheet in Arabic and English.
