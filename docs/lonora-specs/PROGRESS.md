# Progress

## Current wave

2026-10-16: signed device authority integration in wave 4; waves 1 and 2 integrated; shared historical evidence, thesis, explicit Shadow mode and Task failure/recovery integration in wave 3 on `feat/coherent-agent-foundations`, audited base `895eaa8`. All 18 original references remain intact. This is **not completion of the full program**. Source-section matrix distinguishes partial integration from full acceptance.

## Active workstreams

Root owns integration after the scoped parallel foundation work: identity/skills; task/work lanes; collaboration/mentions; market integrity/detectors; financial revalidation/manual broker observations; shared chat/live state. Shared schema and ToolLoop changes have one integration owner. No parallel agent is currently executing.

## Integrated foundations

- Personal identity bootstrapped idempotently; specialist exact-symbol authority preserved.
- Selective validated skills, immutable constitution, packaged playbooks, bounded provenance diagnostics and validated installation API.
- Ticket-based tasks and same-Agent work threads; conversation capacity; cooperative controls; step completion references actual persisted successful tool results.
- Canonical inbox and shared timeline with durable approval anchors; reconnect/loading/scroll improvements and native voice admission guards.
- Canonical quote/candle/account health; suspended/recovered watches; versioned deterministic level/zone/trendline/candle/composite detectors, expiry, hysteresis and confirmation lifecycle.
- Durable collaboration, stable mentions, actual peer records and outcome return; session-only `@all`.
- Serialized final execution revalidation, measured exposure/quality; stale management approvals invalidated after material owner changes.
- Broker recovery and manual-position/order observations; read-only background analysis in internal work threads, actual activity retrieval, deduplicated result return to Personal conversation.
- One derived live-state projection consumed by Agent context, voice, API, Web and Mobile. Speech interruption does not cancel financial/background work.

## Commits already recorded

`0c88299` references/graph; `b6ad9a5` health; `0e1cc27` execution quality; `864aa8c` tasks; `1146d30` skills; `8a433ef` identity/timeline schema. Integration commits: `a3a1760` dynamic watches; `5472796` collaboration/broker/task/live-state integration; `f3e804c` shared clients; `c7cf0de` isolated checks and matrix.

## Migrations

0018 identity/timeline and steering uniqueness; 0019 collaboration/mentions; 0020 material broker snapshot on approvals; 0021 explicit internal work-thread purpose. Applied to disposable PostgreSQL only; no production migration/deployment in this task.

## Checks completed

- Build: `bash scripts/build.sh`, including Python checks, seven client packages and Expo Android/iOS/Web exports.
- Python: 95 pytest cases passed after integration, including real PostgreSQL voice/skills tests and manual-activity/dynamic-watch/task cases.
- Skills: 29 focused cases and authenticated PostgreSQL installation checks.
- Task state: all five cases passed on SQLite and isolated PostgreSQL, including persisted tool evidence.
- Node: 15 timeline/native readiness/transport/OTA cases passed.
- Browser: 18 Web and six Expo Web tests. These do not certify native Android behavior.
- PostgreSQL integration: streaming, clients, binding, collaboration, trading, approvals, pending orders, execution quality, account recovery, goals, market health/runtime/dynamic watches, chart streaming/history passed in isolated databases. Original MetaApi SDK recovery suite preserved and passed separately.
- Ten additional existing regression suites passed (team, group replies, broker discovery/binding, MetaApi, broker history/recovery/orders, charts and generated artifacts). Two assertions were updated for the explicit directory scope fields and earlier Agent ownership rejection; private-data and owner-isolation checks remain.
- Latest account work-lane test passed: actual manual ticket read, observe-only authority, isolated work thread, one returned conversation result, owner SL intervention, reconnect and deduplication.
- Ruff passes. Pyright reports zero errors; client type checks and lint passed; all retained integration scripts and the new isolated foundation runner passed after work-lane integration. After the historical-evidence integration, the full build, Pyright, 95 pytest cases, all 18 Web tests and all six Expo Web tests passed. Expo Web used a fresh disposable database to exclude old interrupted chart fixtures.

