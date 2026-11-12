# Phase 7 map: Proactivity (mandate section 11, P5, P6, 3.1.5, 5.5.6, 10.3 Execution Receipt, section 13)

Read-only survey of `/home/user/wt-agent/mandate` at commit `a776adf` ("Adopt the Lonora Execution Mandate as VISION.md"). Nothing in the repository was changed.
Every path is relative to that checkout. Aliases used below:

| Alias | Path | Alias | Path |
|---|---|---|---|
| `GW` | `packages/gateway/src/lonora_gateway` | `TR` | `packages/trading/src/lonora_trading` |
| `DB` | `packages/db/src/lonora_db` | `MK` | `packages/market/src/lonora_market` |
| `CT` | `packages/contracts/src/lonora_contracts` | `AD` | `packages/adapters/src/lonora_adapters` |
| `CORE` | `packages/core/src/lonora_core` | `AUTO` | `packages/automation/src/lonora_automation` |
| `TOOLS` | `packages/tools/src/lonora_tools` | `API` | `apps/api/src/lonora_api` |
| `AR` | `packages/agent-runtime/src/lonora_agent` | `WEB` | `apps/web/src` |
| `RES` | `packages/agent-runtime/resources` | `MOB` | `apps/mobile` |

"Lonora" in the code is the Personal Agent (`ensure_personal_agent`, `DB/personal_agent.py:16`).

---

## 1. Scheduling and wakes today

### 1.1 The loop
- One gateway process runs every maintenance step as its own supervised task (`GW/service.py:40-65`). Steps of this area: `routines` every 5 s (`:43`), `task_retries` (`:44`), `task_waits` (`:46`), `outcomes` (`:47`), `account_recovery` every 10 s (`:50`), `watches` every 2 s (`:56`), `channels` (`:60`), `attention` (`:61`), `incoming` (`:62`).
- Runs are claimed by worker loops (`GW/service.py:108-142`, `GW/run_dispatch.py:31-93`). There is one "conversation" lane and shared lanes (`GW/service.py:290-301`). Work triggers are `tickets, routine, watch, webhook, subagent, broker_event, activation` (`CT/runs.py:7-9`); the lane filter is at `DB/runs.py:246-255`.
- **One active Run per thread**: a thread with a leased or running Run is not claimed again (`DB/runs.py:256-275`). Any design that puts background runs into the conversation thread makes them queue with the owner's turns.
- `create_run` refuses every Run of a paused agent with `agent_paused` (`DB/runs.py:156-157`).

### 1.2 Routines
- Table `ln_routines` (`DB/schema.py:526-545`): `thread_id` (not null), `prompt`, `title`, exactly one of `interval_seconds` / `cron` / `run_at` (`CT/routines.py:33-35`), `timezone` default `"UTC"` (`CT/routines.py:26`), `goal_id` / `step_id`.
- **A new chat per routine**: `create_routine` adds `ThreadRow(owner_id, agent_id, title=prompt[:80])` for every routine not linked to a goal (`DB/routines.py:67-70`). The thread takes the default purpose `conversation` (`DB/schema.py:227-229`). A goal routine uses the goal's thread (`DB/routines.py:60-66`).
- Firing: `dispatch_routines` (`AUTO/runner.py:6-20`) reads `due_routines` (`DB/routines.py:127-137`) and calls `enqueue_one` → `enqueue_routine`, which creates a Run with `trigger="routine"`, `thread_id=row.thread_id`, `prompt=row.prompt`, metadata `routine_id` (`DB/routines.py:189-202`).
- Paused agents are skipped (`DB/routines.py:108`). Missed schedules collapse into one wake (`DB/routines.py:233-236`). A one-shot fires once and switches off (`DB/routines.py:214-217`). A routine that keeps failing is switched off by quarantine (`DB/routines.py:151-156`, `AUTO/runner.py:10`).
- **Where the output goes**: `complete_run` writes the final message into the Run's own thread (`DB/runs.py:401-416`), so a routine's output lands in the routine's thread, never in the agent's conversation.
- **Who can see it**: the chat list shows only the oldest conversation thread per agent (`DB/inbox.py:24-28`, `:117`), so a routine thread has no row and no unread count. Mobile reaches it through the routine's history (`GET /routines/{id}/history`, `API/routes/routines.py:68-72`, `AUTO/delivery.py:9-22`; `MOB/app/routine.tsx:285-313`, `MOB/lib/routine.ts:19`). Web has no caller of that route (`WEB/shell/domain/api.ts:65-72` lists, updates and deletes only), so on web a routine's output is unreachable from the routine.
- Agent tools: `routine_create`, `routine_list`, `routine_toggle` (`TOOLS/routine.py:147-163`). Owner REST: `API/routes/routines.py:19-65`. Owner screens: `WEB/shell/domain/SchedulesPages.tsx:272-302`, `MOB/app/routine.tsx`.

### 1.3 Watches
- `watch_create` binds a watch to the agent's own conversation (`report_thread`), or to the Task's work thread when a Task created it (`TOOLS/market_watch.py:118-124`; `DB/threads.py:108-129`).
- A watch created with no thread gets a new conversation thread (`DB/market_watches.py:76-85`); the owner REST resource `/watches` goes through that path (`API/routes/watches.py:13`).
- Firing: `check_watches` (`MK/watchers.py:379`, called from `GW/wake_dispatch.py:6-7`) skips paused agents (`MK/watchers.py:399`), then creates a Run with `trigger="watch"` in the watch's thread (`MK/watchers.py:677-701`), once per observation (`MarketWakeReceiptRow`, `MK/watchers.py:636-637`, `:702-713`). A Task-owned watch resumes its Task instead of starting a Run (`MK/watchers.py:654-664`).
- Opportunity transitions wake with `trigger="watch"` in a new **work** thread with `origin_thread_id` (`TR/opportunities.py:403-437`).

### 1.4 Timers
- One-shot routines (`run_at`, `CT/routines.py:15-25`).
- Task waits: `TaskWait.kind` is `watch`, `broker_recovery` or `timer` (5 s to 7 days) (`CT/tasks.py:109-118`); resumed by `resume_ready_waits` (`DB/task_wait.py:167`, `GW/service.py:267`).
- There is no timer outside a Task or a routine.

### 1.5 Everything that starts a Run today

