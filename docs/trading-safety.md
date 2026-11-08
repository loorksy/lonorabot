# Trading safety: one line, one brake

Wave 1.5 slice W15-1. The owner and every agent can always tell, in one line, whether an
agent can trade right now and what is stopping it. Stopping and resuming new trading is
one tap on Web and Mobile. No owner click can create a second financial operation.

Nothing here changes what the financial boundary admits. The single executor
(`lonora_trading.execution`) still re-reads the grant, global trading, restrictions,
money limits and unresolved operations at the moment of sending.

## One brake: Stop new trading / Resume

Global trading has the existing two flags (`TradingControl.enabled`,
`TradingControl.emergency_stop`, `PUT /trading/controls`, owner session only). The API
contract is unchanged; the clients now offer one control:

- **Stop new trading** sends `{enabled: false, emergency_stop: true}`. It stops new risk
  for every agent and the owner's manual orders. Exits stay allowed: closing positions,
  cancelling orders that only add exposure and tightening stops (see
  `financial-execution-recovery.md`). It is the former Emergency Stop, renamed because it
  closes nothing; its critical attention item now reads "New trading stopped" and is
  withdrawn on Resume.
- **Resume trading** sends `{enabled: true, emergency_stop: false}` in one call, one tap,
  no passkey. It widens no authority: each agent still trades only within its ladder
  level, signed grant, pauses and money limits.

Trading OFF and the Emergency Stop flag are both "stopped" everywhere. Trading starts
stopped until the owner starts it: while nobody has changed it (`changed_by: "default"`)
the header sheet says "Trading has not been started yet." and offers **Start trading**
(the same payload as Resume); after the owner stops it, it offers Resume. The Trading
page card reads `GET /trading/controls`, which does not say who changed it, so it keeps
Resume. `save_controls` writes and emits only on a real change, so "stopped since" stays
true when Stop is pressed twice.

Web shows the control on the Trading page and in the header safety sheet; Mobile shows it
in the header safety sheet. Both send the same payloads.

### Brakes come before approval cards