No live-money test, real broker mutation, VPS deployment or native runtime claim. Integration branch has been pushed; draft PR: https://github.com/loorksy/lonorabot/pull/2 . Main was not merged.

## Historical evidence integration

New typed market decisions capture real broker quotes, candles, account, positions/orders and the same canonical health assessments. Server freshness/missing-data gates force WAIT; records never grant execution authority. Existing durable events and effect receipts preserve an immutable logical decision without a new execution journal or migration. Read/history/compare tools and owner API replay stored evidence, not current prices; summaries are bounded in Agent context.

Simulation/PostgreSQL checks passed for exact forex/metal/index/crypto symbols and multiple frames, idempotent identity/intent conflict, stale/missing data, historic price immutability, material deltas, specialist/owner isolation, retained records after connection deletion, and actual AgentRuntime → global router → tool → gated result → chat.

This is a partial foundation for specifications 08/09/11/16. It does not yet supply thesis lifecycle, automatic capture of every trade/management decision, collaboration fusion, shadow execution or performance intelligence.

## Remaining implementation, not external blockers

Versioned decision/evidence snapshots and opportunity/thesis lifecycle; shadow lifecycle/performance; attention policy/coalescing; measured intermarket relationships; advanced market engines; Super Bot proposal/trusted device authorization; collaboration evidence fusion/fresh final market validation; full task retry/recovery policy; dependent UI and end-to-end acceptance. None is silently deferred or marked complete.

## Remote CI

GitHub Actions run 38775590819 did not start any build step. Its check annotation states: "The job was not started because your account is locked due to a billing issue." This is an external runner/account blocker, not a passing remote CI result. Local checks above were actually executed. No attempt was made to modify billing/account settings.

## Concrete blockers

Physical Android voice/keyboard/OS-authentication acceptance requires a device/emulator (no attached device or KVM here). Real order-flow/depth/official speech sources require actual supported feeds; unavailable evidence stays unknown. Production deployment is outside the branch-only instruction.

## Next integration point

Evidence build/browser checks passed and the vertical capability is committed (`4deae52`). Continue by extending the same decision/evidence foundation with thesis identity/lifecycle and pre-trade confirmation linkage before opportunity memory, shadow/performance and attention. Preserve current controls, approval authority, exact broker symbols and no-blind-retry journal semantics throughout.

## Review findings integration (continued after 1209f41)

The new continuation document is preserved unchanged. Root resumed saved edits after the connection interruption; scoped agents could begin review work but their execution quota ended, so root owns integration and remaining implementation.

- R1 VERIFIED: source timestamps (including candle-close boundaries) govern watch TTL and debounce. Processing time stays separate. Already stale confirmation cannot wake an Agent. Intrabar corrections may change a predicate without renewing the bar's source time.
- R2 VERIFIED: session rounds have deterministic identities and one durable synthesis run. Concurrent participant completion/repeated return accumulates actual guest messages before scheduling. A synthesis cannot recursively schedule itself; Run ancestry preserves financial authority checks.
- R3 VERIFIED for server/Web/Expo-Web-compatible projection: cancellation remains cancelled across TaskState, ticket payload, outcome replay, restart/API reads and live state. A materialized terminal projection migration repairs old contradictions; generic ticket APIs cannot rewrite task state. Web uses task controls rather than the generic ticket editor for durable tasks. Native hardware acceptance remains separately blocked.
- R4 VERIFIED: new Personal/unbound-parent children are explicit delegated research identities. They can read authorized account state but cannot propose/execute arbitrary trades or create financial goals. Descendants and peer Run ancestry cannot launder this authority; deleting an intermediate parent retains the nonfinancial role. Specialist children retain exact bindings.
- R5 VERIFIED: new objectives receive new lineage-bound sessions. Continuation is explicit, `@all` captures its session identity in Web/Mobile, and retries do not duplicate sessions/rounds.

