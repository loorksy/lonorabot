# Lonora local runtime for Android integration tests

A real Lonora backend (stock FastAPI API, real resident Gateway and agent loop, PostgreSQL 16)
running in the disposable dev container, with model replies produced by the repository's own
explicit scripted model fixture. No model provider, broker or production host is contacted, and
no financial operation is involved. Verified on 2026-11-27.

Runtime directory (outside the checkout, private to this session):

```
RT=/tmp/claude-0/-home-user-lonorabot/c777793c-4d08-5fcf-a248-25819dbbff0b/scratchpad/lonora-runtime
```

Credentials (server URL, owner email and password, bearer token; local and disposable) are in
`$RT/creds.json` only. This document holds no secret.

## Status

| Component | How it runs | Address | Status |
|---|---|---|---|
| PostgreSQL 16 | `/usr/lib/postgresql/16/bin`, data in `$RT/pg/data` | 127.0.0.1:55432, db `lonora_android_test` | running |
| Migrations | `bash scripts/migrate.sh` (alembic) | head `0201_reply_language_tag` | applied |
| API | stock `.venv/bin/lonora-api --host 127.0.0.1 --port 8840` | http://127.0.0.1:8840 | running, `/health` and `/ready` 200 |
| Gateway (worker) | `$RT/scripted_gateway.py`: stock `lonora_worker.main` with the scripted model | (no port) | running, heartbeat ready |
| Owner | created once through `POST /api/onboarding` with the bootstrap token | | `android-dev@example.com` (password in creds.json) |
| Web UI | not built (`pnpm build` not run; the API serves `/api` without it) | | not needed for Android |
| Docker | client installed, daemon not running | | not used |

## How the repository tests without provider keys

- CI (`.github/workflows/ci.yml`, `scripts/gate.sh`) runs a `postgres:16-alpine` service, creates a
  fresh database per step named `lonora_gate_<run>_<step>_test`, migrates it, and exports CI-only
  dummy values (`LONORA_ENCRYPTION_KEY`, `LONORA_BOOTSTRAP_TOKEN`, `LONORA_COOKIE_SECURE=false`,
  `LONORA_AUTH_RATE_LIMIT_PER_MINUTE=10000`). Every integration check (`tests/check_*.py`,
  `playwright.config.mjs`) refuses a database whose name does not end in `_test`, `_verify` or `_ci`.
- There is **no environment variable or production switch** for a fake model.
  `packages/adapters/src/lonora_adapters/models/fake.py::ScriptedModelAdapter` is documented as
  "explicit test fixture; never part of the production provider registry". Tests inject it:
  - `tests/check_durable_runtime.py` sets `services.router.factory = scripted(fixture)` on the
    owner's `OwnerServices`, stores a dummy `openai` key, routes to a fixture model name, then calls
    the real `lonora_gateway.run_dispatch.dispatch_one`: the real agent loop answers with the
    scripted reply.
  - `tests/check_streaming.py` uses a `ScriptedRouter` in-process, and its `browser` mode
    (`echo '{"action": ...}' | .venv/bin/python tests/check_streaming.py browser`) writes leased
    runs, `run.reply_started` / `run.delta` progress and the final message straight into the
    database. The Playwright web and mobile suites run the stock API on 8830/8831 **without a
    Gateway** and drive replies through this fixture.

This runtime reuses both, without changing the agent engine (mechanisms A and B below).

## Recipe

One-time preparation (already done here; `start.sh` repeats the parts that are missing):

```sh
cd /home/user/lonorabot
uv venv --python /usr/bin/python3.12 .venv            # gitignored, as scripts/install.sh
uv pip install --python .venv/bin/python -e '.[dev]'
```

`$RT/lonora.env` (mode 600) holds the generated local values: PostgreSQL user/password/port/db,
`LONORA_DATABASE_URL`, `LONORA_ENCRYPTION_KEY` (Fernet), `LONORA_BOOTSTRAP_TOKEN`,
`LONORA_COOKIE_SECURE=false`, `LONORA_ALLOWED_ORIGIN=http://127.0.0.1:8840`,
`LONORA_AUTH_RATE_LIMIT_PER_MINUTE=10000`, `LONORA_ARTIFACT_ROOT=$RT/artifacts`,
`LONORA_CLI_SOCKET=.runtime/android-8840/cli.sock`, and the owner email/password. No `.env` is
written in the checkout (the settings read `.env` from the working directory; none exists).

