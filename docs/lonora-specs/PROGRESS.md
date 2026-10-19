# Progress

Current wave (2026-10-18): professional trading Agent environment, Wave 0 audit and Wave 1 context-budget implementation on `feat/trading-agent-environment`, from `80b0ff9`. The prior S19 branch was merged and deployed before this wave; older entries below are historical. No new deployment or APK build is part of this integration.

## Current wave

2026-10-16: signed device authority, first activation review and shared status integration in wave 4; waves 1 and 2 integrated; shared historical evidence, thesis, explicit Shadow mode and Task failure/recovery integration in wave 3 on `feat/coherent-agent-foundations`, audited base `895eaa8`. All 18 original references remain intact. This is **not completion of the full program**. Source-section matrix distinguishes partial integration from full acceptance.

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

## Activation review and authoritative shared status (2026-10-16)

After signed activation, the existing Gateway scheduler now discovers unconsumed active grants and atomically creates one observe-only internal work Run plus an existing effect receipt. Concurrent scheduler ticks and restarts cannot create duplicate review work; the normal Run lease/checkpoint mechanism handles execution recovery. Paused Agents do not starve eligible work. Terminal/paused Goals are not resumed. Blocked Goals may be inspected read-only and retain their actual blocked state. Invalid/revoked/stale grants are reduced safely, not used to initialize work.

One shared background-trigger set classifies the new activation wake in the existing work lane and global Background model capability. There is no new scheduler/Agent/executor. The first review advertises only read tools; the central financial boundary also rejects direct execution and inherited observe-only authority. Read-only work can inspect its same-Agent conversation or current group membership origin through one validated Goal-read helper; mutation scope stays unchanged. Existing durable outcome receipts return one actual result to the origin. Failure due to an unconfigured model is recorded and visible, with no automatic paid retry loop.

The existing AgentLiveState now contains bounded authorization/Goal/review summaries and a separate pending-authorization count. Pending requests are not reported as autonomous. Failed reviews and blocked Goals require attention. Web, Expo and voice consume this same projection; no fabricated monitoring progress or profit is added. Web Goal status translation is shared by its existing Goal view and compact live status.

Local acceptance includes the existing isolated foundation runner plus the new activation fixture: concurrent admission, work/conversation lane separation, actual normal AgentRuntime/global Background router → Goal/account tools → one returned conversation result, direct financial rejection, unconfigured-model visibility without recurring attempts, and blocked Goal inspection/result return in a real group. The complete 165-case pytest run, 18 isolated foundation fixtures plus 11 PostgreSQL Task cases, retained closed-loop Goal suite, Web22 and ExpoWeb8 passed; Ruff/Pyright/client lint and type checks are also recorded in the local acceptance logs. The full source program remains partial. No new migration beyond 0027, deployment or main merge occurred.

Next: Shadow Goal orchestration and richer signed risk-budget fields; automatic financial decision lineage/performance, broader cross-market exposure and advanced market sources remain. Physical native passkey/domain acceptance and remote CI billing remain separate external verification limits.

## Shadow Goals integrated with the existing closed loop (2026-10-16)

Current wave: frozen-mode Goal orchestration. New Goals persist their current Agent execution mode in the existing lifecycle state; legacy Goals remain live. One shared scope check validates Agent, Goal, Run and signed envelope. Switching mode pauses active/waiting/blocked Goals and disables pending/active grants rather than converting old work into financial authority. No migration was necessary.

The existing Goal tools, decisions, approval buttons, signed background authority, journal, recovery, watches and review routines now support virtual execution. Read-only broker quotes/candles/instrument constraints combine with one shared DB projection of virtual positions/orders; Market and Trading reuse it without a dependency cycle. Virtual fills and management remain separate from manually opened real broker tickets. Monetary PnL is explicitly unavailable, including profit-based conditions; price return is not account profit. Local unconditional virtual cancellation remains possible while broker reads are unavailable.