Evidence: check_review_findings (four PostgreSQL groups, three participants and nine duplicate deliveries); check_delegated_scope (three simulation/PostgreSQL groups); source-time unit tests plus actual PostgreSQL watch/restart checks; Web cancellation/reload/control test; two Node mention-session tests. Python suite passed 103 before the additional intrabar correction case; Pyright and client types passed at this review checkpoint. Retained broker/trading/collaboration tests passed through dynamic watches; chart streaming regression exposed the equal-source intrabar case, which was fixed and all eight chart streaming groups then passed. Full final gates continue with the next integration waves; this is not completion of 01–18.

Migrations added: 0022 delegated scope/backfill (orphan descendants remain nonfinancial), 0023 task outcome projection repair. No production deployment or main merge.

Next: continue the shared thesis/opportunity/decision capability, then shadow/performance, attention/relationships, remaining collaboration/authorization/task recovery and dependent clients. REMOTE_CI_BLOCKED_EXTERNAL remains distinct from LOCAL_TESTS_PASSING; Android acceptance stays BLOCKED pending actual Android runtime.

## Thesis/opportunity integration

Shared typed opportunity identity and versioned thesis definition now reference the existing immutable decision ledger. One queryable row represents the same scoped setup across wakes; full transition versions/evidence remain in durable events. Confirmation rechecks authoritative source freshness and optional watch confirmation; explicit horizon/decay and watch invalidation/expiry affect actionability independently of SL. Meaningful automatic transitions create one read-only same-Agent work-lane wake and return actual results to the originating conversation.

`TradeRequest.thesis_id` passes through the existing approvals/executor/journal. Final pre-send checks reject stale/contradicted/unconfirmed scope, reserve an entry identity, and verified broker receipts drive acted-on/full-close state. Partial exits do not claim full completion. Pending ambiguous entry reservations stay blocked until reconciliation. Optional absent thesis IDs preserve legacy financial fingerprints and tool operation identities. No new trade executor, market runtime or evidence database.

Migration 0024 adds queryable opportunity scope/status/horizon. Tools/API provide bounded current/history projections and exact historical version retrieval. Agent context contains bounded active thesis pointers rather than rebuilding the setup from chat.

Evidence: check_opportunity_runtime passed for four asset classes/exact suffixes, persistent identity, confirmation/invalidation/history, expiry without SL, source degradation, restart/API state, one deduplicated read-only wake, bounded context, actual approve→entry→partial/full exit and duplicate-entry prevention. Existing check_trade_approvals passed all eight groups. Python suite passed 106; latest Pyright verification is being finalized. No production broker mutations. Broader regime transitions, all-source evidence fusion, shadow/performance and dependent UX remain open; this is not full 01–18 completion.

Next dependency: explicit shadow/live separation in the shared journal and persistent Agent authority, virtual lifecycle against real source data, then reproducible performance dimensions. Shadow outcomes must never enable financial authority.


## Shadow execution / performance integration (current wave)

Persisted owner-selected execution mode now follows Agent creation and Run admission. Shadow commands reuse shared preflight and the durable execution journal with explicit mode isolation; they never call live broker mutations. Existing trade tools route Shadow actions into virtual positions/orders, deterministic sampled-quote pending fills, protection and partial/full exits. Virtual cancellation works during broker outages. Existing Gateway market maintenance restores and advances virtual rows without browser/model participation.

Historical decision identity/evidence, exact broker symbols, source timestamps, thesis snapshot/version when linked, planned and actual entry quotes and explicit data granularity are retained. Four quality dimensions remain separate. Performance aggregates are bounded, require at least 20 observations before repeated-pattern conclusions, and never equate price return with dollar profit or analysis correctness. Missing currency/contract valuation stays unavailable. Virtual history and live observations are separate API/tool selections. Owner Web/Mobile settings expose mode and virtual history; mode changes pause goals and never enable autonomy. Old Shadow Runs cannot gain live authority by a later owner mode change.

