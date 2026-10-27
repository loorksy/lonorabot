# Complete system audit — source reconstruction and verification record

Baseline: `5315a8cc634486d54b1a64c1fd211b3e46429f14` · Audit date: 2026-10-27 · Source: this checkout.

[System](COMPLETE_SYSTEM_AUDIT.md) · [Capabilities](COMPLETE_CAPABILITY_INVENTORY.md) · [Traces](END_TO_END_EXECUTION_TRACES.md) · [Diagrams](ARCHITECTURE_DIAGRAMS.md) · [Findings](FINDINGS_AND_RECOMMENDATIONS.md) · [Coverage](AUDIT_COVERAGE_MANIFEST.md)


## 1. Executive assessment and completion status

Lonora is a Python/TypeScript monorepo implementing an owner-controlled, persistent agent workspace with Web and Expo clients, a FastAPI application, a resident asynchronous Gateway, PostgreSQL-backed execution/state, model adapters, analytical tools, and a real MetaApi trading execution boundary. It also contains voice session orchestration, collaboration, durable background Tasks, scheduled/watched work, charts, executable skill packages, and a separately provisioned analytical workspace host. These are derived from application assembly and call sites, not from an external agent architecture.

**Inventory completion is not audit completion.** All 1,990 original tracked files are accounted for, with byte hashes and inspection classifications. The exhaustive semantic review requested by the user remains incomplete: substantial first-party code and tests are indexed but not fully read, and selected traces are incomplete at subsidiary branches. The [coverage manifest](AUDIT_COVERAGE_MANIFEST.md) identifies every such path. The word “complete” in the requested artifact names does not certify full semantic coverage. No 100% inspection, feature completeness, or production-readiness claim is made.

The verified local baseline is useful: JavaScript lint, seven workspace type checks, seven workspace build tasks and 25 selected mobile tests passed. Python application imports, backend/DB tests, live integrations, browser journeys and native devices were not verified. Two local probes executed actual extracted repository code against local stand-ins and reproduced defects: an explicitly approved trade batch continues after an ambiguous first result, and Webhook receipt status is overwritten by a numeric HTTP status. These probes do not establish real broker or HTTP execution.

The architecture already has substantive correctness mechanisms: transactional message admission, persistent Run checkpoints, fenced leases, owner scoping, exact-operation journal identity, current pre-send checks, independent financial verification and conservative ambiguous-result handling. Those mechanisms should be preserved. The evidence supports targeted repairs and completion of verification; it does not support replacing the architecture with a smaller unrelated framework.

## 2. Repository boundary and organization

The inspected baseline is commit `5315a8cc634486d54b1a64c1fd211b3e46429f14`, on task branch `coderabbit/arabic-greeting/1c2edbf9`. The working tree was initially clean. The checkout is the only connected source repository used. No external diagram or prior feature list was accepted as implementation truth. Root `AGENTS.md` was read; targeted knowledge-base searches found no available KB files at the expected locations.

| Area | Actual role | Evidence |
|---|---|---|
| `apps/api` | FastAPI composition, owner/session middleware, 44 route modules, three WebSocket modules, health and static delivery | `apps/api/src/lonora_api/app.py:68` |
| `apps/worker` | Process entry point that constructs and serves Gateway, installs shutdown signals | `apps/worker/src/lonora_worker/main.py:10` |
| `apps/web` | React/Vite Web workspace, React Router surfaces, Lingui localization, browser event and voice clients | `apps/web/src/App.tsx:11`; `apps/web/src/pages/Shell.tsx:87` |
| `apps/mobile` | Expo Router/React Native client, native sessions/voice/charts, OTA and signed-release tooling | `apps/mobile/app/_layout.tsx:12`; `apps/mobile/app.config.ts:12` |
| `packages/*` | 25 package directories; shared Python implementation and TS contracts/core/UI libraries | Package manifest inventory below |
| `packages/db/migrations` | Alembic schema/history evolution through 0032, distinct from running application processes | `packages/db/migrations/versions/0032_message_rich_content.py:1` |
| `tests` | 244 tracked artifacts: backend checks/fixtures, frontend/browser/mobile tests and acceptance harnesses | Exact paths/statuses in coverage manifest |
| `scripts` | Installation, build, development, migration, backup/restore, OTA release and static reference/acceptance checks | `scripts/build.sh:1`; `scripts/restore.sh:1` |
| `infra` | Container build, PostgreSQL/Caddy deployment and optional analytical workspace provisioning | `infra/compose/docker-compose.prod.yml:1`; `infra/analysis/compose.workspace.yml:1` |
| Runtime text resources | Constitution, system policy, prompts, playbooks, skills, tool/reference material distributed with Python package | `pyproject.toml:79`; `packages/agent-runtime/src/lonora_agent/skills/loader.py:1` |
| `apps/web/public/charting_library` | Licensed vendor distribution consumed by first-party chart integration | Vendor exclusion is per-file in manifest; first-party verification script remains in scope |

The inventory distinguishes 783 Python files, 389 JavaScript/TypeScript files and 12 shell scripts. These include tests, migrations, declarations and build tools, not only application logic. There are also 110 documentation artifacts, 80 configuration files, 23 presentation resources, 21 other text files, 552 vendor files and 20 binary assets. Generated dependency directories, Git internals, build caches and local state are excluded from first-party semantic review; source-generated wrappers and tracked runtime inputs remain accounted for.

## 3. Actual technical stack and dependency boundaries

The root Python project requires Python >=3.12. FastAPI/Pydantic implement HTTP contracts; SQLAlchemy async sessions and asyncpg implement PostgreSQL persistence; Alembic handles migrations; Uvicorn hosts the API. Provider and remote integrations use httpx/WebSockets and a pinned MetaApi SDK. Password hashing, encrypted secret storage and WebAuthn use dedicated dependencies. Numerical/visual processing includes NumPy, Pillow, tiktoken and Playwright. Exact declarations, including version ranges, are in `pyproject.toml:11` and the package table below. The local Python AST check ran on 3.14.4, not the minimum supported runtime.

