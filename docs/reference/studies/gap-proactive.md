# Gap analysis: proactive agents (work without a user message)

Audience: Lonora developers. Lonora was read at `/home/user/wt-agent/fxmain` (main `d8193b98`), read only. The
reference projects were read only through the two reports `openmausbot-proactive.md` and `rakazo-proactive.md`; nothing
from either clone was run. Paths below are Lonora repo-relative unless marked OMB (OpenMausBot) or RKZ (rakazo).

Effort scale: **S** under a day, **M** 2 to 4 days, **L** 1 to 2 weeks, **XL** more. Each recommendation keeps VISION
section 6 unchanged, adds no Stop control (Amendment 1) and no venue other than MetaTrader through MetaApi (Amendment 2).

## Ranked table

| # | Recommendation | Verdict | Prio | Effort | From | Owner decision |
|---|---|---|---|---|---|---|
| 1 | Skip a routine tick while an earlier run of the same routine is still queued or running; count the skipped ticks | adopt | P1 | S | both | no |
| 2 | Surface owner-only model failures (rejected key, spent billing, unknown model) of background work once, and hold the failing routines until it is fixed | adapt | P1 | M | both | no (a push for it would be) |
| 3 | Tell a late routine run when it was due (scheduled time and missed count in the run, fixed late note in the wake frame) | adopt | P2 | S | both | no |
| 4 | Give every wake a bounded "your standing work" section: own routines, watches and timers with their next due time | adopt | P2 | S | OMB | no |
| 5 | Coalesce watch confirmations for the same agent and thread into a wake that has not started yet | adapt | P2 | M | both | no |
| 6 | Model-free `feed` watch kind: wake only on new news-feed items | adapt | P2 | M | both | no |
| 7 | Owner-connected alert sources (per-source capability URLs for TradingView/Pine alerts, bound to one agent, rate-limited, merged) | adapt | P2 | L | both | **yes** (11.8 and 0.4) |
| 8 | Market-hours gate on routines (FX week or a symbol's broker hours), chosen by the agent | adapt | P2 | M | both | no |
| 9 | A timer set in a chat names that chat, so the run can read it; the tool says the prompt is all the run gets | adapt | P2 | S | both | no |
| 10 | `ends_at` on routines; the last run is told it is the last | adopt | P3 | S | both | no |
| 11 | Accept an exact sentinel as a silent ending besides the empty reply, after measuring each provider | adapt | P3 | S | both | no |
| 12 | Show model cost per run in routine history (a view, never a meter) | adapt | P3 | S | OMB | no |
| A1 | Broker events wake the owning agent from the gateway's own MetaApi connection, grouped and idempotent | already-better | P3 | - | both recommend it | - |
| A2 | Market watches: model-free, tick and candle evaluation, confirmations, debounce, cooldown, expiry, health, quarantine | already-better | P3 | - | both | - |
| A3 | Push: closed list of five kinds (six since Amendment 5), fixed text, no model text, receipt before send, never resent | already-better | P3 | - | both | - |
| A4 | Silence enforced by the server; a failed silent wake gives the owner back its source item | already-better | P3 | - | both | - |
| A5 | Morning brief: server facts, Lonora writes, server fallback, time learned from app opens | already-better | P3 | - | OMB | - |
| A6 | Trade Approval validity by price drift, not a timeout | already-better | P3 | - | both | - |
| A7 | Supervised maintenance steps, per-item isolation and a deterministic watchdog | already-better | P3 | - | both | - |
| A8 | Hidden work thread per routine, output in the agent's own conversation | already-better | P3 | - | both | - |
| S1 | Spend caps, run caps and per-routine budgets for autonomous work | skip | P3 | - | both | - |
| S2 | A global "pause all autonomy" switch | skip | P3 | - | both | - |
| S3 | Owner approval or Undo cards for schedules an agent creates | skip | P3 | - | both | - |
| S4 | Keyed job queue plus reconciler, or a due-timer primitive | skip | P3 | - | both | - |
| S5 | Per-routine model pin | skip | P3 | - | RKZ | - |
| S6 | Daily "strategic check-in" run per agent | skip | P3 | - | RKZ | - |
| S7 | Waits on URL text, files and processes; email and SaaS-app triggers | skip | P3 | - | both | - |
| S8 | Reminder pushes and auto-cancel for unanswered questions | skip | P3 | - | RKZ | - |

---

## 1. What Lonora does today

Lonora has no heartbeat prompt and no free-running "think" loop, the same as both references. Every autonomous model call
comes from one durable row or one server event, and every one is a normal Run on the single engine (P4).

### 1.1 The worker loop

`apps/worker/src/lonora_worker/main.py` starts `Gateway` (`packages/gateway/src/lonora_gateway/service.py`). `STEPS`
holds 35 supervised maintenance steps, each with its own interval, iteration timeout and liveness record
(`liveness.py`, `supervisor.py`). Steps poll the database; the database is the only truth. The proactive ones:

| Step (interval) | Function | What it wakes |
|---|---|---|
| `routines` (5 s) | `lonora_automation.runner.dispatch_routines` -> `lonora_db.routines.enqueue_one` | a `routine` Run |
| `watches` (2 s) and stream ticks | `lonora_market.watchers.check_watches` | a `watch` Run, or resumes a Task waiting on the watch |
| `task_waits` (5 s) | `lonora_db.task_wait.resume_ready_waits` | resumes a durable Task (timer, watch, broker recovery) |
| `account_recovery` (10 s) | `lonora_trading.broker_recovery.wake_for_activity` | a `broker_event` Run per agent and account revision |
| `close_wakes` (10 s) | `lonora_trading.close_wake.wake_for_closes` | self-review after a closed trade (5.5.2), merged into an executing Run as a notice when possible |
| `attention` (2 s) | `lonora_gateway.attention.attention_tick`, `lonora_db.system_alerts.wake_for_alerts` | Lonora's system-alert wake (3.1.5, 9.4) |
| `management_tasks` (60 s) | `lonora_db.management_task.reconcile_management_tasks` | Full mode's continuous task (4.5) |
| `approval_drift` (2 s) | `lonora_trading.approval_drift.check_drift` | wakes the agent whose card drifted (10.3.1) |
| `morning_brief` (30 s) | `lonora_trading.morning_brief.brief_tick` | Lonora writes the brief (11.1) |
| `push` (2 s) | `lonora_gateway.push.dispatch_push` | Expo push for the 11.4 kinds |
| `watchdog` (30 s) | `lonora_gateway.watchdog.Watchdog.tick` | owner items for overdue schedules, stuck operations, quarantined work |

Two more wake doors are HTTP: `lonora wake` from a workspace script (`lonora_db/workspace_wakes.py`, 7.3.7) and the signed
`POST /api/webhook` (`apps/api/src/lonora_api/routes/webhook.py` -> `lonora_agent/automation/webhooks.py`).

### 1.2 Routines

- Contract `packages/contracts/src/lonora_contracts/routines.py`: exactly one of `interval_seconds` (minimum 60),
  `cron` with `timezone`, or one-shot `run_at`. Columns in `RoutineRow` (`packages/db/src/lonora_db/schema.py`): no end
  date, no market-hours gate, no state.
- `create_routine` (`packages/db/src/lonora_db/routines.py`) always creates a hidden work thread (`purpose="work"`); runs
  carry `origin_thread_id`, so output lands in the agent's own conversation (11.6, `background_origin` in
  `lonora_db/threads.py`).
