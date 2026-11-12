# Phase 4 map: workspace, secrets and the `lonora` CLI

Mandate sections 7.1, 7.2, 7.3, with 6.1, 6.10, 10.3 (Secret card), 10.3.2 (`connect_credential`), 12.2, 13, 14.3.11.
Code state: `main` at `a776adf` (checkout `/home/user/wt-agent/mandate`). Paths are relative to that checkout; `path:N` is a line number. Short names used below:
`AR` = `packages/agent-runtime/src/lonora_agent`, `TL` = `packages/tools/src/lonora_tools`, `DB` = `packages/db/src/lonora_db`, `TR` = `packages/trading/src/lonora_trading`, `API` = `apps/api/src/lonora_api`, `GW` = `packages/gateway/src/lonora_gateway`.

## 1. Today's workspace

### 1.1 How a job runs
- **One throwaway Docker container per command.** `AnalyticalContainer.execute` (`AR/workspace.py:344-444`) creates a container named `lonora-analysis-<uuid>` (`:362`), starts it, checks the kernel boundary (`_verify`, `:314-342`), writes the input files, runs the command, kills leftovers, exports files, and force-removes the container (`:436-444`, `_remove` `:463-472`).
- **Container flags** (`create_arguments`, `AR/workspace.py:197-239`): `--network=none` (`:207`), `--read-only` (`:211`), `--cap-drop=ALL` plus `--cap-add=KILL` (`:212-213`), `no-new-privileges` (`:214`), 256 MiB memory with no swap (`:216-219`, `MEMORY_BYTES` `:27`), 32 processes (`:220-221`, `PIDS` `:28`), 0.5 CPU (`:222`), tmpfs `/work` 32 MiB and `/tmp` 8 MiB, both `noexec` (`:230-233`), proxy variables emptied (`:234`), entrypoint `sleep 120` (`:236-238`), log driver `none` (`:228`).
- **User.** The model's command runs as UID/GID 10001 with a clean `env -i` environment (`AR/workspace.py:389-409`). A fixed root control program with only `CAP_KILL` kills every UID-10001 process after the shell returns (`QUIESCE` `:47-71`, called `:413-415`). So a background process never outlives its command.
- **Network.** None. `_verify` fails the job unless `/sys/class/net` is exactly `["lo"]` (`AR/workspace.py:332-342`).
- **Time limit.** `0 < deadline_seconds <= 45`, checked in four places: `AR/workspace.py:358`, `AR/workspace_access.py:333`, `AR/workspace_host.py:71`, `TL/workspace.py:33`. The client's HTTP timeout is 60 s (`AR/workspace_client.py:83`).
- **Image.** Only a local `sha256:` image id is accepted (`AR/workspace.py:187-188`), never pulled (`--pull=never` `:200`). Two profiles: bare Python (`infra/analysis/Dockerfile:3-8`) and an analytics image built offline from hash-pinned wheels (`infra/analysis/analytics.Dockerfile:3-15`, `infra/analysis/build-analytics.sh:9-18`). No package can be installed by a job.
- **Persistence.** Files only, and not on disk: one row per agent in `ln_analytical_workspaces` holds a JSON/base64 snapshot (`DB/schema.py:627-636`), limited to 128 files, 2 MiB each, 8 MiB total (`AR/workspace.py:22-24`). Each command receives the snapshot and returns a new one (`AR/workspace_access.py:359`, `:383-397`). Every write names an exact `revision` (`require_revision`, `AR/workspace_access.py:127-131`). Receipts are in `ln_workspace_operations` (`DB/schema.py:639-658`).
- **Scope.** Per agent, not per owner: the row key is `agent_id` (`DB/schema.py:630-632`). A paused agent cannot write (`AR/workspace_access.py:55-58`). A subagent ("helper") may run commands but not edit files (`TL/base.py:50`, `AR/workspace_access.py:345`).
- **Output to the model** is capped at 128 KiB per stream (`AR/workspace.py:26`, `:264-265`) and already marked as untrusted evidence: `workspace_read`, `workspace_inspect`, `workspace_execute` are in `EXTERNAL_TOOLS` (`AR/context/run_evidence.py:52-57`), which also sets the external-content mark on the run (`TL/registry.py:555-559`).

### 1.2 Process chain and where limits are set
- Tools: `workspace_export`, `workspace_inspect`, `workspace_read`, `workspace_update`, `workspace_execute` (`TL/workspace.py:80-122`); the protocol they call is `WorkspaceAccess` (`TL/workspace_access.py:10-33`).
- Gateway side: `RunWorkspaceAccess` (`AR/workspace_access.py:134-446`), built for every tool context in `GW/runtime.py:107-109` from `WorkspaceClient(self.workspace_socket)`.
- Transport: HTTP over a Unix socket, no retry (`AR/workspace_client.py:62-138`, `:111-114`).
- Host bridge: `lonora_agent.workspace_host` (`AR/workspace_host.py:26-160`), a root systemd service with Docker access, two concurrent jobs, busy answer instead of a queue (`:27`, `:38-39`), socket directory mode 0750 and socket 0660 for group 10001 (`:111-126`), orphan reaping at start (`:141`).
- Limits are code constants (`AR/workspace.py:22-29`), not deployment settings. The only deployment setting is the socket path `LONORA_WORKSPACE_SOCKET` (`API/env.py:41`, `:85-90`), passed through `API/runtime.py:26`, `apps/worker/src/lonora_worker/runtime.py:17`, `GW/service.py:79-151`, `GW/run_dispatch.py:42-74`.

### 1.3 Other callers (all must survive or be replaced)
| Caller | What it uses | Where |
|---|---|---|
| `market_candles_to_workspace` | `write_generated` (CSV into the snapshot) | `TL/market_analysis.py:286-353`, tool `:399-407`; open read `TL/market_binding.py:47` |
| Skill packages | Package files live in the agent's snapshot; utilities run with `workspace_access.execute`; the run pins `skill_execution_image` | `AR/skills/lifecycle.py:203-213`, `:346-357`, `:402-410`, `:469-471`; `AR/context/skills.py:67-69`, `:87-119`; tools `TL/skills.py:124-138`; route `API/routes/agent_skills.py:171-199` |
| `workspace_export` | Snapshot file to chat attachment | `AR/workspace_artifacts.py:67-133` |
| Capabilities view | `workspace_files` always ready; `workspace_execution` ready only with a socket | `TL/capabilities.py:89-90`, `:281-285`; `API/routes/capabilities.py:26` |
| Prompt and manifest | Files chapter and tool policies | `packages/agent-runtime/resources/system/lonora.md:160`, `:223`, `:500`, `:582-590`; `resources/system/manifest.json:28-32`, `:60` |
| Evaluation script | Builds the same access object | `scripts/verify_agent_journeys.py:31-33`, `:496-497` |