Migration 0025 extends existing Agent/journal modes and adds durable virtual trade state. Focused integration passed across forex, metal, index, crypto; all four pending types, offline cancellation, sampled pending fill/target/stop, partial exit, replay/restart and zero real broker mutations. Full pytest on an isolated migrated PostgreSQL database passed 109 tests; initial bare pytest failed because voice tests require explicit test database environment, corrected without disabling tests. Ruff, Pyright, client types, lint and full build passed. All six Expo-Web browser tests passed, including persisted Shadow toggle. Full Web browser suite passed 20 tests after fixing the asynchronous control assertion and reusing authenticated worker sessions instead of consuming the production login throttle. All isolated foundation integrations and all 16 retained runtime/broker/trading/market suites passed. The legacy pending-order fingerprint expectation now explicitly excludes the new absent thesis field. Partial exits aggregate price return by original volume; replay of close-all freezes its original target set and receipts.

Remaining in this capability: Shadow goal orchestration through the same existing goal engine, richer evidence-derived quality scoring and measured session/regime/strategy analytics, full replay presentation. Native hardware acceptance and remote CI billing remain external blockers; they do not block continuing repository implementation. No main merge or production broker mutation.


## Task failure / recovery integration

The existing Task/Ticket/Run checkpoint now persists a bounded retry policy, actual failure code/step/attempt, recoverability and next retry time. Default policy requires owner action. Automatic backoff is permitted only for declared read-only remaining work whose actual server-known tool calls are read-only or checkpoint updates; model declarations cannot relabel an unknown mutation. Retries reuse the original Run, pending call IDs, successful tool results and operation identities, obtain a new fence and keep completed steps. The existing Gateway scheduler tick dispatches due work; there is no second scheduler or model polling loop.

An ambiguous financial journal blocks both automatic and owner resume until authoritative reconciliation; a confirmed receipt permits owner-controlled continuation with the same identity. Unknown external writes remain blocked pending actual reconciliation rather than pretending failure. Pause/cancel during retry wait persist and stop dispatch. Modified-plan failures require a real plan revision before resume. Terminal budgets cannot loop forever. The shared Run completion boundary rejects incomplete declared Task steps; a final model sentence cannot fabricate completion. Web/Mobile live projections expose real retry/review/reconciliation state using the existing controls and translated labels.

Evidence: actual AgentRuntime tool loop → provider outage → durable backoff → two competing Gateway recovery calls → same checkpoint/fresh fence → one returned result passed. Ten Task lifecycle/recovery cases passed on PostgreSQL, including fence/cancel regressions, financial ambiguity and external mutation rejection. Full Python suite passed 115 after adding the authoritative incomplete-step completion guard. Full client types/build and six Expo-Web tests passed. All isolated foundation integrations passed. Web's original 20 cases passed; the additional recovery case passed from a fresh process after correcting a test fixture identity-field typo. The retry/review UI was exercised against actual persisted Task failure and resumed the same Run, not a mocked progress projection. No production mutation or main merge.

Next: continue attention ownership/deduplication and measured intelligence/collaboration/authorization work. The program remains partial; finer source-spec Task acceptance and external reconciliation adapters still require coverage. Native hardware and remote CI blockers remain distinct from implementable repository work.


## Attention integration (2026-10-16)

Current wave: durable attention and meaningful owner interruption, integrated with the existing Gateway and event/channel receipts. Migration `0026_attention` introduces one owner-scoped attention projection, not another scheduler or chat timeline. Source events retain audit decisions including suppressed/duplicate/coalesced outcomes. Personal Agent owns account/global alerts; the specialist owns its setups; final collaboration belongs to the host conversation. Optional opportunity/informational preferences never disable critical/action-required classes.

The original confirmation timestamp and fresh real broker evidence bound opportunity validity. Delivery revalidates setup state; API and both renderers expire cached opportunities. Coalescing has a fixed deadline, and logical identities survive a merged row and worker restart. Obsolete sources cannot retire a newer alert. Mandatory channel dispatch rechecks actual approval/control/broker/task state before submitting its existing effect receipt; an uncertain delivery is not blindly repeated. Arabic and English mandatory message catalogs are packaged in both distribution forms.

