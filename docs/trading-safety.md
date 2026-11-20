Superseded by VISION.md

# Trading safety: one line

Wave 1.5 slice W15-1. The owner and every agent can always tell, in one line, whether an
agent can trade right now and what is stopping it. No owner click can create a second
financial operation. Lonora has no Stop control (owner amendment 1 to VISION.md); the
owner's brake is the pause of an agent or of one piece of its work.

Nothing here changes what the financial boundary admits. The single executor
(`lonora_trading.execution`) still re-reads the grant and unresolved operations at the
moment of sending.

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
| `unresolved_operations` | live `submitted`/`ambiguous` journal rows on readable accounts (a market-bound agent: its own market), with the scoped block `new_risk_on_this_symbol_or_ticket` and whether this agent sent it |

`state` is the one line, chosen in this order: `no_trading` (the agent never trades),
`agent_paused`, `uncertain` (unresolved operations), then `ask_me` or `on_its_own`.
`params` carry the values the line needs (time, symbol, the grant's account, count).

The line speaks only for the accounts the agent acts on: its bound account, its signed
grants when it trades on its own, otherwise every account it may ask to trade on. An
uncertain operation on another account does not change the line of an agent that trades
on its own on account A; the sheet still lists it, with its account named.

The line and every sheet label come from one shared table in
`packages/core/src/trading-readiness.ts` (English and Arabic, tickers and times isolated
with U+2068/U+2069 so they keep their order in Arabic text). Example: "Trades on its own ·
XAUUSD · until you stop it" / «يتداول باستقلال · XAUUSD · حتى توقفه».

## Header safety pill

Every agent thread header shows the line as a pill (Web `SafetyPill`, Mobile
`components/safety-pill.tsx` under the thread title). Tapping it opens a sheet with:
the ladder level, the signed grants and operations awaiting broker confirmation (never
resent; new risk on that market is held, exits stay allowed). No ids, codes or JSON are
shown; account names appear only when several accounts are involved, and then on every
grant and operation.

Web reads `GET /agents/{id}/state` through the shared request layer, which coalesces the
pill's and the background-status strip's concurrent reads of the same path into one
request per refresh. Mobile polls it once per thread screen (`lib/agent-live-state.ts`,
every 15 seconds while focused and active) and passes the result to both the pill and the
strip.

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

## An approval covers one exact request

Without a grant, the executor decides by the agent's trading mode, read under the
authority lock at send (`require_operation_permission`). Full sends on its own. Ask sends
a risk-reducing request (`admission.risk_reducing` on the fresh ticket), and a request
that adds risk only with the owner's approval of that exact operation: an approved Trade
Approval of the same Run whose request has the same `operation_id` and the same
`trade_fingerprint` (`require_exact_approval`). A request that adds risk without such an
approval is refused with `trade_approval_required`, and nothing is sent.

The same exact request repeated in another call of the same Run answers from the card
already raised for it (`reviewed_approval`, newest first): it waits on that card while it
is pending, uses the owner's approval when it is approved or its operation reached the
broker, and returns the owner's rejection until the owner writes again in that
conversation. A result that never reached the broker, or a rejection the owner has spoken
after, asks again.

## A changed ticket is never overwritten

One stale-target check in the executor (`final_admission`, under the account send lock)
covers every close or modify an agent sends: in Full and in Ask, with a card, under a
grant or with neither. At send the broker's current ticket must be exactly as the agent
read it (`material_state`: the ticket without its P&L and operation tag), compared with
two records of that read: the ticket the trade tool captured before sending
(`expected_target`, from `management_snapshot`), and, for a request an approved Trade
Approval of the same Run covers, the ticket that card captured when it was raised
(`approved_targets`). A ticket that changed since (the owner moved a stop or closed part
of it), one the broker no longer shows, or no record of what was read, refuses the request
with `broker_state_changed`, and nothing is sent: an owner's intervention is never
overwritten, not even with an approved card. The trade tool makes the same comparison for
an approved card before the request is reserved, with the same code. A paused agent's exit
is checked the same way and goes through on an unchanged ticket (4.7). The owner's own
orders from the Trading page carry no read of the ticket and are not checked.

## Owner text for boundary codes

The shared financial-boundary table (`packages/core/src/financial-boundary.ts`) holds the
boundary's codes in English and Arabic. Web `userError`, Mobile
`errorText`, and both approval cards resolve codes through it first.

## Verification

- `tests/test_trading_readiness.py`: no grant, Ask me, signed grant, ambiguous and
  submitted operations with their scoped block, a paused and a market-bound agent, the
  owner-only live state and the presentation-only import guard.
- `tests/web/trading-readiness.test.ts` (tsx): every state's line in both languages and
  label key parity.
- `tests/check_trading_mode.py`: in Ask, new risk is sent only as the exact request of an
  approved card of this Run. The stale-target check at the door: an unread or changed
  ticket is not sent in Ask, in Full, under an approved card (against the card's own
  capture) and on a grant's path; a paused agent's exit on an unchanged ticket is sent,
  and so is the owner's own Trading-page change. `tests/check_trade_approvals.py`: one
  card per exact request, reused while it waits, after approval and right after a refusal,
  and a new one after the owner writes again.
- Playwright `tests/web/safety-truth.spec.mjs`: a close retried after a simulated timeout
  and a double-clicked close each produce exactly one journal row and one operation id;
  the pill and sheet. `tests/mobile/safety-pill.spec.mjs`: the
  native pill and sheet in Arabic and English.