### 1.4 What the deployment provides
- **Production is Docker Compose**: `db`, `api`, `migrate`, `gateway`, `caddy` on one default network, four named volumes (`infra/compose/docker-compose.prod.yml:11-95`). There is no workspace service in it. Every service has `cap_drop: ALL` and `no-new-privileges` (`:53-54`, `:79-80`). The stack is sized for about 2.3 GB and a 2-vCPU host (`:6-7`; `docs/operations.md:133-145`).
- **The workspace is an optional overlay.** `infra/analysis/compose.workspace.yml:8-31` only bind-mounts `/run/lonora-analysis` read-only into `api` and `gateway` and sets the socket variable. It is used only when listed in `LONORA_COMPOSE_OVERLAYS` (`docs/operations.md:37`).
- **The host bridge is installed by hand.** `infra/analysis/lonora-analysis.service` runs as root (`:8`) from its own venv (`:10`, `:14`). The installer "neither installs nor upgrades it" (`docs/operations.md:219-222`); it only warns when the socket is missing (`infra/compose/install.sh:132-134`). `docs/analytical-workspace.md:249-250` says no default production activation exists.
- `scripts/install.sh:1-32` is the developer install (venv, `.env` keys, web build); it does not touch the workspace. Development Compose is the database only (`docker-compose.yml:1-17`).
- The server image already carries Chromium (`Dockerfile:18`) and runs as UID/GID 10001 (`Dockerfile:42`). A separate, isolated browser service exists in the research overlay, off by default (`infra/research/compose.research.yml:42-65`).
- Backups cover the database, the artifacts volume and `.env` only (`infra/compose/lonora:272-277`; `docs/operations.md:363-370`).
- **Name collision:** the host operator command is already called `lonora` (`infra/compose/lonora:2-16`, linked as `/usr/local/bin/lonora`, `docs/operations.md:39`). The mandate's `lonora` lives inside the workspace, so the files do not collide, but documents must say which one they mean.

## 2. Today's secrets

### 2.1 Store and encryption
- One table, `ln_secrets`: `id`, `owner_id`, `scope`, `name`, `ciphertext`, `updated_at`; unique on `(scope, name)` without the owner (`DB/schema.py:584-592`; migration `packages/db/migrations/versions/0004_memory_skills.py:126-137`).
- Fernet encryption with `LONORA_ENCRYPTION_KEY` (`packages/security/src/lonora_security/secrets.py:23-37`; `API/env.py:13`).
- `EncryptedSecretStore` (`packages/adapters/src/lonora_adapters/storage/secret_store.py:10-57`): `read(secret_id)` checks only the owner, never the scope (`:14-19`); `write` upserts by `(owner, scope, name)` (`:21-50`); `delete(secret_id)` deletes any row of the owner (`:52-57`). One store instance with every scope is on every tool context (`GW/runtime.py:51`, `:101`; `TL/context.py:28`).

### 2.2 Scopes in use
| Scope | Written by | Read by |
|---|---|---|
| `provider` | `API/routes/providers.py:35` | `packages/providers/src/lonora_providers/credentials.py:14-23` |
| `broker` (MetaApi token, named by account id) | `TR/connections.py:98-101` via `POST /trading/connections` (`API/routes/trading.py:65-76`) | `packages/adapters/src/lonora_adapters/brokers/base.py:50-56`; `TR/connections.py:46`, `:69` |
| `integration` | `POST /integrations/secrets` (`API/routes/integrations.py:80-89`) | `TL/search.py:192`, `TL/mcp.py:157`, `GW/event_dispatch.py:69`; MCP refuses any other scope (`TL/mcp.py:99-106`, `API/routes/mcp.py:24-28`) |
| `agent:<agent_id>` | `POST /agents/{id}/secrets` (`API/routes/agent_secrets.py:21-35`) | **nothing** |

- `API/routes/agent_secrets.py` has three routes: list (`:12-18`), store (`:21-35`), and `DELETE /secrets/{secret_id}` (`:38-43`). The contract allows any name up to 80 characters and a value up to 16,000 (`packages/contracts/src/lonora_contracts/agent_secrets.py:6-8`).
- **No secret reaches a workspace job today.** The job environment is fixed (`AR/workspace.py:393-404`) and `tests/check_analytical_workspace.py:56-58` asserts that no secret or Docker socket is visible. Secrets reach only server-side tools, by `secret_id` stored in a connection or integration payload.
- No web or mobile code calls `/agents/{id}/secrets` or `DELETE /secrets/{id}`; the only client secret call is `/integrations/secrets` (`apps/web/src/shell/settings/IntegrationsPage.tsx:366`, `apps/web/src/shell/settings/ConnectionPages.tsx:767`, `packages/core/src/owner-actions.ts:1286`).

### 2.3 The `connect_credential` card
- **Contract.** Kind at `packages/contracts/src/lonora_contracts/owner_actions.py:27`; a closed list of five targets, `mcp_server`, `news_feed`, `brave_search`, `economic_calendar`, `broker` (`:47`); fields `target` and `service` (`:98-100`); TypeScript mirror `packages/contracts/src/owner-actions.ts:23`, `:38-39`.
- **Database.** `DB/capability_cards.py:38-46` (targets and the resource each creates), `:94-100` (payload), `:168-184` (not needed when Brave already has a key), `:216-244` (`connected_result` checks the resource the form created). Lifetime 7 days (`DB/owner_actions.py:83`). After the tap, the agent is woken with fixed text and trigger `owner_card` (`DB/owner_actions.py:2044-2071`).
- **Tool.** `owner_action_propose` with kind `connect_credential` (`TL/owner_actions.py:316-349`), through `propose_capability_card` (`:241-262`).
- **The fields are chosen by the client, not by the agent or the server**: `credentialForm` maps each target to fixed fields (`packages/core/src/owner-actions.ts:1219-1267`).
- **The value takes two steps.** The client posts it to one of four owner routes (`submitCredential`, `packages/core/src/owner-actions.ts:1277-1328`: `/integrations/secrets` `:1286`, `/trading/connections` `:1289`, `/mcp` `:1301`, `/integrations` `:1316`), then confirms the card with `connected: {resource, id}` (`API/routes/owner_actions.py:435-442`). The two steps are not one transaction.
- **Rendering.** Web: `apps/web/src/components/owner-actions/OwnerActionCard.tsx:177-197`, `:396-400`, `:674-718`. Mobile: `apps/mobile/components/owner-action-card.tsx:132-151`, `:268-295`. Confirmation lines: `packages/bus/src/lonora_bus/attention_messages.json:46-49`, `:96-99`. Prompt rule: `resources/system/lonora.md:566`.

