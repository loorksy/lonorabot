# End-to-end execution traces

Baseline: `5315a8cc634486d54b1a64c1fd211b3e46429f14` · Audit date: 2026-10-27 · Source: this checkout.

[System](COMPLETE_SYSTEM_AUDIT.md) · [Capabilities](COMPLETE_CAPABILITY_INVENTORY.md) · [Traces](END_TO_END_EXECUTION_TRACES.md) · [Diagrams](ARCHITECTURE_DIAGRAMS.md) · [Findings](FINDINGS_AND_RECOMMENDATIONS.md) · [Coverage](AUDIT_COVERAGE_MANIFEST.md)


## Scope and notation

These are selected source-connected traces, with concrete execution boundaries. They are not recordings of live production requests. **Not every significant workflow or every branch has received a complete semantic trace.** The capability registry and coverage manifest enumerate remaining source areas, including unreviewed client controls, adapter branches, contracts and tests. “Confirmed” below refers to a stored domain status unless expressly described as an observed audit result.

For each path, admission, external acknowledgement, independent verification and user-visible projection are kept distinct. Only local build/tests and the two isolated probes described in the system report were executed. No live financial operation, provider request, deployment or production-state mutation was initiated.

## T01. Bootstrap, login and request identity

**Trigger:** Web App opens or a native client signs in; first installation uses bootstrap.

**Path:** `apps/web/src/App.tsx:25` → onboarding status → existing-session lookup or onboarding/login UI → `apps/api/src/lonora_api/routes/auth.py:15` / onboarding route → owner/password/session helpers. Native login returns a bearer token; browser login sets session and CSRF cookies. `packages/auth/src/lonora_auth/sessions.py:14` issues random tokens and stores hashes/expiry; `apps/api/src/lonora_api/middleware/auth.py:16` resolves cookie/bearer identity and checks CSRF for cookie-backed mutations.

**Decisions/state:** bootstrap secret and singleton owner policy; valid password; session not expired/revoked; correct CSRF when required. Owner authentication also ensures the personal agent. Device-based grant activation is an additional proof flow, not a replacement for request identity.

**Effects/output:** owner/session/personal-agent DB records; browser cookies or native token; successful identity allows API work. Login failure returns an error rather than creating work. Logout revokes the session and clears browser cookies. Protected event transports periodically re-check sessions; not every transport edge was runtime tested.

**Confirmation/limit:** source path is wired; real browser/native login and DB constraints were not executed in this audit. Configuration such as secure cookies and allowed origin can prevent a deployment from working even though the routes exist.

## T02. Specialist creation and market binding

**Trigger:** Web agent-create panel or mobile `new` screen submits creation.

**Path:** `apps/api/src/lonora_api/routes/agents.py:34` → validates account/symbol input → owned enabled broker connection → broker symbol/instrument discovery → rechecks connection version → DB agent creation. `packages/db/src/lonora_db/agents.py:33` assigns the agent kind and binding. Personal-agent bootstrap and delegated child creation are distinct entry paths.

**Data/decisions:** name/appearance/instructions plus account ID and exact instrument; ownership, enabled connection, supported symbol and current configuration. Agent account/symbol scope subsequently constrains market, chart and financial tools.

**Effects/output:** persisted Agent and event/response. Invalid/unavailable broker metadata prevents specialist creation. This contradicts the README's “name/avatar/color only” claim (`README.md:31`). Source-connected, not broker-verified.

## T03. Text, attachment, reply or group message to final answer

**Trigger:** owner/client message; Telegram ingress eventually calls the same admission function.

