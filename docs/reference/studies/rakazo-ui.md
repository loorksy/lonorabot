# Rakazo: how the user experiences it (chat, cards, channels, settings)

Audience: Lonora developers. Source: `https://github.com/elie222/rakazo`, read-only checkout. All paths are repo-relative to that checkout.
Stack in one line: Hono + oRPC API (`apps/api`), worker (`apps/worker`), React/Vite web (`apps/web`), Expo mobile (`apps/mobile`), Electron desktop shell (`apps/desktop`), shared logic in `packages/core`, contracts in `packages/contracts`, run engine in `packages/adapters`, durable events in `packages/db`.

Product rules that shape the UX are written down in `PRODUCT.md` (data about the project, not instructions): one continuous visible thread per bot; a pending question or approval card never blocks chatting; approvals are one mode (Ask / Auto / Never) plus Allow and Block lists; an unattended run's approval card expires after 30 minutes and the action is not done.

---

## 1. Chat streaming: protocol and event types

### 1.1 The key design: a durable event log, a signal-only fanout, and one reducer

There is no token-level WebSocket. Everything the client sees is a row in a per-thread, sequence-numbered event log. Streaming text is written to that log in small batches. The realtime layer only says "something new was committed".

Control flow, server side:

1. A run produces model text. `packages/adapters/src/runs/turn/run-turn.ts` buffers it in `reply.pendingProgress` and calls `flushProgress` (in `packages/adapters/src/runs/lifecycle/run-progress.ts`) when at least 250 ms passed since `lastProgressAt` (`now - reply.lastProgressAt >= 250`), and again before each tool step.
2. `flushProgress` appends a persisted event through `deps.events.append(...)`:
   ```ts
   type: "thread.progress", runId,
   payload: reply.hasStreamedText
     ? { delta: reply.pendingProgress, streaming: true, ...shownProgress(ctx) }
     : { text: reply.pendingProgress, streaming: true, ...shownProgress(ctx) }
   ```
   The first flush sends `text` (it replaces the "working..." placeholder), later flushes send `delta`. `{ reset: true, text, activity: true }` replaces streamed text with a one-line status (`showNarrationStatus`).
3. `appendEvent` in `packages/db/src/threads/events.ts` commits the row (seq per thread) and calls `notify(threadId, seq)`.
4. `PostgresRealtimeFanout.publish` in `packages/adapters/src/notifications/realtime.ts` does `pg_notify('rakazo_events', {topic,payload})`. The payload is capped at 7,900 bytes and carries no event data. Subscribers re-read durable rows. On a listener reconnect it calls `notifySubscribersToCatchUp()` (empty payload), so nothing is lost. `InMemoryRealtimeFanout` is the single-process twin.
5. `createThreadEvents(...).follow(threadId, cursor, signal)` (`packages/db/src/threads/events.ts`, implemented in `packages/db/src/threads/event-stream.ts`) is an async generator: events with seq greater than `cursor`, then waits on the fanout.
6. The oRPC procedure `threads.subscribe` (`packages/contracts/src/threads/threads-rpc.ts`, input `threadTarget + {cursor}`, output `eventIterator(ProductEventSchema)`) is implemented in `apps/api/src/routes/threads.ts` (`subscribe: authed.threads.subscribe.handler(async function* ...)`). It wraps `follow` in `withHeartbeats` (`apps/api/src/routes/shared.ts`), filters events of peer and background runs (`shouldForwardPeerThreadEvent`, `shouldForwardBackgroundThreadEvent`), and yields.
7. Transport is Server-Sent Events over oRPC (`accept: text/event-stream`). `withHeartbeats` emits a `heartbeat` event (seq 0, never persisted) after `HEARTBEAT_MS = 20_000` of silence and re-checks the session every `SESSION_RECHECK_MS = 10_000`, ending the stream with `UNAUTHORIZED` if the session was revoked.

### 1.2 Event types

`packages/contracts/src/threads/events.ts` defines `ProductEventType` (excerpt of the thread-facing ones):

```
thread.message.created  thread.message.updated  thread.cleared  thread.message.reaction
thread.progress  thread.artifact  thread.ask  thread.choice  thread.meta
thread.computer  thread.subagent  thread.cloud_agent  thread.call.ended
run.started  run.steering.claimed  run.checkpointed  run.waiting_input
run.completed  run.failed  run.cancelled
agent.tool.called  agent.tool.completed  effect.recorded  effect.reconciled  usage.recorded
computer.status  computer.takeover.{requested,granted,released}  computer.command
routine.*  memory.revised  skill.*  bot.*  group.*  heartbeat
```

Envelope (`ProductEventSchema`): `{id, spaceId, threadId, botId, seq, type, runId?, createdAt, payload}`. A superRefine only validates the coarse "thinking" activity marker: `ThreadActivityPayloadSchema = {activity:{thinking:boolean}}` with a comment "Never accepts provider reasoning content or partial messages". So reasoning text is deliberately not streamed to clients.

A second, per-user stream `notifications.subscribe` carries `alert | roster | <space change kinds> | organizations | heartbeat` (`threads-rpc.ts`, handler in `apps/api/src/routes/account.ts`). `roster`/`runs`/`routines` events only mean "refetch that list".