### 2.4 Redaction today
- By key name and `Bearer` only: `packages/security/src/lonora_security/secrets.py:7-20`. Used for log messages (`packages/logging/src/lonora_logging/sinks.py:14`, `redaction.py:7-12`), stored tool results (`TL/tool_results.py:35`, `:46`) and progress events (`AR/progress.py:17`).
- Reply privacy filter by pattern (`packages/core/src/lonora_core/public_reply.py:10-25`), applied to answers in `AR/model_runtime.py:250`. Its `PRIVATE_LOCATION` pattern removes any `/workspace...` and `/tmp...` path from a reply (`public_reply.py:11-16`).
- The only replace-by-value code is for MetaApi error text (`packages/core/src/lonora_core/error_logging.py:9-39`, values passed at `packages/adapters/src/lonora_adapters/brokers/metaapi.py:218`, `:246`).
- **Nothing scans output for the stored secret values**, and nothing handles base64, hex or URL-encoded forms.

## 3. CLI, agent tokens, and the services a CLI endpoint must call

### 3.1 What exists
- No CLI endpoint and no agent token: no match for `AGENT_TOKEN`, `agent_token` or `cli_token` in `packages/` or `apps/`. Every API route authenticates the owner's session (`API/middleware/auth.py:16-27`).
- The closest thing is `POST /api/webhook` (`API/routes/webhook.py:16-34`): an owner-level HMAC (`packages/channels/src/lonora_channels/webhook/runtime.py:7-10`), a full `RunRequest` from the caller, idempotent by nonce (`AR/automation/webhooks.py:10-21`). It is off unless `LONORA_WEBHOOK_SECRET` is set (`API/env.py:99`). Its prompt reaches the model as a user-role request, not as data (`AR/context/routine.py:13-26`, `AR/context/builder.py:181-187`).
- Caddy forwards every path to `api:8000` (`infra/compose/Caddyfile.prod:35-37`), and all routers mount on that one app (`API/app.py:124-126`). A route added there is reachable from the internet.

### 3.2 Functions per CLI command
| Command | Function to call | Notes |
|---|---|---|
| `price` | `TL/market.py:56-60` (`read_symbol`, then `broker_market(...).quote`) | Argument preparation and result scoping live in `ToolRegistry.dispatch` (`TL/registry.py:573-582`) |
| `candles` | `TL/market.py:63-73` | Timeframes are `15m`, `1h` style (`TL/market.py:26-28`) |
| `account`, `positions`, `orders` | `account_snapshot` (`TR/accounts.py:7-16`), as `TL/account.py:69-73` | One call returns all three |
| account choice | `list_accounts` (`TL/account.py:47-66`), `default_account` (`TL/market_binding.py:92`) | `--account` required when more than one |
| `trade` | `TL/trade.py:742-770` (`execute`), then `approved_execution` (`:358`), then `ExecutionService.execute` (`TR/execution.py:148`) | Symbol check `order_symbol` (`TL/trade.py:760-762`), size check `require_order_size` (`:698-725`) |
| `close`, `modify`, `cancel` | Same path with `close_position`, `modify_position` / `modify_order`, `cancel_order` | `TradeRequest.symbol` is required (`packages/contracts/src/lonora_contracts/trading.py:30`), so the endpoint must look the ticket up first, as `management_targets` does (`TL/trade.py:79-99`); stale-target capture is `management_snapshot` (`:102-106`) |
| `wake` | `conversation_thread` (`DB/threads.py:66-92`) + `create_run` (`DB/runs.py:140-205`), as `wake_agent` (`AR/automation/wakes.py:8-10`) | `create_run` refuses a paused agent (`DB/runs.py:156-157`). `delegate_peer` cannot be reused: it needs the caller's run lease (`AR/collaboration/peer_messages.py:19`) |
| `notify` | No shared helper. Pattern: lock thread, add `MessageRow(role="assistant")`, emit `message.created` (`DB/activation_acknowledgment.py:30-49`, `AR/collaboration/peer_messages.py:74-93`) | `notify_owner` (`DB/attention.py:345-353`) raises an attention item, which is not what 7.3.8 asks |

### 3.3 Operation id, idempotency, identity (the hard part)
- **Tool operation id** is `stable_id(run_id, "trade:" + request_hash(args))` (`TL/trade.py:765`); close-all uses `stable_id(run_id, "close:" + call_id + ":" + position_id)` (`:798-800`); the approval id is `stable_id(run_id, "approval:" + call_id)` (`:367`). `stable_id` is a UUID5 (`packages/session/src/lonora_session/idempotency.py:7-8`). All three are scoped to a run.
- **The fingerprint** is `trade_fingerprint` (`TR/idempotency.py:5-12`); the door refuses the same id with another fingerprint (`TR/execution.py:162-168`) and reserves the row before sending (`DB/trading_journal.py:23-49`, called at `TR/execution.py:238-245`).
- **The door identifies the agent only through a run lease.** `ExecutionService.execute(owner_id, request, lease=None, ...)` (`TR/execution.py:148-158`). With a lease it runs lineage checks (`:160-161`), permission (`:169-173`), the authority lock (`:192-197`) and records `agent_id` from the leased run (`:266-267`). **Without a lease it is "the owner's manual path"** (`:289`): no agent, no mode, no ownership. That is how `POST /api/trading/execute` works today (`API/routes/trading.py:116-120`).
- The journal row has no agent column (`DB/schema.py:676-694`); attribution lives only in `result.details.execution.agent_id`.
- **An approval needs a waiting run.** `decide` refuses with `trade_approval_run_unavailable` unless the card's run is alive and holds the pending call (`DB/trade_approvals.py:145-149`); approval matching is by `run_id` (`TR/agent_permission.py:45-52`); the send happens when that run resumes (`DB/trade_approvals.py:98-110`).
- `TradeRequest` has no reason, tolerance or label (`packages/contracts/src/lonora_contracts/trading.py:14-38`).
- Statuses for exit codes: `reserved`, `submitted`, `confirmed`, `failed`, `ambiguous`, `resolved` (`contracts/trading.py:111-115`).
- Sends are serialized by a PostgreSQL advisory lock per account (`TR/execution.py:570-573`), so a CLI endpoint in the API process and tool sends in the Gateway process stay serialized. `broker.execute` has exactly one caller (`TR/execution.py:576`).
- A subagent run uses its parent's `agent_id` (`AR/collaboration/subagents.py:51-57`), and may run `workspace_execute` (`TL/base.py:50`).
- Agents have no stored handle. A mention is `@` plus the agent's name (`packages/core/src/lonora_core/group_mentions.py:4-9`; `name` at `DB/schema.py:210`), and names are not unique.

