# Map 1.8: runtime and harness (HEAD 9f5b1da)

Scope: processes, bus, gateway, sessions, run leases, concurrency, permissions and
approvals, secrets, channels, and every harness-level failure the owner can see.
Workspace host internals are excluded. All paths are relative to the repository root.
Read-only audit: nothing in the repository was changed.

Labels used below:

- **needed for safety**: the refusal exists for a money-safety rule and must stay.
- **STOP / LEAK / ASK**: the mechanism makes the agent stop, show an internal code, or
  ask the owner instead of taking a safe read-only step.
- **UNSURE**: could not be confirmed from the code read.

---

## 0. The findings that matter most for the owner's complaint

1. **A failed tool call reaches the model as a bare code and nothing else.** Every
   `LonoraError` raised inside a tool becomes `{"ok": False, "code": error.code}`
   (`packages/agent-runtime/src/lonora_agent/tool_dispatch.py:113`). `LonoraError` has no
   human message field the model can see, only `code`, `status` and two diagnostic
   fields kept for logs (`packages/core/src/lonora_core/user_error.py:1-14`). The only
   extra help is a generic `recovery` object. For any code ending in `_not_found` it is
   `category: "not_found"`, `next_action: "inspect_existing_state"`
   (`packages/agent-runtime/src/lonora_agent/environment.py:80-81`). So for the owner's
   example the model saw, in substance, `{"ok": false, "code": "symbol_not_found",
   "recovery": {"category": "not_found", "next_action": "inspect_existing_state", ...}}`.
   There is no field that says "list this account's symbols and pick the gold one". The
   model has nothing to put in its reply except the code, which is what it printed.
   (LEAK, STOP)

2. **The second code in the owner's example is very likely a mis-mapped error.** In the
   MetaApi adapter every HTTP 404 on any stage other than `candles` is turned into
   `broker_account_not_found`, because of operator precedence in
   `if stage != "candles" or "account" in message and missing:`
   (`packages/adapters/src/lonora_adapters/brokers/metaapi.py:57-58`). The contract read
   (`instrument`) reports stage `"instrument"`
   (`packages/adapters/src/lonora_adapters/brokers/metaapi.py:461-474`), so a 404 for an
   unknown symbol on a healthy account is reported as "account not found". This matches
   the owner's transcript («ومحاولة تفاصيل العقد رجعت **broker_account_not_found** على نفس
   الربط»). UNSURE: I did not confirm what HTTP status MetaApi returns for an unknown
   symbol specification; the mapping itself is as cited. (LEAK, misleading)

3. **Symbol resolution accepts only an exact or case-only match.** `catalog_symbol`
   returns the symbol only if it is in the catalog exactly or differs by letter case;
   otherwise it raises `symbol_not_found`
   (`packages/tools/src/lonora_tools/symbols.py:6-15`). `XAUUSD` against a catalog that
   has `XAUUSDm` therefore fails, and no suffix candidate is returned with the error.
   (STOP)

4. **After three failures of the same call the route is refused without running.**
   `blocked_route` blocks a call whose identical (tool, arguments) pair failed three
   times (`packages/agent-runtime/src/lonora_agent/environment.py:127-131`); the model
   then gets `{"ok": False, "code": "tool_route_exhausted", "recovery": {"next_action":
   "alternate_route_or_wait"}}`
   (`packages/agent-runtime/src/lonora_agent/tool_dispatch.py:70-81`). Another bare code.

5. **The harness itself tells the model to ask.** When a conversational model turn is
   empty the runtime appends: "No answer was provided for the selected request. Provide
   the substantive result or ask a necessary clarification with wait_for_input."
   (`packages/agent-runtime/src/lonora_agent/runtime_notices.py:96-99`). The
   `wait_for_input` tool is in the eager core set
   (`packages/tools/src/lonora_tools/runtime_control.py:199-205`). (ASK)

6. **A conversation Run that fails for a non-provider reason shows a dead-end card.**
   The web error card for family `other` has the title "The agent could not reply"
   (`apps/web/src/conversation/Cards.tsx:74`), the fallback text "The request could not
   be completed. Try again." (`apps/web/src/lib/user_error.ts:227-228`) and **no Retry
   button**, because actions render only when `family !== "other"`
   (`apps/web/src/conversation/Cards.tsx:96`). Arabic: «تعذّر على الوكيل الرد»
   (`apps/web/src/i18n/locales/ar/messages.po:7099-7100`) and «تعذر إكمال الطلب. أعد
   المحاولة.» (`apps/web/src/i18n/locales/ar/messages.po:7416-7417`). The text says "try
   again" and offers no way to do it. (STOP)

7. **The agent cannot reach the owner outside the app.** `owner_notify` says "Delivery
   is in-app only for now" (`packages/tools/src/lonora_tools/incoming_call.py:132-133`);
   the constant is `NOTIFY_DELIVERY = "in_app"`
   (`packages/db/src/lonora_db/attention.py:341`). The gateway calls `incoming_tick`
   with no delivery provider (`packages/gateway/src/lonora_gateway/service.py:253`), and
   with `delivery is None` a call request is skipped
   (`packages/voice/src/lonora_voice/incoming.py:353-354`). Telegram is the only
   off-app path and needs an integration the owner configured (section 9).

---

## 1. Processes and how they start

| Process | Started by | What it is |
| --- | --- | --- |
| `api` | `entrypoint.sh:5-9` → `lonora-api` → `lonora_api.server:main` (`pyproject.toml:17`) | uvicorn serving FastAPI (`apps/api/src/lonora_api/server.py:43`). Optionally runs migrations first when `LONORA_MIGRATE_ON_START` is true (`entrypoint.sh:8`); production sets it false (`infra/compose/docker-compose.prod.yml:41`). |
| `gateway` | `entrypoint.sh:10` → `lonora-gateway` → `lonora_worker.main:main` (`pyproject.toml:18`) | The always-on worker: run workers plus every maintenance step (`apps/worker/src/lonora_worker/main.py:11-23`). |
| `migrate` | `entrypoint.sh:11` | One-shot alembic upgrade. |
| `db` | `docker-compose.yml:2-14` (dev), `infra/compose/docker-compose.prod.yml:11` (prod) | PostgreSQL 16. |

- The root `docker-compose.yml` defines only `db` (`docker-compose.yml:1-17`). Dev
  starts api and gateway as two background shell processes
  (`scripts/dev.sh:7-8`).
- Production compose: `api` (`infra/compose/docker-compose.prod.yml:26-54`), `gateway`
  depends on a healthy api and has `stop_grace_period: 40s`
  (`infra/compose/docker-compose.prod.yml:67-80`), both `restart: unless-stopped`.
- `apps/worker` is the gateway process; there is no separate "worker" service. It builds
  one `Gateway` from settings (`apps/worker/src/lonora_worker/runtime.py:8-30`), installs
  SIGTERM/SIGINT handlers that call `request_stop`
  (`apps/worker/src/lonora_worker/signals.py:6-9`), warms two tokenizer encodings, then
  serves (`apps/worker/src/lonora_worker/main.py:15-21`).
