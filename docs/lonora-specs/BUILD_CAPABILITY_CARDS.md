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

These are integration boundaries, not blanket completion claims. Scoped cards below track each implemented increment and its remaining acceptance work.

## ENV-CTX-01 — Verified first integration and remaining limits

- One shared context governor in adapter-kit; existing Agent imports remain compatible. Providers do not import AgentRuntime.
- Global settings/read/write API; known catalog window and optional output cap applied per attempt. Unknown capacity is not invented.
- Text estimator cache prepared by setup, CI, and both Docker build definitions; request path uses locally verified data or an explicit fallback.
- Output reservation reaches all five provider adapters, including streamed requests. Actual reported usage and estimates are stored separately in existing usage rows; no migration.
- Local test evidence and exact logs are indexed in PROGRESS.md.
- Limits: image allowance and non-native tokenizer counts are estimates; absent catalog windows remain unknown. Deployment workload/latency and real-provider calibration are not verified. Mandatory context too large for a known model fails explicitly; selective tool/schema loading remains dependent work.
- Wheel packaging and setup cache preparation were executed. Docker image build, client/native acceptance, APK publication, and deployment were not performed.

## ENV-RESULT-01 — Recoverable large results

Status: VERIFIED for local/scripted Run/call recovery and bounded readback. ToolLoop persists results above 120000 characters as internal artifacts with stable Run/call identity and an argument hash, then checkpoints a bounded observation/reference. Existing artifact storage, lease/fence checks and owner/Agent/thread scope are reused. `artifact_read` accepts that reference as artifact_id with offset/limit/next_offset paging. Internal results are filtered before the artifact-list limit and never automatically become user attachments.

Storage is a redacted JSON projection using Lonora's existing redactor, bounded by the existing 20MB artifact limit; retention is owner-managed, not an automatic-expiry promise. Missing/corrupt files retain the confirmed execution summary and cannot grant mutation replay. A write failure preserves the actual effect result with an explicit storage failure. Ambiguous financial observations continue through the existing same-operation journal/reconciliation handler; this is not a second journal. Existing read-only/replay policies still govern effects without a completed receipt.

Acceptance: independently repeated PostgreSQL ToolLoop crash after receipt/before checkpoint, one actual scripted mutation, complete redacted paging, wrong owner/Agent/thread, changed arguments, stale fence, corrupt/missing files, write failure, 20MB rejection, more than 200 hidden internal rows and ambiguity beyond the first twenty summaries. Existing runtime acceptance now reads a stored result without repeating its original source read. Forty focused unit cases and generated-artifact regressions passed. No live-money operation or migration.

Remaining limits: result files require the existing persistent artifact volume; files exceeding 20MB remain bounded/explicitly unavailable; redaction recognizes existing key/Bearer patterns and is not a universal classifier of arbitrary sensitive prose; no new retention daemon, whole-corpus cache or successor-Run result transfer was introduced.

## ENV-KNOWLEDGE-01 — Scoped bounded memory evidence

- **Sources/dependencies:** Wave 3/R05, existing memory provenance and context assembly. Reuse MemoryRow, SemanticMemoryRow, global embedding configuration and current Agent authorization; no secondary store or schema.
- **Behavior:** existing `retrieve_memory` callers receive bounded, attributed evidence with lexical fallback when semantic retrieval is disabled, unconfigured or unavailable. Arabic/English recall, exact technical identifiers, deduplication and current memory versions are retained. Source recording time is not represented as market freshness.
- **Authority:** SQL owner/Agent filtering precedes candidates and ranking; retrieved content remains explicitly untrusted. Similar vectors cannot substitute another recognized broker symbol or ID. Installed source content never grants financial authority.
- **Bounds:** per-arm 128 notes, 8 delivered items, 6000 delivered text characters, 1600/item; candidate/embedding/query truncation is explicit. An old semantic match outside the bounded candidate window can be omitted. Lowercase alphabetic symbols require explicit metadata to distinguish them from ordinary prose.
- **Verification:** 32 unit cases plus independently repeated PostgreSQL retrieval fixture; scoped denial, peer isolation, fallback, source versions, edits/deletes and malformed/oversized vectors. No live provider quality benchmark.
- **Open:** broader evaluation corpus, measured retrieval quality and evaluated memory adoption. Authorized compacted direct-thread recall and one adjacent turn are tracked separately below; this does not close full knowledge/learning requirements.