1. Client submits thread ID, text, client nonce, optional reply/attachments/mentions/input answer. API returns admission status, not a generated answer (`apps/api/src/lonora_api/routes/messages.py:1`).
2. `send_message` locks the owned thread, checks nonce receipt and returns original identities on replay (`packages/db/src/lonora_db/messages.py:73`). Input-answer replays additionally check the exact original choice/question/content.
3. It validates reply belongs to the same thread, attachments belong to owner, mentions/group membership and optional collaboration session. It increments thread sequence and inserts MessageRow.
4. Direct conversations target the thread agent. Group messages prefer explicit mentions, then name mentions/replied agent, then first available member. Paused agents are skipped (`messages.py:234`).
5. Existing conversational work is updated/steered; waiting input can requeue the same Run. Otherwise a new Run is inserted. Message receipt + event + Run relationship commit together. HTTP acknowledgement includes canonical Run identities/activity.
6. Gateway workers call `claim_next`, serializing on thread and claiming queued/expired work with locks and a new lease fence (`packages/db/src/lonora_db/runs.py:128`). The lease identifies which worker may checkpoint/finish effects.
7. `execute_run` maintains lease heartbeat; `execute_tool_loop` restores messages/pending calls or invokes `build_context` (`packages/agent-runtime/src/lonora_agent/executor.py:33`; `tool_loop.py:165`).
8. `build_context` loads instructions, bound market, memory, scratchpad, environment, skills, reply/history, goal/decision and collaboration context. Attachments may supply images; optional semantic recall is bounded (`context/builder.py:36`).
9. Model routing selects current provider/capability and prepares each attempt. Tool calls are checkpointed. Dispatch validates the live tool schema, scope and lease before handler execution. Results and pending state are saved.
10. Final text/rich content passes public/privacy/financial truth projection. `complete_run` writes terminal state and durable reply; outcome-return handles linked work. Public event delivery reaches clients, which merge projections and refetch canonical state.

**Failure/recovery:** lease loss cancels the worker; stale fences cannot complete. Model/tool errors have specific failure/retry paths; unknown unreceipted mutations become uncertain rather than automatically replaying. Maximum rounds and continuation limits are persisted. New owner steering supersedes queued tool proposals and pending approvals before execution (`tool_loop.py:252`). A DB admission error rolls back the transaction; client nonce permits safe admission recovery, not arbitrary effect replay.

**Observed output:** immediate message/Run acknowledgement, provisional progress/stream, then durable answer or error/question/wait. A queued Run does not prove a provider response exists. Client timeline tests passed locally; complete DB/model/browser path is unverified.

## T04. Model attempt, fallback and tool execution

**Trigger:** no pending tool result or owner steering remains in the current turn.

`model_turn` refreshes routing context, applies operating/visual policy, prepares image observations, chooses conversation/background/vision capability and starts a turn-specific public stream. `GlobalModelRouter.complete` reads global routing/backups/context policy and stored catalogs, rebuilds context for each attempted selection, resolves provider credentials and invokes the concrete adapter (`packages/agent-runtime/src/lonora_agent/model_runtime.py:27`; `packages/providers/src/lonora_providers/router.py:30`).

Five adapter registrations exist (`providers/registry.py:9`). Only eligible `LonoraError` failures from the attempt block fall through to the next selection; preparation/credential-resolution errors occur outside that block. Thus “fallback configured” does not imply every configuration error can use it. This is a source boundary to document/test, not a confirmed incorrect policy.

Tool discovery initially publishes a small schema set; successful exact schema inspection admits additional names. All handlers remain subject to execution-time validation. `ToolRegistry.execute` normalizes market-bound arguments, validates the Pydantic input, enforces scope and scopes the result (`packages/tools/src/lonora_tools/registry.py:157`).

The loop persists an in-flight marker before calling an effect handler. Existing stored results win; financial replay-safe handlers may inspect their own durable journal instead of freezing an ambiguous observation. Other uncertain mutations are reported as uncertain. Retry metadata carries a deadline and bounded attempts, releases the worker and later resumes the same durable work (`tool_loop.py:291`).

Large results (>120,000 serialized characters) use a bounded summary and stored-result retrieval. Failure to store presentation data does not re-execute the underlying mutation (`tool_loop.py:460`). Model token usage/context diagnostics are persisted. Proposed financial tool calls suppress premature success prose; unverified financial outcomes replace unsupported claims (`model_runtime.py:159`). Actual provider API behavior remains unverified.

## T05. Questions, steering, cancellation and recovery

**Trigger:** `wait_for_input`, explicit approval wait, user message while running, cancel route, worker loss or retryable error.