- Settings come from `LONORA_*` environment variables or `.env`
  (`apps/api/src/lonora_api/env.py:11`). Tuning defaults: lease 120 s, 24 tool rounds,
  4 subagents, poll 0.5 s (`apps/api/src/lonora_api/env.py:95-98`); owner session
  86400 s (`apps/api/src/lonora_api/env.py:15`).
- The API creates one `OwnerServices` per owner lazily
  (`apps/api/src/lonora_api/runtime.py:20-41`) and on startup makes sure the owner's
  Personal Agent exists (`apps/api/src/lonora_api/app.py:86-95`).
- Health: `GET /health` checks the database only
  (`apps/api/src/lonora_api/health.py:12-19`); `GET /ready` is 503 unless a gateway
  heartbeat is fresh and no critical step is stalled
  (`apps/api/src/lonora_api/health.py:22-30`,
  `packages/gateway/src/lonora_gateway/health.py:20-42`). The production healthcheck
  uses `/health`, not `/ready` (`infra/compose/docker-compose.prod.yml:49`), so a dead
  gateway does not make the api container unhealthy.

Logging: only the gateway process calls `configure_logging`
(`apps/worker/src/lonora_worker/main.py:13`); the API entry point does not
(`apps/api/src/lonora_api/server.py:35-43`). The JSON formatter and redaction filter
(`packages/logging/src/lonora_logging/logger.py:7-12`) therefore apply to gateway logs
only. UNSURE: whether uvicorn's default logging in the API ever prints sensitive values.

---

## 2. The bus

There is no external broker. The bus is the PostgreSQL events table, polled.

- **Producers** call `emit`, which adds an `EventRow` inside the caller's transaction
  (`packages/db/src/lonora_db/events.py:104-122`). An event exists only if the business
  change committed.
- **Ordering**: `publish_committed` assigns a monotonic public cursor after commit,
  under an advisory lock, so a late commit cannot fall behind a reader's cursor
  (`packages/db/src/lonora_db/events.py:28-61`).
- **Consumers** poll `events_after(owner, cursor)`
  (`packages/db/src/lonora_db/events.py:76-88`). `stream_events` polls every 0.1 s for
  5 s after the last event, otherwise every 0.5 s
  (`packages/bus/src/lonora_bus/durable_events.py:10-27`).
- **Delivery guarantee**: at-least-once replay from a cursor the client holds. Events
  are durable rows; nothing is lost when a client or the API restarts.
- **In-process classes exist but are not the bus.** `RuntimeEvents` drops the oldest
  item when a 128-slot subscriber queue is full
  (`packages/bus/src/lonora_bus/runtime_events.py:14-25`) and `EventQueue` is a plain
  `asyncio.Queue` (`packages/bus/src/lonora_bus/queue.py:7-18`). A search for
  `RuntimeEvents()` and `EventQueue(` outside tests found no instantiation. UNSURE:
  whether a test-only or dynamic path uses them.
- `channel_projection` forwards only `message.created` with role `assistant`
  (`packages/bus/src/lonora_bus/outbound.py:4-10`).
- Attention text: `attention_text(code, locale)` falls back to the Arabic catalog for
  an unknown locale and to `internal_update` for an unknown code
  (`packages/bus/src/lonora_bus/attention.py:19-21`). The fallback text is «يوجد تحديث
  محفوظ في Lonora.» (`packages/bus/src/lonora_bus/attention_messages.json:8`). An
  unknown code is never shown raw on this path.

---

## 3. The gateway

`Gateway` (`packages/gateway/src/lonora_gateway/service.py:68-106`) owns one
`AgentRuntime` with the loaded tool registry and a `Watchdog`.

### 3.1 What it runs

- **Run workers**: `maximum_subagents + 1` shared workers plus one worker restricted to
  the `conversation` lane (`packages/gateway/src/lonora_gateway/service.py:290-301`).
  With defaults that is 5 shared and 1 conversation worker.
- **23 maintenance steps**, each its own supervised task with interval and timeout
  (`packages/gateway/src/lonora_gateway/service.py:40-65`): heartbeat, owners,
  routines, task_retries, activation_reviews, task_waits, outcomes, reconcile,
  verifications, account_recovery, goals, opportunities, market, history, charts,
  watches, voice, voice_notes, channels, attention, incoming, thread_prefs, watchdog.
- A worker claims one Run, builds the tool context and executes it
  (`packages/gateway/src/lonora_gateway/run_dispatch.py:49-93`).

Doc vs code: the step table in `docs/gateway-reliability.md:19-33` does not list
`voice_notes`; the code has it (`packages/gateway/src/lonora_gateway/service.py:59`).
The code wins.

### 3.2 Supervision, backoff, liveness

- A worker loop that raises is restarted after `min(30, 2**min(failures,5))` seconds
  and only the exception type is logged
  (`packages/gateway/src/lonora_gateway/supervisor.py:14-20`).
- A step iteration that raises or exceeds its timeout is counted as a failure
  (`step_timeout` or a stable code) and backs off up to 60 s
  (`packages/gateway/src/lonora_gateway/liveness.py:109-133`).
- A step is stalled after `max(120, interval*12, timeout+interval)` seconds without
  success (`packages/gateway/src/lonora_gateway/liveness.py:29-33`,
  `packages/gateway/src/lonora_gateway/liveness.py:48-54`). A worker running a Run is
  "busy", never stalled (`packages/gateway/src/lonora_gateway/service.py:108-112`).
- Heartbeat row with the liveness snapshot every 10 s
  (`packages/gateway/src/lonora_gateway/heartbeat.py:13-24`); fresh means younger than
  45 s (`packages/gateway/src/lonora_gateway/health.py:10`).
- Per-item isolation inside steps: 45 s item limit, quarantine after 5 failures,
  backoff 10 s doubling to 600 s
  (`packages/db/src/lonora_db/item_failures.py:26-32`).

### 3.3 Watchdog (no model)

`Watchdog.tick` runs five isolated checks
(`packages/gateway/src/lonora_gateway/watchdog.py:82-101`):

| Check | Raises | Citation |
| --- | --- | --- |
| stalled critical step | `gateway_degraded` (`reason_code: step_stalled`) once per episode | `packages/gateway/src/lonora_gateway/watchdog.py:122-142` |
| Run recovered too often | fails it `run_recovery_limit`, raises `run_quarantined`; held if a financial operation is unresolved (needed for safety) | `packages/gateway/src/lonora_gateway/watchdog.py:219-247` |
| routines or timer waits 5 min overdue | `gateway_degraded` (`wakes_overdue`) | `packages/gateway/src/lonora_gateway/watchdog.py:249-292` |
| operation uncertain for 15 min | `operation_unresolved`, never resent (needed for safety) | `packages/gateway/src/lonora_gateway/watchdog.py:294-336` |
| ended episodes | withdraws stale `gateway_degraded` items | `packages/gateway/src/lonora_gateway/watchdog.py:147-189` |