- `due_query` selects enabled, due routines of unpaused agents (4.7) with `FOR UPDATE SKIP LOCKED`. `enqueue_routine`
  creates the Run and advances `next_run_at` in the same transaction; missed occurrences collapse into one wake
  ("never replay a burst after downtime"). A one-shot switches itself off.
- A routine whose enqueue keeps raising backs off and is quarantined with one owner item (`ItemGuard`,
  `packages/db/src/lonora_db/item_failures.py`, `QUARANTINE_AFTER = 5`).
- Agent tools: `routine_create`, `routine_list`, `routine_toggle` (`packages/tools/src/lonora_tools/routine.py`); Lonora
  toggles a team agent's routine through `control_work`. History: `lonora_automation.delivery.routine_history` (last 100
  runs by routine id, silent ones included).

### 1.3 Market watches

`packages/contracts/src/lonora_contracts/market_watch.py` (`Watch`): kinds `price`, `indicator`, `position`,
`account`, `calendar`, `dynamic` (detector trees, relationships); `required_observations`, `debounce_seconds`,
`confirmation_ttl_seconds`, `cooldown_seconds` (minimum 30), `interval_seconds` (minimum 5), `evaluation_mode` (`tick`,
`candle_update`, `candle_close`, `scheduled`), `expires_at`, `dedupe_key`. `check_watch`
(`packages/market/src/lonora_market/watchers.py`) evaluates without a model, records data health
(`watch_health.py`), writes a `MarketWakeReceiptRow` per observation so a confirmation wakes once, and either resumes the
Task that waits on it or creates one `watch` Run.

