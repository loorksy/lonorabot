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
- **Open:** authorized conversation-neighbor retrieval, broader evaluation corpus, measured retrieval quality and evaluated memory adoption. This increment does not close full knowledge/learning requirements.

## ENV-CHART-DRAW-01 — Durable typed drawing geometry

- **Sources/dependencies:** C01–C11, existing ChartState/CloudChartRepository, scoped chart tools and optimistic chart versions. Reuse the same chart/runtime/event path; no new runtime, broker mutation or schema.
- **Behavior:** legacy price/line/note formats remain valid. Time/price geometry adds price zones, rays, channels, Fibonacci levels, arrows and scenarios. `chart_annotate` supports an atomic add/update/delete batch with stable identities and bounded inert style metadata.
- **Authority:** Agents stamp their own attributed layer and cannot overwrite owner/manual legacy drawings or another Agent's layer. Scope filtering preserves actual account, exact symbol and allowed timeframes. Owner REST remains owner authority. Scenarios are visual annotations, never orders/approvals.
- **Persistence:** existing fenced transactions and chart row/version checks serialize updates. Invalid batches roll back. Duplicate stale commands fail with a version conflict without adding duplicate geometry; successful replay receipts are not yet implemented.
- **Verification:** 39 focused Python cases; eight SQLite symbol/timeframe combinations; independently repeated PostgreSQL atomicity, concurrent-writer, identity and zero-order checks. The saved server SVG shares the same ten shape kinds.
- **Open:** client rendering acceptance, durable command receipts, on-demand visual sessions and observed-image verification. Saved semantic geometry is not proof that a client displayed it.

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

Evidence: actual PostgreSQL chart_snapshot → artifact_read → same Run model pixels, interruption/restart with reference-only checkpoint, scope/integrity/MIME/dimension/size failures, five provider HTTP serializer tests including Anthropic ordering, and 36 focused image/context/result cases. HTTP payload acceptance is not proof that every configured external model supports vision or understands a particular chart. On-demand browser capture and source-provenance completion are the next integration; the current semantic image must not be called a TradingView screenshot.