The watchdog lives inside the gateway. If the gateway process is down, nothing raises
an item: an owner message is accepted by the API and its Run stays `queued` (section
5). UNSURE: what the clients show for a Run that stays queued indefinitely; I found no
server-side timeout on a queued conversation Run.

### 3.4 Reconnection and replay (clients)

- SSE `GET /api/events/stream` sends a `ready` frame with the cursor, a keepalive
  every 10 s, and re-checks the session every 5 s; it ends the stream silently when the
  session is no longer valid
  (`apps/api/src/lonora_api/routes/events.py:47-98`). `Last-Event-ID` resumes from the
  larger of header and query cursor
  (`apps/api/src/lonora_api/routes/events.py:34-44`). A first live mount starts from
  the current cursor instead of replaying history
  (`apps/api/src/lonora_api/routes/events.py:108-111`).
- WebSocket `/api/ws/events` has the same contract: first frame carries token and
  cursor, `live` with cursor 0 jumps to the present, close code 1008 on auth failure
  (`apps/api/src/lonora_api/websocket/events.py:61-97`).
- Web client reconnects with backoff `min(10 s, 500 ms * 2**retry)` and forces a
  reconnect if no `ready` frame arrives in 10 s
  (`apps/web/src/lib/events.ts:47-57`). Mobile reconnects after 1.5 s
  (`apps/mobile/lib/events.ts:87-88`).

### 3.5 Drain

On stop the gateway marks itself draining, waits up to 25 s for tasks, cancels the
rest, returns its leases to the queue and closes connections
(`packages/gateway/src/lonora_gateway/service.py:311-325`,
`packages/gateway/src/lonora_gateway/shutdown.py:8-14`). Released Runs go back to
`queued` with the fence kept and `reason_code: gateway_drained`
(`packages/db/src/lonora_db/runs.py:490-526`). This matches
`docs/gateway-reliability.md:145-150`.

---

## 4. Sessions and threads

- **Owner session**: an opaque token stored as a SHA-256 hash with a CSRF hash and an
  expiry of `session_seconds` (`packages/auth/src/lonora_auth/sessions.py:18-28`);
  missing, revoked or expired gives `unauthorized` 401
  (`packages/auth/src/lonora_auth/sessions.py:31-40`). Cookie sessions need the CSRF
  header on mutating requests; bearer tokens do not
  (`apps/api/src/lonora_api/middleware/auth.py:16-27`).
- **Thread**: a conversation bound to one agent or to a group. `create_run` refuses a
  Run whose agent is not the thread's agent (`agent_thread_mismatch`) or not a group
  member (`packages/db/src/lonora_db/runs.py:121-128`).
- **Message order**: each thread has `next_seq`; a message takes it and increments it
  under the thread row lock (`packages/db/src/lonora_db/messages.py:211`,
  `packages/db/src/lonora_db/messages.py:397-425`).
- **Idempotency**: a message with a `client_nonce` already seen in the thread returns
  the stored message and its original run ids with `deduplicated: True`
  (`packages/db/src/lonora_db/messages.py:212-272`).
- **Run states**: `queued, leased, running, waiting_input, waiting_takeover, completed,
  failed, cancelled` (`packages/contracts/src/lonora_contracts/runs.py:11-20`);
  allowed transitions in `packages/core/src/lonora_core/run_state.py:8-25`.
- `packages/session` holds small helpers only: `continuation_state` lets
  `waiting_input`, `waiting_takeover` and `failed` Runs go back to `queued`, anything
  else is `run_cannot_resume`
  (`packages/session/src/lonora_session/continuation.py:4-7`).

---

## 5. Run leases

- **Claim**: `claim_next` takes a `queued` Run, or a `leased`/`running` Run whose lease
  expired and whose `recovery_count` is under 5
  (`packages/db/src/lonora_db/runs.py:194-202`,
  `packages/db/src/lonora_db/runs.py:21`). It sets status `leased`, the owner, a new
  fence (`lease_fence += 1`) and `lease_expires_at = now + lease_seconds`
  (`packages/db/src/lonora_db/runs.py:278-283`), and emits `run.recovered` or
  `run.leased` (`packages/db/src/lonora_db/runs.py:284-292`).
- **Duration**: 120 s by default, minimum 30
  (`apps/api/src/lonora_api/env.py:96`).
- **Renewal**: `keep_lease` renews every third of the lease length. A transient
  database error is retried until `lease_seconds - lease_seconds/6` have passed since
  the last success; then, or on any other error, the lease is declared lost and the
  Run task is cancelled
  (`packages/agent-runtime/src/lonora_agent/executor.py:44-73`,
  `packages/agent-runtime/src/lonora_agent/executor.py:106-109`).
- **Fencing**: every write goes through `require_lease`, which raises `stale_lease`
  (409) when status, owner, fence or expiry no longer match
  (`packages/db/src/lonora_db/runs.py:297-311`). `stale_lease` is never recorded as a
  failure and never shown to the model: the tool dispatcher re-raises it
  (`packages/agent-runtime/src/lonora_agent/tool_dispatch.py:111-112`) and the executor
  swallows it (`packages/agent-runtime/src/lonora_agent/executor.py:310-312`).
- **At expiry**: the Run becomes claimable again by any worker; the claim counts as a
  crash recovery (`packages/db/src/lonora_db/runs.py:266-269`). The new worker restores
  the checkpoint. A non-read-only call that was in flight and is not replay-safe is not
  re-run; the model gets `{"ok": False, "code": "tool_execution_uncertain"}`
  (`packages/agent-runtime/src/lonora_agent/tool_dispatch.py:82-95`). needed for
  safety: this is what stops a repeated broker send after a crash.
- **After 5 consecutive recoveries** `claim_next` stops re-leasing and the watchdog
  quarantines the Run with `run_recovery_limit`, unless an unresolved financial
  operation holds it (`packages/db/src/lonora_db/runs.py:529-577`).
- **Lease released, not expired**: waiting for input sets `lease_expires_at = None` and
  status `waiting_input`
  (`packages/agent-runtime/src/lonora_agent/executor.py:245-253`); a scheduled retry
  sets status `queued` with a `not_before` deadline the claimant respects
  (`packages/agent-runtime/src/lonora_agent/executor.py:261-266`,
  `packages/db/src/lonora_db/runs.py:205-206`).

---

## 6. Concurrency