- A tool's accepted input request is checkpointed with exact call/question identity; the executor yields waiting state. A choice answer validates pending Run/question/choice and exact label, then requeues the same Run (`messages.py:132`). Free-form steering is distinct from approval.
- Owner steering invalidates stale pending calls/approvals, appends corresponding tool-result observations, then merges the new message after the complete tool block (`tool_loop.py:252`). It does not splice a user message between a tool call and its result.
- Root cancellation locks the thread/Run, changes status, settles stream and increments fence. It also cancels immediate children (`packages/db/src/lonora_db/cancellation.py:13`). Grandchildren are not recursively queried in this function; full-tree cancellation semantics remain a risk/open contract question (F-09).
- Worker lease expiry allows a new claimant with a higher fence. Recovery restores checkpointed messages/pending calls. The current Run's lease check is not a guarantee that every ancestor remains active.
- Tool retry queues the same execution with a future retry deadline; finite Task continuation can extend the compute slice budget up to four slices. It does not create a new financial operation identity (`packages/agent-runtime/src/lonora_agent/continuation.py:50`).

**Confirmation:** durable status/fence/events, not merely a client spinner disappearing. Cancellation cannot undo a broker action already sent; that boundary uses journal/reconciliation. No live race or DB concurrency test was run.

## T06. Durable Task, wait, wake and origin-thread outcome

**Trigger:** `task_start` / task API, or signed full-account-management activation.

`create_task` validates owner/agent/origin, creates BoardRow, a dedicated work Thread, a TicketRow carrying typed TaskState and a `tickets` Run; it stores run/task/origin linkage (`packages/db/src/lonora_db/tasks.py:94`). Task state is not synonymous with one Run's transport state. `control_task` uses optimistic version and locked current Run to pause/resume/revise/cancel, including separate failed-attempt recovery branches (`tasks.py:315`).

`prepare_wait` validates a real owned watch or bound broker-recovery source, or stores a timer deadline, and persists an idempotent wait receipt (`packages/db/src/lonora_db/task_wait.py:21`). The tool loop cancels unexecuted sibling proposals so stale financial intent cannot survive across a wait. Executor suspends the Run. Scheduler invokes `resume_ready_waits`; a matching source observation and call identity requeue the same waiting Run, recording wake/consumption receipts (`task_wait.py:82`; `packages/gateway/src/lonora_gateway/scheduler.py:8`).

Continuous tasks have a bounded stop gate: an ordinary final answer does not complete an ongoing responsibility. Two saved nudges can request a real wait, then failure `task_wait_required` is raised; persisted counters prevent restart from buying unlimited nudges (`packages/agent-runtime/src/lonora_agent/stop_gates.py:55`). Task plan revisions can reset the review epoch.

Terminal outcomes return to origin/parent conversations through `return_outcome`; maintenance calls `return_pending_outcomes` to repair missed projection (`packages/agent-runtime/src/lonora_agent/collaboration/outcome_return.py:28`, `:306`). A terminal attempt must not overwrite owner cancellation (`packages/db/src/lonora_db/tasks.py:69`). Source-connected; all retry/failure/outcome branches and database races remain incompletely inspected/tested.

## T07. Routines, market watches and webhook initiation

### Scheduled routines

API/tool creates a validated cron/timezone or interval Routine with an owned agent and work/goal thread. Scheduler's `dispatch_routines` transaction selects enabled due rows for unpaused agents with skip-locked locking; it validates goal plan/source versions and creates `routine` Runs (`packages/db/src/lonora_db/routines.py:88`). It advances next occurrence from the prior schedule, collapsing missed periods to one wake rather than replaying a burst (`routines.py:168`). Output is a queued Run, followed by ordinary execution/outcome paths. Cron evaluation, DST and concurrency were not exercised here.

### Market watches

Gateway polls or receives market updates. Observation code requests the exact bound quote/candles/account/calendar/detector inputs, checks freshness/health and separates source time from processing time (`packages/market/src/lonora_market/watchers.py:50`). It checks version/enabled state after external reads, rejects older source observations, advances watch lifecycle and cooldown, then deduplicates wake identity.

A Task-owned watch creates evidence for scheduler resumption; it does not enqueue a competing watch Run. Ordinary watch matches create a `watch` Run plus MarketWakeReceipt with source metadata; goal-linked matches also validate current plan/step (`watchers.py:634`). Unhealthy data records an unavailable/stale watch state and next check, rather than asserting a valid signal. This creates analysis work, not automatic proof that a subsequent trade is permitted.

### Signed inbound webhook

`apps/api/src/lonora_api/routes/webhook.py:1` verifies raw-body HMAC through the channel helper, parses the declared run/nonce and reaches durable run creation. It is a separate integration entry point from outgoing Webhook delivery. A valid signature establishes the integration secret was used, not successful model execution. Malformed signed payload behavior and complete input parity remain unverified.