## 4. Built but switched off (section 13) in this area
| Item | State today | Where |
|---|---|---|
| Command execution | Off unless an overlay is listed and a hand-installed root service runs; shows `not_set_up` | `API/env.py:41`; `TL/capabilities.py:90`; `docs/operations.md:219-222` |
| Analytics image (NumPy, pandas, matplotlib) | Optional manual build | `infra/analysis/build-analytics.sh:9-18` |
| Per-agent secrets | Routes exist; no screen, no card, and no code reads scope `agent:` | `API/routes/agent_secrets.py:12-35` |
| `DELETE /secrets/{id}` | No screen and no tool; it can delete a broker token still in use | `API/routes/agent_secrets.py:38-43`; `secret_store.py:52-57` |
| Stdio MCP servers | Accepted by the contract, refused everywhere with `mcp_stdio_isolation_required` | `packages/contracts/src/lonora_contracts/mcp.py:10-12`; `TL/mcp.py:97-98`; `API/routes/mcp.py:22-23` |
| Headless browser | A separate service in an overlay, off by default; `web_browse` shows `not_set_up` | `infra/research/compose.research.yml:42-65`; `TL/capabilities.py:86` |
| External wake | `/api/webhook` answers `webhook_not_configured` without a secret | `API/routes/webhook.py:19-20` |
| Off-app delivery of `owner_notify` | Tool text says in-app only | `TL/incoming_call.py:128-137` (phase 7) |
| "What is running" | Nothing: no process table, route, or screen | none |

## 5. Tests in this area
| Test | Covers | After phase 4 |
|---|---|---|
| `tests/test_analytical_workspace.py` (12 tests, `:22-155`) | Snapshot limits, pinned image, `--network=none`, 45 s bound (`:89-95`), kernel-boundary check | Removed with the old path: `test_fixed_boundary_has_no_mounts_or_credential_inheritance` (`:78`), `test_invalid_command_never_contacts_docker` (`:89`), `test_missing_kernel_boundary_blocks_command_and_removes_job` (`:111`), `test_mutable_or_remote_image_identity_is_not_allowed` (`:73`) assert what 7.1 removes |
| `tests/test_workspace_transport.py` (13 tests, `:64-288`) | Host and client protocol, 45 s bound (`:58`), no retry | Rewritten for the new transport. Keep the rule in `test_client_never_retries_an_uncertain_command` (`:158`) |
| `tests/check_analytical_workspace.py` | Real container: no secrets (`:56-58`), no network (`:62`), timeout (`:106-108`), background processes killed (`:115-119`), fewer than 32 processes (`:141`), no leaked container (`:194`) | Almost all of it asserts removed behavior. Replace with a new isolation check (section 8, step 5) |
| `tests/check_workspace_container_runtime.py` | Agent loop, host restart, orphan reaping, zero financial effect (`:152-155`, `:300-304`) | Replace; keep the "files survive a restart" (`:247`) and "journal unchanged" ideas |
| `tests/check_workspace_runtime.py` | Revisions, receipts, fencing, helper rules (`:186-202`) | Revision assertions go; receipt replay and lease fencing stay |
| `tests/check_analytics_profile.py`, `tests/check_workspace_migrations.py` | Image contents; migration 0028 | First removed; second kept while the tables exist |
| `tests/test_workspace_artifacts.py`, `tests/check_workspace_artifacts.py` | Export formats and replay | Kept, new source of bytes |
| `tests/test_workspace_skill_creation.py`, `tests/check_workspace_skill_creation.py`, `tests/test_skill_packages.py`, `tests/check_skill_packages.py`, `tests/check_public_skill_package.py` | Skill packages in the snapshot | Kept; depends on the decision in Q15 |
| `tests/check_market_analysis.py:142-364` | `market_candles_to_workspace` with revisions and quotas | Rewritten for the file system |
| `tests/test_capability_exposure.py:624-626`, `:845-899` | "Unconfigured" states of workspace tools | Removed: the workspace is always there |
| `tests/test_tool_discovery.py:310`, `:388-389`; `tests/test_teammate_runtime.py:432-433`; `tests/test_proactive_wakes.py:98`; `tests/test_context_engine.py:1362-1380` | Tool names in exposure sets | Updated with the tool names |
| `tests/test_trusted_sources.py:1164` (`test_feeds_and_credentials_reach_agents_as_configured_never_as_values`), `:955`; `tests/check_trusted_sources.py:191`; `tests/check_simple_lonora.py:1386`, `:2091` | Credential card; no value in transcripts or model requests | Kept and widened to the Secret card |
| `tests/test_mcp_boundary.py:235` (`test_wrong_secret_purpose_denied_before_decrypt_and_network`) | Scope check on a secret | Kept; the model for the workspace/broker split |
| `tests/web/capabilities.test.ts:194`, `tests/web/capabilities.spec.mjs:78` | Credential form fields | Rewritten for agent-chosen fields |
| none | `/agents/{id}/secrets`, `DELETE /secrets/{id}`, value redaction, any CLI | New tests needed |

Listed in the foundation runner: `tests/run_foundation_checks.py:32-35`. The eleven core tests of 14.1.2 do not touch this area and must stay green at every step.

## 6. Gap list