### 1.4 Broker events and system alerts

`wake_for_activity` (`packages/trading/src/lonora_trading/broker_recovery.py`) turns broker changes that the gateway's
own MetaApi connection observed into wakes: one effect receipt per change, grouped per (agent, attributed) per account
revision into one Run; a change on an unattributed ticket wakes Lonora as `observe_only`; a paused agent is still woken
for its own tickets (4.7.1, `PAUSED_WAKE`). `lonora_db/system_alerts.py` wakes Lonora once per broker health problem or
uncertain operation, with fixed server text.

### 1.5 Silence, attention and push

- `BACKGROUND_TRIGGERS` and `is_background` (`packages/core/src/lonora_core/run_state.py`): the server alone marks a Run
  background (`BACKGROUND_KEY`), and the owner's words end its silence (`OWNER_SPOKE`). Every background wake frame
  carries the fixed `BACKGROUND` sentence (`packages/agent-runtime/src/lonora_agent/context/routine.py`). The router
  accepts an empty reply only for such runs (`allow_empty` in `packages/providers/src/lonora_providers/router.py`); an
  empty reply posts nothing (`tool_loop.py`). `tests/test_background_silence.py` covers about 30 cases.
- A wake's source raises no attention item beside the woken run; if the woken run fails, `projected`
  (`packages/gateway/src/lonora_gateway/attention.py`) decides the source again so the owner still learns of it.
- Push (`packages/gateway/src/lonora_gateway/push.py`): `PUSH_CODES` is the closed list of 11.4; fixed catalog text, no
  model text, an effect receipt per record and phone before the network call, an unknown send never resent.
- Quiet hours exist in the reach-me preferences (`quiet_start_minute`, `quiet_end_minute`; used by
  `lonora_voice/incoming.py` and `owner_notify`); 11.4 pushes are not held by them, on purpose.

### 1.6 Self-scheduling

The agent has routines, watches, Task timers (`task_wait`, `packages/tools/src/lonora_tools/tasks.py`) and
`lonora wake`. The operating manual (`packages/agent-runtime/resources/system/lonora.md`) line 209 forbids claiming to
watch without a saved watch, routine or wait; line 363 asks the agent to call `routine_list` before creating overlapping
checks. That line is the only guard against overlap (section 3.1).

---

## 2. Where Lonora is already ahead

**A1. Broker events are push triggers.** Both reports' main advice for Lonora ("make broker events push triggers, not
polled watches", RKZ avoid 3; "push events from the worker's own connection", OMB avoid 9) is built:
`wake_for_activity` and `close_wake.py`. RKZ polls with a 5-minute floor; OMB long-polls a third-party broker for SaaS
events. Lonora also merges a closed-trade review into a Run that is already executing (`merge_run_notices`) instead of
starting a second one, which is OMB's burst merge applied to the hottest event.

**A2. Market watches.** RKZ's change watch is a fingerprint compare every 5 to 1,440 minutes; OMB's waits probe URLs,
files and processes. Lonora's watches evaluate on ticks and candles with confirmation counts, debounce, cooldown, TTL,
expiry, health states (stale/unavailable with `last_good_at`), quarantine and a wake receipt per observation, all
without a model.

**A3. Push policy.** OMB summarizes model text into notifications; RKZ pushes completion text (180 chars). Lonora pushes
only five record kinds, with fixed text and no price, volume, account number or model text, with receipt-before-send
idempotency and Expo receipts (`push.py`). Nothing to copy.

**A4. Silence.** OMB enforces a `NOTHING NEW` last-line regex; RKZ an exact `NO_RESPONSE` sentinel. Both still depend on
the prompt to decide who is background. Lonora decides it on the server (`is_background`), lets the owner's words end
it, keeps an unverified order always reported (`test_a_silent_exit_still_reports_an_unverified_order`), and restores
the source's attention item when the silent wake fails (`projected`). Neither reference has the last two.

**A5. Morning brief.** OMB's brief is one edited card rendered from checks. Lonora's (`morning_brief.py`) assembles the
facts on the server, has Lonora write them, posts a plain server brief if Lonora has not written it within 30 minutes,
learns the time from the owner's first app opens (11.1), and keeps one effect receipt per local date.

