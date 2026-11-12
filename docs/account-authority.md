Superseded by VISION.md

# Account management through one existing execution boundary

An owner may sign one immutable account delegation. This extends the existing financial executor, device verification,
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
By owner decision D1 the simple review excludes positions the owner opened
manually unless the owner switches them on; grants already signed keep exactly
what they signed. Arbitrary code still cannot access broker credentials or
bypass the typed executor. The same proposal is signed from a grant card in the
conversation (`owner-actions.md`), built only from the card's stored draft.

The grant card offers one choice in its list of options: Custom (the D1 defaults above,
selected by default) or Full delegation. Full signs the same v2 full-management envelope
with `symbol_scope=account`, every action, no expiry, `allow_manual_positions` true and
no numerical cap, and sets no daily loss limit from the card; the composer's identical
proposal is the same pending envelope. It needs the same passkey ceremony, is offered
only where account-wide scope is allowed (the Personal Agent and flexible root agents),
and changes no limit: the account's money limits and execution caps (`ExecutionPolicy`),
and pauses bind it like any grant, and removing a limit is a separate
passkey step. Nothing in the envelope names the choice: a signed grant with exactly these
terms is recognized as Full delegation (`full_delegation`) by the readiness projection
(`full_delegation` on each grant and in the On its own params), the safety sheet and
the permission frame (`full_delegation` on each authorized scope). Grants already signed
keep exactly what they signed; the Full delegation label follows the signed terms, so a
grant signed earlier, or from Custom, with exactly these terms reads as Full delegation
without any change to what it may do. A grant card's passkey challenge names the choice
the card showed and is refused when the stored choice changed meanwhile
(`owner_action_card_changed`), so the passkey never signs Full while the owner's card
shows Custom.

## The ladder: No trading / Ask me / On its own

Each agent has one level, in the same words on Web and Mobile, in English and
Arabic (`tradingSafetyLabels` in `packages/core`): No trading (`analysis`), Ask me
(`supervised`), On its own (`autonomous`, an active signed grant). The ladder is
monotonic:

- Under On its own, a trade no active grant covers becomes an approval card
  exactly as under Ask me, never a refusal. "Covers" means every term of the
  signed grant: its account, markets and actions, and also its order, symbol,
  position and pending caps, its equity floor, the bounded stop-loss and
  protection rules, its action budget and the owner's own positions. The tool
  runs the executor's own grant check read-only against the broker's current
  account, positions and orders before anything is asked or sent
  (`grant_covers`, `GRANT_TERM_REFUSALS`). Without a grant, the executor decides by the agent's
  trading mode, read under the authority lock at send
  (`require_operation_permission`). Full sends on its own. Ask sends a
  risk-reducing request (`admission.risk_reducing` on the fresh ticket), and a
  request that adds risk only with the owner's approval of that exact operation.
  A ticket the agent's own journaled order did not open is refused
  (`ticket_not_owned`) unless the agent is Lonora, the run answers the owner's
  typed message asking for it, or the agent has the owner's standing instruction
  (`manages_all_positions`). A close or modify sent without a grant is refused
  with `broker_state_changed` when the ticket changed after the agent read it, or
  when nothing records what it read. The executor repeats the grant check at send
  for every operation sent under one; a grant decides within its own terms in
  either mode until it is revoked. A grant's management Task is held to its own grant;
  outside it, it asks too. The Full-mode account-management Task
  (`lonora_db.management_task`, docs/owner-actions.md) does not start while such a
  grant Task runs; its own Runs are ordinary Runs of the agent under its mode. Provisional speech never spends a grant: its
  operations are sent under the owner's exact approval only.
- The owner's own positions are the tickets the journal does not connect to an
  agent's entry: a position opened outside Lonora, and also one the owner opened
  from Lonora's own Trading page (`POST /trading/execute`, journaled with no
  agent). `lonora_opened` counts only an entry an agent's leased Run sent
  (`journal_agent`), the same rule broker wakes use (`attributed_agent`).
- A request that adds risk on the broker's current facts (an entry, or a stop
  moved further away) is refused with the pause's own code before any card while
  a pause holds it (`new_risk_requests`,
  `refuse_braked_entries`). The same exact request repeated in
  another call of the same Run answers from the card already raised for it
  (`reviewed_approval`, newest first): it waits on that card while it is pending,
  uses the owner's approval when it is approved or its operation reached the
  broker, and returns the owner's rejection until the owner writes again in that
  conversation. A result that never reached the broker, or a rejection the owner
  has spoken after, asks again.