| Clause | Status | Files it touches |
|---|---|---|
| 7.1.1 One workspace per owner, per-agent Unix user and home, `/workspace/shared` | **Missing.** Today: one snapshot per agent, one shared UID 10001, no shared directory | `AR/workspace*.py`, `DB/schema.py:627-658`, new image and Compose service, new migration |
| 7.1.2 Egress, persistence, package install, background processes, headless browser, "told which processes ended" | **Missing.** Each point is the opposite today (`AR/workspace.py:207`, `:211`, `:231`, `:413-415`) | Same, plus `AR/context/builder.py` for the ended-process notice |
| 7.1.3 Limits 2 CPU / 4 GiB / 20 GiB / 256 processes / 10 min foreground, changeable in the deployment file | **Missing.** Constants in code (`AR/workspace.py:22-29`); 45 s in four places; default tool timeout 90 s (`TL/base.py:16`) | `infra/compose/docker-compose.prod.yml`, `infra/compose/install.sh:37`, `docs/operations.md:133-145` |
| 7.1.4 Isolation from Lonora's network, database, MetaApi and broker endpoints, except the CLI endpoint | **Partly.** Today nothing is reachable because there is no network. The MetaApi host rule exists only for the SDK: `*.agiliumtrade.ai` (`packages/adapters/src/lonora_adapters/brokers/metaapi.py:101-112`) | Compose networks, a filter component, new acceptance check |
| 7.1.5 "What is running" view, stop one, stop all | **Missing** | New table, API route, `apps/web`, `apps/mobile` |
| 7.2.1 Secret connected through conversation with a fixed card | **Partly.** The card exists for five targets; the prompt already forbids secrets in chat (`lonora.md:566`) | `TL/owner_actions.py`, `DB/capability_cards.py` |
| 7.2.2 Agent chooses fields and label | **Missing.** Closed target list (`contracts/owner_actions.py:47`); fields fixed in the client (`packages/core/src/owner-actions.ts:1219-1267`) | Contracts (Python and TS), core, web, mobile |
| 7.2.3 Destination set by the server tool; broker values never enter the workspace | **Partly.** Scope `broker` exists (`TR/connections.py:98-101`), but `read` ignores scope (`secret_store.py:14-19`) and no `workspace` scope exists | `secret_store.py`, `adapter-kit/secrets.py`, new tool |
| 7.2.4 Owner-scoped, any agent by name, requesting agent for display, migrate per-agent secrets | **Missing.** Scope `agent:<id>` is written and never read | `API/routes/agent_secrets.py`, migration, `DB/secrets.py` |
| 7.2.5 Injection as env `NAME` and file `/run/secrets/NAME` | **Missing.** Names are free text up to 80 characters (`contracts/agent_secrets.py:7`) | New workspace access layer |
| 7.2.6 Redaction of value, base64, hex, URL-encoded as `[secret:NAME]` | **Missing.** Key-name redaction only (`security/secrets.py:7-20`) | `packages/security/src/lonora_security/secrets.py`, the workspace client, the CLI endpoint |
| 7.3.1 `lonora` calls the same services | **Missing.** The functions exist (3.2) but take a `ToolContext` with a lease | New `packages/cli` (client) and endpoint |
| 7.3.2 Command set | **Missing** | Same |
| 7.3.3 Per-agent token, injected, readable only by the agent's Unix user, revoked on delete | **Missing** | New table (FK to `ln_agents`, cascade), `DB/agent_creation.py:341` |
| 7.3.4 Orders through the door, journaled, receipts, card in Ask | **Missing; blocked by phase 3.** The door has no agent identity without a lease (`TR/execution.py:289`); an approval needs a waiting run (`DB/trade_approvals.py:145-149`) | `TR/execution.py`, `TL/trade.py`, `DB/trade_approvals.py` |
| 7.3.5 `--key` idempotency | **Partly.** The door's idempotency works for any id (`TR/execution.py:162-168`); the derivation from agent and key is new | Endpoint |
| 7.3.6 One JSON object, exit codes 0/10/20/30/77 | **Missing** | Client and endpoint |
| 7.3.7 `lonora wake` | **Partly.** `create_run` and `conversation_thread` exist; no handle, no data marking for the text | `AR/context/routine.py:13-15`, `packages/contracts/src/lonora_contracts/runs.py:7-9` |
| 7.3.8 `lonora notify` | **Partly.** Message-post pattern exists inline in twelve places; no shared helper | `DB/messages.py` (new helper) |
| 10.3 Secret card: values straight to the store, agent learns "saved" | **Partly.** True in effect, but in two client calls to four routes (2.3) | `API/routes/owner_actions.py:435-442` |
| 10.3.2 `connect_credential` becomes the Secret card | **Missing** | Everything in 2.3 |
| 6.10 Process output and wake text as data | **Partly.** Tool results are marked (`run_evidence.py:52-57`); wake text has no path yet | `AR/context/routine.py`, `AR/context/run_evidence.py` |
| 12.2 Any command-line tool with the owner's API keys | **Missing** (no install, no network, no secrets) | Follows from 7.1 and 7.2 |
| 14.3.11 `DELETE /secrets/{id}` stays | **Exists** (`API/routes/agent_secrets.py:38-43`); needs a chat path and a guard for secrets in use | Same file |

## 7. Design questions

Each has the options visible in the code and a recommendation. None reopens a decision of the mandate.

**Q1. Container technology.** Docker is the only runtime the deployment has (`infra/compose/install.sh:59-60`). (a) Keep the root host bridge and `docker exec` into one long-lived container: keeps a root service with the Docker socket that the installer does not manage (`docs/operations.md:219-222`). (b) A long-lived Compose service `workspace` with a small supervisor as PID 1 that listens on a Unix socket shared with the Gateway: no Docker socket anywhere, installed and updated by the existing installer, and it follows the current socket pattern (`infra/analysis/compose.workspace.yml:13-19`). **Recommend (b)**, in the base Compose file, not an overlay (section 13).

**Q2. Privileges inside the container.** The supervisor needs `SETUID`, `SETGID`, `CHOWN`, `KILL` and `DAC_OVERRIDE` to create users and drop into them; agents get none. If agents had `sudo`, "only the agent's own Unix user can read its token" (7.3.3) would be false. **Recommend no root for agents**; packages install at user level (Q4).

**Q3. Per-agent users and the shared directory.** The UID must be stable across container re-creation because files in the volume are owned by number. Options: store the mapping in a file in the volume, or in the database. **Recommend the database** (a `workspace_uid` per agent, allocated from 20000 upward); the supervisor creates the user and `/home/<user>` (mode 0700) on first use, idempotently. `/workspace/shared` is group `agents`, mode 2775, with umask 002 for agent commands. On agent deletion: stop its processes, revoke its token, hand its home to Lonora's user (the mandate transfers positions in 3.1.2 but is silent on files; ask the owner if deletion of files is wanted instead).