| Level | Limit | Citation |
| --- | --- | --- |
| Per thread | One Run with a live lease at a time. A thread with an active Run is not claimable. | `packages/db/src/lonora_db/runs.py:234-253` |
| Per thread, claim race | Thread row locked `FOR UPDATE SKIP LOCKED` before the Run. | `packages/db/src/lonora_db/runs.py:246-253` |
| Per agent | No numeric limit. A paused agent's Runs are not claimed; creating a Run for a paused agent is `agent_paused` 409. | `packages/db/src/lonora_db/runs.py:241-245`, `packages/db/src/lonora_db/runs.py:134-135` |
| Global | Number of gateway workers: `maximum_subagents + 1` shared plus 1 conversation-only. | `packages/gateway/src/lonora_gateway/service.py:290-301` |
| Conversation lane | The dedicated worker takes only Runs whose trigger is not a work trigger, so background work cannot occupy every worker. | `packages/db/src/lonora_db/runs.py:224-228`, `packages/contracts/src/lonora_contracts/runs.py:7-9` |
| Subagents per parent Run | `maximum_subagents` active children, else `subagent_limit` 409. | `packages/agent-runtime/src/lonora_agent/collaboration/subagents.py:46-47` |
| Tool rounds per Run | 24 by default; Task Runs get up to 4 slices. | `apps/api/src/lonora_api/env.py:97`, `packages/agent-runtime/src/lonora_agent/continuation.py:20` |
| Agent owner cards | 5 pending agent-proposed cards per agent, else `owner_action_limit` 429. | `packages/db/src/lonora_db/owner_actions.py:1313-1314` |
| Agent notifications | 6 per agent per hour, else `owner_notify_rate_limited` 429. | `packages/db/src/lonora_db/attention.py:335`, `packages/db/src/lonora_db/attention.py:396-397` |

### A second owner message while a Run is active

`admit_runs` looks for the agent's earliest Run in the thread in `queued`, `leased`,
`running` or `waiting_input` (`packages/db/src/lonora_db/messages.py:516-525`).

- If that Run is conversational (or waits on a pending question) the message is
  **folded into it**, never a second Run:
  - Run `queued`: its `input_seq` moves to the new message and any retry deadline is
    cleared (`packages/db/src/lonora_db/messages.py:562-569`).
  - Run `leased`/`running`: a `SteeringRow` is added
    (`packages/db/src/lonora_db/messages.py:570-571`). The loop reads it at the next
    boundary; tool calls that had not started are closed as `tool_call_superseded` and
    the owner's new input buys a new round budget
    (`packages/agent-runtime/src/lonora_agent/tool_loop.py:353-361`,
    `packages/agent-runtime/src/lonora_agent/tool_loop.py:402-410`).
  - Run `waiting_input`: the pending question is marked answered and the Run goes back
    to `queued` (`packages/db/src/lonora_db/messages.py:537-553`,
    `packages/db/src/lonora_db/messages.py:572-573`).
- A Run cannot complete while an unconsumed steering row exists: `complete_run`
  returns False and the loop runs again
  (`packages/db/src/lonora_db/runs.py:364-370`).
- Otherwise (no active Run, or the active one is background work) a new `user` or
  `group` Run is queued (`packages/db/src/lonora_db/messages.py:575-593`); it waits for
  the thread's active Run because of the per-thread rule above.
- A new owner message withdraws an approved trade that was not sent yet:
  `tool_call_superseded` (`packages/tools/src/lonora_tools/trade.py:446-447`). needed
  for safety.
- A generated card's send always gets its own Run and starts only after every earlier
  Run of that agent in the thread has ended
  (`packages/db/src/lonora_db/runs.py:207-223`).

Nothing is rejected or lost in these paths; the owner is never told "busy".

---

## 7. Permissions and approvals

### 7.1 The three layers

1. **Tool scope of the Run** (`full`, `observe_only`, `helper`), from trigger and
   metadata (`packages/tools/src/lonora_tools/base.py:49-58`). Subagent Runs are
   `helper`; server-authored wakes marked `authority: observe_only` are `observe_only`.
   A financial tool is never permitted outside `full`
   (`packages/tools/src/lonora_tools/base.py:92-97`).
2. **Agent permission level** (the ladder): `analysis` "No trading", `supervised`
   "Ask me", `autonomous` "On its own" (`docs/unified-permissions-progress.md:9-13`).
   Default is `supervised` for the Personal Agent and root specialist agents, else
   `analysis` (`packages/db/src/lonora_db/agent_permissions.py:34-45`). `autonomous` is
   never stored: it is derived from a valid active signed AccountAuthority
   (`packages/db/src/lonora_db/agent_permissions.py:150-158`).
3. **Owner decisions**: trade approval cards and owner action cards, decided only
   through owner-session routes.

Exposure profiles (`core`, `market`, `research`, `coordination`, `task`) decide which
tool schemas a Run sees natively; they are "presentation only" and every registered
tool stays reachable through `tool_call`
(`packages/tools/src/lonora_tools/base.py:18-25`).

### 7.2 Who decides, and expiry

| Thing | Who decides | Lifetime | Citation |
| --- | --- | --- | --- |
| Permission level (analysis/supervised) | Owner, `PUT /agents/{id}/permissions`; a downgrade revokes pending and active grants | until changed | `apps/api/src/lonora_api/routes/agent_permissions.py:19`, `packages/db/src/lonora_db/agent_permissions.py:204-240` |
| Signed grant (autonomous) | Owner with a passkey (WebAuthn user verification); challenge valid 120 s | until revoked or `valid_until` | `packages/auth/src/lonora_auth/devices.py:99`, `docs/owner-actions.md:152-157` |
| Trade approval card | Owner, `POST /trading/approvals/{id}/decision` | 45 min default, clamped 30-60 min; expired cards are never approvable | `apps/api/src/lonora_api/routes/trading.py:228-244`, `packages/db/src/lonora_db/trade_approvals.py:19-21`, `packages/db/src/lonora_db/trade_approvals.py:135-138` |
| Owner action card | Owner, `POST /owner-actions/{id}/decision`; passkey when it widens what may be lost | Resume/limits/grant 24 h, resolve 7 d, lift 31 d | `apps/api/src/lonora_api/routes/owner_actions.py:177`, `packages/db/src/lonora_db/owner_actions.py:63-68`, `docs/owner-actions.md:142-150` |
| Question to the owner (`wait_for_input`) | Owner answers in chat | no expiry found; the Run stays `waiting_input` | `packages/agent-runtime/src/lonora_agent/executor.py:245-253` |

No tool reaches the decision routes (`docs/owner-actions.md:120-122`). needed for
safety.

Doc vs code: `docs/lonora-specs/DEVICE_AUTHORIZATION.md:3` describes a
`super_bot_propose` tool that creates the pending request. No tool with `super_bot` in
its name exists under `packages/tools/src` (search returned nothing), and
`docs/unified-permissions-progress.md:22` says Super Bot is retired. The code wins:
grants are proposed with `owner_action_propose(kind="grant_authority")`
(`docs/owner-actions.md:154-157`).

### 7.3 Which tool calls prompt the owner