Approval cards now complete with the exact post-approval validation failure instead of remaining approved indefinitely. Failure writes require the current Run fence, preventing an obsolete worker from marking a newer worker's Goal failed. Atomic virtual mutation/journal survives a Goal checkpoint gap; recovery consumes the same operation once. Foreground/supervised virtual actions use the existing buttons; signed autonomous authority is bound to Shadow mode and cannot enter the live executor. Both clients label virtual-only authority in existing cards/status; no UI redesign.

Verified locally: full pytest165; 19 isolated PostgreSQL foundation fixtures plus 11 Task cases; retained live Goal closed-loop/recovery suite; dedicated four-asset Shadow Goal fixture (four pending entry types, pending fill/new-Run target management, signed background protection/partial/final close, virtual watch wake, checkpoint recovery, stale-worker fencing, manual-ticket isolation, mode-change revocation, real approval failures, cancellation during broker outage). Broker execute/reconcile methods are trapped in Shadow acceptance, with global live Trading OFF. Web23 and ExpoWeb8 passed, including actual API/Chromium signed Shadow activation and stopped grant after mode change; 17 Node timeline/mentions/voice/OTA cases passed. Full build passed Ruff/format, Pyright0, all seven client type checks, lint, Web build and Android/iOS/Web JavaScript exports. Arabic extraction:606 strings, zero missing translations.

Active next workstream: richer signed risk budgets and automatic immutable execution-decision lineage/performance. Advanced cross-market exposure/intelligence and full source-section acceptance remain incomplete. Physical native passkey/domain/keyboard/voice verification is still external; Expo export and browser acceptance do not replace it. Remote CI billing lock remains separate from local checks. No production deployment, main merge, real/demo broker mutation or external channel delivery.

## Automatic execution evidence and historical receipt tools (2026-10-16)

A second integrated capability now captures the actual typed preflight snapshot at planning and final before-send validation, with source observation time, exact request, policy, Goal/step/decision reference where present, schema/logic version and honest truncation counts. A quality-gate rejection persists its observed state and reason without authorizing broker submission. The existing financial journal owns these fields: broker response/reconciliation cannot replace them with later or invented evidence. Shadow uses the same capture helper with virtual targets and monetary profit unavailable; a local cancellation records its real virtual target and explicitly omits an unnecessary broker snapshot.

The existing ToolRegistry exposes bounded exact-scope trade_record_history/read tools. They retrieve saved receipts without a broker connection, retain missing legacy evidence explicitly, and grant no authority. The trade-management skill describes this historical workflow. Performance attribution now consumes the already-frozen server execution origin, fixing live receipts dropped by a dependency on an absent repeated lease field; legacy Run attribution remains a fallback. No new event bus, journal, schema migration or UI system.

An integration regression caught first-call Shadow receipts differing from replay after metadata persistence. The first call now returns the same durable receipt as replay. Final validation passed:168 pytest cases,19 isolated foundation fixtures plus11 PostgreSQL Task cases, retained closed-loop live Goal regressions, Ruff/format/Pyright0, skill resource validation, client lint/types and full builds/exports. The preceding wave's Web23/ExpoWeb8/Node17 acceptance remains valid; this second wave changes backend/tools and bundled skill instructions only. No automated external broker mutation occurred. GitHub run38893854139 for3965a0d started zero steps and reported the account billing lock; local checks do not imply remote CI success.

Remaining program scope is still substantial: richer signed monetary risk budgets require trustworthy broker-neutral valuation, complete thesis/collaboration decision timelines and richer performance/strategy attribution, advanced cross-market intelligence/risk, and native hardware acceptance. The matrix retains partial/not-started source requirements and the next work resumes from these dependencies. Full specifications01–18 are not complete.

## Production conversation and mobile repair (2026-10-16)

Audited the requested production conversation read-only. Super Bot setup had no persisted Goal/request: repeated Goal watch schema failures were reduced to a generic code and the Agent asked for ritual retry phrases. The existing ToolLoop now exposes bounded sanitized field paths/types/stable validator codes; mandatory policy and the Goal skill keep repair in the same requested conversational turn. A real existing Run integration repairs the invalid watch into an appropriate scheduled review and creates one pending supervised card without a second user message or financial authority. First activation without registration opens the actual enrollment form; device proof remains mandatory.