JavaScript uses a pnpm workspace with Turbo orchestration, TypeScript and Biome. React/Vite implement Web; Expo/React Native implement mobile. Shared contracts and core projections are separate workspace packages, along with chat/UI/token libraries. The build check used the installed snapshot and lockfile; it did not verify a clean install, dependency supply chain, or all declared version combinations. The checked-in Python requirements are not a complete observed installed environment: the application `.venv` and required global Python packages were absent.

**Essential for resident execution:** PostgreSQL, application settings, API/Gateway processes and Python dependencies. A configured model provider is essential for generated agent turns, but not every read-only API or static page. Broker connection/data are essential for broker-backed market and live trading operations. Voice, web search, economic calendar, MCP, semantic embeddings, chart screenshots and executable workspace utilities have additional conditional dependencies.

**Optional in deployment, imported in code:** feature optionality does not necessarily imply an independently installable Python dependency. Root dependencies include MetaApi and Playwright even when the operator disables those features. Package separation must not be drawn as independent network services.

## 4. Process topology and execution ownership

The production Compose recipe contains PostgreSQL, API, Gateway and Caddy containers. The API image also serves built Web files and chart-renderer assets. Gateway owns concurrent asyncio loops, not one service per package: worker claimants, a conversation lane, maintenance/scheduling/reconciliation, channel delivery, voice attachment, market streaming/shadow advancement, history compaction, chart materialization, watches and attention. `Gateway.serve` creates these tasks and supervises them (`packages/gateway/src/lonora_gateway/service.py:163`).

The optional analytical host is a different security and process boundary. Gateway reaches a configured Unix socket; the host provisions bounded ephemeral Docker execution using a pinned image. The base production recipe does not include this host. Its opt-in overlay mounts the socket directory without giving application containers the Docker socket (`infra/analysis/compose.workspace.yml:4`). A source-present workspace tool is therefore not evidence that execution is configured.

API and Gateway construct their own `OwnerServices`/broker managers. They share durable truth through PostgreSQL and the artifact volume, not shared Python memory (`apps/api/src/lonora_api/runtime.py:1`; `packages/gateway/src/lonora_gateway/runtime.py:1`). Runtime event helper classes exist, but the observed cross-process replay mechanism is the persisted EventRow/public-cursor path. `RuntimeEvents` is an in-memory bounded subscriber helper, not evidence of a production message broker.

## 5. State model and persistence

| Durable concept | Meaning and ownership | Selected source |
|---|---|---|
| Owner, session, device and encrypted secrets | Single owner identity, revocable sessions, proof devices, encrypted credential values | `packages/db/src/lonora_db/schema.py:30`; `packages/auth/src/lonora_auth/sessions.py:14` |
| Agent and bound market | Instructions, pause/state, personal/specialist/delegated identity, account/symbol scope | `packages/db/src/lonora_db/agents.py:33`; `packages/db/src/lonora_db/agent_binding.py:1` |
| Thread and Message | Canonical ordered conversation with reply/attachment/nonce identity | `packages/db/src/lonora_db/messages.py:73` |
| Run and Steering | Executable attempt, lease fence, checkpoint, pending work and arriving owner instructions | `packages/db/src/lonora_db/runs.py:128`; `packages/db/src/lonora_db/steering.py:1` |
| Ticket/Task and Board | Durable work lifecycle, plan steps, origin thread and linked Run, not a second queue service | `packages/db/src/lonora_db/tasks.py:94` |
| Event and EffectReceipt | Durable public projection and idempotency/uncertainty records for named effects | `packages/db/src/lonora_db/events.py:28`; `packages/tools/src/lonora_tools/tool_results.py:1` |
| Trading journal/approval/authority | Exact operation and outcome, immutable reviewed requests, signed bounded delegation | `packages/db/src/lonora_db/trading_journal.py:13`; `packages/db/src/lonora_db/trade_approvals.py:41` |
| Goal, decision, opportunity, watch | Planned execution lineage and evidence-driven state; receipts connect execution outcomes | `packages/trading/src/lonora_trading/goals.py:118`; `packages/trading/src/lonora_trading/opportunities.py:224` |
| Charts, market snapshots, virtual positions | Materialized display/data and mode-separated simulated execution | `packages/trading/src/lonora_trading/shadow.py:101`; `packages/charts/src/lonora_charts/state.py:1` |
| Memory, skills and artifacts | Versioned/owned knowledge, provenance, file metadata and external file bytes | `packages/db/src/lonora_db/artifacts.py:8`; `packages/agent-runtime/src/lonora_agent/skills/lifecycle.py:347` |
| Voice session and attention | Live connection lifecycle, transcript handoffs, attention/incoming-call intent | `packages/voice/src/lonora_voice/sessions.py:73`; `packages/voice/src/lonora_voice/incoming.py:140` |

Generic resources store typed or validated payload/state plus owner/agent/thread association, timestamps and optimistic version. `ResourceRepository.update` validates version/references before assignment; deletion removes the row and records an event (`packages/db/src/lonora_db/transactions.py:172`). JSON payload persistence makes database schema alone insufficient to describe invariants; contracts and handlers must be read together.

A local static graph check found 32 migrations, one root `0001_foundation`, one head `0032_message_rich_content`, all parent references resolved, no cycle. This says nothing about applying migrations to existing data, downgrade safety, or schema/model parity; those require PostgreSQL execution and further review.

## 6. Request, decision and execution flow

The full selected traces are in [END_TO_END_EXECUTION_TRACES.md](END_TO_END_EXECUTION_TRACES.md). Important boundaries:

1. A client acknowledgement means a message and Run identities were admitted, not that a model or tool finished.
2. Run claiming uses thread serialization, row locks and lease fences. Restarts recover saved execution state; they do not establish permission to replay every uncertain effect.
3. Context assembly combines stored instructions, policies, memory, history, skills, bound market, collaboration and goal context. Model text is a proposal/answer, not authority.
4. Tool dispatch checks registry scope, current lease, typed arguments and market binding. Financial handlers separately enforce approvals/grants and call the shared executor.
5. A broker acknowledgement and independent post-state verification are separate results. Ambiguous acknowledgements remain ambiguous until evidence resolves them; missing evidence must not become success.
6. User-visible completion is published through durable messages/events and projections. Provider streaming deltas are provisional; financial/privacy checks can replace a provisional generation (`packages/agent-runtime/src/lonora_agent/model_runtime.py:159`).

## 7. Feature completeness and disconnected components

The [capability catalog](COMPLETE_CAPABILITY_INVENTORY.md) describes 39 discovered families and inventories all 106 registered tools, 203 source-expanded method/WebSocket entries, first-party implementation symbols and client request candidates. These counts are source inventory counts, not certified working features.

Concrete completeness distinctions:

- Real broker mutation methods are implemented and reached by `ExecutionService` through MetaApi; the audit did not authenticate a real account or execute a transaction.
- Browser and native voice transports are present; real provider API compatibility, access entitlement and device/media behavior remain unverified.
- Incoming-call state and in-app overlays are integrated. External device delivery is **not wired** in the normal Gateway call: it invokes `incoming_tick(db, owner)` without an `IncomingDelivery`; the callee skips sending when that parameter is absent (`packages/gateway/src/lonora_gateway/service.py:160`; `packages/voice/src/lonora_voice/incoming.py:333`).
- `StdioMcpTransport` is deliberately disabled (`packages/adapters/src/lonora_adapters/mcp/transport.py:111`); HTTP MCP is the implemented remote path. This is a bounded capability, not proof of full MCP transport coverage.
- Workspace execution and executable skill validation are conditional on the separate host/socket/image, which were not run here.
- A source declaration such as `EventQueue`, `RuntimeEvents`, or a generic channel helper is not proof that normal traffic uses it. Searches found the direct durable Gateway/channel paths; a complete dead-code/import reachability proof has not been performed.
- Reconciliation of ambiguous modification/cancellation operations explicitly returns `mutation_evidence_required`; it is a recovery limitation and conservative tradeoff, not permission to automatically resend.

## 8. Cross-layer consistency matrix

| Flow | Interface → backend → final effect | Observed consistency / limitation |
|---|---|---|
| Conversation | Web/mobile composer → messages route → `send_message` → Run claimant → tool loop → completed Message/Event | Source-connected; nonce recovery and local mobile timeline tests inspected; full DB/browser journey not run |
| Owner trade action | Web trading API → authenticated `/trading/execute` → `ExecutionService` → broker → journal/verification | Direct owner path intentionally has no agent Run lease; do not mislabel that as a bypass of agent approval policy |
| Agent trade approval | Tool → pending immutable approval → UI decision → queued same Run → exact frozen requests → executor | Source-connected, but multi-request approved loop violates its advertised stop-on-uncertainty rule (F-01) |
| Standing authority | Device proof → stored bounded grant → agent tool → current authority checks → shared executor | Scope/expiry/action/budget and unresolved-operation gates exist; no cryptographic/device or DB integration test run |
| Financial display | Journal/approval projection → client refresh/event invalidation → cards/history | Polling/reconnect refresh exists; no claim of permanent UI staleness from a missing event alone |
| Mobile voice | Layout provider/overlay → native transport → voice API → Gateway attach/provider → canonical conversation | TS compile/selected synthetic lifecycle tests pass; external media unverified |
| Incoming call | Attention → stored ringing state → event/overlay; optional delivery protocol | In-app state is distinct from actual device push, which is disconnected in normal Gateway assembly |
| Skills | CRUD/catalog/tools → package/version/hash validation → optional host → activation | Handler registration does not mean executable utility is validated/active; exact host image affects admission |
| Artifacts | Upload bytes → filesystem → DB metadata → download/preview | Owner/path/CSP checks exist; failure between file write and DB commit can orphan bytes (F-04) |
| OTA | Native config/checker → public update endpoint → signed manifest/assets → next app launch | JS build and checker tests pass; signature verification on an installed signed binary not tested |
| Agent creation docs | README says name/avatar/color only → actual route requires account/symbol | Documentation drift, source/frontend enforce stronger requirements (F-10) |

Shared TS/Python contracts coexist; successful TS checking is not proof those contracts are identical. The source request catalog is a cross-layer audit aid, not exhaustive request/response compatibility certification. Remaining components are explicitly marked in coverage.

## 9. Runtime lifecycle and deployment

**Startup:** root CLI entry points are `lonora-api` and `lonora-gateway` (`pyproject.toml:16`). API construction loads required settings, creates DB/runtime services and middleware, imports router modules and conditionally mounts Web assets. Lifespan ensures the personal agent for an existing owner. Gateway installs signals, creates supervised tasks and writes state heartbeats.

**Steady state:** database-backed work claims and events span processes. Per-owner caches are process-local. Gateway maintenance serially performs heartbeat/scheduler/reconciliation/recovery work; an external delay in this loop can affect freshness and subsequent ticks. Market/watch/voice/channel loops are separate supervised tasks, but their internal per-owner operations still have their own latency/failure behavior.

**Shutdown:** stop is requested by signal, Gateway moves to draining, gives work a grace period, cancels/gathers tasks, closes voice/broker/visual resources, writes stopped state and closes DB. Production Compose grants 40 seconds (`infra/compose/docker-compose.prod.yml:51`). Source lifecycle is not proof of graceful broker/network teardown under process kill.

**Health:** `/health` tests DB access. `/ready` returns gateway health in JSON but does not set a failing HTTP status when gateway readiness is false. Compose API health uses `/health`; Gateway has no separate healthcheck in that recipe. See F-03/F-08 before relying on these endpoints as a deployment gate.

