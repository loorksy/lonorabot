# Gap analysis: the user experience (chat, cards, channels, settings)

Audience: Lonora developers. Lonora was read at `/home/user/wt-agent/fxmain` (read only). Reference inputs: `ref/reports/openmausbot-ui.md` and `ref/reports/rakazo-ui.md` (their claims are taken as reported; the third-party clones were not run). Binding texts: `VISION.md` (0.4, 6, 10, 11, 12, 14.1, 17, Amendments 1-3) and `docs/cloud/DECISIONS.md` (D4, D7, D36, D37, D40, D41).

Scope: how the owner experiences Lonora in the conversation and around it: the live stream, activity lines, fixed cards and GenUI, questions, push and Telegram, agent-to-agent display, settings and first run. The agent loop, memory, proactivity triggers and multi-agent runtime have their own gap reports. This one covers only what the owner sees of them.

Effort scale: S = up to 2 days, M = up to a week, L = 1 to 3 weeks, XL = more.

## Ranked table

| # | Recommendation | Verdict | Pri | Source | Effort | Owner decision |
|---|---|---|---|---|---|---|
| 1 | Visible heartbeat plus a client idle timeout on SSE and the mobile WebSocket | adopt | P1 | both | S | no |
| 2 | One shared thread reducer and subscription state machine in `packages/core`, used by web and mobile (apply events, stop refetching on every event) | adapt | P1 | rakazo | L | no |
| 3 | Draw agent-to-agent exchanges on mobile (web already has `PeerCard`) | adopt | P1 | rakazo | S | no |
| 4 | A first run that needs no model: server-raised greeting, model-key Secret card, then the Mandate card | adapt | P1 | rakazo | M | no |
| 5 | Keep live deltas out of the root React context on web | adopt | P2 | openmausbot | M | no |
| 6 | Signal-only fan-out (Postgres LISTEN/NOTIFY), with cursor publication taken out of every client's read path | adapt | P2 | rakazo | M | no |
| 7 | Retention for `run.delta`/`run.rich_partial` rows, plus a `resumed:false` reply in the `ready` frame | adapt | P2 | both | M | no |
| 8 | Record what ended a Trade Approval card (`ended_by`) and show it on the settled line | adapt | P2 | openmausbot | S | no |
| 9 | Show the real host of agent-written links before opening them | adopt | P2 | rakazo | S | no |
| 10 | Deep link in every Telegram alert ("open in the app") | adopt | P2 | rakazo | S | no |
| 11 | Seal Secret card values in the app to the installation's key (HPKE) before TLS | adapt | P2 | openmausbot | L | yes (D4) |
| 12 | Generate the TS wire types for events, runs and owner actions from the Pydantic contracts, with server-made event fixtures | adapt | P2 | both | M | no |
| 13 | A short server-composed target on live steps ("Reading the EURUSD calendar"), redacted and capped | adapt | P3 | openmausbot | S | no |
| 14 | Two-way Telegram: replies to Telegram-originated messages go back to Telegram, cards degrade to a title plus link | adapt | P3 | rakazo | M | yes |
| 15 | Approve or reject a Trade Approval from Telegram (signed link or code) | skip | - | rakazo | M | yes (conflict) |
| 16 | Subscription sign-in UI (Claude/ChatGPT plan login, device code) | skip | - | both | L | yes (conflict, 12.2) |
| 17 | Composer or settings model picker | skip | - | both | M | no |
| 18 | Approval levels: Always allow, Allow for this session, Ask/Auto/Never plus allow/block lists | skip | - | both | M | no |
| 19 | Approval expiry (30 minutes) for unattended runs | skip | - | rakazo | S | no |
| 20 | "Stop" typed in a chat app, or a turn-cancel presented as Stop | skip | - | rakazo | S | no |
| 21 | Large generated settings index and settings dialog | skip | - | openmausbot | M | no |
| 22 | Sandboxed HTML/MCP apps inline in chat | skip | - | both | L | no |
| 23 | Web Push (service worker) | skip | - | rakazo (gap) | M | no |
| 24 | iOS Live Activities and VoIP call push | skip | - | both | L | no |
| 25 | Fixed cards with server-supplied text and trusted slots | already-better | - | both | - | no |
| 26 | Trade Approval validity: tolerance drift, no time limit, withdrawal on mode change, exact match | already-better | - | both | - | no |
| 27 | Mobile push: one push per record, receipts, nothing sensitive, tap opens the card | already-better | - | both | - | no |
| 28 | Streaming privacy: complete words only, effect claims final-only, silent background runs | already-better | - | both | - | no |
| 29 | GenUI v2 parity: server-compiled fixtures that both renderers must draw | already-better | - | openmausbot | - | no |
| 30 | Telegram linking: code typed by the owner (`owner_message_id`), forwarded text refused | already-better | - | rakazo | - | no |

None of these weakens section 6, adds a Stop control (Amendment 1), or adds a venue other than MT5 (Amendment 2).

---

## 1. What Lonora does today