The current chart is ready while old ambiguous financial operations keep broker reconciliation degraded. Shared live-state projection now identifies broker/market health sources and both clients label pending verification accurately. Uncertainty is preserved; no historical mutation is blindly retried or declared failed to remove a warning.

Web/Expo specialist profiles now have confirmed permanent deletion with actual API/error outcomes and safe navigation. The default Personal Agent retains backend deletion protection and an accessible role-based gold star. Mobile voice setup/cancellation/cleanup races are repaired. The published APK manifest lacks WAKE_LOCK while InCallManager acquires it on a native Handler; new native config declares it and release verification requires actual microphone/audio/wake-lock permissions. Unused overlay/legacy storage permissions are blocked. Native version0.2.6/code26101613+ is above the published0.2.5/code26101612; updating must retain the production signer, which differs from the old local build key.

Local checks passed:171 pytest,20 isolated foundation integrations plus11 PostgreSQL Task tests,24 Web,8 ExpoWeb,23 Node checks,6 Android artifact checks (included in pytest), Ruff/format/Pyright0, client types/lint and full Web/Android/iOS JS exports. Arabic catalog615, zero missing. Production native APK was inspected with actual Android tools; native call reproduction and Samsung acceptance remain tracked separately. No new migrations; no test submitted a real/demo trade. Remaining full01–18 program scope is unchanged.

## S19 operating environment integration (2026-10-18)

Branch: `feat/agent-operating-environment`, audited base `21293ad`. Source and kickoff committed in `429205e`. This extension is not merged into main and is not deployed. The original19 source bytes, Nanobot source study (pinned `faf1efaf09d2d69d1887b6ac6b0c6441e3ccccb2`), requirement rows S19-01…S19-88 and dependency graph are retained together.

Completed shared repository work:

- Actual safe ToolRegistry introspection: schema, side-effect/replay policy, scope, bounded result information and stable codes. No tool discovery grants authority.
- Typed recovery observations and bounded route/attempt history in the existing fenced Run checkpoint. Ordinary safe read failures release the worker with a persisted deadline and stable pending call identity; the existing claimant admits the next attempt. Equivalent failure cannot reset its budget merely by changing a call ID.
- Persisted in-flight intent before a handler starts. Only server-declared safe reads or inspected receipt-backed handlers may replay after worker death. Unknown unreceipted mutations and ambiguous financial outcomes are blocked; existing financial journal/reconciliation remains authoritative.
- Actual bounded chart tool views, aligned candle/indicator tails and omission counts. Successful oversized effects preserve actual outcome/operation identity rather than becoming fake failures. Scripted runtime acceptance narrows oversized reads in the same request.
- Task-owned market watches, verified broker recovery and timers wake the same logical Task/Run/checkpoint through the existing scheduler. Source observations and wake receipts deduplicate concurrent/replayed wakes; cancellation wins. Ready-source filtering prevents unrelated long waits from occupying the batch. Owner revisions return to the same work for revalidation.
- Agent-scoped operational facts reuse existing tool events with contract hashes, source Run/time/cursor and bounded retrieval. Memory revision events distinguish server-observed owner writes, Agent-authored writes and legacy unknown authorship. These are mutable untrusted data and cannot modify financial policy.
- Truthful waiting/recovery summaries reuse the existing live-state projection and Web/Expo status components/translations. Voice finalization, silence, disconnect/reconnect and steering use the same Agent, Thread and Task; no second voice runtime.
- Actual concurrently running peer runtimes return success/failure to one active host, which inspects and closes exactly one synthesis. Existing collaboration and financial scope/regression suites are retained.

Parallel work used safe boundaries: read-only Nanobot source study; continuity audit/new voice scenario; chart projections/new chart tests. Shared contracts and runtime integration had one owner. The code is native Lonora; no Nanobot implementation was copied.