**Persistent storage:** production recipe declares database and artifact volumes; read-only OTA/APK release mounts feed public delivery. Encrypted secrets depend on retaining the original encryption key. Backup writes DB dump and filesystem archives/checksums with restrictive umask; restore requires explicit `--replace`, checks checksums and archive paths and restores DB/files. Neither script was executed; syntax passed. Backup/restore correctness under concurrent writes and full disaster recovery remain unverified (`scripts/backup.sh:1`; `scripts/restore.sh:1`).

**Operational assumptions:** valid migrated PostgreSQL; consistent encryption/configuration; allowed origin/session/passkey settings aligned with deployment; required providers configured; production domain/reverse proxy; installed Chromium when screenshot capability is enabled; separately provisioned workspace host for executable analysis. Configuration is evidence of intended deployment, not evidence that these resources exist.

## 10. Security and financial correctness observations

Source-inspected protections include owner scoping and singleton bootstrap, password hashing and session-token hashes, CSRF for cookie mutations, finite session lifetime/revocation, WebAuthn-bound authority, encrypted secrets, URL restrictions, sandboxed artifact previews, bounded MCP responses, workspace network isolation and exact image/source validation. These are relevant controls, not a substitute for a complete adversarial review.

Financial controls are enforced at multiple meaningful boundaries: tool market/agent scope, explicit approval or bounded standing grant, operation identity, broker configuration version, fresh preflight, lease/goal lineage, target material state and executor's `before_send`. Journal state remains the authority for uncertain results. The current confirmed approved-batch defect must be assessed in that context: it continues to later independently authorized operations after uncertainty, rather than proving arbitrary unauthorized trading.

The most important open security questions are full descendant cancellation semantics, check-to-connect DNS binding for configurable URLs, all shared JSON/TS/Python contract edges, optional workspace containment under adversarial inputs, and provider/transcript/rich-content boundaries not fully covered by inspection. F-07/F-09 are conditional risks, not demonstrated exploits.

## 11. Maintainability, duplication and performance

There are multiple intentionally distinct concepts: ordinary Runs vs durable Tasks vs trading Goals; instruction skills vs executable packages; imported simulation vs Shadow; direct owner trade actions vs agent approvals vs signed standing grants. Collapsing them would erase meaningful lifecycle/authority distinctions. The current docs should explain them more accurately.

There is also real duplicated policy surface: the two batch execution loops differ in stop behavior (F-01), and similar Web/native client layers and TS/Python contracts require consistency tests. Thin `session`, `automation`, `channels` and `bus` modules sometimes wrap durable DB functions or offer generic helpers. A package diagram alone overstates their runtime independence. No blanket “too many files” finding is warranted.

Observed build warning: the Web app chunk is 718.56 kB minified / 228.61 kB gzip, exceeding Vite's 500 kB warning threshold. This is a bundle-size observation, not measured slow UX. Market/Trading/Settings are already lazy imported (`apps/web/src/pages/Shell.tsx:87`); any optimization should be based on client timing and route demand. Other performance risks needing measurement include 15-second client refreshes and serial external work in maintenance. No load, memory, latency or concurrency benchmark was run.

## 12. Verification results and legitimate conclusions

| Check | Observed result | What it establishes / does not establish |
|---|---|---|
| Tracked-file inventory/hash + Python AST | 1,990 paths; 783 Python parses; exit 0 | Syntax/structure on local Python; not imports, types or behavior |
| TS parser extraction | 389 files; no parse diagnostics; exit 0 | Syntax/index extraction; not complete reachability |
| `pnpm lint` | Passed, 427 files checked, no fixes | Configured Biome gate only |
| `pnpm check` | Passed, seven workspace tasks, cache misses | Configured TS checks, not Python/DB compatibility |
| `pnpm build` | Passed, seven tasks, cache misses | Web production assets + Expo Web/Android/iOS JS exports; not native binaries/device tests |
| Five CI-declared mobile test files via `tsx --test` | 25 passed, zero failed/skipped | Local OTA/timeline/mention/voice lifecycle fixtures only |
| `bash -n` on 12 tracked shell files | Passed | Shell syntax, no script side effects executed |
| Static migration graph | 32 revisions, one root/head, no unresolved parent/cycle | Structural chain only; no migration SQL applied |
| Actual extracted `WebhookAdapter.send` + dispatcher merge with local transport | Defect reproduced: status stored as numeric 200 | Confirms Python merge behavior; no real endpoint delivery |
| Actual extracted `approved_execution` with local DB/executor stand-ins | Defect reproduced: ambiguous then confirmed, two calls, approval completed | Confirms orchestration control flow; no live financial or real DB verification |
| Every original tracked hash after checks | Unchanged | No application/configuration modification by this audit |
| `bash scripts/build.sh` Python gates | Blocked: .venv and Ruff/Pyright/application deps absent | JS build is not the full repository gate |
| Python tests/foundation checks/PostgreSQL migrations | Not executed: backend prerequisites absent; no isolated migrated DB prepared | No backend/integration pass claimed |
| Browser journeys | Not run: backend not ready | No visual/UI end-to-end certification |
| Signed native build, installation, actual passkey/media/OTA | Not run | JS exports do not establish these behaviors |
| Live broker, model, channels, MCP and financial effects | Not run; audit explicitly prohibits real financial/account/production effects | No external execution claim; local stand-ins are not external evidence |

The exact selected mobile command was:

```sh
pnpm exec tsx --test tests/mobile/ota-checker.test.ts tests/mobile/voice-transport.test.ts tests/mobile/voice-readiness.test.ts tests/mobile/conversation-timeline.test.ts tests/mobile/mention-session.test.ts
```