- **`trade_execute` (and other financial handlers) at level `supervised`, or
  `autonomous` with no covering grant**: an approval card is created
  (`packages/tools/src/lonora_tools/trade.py:372-390`) and the tool returns
  `{"_runtime_wait": True, "_runtime_retry": True, "question": "", "approval_id": ...}`
  (`packages/tools/src/lonora_tools/trade.py:398-404`); the Run moves to
  `waiting_input`. "The ladder is monotonic: a trade no active grant covers asks the
  owner with an approval card ... instead of being refused"
  (`packages/tools/src/lonora_tools/trade.py:335-336`). needed for safety.
- **New risk when trading was never started**: no approval is asked; the owner gets a
  one-tap Start trading card and the tool returns `"code": "trading_not_started"` with
  `"recovery": "Say in one line that trading has not been started and that the owner's
  one tap on the card starts it; ask again after the tap."`
  (`packages/tools/src/lonora_tools/trade.py:226-238`). needed for safety. This is the
  one place I found where a refusal carries a sentence telling the model what to do.
- **`owner_action_propose`**: creates a card and "The tool result says the owner must
  tap and that nothing has changed yet" (`docs/owner-actions.md:41-48`).
- **`wait_for_input`**: a question card. Its description limits it to "a genuinely
  missing owner decision" and says "First recover previous answers and continue work
  already requested" (`packages/tools/src/lonora_tools/runtime_control.py:201`).
- Runtime-raised cards with no model involved: Lift card for a new restriction and a
  resolve card for an ambiguous operation
  (`packages/gateway/src/lonora_gateway/owner_cards.py:48-102`).

### 7.4 Which tool calls are denied silently, and the exact text the model sees

"Silently" here means: no card, no notification; the model alone gets the result and
must explain it. Unless a row says otherwise the model sees `{"ok": false, "code":
"<code>"}` plus the `recovery` object from `classify`; there is no sentence. A refusal
raised inside the executor during a send is instead returned as a trade result with
`status: "failed"` and the same bare code
(`packages/tools/src/lonora_tools/trade.py:464-467`).

| Situation | Code the model sees | `recovery` | Citation | Label |
| --- | --- | --- | --- | --- |
| Unknown tool name | `tool_not_allowed` | `permission_denied` / `respect_scope` | `packages/tools/src/lonora_tools/registry.py:478-480`, `packages/agent-runtime/src/lonora_agent/environment.py:56-69` | LEAK |
| Tool not permitted in this Run's scope | `tool_not_allowed` | same | `packages/tools/src/lonora_tools/registry.py:483-484` | LEAK |
| Financial tool from a helper or observe-only Run | `observe_only_execution_forbidden` | default `terminal_domain_failure` / `alternate_route` | `packages/tools/src/lonora_tools/registry.py:481-482`, `packages/tools/src/lonora_tools/registry.py:489-490`, `packages/agent-runtime/src/lonora_agent/environment.py:36-37` | needed for safety. Note the default action `alternate_route` is the wrong hint for a safety refusal. |
| Financial tool at level `analysis` | `agent_analysis_only` | default `terminal_domain_failure` / `alternate_route` | `packages/tools/src/lonora_tools/trade.py:316-317`, `packages/trading/src/lonora_trading/agent_permission.py:34-35` | needed for safety. The system frame does tell the model to "propose a grant_authority card" (`packages/agent-runtime/src/lonora_agent/context/permissions.py:128-129`). |
| Send without a matching approval | `trade_approval_required` | default | `packages/trading/src/lonora_trading/agent_permission.py:62` | needed for safety |
| Shadow-mode Run tries to trade | `shadow_execution_forbidden` | default | `packages/tools/src/lonora_tools/trade.py:310-311` | needed for safety |
| Approval expired / rejected | `trade_approval_expired`, `trade_approval_rejected` (as result fields, status `expired`/`rejected`) | `rejected` counts as a failure and gets the default `recovery`; `expired` does not (`packages/agent-runtime/src/lonora_agent/environment.py:164-166`) | `packages/tools/src/lonora_tools/trade.py:397-406` | needed for safety |
| Bridge call names an unknown tool | `tool_call_target_unknown` | `not_found` / `inspect_existing_state` (suffix rule) | `packages/tools/src/lonora_tools/registry.py:222`, `packages/agent-runtime/src/lonora_agent/environment.py:80-81` | LEAK |
| Bad arguments | `tool_arguments_invalid` with `issues` and `retryable: True` | `invalid_tool_arguments` / `inspect_schema_and_repair` | `packages/agent-runtime/src/lonora_agent/tool_dispatch.py:114-116`, `packages/agent-runtime/src/lonora_agent/environment.py:38-39` | fine: the model can repair |
| Any `*_not_found` (symbol, account, artifact...) | the code | `not_found` / `inspect_existing_state` | `packages/agent-runtime/src/lonora_agent/environment.py:80-81` | LEAK, STOP: the owner's example |
| Read timed out / connection failed | `tool_read_timeout`, `tool_connection_failure` | `temporary_unavailable`, `safe_to_retry: true` | `packages/agent-runtime/src/lonora_agent/tool_dispatch.py:118-128`, `packages/agent-runtime/src/lonora_agent/environment.py:44-45` | handled: auto-retry (below) |
| Mutation timed out or raised an unknown exception | `tool_execution_uncertain` | `ambiguous_mutation` / `reconcile_before_any_resend` | `packages/agent-runtime/src/lonora_agent/tool_dispatch.py:118-138`, `packages/agent-runtime/src/lonora_agent/environment.py:42-43` | needed for safety |
| Read raised an unknown exception | `tool_internal_failure` | default `terminal_domain_failure` / `alternate_route` | `packages/agent-runtime/src/lonora_agent/tool_dispatch.py:129-138` | LEAK |
| Same call failed 3 times | `tool_route_exhausted`, not executed | `alternate_route_or_wait` | `packages/agent-runtime/src/lonora_agent/tool_dispatch.py:70-81` | STOP |
| Loop guardrail block | `guardrail_blocked`, `executed: False`, with a message such as "{tool} was not executed: the identical read already returned the same result {count} times. Use that result or change the request." | none | `packages/agent-runtime/src/lonora_agent/tool_guardrails.py:302-310`, `packages/agent-runtime/src/lonora_agent/tool_guardrails.py:94-97` | fine: a sentence is given |
| Owner card cap reached | `owner_action_limit` | default | `packages/db/src/lonora_db/owner_actions.py:1313-1314` | LEAK |
| Notification rate limit | `owner_notify_rate_limited` | default | `packages/db/src/lonora_db/attention.py:396-397` | LEAK |

How the transcript form is built: the result dict is serialized with `json.dumps` and
given to the model as is when it is at most 120000 characters
(`packages/agent-runtime/src/lonora_agent/tool_block.py:252-256`).