## T08. User intent to real broker execution, receipt and reconciliation

### Entry routes and authority

There are three important origins:

1. **Direct owner action:** authenticated `POST /api/trading/execute` calls `ExecutionService.execute(owner, request)` without an agent lease (`apps/api/src/lonora_api/routes/trading.py:105`). This is an owner API, not model authority.
2. **Agent tool:** `trade_execute` discards model-supplied operation identity, normalizes symbol and derives stable identity from Run + request hash; Shadow branches before live approval (`packages/tools/src/lonora_tools/trade.py:269`). `approved_execution` either finds a current standing account grant or creates/uses an immutable per-call approval.
3. **Goal step:** `execute_goal_step` binds operation to goal, plan version, step, decision and attempt; it uses the shared executor with additional goal guards (`packages/trading/src/lonora_trading/goals.py:301`).

### Explicit approval path

`approved_execution` checks live financial-agent eligibility and lease, snapshots management targets and stores the exact reviewed request list in TradeApprovalRow (`trade.py:57`). Pending status returns runtime wait/retry metadata. Web/native approval controls call the owner decision endpoint. `decide` checks owned approval, current Run and pending call before setting approved/rejected and requeuing a waiting Run (`packages/db/src/lonora_db/trade_approvals.py:41`). Typed/spoken agreement alone does not call this endpoint.

The resumed handler deserializes frozen requests. Before each execution its authorization callback checks current lease, approval status, exact request fingerprint, no pending owner steering and unchanged target material state (`trade.py:164`). Results are persisted incrementally to the card and finally the approval is completed.

**Confirmed defect:** the explicit-approved multi-request loop lacks a stop when a result is ambiguous/failed. It proceeds to later requests, unlike standing-authority execution which breaks unless confirmed (`trade.py:260`). A local probe of the actual function confirmed two calls after an ambiguous first result and terminal approval completion. This does not prove the first operation succeeded or that later operations are unauthorized. See F-01.

### Shared executor and exact external mutation boundary

`ExecutionService.execute` (`packages/trading/src/lonora_trading/execution.py:126`) follows this order:

1. If agent-originated, check current goal/agent/ancestry/market lineage. Look up operation ID. Existing operation must match owner, request fingerprint and live mode; return its current receipt rather than resend.
2. Capture owned broker configuration/version, authorization callback, global trading controls and planned preflight snapshot.
3. In DB transaction, recheck connection/version/enabled state and lease; validate authority/goal where applicable; reserve operation and persist `submitted` with planned evidence and server-derived origin.
4. Hold a PostgreSQL per-owner/account advisory lock for the external mutation attempt. This serializes distinct operation IDs; it does not turn a network call into an atomic DB transaction.
5. Call `broker.execute(request, before_send)`. The adapter performs preparation, then invokes `before_send` immediately before the SDK mutation.
6. `before_send` revalidates authorization and fresh preflight/quality; global controls, connection/recovery status, lease/lineage, current target, grant/goal limits and optional entry thesis. Persist `send_authorized=True` before allowing mutation (`execution.py:231`).
7. MetaApi dispatches concrete SDK calls: market buy/sell, pending limit/stop, close/partial close, modify position/order and cancel order (`packages/adapters/src/lonora_adapters/brokers/metaapi.py:773`). It normalizes return codes, broker IDs and partial execution; transport uncertainty becomes ambiguous.
8. Correct same-operation confirmed result with authorized send is persisted **before** independent post-state checking. A failed verification read must not erase a true broker acknowledgement (`execution.py:380`).
9. `verify_effect` reads current positions/orders under a bounded deadline and compares expected target/volume/stops/order changes; it can report verification pending separately from acknowledgement (`packages/trading/src/lonora_trading/verification.py:14`).
10. Persist final result/evidence; update linked goal/opportunity decisions where applicable; return through tool/API/card/journal and durable event/client refresh paths.

**Failure/cancellation:** domain failure before the send boundary is failed; uncertainty after send and transport errors are ambiguous. Cancellation after the attempt is conservatively persisted as ambiguous before propagating. A result with wrong operation identity or without authorization is not accepted as ordinary success. Journal terminal confirmed/failed receipts cannot be regressed by late writes (`packages/db/src/lonora_db/trading_journal.py:66`).