**A6. Trade Approval validity.** Both references auto-deny unattended approvals after 30 minutes. VISION 10.3.1
replaces time with price drift (`approval_drift` step), which is the right rule for trading and must stay.

**A7. Fault isolation.** One failing routine, watch, integration or attention event backs off and is quarantined alone
(`ItemGuard`); the watchdog alerts the owner when routines or timer waits run more than 5 minutes late
(`OVERDUE_GRACE`, `SCHEDULER_STEPS`). RKZ has a 30 s reconciler for a job queue that can lose jobs; Lonora has no queue
to lose.

**A8. Work threads.** RKZ hands a due routine's prompt into a busy chat after 5 minutes (`dueRoutineHandoverPrompt`);
OMB creates a hidden task per run. Lonora's routine works in its own hidden work thread and reports to the agent's own
conversation, so owner chat never blocks it and it never opens a new chat (11.6).

---

## 3. Gaps and recommendations

### 3.1 [P1, S, adopt] Do not stack overlapping routine runs

**Today.** `enqueue_routine` (`packages/db/src/lonora_db/routines.py`) creates a Run on every due tick. It does not
look for an earlier run of the same routine. `claim_next` (`packages/db/src/lonora_db/runs.py`) runs one leased or
running Run per thread, so later ticks queue in the work thread behind the one that is running. With the contract's
minimum interval of 60 s and a 4-minute run, three new runs queue behind each running one, and the queue keeps
growing while runs take longer than the interval. Every queued run is a full model call on the owner's key (D6, D41).
The only guard is the prompt line 363 of `lonora.md`, which is about duplicate routines, not overlapping ticks.

**References.** RKZ: "If an earlier tick of this timer is still active (including waiting for the user), return
skipped", plus coalescing of unstarted catch-up ticks (`findPendingRoutineTick`). OMB: `overlap: "skip"` by default,
`"queue"` allows one; skipped occurrences are one counted `missed` row.

**Proposal.** In `enqueue_routine`, when a Run of this routine (`thread_id = row.thread_id`, `trigger = "routine"`) is
`queued`, `leased` or `running`, advance `next_run_at` and create no Run; carry the count as `skipped_occurrences` in
the next Run's metadata so `routine_history` shows it. A run in `waiting_input` does not block the schedule: an
unanswered question must not stop the routine.

**Files.** `packages/db/src/lonora_db/routines.py`, `packages/automation/src/lonora_automation/delivery.py`, a test
beside `tests/test_gateway_reliability.py`.
**VISION.** 11.5 (no pile of runs with nothing new), 17 (durable runs), P6.
**Test.** A 60 s routine whose first run is held running: three dispatch passes leave one Run, and the next Run carries
`skipped_occurrences = 2` once the first ends.

### 3.2 [P1, M, adapt] Owner-only model failures of background work

**Today.** `plan_failure` (`packages/agent-runtime/src/lonora_agent/model_recovery.py`) returns `raise` for every
non-transient error, which includes `AUTH`, `PERMISSION`, `BILLING` and `MODEL_NOT_FOUND` (`FailureReason` in
`packages/adapter-kit/src/lonora_adapter_kit/model_errors.py`). A background routine run then fails. By design it posts
nothing in the conversation (`docs/proactivity.md`), and `classify_attention` (`packages/core/src/lonora_core/attention.py`)
raises no item for `run.failed`, except where `projected` maps a failed watch, broker or opportunity wake back to its
source. A plain routine's failure therefore reaches only the mobile run strip (model and quota families); the web
client shows nothing. Each later tick fails the same way. With BYOK (D6, D41) a revoked key or spent credit is the most
likely overnight failure, and the owner wakes to an account nobody watched.

**References.** RKZ `backOffRoutineAfterAccountError` (`ACCOUNT_REFUSAL_KINDS`: auth, access, key, credit, spending,
model; next run pushed out 5 min x 2^(n-1), capped at 24 h; `releaseRoutineBackoffs` when the owner saves a new
connection) and auto-pause after 5 same-cause failures with a chat line. OMB: owner-only causes "fail immediately and
are told once per bot and cause" (`ownerNotices`), and holds that turn routines off while no AI is signed in and back on
when the cause clears (`routine-holds.ts`).

