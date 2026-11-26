# OpenMausBot: the framework (processes, persistence, run lifecycle)

Audience: Lonora developers. Source: a read-only clone of `milind-soni/OpenMausBot`. All paths are repo-relative. Everything below was read in the code unless marked "not read" or "not found".

## 0. One-paragraph summary

OpenMausBot is not a queue-and-worker system. It is **one long-lived Node/TypeScript server process per "home"** (a laptop, a VPS, a Docker container, or a managed cloud machine). That process owns all state on local disk (`DATA_DIR`, default `~/.openmausbot`), serves HTTP plus one SSE stream to the UI, and starts **one child process per agent engine** (Claude Code CLI, Codex, ACP agents) or calls an HTTP chat API directly. There is no external database server, no Redis, no message broker. "Workers" are engine child processes. Concurrency safety comes from a single process owning the data directory (a lease file), plus SQLite transactions for the job record. Proactivity comes from in-process timers (routines, check-backs, waits, webhooks) that start ordinary turns. The edge (relay, control plane, connector) exists only to reach the home from a phone/browser and to manage cloud machines; it never holds chats.

## 1. Processes and component diagram

```
                       Cloudflare (edge, optional)
        +----------------------------------------------------------+
        | control-plane Worker (D1: accounts, installs, tunnels,   |
        |   push devices)  cloudflare/control-plane/src/index.ts   |
        | relay (Node + ws)  relay/src/server.ts: /v1/host,        |
        |   /v1/host/data, /v1/phone  (splices sealed bytes)       |
        +-----------^----------------------^-----------------------+
                    | tunnel / relay       | WebSocket (Noise-sealed)
                    |                      |
 Browser / Desktop  |   Phone app          |        customer-run VPS
 (React, src/)      |                      |        connector/ (Docker mgmt agent)
   | HTTP + SSE     |                      |              |
   v                v                      v              v
+-----------------------------------------------------------------------+
| HOME SERVER  = ONE Node process  (server/openmausbot.ts -> cli.ts ->   |
|                server/index.ts, ~15k lines, composition root)          |
|                                                                        |
|  HTTP handler (handleRequest) --- routes/ + host/ factories            |
|  SSE /api/events  (broadcast(), replayBuffer, Last-Event-ID)           |
|  Webhook ingress (webhook-ingress.ts, own port/socket)                 |
|                                                                        |
|  Store (store.ts)   bots.json / groups.json  (whole-file atomic)       |
|  message-db.ts      messages.db   (SQLite, WAL)                        |
|  runtime/ + runtime-coordinator.ts   runtime.db (SQLite, WAL)          |
|  harness/bus.ts     events/<thread>.ndjson (append-only event log)     |
|  routines.ts, check-backs, waits, webhooks  (JSON files + timers)      |
|  usage-ledger.ts, decision-log.ts, usage-trace/  (append-only logs)    |
|  turn-watchdog.ts, crash-guard.ts, graceful-shutdown.ts                |
|                                                                        |
|  harness/registry.ts -> ProviderAdapter instances (drivers/)           |
+--------+----------------------+-----------------------+----------------+
         | stdio (stream-json)  | ACP over stdio        | HTTPS
         v                      v                       v
   claude CLI process     codex / ACP agent        OpenAI-compatible APIs
   (1 per thread, warm)   processes                (drivers/openai-*, chat-*)
         |  MCP over loopback HTTP, bearer = per-turn capability
         +--> /api/internal/*  (agents tools, computer, browser, data, ...)
```

Other processes in the repo:

| Process | Defined in | Role |
|---|---|---|
| Home server | `server/openmausbot.ts` -> `server/cli.ts` `main()` -> `server/index.ts` | Everything stateful. `cli.ts` is also a launcher that restarts it (section 8). |
| Desktop app (Electron) | `electron/boot.mjs`, `electron/main.mjs` (main.mjs not read), `electron-builder.yml` | Windows, browser pane, native IPC, runs or connects to a server. Shares the lease code (`electron/data-dir-lease.mjs`). |
| React UI | `src/main.tsx`, `src/state/`, `src/hooks/` | Talks to the server over HTTP and SSE only. |
| Companion sidecar | `companion/README.md`, `companion/src/` | Separate process in front of the loopback-only harness; allowlist plus device token for phones on LAN/tailnet. |
| Relay | `relay/src/main.ts`, `relay/src/server.ts`, `relay/src/hosts.ts`, `relay/src/splice.ts` | Stateless-ish WebSocket splice between a home and a phone, with per-IP and per-host limits. Cannot read payloads. |
| Control plane | `cloudflare/control-plane/src/index.ts`, `wrangler.jsonc`, `migrations/*.sql` | Cloudflare Worker + D1: email-OTP accounts, installation credentials, managed Cloudflare Tunnels, relay tokens, push. Holds no bots or chats (its README says so). |
| Composio broker | `cloudflare/composio-broker/` | Not read. |
| Connector | `connector/src/adopted-home.ts`, `connector/src/docker.ts` | Agent on a customer's VPS that starts/stops the Docker Compose home, backups, updates. |
| Engines | `server/drivers/**`, `server/harness/registry.ts` | Child processes or HTTP clients, one adapter per instance. |
| Reverse proxy | `compose.yaml`, `deploy/local/Caddyfile`, `deploy/fly/` | Caddy terminates TLS and forwards over a Unix socket (`OMB_TUNNEL_SOCKET`). |