## ENV-CHART-DRAW-01 — Durable typed drawing geometry

- **Sources/dependencies:** C01–C11, existing ChartState/CloudChartRepository, scoped chart tools and optimistic chart versions. Reuse the same chart/runtime/event path; no new runtime, broker mutation or schema.
- **Behavior:** legacy price/line/note formats remain valid. Time/price geometry adds price zones, rays, channels, Fibonacci levels, arrows and scenarios. `chart_annotate` supports an atomic add/update/delete batch with stable identities and bounded inert style metadata.
- **Authority:** Agents stamp their own attributed layer and cannot overwrite owner/manual legacy drawings or another Agent's layer. Scope filtering preserves actual account, exact symbol and allowed timeframes. Owner REST remains owner authority. Scenarios are visual annotations, never orders/approvals.
- **Persistence:** existing fenced transactions and chart row/version checks serialize updates. Invalid batches roll back. Native update calls now atomically retain scoped immutable success acknowledgments in existing EffectReceiptRow; identical Run/call replay returns the original acknowledgment without reapplying, while changed intent conflicts. New independent writers still obey optimistic versions.
- **Verification:** 39 focused Python cases; eight SQLite symbol/timeframe combinations; independently repeated PostgreSQL atomicity, concurrent-writer, identity and zero-order checks. The saved server SVG shares the same ten shape kinds.
- **Open:** persistent visual navigation and physical client acceptance. Creation recovery is tracked in ENV-CHART-CREATE-01. Shared browser rendering and one-shot visual capture are tracked separately below. Saved semantic geometry is not proof that a client displayed it.

## ENV-CHART-UI-01 — One scene renderer for Web and Mobile

- **Sources/dependencies:** C01–C11, approved licensed TradingView reuse and AiChart as a visual reference only. Backend typed chart geometry, scenes and existing owner event stream remain authoritative.
- **Contract:** one pinned v31.2.0 vendor tree with 551 hash-verified assets, English/Arabic bundles and all shared dependencies. One shared renderer/component/datafeed/study projection; `/charts/render` and namespaced `/chart-runtime` assets work with either the Web or Expo shell. No credentials in frame URLs, no separate quotes or browser indicator calculations.
- **Behavior:** read-only saved geometry projects all ten types into vendor shapes; indicator panes consume server values. Current/new candles and historical corrections preserve user navigation. Show Agent analysis / opt-in Follow Agent focus real saved geometry; pointer/wheel immediately return viewport priority to the user. Mobile sheets preserve chat/draft/frame, support expand/minimize/reopen and Escape/Back. Desktop reuses the existing side-panel owner.
- **Authority:** origin/source/chart/scene/data revision checks gate client acknowledgment. It describes the current client's applied scene only and grants no financial authority. Specialist account/symbol binding remains server-enforced.
- **Deployment:** normal Web build contains the dedicated renderer; optional LONORA_CHART_RENDERER_ROOT points to that same build when serving Expo Web separately. Unhashed renderer/vendor entries revalidate to avoid stale-entry deployment failures. `react-native-webview`13.16.1 is an SDK-compatible native dependency; older installed binaries are checked before lazy loading and show an explicitly labeled saved-scene fallback. OTA cannot add that native module.
- **Limits:** bounded resident history; generic visual session/precision are not broker instrument specifications. Vendor drawings are locked projections with existing owner editing forms. Native gestures, physical voice continuity and real broker timeframe coverage require separate acceptance. No server browser session or model image observation is implied.

## ENV-VISION-01 — Artifact-backed image observation

Status: VERIFIED for local/scripted raster transport, scope, recovery and model admission. Source audit found snapshots saved images but JSON-only tool observations did not put their pixels into the same Run's model request; Anthropic also ignores images on tool-role messages.

Existing artifact_read now accepts explicit view_image with strict owner/Agent/thread, hash, MIME, dimension and byte checks. Model-boundary preparation resolves only matched successful server tool observations, supplies attributed untrusted user-role images after the complete tool-result block, routes pixels through global VISION, and retains references rather than base64 in checkpoints. Four distinct images/20MB maximum; omitted sources receive bounded explicit notices. Existing user attachments and all effect identities remain unchanged.