**Q4. Persistence of installed packages.** Compose re-creates containers on every `lonora update`, so only volumes survive. Options: (a) volumes for `/home` and `/workspace`, with `pip --user`, npm prefix and similar pointing into the home; (b) also a volume on `/usr/local`; (c) replay a recorded `apt` list at start. **Recommend (a)** with a broad base image (Python, Node, git, curl, OpenSSH client, build tools, Chromium with Playwright), and say in the tool description that system packages come from the image.

**Q5. The 20 GiB disk limit.** Named volumes have no quota on a plain ext4 host. Options: (a) a sparse 20 GiB ext4 file mounted through the `local` volume driver with `o=loop`, created by the installer; (b) XFS project quotas (host-dependent); (c) a soft check by the supervisor. **Recommend (a)**, with the size in `.env` beside the other limits (`docker-compose.prod.yml:19-20` shows the pattern). CPU, memory and process limits are plain Compose keys (`cpus`, `mem_limit`, `pids_limit`). The installer's minimums (2,560 MB RAM, 10 GB disk, `infra/compose/install.sh:37`) and the "2.3 GB" statements (`docs/operations.md:143`) must rise.

**Q6. Egress with the blocks of 7.1.4.** (a) Put the workspace on its own bridge: Docker then blocks the database and API by network separation, but the host's published ports (Caddy, so the public API) and private ranges stay reachable, and MetaApi is not blocked. (b) An HTTP proxy with a deny list: breaks SSH and raw TCP, which 7.1.2 requires. (c) A sidecar that owns the network namespace: the workspace uses `network_mode: service:<sidecar>` and has no `NET_ADMIN`; the sidecar sets nftables rules (drop private, link-local and host-gateway ranges and the server's own public address) and runs a resolver that refuses `agiliumtrade.ai`, `metaapi.cloud` and `LONORA_DOMAIN`, plus an address set refreshed from those names. Needs no host firewall change. **Recommend (c).** A process that hard-codes an address can pass a name-based block between refreshes; the real guarantee is 7.2.3 (the MetaApi token is never in the workspace). The broker endpoint list must come from one place: today it is the suffix check at `brokers/metaapi.py:101-112`; phase 8 adds the provisioning host.

**Q7. Where the CLI endpoint lives.** It must not be a route on port 8000, because Caddy publishes that whole app (`Caddyfile.prod:35-37`). Options: (a) a second listener in the API process on a Unix socket, serving a separate FastAPI app with only the CLI router; (b) a third service: one more set of MetaApi connections. The API process already owns `OwnerServices` and runs the door (`API/runtime.py:20-41`, `API/routes/trading.py:116-120`). **Recommend (a)**, with the socket directory mounted into the workspace. The workspace then has no TCP route to Lonora at all, which makes 7.1.4 easy to test. The client is one stdlib-only Python file.

**Q8. Token.** Random 256-bit value, stored hashed, one row per agent with cascade on agent delete. The supervisor writes it to a 0400 file in the agent's home and sets `LONORA_AGENT_TOKEN` for every command; `/proc/<pid>/environ` is readable only by the same UID. Open point: a subagent run has the parent's agent id (`AR/collaboration/subagents.py:56`) and may run commands (`TL/base.py:50`), and the door must keep refusing subagent and observe-only runs (6.9). **Recommend that the token is injected only for commands started by a run of scope `full`** (`run_scope`, `TL/base.py:53-58`); other runs get no token, so the CLI exits 77.

**Q9. Agent identity at the door for a run-less CLI call (phase 3 dependency).** Options: (a) create a synthetic run per CLI order so the existing lease checks apply: costly and it pollutes the run list; (b) let the door take an explicit actor (owner, agent, optional lease) and apply mode, the authority lock, ownership and Stop to the actor, with run checks only when a lease is present. **Recommend (b)**, done in phase 3 when `require_operation_permission` is rewritten (6.7). The same change must let an approved card be sent by the server without a waiting run, because the CLI returns at once with exit 10 (today: `DB/trade_approvals.py:145-149`). The journal needs an agent column or a fixed key in the row for ownership (3.3.4).

