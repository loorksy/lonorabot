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
Submitted, ambiguous, confirmed and broker-rejected submitted attempts consume
the lifetime budget. Known pre-submission failures do not. Unresolved account
mutations block another autonomous operation; they never produce a blind resend.

Management requires a fresh material target snapshot and rejects owner changes
between observation and submission. Manual-origin positions need explicit signed
permission. Bounded-mode autonomous management cannot remove or widen an existing stop; explicit full-management mode permits discretionary stop decisions.
Provisional voice input and its descendants cannot spend standing authority;
exact immutable approve/reject confirmation remains available through the existing
financial approval path. Read-only voice work is unaffected.

## Limits and accounting still under development

Broker contracts now retain optional sourced tick economics and contract metadata.
The read-only [market-entry sizing estimate](broker-position-sizing.md) uses exact
account money units and an explicit stop; it grants no permission. Signed per-trade
monetary ceilings and daily monetary loss enforcement are **not implemented** by
this delegation. Such envelope fields remain rejected, not silently interpreted
as protection. Volume limits, an equity floor and a
required stop cannot guarantee a maximum loss. The Web and Mobile review both
state this limitation before signing. No authorization was activated on a
production account while implementing or testing this capability.

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

## Remaining monetary foundations

A future signed monetary limit must identify the exact broker account currency
and a precise estimated-loss basis. It must reuse the same Decimal tick-loss
calculation and existing final serialized preflight, with fresh source economics
immediately before mutation. A read-only sizing result cannot create that limit.
Pending-entry price changes can increase modeled risk even when the stop remains
unchanged. Closing, cancelling and protective risk reduction must remain possible
when an existing position exceeds a new ceiling; manual-position permission and
owner intervention still win. Estimated stop fills cannot guarantee maximum loss.

Daily enforcement additionally needs complete account-wide history coverage,
synchronization/pagination evidence, actual deal costs and cash-flow semantics,
explicit day boundaries and any opening-equity baseline required by the chosen
policy. A bounded list of 1,000 recent deals or current floating profit cannot
prove a daily-loss budget. These remain implementation dependencies, rather than
missing credentials or an assumed property of the current volume grant.


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