Runtime-only `ModelMessage.context_origin` binds observations to their producing exchange during admission. They cannot replace the newest real owner instruction, be separated from tool results, or leak internal provenance fields to provider HTTP. The actual global router test exercises primary failure and smaller fallback: owner request + newest complete exchange + pixels survive, or context admission fails explicitly. Historical image exchanges can be omitted together.

Evidence: actual PostgreSQL chart_snapshot → artifact_read → same Run model pixels, interruption/restart with reference-only checkpoint, scope/integrity/MIME/dimension/size failures, five provider HTTP serializer tests including Anthropic ordering, and 36 focused image/context/result cases. HTTP payload acceptance is not proof that every configured external model supports vision or understands a particular chart. On-demand browser capture and immutable provenance are separately verified in ENV-CHART-VISUAL-01; default semantic images must not be called TradingView screenshots.


## ENV-CHART-VISUAL-01 — On-demand server-rendered chart observation

- **Behavior:** `chart_snapshot(renderer="tradingview", chart_id=..., locale="en"|"ar")` captures the actual shared licensed renderer. Backend scene identity, exact broker symbol, timeframe and data revision must match its applied acknowledgment. Existing semantic PNG/SVG snapshots remain separately labeled.
- **Integration:** Worker/Gateway and owner API services pass one optional lazy visual runtime through existing ToolContext, including child contexts. Two bounded concurrent captures use fresh credential-free browser contexts; shutdown is bounded and still closes market/broker services after a browser failure. No separate process host, journal or migration.
- **Isolation:** operator-configured renderer only; no Agent URL/script/shell input. Browser requests are same-origin static renderer GETs; API/external/mutation/WebSocket requests are denied. Chromium receives a minimal environment and private temporary profile. Trusted Playwright driver inherits the host environment because its public startup API has no environment argument; it is not an Agent execution surface.
- **Evidence/recovery:** immutable artifact provenance distinguishes candle observation, quote observation and capture time. Replaying the same Run/call returns original bytes/revisions even after chart changes. Legacy provenance remains explicitly unknown. A worker death after artifact persistence and before checkpoint does not recapture on the next fence. `artifact_read(view_image=true)` admits the actual pixels into the same Run.
- **Verified:** 22 service-level cases with real Chromium and fault injection; PostgreSQL semantic provenance; four exact forex/metal/index/crypto symbols and multiple frames in EN/AR; real ToolLoop crash/replay and stale-fence denial. Combined repository pytest: 334 passed; strict Pyright zero errors. Python wheel contains the service and pins Playwright1.58.0. No APK/container image or production deployment was performed.
- **Open:** persistent interactive visual workspaces, viewport-navigation commands, real external-model interpretation quality and physical native acceptance. Captured, inspected, attached and client-rendered remain distinct claims.


## ENV-RECALL-01 — Authorized compacted conversation evidence

- **Reuse:** canonical MessageRow/ThreadRow and the existing bounded memory evidence fusion; no separate message index or embedding store. ContextBuilder enables recall only for the current owned Agent direct conversation.
- **Behavior:** Arabic/English lexical retrieval and exact technical identifiers return relevant compacted messages, with actual message/thread/sequence/role/author/source time. One adjacent opposite-role canonical turn can expand an exchange within the same shared item/text budget. Historical content is untrusted and never current market evidence.
- **Authority/bounds:** SQL owner/Agent/thread checks precede ranking; group, internal-work, peer transport and guest messages are excluded. Server summary/input/next-sequence cutoffs prevent current/future message duplication. At most128 candidates, bounded text projection, eight delivered items and6000 text characters shared with other evidence. Messages lack a revision column, so version0 is explicitly a non-versioned source rather than an invented revision.
- **Verification:** actual ContextBuilder PostgreSQL integration, precise role/sequence neighboring, wrong scope/author, uncommitted messages, Arabic/symbol identities, edits/deletes and candidate/query/output limits. Independent root PostgreSQL fixture passed; combined pytest334 and strict Pyright passed. Existing skills test mock was updated with real required Thread fields; production checks were preserved.
- **Open:** broader history/cross-thread authorization, semantic message search and measured retrieval-quality acceptance. Bounded lexical candidate coverage is explicit; no global shared Agent memory was added.


## ENV-CHART-COMMAND-01 — Atomic native chart update receipts