Automatic read retry: when `recovery.safe_to_retry` is true the Run is checkpointed and
re-queued with a deadline of `2**attempt` seconds
(`packages/agent-runtime/src/lonora_agent/tool_block.py:309-328`,
`packages/agent-runtime/src/lonora_agent/environment.py:219-224`); only read-only tools
with a code in `TRANSIENT_READ_CODES` qualify
(`packages/agent-runtime/src/lonora_agent/environment.py:92`,
`packages/core/src/lonora_core/runtime_failure.py:10-21`), and after 3 failures it is
switched off (`packages/agent-runtime/src/lonora_agent/environment.py:206-209`).
`symbol_not_found` is not in that set, correctly; but there is no equivalent
"next safe read" step for it.

The permission frame the model reads every turn ends with: "Keep implementation details
private and explain only practical results or the specific help needed from the owner."
(`packages/agent-runtime/src/lonora_agent/context/permissions.py:183-184`). That
instruction exists only inside the financial-permission frame; the tool-failure path
gives the model nothing but implementation details (codes) to explain.

---

## 8. Secrets

- **Storage**: `SecretRow.ciphertext`, encrypted with Fernet using
  `LONORA_ENCRYPTION_KEY` (`packages/security/src/lonora_security/secrets.py:23-31`,
  `packages/adapters/src/lonora_adapters/storage/secret_store.py:10-12`). Reads are
  scoped to the owner, else `secret_not_found`
  (`packages/adapters/src/lonora_adapters/storage/secret_store.py:14-19`). A wrong key
  gives `secret_decryption_failed` 500
  (`packages/security/src/lonora_security/secrets.py:33-37`).
- **What the API lists**: id, name and updated time only, never a value
  (`packages/db/src/lonora_db/secrets.py:7-13`).
- **Redaction function**: `redact` replaces the value of any dict key matching
  `password|secret|token|api.?key|authorization|ciphertext` with `[redacted]` and masks
  `Bearer <token>` in strings (`packages/security/src/lonora_security/secrets.py:7-20`).
- **Where it is applied**:
  - gateway log messages (`packages/logging/src/lonora_logging/sinks.py:14`,
    `packages/logging/src/lonora_logging/redaction.py:7-12`);
  - progress events (`packages/agent-runtime/src/lonora_agent/progress.py:17`);
  - tool results **only when stored because they exceed 120000 characters**
    (`packages/tools/src/lonora_tools/tool_results.py:35`,
    `packages/tools/src/lonora_tools/tool_results.py:46`).
- **Where it is not applied**: an ordinary tool result goes to the model through plain
  `json.dumps(result)` (`packages/agent-runtime/src/lonora_agent/tool_block.py:254-256`).
  Keeping secrets out of normal tool results depends on each handler never returning
  one. UNSURE: I did not audit every handler for this.
- **Logs**: failures log a code or the exception type, not the message: worker loops
  (`packages/gateway/src/lonora_gateway/supervisor.py:16-18`), tool failures
  ("Exception content may contain credentials; only the type belongs in diagnostics",
  `packages/agent-runtime/src/lonora_agent/tool_dispatch.py:130-132`), Run failures
  (`packages/agent-runtime/src/lonora_agent/executor.py:314`).
- **API errors** return `{"code", "request_id"}` only
  (`apps/api/src/lonora_api/errors.py:27-32`).
- Channel secrets: the Telegram bot token and webhook signing secret are read from the
  secret store per delivery
  (`packages/gateway/src/lonora_gateway/event_dispatch.py:69`). The Telegram token is
  part of the request URL
  (`packages/adapters/src/lonora_adapters/channels/telegram.py:14`); `httpx` logging is
  set to WARNING in the gateway (`packages/logging/src/lonora_logging/logger.py:12`).

---

## 9. Channels

Three manifests are registered: telegram, websocket, webhook
(`packages/channels/src/lonora_channels/registry.py:7-8`).

| Channel | Inbound (owner → agent) | Outbound (agent → owner) | Proactive reach |
| --- | --- | --- | --- |
| Web app | `POST /api/threads/{id}/messages` (`apps/api/src/lonora_api/routes/messages.py:92-101`) | SSE event stream (`apps/api/src/lonora_api/routes/events.py:101-116`) | Only while the app is open. Attention items appear in-app. |
| Mobile app | same API with bearer token | WebSocket/SSE events | Only while the app is open. No push library is declared in `apps/mobile/package.json` (search for `expo-notifications`, `firebase`, `notifee` returned nothing). |
| Telegram | Polled every 2 s by the `channels` step; text messages from an allowed chat id are admitted as owner messages into the configured thread (`packages/gateway/src/lonora_gateway/event_dispatch.py:70-91`) | Every assistant `message.created` in scope, plus `attention.ready` items of importance `critical` or `action_required`, as fixed catalog text (`packages/gateway/src/lonora_gateway/event_dispatch.py:103-151`) | **Yes**, the only off-app path, and only if the owner configured an enabled integration with a secret (`packages/gateway/src/lonora_gateway/event_dispatch.py:62-67`). |
| Webhook (out) | none | Same events POSTed as `{"content": ...}` with an HMAC signature to a public URL (`packages/adapters/src/lonora_adapters/channels/webhook.py:15-27`) | Yes, to a machine endpoint, not a person. |
| Webhook (in) | `POST /api/webhook` with `X-Lonora-Signature` starts a Run (`apps/api/src/lonora_api/routes/webhook.py:16-34`); needs `LONORA_WEBHOOK_SECRET`, else `webhook_not_configured` 409 | none | n/a |
| Incoming call | n/a | A call request row is stored, but the gateway passes no delivery provider (`packages/gateway/src/lonora_gateway/service.py:253`), so nothing is sent (`packages/voice/src/lonora_voice/incoming.py:353-354`) | **No** in this build. The tool text says "a persisted request is not proof the device rang" (`packages/tools/src/lonora_tools/incoming_call.py:142`). |

Delivery details:

- Each delivery has a receipt key, so an event is sent to a destination once
  (`packages/gateway/src/lonora_gateway/event_dispatch.py:162-166`). A delivery that
  raises is recorded `ambiguous` / `channel_delivery_unconfirmed` and **not retried**
  (`packages/gateway/src/lonora_gateway/event_dispatch.py:180-185`). A Telegram outage
  at that moment loses that message on Telegram (it remains in the app).
- `gateway_degraded` and `maintenance_item_quarantined` have importance
  `important_change` (`packages/db/src/lonora_db/attention.py:34-39`), so they are not
  mirrored to Telegram; `run_quarantined` and `operation_unresolved` are
  `action_required` and are.
- Agent-initiated `owner_notify`: under reach-me "activity only" a non-critical alert
  raises no item (`activity_only`); quiet hours hold everything but critical items
  (`packages/db/src/lonora_db/attention.py:356-362`,
  `packages/db/src/lonora_db/attention.py:425`).

---

## 10. Every harness-level failure the owner can see, with the text

### 10.1 In the conversation (written by the runtime, not the model)