### 1.3 Client side: one shared reducer, two transports

1. `packages/core/src/threads/thread-subscription.ts` `runThreadSubscription` owns recovery for every app: `loadInitial`/`loadHead` get `{threadId, cursor}`, a snapshot is refreshed in the background with 250 ms to 5 s backoff, then `subscribe(cursor)` is opened. Phases `snapshot -> replay -> live` mean events between a cached snapshot and the head are replayed from storage with UI side effects (sounds, notifications) suppressed. `IDLE_TIMEOUT_MS = 45_000` of total silence means half-open, so reconnect. 4xx answers (401 session gone, 426 build retired) stop retries; 429 honors Retry-After.
2. `packages/core/src/threads/thread-snapshot-events.ts` `reduceThreadSnapshot(prev, event)` applies one event to the snapshot (ignores `event.seq <= prev.cursor`, appends progress, upserts messages, updates the run). `isThreadSnapshotEvent` lists the types that matter. `reduceLiveMessageBlocks` in `packages/core/src/messages/events.ts` builds the live bot message from `thread.progress` and `agent.tool.called` events:
   - `progress` blocks are the streaming tail, `{kind:"progress", text, activity?, shown?, pendingToolNames?}`;
   - a tool call waits in `pendingToolNames` until the sentence ends (`endsSentence`), then becomes a step segment, so a tool row never splits a sentence.
3. Web: `apps/web/src/pages/shell/chat/use-thread-sync.ts` (`useThreadSync`) wires `runThreadSubscription` to `rpc.threads.subscribe`, keeps a per-chat cached snapshot for instant reopen, coalesces refreshes (`createRefreshCoalescer`), snaps scroll to the end only if the reader has not scrolled (`transcript-scroll`), and feeds browser notifications.
4. Mobile: `apps/mobile/lib/api/api-live.ts` `subscribeThread` calls `subscribeRpcEvents("threads/subscribe", ...)`, a hand-written SSE reader over `fetch` (React Native has no EventSource). It splits frames on a blank line, caps a frame at `MAX_MOBILE_RPC_RESPONSE_BYTES`, ignores `heartbeat` frames (so they do not advance the cursor), and gives up after `IDLE_TIMEOUT_MS`. `apps/mobile/lib/thread/thread-live.ts` `useThreadLiveSubscription` runs it only while the app is in the foreground, resumes from the last applied event, and uses the same `reduceThreadSnapshot` and `runThreadSubscription` from `@rakazo/core`.
5. The final reply is not the progress text. On finish `finalizeRun` (`packages/db/src/threads/events.ts`) writes a durable `thread.message.created` with typed blocks; the reducer's `clearLive` drops the live progress for that run. If a run fails, `partialReply` keeps what the user already saw as a bot message.

Not found: no token-by-token WebSocket, no resumable server-sent "partial message" object, no reasoning stream. Latency floor of streaming is the 250 ms batching plus the database round trip.

---

## 2. How tool calls and progress are shown

- Data: `agent.tool.called` / `agent.tool.completed` events (live), then a durable `steps` block on the final message: `{kind:"steps", steps:[{label, count, note?, outcomes?:{succeeded,failed,stopped}}], durationMs?}` (`packages/contracts/src/threads/message-blocks.ts`). Per-call details are kept separately in tool history (`ToolHistorySchema`) and gated for privacy (`apps/api/src/threads/tool-history-privacy.postgres.test.ts` exists).
- `showsAsLiveStep(name)` in `packages/core/src/messages/events.ts` filters which tools appear live at all.
- Narration policy is server side (`run-progress.ts`): text the bot writes before a tool call becomes (a) a durable interim chat message if the budget allows (`canPublishDurableProgress`, `USER_PROGRESS_MESSAGE_MAX_LENGTH`, only on genuinely long turns, capped per run), or (b) a `note` on that step. Browser/desktop tasks may post an early "this takes minutes" heads-up (`canPostLongTaskHeadsUp`). Routines, webhooks and tickets keep transient progress private (`holdsTransientProgress`) so a silent run leaks nothing; silent-allowed runs hold back a possible `NO_RESPONSE` sentinel (`progressHeldForSilence`).
- Web rendering: `apps/web/src/components/messages/ToolActivityDisclosure.tsx` (`ToolSteps`, `ToolActivityDisclosure`): a collapsible card, open while the run is live and folded afterwards, with a window of `LIVE_TOOL_STEP_WINDOW = 6` latest rows and "+N earlier steps", a pulsing glyph for the current row and a check for done rows.
- The tool card is off by default. `apps/web/src/lib/chat/tool-activity-preference.ts` stores `rakazo.showToolActivity`; "Only a saved 'on' shows tool cards... so chats stay clean". `apps/web/src/lib/chat/tool-activity-view.ts` `shouldRenderToolCard`: only a `steps` block renders and only when the preference is on; `progress` blocks with `activity:true` never render in either mode. `isToolOnlyNarration` renders a tool-only bot message as slim lines instead of a bubble.
- Subagents: `thread.subagent` events and a `subagent` block `{agentId, name, task, status: running|completed|failed, progress?, result?}` rendered by `apps/web/src/components/messages/SubagentCard.tsx`; `settleRunSubagents` closes them when the run ends. Cloud coding agents: `cloud_agent` block and `CloudAgentCard.tsx`. Child bots: `child_bot` block.