**Q10. Listing and stopping processes.** Options: (a) a cgroup per job: needs a writable cgroup tree in the container; (b) by UID: every agent has its own UID, so a `/proc` scan grouped by UID gives "process with the agent that started it", and kill-by-UID in a loop stops everything, as `QUIESCE` already does (`AR/workspace.py:47-71`). **Recommend (b)**, plus a table of started background jobs (agent, command, pid, start, end). A Gateway step (`GW/service.py:40-65` lists the steps) polls the supervisor and records ends; the wake context reports each ended process once to its agent. After a container or host restart every row is ended. The command lines shown in the view must pass the redaction scan (a child's argument list can contain an expanded secret).

**Q11. Where the redaction scan sits.** Bytes leave the workspace by five roads: command output, file reads and exports, the process list, CLI arguments (`notify` text, `wake` text, `--reason`, `--label`), and supervisor logs. Options: (a) at `dispatch_call` (`AR/tool_dispatch.py:23-153`, the single place every tool result passes; callers `AR/tool_block.py:196`, `:233`): misses exports, the process view and the CLI; (b) at the two workspace boundaries: the Gateway's workspace client, on decoded fields, and the CLI endpoint's request decoder. **Recommend (b)** as the rule, with one function beside `redact` in `packages/security/src/lonora_security/secrets.py`. Scan decoded text, not the JSON transport (JSON escaping would hide a value). Scan whole buffers, or keep an overlap as long as the longest form when streaming. Forms: raw, base64 standard and URL-safe with and without padding, hex in both cases, percent-encoding. Short values will corrupt ordinary output (a 4-digit password inside a price): **recommend a minimum length of 8 for workspace secrets**, to confirm with the owner.

**Q12. Secret names and migration.** `NAME` must be a valid environment variable and file name; today it is free text (`contracts/agent_secrets.py:7`). **Recommend** `[A-Z][A-Z0-9_]{0,63}` for scope `workspace`. Migration of `agent:<id>` rows to `workspace`: the unique key is `(scope, name)` (`DB/schema.py:586`), so two agents with the same name collide; keep the newest and rename the other with the agent's name as suffix. In practice the table has few or no such rows, because nothing wrote them from the apps (2.2).

**Q13. Shape of the Secret card and the fate of the five targets.** The card needs a server record with `fields` (each: key, label, secret or not), `label`, `destination`, `requesting_agent_id`, and one submit call that stores the values and settles the card in one transaction. The five targets create resources, not only secrets (`DB/capability_cards.py:40-46`). **Recommend:** each becomes a server tool that takes the non-secret details from chat (7.2.1) and raises the Secret card with destination `workspace` or `broker` fixed in the tool; the resource is created by the server when the card is saved. The broker tool is rebuilt in phase 8 (MetaApi provisioning, section 9); in phase 4 keep today's account-id-plus-token form working on the new card. The push for a waiting Secret card is phase 7 (11.4).

**Q14. `/run/secrets/NAME`.** Options: (a) a private mount namespace per command with only the named secrets: needs `SYS_ADMIN` or user namespaces, which Docker's default profile restricts; (b) a tmpfs `/run/secrets`, directory `root:agents` 0750, files 0440, written when first named and removed on rotation or delete. 7.2.4 lets any agent use any workspace secret, so (b) breaks no rule. **Recommend (b)**, and never pass a value on a command line (`/proc/<pid>/cmdline` is world-readable).

**Q15. Tool surface and the skill package store.** The revision-based file tools do not fit a live file system. **Recommend** new tools (run a command in foreground or background with named secrets, list and stop own processes, read and write files, export), registered in `TL/loader.py:17`, behind the same `ToolContext.workspace_access` seam (`TL/context.py:36`). Skill packages are stored in the per-agent snapshot today (`AR/skills/lifecycle.py:203-213`); workspace files become shared by all agents (3.2.4). **Recommend** keeping `ln_analytical_workspaces` as the private skill-package store (renamed later) and running utilities in the new workspace from a copy; `skill_execution_image` (`AR/context/skills.py:67-69`) loses its meaning and needs a replacement decision (pin the workspace image id, or drop the pin).

**Q16. `lonora wake`.** Handle: agents have none (3.3). Options: add a unique `handle` column, or match the name as mentions do. **Recommend a unique handle column**, filled from the name. Trigger: a new one (for example `workspace_wake`) in `WORK_TRIGGERS` (`contracts/runs.py:7-9`) and in `SERVER_AUTHORED_TRIGGERS` (`AR/context/routine.py:13-15`), with fixed server text that names the calling agent and wraps the script's text in the untrusted-data frame used for tool results (`AR/context/run_evidence.py:81-87`). The run must not carry GenUI taint (`DB/runs.py:187-191`) so 6.10's "taint does not spread" holds. A paused target is refused by `create_run` (`DB/runs.py:156-157`): return exit 20 with that code. A script loop can create runs without bound; the mandate sets no cap. **Recommend** coalescing: one queued wake per (caller, target) pair, later calls update its text. The existing `/api/webhook` has the same data-marking gap and should move to the same frame.

**Q17. `lonora notify`.** Add one helper "post a message as an agent in its own conversation" in `DB/messages.py` and use it here. The text passes the secret scan (Q11). Should it also pass the reply privacy filter (`redact_private_reply`, `AR/model_runtime.py:250`)? **Recommend yes**, and remove `/workspace` and `/tmp` from `PRIVATE_LOCATION` (`packages/core/src/lonora_core/public_reply.py:11-16`), otherwise an agent can never name a shared file to the owner.

**Q18. Exit-code edge cases.** Mapping from `TradeResult.status`: `confirmed` gives 0; a raised card gives 10; `reserved`, `submitted`, `ambiguous` give 30. To settle with the owner: `resolved` (owner attestation is not broker confirmation: `contracts/trading.py:126-135`), **recommend 30 with the attested outcome in the JSON**; a broker rejection after send (`failed`), **recommend 20 with the broker's code**; refusals of read commands, **recommend 20**; bad arguments, **recommend 2**; `--account` missing with several accounts, 20 with `account_required`.

**Q19. Backup, restore, update.** The workspace volume is up to 20 GiB and is not in the backup (`infra/compose/lonora:272-277`). **Recommend** leaving it out by default with a flag to include it, stating it in `docs/operations.md`, and making `restore-test` start without the workspace service. A database rollback after a failed update does not roll the volume back: the process table is rebuilt from the supervisor, so only file contents can be newer than the database, which is acceptable.

**Q20. Lonora's own model keys in the workspace.** 12.2 says "with API keys the owner provided". Scope `provider` holds Lonora's engine keys. **Recommend** they are not workspace secrets automatically; the owner connects a key for workspace use through the Secret card.

**Q21. Foreground limit and tool timeouts.** The terminal tool needs `timeout_seconds` above 600 (`TL/base.py:15-16`, `:102-107`); the run lease is renewed while a tool runs (`AR/executor.py:44-62`). Output to the model stays bounded; **recommend** keeping the 128 KiB cap with the full output saved to a file in the agent's home.

## 8. Ordered steps (one pull request each)

Rule 14.1.1: add the new path, move what must survive, then delete. The core tests of 14.1.2 run on every step.

**Needed from phase 3 before step 10** (order trading from the CLI): (i) the door applies Full/Ask, the authority lock, Stop and ownership to an explicit agent actor, with or without a run (Q9); (ii) a Trade Approval card can be approved and sent without a waiting run; (iii) reason, tolerance and label stored beside the request and outside the fingerprint (14.3.9); (iv) the Execution Receipt posted from any path (10.3); (v) agent attribution on the journal row (3.3.4). Steps 1 to 9 do not depend on phase 3.

1. **Secret store by scope.** Add scope `workspace`, a read-by-name function that can return only that scope, name validation (Q12), and a refusal to delete a secret a connection still uses. Migrate `agent:<id>` rows. Keep `DELETE /secrets/{id}` (14.3.11). Tests: scope isolation in the style of `tests/test_mcp_boundary.py:235`.
2. **Value redaction function.** Pure function and tests for the four forms (the test of 7.2.6). Wire it into today's workspace results at once (`AR/workspace_access.py:398-405`, `:212-219`), so it is live before the new workspace exists.
3. **The Secret card, new path.** Contract, record, raising tool, one submit route, web and mobile rendering with agent-chosen fields and a server-set destination. `connect_credential` keeps working.
4. **Move the five targets to the Secret card, then delete `connect_credential`**: contracts (`contracts/owner_actions.py:27`, `:47`, TS mirror), `DB/capability_cards.py`, the client form code (`packages/core/src/owner-actions.ts:1219-1328`), both card components, the attention messages, `lonora.md:566` with the manifest (5.8.6), `docs/owner-actions.md`, `docs/trusted-sources.md`, and stored owner-action rows of that kind (14.3.9).
5. **Workspace service.** Image, supervisor, network sidecar, volumes, limits in `.env`, installer and operator-command changes (`infra/compose/install.sh`, `infra/compose/lonora`, `docs/operations.md`). New acceptance check: internet reachable; database, API, Caddy, private ranges and MetaApi hosts not reachable; files and user-level packages survive a container re-creation; limits enforced. Nothing uses it yet.
6. **New access layer and tools.** Gateway client for the supervisor with the redaction scan in its decoder, per-agent users, foreground and background commands, secret injection (7.2.5), process table, ended-process notice on wake, results marked as data (add the new tool names to `AR/context/run_evidence.py:52-57`). Old tools still registered.
7. **Move survivors.** Copy each agent's snapshot files into its home; point `market_candles_to_workspace` and export at the file system; settle the skill-package store (Q15); rewrite the files chapter (`lonora.md:160`, `:582-590`) and the manifest; update the exposure tests of section 5.
8. **"What is running".** Route, web and mobile view, stop one, stop all (7.1.5, P5).
9. **CLI endpoint, tokens, client: read commands, `notify`, `wake`.** Separate listener (Q7), token table with revoke on delete, `price`, `candles`, `account`, `positions`, `orders`, then `notify` and `wake` with the helper and trigger of Q16 and Q17. Tests: exit 77 without a token; one JSON object per command.
10. **CLI orders** (after phase 3): `trade`, `close`, `modify`, `cancel` through the one service function the tool also uses, `--key` derivation, exit codes. Tests: a CLI order appears in the journal with the calling agent and gets a receipt; the same `--key` twice gives one operation; a changed request with the same key is refused; Ask gives exit 10 and a card; Stop gives exit 20 for a risk-increasing order; an `ambiguous` row gives 30 and is not resent.
11. **Delete the old path.** `AR/workspace.py`, `workspace_host.py`, `workspace_client.py`, the old half of `workspace_access.py`, `infra/analysis/*`, the `Dockerfile:35` copy, `LONORA_WORKSPACE_SOCKET`, the `workspace-host` extra (`packages/agent-runtime/pyproject.toml:13`), the old tests of section 5, `docs/analytical-workspace.md`; drop `ln_workspace_operations` and, if Q15 moves the packages, `ln_analytical_workspaces`.
12. **Section 13 sweep for this area.** Decide stdio MCP servers (they can now run in the workspace), fold or remove the separate browser service, bring `/api/webhook` under the data frame, and remove `not_set_up` states for what is now always present (`TL/capabilities.py:86-90`).

## 9. Risks to the safety core (section 6)

- **6.1 One door, with identity.** A CLI call has no run. If the endpoint calls `ExecutionService.execute` without a lease, the order runs as the owner's manual order (`TR/execution.py:289`): no mode, no Ask card, no ownership, and under 4.8.3 it would even pass Stop as "the owner's own order". Step 10 must not land before the door has an agent actor (Q9).
- **6.2 Operation id.** Tool ids stay run-scoped (`TL/trade.py:765`); CLI ids are derived from agent and key. Use a distinct namespace string so the two can never collide, and derive on the server only: `TradeRequest.operation_id` is a client-settable field (`contracts/trading.py:17`) and the endpoint must overwrite it.
- **6.3 Never resend.** Without `--key` each invocation is a new operation by the mandate's own rule (7.3.5), so a script that retries on exit 30 sends twice. The existing block on new risk for a market with an unresolved operation (`require_operation_scope`, `TR/execution.py:221-228`; `contracts/trading.py:113-114`) must stay in the door and must apply to CLI orders; the exit-30 output should say that repeating without the same key is a new order.
- **6.4 Broker truth.** Exit 0 only for `confirmed`. `resolved` is the owner's word, not the broker's (Q18).
- **6.6 Stale target.** For `close` and `modify` the endpoint must capture the expected target the way the tool does (`TL/trade.py:102-106`) and pass it to the door; in Ask the capture happens when the card is created.
- **6.7 Exact approval.** Approvals match by run today (`TR/agent_permission.py:45-52`). A run-less card must still match on `operation_id` plus `trade_fingerprint`, under the authority lock.
- **6.9 Run integrity.** The token names an agent, not a run. Without Q8, a subagent or an observe-only wake could trade by running `lonora trade` in a command, which the door refuses today through lineage (`TR/execution.py:81-85`, `:105-109`). A paused agent's background script keeps running; the door must apply 4.7 (risk-reducing only) by the agent's state, since `create_run`'s pause check (`DB/runs.py:156-157`) is not on the CLI path.
- **6.10 Provenance.** `wake` text, `notify` text and `--reason` come from a process that may have read a web page. `wake` text must sit in the data frame and never in the system or user role as a request (`AR/context/routine.py:18-26` shows both roads). The reason shown on a Trade Approval card must stay labelled as the agent's words (10.3).
- **Broker secrets.** `SecretStore.read` has no scope check (`secret_store.py:14-19`) and is on every tool context (`TL/context.py:28`). The injection path must use a reader that cannot return scope `broker` or `provider`; otherwise one wrong id puts the MetaApi token in the workspace and the network block of 7.1.4 becomes the only defence.
- **Redaction misses.** Chunked output, JSON-escaped values, process command lines, exported files and images. Images cannot be scanned; the mandate accepts transformed values (7.2.6), but the test of 7.2.6 must cover every byte road listed in Q11.
- **Hostile code with network access.** The workspace now runs downloaded code with internet access on the same host as the door. No Docker socket, no shared network with the database, capabilities dropped for agent users, and the acceptance check of step 5 are what keep sections 6.1 to 6.9 out of its reach. That check must run in CI, not only by hand as today's container checks do (`docs/analytical-workspace.md:200-209`).
- **Host capacity.** A 4 GiB, 2-CPU workspace on a host sized for 2.3 GB (`docker-compose.prod.yml:6-7`) can starve the Gateway and delay reconciliation of uncertain operations. Keep the Compose limits hard and raise the installer's minimums in the same change that adds the service.