| Trigger | Created at | Thread it runs in | Where the owner sees the result | In 11.8? |
|---|---|---|---|---|
| `user` / `group` | owner message `DB/messages.py:600`; card submit `DB/genui_submit.py:393`, `:536` | the conversation | same thread | yes |
| `routine` | `DB/routines.py:189-202` | the routine's own thread | that thread only (1.2) | yes, wrong place |
| `watch` | `MK/watchers.py:677-701` | the agent's conversation, or the Task thread | same thread | yes |
| `watch` (opportunity) | `TR/opportunities.py:418-437` | new work thread | copied to the conversation, `AR/collaboration/outcome_return.py:166-216` | yes |
| `broker_event` | `TR/broker_recovery.py:232-246` | new work thread (`:204-206`) | copied to the conversation, same code | yes |
| `tickets` (Tasks, waits, retries) | `DB/tasks.py:209-222`, `AR/automation/background.py:42-56` | Task work thread | `complete_run` writes no message for `tickets` (`DB/runs.py:401`); wait updates go to the origin conversation (`DB/task_wait_settlement.py:100-119`) | "timers" |
| `peer` | `AR/collaboration/peer_messages.py:94-112`, `DB/collaboration.py:167-175` | the target agent's conversation | both conversations (`peer_messages.py:72-93`) | **not listed** |
| `follow_up` | `AR/collaboration/outcome_return.py:260-266`, `DB/collaboration.py:338-344` | requester's thread | same thread | not listed (server) |
| `subagent` | `AR/collaboration/subagents.py:51-57` | helper thread | returned to the parent | not listed (internal) |
| `webhook` | `POST /webhook` with HMAC, `API/routes/webhook.py:16-34`, `AR/automation/webhooks.py:10-21` | any thread the caller names | that thread | **not listed** |
| `owner_card` | card continuation `DB/owner_actions.py:2085-2119`; renew an expired approval `DB/trade_approvals.py:167-198` | the conversation | same thread | owner's tap |
| `agent_created` | `DB/agent_creation.py:442-448` | the new agent's conversation | same thread | not listed (server) |
| `goal`, `activation` | `TR/goals.py:345-355`, `DB/activation_review.py:98-122` | goal thread / work thread | removed in Phase 3 | removed |
| owner REST `POST /runs` (any trigger string) | `API/routes/runs.py:43-48` | caller's choice | that thread | not listed |

Facts that matter for 11.8 and 4.7:
- Only fixed server prompts stay in the system role (`AR/context/routine.py:13-15`); a routine, watch, peer or Task prompt is delivered as a user-role request with only the trigger named (`AR/context/routine.py:24-26`).
- A broker event wakes an agent only for **external** activity (a change no journaled Lonora operation explains, `TR/broker_recovery.py:91-94`, `:152-153`). The agent's own confirmed close wakes nobody.
- A paused agent is never woken, not even for its own positions: its activity falls back to Lonora, observe-only (`TR/broker_recovery.py:179-186`, `:198-202`, `:230`).
- Broker **health** (`broker.degraded` / `broker.recovered`) wakes no agent at all (section 4).
- No `lonora wake` exists (the CLI is Phase 4). `wake_agent` is an unused helper that would serve it (`AR/automation/wakes.py:8-10`).

### 1.6 "Nothing new" today
- The server posts nothing when the final reply is empty: `complete_run` adds a message only when there is text, an artifact or rich content (`DB/runs.py:401`); the copy to the conversation needs a non-empty result (`AR/collaboration/outcome_return.py:178`); a Task wait update likewise (`DB/task_wait_settlement.py:107`).
- An empty model turn is accepted as final for background triggers; only conversational triggers get the "no answer" retry (`AR/tool_loop.py:575-581`; `is_conversational` excludes `routine, webhook, created, tickets, watch`, `CORE/run_state.py:33-34`). `broker_event` counts as conversational there, so an empty reply to a broker wake is pushed to answer.
- A `group_silence` tool ends a background turn with no message (`TOOLS/runtime_control.py:108-124`; `AR/tool_block.py:395-407`). Its name and prompt text tie it to groups (`RES/system/lonora.md:528-530`).
- The only instruction is one line: "When nothing meaningful changed, avoid another identical background notification." (`RES/system/lonora.md:445`).
- So silence is **possible but not the rule**: nothing tells a routine or watch run to reply with nothing, and nothing checks it. A routine run that says "nothing changed" posts that sentence every time.

---

## 2. Notifications today

### 2.1 The attention engine (in-app only)
- Projection: `attention_tick` (`GW/attention.py:448-523`) reads published events whose kind is in `ATTENTION_KINDS` (`CORE/attention.py:7-35`), classifies each (`classify_attention`, `CORE/attention.py:38-118`), revalidates against current state (`candidate`, `GW/attention.py:110-348`) and stores one `ln_attention` row per logical transition (`decide_attention`, `DB/attention.py:118-301`; table `DB/schema.py:555-582`).
- Importance levels: `critical, action_required, important_change, opportunity, informational, silent` (`CT/attention.py:10-12`). Critical and action-required items are ready at once; others wait 3 s to coalesce (`DB/attention.py:243`, `:275`). `publish_ready` emits `attention.ready` (`DB/attention.py:304-331`).
- System items raised without the projection loop: `raise_system_attention` (`DB/attention.py:578-677`) for `maintenance_item_quarantined, run_quarantined, operation_unresolved, gateway_degraded` (`DB/attention.py:34-39`), from the watchdog (`GW/watchdog.py:112`, `:233`, `:320`) and the failure ledger (`DB/item_failures.py:222`).
- Owner policy: `AttentionPolicy` = `opportunities` (default on), `informational` (default off), `locale` (`CT/attention.py:40-43`), stored under `attention-policy:<owner>` (`DB/attention.py:59-62`).
- Routes: `GET /attention` (open items), `/attention/history`, `/attention/audit`, `POST /attention/seen`, `/seen-all`, `GET/PUT /attention/policy` (`API/routes/attention.py:15-92`).

### 2.2 What creates an item today