There is no separate worker pool, scheduler daemon or queue service. The "scheduler" is timers inside the server process (section 5).

## 2. How processes communicate

| Path | Mechanism | Where |
|---|---|---|
| UI to server | HTTP JSON; one `GET /api/events` Server-Sent Events stream | `server/index.ts` (`handleRequest`, `broadcast()` near line 4667, `/api/events` near 14478) |
| SSE resume | Every frame has `id: <STREAM_ID>:<seq>`; reconnect sends `Last-Event-ID`; `replayBuffer.covers(since,lastSeq)` decides replay or a fresh snapshot | `server/index.ts` |
| Server to engine | stdio (Claude: stream-json both ways; ACP: JSON-RPC) or HTTPS | `server/drivers/claude.ts` header comment, `server/drivers/acp/**` |
| Engine to server (tools) | MCP over loopback HTTP, authenticated by an opaque per-turn bearer | `server/index.ts` `mintInternalCapability`, `/api/internal/*` branch near line 12715; `server/drivers/agents-mcp-env.ts` |
| Adapter to everything else | In-process event bus: `ProviderAdapter.onEvent` -> `EventBus.publish` -> listeners | `server/harness/bus.ts`, `server/contracts.ts` |
| Bot to bot, same server | Not messages: rows in `runtime.db` (`assignments`) driven by `Runtime.tick()` | `server/runtime/runtime.ts`, `server/runtime-coordinator.ts` |
| Bot to bot, across servers | `bot-link`: a computer dials its Cloud; hand-offs and results travel as frames keyed by assignment id; bots addressed as `link-<peer>-<id>` | `server/bot-link/link.ts`, `server/bot-link/protocol.ts` |
| Phone to home | WebSocket to the relay, Noise-sealed, yamux streams carrying HTTP/1.1; or a Cloudflare Tunnel; or LAN/Tailscale | `relay/src/server.ts`, `docs/phone-relay-server.md`, `server/cli.ts` |
| Webhooks in | Separate small HTTP server (port `OMB_WEBHOOK_PORT`, or Unix socket), 256 KB body cap | `server/webhook-ingress.ts`, `server/webhooks.ts` |
| Home to control plane | HTTPS (installation credential `omb_install_...`) | `cloudflare/control-plane/README.md` |

WebSocket upgrade handling also exists on the main server (`upgrades.attach(server, handleRequest)` in `server/index.ts`); I did not read what it carries (the browser/computer viewers appear to use it).

## 3. Persistence

All of it lives under `DATA_DIR` (`server/config.ts`: `export const DATA_DIR = defaultDataDir();`, with `OMB_DATA_DIR` override set by `cli.ts`). Files are 0600, directory 0700.

| Store | Format | What | Durability rule | File |
|---|---|---|---|---|
| `bots.json`, `groups.json` | JSON, rewritten whole | Bots, rooms, threads, tasks, engine session ids | `now` / `pass` / `later` durability classes; temp file + fsync + rename | `server/registry-store.ts`, `server/atomic.ts`, `server/save-batch.ts`, `server/registry-save.ts` |
| `messages.db` | SQLite, WAL, `synchronous=NORMAL` | Tables `messages`, `thread_state`, `chat_followups`, `command_receipts`, `notification_log` | Per statement | `server/message-db.ts` |
| `runtime.db` | SQLite, WAL | Tables `assignments` (one JSON row per job), `assignment_events` (append-only audit), `inbox` (wake lane) | Every state change in one `BEGIN IMMEDIATE` transaction with its event | `server/runtime/store.ts` |
| `events/<threadId>.ndjson` | Append-only NDJSON | Canonical runtime event log per thread, secrets redacted | Queued, batched (64 lines), flushed at turn end and shutdown; capped (`capThreadLog`) | `server/harness/bus.ts` |
| `usage/` | Append-only rows + `usage/spans/<day>.jsonl` | One row per booked turn; spans per AI step and tool call | Fire-and-forget; "never fails the turn" | `server/usage-ledger.ts`, `server/usage-trace/spans.ts` |
| `decisions/YYYY-MM.ndjson` | Append-only | Why a tool call was allowed, denied or carded | Fire-and-forget, redacted, retention-pruned | `server/decision-log.ts` |
| Routines, check-backs, waits, webhooks | JSON files (`routines.json`, `check-backs.json`, ...) + a JSONL occurrence ledger | Scheduled work and its history | Atomic rewrite; ledger appended per change so "a start is on disk before its turn begins" | `server/routines.ts`, `server/routine-ledger.ts`, `server/host/check-backs.ts`, `server/waits.ts`, `server/webhooks.ts` |
| `config.json` | JSON | Settings, engine instances, caps, feature switches; env vars override credentials | Read through `settledFileCache` | `server/config.ts` (`loadConfig`) |
| Sessions | JSON file, sha256 of tokens only | Pairing codes, sessions, stream tickets | Atomic write; flushed at shutdown | `server/sessions.ts` |
| Engine homes | Per-engine dirs (`~/.claude`, `~/.codex`) | Engine logins and native session transcripts | Owned by the engine CLIs; in Docker `HOME=/data` | `Dockerfile` comment, `server/engine-homes/` |