Acceptance is tracked in `S19_ACCEPTANCE.md`. Physical Android is `BLOCKED_EXTERNAL_NATIVE_ANDROID`: no native build/APK, microphone/device reconnect or Samsung hardware certification in this work. Browser/Expo Web and server-side voice tests do not replace that acceptance. No production migration, deployment, real/demo broker mutation or external notification was performed. No remote GitHub Actions success is claimed.

Full specifications01–18 remain incomplete in their original matrix. Their advanced domain features are not invented or silently marked done by S19. The current remaining S19 boundary is physical/native and real-service acceptance, not another runtime or temporary in-memory implementation.

Final financial review also freezes optional Goal step/attempt/plan identity before execution, repairs a committed receipt's still-approved card from its actual saved result, and keeps reconciliation on the original financial call identity. Legacy checkpoint replay is conservative unless a handler's old durable identity is explicitly proven. `check_goal_call_identity` and scripted old-checkpoint/renamed-call fault cases cover these boundaries. Final validation:199 pytest,26 isolated foundations plus11 PostgreSQL Task cases, Pyright0, lint/types, Web24, ExpoWeb8 and Node23. No new native build.


## Trading Agent Environment — Integration Start (2026-10-18)

- Owner-authorized English plan and original visual reference preserved in the repository.
- Current main and origin/main both inspected at `80b0ff9`; dedicated branch `feat/trading-agent-environment`.
- First audited path: ContextBuilder → model_turn → GlobalModelRouter → provider adapter, including background compaction callers.
- Reused: existing tool-exchange validation, newest-user retention, catalog storage, global fallback policy, TokenUsage, lease/fence/effect boundaries.
- Demonstrated gap: model_turn applies only a character cap before routing; fallback attempts reuse identical context without model-window or output-reserve checks; image budgets are absent.
- First capability card: ENV-CTX-01 in BUILD_CAPABILITY_CARDS.md. Implementation and acceptance tests are in progress; none of the new program is yet declared verified.
- No competing runtime, provider policy, scheduler, journal, or permission model will be introduced.
- Next integration: shared request budgeting, router fallback coverage, and existing runtime recovery tests. Full Wave 0 comparison, Chart Use, knowledge/learning, and dependent UX remain open.


## ENV-CTX-01 — First Verified Local Integration (2026-10-18)

Implemented on `feat/trading-agent-environment`: shared adapter-kit governance, model-aware per-attempt admission through GlobalModelRouter, known catalog window/output limits, explicit unknown capacity, offline hash-verified tokenizer cache with conservative fallback, schema/image allowances, bounded provider output, authenticated global context settings, and estimate/actual diagnostics persisted in existing usage records. Existing original inputs/checkpoints/effect identities remain unchanged.

Executed evidence:
- 22 focused context/routing/provider tests passed, including actual HTTP payloads for all five providers in stream/non-stream modes and smaller-model fallback.
- Full pytest in a freshly migrated disposable PostgreSQL database: 228 passed (`.runtime/environment-wave1-release-pytest.log`). Initial unconfigured invocation had 14 voice fixture setup errors; the correct isolated database run passed them.
- Existing isolated foundation runner: all 26 integration groups plus 11 PostgreSQL Task tests passed (`.runtime/environment-wave1-foundation.log`). The separately executed new global-settings fixture passed and is now registered in that runner.
- Actual message → Gateway → AgentRuntime → tools → result integration in check_goals passed, including persisted budget diagnostics, closed-loop simulation, crash/restart and no-blind-retry controls (`.runtime/context-budget-goals-final.log`).
- Authenticated global-context API fixture passed: owner scope, persisted settings, invalid fields rejected (`.runtime/context-budget-settings.log`).
- Ruff whole-repository check and format check passed; Python wheel built with the new shared modules included; verified tokenizer cache preparation ran successfully. Final Pyright: zero errors, warnings, or information messages (`.runtime/environment-wave1-final-pyright.log`); generated packaging output was removed before checking.

Findings fixed during integration: the first byte-only estimate over-rejected the actual 88-tool surface; cached tokenization and a documented 64000-token unknown-capacity admission policy fixed it without inventing model windows. A schema character-framing overcount omitted a useful latest result; the existing character cap is preserved while token framing is budgeted independently. Missing provider usage remains unknown rather than fabricated zero in the new diagnostics.