Verified locally: 129 pytest cases; seven PostgreSQL attention scenario groups including concurrent ticks, replay after coalescing, stale evidence, mandatory preferences, real collaboration synthesis and scripted external-channel deduplication; the entire isolated foundation runner including 11 Task PostgreSQL cases; 22 Web and seven Expo Web browser tests; Ruff, Pyright (zero errors), client checks, lint, full Web/Android/iOS exports. Browser acceptance is not native Android certification. No real broker mutation, external message, VPS deployment or main merge occurred.

Remaining work continues: Super Bot trusted device authorization/proposals, Shadow goal orchestration, measured changing cross-market relationships, richer regime/advanced source intelligence, collaboration evidence fusion/final market validation, automatic decision lineage and complete performance/explanation views, dependent voice/UI acceptance. Remote GitHub CI billing lock and physical Android verification remain external blockers only for those checks; they do not label these implementable capabilities blocked.


## Measured cross-market evidence (2026-10-16)

One pure Market Runtime calculator measures Pearson correlation on identical closed-bar log-return intervals, with non-overlapping recent/baseline windows and explicit strength/change states. It never forward-fills gaps or uses array-index alignment/current forming bars. The existing canonical candle-close helper handles all supported timeframes including monthly bars. No hardcoded pair, suffix normalization, causal assertion or standalone trade signal is introduced.

Normal Agent tools record/read immutable bounded derived samples and source digests through existing durable events/effect receipts. The Personal/account-wide reader and an exact-symbol specialist can inspect relevant same-account comparisons; this does not widen the specialist's financial binding. Historical reads survive connection removal. Decisions can reference measured relationships; absent optional references retain the original durable request fingerprint. Stale/unreliable references force WAIT. The same eligibility function gates thesis revalidation and Shadow entries; attention validity also respects the relationship deadline. Model context receives summaries, not all aligned sample history.

Verified locally: 156 pytest cases including 27 relationship calculations across all supported timeframes, inversion/weakening/breaking, gaps and missing/stale/flat data; PostgreSQL checks for forex/metals/indices/crypto and two horizons, concurrent replay, exact scope, immutable history, owner isolation, source expiry, thesis evidence and actual AgentRuntime → global router → measured tool → gated WAIT → conversation. Ruff, Pyright, client checks and lint pass. This changes backend evidence only; prior Web22/ExpoWeb7/full export acceptance remains the client baseline.

Remaining relationship work: durable change monitors through the existing watch engine, time-aware cluster/currency risk when broker metadata/conversions support it, and richer explainability/performance presentation. No extra schema migration, live broker mutation or deployment.


## Durable relationship change monitoring (2026-10-16)

The existing composite detector contract now accepts a bounded relationship leaf (at most four per tree). It consumes the same measured calculator and can combine changing relationship evidence with existing price/candle conditions. The existing persistent Watch/Gateway scheduler, health transitions, work lane and wake receipts own its entire lifecycle. No new monitor, scheduler or model-per-tick loop exists. Closed-bar monitors normalize to scheduled evaluation and respect their interval during stream callbacks.

Only closed bars contribute to source identity. Forming-bar edits and polling cannot create distinct confirmations. Observation source time is the actual aligned bar-close time; its validity deadline propagates through composite observations, attention and final thesis revalidation. A missing/weakly aligned baseline, stale history or bounded read timeout suspends evaluation. NOT of missing evidence cannot confirm. Same-symbol comparisons and oversized relationship fanout are rejected before persistence.

Acceptance: 158 pytest cases, including 29 relationship cases and 45 focused relationship/dynamic/source-time cases; PostgreSQL full isolated foundation runner; actual normal ToolRegistry → same Market Runtime → persistent Watch → work Run receipts, source replay, two-source confirmation, stale suspension and healthy recovery with no repeated wake. Historical read survives connection deletion. Pyright zero errors, Ruff, client checks, lint and full Web/Android/iOS export build pass. Web22/ExpoWeb7 remain the last actual browser acceptance runs; no client redesign was made in this wave.