Key design facts:
- **Two generations coexist.** The older state (bots, rooms, threads) is whole-file JSON; `server/registry-store.ts` says "A layout that keeps threads as rows can write one row where this one writes a whole file". The newer state (messages, jobs) is SQLite. `scripts/bench-persistence.ts` and `server/registry-save.ts` (`DEFERRABLE_FIELDS`) exist to manage the cost of whole-file saves.
- **Write batching.** `batchSaves()` in `server/save-batch.ts` coalesces whole-file saves requested during one synchronous pass (one event delivery, one turn start) into one write.
- **Row memo.** `server/runtime/store.ts` memoizes parsed assignment JSON keyed by the text itself, capped by count and characters.
- No tenant column anywhere in these stores (section 10).

## 4. The run lifecycle

There are two layers: a **thread turn** (one engine invocation) and an **assignment** (the durable job record). Every turn is now an assignment root (`docs/runtime-contract.md` section 10, PR 4 and 5).

### 4.1 Assignment states

Defined in `server/runtime/types.ts`:

```ts
export type Status =
  | "queued"  | "running" | "needs_input" | "waiting" | "resume"
  | "completed" | "failed" | "cancelled";
export const TERMINAL: readonly Status[] = ["completed", "failed", "cancelled"];
```

`failed` carries an `outcome` (for example `interrupted`, `expired`, `stalled`, `refused`) and `outcomeDetail`. State diagram from `docs/runtime-contract.md` section 2:

```
queued -> running -> completed | failed | cancelled
             |  \-- handed out work --> waiting --children settled--> resume --> running
             \-- question for the person --> needs_input --answer--> running
```

### 4.2 Control flow of a person's message (numbered)

1. UI posts a message. A route (`server/routes/bot-messages.ts`) calls `startOrQueueDirectMessage()` (`server/index.ts` ~line 7049).
2. Pure admission: `admit("direct", {}, { atCapacity, threadBusy, groupTurn, parksBehindCoordination })` in `server/admission.ts` returns `start`, `queue` (with reason `capacity` or `group-turn`), `steer` or `refuse`. The function states "Purity is the contract: no IO". Surfaces: `direct-busy`, `direct`, `room`, `room-steer`, `guarded`, `unattended`, `peer`, `opened-thread`, `incident`.
3. If queued, `queueSteeredMessage()` writes a `chat_followups` row in `messages.db`; `drainQueuedSends()` empties it when a slot frees (also at boot).
4. If started, `startTurn()` -> `beginTurn()` (`server/index.ts` ~7398, wrapped in `batchSaves`). Before dispatch it checks spend caps (`assertWithinBudget`, `usageCapGate.assertTurn`, see 9.2).
5. `beginTurn` registers the root with the runtime: `coordinator.beginTurn({ id: dispatchClaimId, address: { botId, threadId }, brief, ... })` (~7637). The root is created already `running` (`Runtime.begin`, `server/runtime/runtime.ts`).
6. The server mints a per-turn bearer (`mintInternalCapability`), builds the engine's MCP env (`server/agents-turn.ts` `agentsServerEnv`), and calls `instance.adapter.sendTurn(...)` (~8300), wrapped by `quickFallback`, `guardTurnDispatch`, and `withTurnScope` (`server/crash-guard.ts`).
7. The driver emits `RuntimeEvent`s (`turn.started`, `content.delta`, `item.*`, `turn.completed`, `runtime.error`). `EventBus.attach` stamps each with `providerInstanceId` and drops cross-driver events (`server/harness/bus.ts`).
8. `EventBus.publish` merges text deltas (50 ms window), enqueues a redacted line for `events/<thread>.ndjson`, then `deliver()` runs every subscriber inside `batchSaves`. Subscribers update the store, usage, traces, `LiveTurns` (`server/live-turns.ts`), the watchdog, and `broadcast()` to SSE clients.
9. The engine calls tools back through `/api/internal/...`. The handler checks the bearer, that the bearer's `kind` matches the route (`agents`, `computer`, `browser`, `data`, `email`, `hooks`, ...), that claimed `botId`/`fromThreadId` match the bearer, and that the turn is still active (`internalCapabilityIsActive`) before any side effect.
10. If the turn calls `coordinate_bots`, the coordinator creates child assignments (`Runtime.enqueue`), the root goes `waiting`, and `Runtime.tick()` later admits children, collects results, and flips the parent to `resume` (section 4.3).
11. `turn.completed` ends the root (`Runtime.end`), writes the usage row (`appendUsage` ~line 1347), books the trace, settles follow-ups, drains the queue.
12. On failure the error is classified (`server/drivers/engine-errors.ts`, `server/drivers/retry.ts`, `server/turn-continuation.ts`); recoverable cases continue or retry (4.4).

### 4.3 The runtime tick (queued -> running -> waiting -> resume)