The local installed toolchain was Node 24.21.0, pnpm 11.25.0, Python 3.14.4 and Turbo 2.11.7. Checks were run from the checkout, using existing dependencies. No runtime dependency was added. Build outputs were ignored generated artifacts. `.venv` was absent and `find_spec` checks found no FastAPI, Pydantic, SQLAlchemy, asyncpg, httpx, pytest, Ruff, Pyright, cryptography or webauthn in global Python.

Existing test and CI definitions are cataloged, but were not silently counted as passing. CI also embeds a substantial Python regression program in `.github/workflows/ci.yml`; that configuration is executable test input and remains partially reviewed. The foundation harness requires isolated databases; no preexisting database was repurposed.

## 13. Prioritized assessment and minimum next work

See [FINDINGS_AND_RECOMMENDATIONS.md](FINDINGS_AND_RECOMMENDATIONS.md) for the full evidence, impact, validation limits and minimum repair for each finding.

1. Repair and regression-test the approved multi-request stop-on-uncertainty contract (F-01) before relying on that workflow for live management.
2. Repair Webhook receipt typing and artifact failure cleanup; decide explicit channel recovery semantics (F-02/F-04/F-05).
3. Make readiness useful for its actual operational consumer and isolate heartbeat freshness from slow maintenance (F-03/F-08).
4. Label external incoming-call delivery accurately; wire a provider only if that capability is intended (F-06).
5. Verify and address conditional URL resolution and descendant cancellation risks against explicit contracts (F-07/F-09).
6. Correct documentation drift and describe conservative reconciliation limitations (F-10/F-11).
7. Complete outstanding semantic inspection and run the repository's Python/isolated-DB/browser/device gates in an appropriate test environment. Preserve provenance and source hashes when continuing.

No application repair, refactor, dependency/configuration change, deployment, PR, live trade or production mutation was performed.

## 14. Open questions and unresolved scope

- What operational guarantee should cancelling a root delegation provide for grandchildren and already-authorized effects? Immediate children are fenced, but full-tree semantics need explicit confirmation and DB tests.
- Which external device delivery provider, if any, is intended for incoming calls? Normal runtime wiring supplies none.
- What operator evidence/procedure resolves ambiguous modifications/cancellations beyond the current adapter's conservative response?
- Are current voice provider endpoints available to the configured account, and do deployed Web/native origin and media constraints agree? Source strings do not answer this.
- Are production settings, secrets, provider accounts, artifact/OTA volumes, migration state, reverse-proxy identity and optional workspace provisioned correctly? They were not inspected as production state.
- Do all indexed UI controls/TS payloads match Python contracts under authorization errors, races and reconnect? Type checking alone does not establish this.
- Are all migrations upgrade/downgrade-safe for real historical data? Static graph validity is insufficient.
- What are measured runtime performance, event retention, storage growth, backup consistency and restore objectives?
- All `I` files and incompletely reviewed `T` portions in the manifest remain semantic work. This is the exact completion gap, not a claim that excluded vendor files are the only missing review.

## 15. Package dependency inventory

The following table is parsed from every tracked `pyproject.toml` and `package.json`. Names/scripts/dependencies are declarations, not evidence that each package runs independently. This also captures test/build/dev dependencies that are easy to miss when describing only application entry points.