---

## 3. Generative UI and rich cards

There is no free-form "render arbitrary component" protocol. Rich UI is a closed set of typed message blocks (`MessageBlock` discriminated union in `packages/contracts/src/threads/message-blocks.ts`), each with a hand-built web and mobile renderer.

Block kinds: `text`, `card` (key/value lines), `ask`, `choice`, `app_connect`, `connect`, `computer`, `voice_call`, `call_request`, `meta`, `routine_event`, `delivery`, `progress`, `steps`, `subagent`, `child_bot`, `cloud_agent`, `skill_draft`, `mcp_approval`, `import_setup`, `image`, `file`, `app`, `tool_question`, `page`, `handoff`, `channel_message`, `bot_message_sent`, `bot_message_received`, `chart`.

Web dispatch is one long `if (block.kind === ...)` chain in `apps/web/src/pages/shell/chat/message-view.tsx`; cards live in `apps/web/src/components/messages/` and `apps/web/src/pages/shell/chat/message-cards.tsx`. Mobile mirrors it in `apps/mobile/components/cards/` (`AskActions`, `ChoiceCard`, `ComputerCard`, `McpApprovalCard`, `OutgoingDraftCard`, `ToolQuestionCard`, `AppConnectCard`, `ImportSetupCard`, ...).

The three "generative" pieces:

1. Charts. `chart` block: `{name, spec, data}`, the spec being a declarative Observable Plot spec validated by the `render_plot` tool before publish; `MAX_CHART_DATA_ROWS = 5_000` enforced by a `superRefine`. The model writes JSON, never code (`packages/adapters/src/runtime/pi/tools/pi-runtime-tools.ts`, `render_plot` description).
2. Pages and HTML artifacts. `page` block `{pageId, version}` points to a saved page; `apps/web/src/components/messages/SandboxedHtmlViewer.tsx` renders agent HTML in an iframe with `PREVIEW_CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: ..."`, a link-blocking guard and form submit disabled. Diagrams: Mermaid in `packages/chat-ui/src/mermaid.ts` with security tests.
3. MCP apps. `app` block `{artifactId, server, tool, toolArguments, toolResult, csp?, prefersBorder?}` rendered by `McpAppCard.tsx`: an iframe at `MCP_APP_VIEWER_PATH` with opaque origin, CSP built from the server's declared domains (`mcpAppCsp`, `mcpAppDocument` in `packages/core`), lazy load near viewport, 15 s start timeout after which the card is hidden and the text reply stands. The app can only ask the host for two things after a user gesture: open a link (through the confirm dialog) and put text in the composer. It cannot call tools.

Markdown is shared in `packages/chat-ui` (`markdown.web.tsx`, `markdown.native.tsx`, tables, copy, link-confirm prompt `markdown-link-prompt.tsx`).

---

## 4. In-chat approvals and questions

### 4.1 Kinds of card (all are the `ask` block unless noted)

- Conversational question with options: the `ask_user`-style builtin (`packages/adapters/src/tools/builtin-conversation.tool-definition.ts`: "Ask the user one short multiple-choice question with tappable options... they can still type their own"). Options carry letters (`askOptionLetter`) so typing "B" means option B (`packages/core/src/asks/ask-kind.ts`).
- Tool approval: `approvalEffectId` set, actions `allow` / `always` / `deny` (`buildApprovalAskBlock` in `packages/adapters/src/approvals/approval-ask.ts`; `isApprovalAskBlock` / action ids in `packages/core/src/runs/action-approval.ts`). The card text is built "from what was resolved before the effect was recorded, not from what the model typed", secrets redacted, bounded (`MAX_APPROVAL_SUMMARY_LENGTH = 500`, `MAX_APPROVAL_DETAIL_LENGTH = 4_000`). Variants: outgoing draft (Send / Discard), routine edit with before/after fields (`routineUpdate`), payment receipt (`receipt`), instruction diff with undo (`instructionUpdate`), settings change with undo (`settingsUpdate`). `onceOnly` hides "Always allow" for purchases and explicit-approval tools.
- Secret request: `input:"secret"`, purposes `otp|password|api_key`, login fields, one-time code, "dismissed" state (`SecretAskCard.tsx`, mobile `secret-ask-sheet.tsx`). Never implicitly dismissed by a chat message.
- `tool_question`: an MCP server asks the user something while a call waits (elicitation); answer is sealed to a one-time public key, only the run's own user can answer, otherwise `expired`.
- Computer takeover request: `computer` block, plus `computer.takeover.*` events.

### 4.2 Control flow: pause, answer, resume