- Moving down revokes the agent's signed and pending grants, as before
  (`change_permission`). The selector says so first, in one line: "This revokes
  the signed grant for <account>; going back needs a new signature", with Revoke
  and switch / Keep it.
- Defaults: Lonora (the Personal Agent) and a root trading agent with a focus pair
  start at Ask me; general, research and supervisor agents, bound children and
  delegated helpers start at No trading (`default_level`). A level the owner set is
  stored and kept; editing an agent's focus pair stores its current level first,
  so the edit never moves it. Migration `0040_explicit_agent_permission_rows`
  stores an explicit level for every agent that existed before: No trading, and
  Ask me for the Personal Agent. Delegated helpers can still never trade.

Activation atomically creates one existing durable Task and its work Run. Signed
proof replay cannot create another kickoff. It inspects actual state and may
create/reuse watches, choose trades and manage positions without per-order
approval. The task is bound to this exact grant; replacement or revocation cannot
silently let stale kickoff work spend a newer grant. Revocation, replacement and
device removal cancel the corresponding Task using the existing lifecycle. An activation is not an
entry signal or proof a broker is ready. The owner's pauses
remain authoritative and are never silently switched by activation.

A grant is the only authority (W15-9). The former Super Bot requests and per-goal
autonomy are retired: migration `0040_retire_super_bot_requests` marks pending and
activated requests `retired` and keeps every row as audit history, and nothing
reads them for authority. The readiness review and the confirmation line that
followed a Super Bot activation are now keyed on grants:

- A bounded grant (selected markets with explicit limits) gets one observe-only
  readiness review Run in the work lane after it is signed (receipt
  `activation-review:<grant id>`). A full-management grant gets none: its management
  Task is its first work. Grants that were already active when the migration ran get
  a skipped receipt, so no agent is woken for an old grant.
- A grant signed from the trading-level controls (`POST /account-authorities/verify`)
  writes one line in its conversation, in the conversation's language ("Trading on
  its own is on ..."); a lost-response replay adds none. A grant signed from its chat
  card is confirmed by the card itself. The review's own result stays quiet behind
  that line. The review is observe-only and gates nothing, so a review that fails is
  never retried and never puts the agent at "action required"; its status shows one
  review-scoped line ("The readiness check after you signed did not finish; that check
  sent nothing.") until a later Run of the agent completes (`review_status` then reads
  `superseded`). The failed Run stays in Activity.
- The avatar's "trades on its own" marker (`trades_on_its_own` on the agent) is shown
  only while the agent is not paused and holds a grant in force.

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
boundary. The owner's pauses, risk/preflight, execution quality,
manual intervention, idempotency, durable journal and reconciliation still apply.
Submitted, ambiguous, confirmed, owner-resolved and broker-rejected submitted
attempts consume the lifetime budget. Known pre-submission failures and released
reservations do not. An unresolved operation blocks new risk on its market or
ticket for every admission path, and risk-reducing actions stay admissible within
the grant (see `financial-execution-recovery.md`); nothing produces a blind resend.

Management requires a fresh material target snapshot and rejects owner changes
between observation and submission. Manual-origin positions need explicit signed
permission. Bounded-mode autonomous management cannot remove or widen an existing stop; explicit full-management mode permits discretionary stop decisions.
Only the run answering a provisional voice handoff, or a generated card's send,
cannot spend standing authority, and so does a retry or a «طلب جديد» renewal that
re-asks the same request and therefore carries its `voice_handoff`
(`carry_voice_handoff`), or a card send's retry, which carries a provenance-only mark
(`ui_submit_retry_of`, set by `retry_run`, read by `owner_words.ui_submit_provenance`),
not the send's queue rules (genui.md §7). Runs it starts (peers, follow-ups, subagents) and the
agent's later watches, routines and wakes are ordinary runs (mandate 6.10). In Ask
such a run's risk-increasing trades, even where a grant would cover them, take the
exact immutable approve/reject confirmation; in Full its trade_execute and
trade_close_positions send. Read-only voice work is unaffected.

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
product-set numerical quotas. The Personal Agent's review and grant card preselect
all pairs on the account; no permission is ever preselected as signed.
Current authoritative grant summaries enter the existing live Agent projection;
the badge is presentation, never permission.