### 1.1 Live transport
- **One durable owner ledger.** Every producer calls `emit()` in `packages/db/src/lonora_db/events.py`. `publish_committed()` assigns a public delivery cursor (`_ln_public_cursor`) after commit, under `pg_advisory_xact_lock(1524053101)` and a row lock on the `event_publication` setting (lines 27-61), so a late commit can never fall behind a cursor.
- **Web transport: SSE.** `GET /api/events/stream` is in `apps/api/src/lonora_api/routes/events.py`. It honours `Last-Event-ID`, sends an `event: ready` frame with the cursor, re-checks the session every 5 s and sends `": keepalive"` as an SSE comment every 10 s (line 77). `live=true` jumps a new subscriber to the current cursor, and the client then refreshes its snapshots.
- **Mobile transport: WebSocket.** `/api/ws/events` is in `apps/api/src/lonora_api/websocket/events.py`. It uses the same ledger, takes the token in the first frame and re-checks the session every 5 s. It sends no keepalive.
- **Producer side.** `packages/bus/src/lonora_bus/durable_events.py` polls `events_after()` every 0.1 s while busy and every 0.5 s when idle, for each connection. `events_after()` itself calls `publish_committed()`, so every poll from every client is a write transaction that takes the advisory lock.
- **Web client.** `apps/web/src/lib/events.ts` has exponential backoff (0.5 s to 10 s) and resumes on `online`, `pageshow` and `visibilitychange`. A 10 s timer runs only until `ready` arrives (line 57). After that there is no idle detection, and the keepalive is invisible to `EventSource` because it is an SSE comment.
- **Mobile client.** `apps/mobile/lib/events.ts` connects only in the foreground, resumes from the last consumed cursor and reconnects 1.5 s after a close. It also has a readiness timer only (line 32). Two sockets are open while a conversation is shown: the root `HeadsUp` (`apps/mobile/components/heads-up.tsx:136`, mounted in `apps/mobile/app/_layout.tsx`) and the conversation screen (`apps/mobile/app/thread.tsx:557`).
- **Retention.** No code deletes `EventRow` rows. Every streamed reply leaves one row per admitted delta (see 1.2) for ever.

### 1.2 The streaming reply
- `packages/agent-runtime/src/lonora_agent/public_stream.py` admits text only at whole-word boundaries, with at least 8 characters and 200 ms between publications. It turns streaming off for the rest of the turn if the text claims an execution (`EFFECT_CLAIM`) or leaks private names or ids.
- `stream_publication.py` coalesces provider chunks (25 ms). `progress.py` writes `run.reply_started`, `run.delta` (split at 1,024 characters) and `run.rich_partial` inside the leased transaction, and keeps a bounded preview on `RunRow.model_metadata.reply_stream` (`packages/db/src/lonora_db/streaming.py`, 60,000 characters) with turn, fence, generation and sequence.
- `docs/chat-delivery-and-stream.md` (point 10): a background run that may end silent publishes no deltas. Its reply exists only as the final message.
- **Clients.** `packages/core/src/reply-stream.ts` (shared) accumulates the stream and detects gaps. Web repairs a gap from `GET /runs/:id` (`apps/web/src/conversation/Conversation.tsx:222-235`). Mobile does the same through a scheduled snapshot.
- **Web state.** `apps/web/src/hooks/useEvents.ts` keeps the last 150 events and up to 64 streams in one `useState`, exposed by `apps/web/src/providers/ClientProvider.tsx` as a single context value. Every delta creates a new context value, so all of its roughly 40 consumers re-render.
- **Web refetching.** Every non-stream event bumps `revision`, whatever its thread, and about 37 files refetch on `revision`. The open conversation alone re-GETs artifacts, receipts, peer messages and the collaboration record (`Conversation.tsx:194-217`). A 15 s tick refetches as well.
- **Mobile refetching.** `apps/mobile/app/thread.tsx:557-640` applies `message.created`, `message.updated`, reactions and thread options in place. It still schedules a full snapshot 150 ms after every other non-stream event, plus a 15 s fallback poll.

### 1.3 Activity and tool steps
- `packages/core/src/turn-activity.ts` derives a coarse phase from real run and tool events only: preparing, thinking, searching, reading, analyzing, executing, learning, sending, writing, waiting. The tool's `toolset` and `effect` come from registry metadata, not from its name.
- `activityCallLabel()` gives each step a family label in Arabic or English (`apps/web/src/components/ai/TurnActivity.tsx`, `apps/web/src/conversation/Cards.tsx` steps card, `apps/mobile/components/turn-activity.tsx`).
- No step carries a target, so the owner reads "Analyzing", not "Analyzing XAUUSD H1".
- Dead code: `apps/web/src/components/ToolActivityDisclosure.tsx` renders raw tool names in `<code>`, which section 17 forbids in normal views. Nothing imports it. Mention only; per `CLAUDE.md` it is not deleted here.