- **Scope:** chart_set_symbol, chart_set_timeframe, chart_add_indicator, chart_remove_indicator and chart_annotate. Existing native ToolLoop, chart row/version transaction and EffectReceiptRow are reused; no new journal/schema/runtime.
- **Identity:** Run/call receipt namespace, with owner/Agent/thread/tool/validated-arguments digest. A lease fence validates current authority but is not the effect identity. Same call with changed intent or foreign receipt kind is rejected before touching current geometry.
- **Outcome:** mutation and configuration acknowledgment commit atomically. Replays return original configuration/revision, omit transient scene data and explicitly require current scene inspection. They never overwrite later manual owner edits or re-fetch historical data as if it were the original result. REST owner editing retains its existing response behavior.
- **Verified:** independent root PostgreSQL five-tool fixture; actual ToolLoop death after chart commit/before checkpoint, new fence, one effect, stale-worker denial, owner edits preserved, wrong scope/kind/arguments, invalid-batch rollback and no trading journal writes. Existing PostgreSQL drawing race and chart-tool integration pass;32 focused units/Ruff/Pyright pass. Existing integration fixtures now explicitly refresh/inspect through the real chart runtime before asserting current scene values.
- **Open:** persistent visual viewport commands remain separate work. chart_open creation receipts are verified separately in ENV-CHART-CREATE-01.


## ENV-SKILLS-AUTH-01 — Retained instruction authority at runtime boundaries

- **Repair:** current disable/removal/source/eligibility controls were previously rechecked when Skills context was rebuilt, but restored checkpoints and ordinary multi-tool turns could retain withdrawn instructions. ToolLoop now checks selected pinned instructions before each new handler effect and before every model turn, without waiting for steering.
- **Reuse:** existing registry, snapshots, resolver eligibility, Run metadata, fences and Task recovery. Eligibility logic is shared with initial selection. No new Skill table, registry, permission system or per-version control API.
- **Behavior:** withdrawal raises stable skill_continuation_unavailable and stores bounded reason diagnostics without clearing checkpoint, pending calls or immutable instructions. Current catalog updates do not silently upgrade the active Run. Same-source re-enable can continue its retained pending call. Completed result receipts and known same-operation financial reconciliation branches keep their existing priority; no new financial operation is authorized by this check.
- **Verification:** actual PostgreSQL ToolLoop two-effect checkpoint: first effect withdraws the Skill, second is blocked; a new worker still cannot bypass withdrawal; current source changes/removal are enforced; re-enable/newer catalog resumes the original pending identity with pinned old instructions and no repeated first effect. Model-only continuation and stale fences are checked. Scripted ambiguous-financial recovery uses the original call identity before subsequent model admission is blocked. Combined pytest334, strict Pyright, lint, Web build and Mobile types passed.
- **Limits:** controls take effect at subsequent runtime boundaries and cannot recall an already submitted external request. Legacy checkpoints with selected IDs but no trusted snapshot are blocked; checkpoints with neither selection nor snapshot cannot be retroactively verified by this retained-snapshot check. Exact per-version revocation is tracked in ENV-SKILLS-REVOKE-01. Evaluated candidate/adoption/rollback and broad quality benchmarks remain open. No live broker mutation, migration, APK or deployment.


## ENV-CHART-CREATE-01 — Atomic native chart creation and current read preparation

- **Reuse:** chart_open uses the same scoped ChartCommand/EffectReceipt transaction as five native updates. Existing REST chart creation is unchanged. Run/call/resource identity and validated original request are checked before stamping initial Agent drawings or creating a row.
- **Behavior:** initial creation/replay returns an immutable configuration acknowledgment, without broker history or transient scene claims. A later owner edit is preserved; changed intent conflicts; an older unreceipted row returns chart_creation_receipt_missing rather than pretending its current payload proves the original request.
- **Production read path:** chart_inspect, chart_read_indicator and new chart_snapshot generation can materialize an initializing scene once through the existing refresh lease. A concurrent gateway refresh remains explicitly initializing; ready scenes and real failed-source errors do not silently fetch again. Artifact replay still returns original bytes/provenance without refreshing. No test-only refresh is required for open→snapshot.
- **Verified:** actual PostgreSQL ToolLoop death after creation commit/before checkpoint, new-fence replay, stale worker, preserved manual edit, initial drawings, changed request, explicit legacy uncertainty, concurrent same-call creation and zero trades. Native immediate snapshots pass for exact forex/metal/index/crypto symbols and four frames. Existing Agent→market/chart/image/trade, chart tools, generated artifacts and actual Chromium snapshot/vision flows pass. Five preparation units and combined339 pytest pass; strict Pyright and Ruff pass.
- **Open:** persistent visual viewport/navigation, physical native client acceptance and external model-quality evaluation. No new schema, journal, APK or production deployment.