| Trigger | Text shown | Citation |
| --- | --- | --- |
| Run hit the tool-round limit or a guardrail halt, and the final model call returned nothing | «توقفت قبل إنهاء العمل لأن هذه الجولة بلغت حدّها، ولم يُنفَّذ أي إجراء بعد ذلك. اطلب مني المتابعة عندما تريد الاستئناف.» | `packages/agent-runtime/src/lonora_agent/runtime_notices.py:132-139`, used at `packages/agent-runtime/src/lonora_agent/tool_loop.py:284` |
| Task stopped at the work limit | «توقفت هذه المهمة قبل اكتمالها لأن هذه الجولة بلغت حدّ العمل، ولم يُنفَّذ أي إجراء بعد ذلك.» | `packages/agent-runtime/src/lonora_agent/runtime_notices.py:153-157` |
| Task has unfinished steps | «هذه المهمة لم تكتمل بعد.» | `packages/agent-runtime/src/lonora_agent/runtime_notices.py:143-146` |
| Continuous task saved no wait | «هذه المهمة المستمرة غير مراقَبة: لم يُحفظ أي انتظار مراقبة أو مؤقت مراجعة، لذلك لن تحدث أي متابعة تلقائية.» | `packages/agent-runtime/src/lonora_agent/runtime_notices.py:147-152` |

In the normal case at a limit the model writes the final reply itself, under the
instruction "report only results verified by tool observations in this run ... and give
the concrete next steps" (`packages/agent-runtime/src/lonora_agent/runtime_notices.py:117-129`);
the Run completes with `reply_outcome: "limited"`
(`packages/agent-runtime/src/lonora_agent/tool_loop.py:314-322`). STOP: an ordinary
conversation Run gets one slice of 24 rounds and then asks the owner to say "continue".

### 10.2 Failed-Run error card (web, `apps/web/src/conversation/Cards.tsx:69-83`)

A Run fails with `error.code` for any `LonoraError` other than `stale_lease`, and with
`runtime_error` for any other exception
(`packages/agent-runtime/src/lonora_agent/executor.py:310-315`). The family is derived
in `packages/core/src/lonora_core/runtime_failure.py:39-52`.

| Family | Title (Arabic) | Body | Buttons |
| --- | --- | --- | --- |
| quota | «نفدت حصة مزوّد النموذج» (`apps/web/src/i18n/locales/ar/messages.po:7359-7360`) | "The model provider refused the request for quota on its account. Add credit with the provider, choose another model, or retry once it resets." | View usage, Retry |
| rate | «طلبات كثيرة في وقت قصير» (`apps/web/src/i18n/locales/ar/messages.po:7826-7827`) | "Many requests were sent within a minute. Wait a little, then try again." | Retry |
| timeout | «انتهت مهلة الرد» (`apps/web/src/i18n/locales/ar/messages.po:7412-7413`) | «لم يصل الرد في الوقت المحدد، وقد يكون الاتصال ضعيفًا.» (`apps/web/src/i18n/locales/ar/messages.po:7408-7409`) | Retry |
| model | «النموذج غير متاح حاليًا» (`apps/web/src/i18n/locales/ar/messages.po:7331-7332`) | «تعذّر الوصول إلى مزوّد النموذج. جرّب نموذجًا آخر أو أعد المحاولة بعد قليل.» (`apps/web/src/i18n/locales/ar/messages.po:7335-7336`) | Change the model, Retry |
| other | «تعذّر على الوكيل الرد» (`apps/web/src/i18n/locales/ar/messages.po:7099-7100`) | `userError(code)`; unknown codes fall to «تعذر إكمال الطلب. أعد المحاولة.» (`apps/web/src/i18n/locales/ar/messages.po:7416-7417`) | **none** (`apps/web/src/conversation/Cards.tsx:96`) |

Codes that land in `other` include `runtime_error`, `run_recovery_limit`,
`illegal_run_transition` and `input_question_identity_conflict`
(`packages/agent-runtime/src/lonora_agent/executor.py:174`). Known mapped texts in the
same switch: `stale_lease` → «انقطعت هذه الخطوة ثم استُؤنفت. لم يتكرر أي شيء.»
(`apps/web/src/lib/user_error.ts:210-211`,
`apps/web/src/i18n/locales/ar/messages.po:7731-7732`); `tool_round_limit` → "I paused at
this run's step budget. Send a message and I continue from here."
(`apps/web/src/lib/user_error.ts:225-226`).