### 1.4 Cards
- **Fixed cards (VISION 10.3).**
  - Trade Approval: `packages/db/src/lonora_db/trade_approvals.py`, `apps/web/src/components/trading/TradeApprovals.tsx`, `apps/mobile/components/trade-approval.tsx`. It stores the agent's reason, the label and the tolerance beside the request (not in the fingerprint). It drifts outside the tolerance, has no time limit for new rows, and is withdrawn on a mode change or by the agent.
  - Execution Receipt: `apps/web/src/components/trading/ExecutionReceipt.tsx`, `apps/mobile/components/execution-receipt.tsx`.
  - Secret, Mandate and Settle Uncertain Operation are owner-action kinds `secret`, `trading_mode` and `settle_operation` (`packages/contracts/src/lonora_contracts/owner_actions.py:20-28`). Settle is raised without a model by `packages/gateway/src/lonora_gateway/owner_cards.py`.
  - End states share one text table: `approvalStatusText` / `approvalEndTone` in `packages/core/src/financial-boundary.ts`. "withdrawn" is one string whatever withdrew the card. The row has no field that says who or what ended it (`TradeApprovalRow`, `packages/db/src/lonora_db/schema.py:1143`).
- **GenUI v2 ("clay").**
  - Contract and parser: `packages/contracts/src/lonora_contracts/genui.py`. Compiler from turn evidence: `packages/agent-runtime/src/lonora_agent/genui_compile.py`. Slots: `packages/db/src/lonora_db/genui_slots.py`. Closed non-financial intents: `genui_intents.py` (`ask`, `alert.create`, `alert.off`). Submission: `packages/db/src/lonora_db/genui_submit.py`, which gives every submit its own queued run and its provenance (6.10).
  - Parity is enforced by `tests/test_genui_parity.py`: server-compiled fixtures that the web validator and both renderers must draw.
  - The `LONORA_GENUI_V2` flag no longer appears in the code.
- **Questions.** `packages/core/src/thread-questions.ts`, `apps/web/src/components/conversation-question.tsx`, `apps/mobile/components/conversation-question.tsx`. A message typed while a question is pending answers it (`packages/db/src/lonora_db/messages.py:775-806`). Trade Approval rows are never answered by text. Chat never blocks: a typed message steers or queues the run.