| Manifest | Name | Family | Scripts | Dependencies | Optional/development |
|---|---|---|---|---|---|
| `apps/api/pyproject.toml:1` | lonora-api | Python | {} | fastapi>=0.115,<1, lonora-adapters==0.2.0, lonora-agent==0.2.0, lonora-auth==0.2.0, lonora-automation==0.2.0, lonora-bus==0.2.0, lonora-channels==0.2.0, lonora-charts==0.2.0, lonora-contracts==0.2.0, lonora-core==0.2.0, lonora-db==0.2.0, lonora-gateway==0.2.0, lonora-logging==0.2.0, lonora-market==0.2.0, lonora-memory==0.2.0, lonora-providers==0.2.0, lonora-security==0.2.0, lonora-session==0.2.0, lonora-tools==0.2.0, lonora-trading==0.2.0, lonora-voice==0.2.0, pydantic-settings>=2.6,<3, pydantic>=2.10,<3, sqlalchemy[asyncio]>=2.0.36,<3, uvicorn[standard]>=0.30,<1 | {} |
| `apps/mobile/package.json:1` | @lonora/mobile | JS/TS | {"start": "expo start", "android": "expo run:android", "ios": "expo run:ios", "android:release": "python3 scripts/android-release.py", "android:verify": "python3 scripts/android-verify.py", "check": "tsc --noEmit -p tsconfig.json", "check:expo": "expo install --check", "build": "expo export --platform all", "build:web": "expo export --platform web"} | {"@expo/metro-runtime": "57.0.17", "@lonora/contracts": "workspace:*", "@lonora/core": "workspace:*", "@lonora/ui-tokens": "workspace:*", "expo": "57.0.30", "expo-constants": "57.0.22", "expo-document-picker": "57.0.3", "expo-file-system": "57.0.7", "expo-linking": "57.0.13", "expo-router": "57.0.28", "expo-secure-store": "57.0.4", "expo-sharing": "57.0.23", "expo-status-bar": "57.0.1", "expo-updates": "~57.0.26", "react": "19.2.3", "react-dom": "19.2.3", "react-native": "0.86.3", "react-native-incall-manager": "4.3.0", "react-native-passkeys": "0.4.2", "react-native-reanimated": "4.5.1", "react-native-safe-area-context": "5.7.0", "react-native-screens": "4.26.2", "react-native-svg": "15.15.4", "react-native-web": "0.21.2", "react-native-webrtc": "124.0.8", "react-native-webview": "13.16.1", "react-native-worklets": "0.10.1"} | {"@react-native/metro-config": "0.86.3", "@types/react": "19.2.18", "@types/react-dom": "19.2.7", "typescript": "6.0.3"} |
| `apps/web/package.json:1` | @lonora/web | JS/TS | {"check": "tsc --noEmit -p tsconfig.json", "build": "node scripts/verify-chart-assets.mjs && tsc --noEmit -p tsconfig.json && vite build", "dev": "vite --host 0.0.0.0", "i18n": "lingui extract --overwrite"} | {"@fontsource-variable/geist": "5.3.0", "@lingui/core": "6.9.1", "@lingui/react": "6.9.1", "@lonora/chat-ui": "workspace:*", "@lonora/contracts": "workspace:*", "@lonora/core": "workspace:*", "@lonora/ui-tokens": "workspace:*", "@lonora/ui-web": "workspace:*", "lucide-react": "^1.44.0", "react": "19.2.3", "react-dom": "19.2.3", "react-router-dom": "^7.9.0"} | {"@lingui/babel-plugin-lingui-macro": "6.9.1", "@lingui/cli": "6.9.1", "@lingui/vite-plugin": "6.9.1", "@tailwindcss/vite": "^4.1.18", "@types/react": "^19.2.0", "@types/react-dom": "^19.2.0", "@vitejs/plugin-react": "^5.1.0", "tailwindcss": "^4.1.18", "typescript": "5.9.3", "vite": "7.3.7"} |
| `apps/worker/pyproject.toml:1` | lonora-worker | Python | {} | lonora-api==0.2.0, lonora-db==0.2.0, lonora-gateway==0.2.0, lonora-logging==0.2.0 | {} |
| `package.json:1` | lonora-workspace | JS/TS | {"build": "turbo run build", "check": "turbo run check", "lint": "biome check apps/web apps/mobile packages/ui-web packages/chat-ui packages/ui-tokens packages/contracts/src/*.ts packages/contracts/package.json packages/contracts/tsconfig.json packages/core/src/*.ts packages/core/package.json packages/core/tsconfig.json playwright.config.mjs tests/web tests/mobile", "format": "biome format --write apps/web apps/mobile packages/ui-web packages/chat-ui packages/ui-tokens packages/contracts/src/*.ts packages/contracts/package.json packages/contracts/tsconfig.json packages/core/src/*.ts packages/core/package.json packages/core/tsconfig.json playwright.config.mjs tests/web tests/mobile", "i18n": "pnpm --filter @lonora/web i18n", "dev:mobile": "pnpm --filter @lonora/mobile start", "build:mobile": "pnpm --filter @lonora/mobile build", "check:mobile": "pnpm --filter @lonora/mobile check && pnpm --filter @lonora/mobile check:expo", "test:web": "playwright test", "test:clients": ".venv/bin/python tests/check_clients.py", "test:mobile": "LONORA_UI_TEST_APP=mobile playwright test", "test:streaming": ".venv/bin/python tests/check_streaming.py"} | {} | {"@biomejs/biome": "2.5.15", "@playwright/test": "1.58.2", "@types/node": "^24.0.0", "tsx": "^4.21.0", "turbo": "^2.8.0", "typescript": "5.9.3"} |
| `packages/adapter-kit/pyproject.toml:1` | lonora-adapter-kit | Python | {} | lonora-contracts==0.2.0, lonora-core==0.2.0, pydantic>=2.10,<3, tiktoken==0.12.0 | {} |
| `packages/adapters/pyproject.toml:1` | lonora-adapters | Python | {} | httpx>=0.28,<0.29, jsonschema==4.25.1, lonora-adapter-kit==0.2.0, lonora-contracts==0.2.0, lonora-core==0.2.0, lonora-db==0.2.0, lonora-security==0.2.0, lonora-session==0.2.0, lonora-trading==0.2.0, metaapi-cloud-sdk==29.1.1, sqlalchemy[asyncio]>=2.0.36,<3, websockets>=14,<17 | {} |
| `packages/agent-runtime/pyproject.toml:1` | lonora-agent | Python | {} | lonora-adapter-kit==0.2.0, lonora-automation==0.2.0, lonora-contracts==0.2.0, lonora-core==0.2.0, lonora-db==0.2.0, lonora-llm-usage==0.2.0, lonora-memory==0.2.0, lonora-security==0.2.0, lonora-session==0.2.0, lonora-tools==0.2.0, sqlalchemy[asyncio]>=2.0.36,<3, PyYAML>=6,<7 | {"workspace-host": ["fastapi>=0.115,<1", "uvicorn[standard]>=0.30,<1"]} |
| `packages/auth/pyproject.toml:1` | lonora-auth | Python | {} | lonora-contracts==0.2.0, lonora-core==0.2.0, lonora-db==0.2.0, pwdlib[argon2]>=0.2,<1, sqlalchemy[asyncio]>=2.0.36,<3, webauthn>=2.7,<2.8 | {} |
| `packages/automation/pyproject.toml:1` | lonora-automation | Python | {} | lonora-contracts==0.2.0, lonora-core==0.2.0, lonora-db==0.2.0, sqlalchemy[asyncio]>=2.0.36,<3 | {} |
| `packages/bus/pyproject.toml:1` | lonora-bus | Python | {} | lonora-adapter-kit==0.2.0, lonora-contracts==0.2.0, lonora-db==0.2.0 | {} |
| `packages/channels/pyproject.toml:1` | lonora-channels | Python | {} | lonora-contracts==0.2.0, lonora-core==0.2.0, lonora-db==0.2.0, pydantic>=2.10,<3 | {} |
| `packages/charts/pyproject.toml:1` | lonora-charts | Python | {} | lonora-adapters==0.2.0, lonora-contracts==0.2.0, lonora-core==0.2.0, lonora-db==0.2.0, lonora-market==0.2.0, Pillow>=11,<13 | {} |
| `packages/chat-ui/package.json:1` | @lonora/chat-ui | JS/TS | {"check": "tsc --noEmit -p tsconfig.json", "build": "tsc --noEmit -p tsconfig.json"} | {"@lonora/ui-web": "workspace:*", "@lingui/core": "6.9.1", "@lingui/react": "6.9.1", "linkify-it": "5.0.2", "@types/linkify-it": "5.0.0", "react-markdown": "10.1.0", "remark-gfm": "4.0.1"} | {"typescript": "5.9.3", "@types/react": "^19.2.0", "@types/react-dom": "^19.2.0"} |
| `packages/contracts/package.json:1` | @lonora/contracts | JS/TS | {"check": "tsc --noEmit -p tsconfig.json", "build": "tsc --noEmit -p tsconfig.json"} | {} | {"typescript": "5.9.3"} |
| `packages/contracts/pyproject.toml:1` | lonora-contracts | Python | {} | pydantic>=2.10,<3 | {} |
| `packages/core/package.json:1` | @lonora/core | JS/TS | {"check": "tsc --noEmit -p tsconfig.json", "build": "tsc --noEmit -p tsconfig.json"} | {"@lonora/contracts": "workspace:*"} | {"typescript": "5.9.3"} |
| `packages/core/pyproject.toml:1` | lonora-core | Python | {} | croniter>=6,<7, lonora-contracts==0.2.0 | {} |
| `packages/db/pyproject.toml:1` | lonora-db | Python | {} | alembic>=1.14,<2, asyncpg>=0.30,<1, lonora-contracts==0.2.0, lonora-core==0.2.0, pydantic>=2.10,<3, sqlalchemy[asyncio]>=2.0.36,<3 | {} |
| `packages/gateway/pyproject.toml:1` | lonora-gateway | Python | {} | lonora-adapter-kit==0.2.0, lonora-adapters==0.2.0, lonora-agent==0.2.0, lonora-automation==0.2.0, lonora-bus==0.2.0, lonora-channels==0.2.0, lonora-contracts==0.2.0, lonora-core==0.2.0, lonora-db==0.2.0, lonora-market==0.2.0, lonora-providers==0.2.0, lonora-tools==0.2.0, lonora-trading==0.2.0, lonora-voice==0.2.0, sqlalchemy[asyncio]>=2.0.36,<3 | {} |
| `packages/llm-usage/pyproject.toml:1` | lonora-llm-usage | Python | {} | lonora-contracts==0.2.0, lonora-db==0.2.0 | {} |
| `packages/logging/pyproject.toml:1` | lonora-logging | Python | {} | lonora-core==0.2.0, lonora-security==0.2.0 | {} |
| `packages/market/pyproject.toml:1` | lonora-market | Python | {} | lonora-adapter-kit==0.2.0, lonora-adapters==0.2.0, lonora-charts==0.2.0, lonora-contracts==0.2.0, lonora-core==0.2.0, lonora-db==0.2.0, lonora-session==0.2.0, sqlalchemy[asyncio]>=2.0.36,<3 | {} |
| `packages/memory/pyproject.toml:1` | lonora-memory | Python | {} | httpx>=0.28,<0.29, lonora-contracts==0.2.0, lonora-core==0.2.0, lonora-db==0.2.0, lonora-providers==0.2.0, lonora-session==0.2.0, sqlalchemy[asyncio]>=2.0.36,<3 | {} |
| `packages/providers/pyproject.toml:1` | lonora-providers | Python | {} | lonora-adapter-kit==0.2.0, lonora-adapters==0.2.0, lonora-contracts==0.2.0, lonora-core==0.2.0, lonora-db==0.2.0, python-dotenv>=1,<2 | {} |
| `packages/security/pyproject.toml:1` | lonora-security | Python | {} | cryptography>=44,<48, lonora-contracts==0.2.0, lonora-core==0.2.0 | {} |
| `packages/session/pyproject.toml:1` | lonora-session | Python | {} | lonora-contracts==0.2.0, lonora-core==0.2.0, lonora-db==0.2.0 | {} |
| `packages/tools/pyproject.toml:1` | lonora-tools | Python | {} | httpx>=0.28,<0.29, lonora-adapter-kit==0.2.0, lonora-adapters==0.2.0, lonora-agent==0.2.0, lonora-charts==0.2.0, lonora-contracts==0.2.0, lonora-core==0.2.0, lonora-db==0.2.0, lonora-market==0.2.0, lonora-memory==0.2.0, lonora-providers==0.2.0, lonora-security==0.2.0, lonora-session==0.2.0, lonora-trading==0.2.0, pydantic>=2.10,<3, sqlalchemy[asyncio]>=2.0.36,<3 | {} |
| `packages/trading/pyproject.toml:1` | lonora-trading | Python | {} | lonora-adapter-kit==0.2.0, lonora-adapters==0.2.0, lonora-contracts==0.2.0, lonora-core==0.2.0, lonora-db==0.2.0, lonora-market==0.2.0, lonora-security==0.2.0, lonora-session==0.2.0, sqlalchemy[asyncio]>=2.0.36,<3 | {} |
| `packages/ui-tokens/package.json:1` | @lonora/ui-tokens | JS/TS | {"check": "tsc --noEmit -p tsconfig.json", "build": "tsc --noEmit -p tsconfig.json", "generate": "tsx src/generate-css.ts"} | {} | {"typescript": "5.9.3", "@types/react": "^19.2.0", "@types/react-dom": "^19.2.0"} |
| `packages/ui-web/package.json:1` | @lonora/ui-web | JS/TS | {"check": "tsc --noEmit -p tsconfig.json", "build": "tsc --noEmit -p tsconfig.json"} | {"@base-ui/react": "1.8.0", "@lonora/ui-tokens": "workspace:*", "@lingui/core": "6.9.1", "@lingui/react": "6.9.1", "class-variance-authority": "0.7.1", "clsx": "2.1.1", "cmdk": "1.1.1", "lucide-react": "^1.44.0", "tailwind-merge": "^3.6.0", "tw-animate-css": "1.4.0", "@lonora/core": "workspace:*"} | {"typescript": "5.9.3", "@types/react": "^19.2.0", "@types/react-dom": "^19.2.0"} |
| `packages/voice/pyproject.toml:1` | lonora-voice | Python | {} | lonora-agent==0.2.0, lonora-adapters==0.2.0, lonora-api==0.2.0, lonora-bus==0.2.0, lonora-contracts==0.2.0, lonora-core==0.2.0, lonora-db==0.2.0, lonora-gateway==0.2.0, lonora-providers==0.2.0, numpy>=2,<3, sqlalchemy[asyncio]>=2.0.36,<3 | {} |
| `pyproject.toml:1` | lonora | Python | {"lonora-api": "lonora_api.server:main", "lonora-gateway": "lonora_worker.main:main"} | alembic>=1.14,<2, asyncpg>=0.30,<1, fastapi>=0.115,<1, httpx>=0.27,<1, pydantic>=2.10,<3, pydantic-settings>=2.6,<3, sqlalchemy[asyncio]>=2.0.36,<3, uvicorn[standard]>=0.30,<1, PyJWT>=2.10,<3, pwdlib[argon2]>=0.2,<1, cryptography>=44,<48, webauthn>=2.7,<2.8, python-multipart>=0.0.20,<1, croniter>=6,<7, websockets>=14,<17, metaapi-cloud-sdk==29.1.1, numpy>=2,<3, python-dotenv>=1,<2, Pillow>=11,<13, tiktoken==0.12.0, playwright==1.58.0, PyYAML>=6,<7, jsonschema==4.25.1 | {"dev": ["setuptools>=75", "wheel", "aiosqlite>=0.20", "pytest>=8.3,<9", "pytest-asyncio>=0.25,<2", "ruff>=0.11,<1", "pyright>=1.1.406,<2", "types-jsonschema>=4.25,<5"]} |