## Verification

`tests/check_full_delegation.py` signs Full delegation from a grant card and shows that
the account's per-trade risk limit and position cap still refuse under it, while another
pair and the owner's own position are managed without a card.

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
fails with `symbol_not_found` or `symbol_ambiguous` (with the account's real candidates
and the next call, `docs/market-analysis.md`) so the agent or owner corrects it: a
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
grant, exact approval). Owner-manual operations through `POST
/trading/execute` are exempt unless the owner sets `applies_to_owner_manual` on an
all-agent restriction; agents cannot set it. The flag binds the owner's own trades, so
it is rejected together with `agent_id` (a restriction scoped to one agent never
restricts the owner), and matching applies it only to all-agent restrictions.

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
cancellations and tighter stops). A restriction an agent recorded
never blocks a risk-reducing exit, whatever its class: its scope and reason are
model-authored and may come from injected content, so it can stop new risk but never
trap a position, including an exit the owner approves. An agent may impose
`all_mutations` on another agent or on all agents only in a run that answers the owner's
message (source `owner_message`); otherwise creation fails with
`restriction_all_mutations_requires_owner_message`, and on its own initiative an agent
may freeze only itself. Pausing a whole agent stops its exits the same way, so a
supervisor pauses an agent with money standing only from the owner's message
(`supervision_pause_trading_agent`, `docs/supervision.md`). A restriction an agent records for another agent or for all
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
and Mobile header safety sheet lists the restrictions that apply to an agent with a
one-tap Lift (`trading-safety.md`), and every new restriction raises a Lift card in the
conversation (`owner-actions.md`); both use the owner's revoke.

## Monetary risk limits

`ExecutionPolicy.risk` (`PUT /trading/accounts/{id}/execution-policy`, owner only)
holds optional limits in the broker account currency, which the owner names in
`risk.currency`; a policy whose currency differs from the account blocks new risk
instead of converting. Unset means not enforced; no money amount is chosen for the
owner. The agent sees configured and unset limits in its permission frame and through
`trade_restriction_list`; the owner reads the current book against them with `GET
/trading/accounts/{id}/risk-status`. The conversation's money-limit card changes the same
policy; raising or removing a limit there needs the owner's passkey (`owner-actions.md`),
and so does a widening through the policy route itself (`…/execution-policy/challenge`
and `…/verify`); adding or lowering a limit stays one request.

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
partial close, discretionary stops, broker constraints and
revocation. The older authority fixture signs the genuinely original v1 envelope
shape so migration cannot reinterpret its absent fields. Browser checks exercise
actual EN/AR owner surfaces, full and bounded signatures, and unchanged global
controls; Expo Web checks are not physical native acceptance.

The complete trading mandate remains open: this scope does not implement generic
strategy equivalence or native background calls. A fresh
ordinary Task can use the account grant. No production grant or trade is activated
by migration, deployment or these tests.

## Native passkey bindings

Web requires the configured HTTPS `LONORA_ALLOWED_ORIGIN` (localhost HTTP is permitted for development). Android uses `react-native-passkeys` and the OS Credential Manager; iOS uses the platform passkey implementation. New native code requires a new compatible binary once; the existing fingerprint-based OTA mechanism must not deliver it to an old binary.

Set `LONORA_PASSKEY_ANDROID_FINGERPRINTS` to a JSON list of the actual installed APK signing-certificate SHA-256 fingerprints, using colon-separated hexadecimal bytes. These fingerprints are public. `LONORA_PASSKEY_ANDROID_PACKAGE` defaults to `ai.lonora.mobile`. Set `LONORA_PASSKEY_IOS_APP_IDS` to the public Apple `TEAMID.bundleIdentifier` values. The API serves `/.well-known/assetlinks.json` and `/.well-known/apple-app-site-association`; Expo config declares the matching webcredentials domain. Android assertion origins are accepted only for configured certificate hashes, never values supplied by the client. Empty bindings explicitly disable native activation, while offering the secure Web flow without putting bearer tokens in URLs.

Verify the metadata on the public origin, install the correctly signed new binary, and test an OS prompt on real devices before claiming native acceptance. Browser virtual-authenticator tests verify actual WebAuthn creation/assertion and server state, but cannot certify native behavior or a production domain association. Test cancellation, lockout/unsupported devices, session expiry, a changed plan, rejection, lost response, revocation and reload. No device error should grant authority.