## ENV-SKILLS-REVOKE-01 — Exact-version owner controls and checkpoint binding

- **Contract:** owner-authenticated GET/POST `/agents/{agent_id}/skills/revocations`, shared typed Skill ID/semantic-version references, optimistic control revision and stable reason codes. One bounded configuration record in existing settings per owner/Agent; no new table, registry or permission grant. Maximum256 retained denials, exact version strings bounded64 characters; overflow fails explicitly without evicting earlier controls.
- **Lifecycle:** deny exact Skill ID/version independently of claimed source or content hash. Deleting/reinstalling an installed Skill cannot erase the control. Duplicate denial returns its original record without changing reason/time or emitting another event; distinct concurrent writes serialize on the Agent and enforce expected revision. Permanent Agent deletion removes its configuration; audit events retain their existing owner lifecycle. There is no automatic un-revoke or adoption endpoint.
- **Runtime:** selection checks the effective pinned/current version; dependency denial propagates through the existing resolver. A revoked old Run cannot silently substitute a newer catalog version. A fresh Run can select an unrevoked newer version. Controls apply at subsequent boundaries and cannot recall already submitted external requests. Skill denial never changes server tool/financial authority.
- **Crash boundary:** saved execution state retains the IDs of the instructions actually loaded with its messages. Metadata-only context refresh cannot authorize an older checkpoint after a crash. Steering updates that binding with its actual replacement block. Legacy checkpoints conservatively validate all retained definitions when an exact binding is absent; this may require owner recovery for unrelated old entries rather than guessing which instructions were active. New checkpoints validate only actual active IDs.
- **Verified:** authenticated PostgreSQL old-v1/new-v2 behavior, same-version content edits/source relabel/delete/reinstall, current checkpoint versus newer diagnostics, pending-effect prevention with no steering, wrong owner/Agent, forged metadata, stale fence, dependency denial, unused historical snapshots, optimistic concurrency, one event per denial, bounded overflow and Agent cleanup. Eight typed malformed/configuration cases plus combined347 pytest, zero-error Pyright and Ruff. Existing same-operation financial recovery retains priority; no real broker mutation.
- **Open:** owner UI for version controls, candidate generation, independent evaluation/adoption/rollback, measured quality and broader Task version-transition/retention policy. This is a working authenticated backend/runtime control, not completion of the Skills or learning program. No migration, APK or production deployment.

## ENV-SKILLS-DISCOVERY-01 — Next unimplemented boundary

Status: NOT_STARTED implementation; source/caller audit completed after exact-version controls.

Hermes tools/skills_tool.py at22063fc099ec9ad8357d7f8f6e6248a0400680d3 separates metadata-only skills_list from full skill_view. Lonora currently has deterministic instruction selection and explicit owner hints, but no Skill discovery/view entry in the canonical ToolRegistry. The next increment must enable natural-language discovery/progressive reading without requiring literal owner Skill commands.

Dependency constraints: tools cannot import AgentRuntime (the Agent already depends on tools); do not copy the registry into tools or create a second runtime. Agree one narrow injected access contract and reuse the current registry, actual available tools, owner/Agent/Run scope, pinned versions, revocations and shared budgets. Viewing instructions must also bind those actually admitted into the current exchange/checkpoint, so revocation and recovery remain authoritative. A tool result or Skill text must never grant missing tools or financial permissions. Full content should load only when selected, with bounded metadata catalogs first. Model-selected reads need real ToolLoop/restart/dependency/scope/budget acceptance, including after metadata/message checkpoint interruption.

Reference audit is inspiration only: no Hermes/gbrain code copied, no upstream test or comparative-quality claim. Candidate generation/evaluation/adoption/rollback follows this foundation and must reuse exact-version denial controls.