- `server/runtime-coordinator.ts` constructs `Runtime` over `openRuntimeStore(join(dataDir, "runtime.db"))`.
- `server/handoff-ticks.ts` is the clock. Pace-driven, not a fixed poll:

```ts
export const HANDOFF_TICK_MS: Record<HandoffPace, number> =
  { busy: 250, parked: 10_000, idle: 60 * 60_000 };
```

`Runtime.pace()` returns `busy` while anything is queued, running, resumable or has a report to send; `parked` when it only waits on a person, a teammate or a time limit. `kick()` forces an immediate tick after a write that may have made work due. The server calls `coordinator.tick()` from that clock (`server/index.ts` ~9395, wrapped in try/catch), and also prunes finished trees daily (30 days, `PRUNE_AFTER_MS`).
- `Runtime.tick()` (`runtime.ts` ~286) runs inside `withBatch`, deepest node first, and: expires queued work (`queueMs`), applies input-wait limits, re-validates access, admits queued nodes through the host's `canStart`, dispatches resumes, and sends reports. It never throws into a turn (invariant I10).
- Limits (`server/runtime-coordinator.ts`): depth 4, 64 requests and 96 executions per root since last progress, 72 h wait on a person (`PARKED_LIMIT_MS`), `TURN_STALL_MS = 24 h` (deliberately out of the way; the legacy watchdog owns per-turn stalls).
- Level (approval mode) is `max(own, inherited)` over `ask < edits < auto < full` (`server/runtime/level.ts`), recorded on the row at enqueue and capped by engine capabilities (`server/runtime/capabilities.ts`).
- Dedupe: same brief + assignee + parent returns the existing row (`duplicate: true`) unless `rework`.
- Invariants asserted by the test suite: `server/runtime/invariants.ts` (I1..I10, for example "No non-terminal assignment without a live owner", "No result is delivered twice").

### 4.4 Stalls and recovery inside a running server

- `server/turn-watchdog.ts` + `watchdog = new TurnWatchdog({...})` (`server/index.ts` ~4930): sweeps every 60 s. Defaults: 20 min of silence (`OMB_TURN_STALL_MS`), 2 h if a tool is running (`OMB_TOOL_STALL_MS`), parked turns (waiting on a person or computer) are not stalled unless the engine process is known gone, 2 min after the engine process exits. A shell command whose process tree keeps using CPU counts as activity (`engineCommandCpuMs`). On stall: revoke bearers, `interruptTurn`, append a failed-notice activity, report an incident, free the thread.
- Routine failures: `server/routine-recovery.ts` decides retry once, wait for a usage limit reset, or fail at once for owner-fixable causes (signed out, credits).
- Continuations: a turn that stops short ends `continue` and is re-queued; two continuations without a successful tool call, or three identical errors, end `failed(stalled)` (`docs/runtime-contract.md` section 6).
- `server/limit-failover.ts`, `server/quota-switch.ts`, `server/quick-model-fallback.ts`: model/engine fallback on limits (names from the map; not read in detail).

## 5. Always-on and proactive behavior

There is no "agent loop that wakes itself". Proactivity is a set of **durable, timer-driven triggers that each start an ordinary turn**. The turn itself is bounded and ends; the trigger record is what persists.

| Trigger | Persistence | Clock | Key files |
|---|---|---|---|
| Routines (cron, interval, once, limit-reset) | `routines.json` + occurrence ledger (`queued/running/ran/failed/missed/skipped`) | `startDueTimer` (`server/due-timer.ts`): `next()` returns the earliest due time, `poke()` after changes, wall-clock re-check on one shared interval (explicitly because timers stop on macOS sleep) | `server/routines.ts` (`tick`, ~1015), `server/routine-due.ts`, `server/routine-ledger.ts` |
| Checks before the model | Cursor and seen-ids stored on the routine | Run by the routine tick; "Nothing new starts no turn and leaves no run" | `server/host/proactive.ts`, `server/host/routine-checks.ts` (not read), `docs/proactive-routines.md` |
| Check-backs (bot returns to a chat at a time it chose) | `check-backs.json`; start saved before the turn is requested, so a record found mid-start after a restart is closed, never started twice | `DueTimer` | `server/host/check-backs.ts` |
| Waits (`wait_until`: time, URL text, file change, process) | `waits.json`; limits 10 per bot, 50 total | 5 s tick, URL probe every 60 s with backoff to 15 min | `server/waits.ts`, `server/wait-probes.ts` |
| Person waits (turn ended on an open card) | Derived from card rows | Event-driven | `server/host/person-waits.ts` |
| Webhooks | `webhooks.json` with sealed secrets, delivery receipts (idempotency) | HTTP ingress | `server/webhooks.ts`, `server/webhook-ingress.ts` |
| Brief ("Keep an eye on my day") | One ordinary routine, owner chosen by `proactiveOwner` | Routine | `server/host/proactive.ts`, `server/host/brief.ts`, `server/host/proactive-owner.ts` |