An agent at *Ask me*, or a trade outside an *On its own* grant, asks the owner with an
approval card. While Stop new trading or a pause holds new risk, a card for a new entry
could only fail after the owner's tap. `trade_execute` therefore checks the brakes before
it raises a card (`refuse_braked_entries` in `lonora_tools.trade`) and returns the
boundary's own code instead (`trading_disabled`, `emergency_stop`,
`trading_restriction_active`), so the agent tells the owner what is holding it and offers
the Resume or Lift card. Only actions that can never reduce risk are checked there
(`admission.may_reduce_risk`): a close, a cancel or a stop change is still asked and is
decided by the executor against the fresh broker target. The executor repeats every
check at the moment of sending; this only refuses earlier.

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
| `global_trading` | `running` or `stopped`, `since` (the settings row's change time), `changed_by` (`owner`, or `default` when never changed) |
| `restrictions` | active and scheduled restrictions that apply to the agent: class, account, symbol, scope, window, source (`owner_ui`, `owner_message`, `agent`). No reason text: an agent's words are model prose |
| `money_limits` | each readable account's `ExecutionPolicy.risk`, configured or not |
| `unresolved_operations` | live `submitted`/`ambiguous` journal rows on readable accounts (a market-bound agent: its own market), with the scoped block `new_risk_on_this_symbol_or_ticket` and whether this agent sent it |
| `exits_allowed` | false only under an active `all_mutations` freeze on an account the agent acts on (account-wide, or for a market-bound agent, on its market) |

`state` is the one line, chosen in this order: `no_trading` (the agent never trades),
`agent_paused`, `stopped`, `paused` (strongest active restriction first), `uncertain`
(unresolved operations), then `ask_me` or `on_its_own`. `params` carry the values the line
needs (time, symbol, class, account of the pause, count, whether a money limit is set).

The line speaks only for the accounts the agent acts on: its bound account, its signed
grants when it trades on its own, otherwise every account it may ask to trade on. A pause
or an uncertain operation on another account does not turn an agent that trades on its own
on account A into "Paused"; the sheet still lists it, with its account named. With several
accounts the "Paused" line names the account too ("Paused (Simulation · 2): no new
entries · until you lift it").

The stopped line follows `exits_allowed`: "New trading stopped · exits allowed" /
«التداول الجديد متوقف · الخروج متاح» only when no freeze is in force, otherwise "New trading
stopped · exits frozen too" / «التداول الجديد متوقف · والخروج مجمّد أيضًا», matching the
sheet's freeze alert.

The line and every sheet label come from one shared table in
`packages/core/src/trading-readiness.ts` (English and Arabic, tickers and times isolated
with U+2068/U+2069 so they keep their order in Arabic text). Examples: "New trading stopped
· exits allowed" / «التداول الجديد متوقف · الخروج متاح», "Trades on its own · XAUUSD ·
until you stop it · Daily loss 200.00 USD" / «يتداول باستقلال · XAUUSD · حتى توقفه ·
الخسارة اليومية 200.00 USD» when the grant's account has a daily loss limit, and "… · No
money limit set" when it has no money limit at all.

## Header safety pill

Every agent thread header shows the line as a pill (Web `SafetyPill`, Mobile
`components/safety-pill.tsx` under the thread title). Tapping it opens a sheet with:
Stop new trading / Resume, the ladder level and signed grants, active pauses (each with
a one-tap **Lift pause** for the owner, `POST /trading/restrictions/{id}/revoke`; no agent
can lift one), money limits per
account ("No money limit set" when none) and operations awaiting broker confirmation
(never resent; new risk on that market is held, exits stay allowed). No ids, codes or
JSON are shown; account names appear only when several accounts are involved, and then
on every grant, pause, money limit and operation. A pause an agent set names that agent
on both clients ("Set by an agent · <name>").

Web reads `GET /agents/{id}/state` through the shared request layer, which coalesces the
pill's and the background-status strip's concurrent reads of the same path into one
request per refresh. Mobile polls it once per thread screen (`lib/agent-live-state.ts`,
every 15 seconds while focused and active) and passes the result to both the pill and the
strip.

## Permission frame

The agent's financial permission frame (`lonora_agent/context/permissions.py`) adds
`global_trading: {state, since}`, re-read every turn, and one rule: while it is stopped,
new risk is blocked for every agent and exits stay allowed, so the agent attempts no
entry, says so in one line and offers the owner Resume in the conversation header.

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

`trading_disabled` and `emergency_stop` join the shared financial-boundary table
(`packages/core/src/financial-boundary.ts`) with every `risk_*` code and
`trading_restriction_active`, in English and Arabic. Web `userError`, Mobile
`errorText`, and both approval cards resolve codes through it first.

## Verification

- `tests/test_trading_readiness.py`: no grant, Ask me, signed grant with and without a
  money limit, globally stopped (and `since` not moving on a repeated Stop), active and
  scheduled restrictions and a freeze, ambiguous and submitted operations with their
  scoped block, a paused and a market-bound agent, the owner-only live state and grant
  money limits, and the presentation-only import guard.
- `tests/test_agent_permissions_enforcement.py`: `global_trading` is re-read every turn
  and the stopped rule is present.
- `tests/web/trading-readiness.test.ts` (tsx): every state's line in both languages, the
  money-limit line, label key parity, and Web/Mobile parity for the brake and `risk_*`
  codes and the Stop/Resume payloads.
- Playwright `tests/web/safety-truth.spec.mjs`: a close retried after a simulated timeout
  and a double-clicked close each produce exactly one journal row and one operation id;
  the pill, sheet, Stop and one-call Resume. `tests/mobile/safety-pill.spec.mjs`: the
  native pill and sheet in Arabic and English.