1. The tool gate (`packages/adapters/src/runs/tools/run-tool-gate.ts`) decides an effect needs approval; the run calls `deps.events.pauseRunForInput` (`packages/adapters/src/runs/turn/run-turn-pause.ts`), which posts the card and sets the run to `waiting_input`. `publishNarrationBeforeAsk` first posts the text the bot wrote before asking, whole, so the user can answer.
2. For an unattended run (routine, webhook, ticket, another bot) `scheduleApprovalExpiry` (`packages/adapters/src/approvals/approval-expiry.ts`) enqueues a job in the same transaction; `expireApprovalCard` later answers `deny` with `expired:true` if still unanswered. A run someone watches keeps its card open indefinitely.
3. The client answers with `threads.answer` (`threads-rpc.ts`: `{answer, clientNonce?, username?, fields?, dismiss?}` with a refine requiring either an answer or a dismissal). `answerRunInput` in `packages/db/src/threads/thread-ask.ts` commits the answer, marks the block `status:"answered"` with `answerMessageId`, appends events, records a security event `approval.decided`, wakes the run.
4. Which cards are tappable is computed client side by `answerableAskMessageIds` (`packages/core/src/asks/answerable-ask.ts`): an `ask` is answerable only if its run is `waiting_input` and belongs to this user; a `tool_question` while its run is `running`. Secret asks are dismissable only by the run's user.
5. Typing instead of tapping: `retireWaitingQuestionInTransaction` treats a new user message as the answer to a pending plain question. It refuses to do so for secret or approval cards ("Never implicitly dismiss credentials or authorize an external effect").
6. Chat never blocks: the user can send new messages while a card is pending. `QUEUE_HOLDING_RUN_STATUSES` excludes `waiting_input` ("A pending card holds no compute"). Steering (a message sent while a run is working) is claimed by the running turn (`claimSteering` in `packages/db/src/threads/thread-steering.ts`, event `run.steering.claimed`) except for runs that "carry their own prompt" (`NON_CONVERSATIONAL_RUN_TRIGGERS` in `packages/core/src/runs/run-state.ts`).
7. Stop: `apps/api/src/threads/thread-stop.ts` cancels runs, settles stopped helpers' cards and tears down computer work; the same stop is reachable by texting "stop" in any of 20 languages from a chat app (`packages/core/src/messaging/messaging-commands.ts`).

Settings that decide when cards appear: Approvals page (`apps/web/src/components/settings/ApprovalRulesSettings.tsx`, mobile `apps/mobile/app/(settings)/approvals.tsx`, `approval-rule-add.tsx`). Policy semantics are in `PRODUCT.md` (Ask / Auto / Never, Allow and Block lists, auto-review model in `packages/adapters/src/approvals/auto-review.ts`).

---

## 5. Notifications and outside channels

### 5.1 In-app and push

- Run alerts are classified `completion | failure | help | takeover`; `chatAlertNeedsAttention` is true for the last three (`packages/contracts/src/threads/thread.ts`).
- `packages/adapters/src/runs/lifecycle/run-notifications.ts` `notifyRun` / `deliverChatNotice`: honors the bot's `notifyOnFinish` and a routine's own `notify` flag; completion goes to every Space member, but questions, takeovers and failures go only to the run's user; snoozed chats still receive questions/takeovers/failures; background ticket runs notify only for help/takeover.
- Fan-out to open apps: `publishChatAlert` -> `notifications.subscribe` stream. Fan-out to phones: `packages/adapters/src/notifications/expo-push.ts` (Expo push API, retries on 429/5xx, receipts job after 15 min, title 100 / body 180 chars, payload under 3,300 bytes, sender avatar), `push-token-store.ts`, `apns-activity.ts` (iOS live activity for work in progress), `calls/apns-voip.ts` + `incoming-call-push.ts` (incoming voice calls).
- Mobile registration: `apps/mobile/lib/notifications/push.ts` `registerPushToken` -> `rpc("notifications/registerPush", {token, presentation})`; opening a notification routes via `notification-open.ts`; badge `app-badge.ts`; Android sender-avatar presentation uses a native module.
- Web/desktop: `apps/web/src/pages/shell/use-browser-notifications.ts` + `apps/web/src/lib/platform/browser-notifications.ts` (`deliverBrowserNotification`: only when the page is hidden or unfocused, deduped by event id, permission state machine "pending/delivered/discarded"). Desktop badge via `rakazoDesktop.badge.set` (`apps/web/src/lib/platform/use-desktop-badge.ts`).
- Not found: no Web Push (no `PushManager` or `push` listener anywhere; `apps/web/src/pwa/sw.ts` registers only caching/standalone behavior). A closed browser tab never gets an alert; only mobile push and chat apps reach a user who is away.

### 5.2 Chat apps as a channel

Platforms mounted when their env settings are present (`packages/adapters/src/messaging/messaging-platforms.ts`, `messagingPlatforms`): `sendblue` (iMessage, SMS, RCS), `slack`, `teams`, `whatsapp`, `telegram` (plus named extra Telegram bots `telegram-<name>`), `lark` (Feishu), `photon` (iMessage). User-facing names: `packages/core/src/messaging/messaging-providers.ts`. Email: `packages/adapters/src/email/` handles inbound email to a bot (`inbound-email.ts`) and transactional/lifecycle mail (`lifecycle-email.ts`, kinds `model-connection` and `agent-import` only). There is no email or SMS run-completion notification; SMS exists only through sendblue as a messaging identity.

Inbound flow:

1. A webhook or poller hands an event to `apps/api/src/messaging/messaging-inbound.ts` (1,650 lines; intake/settle in `apps/api/src/messaging/intake/` and `packages/adapters/src/messaging/intake/settle-inbound.ts`).
2. The sender must be a linked `messagingIdentity`. Linking is a one-time code pasted into the chat app (`tryRedeemLinkCode`; Slack uses workspace install instead, `messagingConnectOptions` returns `method: "install" | "link"`).
3. Only in the owner's verified 1:1 chat, exact commands are parsed (`parseMessagingCommand`): `YES`, `NO`, `LEAVE`, and "stop" in many languages. `YES/NO` answer the latest prompt about connection requests and channel invites (`applyOwnerCommand`), not tool approvals. Anything else is a normal message that becomes a `thread.message.created` in the same bot thread and wakes a run with trigger `messaging`.
4. Outbound: `packages/adapters/src/messaging/messaging-delivery.ts` sends the run's bot messages through a job queue (`messagingSendJob`, claim and backup job, `MESSAGING_SEND_TIMEOUT_MS = 60_000`, `MESSAGING_DM_OUTBOUND_CAP = 140` consecutive DMs without a reply, long replies split by `markdown-split.ts`). A 1:1 chat-app run sends interim messages immediately (`publishInterimMessage` with `deliverRun(..., {progress:true})`); otherwise replies are sent when the run ends. Group chat posts once at the end.
5. Cards in chat apps are degraded to text: `chatAppAskText` (`packages/core/src/asks/chat-app-asks.ts`) renders a pending question as numbered options plus "Answer in the app: <link>"; approvals, secrets and instruction changes keep only their title because "only its card can answer it, and its detail can hold a command, a diff or tool input". So tool approvals can not be granted from Telegram/Slack/WhatsApp in this codebase. A takeover request becomes "(Take over the screen in the app.)".
6. Shared channels: privacy blocks (`messagingChannelPrivacyBlock`, `nonOwnerChatPrivacyBlock`) stop the bot leaking owner memory in groups; posts are attributed "<name>'s agent". Team chat bridge (`apps/api/src/messaging/team-chat-bridge.ts`, `packages/adapters/src/messaging/team-chat/`) lets several bots share a channel with a judge model deciding whether to reply (`team-chat-judge.ts`).
7. Settings UI: `apps/web/src/pages/settings/MessagingSettingsPanel.tsx` (link status, polls link state every 3 s `LINK_POLL_MS`, pending invites and connection requests via `messagingRequests` in `packages/core/src/messaging/messaging-requests.ts`), mobile `apps/mobile/app/(settings)/messaging.tsx`.

### 5.3 Bot to bot

Bots talk through the same message log, not a separate bus: `bot_message_sent` / `bot_message_received` blocks with intent `request|result|question|status|fyi`, run trigger `bot_message`, a hop counter (`BOT_MESSAGE_MAX_HOPS`, `nextBotMessageHop`, imported by `packages/adapters/src/messaging/messaging-delivery.ts` from `packages/core/src/bots/`), and `thread.subagent` for delegated work. The UI shows them as slim attributed rows in the thread (`message-view.tsx` branches for `bot_message_*`, `handoff`, `child_bot`).

---

## 6. Parity: web, desktop, mobile

