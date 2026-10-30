# General agents and flexible market defaults

New Web and native agents can be created without a broker connection. The owner
chooses General Agent or Default Market, along with name, title, description,
instructions and appearance. Both configurations use the existing agent runtime,
private memory, conversation, tools and permission machinery.

## Identity and compatibility

`scope_mode` distinguishes `fixed_market` from `flexible`. Existing database rows
and older creation requests retain `fixed_market`; new clients explicitly send
`flexible`. An unbound flexible root has role `general`; a flexible root with a
default has role `specialist`. The default Personal Agent is unchanged.

Migration `0033_flexible_agent_scope` adds scope mode and revision without changing
existing account IDs, symbols, permissions, grants, messages or financial records.
The owner can explicitly convert an existing root from settings. Renaming it does
not convert it. Delegated/child identities cannot opt into owner-wide flexible
scope. Research children of general agents remain nonfinancial.

## API contract

`POST /api/agents` accepts `scope_mode: "flexible"` with either both market fields
null/absent or both `trading_account_id` and `trading_symbol` set. Chosen markets
are checked against the enabled owned broker connection and its exact symbols.
No implicit market is selected. Omitting scope mode preserves the legacy API.

`PATCH /api/agents/{id}` changes scope only when all four fields are present:
`scope_mode: "flexible"`, `trading_account_id`, `trading_symbol`, and
`expected_scope_revision`. Explicit nulls clear both defaults. The revision
prevents concurrent settings edits from overwriting a newer scope; a stale edit
returns `409 version_conflict`. Scope edits use the existing financial-authority
lock. Personal and child agents reject this edit. Other profile edits keep their
existing partial-update behavior.

The response includes `scope_mode` and `scope_revision`; descriptive `scope`
metadata distinguishes owner-account visibility from execution authorization.

## Runtime and financial boundary

For flexible agents, omitted market arguments may use the saved default.
Explicit accounts/symbols take precedence. A default symbol is not copied onto a
different explicitly requested account. Market discovery, charts, observations,
watch evaluation, decision history and trade history do not filter an explicit
request back to the preferred market. Fixed-market agents retain their existing
guards and result filtering.

Creating, converting or changing a default never signs a grant or changes a
signed envelope. Scope editors allow separate selected-market or full-account
grant proposals for flexible roots. Existing controls, approvals, exact signed
account/symbol/action scope, preflight, operation identities, broker verification
and reconciliation still enforce financial execution. Changing the preference
does not resend, reinterpret or expand prior financial operations.

The core model guidance and market/chart skills distinguish immutable legacy
bindings from flexible preferences. The updated skill versions remain subject
to existing version/continuation controls.

## Verification

`tests/check_flexible_agents.py` uses an explicitly named disposable PostgreSQL
database, authenticated owner routes, standards-shaped signed device proofs and
the simulation adapter. It verifies general creation, exact-symbol validation,
cross-market discovery/quotes/charts, legacy restrictions, signed-grant
preservation, independently verified simulated execution, rejection outside the
grant, revision conflicts, clearing defaults and child restrictions.

`tests/web/flexible-agents.spec.mjs` and
`tests/mobile/flexible-agents.spec.mjs` exercise bilingual UI creation and settings
through the real API. Native UI tests use Expo Web and do not establish physical
device behavior. Existing binding and account-authority regression scripts remain
applicable. No test requires a live broker operation.

Publish the migrated server before the new mobile bundle. Older mobile bundles
continue sending legacy bound-agent creation requests. The Android JavaScript
update requires the installed bootstrap's matching native fingerprint and pinned
OTA certificate; no native dependencies or signing identities change.

### Recorded acceptance

- Additive migration from a seeded revision32 database to revision33 preserved
  every pre-existing agent field and added only `fixed_market`/revision0.
- The new PostgreSQL/simulation checks, legacy binding checks and signed account
  authority checks passed. Financial operations in these checks were simulation
  operations only.
- Bilingual creation/settings browser checks: two Web and two Expo Web passed.
- Broader Web workspace/chart/profile regressions: thirteen passed. Stale test
  assumptions were corrected to use switch semantics, accept the current model
  fixture keyword arguments and verify durable lost-response acknowledgment
  instead of requiring the owner to resend an already committed message.
- Selected Python tests: 103 passed, one environment-dependent case skipped;
  PostgreSQL behavior was separately exercised by the integration scripts.

Build validation is `bash scripts/build.sh`. External live-broker behavior and
physical-device acceptance are not established by the fixture checks above.