Server retry rule: only a failed `user`/`group` Run with no parent, no task, no
financial effect and no descendants can be retried, else `run_not_retryable`
(`packages/db/src/lonora_db/run_retry.py:91-103`). needed for safety ("a retry can
never repeat a trade", `packages/db/src/lonora_db/run_retry.py:5-6`). The server would
allow a retry for an `other` failure that meets those rules; the web card just does not
offer it. UNSURE: the mobile error card was not read.

Provider failures before the card: a conversation Run retries the model turn with
backoff 10 s base, 60 s cap, and fails after 3 consecutive transient failures; work
Runs 30 s / 900 s / 6 (`packages/agent-runtime/src/lonora_agent/model_recovery.py:59-63`).
During backoff the partial reply preview is withdrawn and `run.retry_scheduled` is
emitted (`packages/agent-runtime/src/lonora_agent/executor.py:268-304`).

### 10.3 Attention items (in-app; Telegram for the action-required ones)

| Code | Arabic text | Citation |
| --- | --- | --- |
| `gateway_degraded` | «خدمة الخلفية في لونورا متأخرة. ستستمر في المحاولة وتبلغك عند الحاجة.» | `packages/bus/src/lonora_bus/attention_messages.json:15` |
| `run_quarantined` | «توقف عمل بعد انقطاعات متكررة. افتح المحادثة لمراجعته.» | `packages/bus/src/lonora_bus/attention_messages.json:13` |
| `maintenance_item_quarantined` | «أوقفت لونورا عنصرًا في الخلفية بعد أخطاء متكررة. يستمر كل ما عداه في العمل.» | `packages/bus/src/lonora_bus/attention_messages.json:12` |
| `operation_unresolved` | «صفقة ما زالت بلا نتيجة مؤكدة من الوسيط. لن يُعاد إرسالها؛ افتح المحادثة لمراجعتها.» (needed for safety) | `packages/bus/src/lonora_bus/attention_messages.json:14` |
| `task_review` | «تحتاج المهمة إلى مراجعتك. افتح المحادثة لفحص سبب التوقف وخيارات الاستكمال.» | `packages/bus/src/lonora_bus/attention_messages.json:7` |
| `approval_required` | «يوجد طلب يحتاج موافقتك. افتح المحادثة لمراجعة التفاصيل؛ لم تنفذ هذه الرسالة أي إجراء.» (needed for safety) | `packages/bus/src/lonora_bus/attention_messages.json:5` |
| unknown code | «يوجد تحديث محفوظ في Lonora.» | `packages/bus/src/lonora_bus/attention_messages.json:8` |

`run_quarantined` tells the owner to "open the conversation to review it"; what he
finds there is the `other` error card from 10.2 with no button.

### 10.4 API refusals the owner can hit directly

All are returned as `{"code": ...}` (`apps/api/src/lonora_api/errors.py:27-32`) and
rendered by the client's `userError`; an unmapped code shows «تعذر إكمال الطلب. أعد
المحاولة.» (`apps/web/src/lib/user_error.ts:227-228`).

| Code | When | Citation |
| --- | --- | --- |
| `unauthorized` 401 | session missing, expired (24 h default) or revoked | `packages/auth/src/lonora_auth/sessions.py:32-36` |
| `csrf_required` 403 | cookie request without the CSRF header | `packages/auth/src/lonora_auth/sessions.py:49-56` |
| `rate_limited` 429 | more than 10 sign-in or enrollment POSTs per minute per host | `apps/api/src/lonora_api/middleware/rate_limit.py:39-40` |
| `database_unavailable` 503 | health check | `apps/api/src/lonora_api/health.py:17-18` |
| `agent_paused` 409 | Run created or question answered for a paused agent | `packages/db/src/lonora_db/runs.py:134-135`, `packages/db/src/lonora_db/messages.py:302-303` |
| `input_answer_expired` 409 | answering a question the Run no longer waits on | `packages/db/src/lonora_db/messages.py:294-300` |
| `run_not_active` 409 | steering a Run that already ended | `apps/api/src/lonora_api/routes/steering.py:24-25` |
| `run_not_retryable` 409, `run_retry_too_early` 409 | retry rules | `packages/db/src/lonora_db/run_retry.py:98`, `packages/db/src/lonora_db/run_retry.py:29-34` |
| `run_cannot_resume` 409 | resume of a Run not waiting or failed | `packages/session/src/lonora_session/continuation.py:5-6` |
| `trade_approval_expired`, `trade_approval_already_decided`, `trade_approval_run_unavailable` 409 | approval decisions (needed for safety) | `packages/db/src/lonora_db/trade_approvals.py:136-147` |
| `owner_action_passkey_required` 403 | a card that widens risk decided without a passkey (needed for safety) | `apps/api/src/lonora_api/routes/owner_actions.py:407` |
| `message_not_editable`, `message_already_edited` 409 | edit-and-resend rules | `packages/db/src/lonora_db/messages.py:657-659` |

The sign-in mapping reuses `unauthorized` for the text "Sign-in failed. Check your
email and password." (`apps/web/src/lib/user_error.ts:84-85`). An expired session on
any other request has the same code. UNSURE: whether the clients intercept 401 before
this text is shown.

### 10.5 Failures the owner does not see at all

- Gateway process down: messages are accepted (202) and Runs stay queued; the
  watchdog that would raise `gateway_degraded` runs inside the same dead process
  (section 3.3).
- Telegram delivery that raised: recorded `channel_delivery_unconfirmed`, not retried
  (`packages/gateway/src/lonora_gateway/event_dispatch.py:180-181`).
- A channel integration that fails with a `LonoraError` only stores the code in its
  own state (`packages/gateway/src/lonora_gateway/event_dispatch.py:186-190`).
- `owner_notify` under "activity only" returns `activity_only` to the model and raises
  no item (`packages/db/src/lonora_db/attention.py:461-465`).

---

## 11. Mechanisms that produce "stops, refuses, leaks a code, or asks": summary

| # | Mechanism | Effect | Citation | Must stay? |
| --- | --- | --- | --- | --- |
| 1 | Tool errors are a bare `code`; `LonoraError` has no owner-safe or model-facing message | LEAK | `packages/agent-runtime/src/lonora_agent/tool_dispatch.py:113`, `packages/core/src/lonora_core/user_error.py:1-14` | No |
| 2 | `classify` gives only a generic category; `*_not_found` → `inspect_existing_state`, no named next read tool, no candidates | STOP | `packages/agent-runtime/src/lonora_agent/environment.py:35-93` | No |
| 3 | MetaApi 404 on non-candle stages is always `broker_account_not_found` | LEAK, wrong diagnosis | `packages/adapters/src/lonora_adapters/brokers/metaapi.py:57-58` | No |
| 4 | Symbol match is exact or case-only | STOP | `packages/tools/src/lonora_tools/symbols.py:6-15` | Exact match must stay for sends (`require_exact_symbol`, `packages/security/src/lonora_security/financial.py:10`); reads could offer candidates |
| 5 | Three failures of one call block the route for the Run | STOP | `packages/agent-runtime/src/lonora_agent/environment.py:127-131` | Partly (prevents loops) |
| 6 | Empty turn notice tells the model it may ask with `wait_for_input` | ASK | `packages/agent-runtime/src/lonora_agent/runtime_notices.py:96-99` | No |
| 7 | `wait_for_input` is always in the native tool set | ASK | `packages/tools/src/lonora_tools/runtime_control.py:199-205` | Needed for real owner decisions |
| 8 | 24-round budget for a conversation Run, then a "limited" reply asking the owner to continue | STOP | `apps/api/src/lonora_api/env.py:97`, `packages/agent-runtime/src/lonora_agent/tool_loop.py:399-438` | A bound must stay; the wording and auto-continue are open |
| 9 | Error card for family `other` has no action | STOP | `apps/web/src/conversation/Cards.tsx:96` | No |
| 10 | No off-app delivery for agent notifications or calls | cannot follow up | `packages/db/src/lonora_db/attention.py:341`, `packages/gateway/src/lonora_gateway/service.py:253` | No |
| 11 | Default `recovery` for unclassified refusals is `alternate_route`, also for safety refusals such as `agent_analysis_only` and `observe_only_execution_forbidden` | wrong hint | `packages/agent-runtime/src/lonora_agent/environment.py:36-37` | The refusals stay (needed for safety); the hint should say "respect scope" |
| 12 | Approval card wait (`_runtime_wait`) | ASK | `packages/tools/src/lonora_tools/trade.py:398-404` | Yes: needed for safety |
| 13 | `tool_execution_uncertain` after a crash or timeout of a mutation | STOP | `packages/agent-runtime/src/lonora_agent/tool_dispatch.py:82-95` | Yes: needed for safety |
| 14 | Retry refused for a Run with any financial effect or descendants | STOP | `packages/db/src/lonora_db/run_retry.py:91-103` | Yes: needed for safety |

### Notes for whoever proposes fixes (constraints, not designs)

- Anything that helps the model after `symbol_not_found` must be a read: listing the
  account's symbols is read-only and touches no money rule. The exact-symbol check at
  the executor (`packages/security/src/lonora_security/financial.py:9-10`) must not be
  loosened.
- A model-facing hint attached to a tool error is English skill/prompt text; the
  owner-facing sentence the agent then writes must be in the owner's language and must
  not contain the code.
- The one existing precedent for a sentence-level recovery hint on a refusal is
  `trading_not_started` (`packages/tools/src/lonora_tools/trade.py:236-237`).
