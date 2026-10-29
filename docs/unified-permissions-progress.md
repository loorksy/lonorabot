# Unified Agent Permissions — implementation and verification

Mandate: [prompt4.md](lonora-specs/prompt4.md). Implementation branch:
`feature/unified-agent-permissions`, [PR #12](https://github.com/loorksy/lonorabot/pull/12).
The feature has not been merged or deployed.

## One permission model over existing financial infrastructure

| User selection | Server meaning | Financial execution |
| --- | --- | --- |
| Analysis Only / تحليل فقط | `analysis`, default without a broader valid authorization | No broker mutations; analysis, charts, memory, watches and analytical tasks remain available |
| With My Approval / بموافقتي | `supervised`, authenticated immediate selection | Existing immutable approval for each exact operation |
| Autonomous Management / إدارة مستقلة | `autonomous`, derived from valid signed AccountAuthority | Only the account, markets, actions, limits and duration in that grant |

Both bounded grants and customized full-management grants represent autonomy.
Numerical restrictions do not select the supervised level. Global Trading ON/OFF
and Emergency Stop are unchanged and never switched by the permission selector.
Existing valid account grants remain recognized without a preference record.
Legacy Goal/Super Bot signatures alone cannot grant current Agent trading rights.

## Server state, signing and transitions

- Python contracts and the shared TypeScript contracts define the same state.
  Per-Agent fallback, revision and non-executable customization preferences use
  the existing SettingsRow storage; no database migration or second grant engine.
- `GET /agents/{id}/permissions` projects current validated authority. Authenticated
  `PUT` selects analysis/supervised with an expected revision. The customization
  endpoint stores reusable drafts separately from executable authorization.
- Existing AccountAuthority proposals accept `permission_revision` for optimistic
  concurrency, under the same Agent lock as downgrade and activation. A new
  proposal supersedes other pending proposals for that Agent.
- Existing WebAuthn enrollment, exact envelope review, proof verification and
  account-management task activation are reused. Pending, canceled or failed
  signing does not raise the effective permission. Used proofs cannot reactivate
  a revoked or expired grant.
- Downgrades revoke pending and active account grants, stop grant-bound management
  tasks and disable historical financial Goal delegation. They preserve analytical
  Goals, watches, routines, broker journals and open positions. No close/cancel
  request is sent to the broker just because permission changes.
- Device revocation shares the owner/device and Agent locking order, and publishes
  a permission revision for each affected Agent. Connected clients refresh from
  permission events rather than interpreting conversation text.

## Desktop, mobile browser and native experience

- The actual conversation composers expose a compact three-level selector.
  Desktop uses an attached popover; mobile browser and native use selection sheets.
  The old settings entry reuses the same component and signing flow.
- Advanced customization is available only for autonomous management. Four
  collapsible groups cover account/market scope, the existing ten operations,
  six optional numerical limits, and duration/manual-position coverage.
- Desktop has a centered two-column editor with live summary. Mobile browser has
  a full-height single-column editor and persistent review footer. Native uses
  React Native Modal, safe areas, keyboard avoidance, scrollable controls and Back.
- Account and symbol options come from authoritative connections and broker data.
  Specialist bindings remain fixed; eligible Personal Agents can explicitly review
  account-wide scope. Minimum equity is labeled in the actual account currency.
- Empty numerical inputs remain null restrictions. Duration presets produce exact
  timezone-aware expiry during proposal preparation; the signed review shows the
  actual expiry and never silently extends it. Decimal volume comparisons preserve
  precision instead of rounding through JavaScript floating point.
- Effective permission is shown separately from a pending request. Draft edits
  survive group navigation and downgrade; returning to autonomy requires a fresh
  signature. Conflict handling preserves local edits instead of overwriting them.
- English/Arabic copy, RTL/LTR, keyboard focus, accessible controls, responsive
  geometry, reduced motion and supported themes are included. Permission errors
  have shared human explanations rather than exposed internal error codes.
- Permission fetching is independent of message submission and streamed response
  events. Opening/editing settings does not clear or submit the chat draft.
- The transcript also reuses canonical Runs already fetched by the workspace.
  Valid SSE text no longer waits for a second successful thread-specific status
  request. Existing identity, thread scope, timestamps and stream fencing remain
  authoritative; no request or fabricated execution state was added.

## Agent Runtime and broker enforcement

- Each model turn receives fresh trusted permission context: effective level,
  approval requirements, valid scopes/actions/limits and observer status. Pending
  proposals and customization drafts never enter that context as active rights.
- The LLM keeps analytical and decision-making freedom. No keyword router or
  trading decision algorithm is introduced. Contradictory historical Goal policy
  language is updated within the existing mandatory prompt budget and checksum.
- Financial tools and the shared executor recheck current permission. The final
  broker send uses the existing Agent lock, scoped grant/exact approval validation,
  binding, preflight, idempotency, manual-intervention checks and global controls.
- Goals, scheduled work, watch wakeups, stale leases, retries and collaborating
  agents reach the same boundary. Subagents and observe-only delegation cannot
  acquire independent financial rights. Provisional speech requires the existing
  exact approval as well as any applicable signed scope.
- Already admitted operations retain existing reconciliation semantics. Reading a
  completed journal or exact completed tool result after downgrade does not resend
  a financial operation. Authenticated owner manual execution is a separate existing
  owner action; Agent tools always execute with their lease.

## Main implementation files

- Shared contracts/helpers: `packages/contracts/src/agent-permissions.ts`, Python
  `lonora_contracts/agent_permissions.py`, `packages/core/src/agent-permission.ts`
  and `agent-permission-errors.ts`.
- Persistence/API/signing: `lonora_db/agent_permissions.py`, the existing
  `account_authority.py` DB/auth modules, and API `agent_permissions.py`,
  `account_authority.py`, `device_authority.py`.
- Enforcement/context: `lonora_trading/agent_permission.py`, existing financial
  executor/Goal/AccountAuthority/tool modules, and
  `lonora_agent/context/permissions.py` plus existing live routing context.
- Web: `apps/web/src/components/permissions/`, composer integration and the
  existing settings wrapper. Native: `apps/mobile/components/agent-permissions.tsx`,
  native labels, composer/thread integration and settings wrapper.
- Verification: `tests/check_unified_permissions.py`, contract/enforcement pytest
  files, shared proposal tests and Web/native permission browser specifications.
  CI includes the new checks through the existing isolated foundation runner.
- Existing fixtures now explicitly opt into supervised or signed autonomous
  behavior where intended. Scripted models read the exact tool evidence rather
  than assuming the final context message is always a tool result; lifecycle
  assertions verify actual Run completion rather than only expected side effects.

## Verification results

| Verification | Actual result |
| --- | --- |
| `bash scripts/build.sh` | Passed: Ruff, formatting, strict Pyright, resource/distribution checks, Biome, all TypeScript checks and all seven build targets |
| Full pytest suite | 1,389 passed |
| Shared permission and AccountAuthority TypeScript tests | 15 passed |
| Existing activity/timeline TypeScript regressions | 11 passed unchanged |
| Isolated foundation integrations | All 63 listed integration scripts passed, plus the runner's 11 Task Runtime tests |
| Web permission and conversation browser cases | 29 passed: desktop/mobile/tablet, EN/AR, supported themes, signing, cross-tab sync, chat draft/latency/SSE/ordering and failure behavior |
| Expo native component browser cases | 7 passed: existing settings plus composer/customization/review, narrow/portrait/landscape and settled sheet geometry |
| Real WebAuthn verification | Scripted cryptographic proofs and browser virtual authenticators passed bounded/full/customized scope and revocation; no physical-device claim |

The foundation integrations used separately migrated disposable databases. The
verified prefix and completed remainder cover all 63 entries in the existing
runner. An environment interruption likewise split the final Web run into 24
completed cases and the remaining five SSE cases; both used the same final source.
No incomplete test process is counted as a pass.

The checked [GitHub Actions run](https://github.com/loorksy/lonorabot/actions/runs/40705042834)
did not execute any steps: GitHub reported an account billing lock. This is
separate from the successfully executed local validation above.

## Boundaries of verification

All financial checks use simulation and disposable PostgreSQL databases. WebAuthn
proofs use scripted or browser virtual authenticators with the production verifier;
physical-device passkey signing is not claimed. Native browser coverage exercises
the Expo component implementation but does not replace Android/iOS device testing.
No live financial operation, merge or deployment was performed for this feature.
The optional standalone HTML reference was absent; the documented responsive
layouts and interactions were implemented directly in the existing applications.

## Complete changed-file inventory

84 files relative to `main`: 22 added, 62 modified.

| Change | File |
| --- | --- |
| Modified | [.github/workflows/ci.yml](../.github/workflows/ci.yml) |
| Modified | [apps/api/src/lonora_api/app.py](../apps/api/src/lonora_api/app.py) |
| Modified | [apps/api/src/lonora_api/routes/account_authority.py](../apps/api/src/lonora_api/routes/account_authority.py) |
| Added | [apps/api/src/lonora_api/routes/agent_permissions.py](../apps/api/src/lonora_api/routes/agent_permissions.py) |
| Modified | [apps/api/src/lonora_api/routes/device_authority.py](../apps/api/src/lonora_api/routes/device_authority.py) |
| Modified | [apps/mobile/app/thread.tsx](../apps/mobile/app/thread.tsx) |
| Modified | [apps/mobile/components/account-authority-settings.tsx](../apps/mobile/components/account-authority-settings.tsx) |
| Added | [apps/mobile/components/agent-permissions.tsx](../apps/mobile/components/agent-permissions.tsx) |
| Modified | [apps/mobile/components/thread-composer.tsx](../apps/mobile/components/thread-composer.tsx) |
| Added | [apps/mobile/lib/permission-labels.ts](../apps/mobile/lib/permission-labels.ts) |
| Modified | [apps/mobile/lib/session.tsx](../apps/mobile/lib/session.tsx) |
| Added | [apps/web/src/components/permissions/AgentPermissions.tsx](../apps/web/src/components/permissions/AgentPermissions.tsx) |
| Added | [apps/web/src/components/permissions/PermissionEditor.tsx](../apps/web/src/components/permissions/PermissionEditor.tsx) |
| Added | [apps/web/src/components/permissions/agent-permissions.css](../apps/web/src/components/permissions/agent-permissions.css) |
| Added | [apps/web/src/components/permissions/permission-labels.ts](../apps/web/src/components/permissions/permission-labels.ts) |
| Modified | [apps/web/src/components/trading/AccountAuthoritySettings.tsx](../apps/web/src/components/trading/AccountAuthoritySettings.tsx) |
| Modified | [apps/web/src/hooks/useThreads.ts](../apps/web/src/hooks/useThreads.ts) |
| Modified | [apps/web/src/lib/user_error.ts](../apps/web/src/lib/user_error.ts) |
| Modified | [apps/web/src/pages/Shell.tsx](../apps/web/src/pages/Shell.tsx) |
| Modified | [apps/web/src/pages/shell/chat-context.tsx](../apps/web/src/pages/shell/chat-context.tsx) |
| Added | [docs/lonora-specs/prompt4.md](../docs/lonora-specs/prompt4.md) |
| Added | [docs/unified-permissions-progress.md](../docs/unified-permissions-progress.md) |
| Modified | [packages/agent-runtime/resources/constitution/trading-policy.md](../packages/agent-runtime/resources/constitution/trading-policy.md) |
| Modified | [packages/agent-runtime/resources/skills/trading-goal/SKILL.md](../packages/agent-runtime/resources/skills/trading-goal/SKILL.md) |
| Modified | [packages/agent-runtime/resources/system/lonora.md](../packages/agent-runtime/resources/system/lonora.md) |
| Modified | [packages/agent-runtime/resources/system/manifest.json](../packages/agent-runtime/resources/system/manifest.json) |
| Modified | [packages/agent-runtime/src/lonora_agent/context/builder.py](../packages/agent-runtime/src/lonora_agent/context/builder.py) |
| Modified | [packages/agent-runtime/src/lonora_agent/context/goals.py](../packages/agent-runtime/src/lonora_agent/context/goals.py) |
| Added | [packages/agent-runtime/src/lonora_agent/context/permissions.py](../packages/agent-runtime/src/lonora_agent/context/permissions.py) |
| Modified | [packages/agent-runtime/src/lonora_agent/context/team.py](../packages/agent-runtime/src/lonora_agent/context/team.py) |
| Modified | [packages/auth/src/lonora_auth/account_authority.py](../packages/auth/src/lonora_auth/account_authority.py) |
| Added | [packages/contracts/src/agent-permissions.ts](../packages/contracts/src/agent-permissions.ts) |
| Modified | [packages/contracts/src/index.ts](../packages/contracts/src/index.ts) |
| Added | [packages/contracts/src/lonora_contracts/agent_permissions.py](../packages/contracts/src/lonora_contracts/agent_permissions.py) |
| Added | [packages/core/src/agent-permission-errors.ts](../packages/core/src/agent-permission-errors.ts) |
| Added | [packages/core/src/agent-permission.ts](../packages/core/src/agent-permission.ts) |
| Modified | [packages/core/src/index.ts](../packages/core/src/index.ts) |
| Modified | [packages/db/src/lonora_db/account_authority.py](../packages/db/src/lonora_db/account_authority.py) |
| Added | [packages/db/src/lonora_db/agent_permissions.py](../packages/db/src/lonora_db/agent_permissions.py) |
| Modified | [packages/tools/src/lonora_tools/registry.py](../packages/tools/src/lonora_tools/registry.py) |
| Modified | [packages/tools/src/lonora_tools/super_bot.py](../packages/tools/src/lonora_tools/super_bot.py) |
| Modified | [packages/tools/src/lonora_tools/trade.py](../packages/tools/src/lonora_tools/trade.py) |
| Modified | [packages/tools/src/lonora_tools/trading_goal.py](../packages/tools/src/lonora_tools/trading_goal.py) |
| Modified | [packages/trading/src/lonora_trading/account_authority.py](../packages/trading/src/lonora_trading/account_authority.py) |
| Added | [packages/trading/src/lonora_trading/agent_permission.py](../packages/trading/src/lonora_trading/agent_permission.py) |
| Modified | [packages/trading/src/lonora_trading/execution.py](../packages/trading/src/lonora_trading/execution.py) |
| Modified | [packages/trading/src/lonora_trading/goals.py](../packages/trading/src/lonora_trading/goals.py) |
| Modified | [tests/check_account_authority.py](../tests/check_account_authority.py) |
| Modified | [tests/check_account_recovery.py](../tests/check_account_recovery.py) |
| Modified | [tests/check_activation_review.py](../tests/check_activation_review.py) |
| Modified | [tests/check_agent_binding.py](../tests/check_agent_binding.py) |
| Modified | [tests/check_agent_environment.py](../tests/check_agent_environment.py) |
| Modified | [tests/check_agent_market.py](../tests/check_agent_market.py) |
| Modified | [tests/check_chart_visual_observation.py](../tests/check_chart_visual_observation.py) |
| Modified | [tests/check_conversational_setup.py](../tests/check_conversational_setup.py) |
| Modified | [tests/check_decision_readiness.py](../tests/check_decision_readiness.py) |
| Modified | [tests/check_decision_replay.py](../tests/check_decision_replay.py) |
| Modified | [tests/check_execution_quality.py](../tests/check_execution_quality.py) |
| Modified | [tests/check_full_account_management.py](../tests/check_full_account_management.py) |
| Modified | [tests/check_generated_artifacts.py](../tests/check_generated_artifacts.py) |
| Modified | [tests/check_goals.py](../tests/check_goals.py) |
| Modified | [tests/check_group_replies.py](../tests/check_group_replies.py) |
| Modified | [tests/check_image_observations.py](../tests/check_image_observations.py) |
| Modified | [tests/check_opportunity_runtime.py](../tests/check_opportunity_runtime.py) |
| Modified | [tests/check_personal_agent.py](../tests/check_personal_agent.py) |
| Modified | [tests/check_progressive_skills.py](../tests/check_progressive_skills.py) |
| Modified | [tests/check_relationships.py](../tests/check_relationships.py) |
| Modified | [tests/check_skill_packages.py](../tests/check_skill_packages.py) |
| Modified | [tests/check_skill_repository.py](../tests/check_skill_repository.py) |
| Modified | [tests/check_strategy_research.py](../tests/check_strategy_research.py) |
| Modified | [tests/check_streaming.py](../tests/check_streaming.py) |
| Modified | [tests/check_task_environment_wait.py](../tests/check_task_environment_wait.py) |
| Modified | [tests/check_trade_approvals.py](../tests/check_trade_approvals.py) |
| Added | [tests/check_unified_permissions.py](../tests/check_unified_permissions.py) |
| Modified | [tests/check_workspace_artifacts.py](../tests/check_workspace_artifacts.py) |
| Modified | [tests/check_workspace_skill_creation.py](../tests/check_workspace_skill_creation.py) |
| Modified | [tests/mobile/account-authority.spec.mjs](../tests/mobile/account-authority.spec.mjs) |
| Added | [tests/mobile/agent-permissions.spec.mjs](../tests/mobile/agent-permissions.spec.mjs) |
| Modified | [tests/run_foundation_checks.py](../tests/run_foundation_checks.py) |
| Added | [tests/test_agent_permission_contracts.py](../tests/test_agent_permission_contracts.py) |
| Added | [tests/test_agent_permissions_enforcement.py](../tests/test_agent_permissions_enforcement.py) |
| Modified | [tests/web/account-authority.spec.mjs](../tests/web/account-authority.spec.mjs) |
| Added | [tests/web/agent-permission.test.ts](../tests/web/agent-permission.test.ts) |
| Added | [tests/web/agent-permissions.spec.mjs](../tests/web/agent-permissions.spec.mjs) |