### Reconciliation and what “confirmed” means

Maintenance scans due live ambiguous and old submitted operations, skips still-active Run leases and asks broker reconciliation (`packages/trading/src/lonora_trading/reconciliation.py:25`). MetaApi correlates current/history evidence using broker/client operation identity, symbol and target/deal characteristics. Bounded history/truncation or absence of a match is uncertainty, not definitive rejection (`metaapi.py:916`). Modification/cancellation returns `mutation_evidence_required` rather than guessing (`metaapi.py:974`). Backoff controls repeated evidence reads; it does not resend the order.

Journal `confirmed` is acknowledgement evidence; `verification` records independent observed effect. Neither a model saying “done”, a tool being registered, an HTTP 202, nor a plan step being proposed establishes real settlement. This audit traced the source to the SDK boundary and return/reconciliation paths but **performed no real broker call**.

## T09. Signed grants, goal planning and account management

**Trigger:** owner reviews a plan/account envelope, supplies device assertion, then activates authority.

Auth challenge binds owner session, request kind, envelope hash and expiry; assertion validates registered device, RP/origin, signature/sign count and required user verification (`packages/auth/src/lonora_auth/devices.py:138`; `packages/auth/src/lonora_auth/account_authority.py:40`). The resulting durable grant specifies account/symbol/actions/limits. Full account-management activation starts a continuous Task; advisory/supervised/autonomous goal modes remain distinct.

`available_authority` refuses standing authority for goal-bound or provisional voice ancestry. `require_account_execution` rechecks active grant, exact bound account/action/symbol, action budget, unresolved account journal entries and current snapshot (`packages/trading/src/lonora_trading/account_authority.py:39`, `:86`). The shared send boundary repeats these checks. Revocation/expiry/current broker state can block an operation after earlier proposal.

Goal state advancement depends on declared steps and actual decision receipts. `guard_goal_execution` checks goal active, Run/thread/agent binding, current plan version, exact declared trade and decision operation/attempt; goal autonomous limits and signed authority are enforced again (`packages/trading/src/lonora_trading/goals.py:118`). Unknown targets can wait for broker evidence and scheduled review rather than fabricating IDs. Full activation/recovery/target-resolution paths are partially reviewed and not runtime verified.

## T10. Simulation, Shadow, research, decisions and opportunity state

**Simulation:** explicit imported snapshot data feeds the simulation adapter and its configured broker connection. It is a test/data mode, not a default real account. Import source and adapter semantics are inventoried but not all branches reviewed.

**Shadow:** `trade_execute` can dispatch to `execute_shadow`; this checks current Run/agent mode, exact binding and mode-specific operation identity. `ShadowReadView` uses broker account/market reads but returns virtual positions/orders. Entry requires appropriate recorded decision/evidence; mutations store virtual state and a Shadow-labelled journal (`packages/trading/src/lonora_trading/shadow.py:101`). Gateway `advance_shadow` evaluates later market movement against virtual state. No broker financial mutation is established by Shadow success.

**Research:** validated finite instrument/candle data → chronological research windows → training candidate selection → validation selection → untouched test folds → aggregated costs/equity/drawdown and closed-trade resampling. Saved outputs include configuration/data/result identities and declared limitations (`packages/market/src/lonora_market/research.py:159`, `:247`, `:370`). Resampling is not a future profit probability, and research does not call `ExecutionService` as a trading side effect.

**Opportunity:** recorded supporting/contradicting decisions and watchers define evidence for a versioned thesis. Update cannot directly claim acted_on/completed; linked journal receipts drive those states (`packages/trading/src/lonora_trading/opportunities.py:158`, `:224`). Linked entries must be current/confirmed and cannot reuse an unresolved/acted-on entry; protective exits still pass normal execution controls. `thesis_id` is optional, so this is not a universal prerequisite for every live trade. Full analytical correctness and Shadow settlement cases remain unverified.

## T11. Charts, snapshots and rich results

**Trigger:** owner opens/edits a chart or the agent calls chart tools; model emits a structured visual response.

Chart commands update owned/versioned chart state and receipts, then runtime materializes scene data from broker/history/indicators. Web iframe and native WebView render the scene and use revision-aware bridges. Snapshot capture is a separate server capability: bounded Chromium capacity/context, allowed resource URL/method restrictions, blocked WebSockets, exact chart/version/data-revision readiness, screenshot and PNG validation (`packages/charts/src/lonora_charts/visual.py:241`). A chart record existing does not prove its scene or snapshot rendered.