## 16. Migration inventory

Names are structural identifiers; detailed data transformations have not all been semantically audited. The coverage manifest states per-file inspection.

| Migration file | Revision | Parent |
|---|---|---|
| `packages/db/migrations/versions/0001_foundation.py:1` | 0001_foundation | None |
| `packages/db/migrations/versions/0002_thread_sequences.py:1` | 0002_thread_sequences | 0001_foundation |
| `packages/db/migrations/versions/0003_run_leases.py:1` | 0003_run_leases | 0002_thread_sequences |
| `packages/db/migrations/versions/0004_memory_skills.py:1` | 0004_memory_skills | 0003_run_leases |
| `packages/db/migrations/versions/0005_routines.py:1` | 0005_routines | 0004_memory_skills |
| `packages/db/migrations/versions/0006_groups_peers.py:1` | 0006_groups_peers | 0005_routines |
| `packages/db/migrations/versions/0007_global_models.py:1` | 0007_global_models | 0006_groups_peers |
| `packages/db/migrations/versions/0008_voice.py:1` | 0008_voice | 0007_global_models |
| `packages/db/migrations/versions/0009_broker_sessions.py:1` | 0009_broker_sessions | 0008_voice |
| `packages/db/migrations/versions/0010_charts_watches.py:1` | 0010_charts_watches | 0009_broker_sessions |
| `packages/db/migrations/versions/0011_trading_journal.py:1` | 0011_trading_journal | 0010_charts_watches |
| `packages/db/migrations/versions/0012_reconciliation.py:1` | 0012_reconciliation | 0011_trading_journal |
| `packages/db/migrations/versions/0013_market_snapshots.py:1` | 0013_market_snapshots | 0012_reconciliation |
| `packages/db/migrations/versions/0014_agent_profiles.py:1` | 0014_agent_profiles | 0013_market_snapshots |
| `packages/db/migrations/versions/0015_trading_goals.py:1` | 0015_trading_goals | 0014_agent_profiles |
| `packages/db/migrations/versions/0016_trade_approvals.py:1` | 0016_trade_approvals | 0015_trading_goals |
| `packages/db/migrations/versions/0017_agent_trading_binding.py:1` | 0017_agent_trading_binding | 0016_trade_approvals |
| `packages/db/migrations/versions/0018_agent_scope_timeline.py:1` | 0018_agent_scope_timeline | 0017_agent_trading_binding |
| `packages/db/migrations/versions/0019_collaboration_mentions.py:1` | 0019_collaboration_mentions | 0018_agent_scope_timeline |
| `packages/db/migrations/versions/0020_approval_broker_snapshot.py:1` | 0020_approval_broker_snapshot | 0019_collaboration_mentions |
| `packages/db/migrations/versions/0021_thread_work_lane.py:1` | 0021_thread_work_lane | 0020_approval_broker_snapshot |
| `packages/db/migrations/versions/0022_delegated_scope.py:1` | 0022_delegated_scope | 0021_thread_work_lane |
| `packages/db/migrations/versions/0023_task_outcome_projection.py:1` | 0023_task_outcome_projection | 0022_delegated_scope |
| `packages/db/migrations/versions/0024_trading_opportunity.py:1` | 0024_trading_opportunity | 0023_task_outcome_projection |
| `packages/db/migrations/versions/0025_shadow_execution.py:1` | 0025_shadow_execution | 0024_trading_opportunity |
| `packages/db/migrations/versions/0026_attention.py:1` | 0026_attention | 0025_shadow_execution |
| `packages/db/migrations/versions/0027_device_authority.py:1` | 0027_device_authority | 0026_attention |
| `packages/db/migrations/versions/0028_analytical_workspace.py:1` | 0028_analytical_workspace | 0027_device_authority |
| `packages/db/migrations/versions/0029_account_authority.py:1` | 0029_account_authority | 0028_analytical_workspace |
| `packages/db/migrations/versions/0030_full_account_management.py:1` | 0030_full_account_management | 0029_account_authority |
| `packages/db/migrations/versions/0031_event_delivery_indexes.py:1` | 0031_event_delivery_indexes | 0030_full_account_management |
| `packages/db/migrations/versions/0032_message_rich_content.py:1` | 0032_message_rich_content | 0031_event_delivery_indexes |
