# Account management through one existing execution boundary

An owner may sign one immutable account delegation without first authoring a
Trading Goal. This extends the existing financial executor, device verification,
account serialization and journal; it creates no second execution or risk engine.

## Explicit full management (v2)

The owner selects an account and reviews automatic management once. The new
`management_mode=full` proposal is signed as envelope schema version2; it can
leave volume, position count, activity, equity-floor and expiry limits unset.
No large numeric sentinel represents unlimited permission. The nullable expiry
is persisted through migration0030. Optional explicit limits remain enforced.
There is no product-imposed monetary loss ceiling when none is selected.

The Personal Agent may receive explicit `symbol_scope=account` for all exact
broker instruments on that one account. Specialists retain their immutable
selected symbol; account-wide scope is rejected for them. Actual instruments,
lot steps, market prices and supported actions are checked at execution time.
The simple review includes management of manually opened positions. Arbitrary
code still cannot access broker credentials or bypass the typed executor.

Activation atomically creates one existing durable Task and its work Run. Signed
proof replay cannot create another kickoff. It inspects actual state and may
create/reuse watches, choose trades and manage positions without per-order
approval. The task is bound to this exact grant; replacement or revocation cannot
silently let stale kickoff work spend a newer grant. Revocation, replacement and
device removal cancel the corresponding Task using the existing lifecycle. An activation is not an
entry signal or proof a broker is ready. Global Trading ON/OFF and Emergency Stop
remain authoritative and are never silently switched by activation.

Full management leaves stop/target choices to the Agent, including changes to
existing stops; broker validity and fresh target comparison still apply. Losing
funds is possible. No hardcoded lot or loss amount is chosen for the owner.
The ordinary advanced bounded setup remains available. Web and Mobile share the
same proposal and signature verification; no new financial runtime exists.

## Existing bounded grants (v1)

New permissions are OFF by absence. Proposals remain unsigned until an enrolled
passkey verifies the exact immutable envelope, current owner session, relying
party and user verification. A proposal expires after ten minutes; the separately
signed delegation expires within thirty days. Scope expansion requires a fresh
proposal/signature. Replacement revokes the previous active Agent/account grant.
Revocation and device revocation take effect at the next authoritative boundary;
replaying a consumed signature cannot revive a revoked permission.

The envelope names one owned account, its conversation and Agent, exact broker
symbols/actions, maximum order and aggregate symbol volume, current/future
position slots, pending-order slots, lifetime execution count, entry equity floor,
expiry and explicit permission to manage externally opened positions. Specialists
retain their immutable exact-symbol binding; Personal Agent visibility does not
itself authorize a symbol. Broker-discovered symbols are checked before proposal.

Each execution revalidates signature state, expiry, device, ownership, current
broker snapshot and envelope limits inside the existing serialized financial
boundary. Global Trading ON/OFF, Emergency Stop, risk/preflight, execution quality,
manual intervention, idempotency, durable journal and reconciliation still apply.
Submitted, ambiguous, confirmed, owner-resolved and broker-rejected submitted
attempts consume the lifetime budget. Known pre-submission failures and released
reservations do not. An unresolved operation blocks new risk on its market or
ticket for every admission path, and risk-reducing actions stay admissible within
the grant (see `financial-execution-recovery.md`); nothing produces a blind resend.

Management requires a fresh material target snapshot and rejects owner changes
between observation and submission. Manual-origin positions need explicit signed
permission. Bounded-mode autonomous management cannot remove or widen an existing stop; explicit full-management mode permits discretionary stop decisions.
Provisional voice input and its descendants cannot spend standing authority;
exact immutable approve/reject confirmation remains available through the existing
financial approval path. Read-only voice work is unaffected.

## Grant limits and accounting