- One logic layer, three shells. `@rakazo/core` (reducers, ask logic, subscription recovery, model/provider helpers, call logic) and `@rakazo/contracts` are imported by web and mobile alike; only renderers and transports differ (DOM `ChatMarkdown` vs `markdown.native.tsx`; browser SSE vs the hand-written fetch SSE reader).
- Desktop is the web client in Electron plus a typed bridge `window.rakazoDesktop` (contract type `RakazoDesktop` from `@rakazo/contracts`, exposed in `apps/desktop/src/preload/preload.cjs`): clipboard, badge, locale, menu commands, passkey rpIds, `oauth.open/cancel` loopback capture, `computer.requestAccess/revokeAccess` (this computer as the bot's computer, `apps/desktop/src/main/this-computer/`), `device.setAllowed`, server change, local stack (`local-stack.ts`) for self-hosting. `apps/web/src/lib/platform/desktop.ts` `desktopBridge()` returns `undefined` in a browser, so features degrade by presence checks.
- Mobile-only capabilities: push and live activities, CallKit-style incoming calls, widgets, watch targets (`apps/mobile/ios-widgets`, `ios-watch`, `ios-watch-complications`, `ios-intents`), native calendar bridge (`threads.nativeCalendar*`), haptics, store review nudge.
- Mobile settings screens map nearly one to one to web (`apps/mobile/app/(settings)/models.tsx`, `model-connection.tsx`, `model-picker.tsx`, `voice.tsx`, `approvals.tsx`, `messaging.tsx`, `memory.tsx`...). Where web uses overlays, mobile uses routes and sheets (`secret-ask-sheet.tsx`, `run-error-sheet.tsx`).
- Parity is enforced by shared tests (`*.test.ts` in core) and per-app e2e (`apps/web/e2e`, `apps/mobile/e2e`, `apps/desktop/e2e`), not by a single codegen. Gaps exist by design: the screen takeover card is app-only; OAuth auto-capture is desktop-only (browsers show a paste-code step).

---

## 7. Onboarding and first run

1. Web route `/onboarding` (`apps/web/src/pages/onboarding/Onboarding.tsx`): loads `rpc.me()` and `rpc.models.list()`, then goes to `survey` (if `needsSignupSurvey`), `model` (if `needsModel`), or `bot`.
2. Model step (`model-step.tsx` + `use-onboarding-model.ts`): provider select (popular first), subscription sign-in or API key, model pick, save; then `bot`.
3. First bot: `rpc.onboarding.firstBot()` -> `ensureFirstBot` in `apps/api/src/account/first-bot.ts`. It reuses a bot named "Chief" (spawnKey `FIRST_BOT_SPAWN_KEY`) or creates it only if the person's own Spaces never held a chat (`hasChatHistory` looks across Spaces with `runAsSystem`). It then runs `introduce` (an intro run that asks what the bot is for when a model is set) and `promptFocus`, both best-effort and ordered so only one opener appears.
4. Deterministic seeded conversation, zero model tokens: `apps/api/src/account/onboarding.ts` posts a greeting, a `choice` block with four focus options (day-to-day, inbox, research, everything), then `app_connect` cards for the matching apps. Choosing calls `onboarding.choose`; authorizing an app calls `onboarding.appConnected`. Focus never renames the bot.
5. A lifecycle email reminds people who stalled before connecting a model (`model-connection`) or importing an agent (`agent-import`), at most one mail per 24 h (`LIFECYCLE_EMAIL_GAP_MS`).
6. An `ask` action id `agent-import` opens the agent importer instead of answering (clients hide it where there is no importer).

---

## 8. Settings: providers and models

### 8.1 Model roles and picker

- Roles: `main`, `approval`, `computer` (`packages/contracts/src/models/model-roles.ts`). Each has `primary` plus ordered `backups`; `ModelRoleViewSchema` adds `deploymentPrimary`/`deploymentIncluded` (what runs when the member chose nothing, and whether the deployment pays) and `seesImages`.
- Account defaults with a per-Space override (`scope: SettingsScope`), per PRODUCT.md: "a space customizes one only as a deliberate exception".
- Catalog entry (`ModelCatalogEntrySchema` in `packages/contracts/src/models/model-connections.ts`): `provider, id, label, billing, auth: api-key|oauth|both, subscription, subscriptionName, signIn: device-code|auth-url, signInSetup {label,url,note}, reasoning, thinkingLevels, images, contextWindow, maxTokens, recommended, managed, live, endpointPresets, routingFields (account/gateway/project ids)`. Live provider lists merge with a bundled catalog (`packages/adapters/src/runtime/pi/models/pi-live-catalog.ts`, `pi-catalog-availability.ts`, `pi-codex-catalog.ts`).
- Popular providers first: `POPULAR_MODEL_PROVIDER_IDS = ["openai-codex","anthropic","openai","openrouter","google"]` (`packages/core/src/models/model-providers.ts`); `pickCatalogModelId` preselects saved, then recommended, then first.
- Thinking level is clamped to what the model supports (`clampCatalogThinkingLevel`).
- Web surfaces: Models overlay (`apps/web/src/pages/model-settings/ModelSettingsOverlay.tsx`, `providers-section.tsx`, `provider-page.tsx`, `ModelRoleSettings.tsx`, `role-model-picker.tsx`), one model's own settings (`model-settings-panel.tsx`), chat picker (`apps/web/src/pages/shell/chat/chat-model-picker.tsx`: searchable Command list, grouped, older models collapsed, "Connect" entry at the end) and an opt-in composer picker (`apps/web/src/pages/shell/composer/composer-model-picker.tsx`, off by default and kept per device; absent in group chats because each bot may use another model, per PRODUCT.md). A bot's model can also be changed from chat, producing an `ask` with `settingsUpdate {before, after}` and an undo.

### 8.2 API key vs subscription sign-in

Two connection types share one list:

1. API key: `models.connect` with `ModelConnectInputSchema` (key at least 8 chars, optional routing ids, optional endpoint headers). `models.probeCatalog` / `probeOpenAiCompatible` list models for a key before saving. OpenAI-compatible endpoints have presets, protocol choice (chat or Anthropic Messages) and a data-retention control.
2. Subscription (ChatGPT via provider id `openai-codex`, Claude via `anthropic`): OAuth, implemented in `packages/adapters/src/runtime/pi/models/pi-oauth.ts` (`PiOAuthLogins` with `begin/submit/complete/finish/cancel`, 1,272 lines) with two flows:
   - ChatGPT device code (`pi-chatgpt-device-code.ts`, `createChatGptDeviceCodeLogin`): POST to `auth.openai.com/api/accounts/deviceauth/usercode`, show `userCode` and `verificationUri`, poll the token endpoint at the provider interval, `slow_down` adds 5 s, code TTL 15 min, rides out 5xx and 408/429 (the stock flow gives up on the first 5xx).
   - Claude authorization URL with PKCE (`pi-anthropic-oauth.ts`, `createManualAnthropicOAuthLogin`): authorize URL on `claude.ai/oauth/authorize`, redirect either to `http://localhost:53692/callback` (desktop captures it) or to Anthropic's code page (everyone else pastes a `code#state`); `state` is the PKCE verifier and a mismatch aborts. Both use public client ids of the vendors' own CLIs (named, not copied).
   - RPC sequence (`apps/api/src/routes/models.ts`): `beginOAuth` -> client shows step UI -> device mode: client polls `completeOAuth` every 5 s (`waitForModelOAuthCompletion` in `packages/core/src/models/model-oauth.ts`, timeout = expiry + 60 s) / auth-url mode: `submitOAuthCode` -> `finishOAuth` saves the credential and optionally makes it the default (`makeDefault`, `scope`) -> `cancelOAuth` with a reason for measurement.
   - Client UI: `apps/web/src/lib/models/use-model-oauth-signin.ts` (`useModelOAuthSignIn`, handles desktop loopback capture via `onDesktopOAuthCallback`, paste fallback, cancel and restart guards, step analytics `reportSignInStep`) and `apps/web/src/components/models/SubscriptionSignInSteps.tsx`, a `Stepper`: optional provider-side setting step (`signInSetup`), "Get a sign-in code", then either "Enter this code at <host>" with a "Copy code and open" button and "Waiting for you to sign in", or "Sign in at <host>" and "Paste the code it shows you". Detail: "The provider's page opens only from the user's click, after the code it needs is on screen" (browsers block popups opened after an await).
   - Token upkeep: `pi-credentials.ts`, `model-auth-resolution.ts` (refresh when less than 5 minutes valid, `MIN_OAUTH_VALIDITY_MS`; terminal refresh errors such as `invalid_grant` mark the credential failed and retire it), `model-credential-refresh.ts`.
3. Deployment-managed models: `managed` entries and `deploymentPrimary` let a hosted install pay for the default model; "credits" funding is a separate `creditOfferingId` (`packages/adapters/src/models/credits/`).
4. Provider allowlist per deployment: `model-provider-allowlist.ts` + `assertModelProviderAllowed` in the route.
5. Settings screens list: `apps/web/src/pages/settings/settings-nav.ts` (General, Models, Approvals, Vault, Wallet, Memory, Voice, Messaging, Computers, Labs, Usage, Billing, Spaces, Organization, Updates; some only when the deployment offers them). Provider setup follows PRODUCT.md: provider, one short description, only required fields, everything optional behind one "Advanced" disclosure.

---

## 9. Voice

- Calls: web `apps/web/src/lib/calls/call-session.ts` (`startCall`, `endCall`, `useCallSession`) reuses the same thread subscription (`runThreadSubscription` + `reduceThreadSnapshot`), so a call is the chat spoken aloud: user speech is sent as a normal user message with a call nonce (`callClientNonce`), bot text is sliced into speech as the run streams (`createCallReplySpeech`, `speechFromBlocks`), `thread.call.ended` ends it. Echo and barge-in logic is pure core code (`packages/core/src/calls/echo.ts`, `barge-in.ts` with interrupt words in several languages, `farewell.ts`). Approval or secret asks during a call are spoken as decisions (`spokenDecision`, `pendingCallSecretAsk`); secrets are never dictated in a call.
- Speech input: browser SpeechRecognition or server transcription (`dictation.ts`, `usesServerDictation`, `desktop-speech.ts`), hold-to-talk in the composer (`apps/web/src/pages/shell/composer/hold-to-talk.tsx`), consent dialog before audio leaves the device (`voice-consent.ts`, `AiDataConsentDialog.tsx`).
- Speech output and providers: `packages/adapters/src/voice/voice-providers.ts` lists `macos, elevenlabs, openai, cartesia, fish-audio, xai, openrouter, openai-compatible, scripted`; settings in `apps/web/src/pages/settings/VoiceSettingsOverlay.tsx` and mobile `apps/mobile/app/(settings)/voice.tsx`. A bot setting `autoSpeak` and `voiceId` can be changed from chat.
- Bot-initiated calls: `call_request` block, `call-request.ts` with a cooldown and ring seconds, `notifications.subscribeCalls` stream (`incoming.calls`), VoIP push for iOS (`apns-voip.ts`), `IncomingCall.tsx`, mobile `apps/mobile/lib/calls/incoming-calls.ts`.
- Not found: no phone-number (PSTN) calling or SMS voice in this tree under the topic searched; calls are app-to-bot audio.

---

## 10. What Lonora should copy / avoid

Lonora context: always-on assistant for MetaTrader 5, FastAPI server and worker, React web and Expo mobile, a lead agent "Lonora" plus agents the owner creates.

### Copy

1. A durable per-thread event log with a monotonic `seq`, a signal-only realtime fanout, and a client cursor. It makes reconnects, mobile backgrounding and multi-device identical. In Python: an `events` table, `LISTEN/NOTIFY` (or Redis pub/sub) that carries only `thread_id, seq`, an SSE endpoint that replays `seq > cursor` then waits. Add the heartbeat (20 s) plus client idle timeout (45 s) so half-open sockets die quickly, and re-check authorization on a timer so a revoked token ends the stream.
2. One shared client reducer. Put `reduceThreadSnapshot`-style logic in a shared TypeScript package used by the React app and Expo app, plus the three-phase recovery (snapshot, replay with effects suppressed, live). It removes web/mobile drift.
3. Batch streamed text at about 250 ms and persist the batches, instead of a separate ephemeral channel. Mark which text is the user-visible reply (`shown`) and keep tool narration as a note on a step. Hold back text in silent runs (routines, watchers) so an agent that decides to say nothing leaks nothing; this matters for always-on trading agents.
4. Typed block union as the "generative UI". A closed set (`text`, `ask`, `choice`, `steps`, `chart`, `page`, `file`, `subagent`, `bot_message_*`) validated by schema on both sides is safer than arbitrary UI code. Charts as a declarative spec with a row cap and server-side validation before publish fits market data. Sandbox any agent HTML (iframe, `default-src 'none'`, no network) as `SandboxedHtmlViewer.tsx` does.
5. Approval cards built by the server from resolved arguments, not from model text; secrets redacted; a `once-only` flag for dangerous classes; before/after diffs with an Undo for settings and instruction changes. For Lonora trade approvals show symbol, side, size, price, SL/TP and risk as resolved fields, bind the answer to the exact effect id, and never offer "Always allow" for orders.
6. The state machine "pending card holds no compute; chat is never blocked": `waiting_input` status, `answerableAskMessageIds`, typed text answers only plain questions and never approvals or secrets. Adopt the 30-minute expiry that denies by default for unattended runs; for trading it should deny and tell the owner (push) rather than silently expire.
7. Notification policy by kind: completion to everyone, question/failure/takeover only to the run owner, snooze that lets attention kinds through, per-bot and per-routine notify flags. Mobile push with an Expo receipt check job and a sender avatar so the owner can tell which agent is speaking.
8. Chat-app channel done conservatively: link by one-time code, owner commands only in the verified 1:1 chat and only exact words (YES/NO/STOP in several languages), cards degraded to text with a deep link, interim messages sent immediately in 1:1, a send claim plus backup job and a consecutive-outbound cap. A Telegram "stop" for Lonora's trading agents is high value: copy `parseMessagingCommand` + `stopOwnerWork`.
9. Model settings: roles with primary plus backups, account default with per-Space exception, popular providers first, clamp thinking level to the model, subscription sign-in as a stepper whose browser window opens only from the user's click. Copy the device-code flow's tolerance for transient 5xx and the PKCE `state` check. Keep the public client ids out of docs and make the sign-in provider-allowlisted per deployment.
10. Deterministic first run: a server-seeded greeting with a choice card and app-connect cards costs no model tokens and works before a model is connected. For Lonora: seed "connect MT5 account", "set risk limits", "choose model" as cards, then hand over to the lead agent.
11. A bridge object for desktop features with presence checks (`desktopBridge()`), so the same web build runs in a browser.

### Avoid

1. Do not persist one database row per streamed delta forever. Rakazo writes `thread.progress` rows for every 250 ms batch; they are projected away once the final message arrives but still cost writes. Use a TTL or a separate unlogged table for live deltas, keep only the final message and tool steps durable.
2. Do not copy the 1,650-line inbound handler and 1,548-line delivery module shape; split intake, identity, commands, delivery. Do not copy the giant `if (block.kind === ...)` chain in `message-view.tsx`; use a registry keyed by block kind shared by web and mobile.
3. Do not make approvals impossible outside the app if the owner is away from the app and a position is at risk. Rakazo's chat apps cannot approve tool calls (only "Answer in the app"). For Lonora, allow a one-tap approve/reject for trade approvals from Telegram via a signed, single-use, expiring link or a short code bound to the effect id, while keeping the rule that text read from market news or another agent never authorizes anything.
4. Do not rely on browser notifications only. Rakazo has no Web Push, so a closed tab hears nothing. Lonora should add Web Push (service worker `push` handler) or accept that mobile push and Telegram are the only away channels, and say so in onboarding.
5. Do not hide all tool activity by default for a trading product. Rakazo keeps tool cards off to keep chats clean. For Lonora the owner needs an always-visible execution trail (what order was sent, what the broker answered). Show a compact receipt block per effect regardless of the preference.
6. Do not stream reasoning to clients (Rakazo is right to refuse it), but do show a coarse activity phase such as monitoring, analyzing, waiting for broker.
7. Do not expose provider OAuth for third-party consumer subscriptions as the only path. The flows reuse the vendors' CLI client ids, which can break or violate terms at any time; keep API keys as the supported path and mark subscription sign-in as best-effort with clear failure copy.
8. Do not put the whole onboarding behind a model connection. Rakazo's route order (survey, model, bot) means no value before a model works; Lonora should let the owner see a demo or paper account first.
9. Parity is by convention here (shared core plus per-app renderers plus e2e). Without a contracts package generated from one schema (Zod here), Lonora's Python server and two TS clients will drift; generate TS types from FastAPI's OpenAPI or Pydantic models and test block rendering with the same fixtures on web and mobile.

### What the code does not do (so Lonora does not assume it)

- No token-level or reasoning streaming; no WebSocket; no Web Push; no email/SMS run notifications; no tool approval from chat apps; no PSTN calling; no generic server-driven UI beyond the closed block set and sandboxed HTML/MCP apps.
- Proactivity (agents that start work unprompted) is not a UI feature here; it comes from routines, webhooks, tickets and bot-to-bot messages that create runs with `routine/webhook/tickets/bot_message` triggers, surfaced as ordinary chat messages and alerts (see `RUN_TRIGGERS` in `packages/contracts/src/runs/runs.ts`). The runtime side of that is covered by other reports.