Rich reply compiler accepts typed structure and resolves fact references from actual tool observations/resource ownership. Providers cannot inject compiled rich data; model runtime clears it before projection (`packages/agent-runtime/src/lonora_agent/model_runtime.py:143`; `visual_response.py:219`). Web/native components consume the compiled document with shared TS evaluators. These are distinct from arbitrary HTML artifact previews, which receive restrictive sandbox CSP (`apps/api/src/lonora_api/routes/artifacts.py:83`).

**Outputs:** chart state, scene revisions, rendered client content, optional image artifact and durable rich message. Web/Expo build success verifies bundling; no screenshot/interactive renderer/device run was performed. Remaining renderer/expression/source-provenance branches are explicitly outstanding in the manifest.

## T12. Realtime voice, handoff and incoming calls

**Trigger:** Web/native owner starts a call with local microphone/peer transport.

Client creates an offer and requests a voice session. Server validates owned thread/agent/nonce/offer identity, serializes owner admission and commits an allocation receipt before provider I/O. Adapter creates the remote live session; remote ID/answer SDP are stored. The server waits for Gateway attachment before returning ready SDP (`packages/voice/src/lonora_voice/sessions.py:73`; `packages/adapters/src/lonora_adapters/voice/realtime.py:1`). Media travels through the configured WebRTC/provider path; Gateway controls/observes the live session separately.

`RealtimeVoiceSession` accumulates ordered transcript fragments, stability/correction state and deduplicated handoffs; `delegate` calls canonical message admission in the same agent/thread rather than a separate financial executor (`packages/voice/src/lonora_voice/realtime.py:180`). Provisional speech metadata propagates through ancestry and cannot spend standing authority; explicit approval controls remain necessary. Corrections can supersede pending proposals. Barge-in, shutdown compensation and result delivery have dedicated modules; full media/provider behavior remains unverified.

**Incoming calls:** attention + opt-in policy + verified device + scope/quiet/rate/expiry checks → durable ringing state/event → client in-app overlay (`packages/voice/src/lonora_voice/incoming.py:140`). Gateway calls `incoming_tick` with no delivery implementation. It handles expiry/consent, but skips provider send (`incoming.py:333`). Provider acknowledgement, device presentation and owner acceptance are distinct states. The normal runtime cannot be described as delivering background phone notifications merely because an overlay/Protocol exists.

**Validation:** selected mobile transport/readiness local tests passed, including teardown/startup races. They use explicit stand-ins and establish neither real WebRTC negotiation nor the availability of the provider endpoint currently named in source.

## T13. Channels and public event projection

**Telegram ingress:** enabled owned integration + encrypted token + allowed destinations → `getUpdates` → decode → `send_message` with external identity → update offset in transaction (`packages/gateway/src/lonora_gateway/event_dispatch.py:30`). It enters the same durable conversation machinery.

**Outbound:** committed assistant/attention event → integration cursor and destination list → `EffectReceipt(status=submitted)` → commit → remote send → store result (`event_dispatch.py:76`). Only relevant active/mandatory attention is sent. Webhook adds HMAC of exact JSON bytes and disables redirects.

**Known gaps:** the result merge lets numeric webhook `status` overwrite lifecycle status (F-02). Cursor/receipt commit precedes transport, while any existing receipt suppresses re-attempt; crash/timeout delivery is not repaired by this dispatcher (F-05). No exactly-once delivery guarantee is established. External calls were not made.

**Client events:** `publish_committed` assigns a serialized public cursor to committed events before owner-scoped replay (`packages/db/src/lonora_db/events.py:28`). SSE/WS consumers retain cursor/projection state and reconnect; Web ClientProvider additionally refreshes every 15 visible seconds, on reconnect and visibility/online events (`apps/web/src/providers/ClientProvider.tsx:16`). These mechanisms are separate from outgoing chat-channel delivery.

## T14. Workspace execution and executable skill admission

**Trigger:** workspace tool or exact-version skill utility validation.

Tool → current lease/agent workspace access → versioned file/revision checks → Unix-socket `WorkspaceClient` → separately provisioned `workspace_host` → bounded ephemeral container → output/updated revision/artifact receipt (`packages/agent-runtime/src/lonora_agent/workspace_access.py:1`; `workspace_client.py:21`; `workspace_host.py:26`; `workspace.py:178`). The client has bounded requests/responses/timeouts and does not automatically replay uncertain execution.