| Event | Code, importance | Source | Item? |
|---|---|---|---|
| Trade approval becomes pending | `approval_required`, action_required | `DB/trade_approvals.py:64-73` → `CORE/attention.py:68-73` | yes |
| Operation becomes ambiguous | `operation_uncertain`, action_required; plus a `resolve_operation` card | `TR/operation_events.py:72-110` → `CORE/attention.py:64-67`; card `GW/owner_cards.py:81-97` | yes |
| Emergency stop set | `emergency_stop`, critical | `CORE/attention.py:62-63` | yes |
| Broker degraded or disconnected | `broker_degraded`, **important_change**; critical only with open positions or unresolved operations | `CORE/attention.py:74-80`; `GW/attention.py:159-162` | yes, not urgent |
| External broker activity | `external_broker_activity`, important_change | `CORE/attention.py:81-83` | yes |
| Watch confirmed / invalidated, opportunity transitions | `setup_confirmed` (opportunity), `thesis_invalidated` | `CORE/attention.py:84-92` | yes |
| Task failed / needs owner / degraded / completed | `task_review`, `task_degraded`, `task_completed` | `CORE/attention.py:102-116` | yes |
| Agent's own alert (`owner_notify`) | `agent_notification`, agent-chosen importance | `DB/attention.py:345-491` | yes |
| **Credential request card pending** (`connect_credential`) | none | `owner_action.updated` (`DB/owner_actions.py:1055-1069`) is not in `ATTENTION_KINDS` | **no** |
| **Grant card pending** (`grant_authority`, today's Mandate ancestor) | none | same | **no** |
| Broker-confirmed operation | silent `internal_update` | `CORE/attention.py:59-61` | no (correct for 11.4) |

### 2.3 `owner_notify` and the other agent tools
- Tools `owner_attention_list`, `owner_notify`, `owner_call_request` (`TOOLS/incoming_call.py:118-148`).
- `notify_owner`: one item per agent and `dedupe_key`; 6 alerts per agent per hour (`NOTIFY_LIMIT_PER_HOUR`, `DB/attention.py:335`, `:396-406`); 6 critical per owner per hour (`:339`, `:409-422`); quiet hours hold everything but critical (`:434`, `:476-478`); reach-me "activity only" raises no item (`:466-468`); per-agent rules `in_app` and `daily_limit` (`DB/agent_delivery.py:58-92`).
- Delivery is fixed to `"in_app"` (`NOTIFY_DELIVERY`, `DB/attention.py:341`). The tool tells the model "Off-app delivery (push, messaging channels) is not available yet." (`TOOLS/incoming_call.py:29-32`, `:132-133`); the prompt says "in-app only for now" (`RES/system/lonora.md:209`).

### 2.4 Quiet hours and reach-me
- One stored policy, `IncomingCallPolicy` (`CT/incoming_calls.py:41-58`): `channel` in `activity, notify, message, call` (default `message`), `timezone` default `"UTC"` (`:50`), quiet hours to the minute (`:51-56`), `quiet_until` (`:113-126`). Read by `reach_me_policy` (`DB/owner_profile.py:175-183`).
- Quiet hours apply only to agent-raised alerts and to calls. System items (approvals, uncertain operations, broker health) ignore them.
- Web also filters its banner on the device by quiet hours, mute and archive (`WEB/shell/lists/HeadsUp.tsx:26-29`; rules `packages/core/src/chat-rows.ts:226-260`).

### 2.5 Mobile push: nothing exists
- No push code anywhere: no `expo-notifications` dependency (`MOB/package.json:18-45`), no plugin (`MOB/app.config.ts:69`), no notification permission (`MOB/app.config.ts:43`), no token table, no route, no sender. A repository-wide search for `expo push`, `push_token`, `ExponentPushToken`, `exp.host`, `fcm`, `apns` matches documents only.
- The reserved place is a stub: `export const notificationPermissionFlow: null = null;` (`MOB/components/shell/notifications.ts:1-4`).
- Mobile learns of attention only while the app is active: it polls `GET /attention` every 5 s under `AppState === "active"` (`MOB/lib/shell-data.tsx:2`, `:120`, `:159-165`).
- The Android app is built locally (`expo prebuild` + Gradle, `MOB/scripts/android-release.py:62-70`) and served by the Lonora server (`LONORA_ANDROID_APK_PATH`, `.env.example`); `runtimeVersion` follows the native fingerprint (`MOB/app.config.ts:52`). A native module cannot arrive over OTA (`docs/incoming-attention.md:119-123`), so push needs a new native release.
- No deployment setting for push exists (`API/env.py:10-100`).

### 2.6 Other channels
- `dispatch_channels` (`GW/event_dispatch.py:35-190`) serves `telegram` and `webhook` integrations (`:62-67`). Outbound: assistant `message.created` events (`:152-153`) and `attention.ready` items that are **critical or action_required only** and still current (`:124-151`), as fixed catalog text (`attention_text`, `packages/bus/src/lonora_bus/attention.py:19-21`). Each delivery has an effect receipt and is never resent when unconfirmed (`:162-166`, `:179-185`).
- Telegram adapter: long polling and `sendMessage` (`AD/channels/telegram.py:7-34`). Inbound text becomes an owner message in the bound conversation (`GW/event_dispatch.py:70-98`).
- **Telegram is linked but inert**: deliveries and inbound both depend on `allowed_destinations` (`GW/event_dispatch.py:81-83`, `:154-158`), and nothing ever writes that field: the web sheet posts type, name, `secret_id`, `deliver_to_agent_id`, `enabled` (`WEB/shell/settings/IntegrationsPage.tsx:356-378`); the repository sets only `thread_id` (`DB/integrations.py:46-57`); no test sets it. The web comment calls Telegram "an inbound channel to an agent, never a delivery channel to the owner (Q53)" (`IntegrationsPage.tsx:38-41`).
- `Integration.enabled` defaults to `False` (`CT/integrations.py:23`).
- Calls: `owner_call_request` persists an invitation, but the gateway calls `incoming_tick` with no transport (`GW/service.py:250-253`), so every invitation stays `provider_unconfigured` (`packages/voice/src/lonora_voice/incoming.py:259`, `:351-353`). `IncomingDelivery` is a protocol with no implementation (`incoming.py:41-52`).

---

## 3. Briefs, reports, time zone, app opens

- **No morning brief, daily summary or weekly report exists** in code, prompts, skills or playbooks (`RES/playbooks` holds six trading playbooks; `RES/skills` nine skills, none about reports). The only trace is a test that makes an ordinary one-shot routine titled «موجز الصباح» with the prompt "Prepare the brief" (`tests/test_domain_pages.py:84-87`).
- Material a brief can read:
  - account state per connection: `BrokerRecoverySnapshot` with account, positions and orders (`TR/broker_recovery.py:95-112`), saved in `BrokerSessionRow.state["broker_recovery"]` (`:134-137`);
  - the journal (`GET /trading/journal`, `API/routes/trading.py:123-134`);
  - a per-agent quality snapshot (`performance_snapshot`, `TR/performance.py:71`; `API/routes/performance.py:14-37`), which is quality counts, not money P&L (its docstring: "price return is not monetary P/L", `TR/performance.py:1`);
  - the economic calendar tool, only when the owner configured a source (`TOOLS/market_analysis.py:234-252`);
  - pending approvals (`ln_trade_approvals`).
- **No stored account history**: no row keeps balance or equity over time, so "the account change since the last brief" has no baseline today.
- **Weekly close**: `fx_week(now)` gives Sunday 17:00 to Friday 17:00 New York (`MK/sessions.py:93-104`); `broker_trading_state` gives the broker's own hours per symbol (`MK/sessions.py:245`).
- **Owner time zone**: the only stored one is `reach_me.timezone`, default `"UTC"` (`CT/incoming_calls.py:50`). The owner sets it by hand on web (`WEB/shell/settings/OwnerPage.tsx:78`, `:129-130`) or mobile (`MOB/components/incoming-call-settings.tsx:76`). Clients send the device zone only when creating a routine (`WEB/shell/domain/SchedulesPages.tsx:84`, `:456`; `MOB/app/routine.tsx:147-148`). The model sees it in the UI capabilities block (`AR/genui_capabilities.py:32`, `:37-38`).
- **App opens are not recorded.** `ln_sessions` has no last-used column (`DB/schema.py:40-46`); `require_owner` writes nothing (`API/middleware/auth.py:16-27`); the event stream records no connection (`API/routes/events.py:47-70`). Indirect traces only: `thread.read` events (`DB/thread_prefs.py:92-111`) and owner messages. The natural client hooks are the mobile `AppState` listener (`MOB/lib/shell-data.tsx:165`) and the web shell mount.

---

## 4. Broker health today

- Detection: `maintenance_account_recovery` every 10 s for up to 32 enabled connections (`TR/broker_recovery.py:249-269`; `GW/service.py:186-191`). `reconcile_broker_account` reads account, positions and orders under the account send lock with a 30 s limit (`TR/broker_recovery.py:38-60`).
- Any failure marks the snapshot `disconnected` with the adapter's code (`TR/broker_recovery.py:113-128`). Codes the MetaApi adapter already produces: `broker_credentials_rejected` on 401/403 (`AD/brokers/metaapi.py:66-67`), `broker_account_undeployed` and `broker_account_not_ready` (`AD/brokers/metaapi.py:374-382`), `broker_account_not_found` (`:62`), `broker_connection_timeout` / `broker_connection_unavailable` (`:70-86`), `broker_connection_closed` (`:353`). So the three cases of 9.4 are **already distinguished** in `reason_code`.
- On a change of `(status, reason_code)` one event is emitted: `broker.degraded` or `broker.recovered`, with `account_id`, `status`, `reason_code`, `previous_status`, `transition_id` (`TR/broker_recovery.py:138-151`).
- What it does today: an attention item `broker_degraded` in **Lonora's** conversation (`GW/attention.py:131-132`), importance `important_change` (so no Telegram or webhook delivery, `GW/event_dispatch.py:130`), fixed text "The broker connection is degraded…" that does not say which problem (`packages/bus/src/lonora_bus/attention_messages.json:6`, `:56`). The item is withdrawn when the state moves on (`DB/attention.py:93-100`, `:186-210`). Web opens a recovery page for it (`WEB/shell/domain/UpdatesPages.tsx:180-181`, `WEB/shell/agent/RecoveryPage.tsx:39`).
- **No agent is woken and nothing offers a fix.** One failed 10-second read is enough to emit `broker.degraded`; there is no debounce.

---

## 5. The unified view across agents today

- Server: `GET /attention` returns every open item of the owner across agents, filtered by the policy and by `valid_until` (`API/routes/attention.py:39-60`). Each item carries `agent_id`, `thread_id`, `code`, `parameters` (`DB/attention.py:42-56`).
- Web: the «المستجدات» tab is one of four roots (`WEB/shell/routes.ts:2`; `WEB/shell/pages.tsx:199`). `UpdatesPage` shows agent "stories", a notifications list read from `/attention/history` (the last 50 of any status), upcoming schedules and the latest actions (`WEB/shell/domain/UpdatesPages.tsx:140-330`). A tab dot shows while open items exist (`WEB/shell/Shell.tsx:827`, `:924`). `HeadsUp` shows a banner for critical and action-required items (`WEB/shell/lists/HeadsUp.tsx:180-200`). Open items come from `AttentionProvider` (`WEB/providers/AttentionProvider.tsx:42-60`).
- Mobile: the Updates tab renders `AttentionInbox` over the polled open items (`MOB/app/(tabs)/updates.tsx:46-53`; `MOB/components/attention-inbox.tsx:17-41`), with a tab dot (`MOB/app/(tabs)/_layout.tsx:31`). No banner.
- What is missing for 11.7: the list is a notification log, not "what needs you". It mixes items that need nothing (opportunities, completed tasks, recoveries) and misses pending credential and grant cards (2.2). No item shows the card itself; a tap opens the conversation. Web and mobile read different endpoints (`/attention/history` against `/attention`).
- P5 contrast: outside conversations the apps today also have a Tasks tab, a Settings tree (including the notification settings page `WEB/shell/settings/NotifyPages.tsx:36-41`), schedules pages and an activity log (`WEB/shell/pages.tsx:300`, `:327`).

---

## 6. Receipts today

- There is no receipt message and no receipt card. A confirmed operation appears in chat only as:
  1. the web **order line**: journal rows anchored to a conversation (`thread_id`, `timeline_seq`) are drawn between messages (`WEB/conversation/Conversation.tsx:180`, `:313-324`; `WEB/conversation/Cards.tsx:267`), refreshed on `trading.operation_updated` (`TR/operation_events.py:72-110`);
  2. whatever the agent writes in its reply (model words);
  3. a `stop_tightened` notice card when an agent tightens a stop under a grant (`TOOLS/trade.py:621-644`; kinds `CT/owner_actions.py:36`).
- The anchor is written only when a leased Run requested the operation (`TR/execution.py:248-249`; `DB/trading_journal.py:52-67`).
- Paths with **no** line in any chat:
  - the owner's own orders through `POST /trading/execute` (`API/routes/trading.py:116-120`): no Run, no anchor;
  - **mobile, for every operation**: no file under `apps/mobile` reads the journal or draws an order line.
- Operations confirmed later by reconciliation emit the same event (`TR/reconciliation.py:191-200`), so the web line updates; nothing new is posted.
- The event separates "confirmed, verification pending" from verified (`TR/operation_events.py:47-59`). The owner's own statement on a resolve card is recorded as "not broker confirmation" (`CT/owner_actions.py:59`).
- GenUI has an agent-drawn card kind named `receipt` (`CT/genui.py:53`), which is the agent's own composition, not a trusted record.

---

## 7. Built but switched off or unwired in this area (section 13)

| # | What | Evidence | Kind |
|---|---|---|---|
| 1 | Mobile notification permission flow | stub `MOB/components/shell/notifications.ts:1-4` | half-built |
| 2 | Telegram channel: linked from web, never delivers or receives | 2.6; `GW/event_dispatch.py:81-83`, `:154-158` | half-built path |
| 3 | Outbound webhook channel | served by `GW/event_dispatch.py:62-67`, `:175-178`; no client creates one (`WEB/shell/settings/IntegrationsPage.tsx` has no webhook form) | capability with no screen |
| 4 | Inbound `POST /webhook` wake | off unless `LONORA_WEBHOOK_SECRET` is set (`API/routes/webhook.py:19-20`; `API/env.py:99`; empty in `.env.example:35`, generated by `infra/compose/install.sh:197`) | off in configuration |
| 5 | Agent calls to the owner | no transport: `GW/service.py:250-253`; `packages/voice/src/lonora_voice/incoming.py:41-52`, `:351-353` | half-built |
| 6 | GenUI `Delivery` block accepts `push` and `call` (`CT/genui.py:68`, `:604-609`; `packages/core/src/genui/spec.ts:75`; `WEB/components/genui/UiCard.tsx:236`) while the model is told delivery is `app` only (`AR/genui_capabilities.py:22`) | accepted, not backed |
| 7 | Routine run history | server and mobile only (1.2); no web screen | missing on one client |
| 8 | Order lines | web only (6); missing on mobile | missing on one client |
| 9 | Web attention inbox page with the policy switches | `WEB/pages/ActivityList.tsx:27` is imported nowhere; `WEB/components/ai/AttentionInbox.tsx` is used only for its labels (`WEB/shell/domain/UpdatesPages.tsx:7`) | unrendered |
| 10 | Unused helpers | `wake_agent` (`AR/automation/wakes.py:8`), `routine_tick` (`AR/automation/routines.py:5`), `compute_next` (`AUTO/scheduling.py:7`), `validate_binding` (`AUTO/binding.py:4`), `ScheduledWake` (`AUTO/types.py:6`), `deliver_notification` (`packages/bus/src/lonora_bus/notifications.py:7`), `channel_projection` (`.../outbound.py:4`), `EventQueue` (`.../queue.py:7`), `dispatch_event` (`GW/event_dispatch.py:31`), `receive_message` (`packages/channels/src/lonora_channels/manager.py:9`), `verify_webhook_token` (`.../telegram/validation.py:6`), `decode_message` (`.../websocket/runtime.py:6`); `scheduler_tick` is used by one test only (`GW/scheduler.py:11`; `tests/check_activation_review.py:46`) | unwired |
| 11 | `informational` attention off by default (`CT/attention.py:42`); reach-me default `message` (`CT/incoming_calls.py:44`) | defaults | off by default |
| 12 | Tool hint that limits self-scheduling: "create it enabled, and only when the owner asked for it" (`TOOLS/market_watch.py:96-108`), against 5.2 and P6 | prompt text | contradicts mandate |

---

## 8. Tests in this area

| File | Covers | Mandate impact |
|---|---|---|
| `tests/test_attention.py:12-56` | classification table | `:42-48` fixes broker health at `silent` / `important_change`; 11.4 makes a broker problem push once → changes |
| `tests/check_attention.py` (416 lines) | projection, coalescing, restart, webhook channel delivery (`:316-370`), Personal ownership of account items (`:243`) | channel part extends to push; ownership matches 3.1.5 |
| `tests/test_proactive_wakes.py` (1114 lines) | broker-event wakes, observe-only, `owner_notify` rules | `:757` "a paused agent's activity falls back to the personal agent" contradicts 4.7.1 (a paused agent wakes for its own positions); `:949` asserts `delivery == "in_app"`; `:918`, `:1051` rate and quiet-hour rules stay unless the owner removes them |
| `tests/test_genui_taint.py` (906 lines) | taint inheritance | `:91`, `:227`, `:456`, `:618`, `:698`, `:730` assert that taint **does** spread to watches, routines and their wakes: the opposite of 6.10 (section 12, R1) |
| `tests/test_domain_pages.py:72-108`, `:501-700`, `:826-1020` | routine REST, one-shot rules | `:100-102` counts runs in `row.thread_id`; holds only if the routine keeps its own run thread (Q1) |
| `tests/test_gateway_reliability.py:97-162`, `:1141-1162` | routine isolation, quarantine | unchanged; a new push or brief step needs the same isolation tests |
| `tests/test_agent_delivery_rules.py` | per-agent `in_app`, `daily_limit`, calls | unchanged unless per-agent caps are removed |
| `tests/test_incoming_call_policy.py`, `tests/check_incoming_calls.py:128-308` | reach-me policy, invitation states | `:128` asserts `provider_unconfigured`; changes if calls get a transport |
| `tests/test_watch_lifecycle.py`, `tests/check_dynamic_watches.py`, `tests/test_trial_creations.py:20-47` | watch states, create-enabled rule | unchanged |
| `tests/check_broker_recovery.py`, `tests/check_account_recovery.py`, `tests/test_manual_activity.py` | reconciliation, external activity | core list of 14.1.2 for the first two: must pass after every step |
| `tests/test_order_line_fixture.py`, `tests/web/order-state.test.ts` | web order line | replaced by the Execution Receipt (Phase 3) |
| `tests/web/attention.spec.mjs`, `tests/mobile/attention.spec.mjs`, `tests/web/agent-alert.spec.mjs`, `tests/mobile/agent-alert.spec.mjs`, `tests/check_attention_browser.py`, `tests/check_agent_alert_browser.py` | inbox and banner UI | rewritten with the attention view (11.7) |
| `tests/web/settings.spec.mjs`, `tests/mobile/reach-me.spec.mjs`, `tests/mobile/reach-me.test.ts` | notification settings pages | affected by P5 (Q12) |
| `tests/mobile/routine-title.test.ts`, `tests/web/domain-pages.spec.mjs` | routine screens | affected by 11.6 and P5 |

No test covers: push, a brief, a weekly report, app-open recording, silence of a background run, or a receipt for the owner's own order.

---

## 9. Gap list

| Clause | State | What exists (files) | What is missing |
|---|---|---|---|
| **11.1** brief every day, from Lonora | **missing** | scheduler pattern (`DB/routines.py`, `AUTO/runner.py`), account snapshot (`TR/broker_recovery.py:95-112`), journal, calendar tool | the schedule, the facts (account change, per-agent actions and results, open positions, pending approvals, events, "nothing else needs you"), the Lonora wake, the every-day guarantee |
| 11.1 learned time, 07:00 before 3 days | **missing** | `reach_me.timezone` (`CT/incoming_calls.py:50`) | app-open recording, a learned time, a real owner time zone (default is UTC) |
| **11.2** receipt after every confirmed operation | **partly** (Phase 3 builds the card) | one confirmation event for all paths (`TR/operation_events.py:72-110`), web order line | a receipt record and card; owner's own orders; CLI orders (Phase 4); mobile; reconciliation-confirmed operations posted once |
| **11.3 / 5.5.6** weekly report per agent | **missing** | `fx_week` (`MK/sessions.py:93-104`) | the weekly wake per agent, the report in its conversation, Lonora's summary in the next brief; content from Phase 5 |
| **11.4** push for five events | **missing** | attention items for approval and uncertain operation (2.2); delivery ledger pattern (`GW/event_dispatch.py:162-185`); broker reason codes (section 4) | device token registration, Expo sender, deployment settings, native module and release; items for Secret and Mandate cards; broker health as a push event; "one push per card" |
| 11.4 no push for receipts and reports | **exists by absence** | confirmed operations classify as silent (`CORE/attention.py:59-61`) | keep it true when receipts and reports are added |
| 11.4 other channels (Telegram) | **partly** | adapter, dispatcher, web link sheet | chat-id pairing (2.6), the same five events, enabling from chat |
| **11.5** silence | **partly** | empty reply posts nothing (1.6) | the rule itself: a taught and checked "nothing new → no post" for every background trigger; `broker_event` empty-turn handling (`AR/tool_loop.py:576`) |
| **11.6** routine output in the agent's conversation | **missing (opposite)** | origin-thread copy for work wakes (`AR/collaboration/outcome_return.py:166-216`) | routines create and post into their own chat (`DB/routines.py:67-70`); owner-created watches too (`DB/market_watches.py:76-85`) |
| **11.7** one attention view | **partly** | `GET /attention`, web Updates tab, mobile Updates tab (section 5) | one definition of "needs you"; Secret and Mandate cards; same view on both clients; card shown in place; removal of the rest per P5 |
| **11.8** wake sources | **partly** | owner messages, external broker events, watches, routines, Task timers | `lonora wake` (Phase 4); extra sources not in the list (`peer`, `webhook`, `POST /runs`); paused-agent rule 4.7; closed-trade wake 5.5.2 (Phase 5) |
| **3.1.5** Lonora speaks for the team | **partly** | account-level and unattributed items go to Lonora's conversation (`GW/attention.py:131-132`, `:182-185`; `DB/attention.py:546-571`) | Lonora is not woken by system alerts; no brief |
| **10.3** Execution Receipt | **missing** | see 11.2 | Phase 3 |
| **P5** only six surfaces outside chat | **not met** | section 5 | which phase removes Tasks, Settings, schedules and activity pages is not stated (Q12) |
| **P6** proactive by default | **partly** | watches and routines work with the app closed | no default brief or report; a tool hint forbids self-scheduling (`TOOLS/market_watch.py:104-105`) |
| **Section 13** | see section 7 | | each row is switched on, completed or reported to the owner |

---

## 10. Design questions the mandate leaves open

**Q1. How does routine output reach the conversation (11.6) without blocking it?**
- (a) Run the routine in the agent's conversation thread. Simple, but a routine Run then queues with the owner's turns (`DB/runs.py:256-275`) and the conversation history grows with background turns.
- (b) Keep one hidden work thread per routine as its memory, add `origin_thread_id` = the agent's conversation, and copy the non-empty result there, as `broker_event` wakes do (`TR/broker_recovery.py:204-212`; `AR/collaboration/outcome_return.py:166-216`).
- **Recommend (b).** It reuses a tested path, gives 11.5 for free (empty result → no copy, `outcome_return.py:178`), keeps approval cards and receipts in the conversation (`DB/trading_journal.py:61-66`), and existing routine threads only change purpose to `work`. Same rule for watches created with no thread.

**Q2. Who decides "nothing new" (11.5)?**
- (a) The model: taught in the wake frame and tool descriptions to end with an empty reply; the server posts nothing for an empty reply.
- (b) The server compares the new text with the last one.
- **Recommend (a)**, with server guarantees: empty reply → no message, no attention item, no push; a failed background Run posts nothing in the conversation; `broker_event` is treated as a background trigger in `is_conversational`. (b) judges content, which P2 forbids.

**Q3. What is "opening the app", and how is the brief time learned (11.1)?**
- Options for the signal: (a) a client ping when the app becomes active (mobile `AppState`, web shell mount), stored once per local day with its time and the device time zone; (b) infer from `thread.read` events.
- Options for the rule: first open of the day, median over the last 7 to 14 recorded days, brief sent a fixed lead before it (for example 15 minutes), never moved by more than one hour per day.
- **Recommend (a) with the median rule**, stored in a small server table and exposed to the owner model of Phase 6 (8.1 "when the owner wakes and reads"). The owner confirms the lead and the window.

**Q4. Which time zone is "the owner's" (11.1)?** Today it is `reach_me.timezone`, default UTC, and 8.2 says reach-me settings change only on the owner's typed message.
- (a) Use `reach_me.timezone` only; a new install sends the brief at 07:00 UTC until the owner says otherwise.
- (b) Record the device time zone with each app open and use it for the brief while the owner has set none.
- **Recommend (b)**; the owner decides whether the device zone may also fill `reach_me.timezone`.

**Q5. Is the brief a routine row or a built-in schedule?**
- (a) A system routine on Lonora: visible in schedules, but any pause or toggle silences it, and it posts into a routine thread today.
- (b) A dedicated gateway step with one stored record per owner (next time, last local date sent, account baseline), idempotent per local date by effect receipt.
- **Recommend (b)**: "posts every day" must not depend on a row an agent or a pause can switch off.

**Q6. Who writes the brief, and what if the Run fails or Lonora is paused?** 10.1.2 forbids a fixed brief card; 11.1 says it posts every day; `create_run` refuses a paused agent (`DB/runs.py:156-157`).
- **Recommend**: the server assembles the facts and wakes Lonora with fixed server text (a new server-authored trigger, `AR/context/routine.py:13-15`); Lonora composes the brief. An empty reply to this trigger is not accepted. If no brief message exists after a deadline, the server posts a plain-text brief from the same facts. The owner confirms the fallback.

**Q7. What is "the account change since the last brief"?** Options: balance, equity, or both, per account, plus realized P&L from broker history. **Recommend** storing balance and equity per account in the brief record at each brief and showing both differences; realized P&L per agent comes from Phase 5 (5.5.4).

**Q8. How is the weekly market close defined (5.5.6)?**
- (a) The FX week close, Friday 17:00 New York (`MK/sessions.py:93-104`).
- (b) Each account's own broker hours (`MK/sessions.py:245`).
- (c) A fixed owner-local time.
- **Recommend (a)**: one clock for the whole team; an agent on a 24/7 market reports on the same day. Sequence: at the close each agent is woken once for its report; the first brief after the close includes Lonora's summary and names any report that is not ready.

**Q9. How are Expo push credentials "configured once in the deployment"?** The Expo push service needs an Expo project id in the app, FCM credentials (Android) and an APNs key (iOS) registered with that Expo project, and optionally an access token on the server.
- (a) Owner's own Expo project: `LONORA_EXPO_PROJECT_ID` and the Firebase file as inputs of `MOB/scripts/android-release.py`, `LONORA_EXPO_ACCESS_TOKEN` as an optional server setting in `API/env.py`, documented in `docs/operations.md`.
- (b) One Expo project owned by the Lonora publisher for all installs.
- **Recommend (a)**; it matches "self-hosted for a single owner" (section 17). It forces a new native release. With no token registered, readiness reports push as not configured instead of failing.

**Q10. What does a push say?** Push text passes through Expo, Google and Apple.
- **Recommend** fixed catalog text per event in the owner's language plus the agent's name, no price, no volume, no model-written text; a tap opens the conversation at the card. No notification action buttons: approval stays on the fixed card (6.10).

**Q11. Exactly which records push, and when?**
- Trade Approval and Settle: at creation of the card. Re-raised cards after drift are new cards and push again (acceptance step 4).
- Secret card: only one raised by an agent's Run. Mandate card: only one an agent proposed; **ask** whether the migration's one-time Mandate cards (14.3.18.2) push.
- Broker health: one push per account per problem, not per flap. **Ask** whether a lost connection pushes at the first failed read or after a short confirmation (for example two minutes); a rejected token and an undeployed account push at once.
- **Ask** whether quiet hours ever hold these five (the mandate lists no exception; today system items ignore quiet hours).

**Q12. P5: which phase removes the other surfaces?** Tasks tab, Settings tree, schedules pages, activity log and notification settings exist outside chat on both clients. Section 15 assigns P5 to no phase. **Recommend** Phase 7 delivers only the attention view and removes the Updates tab's other sections; the owner assigns the rest.

**Q13. What is in the attention view (11.7), and is it a projection or Lonora's writing?** **Recommend** a server projection (no model): pending Trade Approval, Settle, Secret and Mandate cards, open broker health problems, Runs waiting for the owner's answer, Tasks that need review. Each row renders the fixed card or opens it. Opportunities, completions and recoveries go to conversations, not to this view.

**Q14. Do system alerts wake Lonora (3.1.5, 9.4)?** **Recommend** yes: one wake per broker problem with fixed server text, in a work thread, result in Lonora's conversation. The offer to fix belongs to Phase 8; Phase 7 delivers the item, the push and the wake.

**Q15. Wake sources outside the 11.8 list.** `peer` messages wake the recipient today; `POST /webhook` and `POST /runs` start Runs from outside. **Recommend**: keep peer wakes (3.2.3 and acceptance step 4 need them), keep server-defined wakes named elsewhere in the mandate (4.2.3, 10.3.1.2, 3.1.2), and replace `POST /webhook` by `lonora wake` once Phase 4 lands. The owner confirms.

**Q16. `owner_notify`, `lonora notify` and the caps.** Neither pushes under 11.4. **Ask** whether `owner_notify` stays (an in-app attention item) or folds into `lonora notify` (a message in the agent's conversation), and whether the hourly and daily alert caps stay (`DB/attention.py:335-339`; `DB/agent_delivery.py:58-92`).

**Q17. Telegram.** **Recommend** completing it as a second delivery of the same five events: pair the chat by a one-time code sent to the bot, store the chat id, enable from chat. **Ask** which Secret-card destination holds the bot token (7.2.3 names only workspace and broker).

**Q18. Agent calls (section 7 row 5).** Complete them over the same push sender, or report them to the owner as out of scope. The mandate does not mention calls.

---

## 11. Ordered steps (one reviewable pull request each)

Core tests of 14.1.2 run after every step. "Needs" names a dependency on another phase.

| # | Pull request | Main files | Needs |
|---|---|---|---|
| 1 | **Routine output in the agent's conversation** (Q1): work thread per routine, `origin_thread_id`, copy of the non-empty result, migration of existing routine threads, same for watches with no thread; web and mobile open the conversation | `DB/routines.py:47-92`, `:189-202`; `AR/collaboration/outcome_return.py:166-216`, `:344`; `DB/market_watches.py:76-85`; new Alembic revision | none |
| 2 | **Silence** (Q2): one rule for every background trigger, wake-frame text, empty reply and failed Run post nothing, tests per trigger | `CORE/run_state.py:33-34`; `AR/tool_loop.py:575-581`; `AR/context/routine.py`; tool descriptions; `RES/system/lonora.md:445` with manifest (5.8.6) | 1 |
| 3 | **Wake sources** (Q15): one table of triggers, tests that nothing else starts a Run; `lonora wake` and `lonora notify` land in the conversation, text marked as data | `CT/runs.py:7-9`; `AR/context/routine.py:13-26`; `API/routes/webhook.py`, `API/routes/runs.py:43-48` | Phase 4 (CLI); Phase 3 and 6 for the paused-agent rule 4.7 |
| 4 | **Attention items for the five events**: Secret and Mandate cards, broker health with its reason code and its own importance; withdrawal when the card ends | `CORE/attention.py:7-118`; `GW/attention.py:110-348`; `DB/attention.py:65-115`; `CT/attention.py:13-37`; `packages/contracts/src/attention.ts`; catalogs `packages/bus/src/lonora_bus/attention_messages.json` | Phase 3 (the five cards exist) |
| 5 | **Device push registration**: token table, authenticated register and delete routes, mobile `expo-notifications`, permission flow, build inputs, native release | new `DB` table and revision; new `API/routes`; `MOB/components/shell/notifications.ts`; `MOB/app.config.ts:43`, `:69`; `MOB/scripts/android-release.py` | Q9 answered |
| 6 | **Push sender**: gateway step that reads `attention.ready` for the five codes, one effect receipt per card and device before any network call, Expo adapter, timeouts, isolation, readiness, fake-transport tests; no push for receipts and reports | new `AD/channels/expo_push.py`; `GW/service.py:40-65`; pattern `GW/event_dispatch.py:99-185`; `API/env.py` | 4, 5 |
| 7 | **Telegram completed** (Q17) with the same five events | `GW/event_dispatch.py`; `DB/integrations.py`; `AD/channels/telegram.py` | 4; Phase 4 (Secret card) |
| 8 | **App opens and time zone** (Q3, Q4): ping route, per-day record, learned time | new `DB` table; new route; `MOB/lib/shell-data.tsx:165`; `WEB/shell/Shell.tsx` | feeds Phase 6 (8.1) |
| 9 | **Morning brief** (Q5, Q6, Q7): gateway step, facts builder, account baseline, Lonora wake, fallback, once per local date | new step in `GW/service.py`; new module beside `TR/broker_recovery.py`; `AR/context/routine.py:13-15` | 8; Phase 3 (approvals with reasons); Phase 5 (5.4 picture, 5.5.4 results); Phase 6 (3.1.5, 3.1.6) |
| 10 | **Weekly report** (Q8): per-agent wake at the weekly close, report in the agent's conversation, summary in the next brief | step 9 modules; `MK/sessions.py:93-104` | 9; **Phase 5 owns the content** (5.5) |
| 11 | **Attention view** (Q13, Q12): one server definition, same view on web and mobile, cards in place, removal of the Updates tab's other sections | `API/routes/attention.py:39-60`; `WEB/shell/domain/UpdatesPages.tsx`; `WEB/shell/lists/HeadsUp.tsx`; `MOB/app/(tabs)/updates.tsx`; `MOB/components/attention-inbox.tsx` | 4; Phase 2 (mobile renders cards natively); Phase 3 (cards) |
| 12 | **Receipts check** (11.2): tests that every path posts exactly one receipt and none pushes; mobile shows it | Phase 3's receipt module; `TR/operation_events.py`; `TR/reconciliation.py:191-200` | Phase 3 (card), Phase 4 (CLI path) |
| 13 | **Section 13 sweep and text**: rows of section 7; prompt and tool text ("in-app only", `RES/system/lonora.md:209`; `TOOLS/incoming_call.py:29-32`, `:128-137`; `AR/genui_capabilities.py:1-6`, `:22`; `TOOLS/market_watch.py:104-105`); documents `docs/proactive-wakes.md`, `docs/incoming-attention.md`; manifest regenerated | as listed | all above |

Steps 1 to 3 need no other phase and can start at once. Steps 4 to 7 form the push chain. Steps 8 to 10 form the brief chain and are the ones blocked by Phases 5 and 6.

---

## 12. Risks to the safety core (section 6) and to provenance (6.10)

- **R1. Today's taint rule is the opposite of 6.10.** A Run started by a card submission is tainted and "its trades become approval cards"; the taint is stored on every watch, routine, Task and goal the Run creates or changes, and every wake from them inherits it (`DB/genui_taint.py:1-17`, `:30-37`, `:126-140`; `DB/runs.py:187-191`; `TOOLS/routine.py:43-44`, `:117-118`; `TOOLS/market_watch.py:164-165`; `MK/watchers.py:666-673`). 6.10 says a submission never turns a decision into an approval card in Full mode and taint MUST NOT spread to later watches, routines or wakes. `tests/test_genui_taint.py` asserts the old rule. The mandate assigns this change to no phase by name. Phase 7 adds wake paths (routine origin, brief, weekly report, `lonora wake`): none may pass `parent_run_id` or a tainted row id into `create_run`, and by section 0.4 none may extend the old rule. **Ask the owner which phase rewrites it** before step 1 merges.
- **R2. A receipt must state broker truth only (6.4).** A journal row can be `confirmed` with verification still `pending` (`TR/operation_events.py:47-59`); the owner's "executed" on a settle card is a statement, not broker evidence (`CT/owner_actions.py:59`). The receipt is posted once per operation id, from the journal transaction, on broker evidence, including the reconciliation path (`TR/reconciliation.py:191-200`). Nothing in the brief or weekly report may read as a confirmation: facts in them come from the journal and the broker snapshot, never from an agent's sentence.
- **R3. A push is never an approval surface (6.7, 6.10).** No action buttons, no deep link that approves. The tap opens the fixed card, which reads the live record. The same holds for Telegram replies: an inbound "yes" is an owner message to an agent, never an approval of a card.
- **R4. The push step must not delay or duplicate.** Network calls to Expo run in their own step with a timeout and per-item isolation, as channels do (`GW/event_dispatch.py:27-28`, `:50`). The receipt is written before the call and an unconfirmed send is never repeated (`:162-185`), so "one push" holds across restarts and two gateways. The attention loop keeps its critical-first order (`GW/attention.py:465-477`).
- **R5. The brief wake is an injection path into the lead agent.** The brief's facts include other agents' reports and reasons, peer messages and news, and Lonora may close any team position (3.1.3) and delete agents (3.1.2). That text must reach Lonora marked as data (6.10; helpers `mark_external_content`, `external_content_seen`, `TOOLS/restrictions.py:66-96`). Making the brief Run observe-only (`TR/execution.py:83-85`, `:107-109`) would be a new limit the mandate does not list (P2): **ask the owner** rather than add it.
- **R6. Moving routine runs changes thread lineage, not run integrity.** The lease, Task authority and ancestry checks of 6.9 read the Run, not the thread. Verify that an approval card and a receipt from a routine Run anchor in the conversation (`TOOLS/trade.py:424-427`; `DB/trading_journal.py:61-66`) and that `agent_thread_mismatch` (`TOOLS/trade.py:426-427`) does not refuse them.
- **R7. Push tokens and third parties.** A device token is registered only through the authenticated owner session, stored per device, removed on sign-out, never logged and never given to a model. No account number, price or agent text leaves the server in a push (Q10).
- **R8. Missed schedules.** After downtime, at most one brief per local date and one weekly wake per agent per week are sent; the routine dispatcher already collapses missed runs (`DB/routines.py:233-236`), and the new steps need the same rule and the same effect-receipt idempotency.
- **R9. Stored payloads (14.3.9).** Every contract forbids unknown fields (`CT/domain.py:16-17`). A new field on `Routine`, `Watch`, `AttentionPolicy` or `IncomingCallPolicy`, or a new attention code, needs its stored rows and the TypeScript contract (`packages/contracts/src/attention.ts`) migrated in the same change; the attention status and code columns have fixed sets (`DB/schema.py:559-561`, `CT/attention.py:13-37`).
- **R10. Paused agents and Stop.** While Stop is on, the brief and reports still run (4.8.3 keeps analysis). A paused team agent's routines stay held (4.7.1; today `DB/routines.py:108`), so its weekly report is skipped and the brief says so. A paused Lonora must not silence the brief (Q6).
