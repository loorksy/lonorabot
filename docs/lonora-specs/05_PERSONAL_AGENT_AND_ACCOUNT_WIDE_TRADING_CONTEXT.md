PROJECT: Lonora (`loorksy/lonorabot`)

IMPORTANT:
- Implement, do not stop at an architecture report.
- Inspect the current repository before changing code. Do not assume conceptual names in this prompt already exist.
- Reuse existing Lonora primitives. Do not build a parallel runtime, event bus, broker ledger, or trading executor.
- Preserve Trading ON/OFF, Emergency Stop, ownership checks, authorization, risk controls, exact broker symbols, idempotency, journal, locking, and reconciliation.
- Never fabricate unavailable market, account, order-flow, execution, correlation, or performance data. Mark unavailable data as unavailable.
- Keep existing global model routing; do not introduce per-Agent provider/model selection.
- Keep Arabic-first/RTL compatibility.
- Do not mention paid API/token/key requirements.
- Work on a dedicated branch and add focused tests.


# 05 — Default Personal Agent and Account-Wide Trading Context

## Objective
Add exactly one default Personal Agent for the owner. It has account-wide/all-market visibility, while user-created trading Agents remain specialized to one trading account + one exact broker symbol.

The Personal Agent is not a manager hierarchy or second trading engine. It is the owner's default broad-scope Agent.

## Inspect first
The current repo already has Agent trading bindings including `trading_account_id` and `trading_symbol`. Inspect the actual binding enforcement and preserve it for specialized Agents.

Do not fake all-market scope with a wildcard if that breaks current binding invariants. Use an explicit clean representation compatible with the codebase.

## Personal Agent
Required behavior:
- automatically exists for every owner
- stable server-side identity independent of display name
- idempotent bootstrap; never duplicate on retry/restart
- can inspect every trading account owned by the owner
- can discover every exact broker symbol available through those accounts
- can analyze any requested market
- can compare markets
- can inspect account-wide balance/equity/margin/positions/orders/history/exposure
- receives account-level broker events
- acts as fallback when no specialized Agent exists for a requested symbol

All-market visibility does NOT imply unrestricted execution.

Separate:
- visibility
- recommendation
- execution authority
- Super Bot autonomy

All broker mutation still passes current server-side financial controls.

## Specialized Agents
User-created trading Agents remain:
- bound to one account
- bound to one exact broker symbol
- unable to silently expand scope through collaboration
- owners of their own symbol-specific watches/goals/theses

Selecting the symbol during Agent creation remains the normal specialist flow.

## Context loading
Do not inject all accounts/symbols into every model turn.

Use task-relevant retrieval:
- one-symbol question → load that symbol
- comparison → load requested symbols
- best-opportunity request → lightweight scan/shortlist, then deep analysis
- portfolio question → load account-wide exposure

## Account-level event ownership
Primary conversational owner: Personal Agent.

Examples:
- manual/external position opened or closed
- manual SL/TP change
- manual pending-order change
- account margin/equity warning
- broker/account connectivity state

Do not let multiple specialized Agents send duplicate account-level notifications.

Symbol-specific events created by a specialist remain with that specialist.

## Specialist discovery
The Personal Agent may consult specialized Agents for an exact symbol through the collaboration system.

Discovery must use structured binding/capability data, not display-name matching.

If no specialist exists, Personal Agent analyzes directly.
Do not auto-create a specialist without owner request.

## Multiple specialists
If multiple Agents are bound to the same symbol, they may all exist.
Do not wake them all by default; participant selection belongs to Collaboration Session logic.

## Super Bot
- Specialist + Super Bot → remains single-symbol/account scoped.
- Personal Agent + Super Bot → may search across authorized accounts/markets, but only inside the explicit owner authorization/risk envelope.

All-market visibility must not silently expand autonomous execution scope.

## UI
Personal Agent appears as the default/top-level Agent.
Specialized Agents show their symbol/account naturally.
Keep UI simple; do not expose internal architecture.

## Tests
Cover:
- exactly one Personal Agent per owner
- idempotent bootstrap
- identity survives rename
- specialist remains exact-symbol bound
- Personal Agent can inspect multiple exact broker symbols
- visibility does not grant execution
- account-level event routes once to Personal Agent
- specialist symbol event remains specialist-owned
- no-specialist fallback
- specialist discovery uses metadata, not name parsing
- restart/client reconnect does not duplicate Personal Agent

## Definition of done
Every owner has one stable Personal Agent with account-wide/all-market visibility; user-created trading Agents remain exact-symbol specialists; account-level events have one clear owner; specialists can still collaborate; financial authority is unchanged.