Host/container code specifies pinned image identity, no external network, read-only base filesystem, resource/capability restrictions and temporary writable working areas. This is source-level containment configuration, not an adversarial sandbox verification. Normal production Compose requires an optional host-service overlay to reach it.

Package import/create stores versioned files and hashes. `validate_package` executes a declared Python utility against the exact revision and records source hash/image/arguments/exit code. `control_package` activation rechecks source, graph, revocation and current validation image; rollback restores disabled source, and removal retains source files (`packages/agent-runtime/src/lonora_agent/skills/lifecycle.py:347`). A smoke pass is evidence of that command only, not general package correctness. No such host/container execution was performed during this audit.

## T15. Artifact upload, retrieval and deletion

Owner upload → bounded file read/size/name/path handling → create directory/write bytes → DB artifact creation/reference checks → metadata response (`apps/api/src/lonora_api/routes/artifacts.py:20`). Attachment messages subsequently reference owned artifact IDs. Download checks owner-scoped metadata, confined path and existence; previews whitelist types and apply sandbox/no-script CSP.

**Failure gap:** bytes are written before thread reference checks/transaction success, with no local compensating unlink. DB rejection leaves unreferenced bytes. Generic resource deletion deletes the row/events, not the underlying filesystem object (`packages/db/src/lonora_db/transactions.py:211`). Generated-artifact repair modules do not establish a general filesystem garbage collector. See F-04; no user artifact was created or deleted during validation.

## T16. Mobile release and OTA consumption

**Trigger:** native startup/update check; operator offline release procedure is a separate path.

Expo config declares HTTPS update URL/channel, fingerprint runtime version, embedded RSA signing certificate and next-launch behavior (`apps/mobile/app.config.ts:52`). Client checker rate-limits concurrent checks, downloads available update/rollback and never forces reload into an active conversation (`apps/mobile/lib/ota-checker.ts:1`).

Server read-only update route validates protocol/platform/channel/runtime, resolves immutable release pointer, rollout selection and requested content-hashed assets; no-update can return 204, rollback uses the update protocol response (`apps/api/src/lonora_api/routes/mobile_updates.py:1`). Secure storage uses bounded no-follow path traversal; syntactic signature metadata is not equivalent to client cryptographic verification. APK/app-association endpoints are separate public delivery surfaces.

**Confirmation:** a downloaded response is not proof a signed native build installed/applied the update. Audit built JS bundles and ran checker tests; no signing keys, real release publication, APK install, device passkey or next-launch activation were used. Release/signing helper internals remain partly unreviewed.

## T17. Installation, migration, backup and shutdown

Repository scripts/containers define dependencies and entry commands. The audit inspected configuration without running installers, destructive restore, deployment or existing-data migrations. Production API waits for DB health; Gateway depends on API health; Caddy proxies public traffic (`infra/compose/docker-compose.prod.yml:16`). These checks do not prove Gateway readiness (F-03).

Backup captures DB/files and checksums; restore explicitly requires `--replace`, validates archive members and restores the original encryption key plus DB/artifacts (`scripts/backup.sh:1`; `scripts/restore.sh:1`). Syntax checks passed, operational recovery did not run. Concurrent-write backup consistency and failure recovery remain unanswered.

Gateway stop transitions running → draining → stopped, drains/cancels tasks and closes resources (`packages/gateway/src/lonora_gateway/service.py:184`). A process kill can leave leased Runs, submitted/ambiguous financial operations, voice/channel uncertainty and partial filesystem work; each has different recovery semantics described above. There is no single universal “retry everything” path.

## Trace completion backlog

The above paths account for principal observed execution families. They do not exhaust every meaningful branch. Outstanding detail includes all model-adapter response/error variants, every Pydantic/TS contract edge, all Task/goal/Shadow transitions, full market mathematics and detector/indicator cases, every UI interaction and native permission failure, complete MCP protocol behavior, executable-workspace adversarial containment, every migration transformation and most tests. Exact source scope is not hidden: see statuses `I` and `T` in [AUDIT_COVERAGE_MANIFEST.md](AUDIT_COVERAGE_MANIFEST.md).