Broker contracts retain optional sourced tick economics and contract metadata. The
read-only [market-entry sizing estimate](broker-position-sizing.md) uses exact account
money units and an explicit stop; it grants no permission. Signed per-trade monetary
ceilings and daily monetary loss fields are **not part of the signed envelope**: such
envelope fields remain rejected, not silently interpreted as protection. Monetary
limits are instead owner policy enforced at the execution boundary for every path (see
"Monetary risk limits" below). Volume limits, an equity floor and a required stop
cannot guarantee a maximum loss. Grant summaries from the owner routes and the live
Agent projection carry the account's `money_limits` (configured limits, or none), and
the Web and Mobile review show them, or "No money limit set", before signing (see
`trading-safety.md`). No authorization was activated on a production account while
implementing or testing this capability.

The compact Web/Mobile bot settings reuse existing account/market selectors and
passkey enrollment/signing. The advanced bounded form requires explicit limits;
the full-management review explicitly grants discretionary choices without
product-set numerical quotas. No pair or permission is preselected for an unbound Personal Agent.
Current authoritative grant summaries enter the existing live Agent projection;
the badge is presentation, never permission.

## Verification

`tests/check_account_authority.py` uses disposable PostgreSQL, genuine WebAuthn
signatures and the simulation adapter. It covers exact forex/metal/index/crypto
symbols; market/pending/management commands; concurrency and budgets; real
approval fallback; global controls; provisional voice; expiry, revoked devices,
tampering, stale material targets, uncertain execution and no duplicate resend.
`tests/web/account-authority.spec.mjs` exercises the actual Web review/sign/revoke
flow with a virtual WebAuthn authenticator and EN/AR layouts. Shared client tests
reject optimistic activation, wrong returned scope/limits, cancelled proof and
expired signing. Native hardware verification remains separate.

## Owner restrictions

