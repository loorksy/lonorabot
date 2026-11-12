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
  (`grant_covers`, `GRANT_TERM_REFUSALS`). The executor admits an operation without a grant only
  with the owner's approval of that exact operation
  (`require_operation_permission`), and repeats the grant check at send for every
  operation sent under one. A grant's management Task is held to its own grant;
  outside it, it asks too. Provisional speech never spends a grant: its
  operations are sent under the owner's exact approval only.
- The owner's own positions are the tickets the journal does not connect to an
  agent's entry: a position opened outside Lonora, and also one the owner opened
  from Lonora's own Trading page (`POST /trading/execute`, journaled with no
  agent). `lonora_opened` counts only an entry an agent's leased Run sent
  (`journal_agent`), the same rule broker wakes use (`attributed_agent`).
- The same exact request repeated in another call of the same Run answers from
  the card already raised for it (`reviewed_approval`, newest first): it waits on
  that card while it is pending, uses the owner's approval when it is approved or
  its operation reached the broker, and returns the owner's rejection until the
  owner writes again in that conversation. A result that never reached the broker,
  or a rejection the owner has spoken after, asks again.
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

## Monetary risk limits

`ExecutionPolicy.risk` (`PUT /trading/accounts/{id}/execution-policy`, owner only)
holds optional limits in the broker account currency, which the owner names in
`risk.currency`; a policy whose currency differs from the account blocks new risk
instead of converting. Unset means not enforced; no money amount is chosen for the
owner. The agent sees configured and unset limits in its permission frame; the owner
reads the current book against them with `GET /trading/accounts/{id}/risk-status`.
The conversation's money-limit card changes the same policy; raising or removing a limit
there needs the owner's passkey (`owner-actions.md`), and so does a widening through the
policy route itself (`…/execution-policy/challenge` and `…/verify`); adding or lowering
a limit stays one request.

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
Blocked operations carry tool recovery metadata that matches the boundary: every
`risk_*` code is `risk_limit_blocked` / `inspect_risk_assessment` (resize or protect to
fit the limit, reduce exposure, or wait for the owner).

`tests/test_risk_limits.py` covers per-trade risk from stop distance and tick value, open
risk with pending and unresolved operations, daily loss with conservative deal types and
history coverage, free margin, currency mismatch, permission-frame rendering and the
recorded assessment. `tests/check_risk_limits.py` (disposable PostgreSQL, simulation
broker, real owner API and approval path) covers every monetary limit on the owner and
agent paths, the passkey for a widening, and closing and cancelling under a limit.

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