Start everything (idempotent: it only starts what is not running; about 5 s warm):

```sh
bash $RT/start.sh
```

It does, in order:

1. Creates the virtualenv if `.venv/bin/lonora-api` is missing.
2. PostgreSQL: `initdb` if `$RT/pg/data` is empty (`-U lonora`, scram-sha-256, then
   `listen_addresses='127.0.0.1'`, `port=55432`, `unix_socket_directories=''`), `pg_ctl start`
   unless `pg_isready` answers, `CREATE DATABASE lonora_android_test` if missing.
3. `bash scripts/migrate.sh`.
4. API: `setsid nohup .venv/bin/lonora-api --host 127.0.0.1 --port 8840` (pid `$RT/api.pid`,
   log `$RT/logs/api.log`). Its environment has no provider key.
5. Gateway: `LONORA_OPENAI_API_KEY=explicit-local-fixture-key setsid nohup .venv/bin/python
   $RT/scripted_gateway.py` (pid `$RT/gateway.pid`, log `$RT/logs/gateway.log`).
6. Waits for `/health` and `/ready`, then `$RT/bootstrap_owner.py`: `GET /api/onboarding`,
   `POST /api/onboarding` once with the bootstrap token, `POST /api/auth/mobile/login`, and writes
   `$RT/creds.json` (a new 24 h bearer token on every start) and `samples/login-response.json`.

Every Lonora process runs behind a network guard: `HTTP(S)_PROXY`/`ALL_PROXY` point at the closed
port `127.0.0.1:9` and `NO_PROXY=127.0.0.1,localhost,::1`. Direct DNS is already blocked in this
container, so no outbound host is reachable from the API or the Gateway.

Stop and reset:

```sh
kill -TERM $(cat $RT/gateway.pid) $(cat $RT/api.pid)
unshare --user --map-user=1000 --map-group=1000 /usr/lib/postgresql/16/bin/pg_ctl -D $RT/pg/data -m fast -w stop
# full reset: stop, then rm -rf $RT/pg (start.sh re-creates and re-migrates; a new owner is bootstrapped)
```

### Container specifics

- The Docker daemon is not running (`/var/run/docker.sock` missing), so `docker compose up db`
  (`scripts/dev.sh`) cannot be used; the local PostgreSQL 16 binaries are used instead.
- PostgreSQL refuses to run as root, and the harness resets `/tmp/claude-0` to mode 0700 between
  commands, so the `postgres` user cannot reach a data directory under the scratchpad. The server
  therefore runs as uid 1000 inside a user namespace
  (`unshare --user --map-user=1000 --map-group=1000`); its files stay owned by root outside.
- The scratchpad path is too long for a Unix socket (107-byte limit), so PostgreSQL listens on
  TCP only and the API's CLI socket is `.runtime/android-8840/cli.sock` (gitignored, and separate
  from the default `.runtime/cli/lonora.sock` that a Playwright run would replace).
- `scripts/cache_model_tokenizers.py` was not run: it downloads tokenizer files from
  `openaipublic.blob.core.windows.net`. Lonora then counts tokens as UTF-8 bytes
  (`utf8_bytes_fallback_v1`), roughly four times the real count; see the context setting below.

## Getting a scripted reply

### A. Live: scripted Gateway (default, running now)

`$RT/scripted_gateway.py` runs the stock resident Gateway (`lonora_worker.main.main`, with every
maintenance step, heartbeat and worker lane) after making the `check_durable_runtime.py`
substitution for every `OwnerServices` the process creates: `services.router.factory` returns a
`LocalScriptedAdapter`, a subclass of the repository's `ScriptedModelAdapter` that never runs out
and streams its text through `on_delta` three words at a time (0.15 s apart;
`LONORA_SCRIPTED_DELAY` changes it). At start it also writes two owner settings:

- `model_routing`: unified `{"provider": "openai", "model": "scripted-local-fixture"}`
  (what `PUT /api/settings/models` stores);
- `model_context`: `maximum_input_tokens=400000`, `input_ceiling_tokens=null` (what
  `PUT /api/settings/models/context` stores). The fixture model has no catalog window, so the
  64000 default for unknown windows applies, and the byte estimate of a fresh conversation
  (about 84k) failed admission with `context_limit_exceeded` before this was set.