### 1.5 Notifications, push and channels
- **Attention.** One "needs your attention" projection: `packages/gateway/src/lonora_gateway/attention.py` and `packages/db/src/lonora_db/attention.py`. It is shown by `apps/web/src/shell/domain/UpdatesPages.tsx` and `apps/mobile/app/(tabs)/updates.tsx`. Reach-me rules and quiet hours: `NotifyPages.tsx` and `notify-settings.tsx`.
- **Mobile push.** `packages/gateway/src/lonora_gateway/push.py` sends the five 11.4 kinds (`PUSH_CODES`) once per record and phone. (Since Amendment 5 there are six: Lonora's own background work, `gateway_stopped` and `model_access_failed`.)
  - The effect receipt is written before the network call, an unknown outcome is never resent, and Expo receipts are read after 15 minutes.
  - The text is fixed catalog text under the agent's name, and there is no action button.
  - A tap opens the conversation at the card (`apps/mobile/lib/push.native.ts`).
- **Web.** No browser notifications and no service-worker push.
- **Telegram.** `packages/gateway/src/lonora_gateway/event_dispatch.py` polls `getUpdates`.
  - Linking: an unpaired private chat gets a one-time code, which the owner must type to an agent (`packages/tools/src/lonora_tools/telegram.py`, gated by `owner_message_id`). Forwarded or via-bot text is dropped.
  - Outbound: only `attention.ready` items whose code is in `PUSH_CODES` (line 171), as "<agent>: <fixed text>". The text has no link, and agent replies are never sent.
  - Inbound: text reaches a conversation only if the integration has a `thread_id`. `link_chat` does not set one.

### 1.6 Agent-to-agent display
Web draws persisted peer exchanges as a `PeerCard` ("Agent collaboration", with links to both conversations; `apps/web/src/conversation/Cards.tsx:529-611`, fed by `/peer-messages`). Mobile does not fetch `/peer-messages`. It only unwraps the peer outcome text in `apps/mobile/components/message-bubble.tsx:258`, so on the phone a request between agents reads as an unattributed message.

### 1.7 Settings and first run
- **Web settings home** (`apps/web/src/shell/settings/SettingsRoot.tsx`): profile and "What I know about you", "What is running", language and theme, chat experience, accessibility, notifications, integrations (accounts, AI providers, MCP, feeds), usage, storage, files, privacy and lock. Mobile mirrors most of it under `apps/mobile/app/(settings)/`.
  - P5 lists only a few views outside conversations (Amendment 3.5 adds an Account link). By 0.4 the extra pages keep working but must not be extended.
- **First run.**
  - `POST /api/onboarding` (`apps/api/src/lonora_api/routes/onboarding.py`) creates the owner. `ensure_personal_agent()` (`packages/db/src/lonora_db/personal_agent.py:16-52`) creates Lonora and raises its Mandate card (4.3.1).
  - Nothing else is seeded. With no model key, the owner's first message fails with `model_not_configured`, and the error card offers "Open model settings" (`apps/web/src/conversation/Cards.tsx:70-95`). The Secret card for a model provider (`CredentialTarget` `model_provider`, `packages/db/src/lonora_db/secret_cards.py:60`) can only be raised by an agent, and the agent has no model yet.
- **Model key check.** After a key is saved, the provider's catalog is read and the agent is told how many models appeared (`secret_cards.py:401-408`).

### 1.8 Contract parity
- GenUI has a generated client catalog (`scripts/export_genui_catalog.py`) and parity fixtures.
- The event envelope, run, stream identity and owner-action TS types in `packages/contracts/src/*.ts` are written by hand beside their Pydantic twins.

---

## 2. What the reference projects do differently (only what bears on Lonora)

- **Liveness.**
  - OpenMausBot sends visible `ping` frames and uses a 40 s stale timer, with phases `opening/open/retrying/offline/hidden/asleep`.
  - Rakazo sends a `heartbeat` event after 20 s of silence, and the client has a 45 s idle timeout. Both ignore heartbeats for cursor purposes.
  - Lonora's keepalive is invisible to `EventSource`, and the WebSocket has none.
- **Resume.**
  - OpenMausBot's `hello` carries `resumed`. A cursor outside its replay buffer forces a full snapshot, never a partial replay.
  - Rakazo replays from the durable log and runs a three-phase recovery (snapshot, then replay with side effects suppressed, then live) in shared core code.
- **Client state.**
  - OpenMausBot keeps token deltas outside the app store in a per-thread external store read with `useSyncExternalStore`, so a delta re-renders only its own transcript.
  - Rakazo applies every event to a cached snapshot with one reducer (`reduceThreadSnapshot`) shared by web and Expo.
  - Lonora re-renders the whole provider on each delta and refetches on each durable event.
- **Fan-out.** Rakazo's `pg_notify` carries only `(topic, seq)`, and subscribers re-read rows. Lonora polls the database per connection, and each poll is a locking write.
- **Who decided.** OpenMausBot records `request.resolved.source` (user, auto, timeout, system, peer) and settles a card to a one-line outcome. Rakazo records an `approval.decided` security event.
- **Links.** Rakazo opens agent-written links through a confirm prompt that shows the real host (`markdown-link-prompt.tsx`).
- **Chat apps.** Rakazo links an account by one-time code, sends 1:1 replies and interim messages, splits long replies, caps consecutive outbound messages, and degrades cards to text plus "Answer in the app: <link>". It cannot approve tool calls from a chat app.
- **First run.** Rakazo posts a deterministic greeting, a choice card and connect cards without spending model tokens, then hands over to the lead bot.
- **Secrets on the phone.** OpenMausBot seals phone-entered secrets with HPKE to a key pinned at QR pairing.
- **Step labels.** OpenMausBot's server builds a redacted `LiveStep` target, at most 60 characters.
- **Parity.** OpenMausBot uses one protocol package with server-generated fixtures and protocol vectors. Rakazo shares core reducers and per-app e2e tests.

---

## 3. Recommendations (adopt / adapt)

### R1. Visible heartbeat and client idle timeout (adopt, P1, S)
- **What.**
  - SSE: replace the comment keepalive with a real frame (`event: ping`, no `id:`, so it never moves `Last-Event-ID`) every 15 to 20 s.
  - WebSocket: send `{"type":"ping"}` on the same period.
  - Both clients: close and reconnect after 45 s with no frame at all, reusing the existing backoff. On mobile, also reconnect on `NetInfo`/`AppState` changes.
- **Why.** A half-open TCP connection (phone moved from Wi-Fi to mobile data, laptop resumed from sleep) currently leaves the app showing "connected" while it receives nothing.
  - For Lonora this means a stale Trade Approval card (it may already have drifted), a missing Execution Receipt, and an agent status line that lies.
  - `NetworkStrip` and the "Reconnecting" phase depend on `connected`, which never turns false in this case.
- **Files.** `apps/api/src/lonora_api/routes/events.py`, `apps/api/src/lonora_api/websocket/events.py`, `apps/web/src/lib/events.ts`, `apps/mobile/lib/events.ts`. Tests: the web and Expo event specs.
- **VISION.** 10.3.1 (drift must be visible), 11.4 (reaching the owner), 17 (one plain status line built from what is really happening), D36 (the app is the product). No conflict.

### R2. One shared thread reducer and subscription state machine (adapt, P1, L)
- **What.** Move thread state into `packages/core`: an `applyThreadEvent(snapshot, event)` reducer (messages, runs, streams, reactions, thread options, owner-action and approval rows, receipts, peer rows) and a `runThreadSubscription` loop.
  - Phases: snapshot, then replay, then live.
  - Behaviour: honour the cursor, suppress side effects (sounds, heads-up) during replay, and refetch a snapshot only on a gap or on `resumed:false` (R7).
  - Web `Conversation.tsx`/`useThreads.ts` and mobile `thread.tsx` become thin adapters. The 37 `revision` consumers stop refetching on other threads' events.
  - Mobile opens one owner socket and fans it out (heads-up and thread), not one per screen.
- **Why.**
  - Today web and mobile each hand-code a different reducer: web refetches everything, mobile patches some kinds and refetches the rest. That is exactly the drift VISION 10.1.5 and 13.1 forbid.
  - D36 and Amendment 3.13 make the Android app the product, so mobile must not be the second-class copy.
  - Fewer refetches also means less load per customer VM (D1, Amendment 3.4).
- **How (adapted from Rakazo).**
  - Keep Lonora's server snapshots as the canonical repair path. Lonora's events already carry `payload.run` and full message rows, so most kinds can be applied without a GET.
  - Do not copy Rakazo's giant `if (block.kind)` chain. Use a registry keyed by event kind.
- **Files.** `packages/core/src/reply-stream.ts`, `packages/core/src/turn-activity.ts` (`projectRunEvents` already exists), new `packages/core/src/thread-snapshot.ts`, `apps/web/src/hooks/useEvents.ts`, `apps/web/src/hooks/useThreads.ts`, `apps/web/src/providers/ClientProvider.tsx`, `apps/web/src/conversation/Conversation.tsx`, `apps/mobile/app/thread.tsx`, `apps/mobile/lib/events.ts`, `apps/mobile/components/heads-up.tsx`, `apps/mobile/lib/shell-data.tsx`.
- **Test.** Replay one recorded event fixture (R12) through the reducer on both clients and compare the resulting timeline.
- **VISION.** 10.1.5, 13.1, 17 (durable runs, recovery after restarts), D36/D37. No conflict.

### R3. Agent-to-agent exchanges on mobile (adopt, P1, S)
- **What.** Move `peersByMessage` and the peer label logic from `apps/web/src/conversation/Cards.tsx` into `packages/core`. Fetch `/peer-messages?thread_id=` in `apps/mobile/app/thread.tsx`, and add `apps/mobile/components/peer-card.tsx` with the same frame as the web: who asked whom, a link to the other conversation, and the status.
- **Why.** VISION 3.2.3 (peers message each other) and 3.1.5/3.1.6 (Lonora reads and speaks for the team). The owner can see the team talking on web but not on the phone. Rakazo draws `bot_message_sent/received` rows on both clients. This is a 13.1 "mobile screen missing where web and server have it".
- **Files.** `apps/web/src/conversation/Cards.tsx`, `packages/core/src/peer-outcome.ts`, `apps/mobile/app/thread.tsx`, `apps/mobile/components/message-bubble.tsx`, new `apps/mobile/components/peer-card.tsx`.
- **VISION.** 3.2.3, 13.1, Amendment 3.13, D36. No conflict.

### R4. A first run that needs no model (adapt, P1, M)
- **What.** In `ensure_personal_agent()`, or the first owner session after it:
  - Post one fixed server greeting from Lonora (catalog text, Arabic first, no model call).
  - Raise a system `secret` card with target `model_provider`. Its fields are set by the server (7.2.3), and it links to the provider's own key page, in line with the D41 help-centre guides.
  - Keep the existing Mandate card (4.3.1).
  - When the key is saved, the existing `secret_cards.py` wake text hands over to Lonora. Lonora then runs the 9.2 broker connection in chat.
  - The `model_not_configured` error card should point at that Secret card in the conversation, not at a settings page.
- **Why.** Today the first thing a new owner sees is a failure. 7.2.1 says secrets are connected through conversation, but the only path to the first model key is a settings page, because no agent can ask without a model. Rakazo's seeded first run costs zero tokens and works before any model is connected. The acceptance scenario (16.1) starts in chat.
- **Adapted.** No focus survey and no choice card. Lonora's first run is: key, Mandate, then a chat with Lonora that connects MT5 (Amendment 2).
- **Files.** `packages/db/src/lonora_db/personal_agent.py`, `packages/db/src/lonora_db/owner_actions.py` (`raise_system_card` for `secret`), `packages/db/src/lonora_db/secret_cards.py`, `packages/bus/src/lonora_bus/attention_messages.json` or a new greeting catalog, `apps/web/src/conversation/Cards.tsx`, `apps/mobile/app/thread.tsx`, `apps/mobile/lib/i18n.ts`.
- **VISION.** P5, 4.3.1, 7.2.1-7.2.3, 12.1, 16.1, D41. No conflict.

### R5. Live deltas out of the root context on web (adopt, P2, M)
- **What.** Keep `streams` in a small external store keyed by run id or thread id, read with `useSyncExternalStore` by the transcript that shows that thread only. Take `events` out of the `ClientProvider` value, or replace it with per-thread selectors. Swap the preview for the committed message in one commit (Lonora already matches on `message_id`).
- **Why.** Every admitted delta (about 5 per second) re-renders all `useClient()` consumers, the shell included. This is the OpenMausBot `live-reply.ts` pattern.
- **Files.** `apps/web/src/hooks/useEvents.ts`, `apps/web/src/providers/ClientProvider.tsx`, `apps/web/src/lib/response_streaming.ts`, `apps/web/src/conversation/Conversation.tsx`, `apps/web/src/components/ai/TurnActivity.tsx`.
- **Priority.** P2 rather than P1 because D37 plans to switch web off for cloud customers. It stays the self-hosted client. Do it together with R2.
- **VISION.** 10.1.4 (budgets), 17. No conflict.

### R6. Signal-only fan-out (adapt, P2, M)
- **What.**
  - Run `publish_committed()` once in a single publisher: the API process, or a worker step woken by the writer's `NOTIFY`. It then sends `pg_notify('lonora_events', '<owner_id>:<cursor>')` with no payload data.
  - `stream_events()` waits on a per-process `LISTEN` connection and re-reads `events_after()` as a plain read, with a 1 to 2 s poll as fallback.
  - On a listener reconnect, wake every subscriber once to catch up (Rakazo's `notifySubscribersToCatchUp`).
- **Why.** Each open client currently runs a locking write transaction 2 to 10 times a second (`events.py:31-61`). With web, the phone's heads-up and an open conversation, that is three pollers per owner. It adds up to 0.5 s of latency when idle and costs CPU on every customer VM. Rakazo's design keeps the durable log as the truth and uses the notify only as a doorbell.
- **Keep.** The commit watermark logic that `publish_committed()` exists for.
- **Files.** `packages/db/src/lonora_db/events.py`, `packages/bus/src/lonora_bus/durable_events.py`, `apps/api/src/lonora_api/routes/events.py`, `apps/api/src/lonora_api/websocket/events.py`, `packages/gateway/src/lonora_gateway/service.py`.
- **VISION.** 17 (durable runs), Amendment 3.4 (plans limit hosting resources only, so per-instance cost matters), D1, D13. Section 6 untouched: the trading journal is separate.

### R7. Retention for live deltas and a `resumed` flag (adapt, P2, M)
- **What.** A maintenance step that deletes `run.delta` and `run.rich_partial` rows older than N days (for example 7) whose run's `reply_stream.phase` is terminal. The preview state lives on `RunRow`, and clients seed from runs, so nothing is lost.
  - Keep every other kind: the push, channel and attention cursors read `attention.ready` and `message.created`.
  - If a client resumes with a cursor older than the oldest retained row, the `ready` frame says `resumed:false`, and the client refetches snapshots instead of replaying a gap (OpenMausBot's rule).
- **Why.** Unbounded growth of one row per 200 ms of every streamed reply, for ever, inflates the database, `lonora backup` and its restore time (D10, D24). Rakazo's own report names this as its mistake.
- **Files.** `packages/db/src/lonora_db/events.py`, a new maintenance step in `packages/gateway/src/lonora_gateway/service.py`, a migration (index on kind and created_at), `apps/api/src/lonora_api/routes/events.py`, `apps/api/src/lonora_api/websocket/events.py`, `apps/web/src/lib/events.ts`, `apps/mobile/lib/events.ts`.
- **VISION.** 17, Amendment 3.4, D10. No conflict. Do not touch journal, receipt, approval or settlement records (3.1.2: never deleted).

### R8. Record what ended a Trade Approval card (adapt, P2, S)
- **What.** Add `ended_by` (`owner`, `agent`, `mode_change`, `agent_deleted`, `drift`, `conversation_deleted`) to `ln_trade_approvals`, set in `end_card`, `withdraw_own`, `withdraw_pending` and the decision path. Show it on the settled line, for example "Withdrawn: the agent was switched to Full", or "Withdrawn by the agent: its reason no longer holds".
- **Why.** Today "withdrawn" reads the same whether the owner's Mandate tap or the agent withdrew it. OpenMausBot's `source` field makes the settled outcome honest and auditable. 5.3.3 (never claim what did not happen) and 10.3.1.3 (each ending is distinct) are better served with the cause on screen.
- **Guard.** This is a column on the approval row, outside `TradeRequest`. `trade_fingerprint`, the operation id and the exact-approval match (6.2, 6.7, 14.3.9) are unchanged.
- **Files.** `packages/db/src/lonora_db/trade_approvals.py`, `packages/db/src/lonora_db/schema.py` plus a migration, `packages/core/src/financial-boundary.ts`, `apps/web/src/components/trading/TradeApprovals.tsx`, `apps/mobile/components/trade-approval.tsx`, the i18n catalogs.
- **VISION.** 10.3, 10.3.1.3, 5.3.3, 17. Section 6 preserved.

### R9. Show the real host of agent-written links (adopt, P2, S)
- **What.** For `[label](https://host/...)` where the label is not the host, either render the host after the label, or ask once on tap ("Open broker-login.example?"), on web and mobile. Bare URLs stay as they are.
- **Why.** Agents read third-party pages, feeds and peer messages (6.10). A disguised "[log in to your broker](https://phish)" in an otherwise trusted agent bubble is the cheapest attack on a trading owner, and 9.2 says broker passwords go only into the Secret card. Rakazo confirms links this way.
- **Files.** `apps/web/src/conversation/Markdown.tsx:72`, `packages/chat-ui/src/markdown.web.tsx:25`, `apps/mobile/components/markdown.tsx:34`.
- **VISION.** 6.10 (third-party content is data), 9.2, 7.2. No conflict.

### R10. Deep link in Telegram alerts (adopt, P2, S)
- **What.** Append to each Telegram alert a link that opens the conversation at the card: the app scheme (`brand.scheme` in `apps/mobile/app.config.ts`) or the installation's web URL, with the same `thread_id` and `around` the push uses.
- **Why.** Today the owner reads "<agent>: a trade waits for your approval" in Telegram and has to find it in the app by hand. The link only opens the fixed card, which reads the live record. It never approves anything (6.7, 6.10), and it carries nothing sensitive (the same rule as `push.py`).
- **Files.** `packages/gateway/src/lonora_gateway/event_dispatch.py` (the `outbound` built at line 219), `packages/gateway/src/lonora_gateway/push.py` (reuse `push_record` for `around`), `apps/mobile/lib/push.native.ts` or the Expo linking handler.
- **VISION.** 11.4, 6.10. No conflict.

### R11. Seal Secret card values on the client (adapt, P2, L, owner decision)
- **What.** Each installation holds an X25519 key pair. The app pins the public key when it connects by QR (Amendment 3.6 hosting hook) and seals Secret card values with HPKE before sending. The server opens them only in `secret_cards.py` and writes them to the encrypted store as today. Web uses the same envelope with the key served from its own origin (weaker, but it does no harm).
- **Why.** D4 proposes Cloudflare-proxied TLS, so Cloudflare would see broker passwords and model keys in plain text at the edge. Amendment 3.3 and D7 promise that the operator side cannot access an installation. OpenMausBot seals phone-entered secrets to a pinned key for the same reason. This makes the promise hold even with a TLS-terminating edge.
- **Owner decision.** It is entangled with D4 (Proposed) and D30. If the owner picks DNS-only plus Caddy, the value is smaller.
- **Files.** `apps/mobile/components/owner-action-card.tsx`, `apps/web/src/components/owner-actions/OwnerActionCard.tsx`, `apps/api/src/lonora_api/routes/owner_actions.py`, `packages/db/src/lonora_db/secret_cards.py`, `packages/security/` (cipher), `apps/mobile/app/server.tsx` (pinning).
- **VISION.** 7.2.6, Amendment 3.3 and 3.6, D4, D7, D30. No conflict with section 6. It is a hosting hook, so per Amendment 3.6 it must be additive and must not change agent behaviour.

### R12. Generated wire types and event fixtures (adapt, P2, M)
- **What.** Extend the `scripts/export_genui_catalog.py` pattern: export JSON Schema from `lonora_contracts.events`, `runs`, the stream identity and `owner_actions`, and generate `packages/contracts/src/*.ts` from it. A test fails when the hand-written and generated types differ. Record a server-made event sequence (stream, tool steps, card raised, decided, receipt) as a fixture and replay it through the R2 reducer on web and Expo.
- **Why.** The Python server and two TS clients drift today wherever GenUI's generated catalog does not reach. Both references pin parity with one source: OpenMausBot's protocol package and vectors, Rakazo's Zod contracts.
- **Files.** `scripts/export_genui_catalog.py` (pattern), new `scripts/export_contracts.py`, `packages/contracts/src/events.ts`, `runs.ts`, `owner-actions.ts`, `tests/fixtures/`, `tests/web/`, the Expo e2e.
- **VISION.** 10.1.5, 13.1, D36. No conflict.

### R13. A target on live steps (adapt, P3, S)
- **What.** On `tool.started`, the server adds a short `target` taken only from validated, non-secret arguments: symbol, timeframe, account login label, file name. It is at most 60 characters and goes through `redact()` (already called in `progress.py`). The step label becomes "Analyzing · XAUUSD H1".
- **Why.** Section 17 asks for a plain status line built from what is really happening. "Analyzing" alone says little to a trader. OpenMausBot's `LiveStep` shows that a server-built, redacted target is safe on any client.
- **Never.** The target must never carry tool ids, JSON or raw names (17), and never a secret (7.2.6).
- **Files.** `packages/agent-runtime/src/lonora_agent/progress.py`, the tool registry metadata in `packages/tools/`, `packages/core/src/turn-activity.ts`, `packages/core/src/agent-status.ts`.
- **VISION.** 17, 7.2.6. No conflict.

### R14. Two-way Telegram (adapt, P3, M, owner decision)
- **What.** When the owner writes from the linked Telegram chat, route the message to Lonora's conversation (or an @mentioned agent; 3.2.5) and send that run's final reply back to the same chat. Split long replies, and cap consecutive outbound messages as Rakazo does.
  - Cards degrade to their title plus the R10 link.
  - Secret, Trade Approval, Mandate and Settle are never answerable in Telegram.
  - Execution Receipts and reports stay in the app (11.4 says they do not push). Telegram replies are only answers to the owner's own Telegram messages.
- **Why.** 11.4 allows the owner to enable other channels. Inbound already exists but is unreachable after linking, because `link_chat` sets no `thread_id`. The owner gets no answer where they asked.
- **Owner decision.** The current code deliberately limits Telegram to push-coded alerts ("Telegram carries the events that push (11.4), nothing else", `event_dispatch.py`). Sending conversation text to Telegram moves owner data to a third party. That is the owner's call.
- **Files.** `packages/gateway/src/lonora_gateway/event_dispatch.py`, `packages/db/src/lonora_db/telegram_pairing.py`, `packages/channels/src/lonora_channels/telegram/runtime.py`, `packages/adapters/src/lonora_adapters/channels/telegram.py`.
- **VISION.** 11.4, 3.2.5, 6.10 (Telegram text is owner input to judgement, never an approval). No conflict with section 6.

---

## 4. Skips and conflicts

| # | What | Why not |
|---|---|---|
| 15 | Approve or reject a Trade Approval from Telegram (Rakazo's own report suggests a signed single-use link) | 10.3 makes Trade Approval a fixed card in the app. 6.10 says no other element can stand in for a fixed card. 6.7 binds approval to the exact row. A Telegram text or link-click outside the app is a second approval surface. **Conflict: owner decision only.** R10's link to the in-app card covers the need without it. |
| 16 | Subscription sign-in (OpenMausBot `ClaudeSignIn`/`codex login`/ChatGPT PKCE; Rakazo `PiOAuthLogins`, `SubscriptionSignInSteps`) | 12.1/12.2 allow API keys only and prohibit subscription logins, OAuth tokens and reuse of vendor CLI client ids. See `ref/reports/policy-subscription-signin.md` (Anthropic forbids it for third-party products; OpenAI's hosted path is partner-only). **Conflict: needs an owner amendment to 12.** Until then, keep BYOK and the D41 guides. |
| 17 | Model picker in the composer or settings (OpenMausBot `ModelPicker.tsx`, Rakazo `composer-model-picker.tsx`) | 12.3 and 10.3.2 (`agent_model` becomes the owner's typed message). P5 says chat is the control surface. Lonora's `AgentModelCard` already shows the current choice. |
| 18 | Always allow / Allow for this session / Ask-Auto-Never with allow and block lists | 4.1 allows exactly two modes, and P1 allows no caps or lists. 10.3 Trade Approval is Approve or Reject only. Full via the Mandate card is the "always". |
| 19 | 30-minute expiry of unattended approvals | 10.3.1.3: a card has no time limit and ends only by decision, drift or withdrawal. |
| 20 | "stop" typed in Telegram, or a turn cancel labelled Stop | Amendment 1 removes every Stop control. Lonora's pauses (4.6, 4.7) and the Mandate card are the owner's controls. Pausing an agent from chat already works. |
| 21 | Generated settings index and a large settings dialog (OpenMausBot) | P5 lists the only views outside conversations (plus the Amendment 3.5 Account link). By 0.4 the existing extra pages must not be extended. New settings go to chat. |
| 22 | Sandboxed HTML or MCP Apps inline in a reply | 10.1.1: one design system, and agents never write CSS. 6.10 provenance. Lonora already has an isolated viewer for files (`apps/web/src/components/SandboxedHtmlViewer.tsx`). |
| 23 | Web Push via a service worker | D36/D37: the Android app is the product and web is a fallback. 11.4 requires mobile push through Expo, which exists. Not worth building for a client that will be switched off for cloud customers. |
| 24 | iOS Live Activities, VoIP incoming-call push | D40: iOS comes later. Revisit with the iOS build. |

---

## 5. Where Lonora is already ahead

- **Fixed cards with server-supplied content (10.2, 10.3).** In OpenMausBot widgets and Rakazo blocks, the model can lay out anything, approvals are a separate card type, and a widget cannot hold an approval. Lonora lets the agent place a fixed card as a trusted slot. The server supplies every word and button, and the agent cannot hide or restyle it. GenUI intents are closed and non-financial (`genui_intents.py`), and a submit gets its own run with provenance.
- **Trade Approval validity.**
  - Lonora: exact `operation_id` plus fingerprint match, the agent's reason labelled as the agent's words, tolerance from the executable side, drift detection with a fixed wake, no clock, and withdrawal on a mode change.
  - Rakazo's card text is built from resolved arguments too, but it offers "Always" and expires unattended cards.
  - OpenMausBot defaults bots to Full access.
- **Push.**
  - Lonora (`push.py`): one push per record and phone across restarts and gateways, the receipt written before the send, no resend on an unknown outcome, Expo receipt checks, catalog text only, and a tap that lands on the card position.
  - OpenMausBot's Android push was not live. Rakazo has receipts but no once-per-record rule across restarts.
- **Streaming privacy.**
  - Lonora: `PublicStream` admits whole words only, turns streaming off on any execution claim or private id (5.3.3), and background runs stream nothing (11.5).
  - Rakazo holds transient progress for silent runs. OpenMausBot streams everything.
  - Lonora also matches the references on stream generation, sequence and fence with gap repair (`reply-stream.ts`).
- **GenUI parity mechanism.** `tests/test_genui_parity.py` compiles server fixtures that the validator and both renderers must draw. This matches OpenMausBot's fixture approach and is stricter than Rakazo's convention.
- **Telegram linking.** The code must appear in the owner's own typed message (`owner_message_id`, at most 160 characters). Forwarded and via-bot text is dropped, and outbound carries only fixed alert text. Rakazo's link code has no forwarded-text rule.

---

## 6. Notes and limits

- Both reference reports describe code I did not run. Their numbers (heartbeat 20 s, idle 45 s, stale 40 s) are taken from those reports.
- I did not measure render cost or database load. R5 and R6 rest on reading the code paths (one context value per delta; a locking write per poll), not on profiles.
- I did not read the whole of `apps/web/src/conversation/Conversation.tsx` or `apps/mobile/app/thread.tsx`. The statements about them come from the event and refetch sections quoted above.
- Proactivity triggers, the morning brief, memory and the agent loop are covered by the sibling gap reports. This report treats only their surfaces: attention, push, Telegram, peer cards.
