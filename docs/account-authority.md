# Bounded account delegation

An owner may sign one immutable account delegation without first authoring a
Trading Goal. This extends the existing financial executor, device verification,
account serialization and journal; it creates no second execution or risk engine.

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
permission. Autonomous management cannot remove or widen an existing stop.
Provisional voice input and its descendants cannot spend standing authority;
exact immutable approve/reject confirmation remains available through the existing
financial approval path. Read-only voice work is unaffected.

## Honest limits

The current broker Instrument contract lacks verified monetary tick value,
contract size and currency conversion. Dollar stop-risk sizing and daily monetary
loss budgets are **not implemented** by this delegation. Such fields are rejected,
not silently interpreted as protection. Volume limits, an equity floor and a
required stop cannot guarantee a maximum loss. The Web and Mobile review both
state this limitation before signing. No authorization was activated on a
production account while implementing or testing this capability.

The compact Web/Mobile bot settings reuse existing account/market selectors and
passkey enrollment/signing. Every financial limit and action must be supplied
explicitly. No pair or permission is preselected for an unbound Personal Agent.
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
