# OpenMausBot: the user experience (chat, cards, channels, settings)

Audience: Lonora developers. Repo studied read-only: `milind-soni/OpenMausBot`. All paths are repo-relative. Where a feature does not exist in the code, this report says so.

Short version: OpenMausBot is a local-first Node server plus a React renderer (web, Electron desktop, installable phone web app) plus a native phone companion whose app source is NOT in this repo (only its Node-side companion and protocol). One SSE stream carries every live update to every client. There is no Telegram, WhatsApp or SMS bot channel; Slack exists only as a Cloud-team ingress; push is APNs/FCM through a control-plane worker; email exists for sign-in codes and "away" digests. Proactivity is deliberately limited to explicit triggers (routines, webhooks, waits, auto mode), not a heartbeat.

## 1. Chat streaming: one SSE stream, a replay buffer and a cursor

### 1.1 Transport (server)
1. Client opens `GET /api/events?since=<cursor>&window=1&frames=thread[&screens=off]` (built by `liveEventsUrl()` in `src/lib/live-events.ts`).
2. `server/index.ts` (route `method === "GET" && path === "/api/events"`) builds an `SseClient`, starts `openSseHeartbeat()` (`server/sse-fanout.ts`, period `SSE_HEARTBEAT_MS`), writes headers `content-type: text/event-stream`, `x-accel-buffering: no`.
3. It prefers the `Last-Event-ID` header over `?since=` ("EventSource reconnects with a newer Last-Event-ID while the URL keeps an older ?since=").
4. It decides `resumed`: the cursor must be inside `replayBuffer` (`replayBuffer.covers(since, lastSeq)`), the per-bot frame table must be resumable, and for team members no audience change may have happened after the cursor. Otherwise `resumed:false` and the client must re-hydrate (no partial replay "would leave a permanent hole").
5. First frame is always `{kind:"hello", cursor:"<STREAM_ID>:<seq>", resumed}`. If resumed, buffered frames newer than `since` are replayed, filtered per client by `wants()`, `teamOwners.reaches()` and `streamFor()`; admins get the full frame, others a `clientFrame` (a redacted variant per audience).
6. Frames are all `data:` lines of JSON with a `kind`; there is no named SSE `event:`. Heartbeats are visible `ping` frames because browsers hide SSE comments from `EventSource`.