Next integration: persistent authority proposals/trusted device authorization and Shadow goal orchestration; richer financial decision lineage/performance, account cluster valuation and advanced regime sources remain implementable work. Native hardware acceptance and the external remote-CI billing lock remain separate concrete blockers. Full specifications 01–18 are still incomplete.

## Signed Super Bot authority over the existing Goal runtime (2026-10-16)

Implemented one durable proposal/authorization lifecycle, not a second Agent or execution architecture. The normal model tool can propose a bounded goal/account/exact-symbol/plan envelope but cannot activate it. Password-confirmed passkey enrollment uses standard WebAuthn; activation verifies an expiring owner/session/request/hash-bound ES256 proof with presence and user verification. Only public credential material is persisted. Replay returns the existing current status and cannot reactivate paused/replaced/revoked authority. Revocation disables the associated active grants. Expansion and plan edits require fresh review/proof; reductions/stop/Emergency Stop never require another device prompt.

Advisory financial steps fail closed. A signed supervised background wake prepares the existing approval card and waits; the exact approved operation is rechecked in the executor before send and then produces the real simulated broker receipt. Signed autonomous goals still pass global Trading, fresh evidence, exact scope, limits, lease fencing, account serialization, journal and reconciliation. Activation neither enables global Trading nor sends a trade. Migration `0027_device_authority` adds focused credential/challenge/proposal tables and disables old unsigned autonomous goals; applied only to disposable databases here.

Web and Expo consume the same immutable review/status cards, with localized review details, rejection/stop and actual server refresh. Mandatory pending-authorization attention reuses the existing attention projection and current-state validation. Web registers and signs with the browser OS passkey flow. Native support uses the platform passkey SDK via lazy loading, explicit public Android certificate / Apple application association metadata, and safe unsupported/configuration fallback. Version 0.2.5 / Android code 6 records the new native dependency: a compatible native binary is required once; fingerprint OTA separation remains in place.

Verified locally: 165 pytest cases; all isolated PostgreSQL foundation checks including signed device authority and 11 Task cases; retained Goal/Gateway/AgentRuntime/tool closed-loop suite plus supervised approval → one broker mutation and advisory denial; forged/missing-UV/wrong-origin/expired/tampered/cross-session/revoked/replayed proof rejection; model-tool proposal remains non-authoritative and replay-idempotent; mandatory attention becomes obsolete after activation. Web22 passed with actual Chromium CTAP2 registration/assertion; ExpoWeb8 passed including real API review/rejection/reload. `bash scripts/build.sh` passed Ruff/format/Pyright, all client checks/lint, Web build and Android/iOS/Web JS exports. Dependency consistency (`pip check`) and 17 Node timeline/mentions/voice/OTA cases passed. Expo compatibility identified five SDK-57 patch updates; the mobile lockfile was updated to the recommended patch set and `pnpm check:mobile` then passed. ExpoWeb8 passed again against that patch set. Arabic catalog extraction reports 603 messages and zero missing translations. Initial unconfigured pytest invocation correctly failed the disposable-database requirement; the final full run used a migrated disposable PostgreSQL database and passed.

External acceptance still pending: physical Android/iOS passkey prompts and public installed-app/domain associations, plus native keyboard/voice acceptance. Native export/browser tests do not satisfy those checks. Remote GitHub CI has a previously verified account billing lock; local passes do not imply remote CI ran. No deployment, main merge, real-money/demo broker mutation or channel delivery occurred.

Next integration point: durable activation review/wake through existing Gateway lanes (without an automatic first financial action), bounded authorization/Goal state in the existing unified live-state projection, Shadow Goal orchestration, richer risk-budget envelopes and financial decision lineage/performance, then advanced cross-market risk and market-source acceptance. The source matrix keeps these partial/not-started scopes explicit; full specifications 01–18 remain incomplete.