**Proposal.**
1. One attention item per provider route and cause, code for example `model_access_failed`, with fixed server text
   (provider name and failure family only, never the provider's message). It is withdrawn when a run on that route
   succeeds or the credential changes. Lonora cannot write it (3.1.5), because Lonora's own model is what fails.
2. While the item stands, due routines of the agents whose every model candidate fails for that cause advance without
   a Run and count as skipped (as in 3.1); saving a credential through `ProviderCredentials` releases them at once.
   Watches keep evaluating without a model; their confirmations already fall back to owner items through `projected`.
3. No new push kind. 11.4 is a closed list, and adding one is the owner's decision.

**Files.** `packages/agent-runtime/src/lonora_agent/model_recovery.py`, `packages/contracts/src/lonora_contracts/attention.py`
(new code), `packages/core/src/lonora_core/attention.py`, `packages/db/src/lonora_db/attention.py`,
`packages/db/src/lonora_db/routines.py`, `packages/providers/src/lonora_providers/credentials.py`, the shared attention
labels (ar/en) for web and mobile.
**VISION.** 11.7 (one "needs your attention" view), P6, 11.5 (silence must not hide a failure only the owner can fix),
12.1, DECISIONS D6/D41. It does not limit a decision (P1): the held runs could not run.
**Test.** A provider stub answering 401: the first routine failure raises one item; the next ticks create no Run;
saving a key withdraws the item and the routine fires on its next tick.

### 3.3 [P2, S, adopt] Tell a late routine run that it is late

**Today.** The routine Run carries `routine_id` and `origin_thread_id` only. After downtime, a suspension and
`lonora quiesce` (Amendment 3.9), or a weekend update window (DECISIONS D11), `enqueue_routine` collapses the missed
occurrences into one wake that starts at once, with nothing saying it was due hours ago. A "check positions before the
London open" run then starts mid-session and believes it is on time.

**References.** RKZ `lateRoutineRunInstruction` after 15 minutes (`LATE_ROUTINE_RUN_MS`); OMB "runs late" sentence and
a 12 h catch-up window.

**Proposal.** `enqueue_routine` writes `scheduled_for` (the occurrence it fires) and `missed_occurrences` (from the
collapse) into the Run metadata. `wake_context` adds one fixed server sentence when the start is more than 15 minutes
after `scheduled_for`: due time, start time, missed count, "re-check what changed". No fixed catch-up window: the agent
judges staleness (5.1).

**Files.** `packages/db/src/lonora_db/routines.py`, `packages/agent-runtime/src/lonora_agent/context/routine.py`.
**VISION.** 5.2 (Timing), 17 (recovery after restarts), Amendment 3.9.
**Test.** A routine due 3 hours ago fires once with the late sentence and `missed_occurrences` set; one due 1 minute ago
has no sentence.

### 3.4 [P2, S, adopt] "Your standing work" on every wake

**Today.** The context builder (`packages/agent-runtime/src/lonora_agent/context/builder.py`) gives the agent its
responsibility, memory, skills, scratchpad, the account picture (`context/picture.py`) and ended workspace processes. It
does not list the agent's own enabled routines, watches and pending timers. The agent has to call `routine_list` and
`watch_list`, and line 209 of `lonora.md` makes every monitoring claim depend on that.

**Reference.** OMB `active-routines-context.ts`: up to 6 enabled automations (4,000 chars total, 500-char previews) in
the bot's system prompt, labelled "bounded previews, not permission to act".

**Proposal.** One `ContextSection("standing_work", ...)` labelled `agent_authored`: at most 10 items with kind, id,
title or condition (symbol, level, kind), next due or next check, and who paused it. Never the full prompt.

**Files.** `packages/agent-runtime/src/lonora_agent/context/builder.py`, a new `context/standing.py`, reads from
`packages/db/src/lonora_db/routines.py`, `market_watches.py`, `task_wait.py`.
**VISION.** 5.2 (self-scheduling), 5.4 (adds to the full picture; replaces nothing), 6.10 (labelled as the agent's own
text), `lonora.md` lines 209 and 363.
**Test.** An agent with two routines and one watch gets a section naming the three with their next times; an agent
with none gets no section.

### 3.5 [P2, M, adapt] Coalesce watch wakes that have not started

**Today.** Every confirmation that passes cooldown creates one `watch` Run (`check_watch`). On a data release, several
watches of the same agent (EURUSD, GBPUSD, XAUUSD) confirm within seconds. Their Runs queue in the same thread and each
calls the model separately, each seeing one symbol.

**References.** OMB `mergeIntoQueuedRun` (events join a queued, unstarted run of the same trigger); RKZ coalesces
unstarted catch-up ticks.

**Proposal.** When an agent's earlier watch Run in the same thread is still `queued`, a new confirmation joins it: its
observation is appended to a `watch_ids` list in that Run's metadata and its wake receipt points at that Run. A Run
that has started is not touched (a close-wake style notice is an option later). `projected` maps a failed merged wake
back to every watch it stood for, as it already does for `broker_event_ids`.

**Files.** `packages/market/src/lonora_market/watchers.py`, `packages/gateway/src/lonora_gateway/attention.py`,
`packages/agent-runtime/src/lonora_agent/context/routine.py`, `tests/test_background_silence.py`.
**VISION.** 5.4 (full picture), 11.5, 17.
**Test.** Three watches confirming while the agent's thread is busy produce one queued Run that lists three
observations; if it fails, three owner items return.

### 3.6 [P2, M, adapt] A model-free `feed` watch

**Today.** News feeds are read only by `news_feed_read` (`packages/tools/src/lonora_tools/feeds.py`) inside a Run that
already exists. "Watch the central-bank feed" is therefore a routine that calls the model every interval even when no
item is new. The acceptance scenario (16.4, the news agent tells the others about a central-bank speech) depends on
this path.

**References.** RKZ `tool`/`http` change watches (fingerprint, `track` fields, `baseline | unchanged | changed |
failed`, pause and explain after a hard failure); OMB cheap checks before any model call, with cursors moved only after
the answer is kept.

**Proposal.** `Watch.kind = "feed"` with `integration_id` of a subscribed `news_feed` and optional `keywords`. The
watcher reads the feed through the existing SSRF-safe client (`packages/adapters/src/lonora_adapters/market/news_feed.py`),
keeps seen item ids in watch state (as `seen_events` for calendars, capped at 1,000), and wakes only on new matching
items; their titles and links reach the model as untrusted data. `MarketWatch` payloads are `extra="forbid"`, so the
stored-payload migration of 14.3.9 comes first.

**Files.** `packages/contracts/src/lonora_contracts/market_watch.py`, `packages/market/src/lonora_market/watchers.py`,
`packages/tools/src/lonora_tools/market_watch.py`, `packages/adapters/src/lonora_adapters/market/news_feed.py`, a migration.
**VISION.** 11.8 (its own watches), 16.4, 11.5, 6.10 (items are data), 14.3.9.
**Test.** A feed with no new items produces no Run across ten checks; one new matching item produces one Run whose
context labels the item untrusted.

### 3.7 [P2, L, adapt; owner decision] Owner-connected alert sources

**Today.** `POST /api/webhook` (`apps/api/src/lonora_api/routes/webhook.py`) requires an HMAC of the body in
`x-lonora-signature` with the one installation-wide `LONORA_WEBHOOK_SECRET`; the caller names the agent and thread in the
body. The prompt is fixed and the caller's text (4,000 chars at most) is an untrusted section (`webhooks.py`), which is
correct. But there is no per-source secret, no rate limit (`RateLimitMiddleware` limits only the sign-in routes), no cap
on pending runs, no merge of bursts, and no owner instruction attached to a source. TradingView alerts, the natural output
of the Pine Script that agents may write (5.7), cannot sign a body or set a header: they POST plain text to a URL.

**References.** OMB `webhook-ingress.ts`: capability URL `/hooks/wh_<id>/<secret>` checked before the body is read,
256 KiB cap, event allow-list and payload filter, `maxPendingRuns` 3, 10 per minute per endpoint, delivery-id dedupe,
owner instructions block before an `[UNTRUSTED WEBHOOK EVENT DATA]` block, hashed and sealed secrets. RKZ: a webhook wakes
nothing unless an owner routine enables it; the owner's routine prompts come first.

**Proposal.** Per-source capability URLs, each bound to one agent, created, rotated and deleted from chat on the owner's
typed message (`owner_message_id`, as trusting a source in 10.3.2); hashed secret; per-source rate limit and pending
cap; alerts arriving while that source's wake is still queued join it; the owner's words saved with the source reach
the run as a user-role request, the payload as untrusted data. Orders still go only through the door; nothing here
touches section 6.

**Owner decision.** 11.8 lists what wakes an agent and does not list webhooks; 0.4 lets contradicting code keep working
but forbids extending it. The owner either adds "owner-connected alert sources" to 11.8, or chooses the `lonora wake`
path, which would need public ingress into the workspace that 7.1 and Amendment 3.11 do not provide today.
**Files.** `apps/api/src/lonora_api/routes/webhook.py`, `packages/agent-runtime/src/lonora_agent/automation/webhooks.py`,
a new table and migration in `packages/db`, `packages/agent-runtime/src/lonora_agent/context/routine.py`,
`apps/api/src/lonora_api/middleware/rate_limit.py`.
**VISION.** 11.8 (conflict), 0.4, 5.7, 6.10, P5 (managed from chat), Amendment 3.11 (no narrowing of the agent).

### 3.8 [P2, M, adapt] Market-hours gate for routines

**Today.** Routines know cron, interval and one-shot only. An interval routine runs through the weekend, when the FX
week is closed, and each run is a model call that ends silent. Cron can approximate `1-5` weekdays but not the
DST-correct Sunday 17:00 to Friday 17:00 New York week that `fx_week` (`packages/market/src/lonora_market/sessions.py`)
already computes, nor a symbol's broker hours (`broker_trading_state`).

**References.** OMB interval schedules have `weekdays` and a `window` (allow-window); RKZ's report recommends "skip
when the market is closed" schedule kinds.

**Proposal.** Optional `active_hours`: `"fx_week"` or `{account_id, symbol}` (broker hours). `next_run` skips to the
next open interval. The agent chooses it per routine; the server never imposes it.

**Files.** `packages/contracts/src/lonora_contracts/routines.py`, `packages/db/src/lonora_db/routines.py`,
`packages/db/src/lonora_db/schema.py` plus a migration (14.3.9: `Routine` payloads are `extra="forbid"`),
`packages/market/src/lonora_market/sessions.py`, `packages/tools/src/lonora_tools/routine.py`.
**VISION.** 5.2 (Timing), 11.5, P1 (the agent's own scheduling choice, never a limit), Amendment 2 (the broker's symbols
and hours).
**Test.** A 15-minute `fx_week` routine set on Friday 16:50 New York fires at 16:50, then next on Sunday 17:00.

### 3.9 [P2, S, adapt] A timer set in a chat

**Today.** `create_routine` gives every routine, one-shot timers included, a new hidden work thread titled with the
prompt. A run set from a conversation ("check this again at the New York open") sees only its prompt; the
`routine_create` description does not say so. Watches set in a chat keep that chat (`docs/proactivity.md`); routines
do not.

**References.** OMB `check_back` (note, optional condition, the same chat, saved before it starts, at most once) and its
`TRIGGER_PROMPT` rule "complete steps for a future run that will not see this chat"; RKZ's one-shot follow-up that
records its id in the open item and is cancelled when the item resolves.

**Proposal.** Keep the work thread and the output in the agent's own conversation (11.6). Record the originating
conversation and message seq on a routine created in a chat; the wake frame names them, so the run can read that
conversation with the existing `session_search`. The tool description says the prompt is all the run receives.

**Files.** `packages/db/src/lonora_db/routines.py`, `packages/tools/src/lonora_tools/routine.py`,
`packages/agent-runtime/src/lonora_agent/context/routine.py`, `docs/proactivity.md`.
**VISION.** 5.2 (self-scheduling, "wake me at 2,425"), 11.6, 11.8 (timers), 6.10.

### 3.10 [P3, S, adopt] Routine end time

Routines have no end; watches have `expires_at`. "Every 15 minutes until the release is over" ends only if the agent
remembers to toggle it. Add `ends_at` (contract, column, `due_query`), and tell the last run it is the last (RKZ
`endsAt`; OMB interval `endsAt`). Files: `packages/contracts/src/lonora_contracts/routines.py`,
`packages/db/src/lonora_db/routines.py`, a migration. VISION 5.2, 11.5, 14.3.9.

### 3.11 [P3, S, adapt] Sentinel as a second silent ending

Lonora's silence is an empty provider reply (`allow_empty`). A model that cannot end empty writes "No changes" and that
text is posted. RKZ accepts an exact `NO_RESPONSE` (repeated allowed; mixed with prose fails closed and keeps the text);
OMB accepts `NOTHING NEW` on the last line. First measure, per provider (OpenAI, Anthropic, DeepSeek, Z.ai, OpenRouter),
how often a background run with nothing new ends empty, using `scripts/agent_eval`. Only if some provider misses, accept
one exact sentinel as equal to empty, stripped by the server so it never shows (17). Files:
`packages/agent-runtime/src/lonora_agent/tool_loop.py`, `packages/providers/src/lonora_providers/router.py`,
`packages/agent-runtime/src/lonora_agent/context/routine.py`, `scripts/agent_eval/score.py`. VISION 11.5, 17.

### 3.12 [P3, S, adapt] Cost per run in routine history

`ln_usage` rows carry `run_id` (`packages/llm-usage/src/lonora_llm_usage/store.py`). `routine_history` could add the
priced cost of each run (`lonora_core.model_pricing`), as OMB's `RoutineRun.cost`, so the owner sees what a 1-minute
routine costs on their key. It is a view only: never a meter against a limit (`docs/usage-dashboard.md`, decisions
D4/Q22). Files: `packages/automation/src/lonora_automation/delivery.py`. VISION: DECISIONS D6/D41.

---

## 4. Skipped, with the clause that rules it out

**S1. Spend caps, run caps, per-routine budgets.** OMB `usage-caps.ts`, `CHECK_RUNS_PER_DAY = 24`, starter
concurrency; RKZ `MAX_ACTIVE_ROUTINES_PER_BOT = 50`; both reports' "add budgets" advice. P1 forbids caps, quotas and
activity budgets; `docs/usage-dashboard.md` (D4/Q22) and DECISIONS D6 forbid spend caps; Amendment 3.4 forbids plans
that limit model use. Sections 3.1 and 3.2 cut the waste without a limit.

**S2. "Pause all autonomy" switch.** RKZ avoid 1, OMB "pause all". Amendment 1 removed every Stop control; the owner's
controls are the Mandate card, the pause of one agent or piece of work, and the broker connection.

**S3. Owner approval or Undo cards for agent-created schedules.** RKZ treats `schedule_create` as a "lasting write";
OMB shows an Edit/Pause/Undo card. VISION 5.2 makes self-scheduling the agent's judgment, 6.10's last bullet says taint
must not spread to later watches, routines or wakes, and 10.3.2 maps change notices to the agent's own composition.
Lonora's `profile_taint.py` mark is read only by the owner-profile check, which is the narrow form 6.10 allows.

**S4. Keyed job queue and reconciler (RKZ), due-timer primitive (OMB).** Lonora polls the database in each step with
`FOR UPDATE SKIP LOCKED`; the database is the only truth, so there is no lost job to reconcile. OMB's due timer exists
for laptop sleep; Lonora runs on an always-on server or one VM per customer (DECISIONS D1).

**S5. Per-routine model pin (RKZ).** 12.3: the owner assigns the model per agent from chat, and `owner_message_id`
gates model assignment (14.3.5). An agent pinning its own routine model would bypass that. Only by owner amendment.

**S6. Daily strategic check-in per agent (RKZ).** An unprompted daily model call per agent with `ask_user` only. The
morning brief (11.1) and line 209 of `lonora.md` (no monitoring claim without a saved wake) cover open loops; revisit
if evaluations show forgotten follow-ups.

**S7. URL/file/process waits (OMB), email and SaaS-app triggers (both).** P3: workspace scripts already do this and
call `lonora wake` (7.3.7); 7.1.2 deliberately reports ended processes on the next wake. MT5 data comes from MetaApi,
not email. External signals belong in 3.7.

**S8. Reminder push and 24 h cancel for unanswered questions (RKZ `reconcileStuckWork`).** 11.4 is a closed push list;
background questions are already in the attention view (11.7) and copied into the conversation (`report_thread`).

---

## 5. Limits of this analysis

- The reference projects were read only through their reports; claims about them are the reports' claims.
- In Lonora I read the files cited above. I did not read the web or mobile routine and watch screens,
  `lonora_db/management_task.py` beyond its header and timer handover, `lonora_trading/weekly_report.py` beyond its
  name, or `lonora_trading/opportunities.py`. Nothing was run; the overlap (3.1) and failure (3.2) gaps come from
  reading `enqueue_routine`, `claim_next`, `plan_failure` and `classify_attention`, and each has a test proposed that
  would confirm it before any fix.
- The Lonora Cloud documents add nothing specific to proactivity except D1 (one VM per customer, always on), D6/D41 (the
  customer's own key, which makes 3.2 more important) and D11 (weekend update window, which makes 3.3 more useful).
