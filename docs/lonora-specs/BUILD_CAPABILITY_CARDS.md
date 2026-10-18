# Trading Agent Environment Capability Cards

Baseline: `80b0ff9`. Integration branch: `feat/trading-agent-environment`. The approved plan is [Professional Trading Agent Environment](NANOBOT_PARITY_AND_RELIABILITY_PLAN.md). Existing source specifications remain authoritative.

## ENV-CTX-01 — Model-aware request admission and fallback budgeting

- **Source:** Wave 1; B01/B02/B04/B07; R01/R07; existing S19 context and recovery requirements.
- **Status:** VERIFIED for local request-admission behavior and scripted routing/HTTP/PostgreSQL integration. Wave 1 and the full program remain incomplete; no live-provider capacity calibration or production acceptance claimed.
- **User behavior:** an ongoing Arabic/English trading conversation preserves current instructions and the latest complete tool observation when routed to a configured smaller fallback. A mandatory request that cannot fit fails explicitly before the provider call.
- **Audit:** ContextBuilder and model_turn apply character-only governance. GlobalModelRouter selects the model afterward and retries identical messages on fallback. ModelDescriptor already exposes optional context_window; catalog storage and global settings exist. Anthropic has a fixed output limit; compatible providers have no explicit output reservation.
- **Owner:** root/integration owns shared request contracts, governance relocation, router admission and adapters. No parallel edits to these owners.
- **Dependencies:** reuse ModelMessage, ToolDefinition, catalog settings, global routing/backups, provider adapters, TokenUsage and existing tool exchange grouping. Core cannot import adapter-kit because adapter-kit already depends on core.
- **Contracts/persistence:** preserve existing public model selection settings. Add bounded global context policy and diagnostics to existing settings/response metadata where needed. No migration or per-Agent model settings.
- **Authority/effects:** context trimming never executes tools, changes permissions, retries broker operations, or rewrites durable history. Preserve financial result identity when omitting a body. Reject an unrepresentable newest exchange rather than sending a broken protocol.
- **Budget:** use cached model-mapped tiktoken encoding where supported, otherwise a labeled proxy with margin or conservative offline byte fallback; count textual payloads, schemas, message framing and image estimates; reserve bounded output and safety headroom. Use catalog context windows where present and a clearly labeled global admission policy when absent, not an invented model capacity. Disclose approximate counting and verify final admission per attempt.
- **Acceptance:** Arabic/English and JSON-heavy contexts; schemas/images consume budget; latest user and complete latest tool batch retained; immutable inputs; mandatory overflow rejected; original financial outcome identity retained; actual router fallback rebuilds each attempt; provider output limits match reservation; unknown metadata is explicit; existing runtime recovery and effect-safety checks pass.
- **Delivery:** branch-only logical commits. No UI redesign, migration, APK build, live broker mutation, or production deployment. Regression evidence recorded in PROGRESS/matrix. Existing checkpoints do not change shape; rollback restores prior code without replaying tools.

## Subsequent integration points

1. Persisted large-result retrieval and durable references (Wave 2).
2. Scoped knowledge/evidence and typed Chart Use contracts (R05, C01–C11).
3. Skills eligibility/version lifecycle and bounded evaluated learning (Waves 3/5).
4. Collaboration and on-demand chart observation using existing Task/Gateway lifecycle.
5. Web/Mobile/voice journeys and separate physical-device acceptance.

These are NOT_STARTED as new acceptance requirements. Create detailed cards after their actual callers/contracts are audited; do not claim completion from this list.

## ENV-CTX-01 — Verified first integration and remaining limits

- One shared context governor in adapter-kit; existing Agent imports remain compatible. Providers do not import AgentRuntime.
- Global settings/read/write API; known catalog window and optional output cap applied per attempt. Unknown capacity is not invented.
- Text estimator cache prepared by setup, CI, and both Docker build definitions; request path uses locally verified data or an explicit fallback.
- Output reservation reaches all five provider adapters, including streamed requests. Actual reported usage and estimates are stored separately in existing usage rows; no migration.
- Local test evidence and exact logs are indexed in PROGRESS.md.
- Limits: image allowance and non-native tokenizer counts are estimates; absent catalog windows remain unknown. Deployment workload/latency and real-provider calibration are not verified. Mandatory context too large for a known model fails explicitly; selective tool/schema loading remains dependent work.
- Wheel packaging and setup cache preparation were executed. Docker image build, client/native acceptance, APK publication, and deployment were not performed.

## ENV-RESULT-01 — Next dependency: recoverable large results

Status: audit started, no implementation claim. Existing ToolLoop replaces results above 120000 characters with a bounded observation; current artifact_create/read, confined storage, producer identity, and lease checks can be reused. The artifact auto-attachment query currently includes all generated producer artifacts, so internal results need an explicit delivery distinction before integration.

Required next work: define internal result identity/retention and bounded readback; preserve original effect outcome and references through compaction/restart; ensure persistence failure cannot trigger mutation replay; enforce owner/Agent/Task scope; test duplicate delivery, missing/corrupt storage, and no unintended attachment or secret retention. Complete this card's contracts and acceptance tests before implementation.