Limits: unknown model capacity stays unknown; images and cross-provider tokenization remain labeled estimates. Real-provider calibration, full Wave 0 comparative benchmark, Docker image deployment, TradingView assets/Chart Use, client/native acceptance, and subsequent waves remain open. No APK, production deployment, real broker mutation, or migration was performed.

Next integration: ENV-RESULT-01. Audit found that current generated-artifact auto-delivery would attach internal tool-result files unless explicitly distinguished; define that contract with retention, scope, and effect-safe recovery before implementing readback.


## Parallel Wave — Skills Run Pinning (2026-10-18)

User authorized parallel implementation and incremental GitHub pushes; root owns shared contracts, commits and integration. Skills owner delivered bounded current-Run manifest/content snapshots in existing metadata, deterministic dependency handling, quarantined invalid installed content/graphs, and observe-only selection enforcement. Review preserves existing tool and financial authority; refresh/restart retains selected content while current disable/removal/source changes remain authoritative.

Owner evidence: 37 Skills cases passed against disposable PostgreSQL, focused Ruff and strict Pyright passed. Root repeated the focused Skills tests; exact counts in `.runtime/parallel-skills-root-review.log`. This is current-Run pinning only; cross-Run Task transfer, explicit per-version revocation, full initial source-eligibility audit, and evaluated adoption/rollback remain open. No migration, production deployment, APK build, or real broker mutation.

### Skills admission and recovery review

Follow-up review found and repaired two real boundaries before further integration: authenticated install/delete must reject invalid dependency graphs transactionally even though runtime selection quarantines invalid installed content; caller Run metadata must not inject server-owned `skill_snapshot` or `skill_selection`. Both now have authenticated PostgreSQL regression checks. Installed source labels are descriptive owner-supplied provenance, not verified publisher authority.

Root independently ran `check_skill_installation.py` and `check_skills_versioning.py` against separate freshly migrated databases: both passed. The latter exercises forged builtin snapshot rejection, real Task pause/resume and classified provider retry on the same Run, retained instruction content, new lease fence, stale-worker rejection, and current disable. No successor-Run snapshot store was created: current recovery already reuses the same Run. Owner's focused suite: 48 passed, Ruff/format/strict Pyright clean. Per-version revocation and evaluated learning remain open.

### Scoped memory evidence integration

Existing context assembly now reaches one bounded lexical/semantic evidence implementation through the unchanged `retrieve_memory` interface. Existing memory and semantic-note rows are reused; edits/deletes are visible on the next retrieval. SQL owner/Agent scope precedes ranking. Evidence carries actual source identity/version/provenance, explicit unavailable/fallback/candidate limits, and unknown historical freshness. Arabic diacritics and ordinary prose are normalized while recognized technical identifiers preserve case and broker suffix punctuation.

Root review caught mixed-case `XAUUSDm` and terminal `BTCUSD#` identity gaps; both were fixed generically and added to regressions. Root repeated 32 unit cases and the isolated PostgreSQL retrieval fixture, both passed. Owner's combined runtime tests: 60 passed, one existing skip; targeted Ruff and strict Pyright clean. Limits remain: bounded candidate coverage, purely lowercase alphabetic identifiers without metadata, no live embedding calibration, and no conversation-history expansion yet. No migration or new memory store.

### Typed chart drawing foundation

Backend supports ten typed drawing kinds through existing chart tools and saved ChartState: legacy price/line/note plus zones, rays, channels, Fibonacci, arrows and scenarios. Stable drawing identities, atomic add/update/delete batches, exact account/symbol/timeframe filtering and server-side Agent/manual layer protection reuse chart versions and fenced transactions. Saved SVG rendering moved into the charts package with a tools compatibility import, keeping one shape projection owner.