Properties worth noting:
- **Missed occurrences are accounted for.** `server/routine-catch-up.ts`: the newest missed occurrence runs late if within `CATCH_UP_MS = 12 h`; older ones collapse into one "missed" row that counts them and says why (computer off, cloud down, scheduler late). Late starts are staggered (15 s apart, up to 40 steps).
- **Unattended runs are fenced.** The proactive fence (`proactive.fence.refusesRoute`, `server/read-and-draft.ts`) refuses write routes with `READ_AND_DRAFT_REFUSAL` during a proactive run: "reads and drafts only".
- **Run limits.** Default 3 h per routine run, 12 h per goal run (`server/routine-run-limits.ts`, env `OMB_ROUTINE_RUN_LIMIT_HOURS`).
- **Sleep awareness.** `server/routine-due.ts` computes `wakeHoldOf` (keep a desktop awake for due work) and `nextDueOf` (when a sleeping Cloud home should wake); Cloud power in `server/cloud-power.ts` (not read).
- **Startup storms are throttled.** A headless server runs startup routines at most once per `OMB_STARTUP_ROUTINE_GAP_MS` (30 min) and staggers restart reruns 30 s apart (`server/routine-restarts.ts`).

## 6. Crash, restart and recovery

1. **Launcher policy** (`server/restart.ts`): exit code 75 = "restart me" (at most 5 in a row); exit code 70 = crash, restart after backoff `[1, 2, 5, 15, 30] s`, then stop; a run that lives 60 s resets the counters. SIGKILL/SIGABRT/SIGSEGV and 134..139 count as crashes. `server/cli.ts` applies this in `serve`/`start`; `OMB_` docs: `docs/self-hosting.md`; services via `server/service-cli.ts`, `server/service-unit.ts`.
2. **Crash guard** (`server/crash-guard.ts`): unhandled rejection = log and stop only the turn it belonged to (found via `AsyncLocalStorage` `runInTurn`); driver exceptions inside a turn scope stop that turn; socket EPIPE/ECONNRESET are survivable; anything else, or more than a storm limit of errors, marks running turns cut, flushes nothing held in memory, and exits with code 70.
3. **Graceful shutdown** (`server/graceful-shutdown.ts`): SIGINT/SIGTERM run all cleanup jobs concurrently under an 8 s deadline (`SHUTDOWN_DEADLINE_MS`, chosen to sit above engine kill timing in `server/engine-stop.ts` and below Docker's 10 s). Order in `server/index.ts`: stop coordinator, revoke all turn bearers, stop timers, close engines, flush usage/decision/profile/memory ledgers, flush the event bus (1 s), close sessions, close `messages.db`, mark the engine run clean, release the data-dir lease, exit.
4. **Boot reconciliation of the job record** (`Runtime.open()`, `server/runtime/runtime.ts` ~109; table in `docs/runtime-contract.md` section 5). Deepest node first, from stored data only:

| State at crash | Result |
|---|---|
| `queued`, `waiting`, `resume` | Unchanged; dispatches normally |
| `needs_input` | Stays parked; `park` re-run, but cards/chips/notifications already posted are not re-posted |
| `running`, children started | `waiting`, marked `restart: "cut"`; nothing of it reruns |
| `running`, no children, host reports an outward action done (sent, pushed, paid) | `failed(interrupted)`, never rerun, "so nothing is done twice" |
| `running`, no children, nothing outward | One rerun (`restart: "rerun"`, `restarts: 1`); cut a second time -> `failed(interrupted)` |

The outward-action knowledge is read through the host port `outward(a)` from the thread's own activity rows, "never from model text".
5. **Boot reconciliation of chat sends** (`server/index.ts` before `server.listen`): `chat_followups` rows in `dispatching`/`interrupted` are settled `interrupted`, the user's words are re-attached as a message with a review notice, and "never to a model a second time".
6. **Interrupted turns get a visible line.** `noteTurnsCutByShutdown()` appends `chat.notice.restartInterrupted` to threads that were busy and not held by the runtime.
7. **Routines after a restart**: ledger rows `restarted`, `turn-gone`; runs cut by a restart start again one after another (`restartRetryAt`); another machine's lease on the same data is respected (`OccurrenceLease`).
8. **Webhooks and check-backs** each have a restart e2e test (`server/webhook-restart.e2e.test.ts`) and idempotency receipts (`server/webhook-idempotency.test.ts`).
9. **Memory pressure** (`server/engine-memory.ts`, `server/machine-pressure.ts`): on a Cloud home or self-hosted Linux box a turn that needs a new engine waits for memory or pids headroom rather than letting the kernel kill engines; a routine run cut for want of memory fails with a stated cause (`restartCut`).

What it does not do: there is no replay from the event log (the NDJSON log is for history and bug reports, not recovery), and `parkedSeats` is memory-only (`docs/runtime-contract.md` section 10, item 6).

## 7. Concurrency and locking

- **One process per data directory.** `server/data-dir-lease.ts` re-exports `electron/data-dir-lease.mjs`: a lease file `openmausbot-server.lease` created with `linkSync` (atomic), holding pid, boot id (`/proc/sys/kernel/random/boot_id`), machine id. Boot id and uptime may "only prove a lease dead, never alive". A delegated child lease is passed by env var for Electron's utility server. `releaseDataDirLeaseAtExit()` runs on every exit path.
- **Single-threaded event loop = the lock.** State machines in memory (`Map`s of live turns, `groupSpeakers`, `directRequestOwners`) are mutated synchronously; `batchSaves` makes a pass atomic with respect to disk writes.
- **SQLite transactions.** `server/runtime/store.ts` `transaction()`: `BEGIN IMMEDIATE`, nested calls become `SAVEPOINT`s.
- **Per-thread serialization.** "Same-conversation turns never overlap" (`docs/runtime-contract.md`); `server/admission.ts` plus `sendSequencer.run(key, fingerprint, fn)` for idempotent sends keyed by `sendId`.
- **Capacity.** `botAtThreadCapacity`, room "speaker" rules, one-answer-to-the-same-request join (`server/same-request.ts`, not read).
- **Admission gates for a running server:** `guarded` surface refuses rather than queues; `unattended` surface refuses on busy ("busy means a missed run").
- **Cross-machine.** Routine occurrence leases (`OccurrenceLease { machine, boot, until }`) and `cloud-send-lease.ts` (name only) for a Cloud shared with a computer.
- **Not found:** no distributed lock, no database-level row lease for jobs, no multi-writer SQLite. The design assumes exactly one writer process.

## 8. Configuration

- Layers: built-in defaults < `config.json` in `DATA_DIR` (zod-parsed by `parseStoredConfig`; a bad file is ignored with a one-time warning, never quoting its content) < environment variables for every credential (`loadConfig` in `server/config.ts`; "Env wins over the file for every credential").
- Naming: `OMB_*` (for example `OMB_DATA_DIR`, `OMB_PORT`, `OMB_TURN_STALL_MS`, `OMB_USAGE_CAP_DAILY_USD`, `OMB_PUBLIC_URL`, `OMB_TUNNEL_SOCKET`, `OMB_PHONE_RELAY`, `OMB_LICENSE_KEY`, `OMB_ENTERPRISE_DIR`). Numeric env parsing is defensive (`stallLimitMs`, `envWhole`): "Number() also reads 'Infinity' ... and an endless limit would switch the watchdog off".
- Feature switches: `features` object in `config.json` (`docs/feature-flags.md`). Instances (engines) under `instances` (`docs/custom-engines.md`).
- Model catalog: bundled manifest + models.dev snapshot (`server/model-catalog/`, `server/model-manifest/`, `scripts/build-model-catalog.mjs`).
- Edition: `server/enterprise.ts` loads `enterprise/server/index.ts` only if present.

## 9. Observability, usage and cost

### 9.1 Logs and traces
- `console.*` to stdout/stderr (the launcher/service captures it). Prefixes like `runtime:`, `coordinator:`, `bus:`.
- Canonical per-thread event log: `events/<thread>.ndjson` (`server/harness/bus.ts`), secrets scrubbed by `redactSecrets`. If the disk write fails or the queue overflows (4096 events / 32 MB) a `runtime.error` "Canonical event history is incomplete" event is delivered live.
- Per-turn trace: `server/usage-trace/recorder.ts` builds steps and tool spans from runtime events; `spans.ts` writes `usage/spans/<day>.jsonl` with names, times, token counts, one clipped redacted detail, "never arguments, outputs, prompts or replies".
- Audit: `decisions/YYYY-MM.ndjson` (`server/decision-log.ts`), kinds `auto-approved`, `auto-denied`, `card-shown`, `user-approved`, `user-denied`, ...
- Runtime audit: `assignment_events` table (every transition; invariant I7 says a row can be rebuilt from its events).
- Health: `GET /api/health` (compose healthcheck in `compose.yaml`); `server/sentinel/` is an opt-in out-of-process scanner of the data dir (`docs/sentinel.md`); loop-stall and memory-stall sampling in `server/perf/` and `server/machine-pressure.ts`.
- Product analytics: opt-in PostHog from the web client only (`docs/analytics.md`).

### 9.2 Usage and cost accounting
- `server/usage-ledger.ts`: append-only rows under `<data>/usage/`, one per turn, with `botId`, `threadId`, `driverKind`, `model`, token counts, a `UsageTrigger` (`user`, `owner`, `routine`, `bot`, `helper`), price via `server/prices.ts` / `server/model-prices.ts` with a `CostSource`. Rows "never carry message text".
- Attribution to a person: `server/usage-attribution.ts` (cost of a delegated turn goes to the person whose turn caused it).
- Caps: `server/usage-caps.ts`: day and month, USD and tokens, per server and per bot, `OMB_USAGE_CAP_*` env, warn at 80 percent, `OMB_USAGE_CAP_STOPS` = `unattended` or `everything`. Enforced before dispatch (`usageCapGate.assertTurn`), and by the licensed budget in `server/spend.ts`.
- Plan-limit awareness for subscription engines: `server/plan-usage.ts`, `server/drivers/claude-limits.ts`, `shared/limit-reset.ts` (a routine type `limit_reset` runs when a limit resets).

## 10. Multi-user and tenancy

- **Default is single-owner.** One data dir = one person's home. Access: loopback requests (Host and Origin both loopback) are the owner; remote devices pair with a 60-bit single-use code (10 min TTL) and get a session (256-bit token, only sha256 stored) with scope `admin` or `client` (`server/sessions.ts`, `server/request-auth.ts`). A shared server can switch loopback to "service trust" so bot shells that are loopback callers are not owners.
- **Team Cloud** (`docs/team-cloud.md`): one server, several people; roles Owner/Admin/Member; `teamOwners`, `personRooms`, per-person read marks (`room-reads.json`), per-person streams (`streamFor(client, person)` in SSE delivery). "New conversation is yours alone". Tenancy is enforced **in application code at read/stream time**, not by a tenant id in the schema. I found no row-level isolation.
- **Bot box** (`server/bot-box/`, `docs/bot-box.md`): Linux sandbox for bot shells (seccomp, egress gate, hidepid, broker for credentials) so a bot with a shell cannot read other people's data.
- **Edge accounts**: control plane (Better Auth email OTP in D1) identifies the owner of installations; it does not hold chats.
- **Per-turn authority**: the bearer carries `{botId, threadId, generation, depth, kind, ...}`; the harness checks it on every call and refuses disagreeing ids. `externalRuntimeMayCall` limits external runtimes to listing peers, `coordinate_bots`, `assignment_status`.

## 11. Deployment and self-hosting

- Four ways to run: desktop app; `npx openmausbot serve ...` (Node 24+); Docker Compose (`compose.yaml`: `omb` + `caddy`, volume `/data`, `init: true`, healthcheck on `/api/health`); managed Cloud home (`Dockerfile --target cloud-home`, `deploy/fly/fly.toml`). Podman: `deploy/podman/`.
- Reach options (`docs/self-hosting.md`): `--public-url`, `--domain` (managed Caddy, `server/caddy.ts`), `--tailscale`, `--lan`, `--tunnel` (Cloudflare Tunnel from the control plane), `--relay` (phones only). The server always binds `127.0.0.1`; "the loopback-trust invariant is the auth model" (`Dockerfile` header).
- Updates: `deploy/update.sh`, `deploy/update-runner.sh`, the server's own updater, and the connector hands updates to the server's updater (`connector/src/adopted-home.ts`). CI: `.github/workflows/*.yml`.
- Packaging: `scripts/bundle-server.mjs`, `scripts/build-npm-package.mjs`, `electron-builder.yml`.
- Idle housekeeping on Cloud: `server/host/idle-reclaim.ts` (`docs/idle-reclaim.md`), off by default (`OMB_IDLE_RECLAIM`).

## 12. Extension points

| Extension | How | Files |
|---|---|---|
| Engines | `ProviderDriver` / `ProviderAdapter` with a `capabilities` object; registry builds instances from `config.json` `instances`; zero-code `customAcp` (spawn any ACP CLI) and OpenAI-compatible endpoints | `server/contracts.ts`, `server/harness/registry.ts`, `docs/custom-engines.md`, `server/drivers/**` |
| Tools for the agent | One MCP "agents" server; catalog with profiles; `find_tool`/`use_tool` bridge keeps listed tools small ("a bridged call is never judged more permissively than the same call made directly") | `server/drivers/agents-catalog.ts`, `server/drivers/agents-bridge.ts`, `docs/agents-tool-bridge.md` |
| Person's own MCP servers | Paste a URL, `claude mcp add` line or JSON; connected and tested on add | `server/mcp-bot-servers.ts`, `server/mcp-registry.ts`, `docs/custom-mcp-servers.md` |
| Connected apps | Composio broker/relay | `server/composio-session.ts`, `server/connected-reads.ts`, `docs/composio.md` |
| Skills | `SKILL.md` import and library | `server/skill*.ts`, `shared/skill-md.ts`, `skills/` |
| Webhooks and routines as triggers | Section 5 | |
| Bot API | HTTP API for external runtimes (`reply: poll`) | `docs/bot-api.md`, `server/routes/bot-messages.ts` |
| Enterprise layer | Optional folder loaded by `server/enterprise.ts`; Ed25519-signed `OMB_LICENSE_KEY`, offline verification | `enterprise/server/index.ts`, `enterprise/server/license.ts` |
| Hooks | Engine hook helper registered with the engine (`capabilities.hooks`) -> `/api/internal/hook` | `server/drivers/claude-hooks.ts`, `server/index.ts` |

There is no in-process plugin loader for third-party server code outside the enterprise layer; extension is by configuration (engines, MCP servers, skills) rather than loading code.

## 13. Not found / what the code does not do

- No external queue, worker fleet or distributed scheduler. Not found: Postgres, Redis, Kafka.
- No automatic multi-instance high availability; one writer per data dir by design.
- No distributed tracing (OpenTelemetry) in what I read; traces are local JSONL.
- No row-level tenant isolation; no per-tenant database.
- The agent does not run its own unbounded loop; "continuous work" is bounded continuations (guards at 2 no-progress or 3 identical errors) plus timers.
- Not read in detail: `electron/main.mjs`, `cloudflare/composio-broker/`, `server/cloud-power.ts`, `server/same-request.ts`, the WebSocket upgrade handlers, most of `server/routes/`, `server/host/routine-checks.ts`.
- `server/index.ts` is a 15k-line composition root; `server/host/README.md` documents the ongoing split and a line-count ratchet. Expect to read it in pieces.

## 14. What Lonora should copy / avoid

Lonora context: always-on trading assistant for MT5, FastAPI server + worker, React web, Expo mobile, lead agent "Lonora" plus owner-created agents.

### Copy

1. **A single durable job record with an append-only event table and a pure state machine** (`server/runtime/types.ts`, `store.ts`, `runtime.ts`). Lonora already has migrations and a worker; model "agent work" as `assignments` + `assignment_events` + `inbox` in Postgres (or SQLite for a dev lane), written in one transaction per transition, with the invariants (I1..I10) as tests.
2. **Restart policy that refuses to repeat outward actions.** Rule: a cut turn reruns once, unless it already sent/posted/paid, then it fails `interrupted`. For Lonora this maps directly to broker orders: never re-run a turn that submitted an order; reconcile the order instead. Read "outward" from the activity/journal rows, never from model text.
3. **Pure admission function** (`server/admission.ts`) with named surfaces (`direct`, `unattended`, `guarded`, `peer`). Unattended work refuses on busy rather than queues; user messages queue and can steer a live turn.
4. **Pace-driven tick** (`HANDOFF_TICK_MS`: 250 ms busy, 10 s parked, 1 h idle) plus `kick()` instead of a fixed poll. Cheap when idle, fast when busy.
5. **Triggers are records, turns are bounded.** Routines, check-backs, waits, webhooks each persist a trigger and start a normal turn; "a check-back starts at most once: the start is saved before the turn is asked for". Add the occurrence ledger (`queued/running/ran/failed/missed/skipped` with reasons) and the catch-up rule (run the newest missed one if within a window, collapse the rest into one counted "missed" row). This is the core of an honest always-on agent.
6. **Checks before the model.** Plain code reads calendar/mail/market and starts no turn when nothing is new. For Lonora: price/news/position/margin checks run as code; wake an agent only on a condition.
7. **Per-turn capability bearer** checked on every tool call (kind must match route, claimed ids must match, turn must still be active, revoked at turn end and on stall). Use this between the agent runtime and the trading tools so one agent cannot impersonate another or outlive its turn.
8. **Hand-offs as assignments with a single envelope written by the harness**, not model text (`server/runtime/envelope.ts`): who asked, authority (on behalf of the owner at level X vs outside content), and a rule that the requester's wake carries every settled child at once. This is the right shape for "Lonora the lead delegates to the owner's agents".
9. **One level rule** `max(own, inherited)` capped by capability, recorded on the row. Matches Lonora's Ask/Full mandate: compute the authority at enqueue, store it, assert the turn ran with it.
10. **Watchdog with context.** Silence limit, longer limit while a tool runs, no stall while waiting on a person, CPU-aware for long commands. Adapt: a long MT5 call or backtest is activity if the worker heartbeats.
11. **Append-only, redacted, fire-and-forget logs** for usage, decisions and spans, with rows that never carry message text; plus hard caps (`usage-caps.ts`) enforced before dispatch with an `unattended` vs `everything` stop mode. A budget cap that stops only unattended work first is a good default for a trading assistant.
12. **Crash discipline:** typed exit codes (75 restart, 70 crash) and a backoff table in the launcher; crash guard that attributes an uncaught error to a turn via `AsyncLocalStorage`; 8 s graceful shutdown ordered below the container's stop timeout.
13. **Edge stays dumb.** Relay splices sealed bytes and has per-host and per-IP limits; control plane holds identity and tunnels only. For Lonora, keep the FastAPI server authoritative and let the phone reach it over an authenticated channel without the edge reading data.

### Avoid

1. **A 15k-line composition root** (`server/index.ts`) and whole-file JSON registries (`bots.json`, `groups.json`) that need `batchSaves`, durability classes and ratchet tests to stay tolerable. Lonora should keep agents, threads and tasks as database rows from day one.
2. **Tenancy enforced only in read paths.** For multi-owner Lonora put the owner id in every table and every query; do not rely on stream-time filtering.
3. **Single-writer-by-lease as the only safety.** Fine for a home server; Lonora's server and worker are separate processes, so use database locks/leases (`SELECT ... FOR UPDATE SKIP LOCKED` or a lease column with expiry and fencing token) and idempotency keys for broker calls.
4. **Idle-heavy timers per feature** (routines, check-backs, waits, due-timer, upkeep each with their own timer and file). Prefer one scheduler table and one due-time query so recovery and visibility are uniform.
5. **Reimplementing engine CLI orchestration.** OpenMausBot's complexity (warm processes, resume cursors, per-driver quirks) comes from wrapping external CLIs. Lonora calls model APIs directly; take the event vocabulary (`turn.started`, `content.delta`, `item.*`, `turn.completed`, `runtime.error`) and the bus, not the process management.
6. **Counting on model text for safety facts** anywhere. They avoid it (outward actions, envelope, levels); do the same for orders, balances and approvals.
7. **Docs and tests that read source text** to enforce structure (their host README admits it). Use real unit tests on extracted modules.