The `openai` key the router needs is the dummy `LONORA_OPENAI_API_KEY` in the Gateway's
environment only (`ProviderCredentials.resolve` reads it); nothing is stored in the database. The
launcher refuses to start unless the database name ends in `_test`, `_verify` or `_ci` and the key
is that dummy. Do not run the stock `lonora-gateway` against this database: with no key its runs
fail with `model_not_configured`.

Any owner message to any agent then gets, through the real dispatch, context building, streaming,
persistence and events:

```
Scripted local reply (no model provider was contacted). You said: <your text> [<YYYY-MM-DD HH:MM> UTC, owner]
```

The bracketed suffix is the runtime's own annotation of the owner message in the model context.
Assert with `startsWith("Scripted local reply")` and `contains(<sent text>)`, not equality. A reply
takes about 1.8 s end to end. To capture a whole exchange again (creates or reuses the agent
"Android Scripted Agent", subscribes over WebSocket and SSE, sends one message, writes `samples/`):

```sh
cd /home/user/lonorabot && env HTTPS_PROXY=http://127.0.0.1:9 HTTP_PROXY=http://127.0.0.1:9 \
  NO_PROXY=127.0.0.1,localhost .venv/bin/python $RT/capture_exchange.py "your message"
```

### B. Test-harness fixture (as the Playwright suites do)

`tests/check_streaming.py browser` works against this live server too (verified with the
commands below: `init`, `append`, `recover`, `complete`, `cleanup`). It builds its own in-process app on the same database and signs in with
`LONORA_UI_TEST_EMAIL` / `LONORA_UI_TEST_PASSWORD` (set them to the owner in creds.json). **Stop
the scripted Gateway first** (`kill -TERM $(cat $RT/gateway.pid)`), or it races the fixture for the
queued run; `/ready` is 503 while it is stopped.

```sh
cd /home/user/lonorabot && set -a && . $RT/lonora.env && set +a
export LONORA_UI_TEST_EMAIL=$LONORA_OWNER_EMAIL LONORA_UI_TEST_PASSWORD=$LONORA_OWNER_PASSWORD
F=$RT/fixture.json
step() { jq --arg a "$1" '.action=$a' "$F" | .venv/bin/python tests/check_streaming.py browser; }
echo '{"action":"init"}' | .venv/bin/python tests/check_streaming.py browser > "$F"
# a group of 2 agents and a leased run streaming "START durable browser prefix "
step append  > "$F.next" && mv "$F.next" "$F"   # 170 more deltas on the same turn
step recover > "$F.next" && mv "$F.next" "$F"   # new lease and turn: replaces the preview
step complete                                   # commits the current text as the final message
step cleanup                                    # deletes the fixture's agents, group and thread
bash $RT/start.sh                               # brings the Gateway back
```

`append` and `recover` print the fixture JSON with the new `text`, `turn` and `lease`, which the
next step needs (a step with an older lease fails with `stale_lease`). `$F` holds the `thread`,
`group`, `agents` and `run` ids for the app to open. The observed durable sequence for `init` then
`complete` was `run.queued, run.running, run.reply_started, run.delta, run.reply_committed,
message.created, run.completed`. B suits deterministic eviction, reload and fenced-restart cases;
A suits ordinary chat flows.

## API surface verified with the bearer token

All under `http://127.0.0.1:8840`, header `Authorization: Bearer <creds.json bearer_token>`.
Bearer requests need no CSRF header and the native login sets no cookie.

| Call | Result |
|---|---|
| `POST /api/auth/mobile/login` `{email,password}` | 200 `{"owner":{"id","email"},"token":<64 chars>,"expires_in":86400}`, `Cache-Control: no-store` |
| `GET /api/agents` | personal agent `Lonora` (`role: personal`), created at onboarding, plus created agents |
| `POST /api/agents` `{"name","scope_mode":"flexible"}` | 201 agent (`role/template: general`). Without `scope_mode: flexible` it needs a broker account and symbol (422 `agent_trading_binding_required`) |
| `POST /api/agents/{id}/conversation` `{}` | the agent's one canonical thread |
| `POST /api/threads/{id}/messages` `{"content","client_nonce"}` | 202 `{"message","run_ids","runs","deduplicated"}`; a repeated nonce is deduplicated |
| `GET /api/threads/{id}/messages?limit=&before=&around=` | messages oldest first (`role` user/assistant, `seq`) |
| `GET /api/runs?thread_id=` / `GET /api/runs/{id}` | run with `status` and `stream` (durable preview: `turn_id`, `sequence`, `text`, `phase` streaming/committed, `message_id`) |
| `GET /api/events?cursor=&thread_id=` | durable events after a cursor |
| `DELETE /api/agents/{id}` | `{"deleted":true}` |