Owner checks: 39 focused Python cases, eight SQLite symbol/timeframe combinations, Ruff and targeted strict Pyright. Root independently repeated PostgreSQL concurrent-writer version conflicts, duplicate prevention, atomic failed batches, preserved identity and zero-order checks. No new schema or broker mutation. Important limit: a repeated stale command returns version_conflict rather than replaying a saved success receipt; on-demand visual observation and successful replay receipts remain separate unfinished work. Client rendering is integrated in the next increment, not claimed by these backend tests.

### Large-result persistence and recovery

Results above the existing 120000-character observation limit now use stable internal artifacts, a redacted JSON projection and bounded paginated readback through the existing artifact_read tool. Owner/Agent/thread/Run/call and argument identity remain explicit. Existing lease/fence checks protect writes; SQL filters hide internal results before list limits and generated attachments. There is no second execution journal or result database.

Root independently repeated actual PostgreSQL ToolLoop crash/recovery tests: a scripted mutation executed once despite death after result persistence and before checkpoint; complete readback, isolation, changed arguments, corrupt/missing files, failed writes, stale fences, 20MB limit and hidden-artifact limits passed. Ambiguous financial results still invoke their existing same-operation reconciliation path. The intentional PermissionError fault emitted only tool name and exception type. Owner's 40 unit cases and existing environment/generated-artifact integration checks passed. Full integration checks continue below.

Retention is owner-managed on the existing persistent artifact volume. Files over 20MB stay explicitly unavailable, and existing redaction patterns do not guarantee classification of arbitrary sensitive prose. No migration, APK, production deployment or real/demo broker mutation.

### Shared TradingView client integration and full local regression

One licensed TradingView31.2.0 distribution now renders backend scenes for Web and Mobile: 551 inventoried SHA-256 assets, shared EN/AR dependencies, server indicator panes and all ten drawing types. A dedicated credential-free chart entry and strict namespaced API static routes support separate Expo/Web shells without duplicate vendor bundles. Frame URLs contain no credentials; client-local acknowledgments check actual chart/scene/data revisions. Public entry files revalidate across deployment; missing assets never fall back to the Expo shell.

Chart updates preserve browsing and exact broker symbols; live ticks never force Agent focus. Owner gestures override opt-in Follow Agent. Mobile sheets retain thread/draft/frame through minimize/reopen; desktop uses the existing side-panel/focus owner. Native module detection precedes lazy loading, so an old installed binary falls back to an explicitly labeled saved-scene preview. OTA does not install the new WebView native module; no APK was built.

Full regression evidence:
- Final Python run before the image-observation increment: 292 passed. Whole-repository Pyright: zero errors/warnings; Ruff lint/format: 695 files clean.
- Isolated foundation runner: 29 PostgreSQL integration groups plus 11 Task cases passed. The new large-result fixture passed separately and is now also registered for future runs.
- Full real Chromium Web suite: 27 passed. Full Expo Web suite initially had 9 passed/2 failed, exposing a real vendor theme readiness race and an obsolete SVG selector. The lifecycle fix waits for vendor readiness and disconnects before disposal, handles sync/async failures, and preserves actual error reporting. Updated workspace tests assert the real renderer/RSI/drawing scene rather than obsolete SVG nodes. Fresh full Mobile retry: 11 passed, no weakened assertions/timeouts.
- Additional real-vendor theme/readiness/locale/failure-recovery regression: 3 passed. Types, SDK compatibility, manifest verification, shared renderer confinement tests, Web build and lint passed. Build retains a non-failing large-chunk advisory.

No production deployment, native hardware/voice certification, real-money/demo mutation or migration. Remaining chart boundaries: bounded resident history, generic display metadata (not broker instrument specs), read-only projected vendor geometry, server visual-session lifecycle and model image observation. Native gesture/voice continuity and live broker daily/weekly/monthly coverage are not claimed.

Next integration is ENV-VISION-01: audit confirmed tool-generated PNGs currently remain JSON references, and Anthropic ignores tool-role images. One owner is implementing strict artifact-backed images at the actual model boundary; a separate owner preserves original snapshot source revisions on replay. Both reuse current scope/fence/artifact contracts. No general coding/browser/shell authority is being added. Work resumed on 2026-10-19 from preserved files after the session interruption; the image increment is not yet verified.