### 1.2 Transport (client)
1. `openLiveEvents()` in `src/lib/live-events.ts` owns the connection. It tracks `cursor` and a `snapshotGeneration`.
2. On `hello` with `resumed === false` it calls `onSnapshotRequired()` (the store's `hydrate()` plus `publishMissedFrames()`, `forgetLiveTurns()`), and commits the new cursor only after that resolves true.
3. Stale detection: `LIVE_EVENTS_STALE_MS = 40_000`; retry backoff 500 ms to 10 s; phases `idle|opening|open|retrying|offline|hidden|asleep` (`LivePhase`). It holds the connection while the page is hidden or offline and does not reconnect to a sleeping Cloud home (reconnecting would wake it; `src/lib/cloud-power.ts`).
4. `src/state/store.tsx` (`onFrame` inside the live effect) queues frames (`store.enqueueFrame`) and dispatches each `kind` in a big switch.
5. Remote clients tunnel the same stream through the relay: `src/lib/relay-server.ts` supplies a `relayEventSource` with the same interface.

### 1.3 Frame kinds (`ServerFrame`, `packages/phone-protocol/src/wire.ts`, re-exported by `shared/wire.ts`)
`hello`, `message`, `message.patch`, `thread` (active leaf), `bot`, `group`, `notify`, `notifications.read`, `group.deleted`, `routine`, `routine.run`, `webhook`, `app-trigger`, `runtime`, `screen`, `computer`, `computer-control`, `bot.queued`, `live.call`, `device.job`, `config`, `theme`, `apps-catalog`, `window-pref`, `bots.order`, `sections`, `companion.endpoints`, `mcp.changed`, `cli-login`, and more. Server state (bots, threads, routines) rides as whole-object patches; only live turn activity rides as `runtime`.

### 1.4 Runtime events (the token/tool stream)
`runtime` frames wrap a `RuntimeEvent` (`packages/phone-protocol/src/runtime-events.ts`), a normalised union across all engines (Claude Code, Codex, ACP agents, OpenAI-compatible, Pi):
- lifecycle: `session.started`, `session.exited`, `turn.started`, `turn.retrying`, `turn.completed`, `cap.exhausted`, `turn.wait_started/ended`
- items: `item.started`, `item.updated`, `item.output` (tool stdout), `item.completed` with `itemType` `tool | assistant_text | assistant_image`
- text: `content.delta` with `streamKind: "assistant_text" | "reasoning_text"` and an optional `botId` for room replies
- asks: `request.opened` (`requestType: "permission" | "question"`, `tool`, `summary`, `choices`, `questions`, `allowSession`, `requiresExplicitApproval`) and `request.resolved` (`behavior: allow|deny|answer`, `source: user|auto|timeout|system|unavailable|peer`)
- misc: `thread.token-usage.updated`, `runtime.error`, `runtime.notice`, `context.compacted`, `context.summarizing`
- a live-only `turn.progress` (`packages/phone-protocol/src/turn-progress.ts`): `{activity: write|edit|command|web|read|fetch|search|tool, target, detail, bytes, quiet}`; "never written to the event log or the message log".

### 1.5 How the client draws a streaming reply
1. `store.tsx` `case "runtime"` calls `spokenReplyStream.onRuntimeEvent` (TTS) and `runtimeFrameAction(frame.event)` (reducer).
2. Text deltas are NOT put in the app reducer. `src/state/live-reply.ts` (`noteLiveReplyEvent`) holds each thread's streaming items outside React state and exposes them through `useSyncExternalStore`, "so a delta re-renders only the transcript that shows that thread". A streamed item stays drawn until the saved `message` with the same id arrives, so the swap is one commit (`savedAs`, `itemId`).
3. If the stream restarted without its missed frames (`gapped`), deltas are skipped until the next item or turn boundary, because an item open across the gap lost its start.
4. `src/state/turn-status.ts` (`noteTurnEvent`) keeps a per-thread `TurnLive {turnId, ended, status}` where `status.activity` is `thinking|reply|summarizing` or a tool activity. This drives the single "working line".
5. Durable messages arrive as `message` (new) and `message.patch` (update in place; used for cards and widgets). Wire message `kind` values: `text | options | activity | screen | connector | secret | signin | routine.run | goal.run | burst | digest | compaction | call | widget | app` (`WireMessage` in `wire.ts`).
6. Optimistic send and queued messages: `src/state/optimistic-send.ts`, `src/state/queue-receipts.ts`, `src/components/ComposerQueuedMessages.tsx` (a second Enter within `DOUBLE_ENTER_STEER_WINDOW_MS = 1_500` steers the running turn). Server side `bot.queued` frames carry the queues.

## 2. Tool calls and progress

1. Each tool call becomes an activity message with a `WireTool` (`packages/phone-protocol/src/wire-tool.ts`): `name, ok, summary, input, output, step (LiveStep), whose, itemId, fullResult`, plus error-row extras (`claudeUpdate`, `limitResetsAt`, `place`).
2. While running, the working line shows the server-made `LiveStep` (target at most 60 chars, redacted twice, "never an environment variable's value or a credential"). `src/lib/tool-step-label.ts` maps tool names (`bash`, `read`, `grep`, `websearch`, ...) to localized verbs (`toolStep.runCommand`, `toolStep.readFile`, ...); `src/lib/friendly-activity.ts`, `src/lib/now-steps.ts` build the "Now" card.
3. `src/components/NowCard.tsx` renders steps with marks done/failed/now. `src/components/ToolActivity.tsx` renders the chip; opening it lazily fetches the full clipped output ("kept once it arrives, asked again after a failure").
4. Output is clipped in conversation pages and fetched on demand; secrets are redacted before they ever reach the wire (`shared/redact.ts`).
5. `src/components/ChatActivity.tsx` is the Advanced-mode switch for whether routine updates and finished tool entries show in the chat (kept per device). There is a simple mode that hides them (`src/lib/interface-mode.ts`, `src/lib/simple-only.ts`).
6. A "quiet" notice appears when a long call has sent no output (`StepQuiet`: output time, or network/busy/idle from process inspection), and a `first-reply-rescue` notice when the model has said nothing for a while (`packages/phone-protocol/src/first-reply-rescue.ts` via `WireTool.rescue`).

## 3. Generative UI and rich cards

Three layers, from safest to most open:

1. **Cards (`kind:"options"`)**: server-authored, typed, answerable. One message with `card` data and a `requestId`: approvals, questions, routine/skill/profile/model requests, sign-in, credential, setup, share, connector. Renderers: `ApprovalCard.tsx`, `AskCard.tsx`, `PendingApproval.tsx`, `SignInRequestCard.tsx`, `src/components/keys/` etc. The types live in `packages/phone-protocol/src/*-request.ts`, `options-card.ts`, `setup-card.ts`, `connector-card.ts`, `share-card.ts`.
2. **Widgets (`kind:"widget"`)**: a bot calls `show_widget` with a JSON tree (ChatKit-style node names). `packages/phone-protocol/src/widget.ts` normalises model input once and refuses oversize input with the path of the problem: `WIDGET_LIMITS` = 32 000 bytes, 250 nodes, depth 10, 60 table rows, 100 chart rows, 4 chart series, etc.; icons are a fixed list (`WIDGET_ICON_NAMES`). Every platform renders only canonical trees (`src/components/widget/WidgetNodes.tsx`, `WidgetChart.tsx`, `WidgetTable.tsx`, `WidgetFields.tsx`, ...). A press is not an RPC to the bot: `src/components/widget/widget-send.ts` `sendWidgetAction()` POSTs to `/api/bots/:id/messages` with `{sendId, widgetAction:{messageId, ref, rev, values, other}}` ("a press is a reply on the existing send route"). `sendId` makes retries idempotent; `rev` makes stale presses refusable.
3. **Apps (`kind:"app"`)**: HTML in a sandboxed `srcdoc` iframe (`sandbox="allow-scripts allow-forms"`, opaque origin) speaking the MCP Apps bridge. Design spec: `docs/superpowers/specs/2026-10-14-chat-apps-design.md` (bot HTML via `show_html`/`update_html`, MCP servers with `_meta.ui.resourceUri`; the server builds the frame document and CSP; one shared host module for desktop and phone web views; v1 is inline only, not in rooms; older channels get a text fallback).
4. Charts and tables from data: `dataResult` on a message (`kind: table|chart|text`), `shared/data-surface.ts`, `src/components/widget/WidgetTable.tsx`.

## 4. In-chat approvals and questions

### 4.1 Approval (permission) path
1. The engine driver reports a native permission request. The harness emits `request.opened {requestType:"permission", tool, summary, command?, allowSession}` and persists an `options` message with `card.requestId`, `card.tool`. Secrets-bearing fields (`command`, `commandLine`, `reads`) are "never broadcast".
2. The server may answer without the person: Full-access level, a saved exact command, narrow built-in allowances, or the bot reading its own files (`docs/approval-levels.md`; `server/drivers/chat-tool-approval.ts`, `codex-approval-config.ts`; safety floor in `docs/verification/safety-floor.md`).
3. Otherwise the card shows. `pendingApprovals(messages)` in `src/components/PendingApproval.tsx` selects unanswered, undismissed, unexpired option cards that have a `tool`.
4. `PendingApprovalActions` offers Allow, Deny, "Always allow" (saves `alwaysAllow` on the bot, with the grant saved BEFORE the bot is released), "Allow for this session" (`allowSession`), "Remember this command" (owner/admin only, exact command + cwd), and Cancel turn.
5. Click dispatches `decideRequest` (`src/state/store.tsx`), which first waits for pending execution-settings flushes, optionally saves the grant, then `POST /api/threads/:id/respond {requestId, behavior, message?, always?, rememberCommand?, reviewedSha256?}` (`server/routes/bot-messages.ts`). A failed grant save stops the response "so work never resumes under a stale approval level".
6. The harness emits `request.resolved {source: user|auto|timeout|system|unavailable|peer}`; the card settles into a one-line outcome (`approvalCardOutcome`).
7. Approvals notify (kind `approval`) in every thread, even bot-opened ones; clicking a notification opens the exact thread.

### 4.2 Question path
1. Claude's `AskUserQuestion` or a harness tool becomes `request.opened {requestType:"question", questions[]}`; shape in `packages/phone-protocol/src/ask-question.ts` (1 to 6 questions, 2 to 12 options, `multiSelect`, free-text up to 2000 chars unless `custom:false`).
2. `AskCard.tsx` draws header, choices chips, a free-text reply, and a settled line (`AskSettledTone`: done, closed, stopped, expired). Dismiss sends `QUESTION_DISMISS_MESSAGE` ("Use your best judgment and continue.").
3. Question cards are durable: they survive reload and a parked root waits on them with no clock (`docs/runtime-contract.md`: "a root parked on the person's cards has no clock at all").

### 4.3 Handoff and secret cards
- Sign-in handoff (`kind:"signin"`): the bot asks the PERSON to sign in to a website in the bot's own browser; OpenMausBot never receives the password (`packages/phone-protocol/src/sign-in-request.ts`). Routes `server/routes/sign-in-cards.ts` (`done|cancel|save-login|use-login`); `need: sign_in|captcha|payment|approval|other`; cards expire (`expiresAt`).
- Credential request (`kind:"secret"`): `request_credential` shows a secure card; the value goes straight to a route (`server/routes/secret-cards.ts`: `/provide`, `/save`, `/use`) and is "never echoed back, logged or added to the card". The agent chooses only a target id from `CREDENTIAL_TARGETS` in `packages/phone-protocol/src/credential-request.ts`, never a config path or field name. On a phone the secret is sealed with HPKE (`phone-secret-envelope.ts`) pinned to the QR.

## 5. Notifications and outside channels

### 5.1 Policy and wire
1. The harness owns interruption policy. `server/notify.ts` (`buildNotification`, `buildMentionNotification`, `unaskedBotThread`) returns `null` when a bot has notifications off, when a `done` has an empty body, or when the thread was opened by another bot and the person has not spoken in it.
2. Kinds (`packages/phone-protocol/src/notification.ts` `NotifyKind`): `approval, question, done, routine-failed, routine-deferred, turn-failed, incident, sign-in, secret, delegation-settled, mention, spend, brief, wait, notice`. Each carries `botId` AND `threadId`; a click must select the bot and switch to that task (`docs/notification-and-proactivity-qa.md`).
3. Delivered as a `notify` frame on the SSE stream and also logged in a feed (`notifications.read` frame marks entries read when a conversation opens).
4. Titles are localized server lines (`server/server-lines.ts`, keys `server.notify.*`), and summaries strip fenced code and Markdown (`summarize()` 140 chars).

### 5.2 Surfaces
- Browser: `src/lib/notify.ts` (`requestNotificationPermission` must be called from a click; preferences in `src/lib/notification-preferences.ts`; suppressed when the window has focus).
- Desktop (Electron): `electron/desktop-notifications.mjs` shows the notification from the main process, because a page's own `new Notification` dies with the page and clicks after a reload do nothing; main routes the click back to the right "place" (origin) and waits up to 2 minutes for a sleeping Cloud to open.
- Phone push when the app is closed: `server/phone-push.ts` (+ `phone-push-admin.ts`), `packages/phone-protocol/src/phone-push.ts`, control-plane worker `cloudflare/control-plane/src/push.ts`, `push-fcm.ts`, `push-activity.ts`, `push-cloud-homes.ts`; docs `docs/phone-push.md`. APNs on iPhone; Android FCM was not live at the time of that doc ("Android does not have push yet"). Cloud homes relay through the Admin. On a Team Cloud each person's phone gets only what that person's own stream would carry (`pushReaches`), and iOS Live Activities are not offered there.
- Without push, the phone builds notifications from live `notify` frames: while the app is open, about 25 s after backgrounding on iPhone, or always on Android with Always-on (`docs/phone-push.md`).
- Email: `server/email.ts`, `server/email-code.ts`, `server/sign-in-mail.ts` (sign-in codes), `cloudflare/control-plane/src/email.ts`, and an "away emails" setting (`src/components/AwayEmailsSetting.tsx`). Not an agent conversation channel.
- Slack: only as a Cloud-team ingress (`server/team-slack.ts`, `docs/team-slack.md`): the Admin receives Slack events, opens a session for the member who wrote, POSTs `/api/slack/team/messages` to the Cloud, and gets a signed report back (`teamSlackSignature`, HMAC over `omb-team-slack-v1`). The Slack bot token never reaches the machine. This is a request/answer bridge, not a push channel.
- Telegram, WhatsApp, SMS: NOT PRESENT as channels. Grep hits are (a) the README's description "a Telegram-style chat app", (b) reaction emoji naming in `packages/phone-protocol/src/reactions.ts`, (c) the chat-apps spec line "Old clients and channels (Slack, Telegram) read a text fallback", and (d) agent PHONE tools that open the phone's own messages/WhatsApp compose sheet and send only when the person taps Send (`server/phones/instructions.ts`, `server/phones/tools.ts`). I found no Telegram/WhatsApp/SMS server code.
- Voice calls to the user (outbound phone): not found.

### 5.3 Proactivity (explicit, not a heartbeat)
- `docs/notification-and-proactivity-qa.md` states the rule: "proactivity as an explicit trigger, not as a hidden heartbeat... no background polling that invents work".
- Triggers: routines (`server/routines.ts`, `docs/routine-schedules.md`), webhooks (`server/webhook-address*`, `shared/webhooks`), app events from Composio (`cloudflare/composio-broker/src/app-events.ts`, `server/app-events.ts`), waits (`wait_until`, `packages/phone-protocol/src/wait-request.ts`), check-backs (`shared/check-back.ts`, `server/host/` check-back services), calendar calls, and auto mode within an active task.
- One built-in proactive routine, "Keep an eye on my day", owned by one `proactiveOwner` bot (`docs/proactive-routines.md`, `server/host/proactive-owner.ts`): it posts one brief card a day into a fixed chat, and notification kind `brief` opens that chat.
- Anti-spam: a bot-opened thread sends no "Finished" until the person speaks in it; `done` with an empty result stays quiet.

## 6. Parity: web, desktop, phone

1. One renderer (`src/`, Vite/React) serves browser, the Electron shell (`electron/`) and the installed phone web app (`docs/phone-web-app.md`: Home Screen install, "does not add offline chat, push notifications or native phone computer control").
2. The native phone app (iOS and Android store apps) is not in this repo. What is: the wire contract `packages/phone-protocol/` ("shared by server, UI and desktop"), the Node-side `companion/` (pairing, E2E Noise sessions, yamux, relay client, default-deny route policy in `companion/src/routes.ts`), `relay/`, and docs (`docs/ios-companion.md`). iOS tests are referenced in docs (`ios/Tests/...`) but the `ios/` folder is not in the checkout.
3. Pairing: QR from Settings → Devices; transports: hosted HTTPS, Tailscale, local, relay ("Anywhere", end-to-end encrypted). Per-device trust with revocation. `src/lib/phone-pairing.ts`, `src/lib/companion-pairing.ts`.
4. The phone gets: bot and room lists, paged transcripts, sending, interruption, unread, approvals and questions with "always allow", resumable SSE and streamed text, secure credential cards, Markdown. Closed-app push and voice were not in the first iOS version (`docs/ios-companion.md`, "Current status").
5. Parity mechanism: server-side normalization so every renderer gets canonical data (widgets normalised once; phone fixtures generated by the server; `scripts/capture-companion-fixtures.mjs`; `companion/src/e2e/vectors/v1.json` protocol vectors).
6. Desktop-only: browser pane, computer control, native notifications via main, OS-level voice dictation; VPS SSH viewer is desktop-only.
7. Frames are filtered by audience: the same stream gives members a `clientFrame` and admins the full frame.

## 7. Onboarding and first run

1. `src/components/onboarding/WelcomeGate.tsx` decides whether to show `WelcomeFlow.tsx`. `src/lib/onboarding.ts` holds `OnboardingStatus {completedAt, version, reelSeen, hintsSeen, firstTurnAt}` and `beatsFor({hosted})` = `["meet","chief"]` locally, `["meet"]` when hosted. A reloaded first run resumes at the saved beat (`resumeBeat`); the draft name is kept (`src/lib/welcome-draft.ts`).
2. On a genuine first run on the person's own computer, the name is pre-filled from the OS account (`nameFromComputer` in `WelcomeFlow.tsx` via `window.ogb.desktopProfile.systemName()`); never on a Cloud or remote page.
3. `MeetScreen.tsx` (meet the main agent), `ChiefIntro.tsx` (the lead agent, "Chief of Staff"), then `ConnectAi.tsx` which reuses `EngineSetup` to connect an AI. Ranking of which AI to offer first and which a new bot gets: `shared/ai-ranking.ts` (Claude account, then ChatGPT plan, then Gemini/Antigravity, then Grok, then others; OpenCode free models last as `freeFallback`). It can send a real test message to each AI (`AiTestState`, reasons `signed_out|credits|usage_limit|rate_limit|...`).
4. A first bot is created already running on the best ready AI, with Full access by default (`docs/approval-levels.md`); a missing key or real question still reaches the person.
5. After the flow: `FirstConversationTour.tsx`, `GuidedTour.tsx`, `Spotlight.tsx` hints (`hintsSeen`), `HelperKeySuggestion.tsx` (a card inside chat suggesting adding a key).
6. Headless: `docs/cli-onboarding.md`, `server/cli/`. Sign-in gate for hosted pages: `src/lib/sign-in-gate.ts`, `server/email-sign-in.ts`.

## 8. Settings: providers, keys, subscription sign-in, model picker

### 8.1 Layout
`src/components/settings/SettingsDialog.tsx` + `SettingsNav.tsx`; the list of places is generated (`shared/settings-places.ts`, `scripts/gen-settings-places.ts`, `src/components/settings/settings-index.ts`) so search, deep links and the phone share one index. Pages under `src/components/settings/pages/`. Engines: `EnginesSettings.tsx`, `EngineLibrary.tsx`, `EngineSetup.tsx`, `EngineAccounts.tsx`, `EngineUsage.tsx`; keys: `src/components/keys/KeysPage.tsx`, `KeyRow.tsx`, `key-catalog.ts`, `key-save.ts`; voice: `VoiceSettings.tsx`, `LiveProviderSettings.tsx`, `bot-settings/VoiceSection.tsx`.

### 8.2 The two ways in, per provider
Each provider is a `ProviderInstance` with a `snapshot` (`state`, `authenticated`, `version`, `authenticationUnavailableReason`) the UI reads:
- `needsCli(instance)`: engine not installed (`state !== "available"`).
- `needsSignIn(instance)`: installed but `authenticated === false`.
- `hasSavedApiKey(instance)`: key engines with `authenticated === true`.
`src/components/EngineSetup.tsx` chooses the flow from `instance.authenticationMethod` and the engine kind.

### 8.3 Subscription sign-in flows (server)
Common shell: `server/provider-auth-sessions.ts` `ProviderAuthSessions` holds one in-flight login per instance, owned by the admin session that started it ("never put its device code on global SSE"); a second start returns 409; flows expire. HTTP: `POST /api/instances/:id/auth/start`, `GET .../auth/status?flowId=`, `POST .../auth/complete`, `POST .../auth/cancel` (called from `EngineSetup.tsx`, `DeviceSignIn.tsx`, `ClaudeSignIn.tsx`; routes in `server/routes/instances.ts`).
1. **Claude subscription**: `server/drivers/claude-login-auth.ts` runs the UNMODIFIED `claude auth login` with pipes, shows only its sign-in link (hosts allow-listed to `claude.com, claude.ai, console.anthropic.com, platform.claude.com`), pastes the code to its stdin, confirms with `claude auth status --json`. The header comment states that Anthropic permits an end user signing in to the unmodified binary with their own subscription, and forbids flows that intermediate claude.ai credentials, "hence no OAuth client code in this repository". Client: `src/components/ClaudeSignIn.tsx` (also only https Anthropic links).
2. **ChatGPT/Codex plan**: two paths. `server/drivers/codex-device-auth.ts` runs `codex login --device-auth` (a `DeviceAuthController` in `server/drivers/device-auth.ts` parses the code and URL via `shared/device-sign-in.ts`); `server/drivers/chatgpt-plan-auth.ts` implements OpenAI's own PKCE flow (issuer `auth.openai.com`, scope `chatgpt.tokens.use.direct`, 15 min lifetime) and a token bridge so Codex asks a local command for a fresh token (`codex-plan-token.ts`, `chatgpt-plan-token-bridge.ts`); consent is explicit ("ChatGPT plan usage is not enabled... or explicitly choose another provider").
3. **Gemini/Antigravity, Grok, Cursor**: `antigravity-native-sign-in.ts`, `acp/grok-sign-in.ts`, CLI login handoff `server/routes/cli-login.ts` (+ `src/components/CliLoginCard.tsx`: a terminal waiting on one click is shown "above Settings and every dialog").
4. Per-engine credential homes: `server/engine-homes/` so several accounts per engine can coexist; `EngineAccounts.tsx`.
5. Cloud: `CloudEngineSignIn.tsx` and `PhoneSetupSignInRoutes.tsx` let a phone-reached server be signed in from the phone.

### 8.4 API keys
1. UI: `KeyRow.tsx` / `KeysPage.tsx`; save via `saveKey()` in `src/components/keys/key-save.ts` into either the desktop's encrypted store (`window.ogb.setCredential`) or `PUT /api/config`. "Secrets are write-only; GET /api/config returns configured flags and, for admins, the last four characters."
2. A key is checked before it is trusted: `server/provider-key-check.ts` `checkProviderKey()` for `anthropic, openai, openrouter, openaiCompat, xai, mistral, cerebras, groq, greenference, modelgo, meta` with a loopback/URL safety check (`keySafeUrl`).
3. In chat: a bot can ask for a key on a secure card (`HelperKeySuggestion.tsx`, `server/routes/secret-cards.ts`).
4. `docs/voice-mode.md` (historical) states the same rule for voice: the renderer never talks to the provider; the harness holds the key; "configured" and "ready" are separate states and a missing setup is a 409, not a provider failure.

### 8.5 Model picker
1. Model lists come from the engines and a bundled manifest (`agent.catalog` node; `shared/model-*`; `src/lib/model-choices.ts`, `model-label.ts`, `favorite-models.ts`).
2. `src/components/ModelPicker.tsx` (1017 lines) with `ModelPickerFull.tsx`, `SimpleModelMenu.tsx`, `ModelPickerTrigger.tsx`. Rows are grouped by engine rail (`splitEngineRail`, `signInFamily` in `src/lib/engine-rail.ts`). Each row shows provider, "default", "loaded now", and is disabled with a reason if `orgBlocked` or `needsCliUpdate` (`ModelRow`). The engine header shows `engineStatus()`: "Setup required", "Sign-in required", or the version.
3. Reasoning effort is a second control (`EffortLevel`, `model-picker-reasoning.ts`); some engines expose variants instead (`session.model-variants` runtime event).
4. Scope: a model is per bot with optional per-thread override (`thread.modelSelection`); `POST /api/bots/:id/threads/follow-model` resets threads to the bot's model; a thread with a running turn keeps its model until it settles (`server/routes/thread-models.ts`). The picker works while busy (`ModelPickerBusyMenu.tsx`).
5. A cheaper "decider" model for routing/triage is configured separately (`DecisionModelSettings.tsx`, `docs/decision-model.md`, `server/decider.ts`).
6. Custom OpenAI-compatible endpoints and local models: `src/lib/openai-compat-endpoints.ts`, `local-model.ts`, `CompanyModels.tsx` (org-set models).

## 9. Voice (present)
- Push-to-talk and call mode: `CallSheet.tsx`, `src/lib/call.ts`, `call-mode.ts`, `push-to-talk.ts`, `use-composer-dictation.ts`, live voice providers `src/lib/live-call-elevenlabs.ts`, `live-call-gemini.ts`, `live-call-gemini-audio.ts`, `live-call-fish.ts`; wire `packages/phone-protocol/src/live-call-wire.ts`; `live.call` frames.
- Text to speech: `src/lib/tts/`, `src/lib/spoken-reply-stream.ts` (speaks assistant text as it completes; `spokenReplyStream.onRuntimeEvent`), `server/routes/tts.ts`, `server/tts/speech-text.ts` ("the spoken register": says the prose, names the artifacts, drops the syntax).
- Design stance (from `docs/voice-mode.md`, partly historical): half-duplex on purpose (no echo cancellation; mic live only when the bot is silent), local turn detection with a silence endpoint (`CALL_ENDPOINT_MS` 1.7 s), one request per utterance with prefetch of the next, keys on the server.
- Approvals can be spoken (`spokenApprovalPrompt` in `PendingApproval.tsx`).

## 10. What I could not find / what the code does not do
- No Telegram, WhatsApp or SMS agent channels; no outbound phone calls. Slack only via a Cloud Admin ingress.
- Native iOS/Android app source is absent from this checkout; claims about phone UI rest on `docs/ios-companion.md`, `docs/phone-push.md` and the protocol package.
- Android push: docs say not yet live.
- No evidence of a scheduled "heartbeat" that invents work; proactivity is trigger-based by design.
- I did not read all 1000+ lines of `packages/phone-protocol/src/wire.ts` or the whole of `ModelPicker.tsx`/`EngineSetup.tsx`; statements about them are from signatures, headers and call sites.
- I did not run anything; tests were read only by name.

## 11. What Lonora should copy / avoid

Copy:
1. **One resumable SSE stream with a hello/cursor/resumed handshake** and a bounded replay buffer. If the cursor fell off, force a snapshot rather than a partial replay. Visible `ping` frames, stale timer, backoff, hold while hidden/offline. Maps directly onto a FastAPI SSE endpoint and the web and Expo clients.
2. **Normalised runtime events** (`turn.started`, `item.*`, `content.delta`, `request.opened/resolved`, `runtime.error`) as the one contract between the worker and every client, with a live-only `turn.progress` that is never persisted.
3. **Keep token deltas out of the app store.** A per-thread external store (`live-reply.ts`) replaced by the saved message with the same id in one commit. Also a gap flag so a reconnect never draws half an item.
4. **Server-composed step labels with redaction** (`LiveStep` target at most 60 chars, redacted twice) so a status line like "Reading EURUSD calendar" is safe on any client.
5. **Durable typed cards for approvals and questions**, resolved with `requestId`, an explicit `source` of who decided (user, auto, timeout, system, peer), and settled one-line outcomes. For trading this is the Trade Approval card: store who/what/when decided and render the outcome from the record.
6. **Grant saved before release**: persist an "always allow" before answering the request; if it fails, keep the request waiting.
7. **Widgets as validated JSON, never executable code**, with hard limits, a fixed icon list, `rev` and `sendId` on presses, and presses sent as a normal user message. Use this for Lonora's trade tickets and result tables; keep sandboxed HTML apps out of v1.
8. **Notification policy owned by the server**: a closed list of kinds, every notification carries agent id and thread id, quiet by default for agent-opened threads, one banner per event, click opens the exact thread. Add trading kinds (order filled, risk limit hit, stop engaged, connection lost).
9. **Secrets by card, never in chat**: the agent names a target id from a fixed list, the value goes to a dedicated route, never echoed; sign-in handoff cards for broker web logins; phone secrets sealed to a pinned key.
10. **Provider sign-in architecture**: per-instance login state with owner binding; use the vendor's own unmodified CLI or device-code flow and show only allow-listed links; show "Setup required / Sign-in required / ready" per provider; test each provider with a real message and a fixed reason list; rank providers for the default model. Check API keys against the provider before saving and keep them write-only.
11. **Model picker rules**: group by provider, show disabled reasons, per-agent default plus per-thread override that never changes mid-turn, a cheap decider model configured separately.
12. **Proactivity by explicit trigger**: routines, webhooks, waits, event wake-ups, with one owner agent (Lonora) for the daily brief and a visible initiating trigger for every autonomous run. This matches a trading assistant, where silent invented work is a risk.
13. **Parity through a shared protocol package**: one set of wire types and server-generated fixtures consumed by both web and mobile, plus protocol test vectors.
14. **Settings index generated from one table** so deep links, search and mobile share it.

Avoid:
1. A 15 000-line request handler (`server/index.ts`) and 3 000-line store (`src/state/store.tsx`): split routes and frame reducers from the start.
2. Sandboxed HTML apps and MCP Apps in the first release: large attack surface for little gain in trading.
3. Default "Full access" for agents. OpenMausBot defaults every bot to Full access; Lonora's money-moving tools must default to Ask with an explicit Mandate/limit grant.
4. Claiming push without closed-app delivery: OpenMausBot's phone is silent once suspended without APNs/FCM; plan push (Expo push) early because a trading alert that arrives late is worse than none.
5. Heavy engine-specific permission modes surfaced to users (approval levels per provider). Lonora has one engine path; keep one ladder.
6. Many overlapping onboarding beats and tours; Lonora needs: connect an AI, connect MT5, set limits, first chat.
7. Treating Slack/Telegram as a trust boundary without a signed ingress contract. If Lonora adds Telegram, copy the Slack pattern: signed, idempotent per message id, the token stays off the worker, a message is the member's own request with no extra authority.