Realtime, both verified in parallel for the same exchange (identical events):

- **WebSocket** `ws://127.0.0.1:8840/api/ws/events`. First client frame within 10 s:
  `{"token": "<bearer>", "live": true}` (or `"cursor": N` to resume after N). Server frames:
  `{"type":"ready","cursor":N}`, then one JSON event per frame, and `{"type":"ping"}` every 15 s.
  A present `Origin` header must equal `LONORA_ALLOWED_ORIGIN` (`http://127.0.0.1:8840`), else
  close 1008; native clients normally send none. The session is rechecked every 5 s (revoked or
  expired: close 1008).
- **SSE** `GET /api/events/stream?live=true` with the bearer header; `cursor=N` or the
  `Last-Event-ID` header resumes. Frames: `id: N` / `event: ready` / `data: {"cursor":N}`, then
  `id: <cursor>` + `data: <event JSON>` per event, and `event: ping` (no id) every 15 s.

Event JSON: `{"cursor", "kind", "thread_id", "agent_id", "run_id", "payload", "created_at"}`.
Sequence for one exchange (owner message, scripted reply):

```
ready → run.queued → message.created (owner) → run.leased → run.running → run.context_started
→ run.context_ready → run.reply_started {turn_id, provider, model, generation, sequence: 0}
→ run.delta {turn_id, text, sequence: 1..n} (×4) → usage.created → run.delta (last)
→ run.reply_committed {message_id, phase: committed} → message.created (assistant) → run.completed
```

The reply text is the concatenation of `run.delta.payload.text` for one `turn_id`; a new
`generation` or `turn_id` replaces the preview (fallback or recovered worker); `message.created`
with the committed `message_id` replaces the preview with the durable message.

## Samples (`$RT/samples/`)

| File | Content |
|---|---|
| `login-response.json` | mobile login status, headers and body (token replaced by a placeholder) |
| `agents-list.json`, `agent-create-response.json` | agents list after creating a flexible agent |
| `conversation-thread.json` | `POST /agents/{id}/conversation` |
| `send-message-request.json`, `send-message-response.json` | owner message and its 202 admission |
| `thread-messages.json` | the thread after the reply |
| `run.json` | the completed run, with its committed stream snapshot |
| `ws-frames.jsonl` | every raw WebSocket frame of the exchange, one per line |
| `sse-stream.txt` | the raw SSE body of the same exchange |
| `events-since-zero-for-thread.json` | `GET /api/events?thread_id=` |

## Reaching it from Android

The API listens on 127.0.0.1 of this container only. From an emulator or device attached through
adb to a machine that can reach this port, `adb reverse tcp:8840 tcp:8840` makes
`http://127.0.0.1:8840` work in the app; the emulator's `10.0.2.2:8840` reaches the host's
loopback only when the emulator runs where this server runs. Plain HTTP needs a cleartext
exception in the debug network security config.

## What failed or is not covered

- Docker daemon unavailable; replaced by local PostgreSQL 16 in a user namespace.
- The first scripted run failed with `context_limit_exceeded` (byte-based token estimate against the
  64000 unknown-window default); fixed by the `model_context` setting the launcher writes.
- No Web build, no tokenizer cache, no voice, push, broker, market data or research services:
  none is needed for chat, and the network guard makes any such attempt fail locally.
- The scripted model returns text only (no tool calls, cards or generated UI). Flows that need
  tool activity can publish `tool.started` / `tool.completed` with the `peer_init` /
  `peer_activity` actions of `tests/check_streaming.py browser` (mechanism B).
- `start.sh` makes a new owner session (bearer token) on every run; older tokens stay valid until
  they expire.