A restriction (`ln_trading_restrictions`, migration 0034) narrows what the single
execution boundary admits; it never grants anything. It names one owned account,
optionally one agent (otherwise every agent) and one exact broker symbol (otherwise
every symbol), an action class, `valid_from`/`valid_until` (open-ended when unset),
its source (`owner_ui`, `owner_message` with the owner's message id, or `agent`),
reason, creator and `revoked_at`.

The symbol is stored in the broker's spelling. When the broker's symbol catalog can be
read it must list the symbol (a case-only difference is resolved), otherwise creation
fails with `symbol_not_found` or `symbol_ambiguous` so the agent or owner corrects it: a
restriction on a spelling the broker does not use would never match a trade. Only when
the catalog cannot be read (broker unavailable, failed or empty listing) is the symbol
kept as given and recorded with `symbol_verified: false`, visible in listings and the
permission frame, because recording an owner's narrowing must not wait for the broker.
Matching ignores letter case only. The action classes:

- `no_new_entries`: no market or pending entry and no pending-entry edit
  (`modify_order`). Managing, closing and cancelling continue. This is "keep
  watching gold, but stop opening new positions today".
- `no_risk_increase`: only risk-reducing requests (`admission.risk_reducing` against
  the fresh broker target and open positions): closes, cancellations of orders that
  would only add exposure, tighter or added stops. Closing one leg of a hedged book is
  an exit and stays allowed even though it changes the net direction on the symbol;
  cancelling a protective order (an opposite-side order whose fill would offset open
  positions on its symbol) removes protection and is blocked like removing a stop.
- `all_mutations`: no broker mutation in the scope, reduce-only included.

Restrictions govern agent-originated operations: every leased path (signed account
grant, exact approval, Goal step). Owner-manual operations through `POST
/trading/execute` are exempt unless the owner sets `applies_to_owner_manual` on an
all-agent restriction; agents cannot set it. The flag binds the owner's own trades, so
it is rejected together with `agent_id` (a restriction scoped to one agent never
restricts the owner), and matching applies it only to all-agent restrictions. Shadow
execution never reaches a broker and is unaffected.

The decisive check runs in the executor's `before_send` callback, under the per-account
send lock, in the same transaction that moves the reserved journal row to `submitted`.
It holds a transaction-scoped shared advisory lock that restriction creation takes
exclusively, so an operation either committed its send authorization before the
restriction existed (it is then an already submitted operation, reported separately and
never reversed) or it sees the restriction. Approved or queued work is therefore decided
when it is sent, not when it was queued. A fail-fast copy of the check runs before the
reservation. A blocked send is journaled as `failed` with `send_state: not_sent` and
`details.admission_block.restriction`.

Expiry needs no scheduler: every read compares `valid_from`/`valid_until` with the
database clock (`database_now`), which also stamps an immediate restriction's start, so
clock skew between hosts cannot make a visible restriction look scheduled. Restrictions are listed as `scheduled`, `active`, `expired` or `revoked`
with `ended_at`; creation and revocation emit durable `trading.restriction_created` and
`trading.restriction_revoked` events for "what happened" summaries.

Agents use `trade_restriction_create` (narrowing only, no financial authority needed,
idempotent on crash replay, records the owner's message when the run answers one) and
`trade_restriction_list`. The current restrictions that apply to an agent are rendered
in its per-turn financial permission frame. That frame is part of the system role, so it
carries structured fields only (scope, class, state, window, `recorded_by`); the owner's
own reason is shown bounded as `owner_reason`, while a reason an agent wrote —
model-authored text that may carry injected content — never enters another Agent's
system prompt and is read through `trade_restriction_list` output instead. A market-bound specialist records and sees
restrictions on its own account and market only (`all_symbols` is refused with
`agent_trading_symbol_mismatch`). The Personal Agent and flexible agents can scope one
to any owned account and symbol. Like every market tool, an omitted symbol is filled
with the agent's home symbol when the restriction is on its home account; such an agent
passes `all_symbols: true` for every symbol on that account (rejected together with
`symbol`).

`all_mutations` created by the owner also blocks risk-reducing exits (closes,
cancellations, tighter stops and Goal protective steps). A restriction an agent recorded
never blocks a risk-reducing exit, whatever its class: its scope and reason are
model-authored and may come from injected content, so it can stop new risk but never
trap a position, including an exit the owner approves. An agent may impose
`all_mutations` on another agent or on all agents only in a run that answers the owner's
message (source `owner_message`); otherwise creation fails with
`restriction_all_mutations_requires_owner_message`, and on its own initiative an agent
may freeze only itself. A restriction an agent records for another agent or for all
agents is time-boxed: it needs `valid_until` (`restriction_valid_until_required`) at
most 31 days after it starts (`restriction_window_too_long`); open-ended or longer
restrictions on other agents are the owner's own.

Blocked operations carry tool recovery metadata that matches the boundary:
`trading_restriction_active` is `permission_denied` / `respect_scope` (never route around
it through another symbol or account), and every `risk_*` code is `risk_limit_blocked` /
`inspect_risk_assessment` (resize or protect to fit the limit, reduce exposure, or wait
for the owner). No agent tool lifts a restriction. The owner
lists, creates and lifts them through `GET/POST /trading/restrictions` and `POST
/trading/restrictions/{id}/revoke` (owner session with CSRF, or bearer token). The Web
and Mobile header safety sheet lists the restrictions that apply to an agent, read only
(`trading-safety.md`); lifting one from a card arrives with owner action cards (W15-2),
until then the API is the owner's lift surface.

## Monetary risk limits

`ExecutionPolicy.risk` (`PUT /trading/accounts/{id}/execution-policy`, owner only)
holds optional limits in the broker account currency, which the owner names in
`risk.currency`; a policy whose currency differs from the account blocks new risk
instead of converting. Unset means not enforced; no money amount is chosen for the
owner. The agent sees configured and unset limits in its permission frame and through
`trade_restriction_list`; the owner reads the current book against them with `GET
/trading/accounts/{id}/risk-status`.

- `max_trade_risk` / `max_trade_risk_equity_percent`: modeled loss at the stop-loss of
  a new entry, a pending-entry edit or a risk-increasing position edit. A stop-loss is
  required while a per-trade limit is set. The stricter of amount and percent of
  current equity applies.
- `max_open_risk` / `max_open_risk_equity_percent`: modeled loss at the stops across
  open positions (from the current closing price), pending orders (from their price),
  `submitted`/`ambiguous` entries and confirmed entries still awaiting state
  verification whose ticket is not yet visible, plus the request itself. An unresolved
  stop or pending-order edit counts as the worse of current and requested state.
  Anything without a stop makes open risk unbounded, which blocks new risk.
- `max_daily_loss`: broker-reported realized P&L since local midnight in
  `trading_day_timezone`, plus the current floating profit of open positions. Deals
  count conservatively: trade deals (`DEAL_TYPE_BUY`, `DEAL_TYPE_SELL`) with profit,
  commission and swap; balance, credit and bonus cash flows not at all; every other
  type (correction, charge, commission-only, interest, dividend, tax, cancelled deals
  and unknown or missing types) only when its total is negative, so a non-trading
  credit never offsets a trading loss. Reaching the limit blocks new risk. A full
  history page (1,000 deals) or unreadable history blocks rather than counting as zero
  loss.
- `min_free_margin`: new entries need at least this current free margin (the new
  order's own margin is not modeled).

Risk at a stop reuses the sizing arithmetic (`broker-position-sizing.md`): whole ticks
between reference price and stop rounded up, times the broker's per-lot loss tick value,
times volume. Limits apply to every admission path, owner-manual included, like the rest
of `ExecutionPolicy`. They are evaluated in `before_send` under the account send lock
with fresh broker economics; the evaluation is stored as `details.risk_assessment` on
admitted and blocked operations. Risk-reducing requests are never blocked by a limit,
so closing, cancelling and tightening remain possible when a position exceeds a newly
set ceiling. Estimates exclude gaps, slippage, future commission, swap and new-order
margin: a stop-loss limit is not a guaranteed maximum loss. Limits are owner policy,
not part of the signed grant envelope; signed monetary envelope fields remain rejected.

## Verification of restrictions and limits

`tests/test_trading_restrictions.py` covers action classes, scope and owner exemption
(including the owner flag on agent-scoped restrictions), expiry, symbol verification,
the home-symbol default and `all_symbols`, permission-frame rendering, recovery
classification, per-trade risk from stop distance and tick value, open risk with
pending and unresolved operations, daily loss with conservative deal types and history
coverage, free margin and currency mismatch. `tests/check_trading_restrictions.py` (disposable
PostgreSQL, simulation broker, real owner API and approval path) covers the agent tool
sourcing the owner's message, a mis-spelled symbol refused while the catalog is
readable, a flexible agent with a home market recording an every-symbol restriction,
an agent-initiated `all_mutations` restriction on other agents refused, a restriction
created while approved work waits for the send lock and enforced at the send boundary, reduce-only under restriction, owner-flagged restrictions and owner-only
lifting, expiry, every monetary limit, and an operation interrupted after submission
that stays traceable and is recovered without resend while the restriction blocks new
orders.

## Remaining monetary limitations

Daily loss is what broker history reports at the decision: a deal the broker has not yet
synchronized is not counted, so a position closed by its stop moments earlier can
briefly drop out of both floating and realized P&L. Positions carried over from an
earlier day count with their full current floating P&L (no opening-equity baseline is
recorded), which over-counts a loss that began earlier and lets an earlier floating gain
offset today's losses. Open risk values every symbol with its current quote's loss tick
value; a stale quote outside market hours is used as reported. Estimated stop fills
cannot guarantee a maximum loss, and the new order's own margin is not modeled.

## New acceptance

`test_full_account_management.py` verifies explicit mode/version, absent versus
null legacy limits, exact symbols and optional limits. The signed simulation
fixture `check_full_account_management.py` exercises the actual owner API,
WebAuthn, durable kickoff Task/Run, repeat signatures, grant replacement, stale
work, four symbol classes, market/pending orders, manual position management,
partial close, discretionary stops, broker constraints, Emergency Stop and
revocation. The older authority fixture signs the genuinely original v1 envelope
shape so migration cannot reinterpret its absent fields. Browser checks exercise
actual EN/AR owner surfaces, full and bounded signatures, and unchanged global
controls; Expo Web checks are not physical native acceptance.

The complete trading mandate remains open: this scope does not implement generic
strategy equivalence, native background calls or new Goal-bound execution policy.
Goal-linked Runs retain the existing Goal/device authorization boundary. A fresh
ordinary Task can use the account grant. No production grant or trade is activated
by migration, deployment or these tests.
