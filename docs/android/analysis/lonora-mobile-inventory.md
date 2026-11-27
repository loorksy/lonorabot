# Lonora Expo app (`apps/mobile`) — exhaustive inventory for the native Android (Flutter) port

Scope: every screen, sheet, menu, action, state, gesture, notification/heads-up behaviour, deep link,
OTA logic, voice-call flow and settings item of the Expo companion app, plus the i18n system, the
GenUI v2 renderer, rich (v1) responses, fixed cards, the avatar and the build configuration.
Each feature is mapped to the API endpoints it calls (all paths are under `/api`).

Legend: **VERIFIED** = read in the cited file (`path:line`); **INFERRED** = deduced from code shape,
naming or absence of code, not directly stated. Paths are repo-relative.

Important context (VERIFIED, `VISION.md:801-803`, Amendment 3 item 13): "Once the app offers every owner
capability of the web client (section 13), the web client may be switched off for customers". The
Expo app is still a *companion* (`apps/mobile/README.md:68`); the web-only capabilities are listed in
`lonora-web-inventory.md`.

---

## 1. Build and release configuration (`apps/mobile/app.config.ts`)

| Item | Value | Evidence |
|---|---|---|
| App name / slug / URL scheme | `Lonora` / `lonora` / `lonora` (from `brand`) | VERIFIED `app.config.ts:23-27`, `packages/ui-tokens/src/brand.ts:1-8` |
| Android package (applicationId) | `ai.lonora.mobile` | VERIFIED `app.config.ts:45`, `brand.ts:5` |
| versionName | `0.2.8` | VERIFIED `app.config.ts:25` |
| versionCode | `26102101` | VERIFIED `app.config.ts:46` |
| versionCode scheme | `YYMMDDNN` (date of build + 2-digit sequence): history 26101612 (0.2.5), 26101613 (0.2.6), 26101901 (0.2.7, 2026-10-19), 26102101 (0.2.8, 2026-10-21) | INFERRED from `apps/mobile/README.md:80,85` and `docs/mobile/ota.md:5` |
| Orientation / UI style | portrait / automatic (light+dark) | VERIFIED `app.config.ts:28-29` |
| Android permissions requested | `RECORD_AUDIO`, `MODIFY_AUDIO_SETTINGS`, `WAKE_LOCK` | VERIFIED `app.config.ts:54`; WAKE_LOCK reason (InCallManager crash) `docs/mobile/voice-native-verification.md:42-48` |
| Android permissions blocked | `CAMERA`, `SYSTEM_ALERT_WINDOW`, `READ_EXTERNAL_STORAGE`, `WRITE_EXTERNAL_STORAGE`, `ACCESS_WIFI_STATE` | VERIFIED `app.config.ts:57-63` (attachments use the system document picker + cache) |
| Keyboard | `softwareKeyboardLayoutMode: "resize"` | VERIFIED `app.config.ts:52` |
| Icons | adaptive foreground/monochrome PNGs, background `#000000`; iOS light/dark/tinted | VERIFIED `app.config.ts:31-35,47-51`; assets in `apps/mobile/assets/brand/` |
| Push | `expo-notifications` plugin, `color #000000`, `defaultChannel "attention"`; Expo project id `LONORA_EXPO_PROJECT_ID` + `google-services.json` path `LONORA_ANDROID_GOOGLE_SERVICES_FILE`; without both, no push | VERIFIED `app.config.ts:12-20,53,65,86`, `scripts/android-release.py:54-65` |
| Release signing | config plugin replaces the debug signingConfig and reads `LONORA_ANDROID_KEYSTORE`, `LONORA_ANDROID_STORE_PASSWORD`, `LONORA_ANDROID_KEY_ALIAS`, `LONORA_ANDROID_KEY_PASSWORD`; a release build without them fails | VERIFIED `plugins/with-release-signing.cjs:1-46` |
| Release signer | SHA-256 `f1739a3196d6a9d1ce446d883d1d87527dab50226f979aa35dc8aef22ddcceee` (rotated 2026-10-19); `LONORA_EXPECTED_SIGNER_SHA256` checked by the verifier | VERIFIED `apps/mobile/README.md:85-89`, `scripts/android-verify.py:113` |
| ABIs / min SDK | universal APK, `armeabi-v7a, arm64-v8a, x86, x86_64`; Android 7 / API 24+ | VERIFIED `scripts/android-release.py:88`, `scripts/android-verify.py:109`, `README.md:31` |
| OTA (Expo Updates protocol v1, self-hosted) | `updates.url` = `LONORA_OTA_URL` default `https://lonora.lork.cloud/api/mobile/updates`; header `expo-channel-name` = `preview`/`production`; `checkAutomatically: ON_LOAD`; `fallbackToCacheTimeout: 0`; `useEmbeddedUpdate: true`; code signing cert `certificates/ota.pem`, `keyid main`, `rsa-v1_5-sha256`; `runtimeVersion.policy: fingerprint` | VERIFIED `app.config.ts:5-10,66-76`; server `apps/api/src/lonora_api/routes/mobile_updates.py` (`GET /mobile/updates`, `GET /mobile/updates/assets/{filename}`) |
| iOS (reference only) | bundle id = package; `associatedDomains webcredentials:<ota host>` (passkeys); mic usage string ar+en | VERIFIED `app.config.ts:36-42` |

Port notes (INFERRED): a Flutter APK can only upgrade the installed Expo app in place if it keeps
`ai.lonora.mobile`, the same signing certificate and a versionCode > 26102101. The Expo OTA endpoint
(`/api/mobile/updates`, Expo manifest protocol) cannot update a Flutter binary; the Flutter app needs
its own update path (or none).

---

## 2. Runtime architecture

### 2.1 Provider tree and global overlays — VERIFIED `app/_layout.tsx:40-79`
`useOtaUpdates()` → `SessionProvider` → `PushRegistration` → `ThemeProvider` → `ShellDataProvider` →
`ToastProvider` → `ListsProvider` → `SheetProvider` → `VoiceSessionProvider` → `ChartSheetProvider` →
Stack + three always-mounted overlays: `HeadsUp` (`:67`), `VoiceOverlay` (`:68`), `IncomingCallOverlay`
(`:69`). Modal presentations: `connect`, `new-group`, `bot-settings`, `group-settings` (`:57-65`).
Stack animation `slide_from_right`, header hidden (`:23-28`).

### 2.2 Session and authentication — VERIFIED `lib/session.tsx`, `lib/api.ts`, `lib/storage.ts`
- Server URL is user-entered; normalised (http/https only, no credentials/query/hash, strips trailing
  `/api`) `lib/api.ts:100-109`.
- First-run detection: `GET /onboarding` → `{owner_initialized:boolean}` (only a boolean answer counts)
  `lib/api.ts:113-123`; debounced 400 ms, 10.4 s timeout `app/sign-in.tsx:28-52`.
- Owner setup: `POST /onboarding {email,password,bootstrap_token}` then login; `owner_already_initialized`
  tolerated `lib/session.tsx:128-143`. Password ≥ 12 chars and token ≥ 24 chars enforced client side
  `app/sign-in.tsx:80-93`.
- Native login: `POST /auth/mobile/login {email,password}` → `{owner, token}`; opaque expiring token in
  SecureStore key `lonora.session`; every request `Authorization: Bearer` `lib/session.tsx:108-126`,
  `lib/storage.ts:25-34`, `lib/api.ts:145-154`. (Web/Expo-web: `/auth/login` + HttpOnly cookie + `X-CSRF-Token`
  from cookie `lonora_csrf` `lib/api.ts:139-152`.)
- Session restore: `GET /auth/session` at launch `lib/session.tsx:79`. 401 on a non-`/auth/` request →
  expire (token cleared, resources closed) `lib/api.ts:82`, `lib/session.tsx:54-59`.
- Logout: `POST /auth/logout`, always clears local token, closes voice/WS/outbox/draft resources
  (`session-lifecycle.ts` teardown registry) `lib/session.tsx:145-167`.
- Change server: logs out first, then stores the new server `lib/session.tsx:168-186`.
- Request fencing: a global generation counter cancels every in-flight request on login/logout/server
  change (`SessionRequestCancelled` is never shown as an error); 30 s timeout per request; GETs pass a
  `ReadRequestGate` (concurrency gate); background reads are aborted when the app leaves the foreground
  `lib/api.ts:17-98`, `lib/session.tsx:93-98`.
- Error text precedence for an `ApiError.code`: `agentPermissionError` → `financialBoundaryError` →
  `ownerActionError` → `ownerProfileError` (all `@lonora/core`) → mobile label with the same key → fallback
  → `request_failed`; no HTTP answer → `network` `lib/session.tsx:192-209`.
- Device-local storage keys (SecureStore): `lonora.server`, `lonora.session`, `lonora.locale`,
  `lonora.theme`, `lonora.chatPrefs`, `lonora.push.device`, outbox `lonora.outbox.v1:*` (≤1 MB), drafts,
  visual state files under the document dir `lonora-visual-state/` VERIFIED `lib/storage.ts`,
  `lib/theme.tsx:41`, `lib/chat-prefs.ts:14`, `lib/push.native.ts:17`, `lib/outgoing-messages.ts:50-51`,
  `lib/visual-state.ts:6-30`, `lib/draft-store.ts:1-5`.

### 2.3 Live data
- **Owner event stream** (one WebSocket per subscriber): `wss://<server>/api/ws/events`; after open the
  client sends `{cursor, live?:true (first connect only), token}`; server replies `{type:"ready",cursor}`
  then events `{cursor, kind, payload, thread_id?, run_id?}` and cursor-less pings at least every 15 s;
  45 s silence → replace socket; reconnect after 1.5 s; socket closed in background, reopened on
  foreground; network type change forces reconnect; durable resume from last cursor. VERIFIED
  `lib/events.ts:8-147`. Connection state `connecting | connected | reconnecting` drives avatar
  "connecting" and turn activity.
- Event kinds consumed: `message.created`, `message.updated`, `message.reaction_updated`,
  `thread.updated`, `run.*` (queued, leased, running, delta, rich_partial, reply_started,
  reply_committed, progress, waiting_input, waiting_takeover, completed, failed, cancelled, recovered,
  context_started), `tool.started|completed|cancelled|failed`, `cloud_charts.scene_updated|created|
  updated|deleted`, `broker_identity.updated` VERIFIED `app/thread.tsx` (event handler `:580-655`),
  `app/charts.tsx:187-199`, kinds list in `packages/core/src/turn-activity.ts`.
- **Shell poll** every 5 s while active (and on foreground): `GET /agents`, `GET /groups`,
  `GET /threads/inbox`, `GET /chat-lists`, `GET /threads/settings`, `GET /runs`, `GET /attention`,
  `GET /attention/view` (unseen count → Updates tab dot); `POST /app-opens` on each foreground (morning
  brief learning) VERIFIED `lib/shell-data.tsx:31,94-203`. Offline = a read failing without HTTP status
  (`:146-156`).
- Thread screen: snapshot on focus + every 15 s fallback + 150 ms debounced refetch after non-streaming
  events VERIFIED `app/thread.tsx:560-680`.
- Agent live state: `GET /agents/{id}/state` every 15 s while the thread/bot-settings is focused
  VERIFIED `lib/agent-live-state.ts:12-55`.
- Conversation cache: in-memory only, scoped `server+owner`, generation-fenced; last 1000 messages per
  thread VERIFIED `lib/conversation-cache.ts:37-38`, `app/thread.tsx:521-534`.

---

## 3. Route map (expo-router file routes)

| Route | File | Entry points | Params |
|---|---|---|---|
| `/` (Chats tab) | `app/(tabs)/index.tsx` | tab bar | — |
| `/updates` | `app/(tabs)/updates.tsx` | tab bar (dot when unseen) | — |
| `/tasks` | `app/(tabs)/tasks.tsx` | tab bar; search hit "task" | — |
| `/settings` | `app/(tabs)/settings.tsx` | tab bar | — |
| `/sign-in` | `app/sign-in.tsx` | redirect when no owner | — |
| `/connect` (modal) | `app/connect.tsx` | deep link `lonora://connect` | `server`, `token` |
| `/server` | `app/server.tsx` | Account › Server row | — |
| `/agents` | `app/agents.tsx` | New-chat sheet «إدارة الوكلاء»; GenUI `go agents` | — |
| `/archived` | `app/archived.tsx` | «المؤرشفة» row on Chats | — |
| `/thread` | `app/thread.tsx` | row tap, push tap, heads-up, search, incoming call «reply by message», attention row, task/run row, peer card | `id`, `around?` (seq to centre on) |
| `/group-thread` | `app/group-thread.tsx` | group row (resolves/creates group thread) | `groupId` |
| `/bot-settings` (modal) | `app/bot-settings.tsx` | thread header name/settings, action menu, search hit "knowledge/skill" | `botId` |
| `/group-settings` (modal) | `app/group-settings.tsx` | group thread header/action menu | `groupId` |
| `/new-group` (modal) | `app/new-group.tsx` | New-chat sheet; selection «مجموعة من المحددين» | `members?`, `name?` |
| `/skills` | `app/skills.tsx` | bot-settings «المهارات» | `botId` |
| `/routine` | `app/routine.tsx` | bot-settings «المهام الدورية», thread action menu | `botId?` |
| `/artifacts` | `app/artifacts.tsx` | thread action menu; GenUI `go files` | `threadId?` |
| `/artifact` | `app/artifact.tsx` | file card, visual action `open_artifact`, search hit | `artifactId` |
| `/image` | `app/image.tsx` | tap on image preview | `artifactId` |
| `/charts` | `app/charts.tsx` (also embedded in chart sheet) | GenUI `go market` | `threadId?`, `botId?`, `chartId?` |
| `/owner` | `app/owner.tsx` | Settings «ما أعرفه عنك» | — |
| `/account`, `/integrations`, `/models`, `/notify-settings`, `/voice`, `/running` | `app/(settings)/*.tsx` | Settings rows (models via Integrations; voice via Notify) | — |
| `+not-found` | `app/+not-found.tsx` | unknown link → «الصفحة غير موجودة» + Inbox | — |

VERIFIED by navigation grep (`router.push|replace|navigate` across `app/`, `components/`, `lib/`).
Every protected screen does `if (!ready) <Loading/>; if (!owner) <Redirect href="/sign-in"/>`
(e.g. `app/(tabs)/_layout.tsx:20-21`).

---

## 4. Screens — elements, actions, states, endpoints

### 4.1 Sign-in / first-run setup — `app/sign-in.tsx`
- Header: brand name + language toggle button («English»/«العربية») `:110-119`.
- Logo, title «تسجيل الدخول» or «إعداد Lonora», hint text `:134-158`.
- Fields: Server URL (LTR, `https://lonora.example.com` placeholder), Email, Password (setup: new
  password ≥12), Setup token (setup only, secure) `:159-199`.
- Submit button «تسجيل الدخول» / «إنشاء» (shows «جارٍ الاتصال» while busy), disabled rules `:80-86`.
- States: loading (session not ready), pending check, setup vs sign-in, error notice; failure re-checks
  onboarding `:101-104`. A connect-link token fills the setup token only for the same server `:59-76`.
- Endpoints: `GET /onboarding`, `POST /onboarding`, `POST /auth/mobile/login`.

### 4.2 Connect deep link — `app/connect.tsx`, `lib/connect-link.ts`
`lonora://connect?server=https://<host>[&token=<20-128 [A-Za-z0-9_-]>]`; https required except local
hosts (localhost, *.local, 10/8, 172.16/12, 192.168/16, 127/8, [::1]) `lib/connect-link.ts:1-31`.
Shows host, «الاتصال» confirm → `changeServer` (logs out) → holds token in memory → `/sign-in`;
«ليس الآن» → `/`. Invalid link → «connectInvalid» `app/connect.tsx:24-67`.

### 4.3 Change server — `app/server.tsx`
Field + hint + Save → `changeServer` → `/sign-in` `app/server.tsx:7-44` (VERIFIED). Revokes old session.

### 4.4 Tabs shell — `app/(tabs)/_layout.tsx`, `components/shell/chrome.tsx`
- Floating glass tab bar (Telegram-style lens), order reversed in RTL; tabs: المحادثات (unread badge =
  `unreadBadgeTotal(inbox)`), التحديثات/يحتاج انتباهك (dot), المهام, الإعدادات VERIFIED
  `app/(tabs)/_layout.tsx:24-38`, `components/shell/chrome.tsx:12-20,227-366`.
- Network strip under the status bar: «لا يوجد اتصال بالإنترنت» + count of waiting outbox messages,
  then «تم استعادة الاتصال» for 2.2 s VERIFIED `components/shell/network-strip.tsx:1-30`.

### 4.5 Chats tab — `app/(tabs)/index.tsx`, `components/shell/chat-list.tsx`, `thread-row.tsx`, `selection.tsx`, `list-sheets.tsx`, `unified-search.tsx`, `new-chat-sheet.tsx`
- **Header** «Lonora», search pill (expands, ✕ closes; Android back closes search) and «+» (new chat)
  `components/shell/chrome.tsx:61-170`, `app/(tabs)/index.tsx:154-163`.
- **Filters** hidden above the first row, revealed by pull-down: الكل · غير مقروءة · المفضلة · الوكلاء ·
  المجموعات · each custom list · «+» new list; long-press a list chip → list menu (edit, the chats,
  delete with undo) `chat-list.tsx:1-2,79-139`, `list-sheets.tsx:380-410`.
- **«المؤرشفة» row** → `/archived` `chat-list.tsx:158-182`.
- **Rows** (agent or group): avatar (live `BotAvatar`, group cluster), name, HH:mm (Latin digits),
  preview with «أنت:» ticks (one grey tick = server received; two accent ticks = the agent's run
  started), speaker prefix in groups, outbox state («لم يُرسل» / «بانتظار الشبكة…»), muted/pinned
  icons, paused badge, unread count or 12 px dot (marked unread), spoken summary VERIFIED
  `thread-row.tsx:1-3,84-303`.
- **Gestures**: tap = open (agent without a thread gets `POST /agents/{id}/conversation`; group →
  `/group-thread`) `chat-list.tsx:48-62`; long-press = start selection `thread-row.tsx:192-193`;
  pull-to-refresh (`RefreshControl`) `chat-list.tsx:258`.
- **Selection toolbar**: ✕ · count | pin/unpin · mute/unmute · archive/unarchive · delete · ⋮ (select
  all, mark read/unread, add/remove favourite, add to list, group from selected, clear messages)
  `selection.tsx:208-311`. Actions → `POST /threads/prefs {thread_ids, pinned|muted|archived|
  marked_unread|favourite}`, `POST /threads/{id}/read {seq}`, `POST /threads/{id}/clear`
  (delete = clear history for the owner only; agent/group never deleted) `selection.tsx:1-3,96-162`,
  `lib/lists-api.ts:11-25`. Archive shows toast with «تراجع» undo `selection.tsx:145-152`. Confirm sheets
  for clear/delete `:60-110`.
- **Custom lists** (WhatsApp «القوائم»): full-height two-page sheet (name with 😊 emoji panel, then pick
  agents/groups with search), create/rename/members/move/delete(+undo) → `POST /chat-lists`,
  `PUT /chat-lists/{id} {name|position}`, `PUT /chat-lists/{id}/members {thread_ids}`,
  `DELETE /chat-lists/{id}` `list-sheets.tsx:1-3,254-458`, `lib/lists-api.ts:20-25`. Name taken / max
  length warnings.
- **Archived page**: archived rows, note, «إبقاء المحادثات مؤرشفة» switch → `PUT /threads/settings
  {keep_archived}` `chat-list.tsx:384-432`.
- **Empty states**: «لا توجد رسائل غير مقروءة», favourites hint, «لا توجد محادثات», «لا محادثات في
  «{0}» بعد» + «إضافة محادثات» `chat-list.tsx:318-346`. Loading: skeleton rows (`SkRows`).
- **Unified search** (header field): `GET /search?q=&limit=&offset=&category=`; tabs الكل · المحادثات ·
  الرسائل · المهام · الملفات · أخرى (knowledge+skills); الكل = 3–4 per category, a tab pages by 32; empty
  query browses recent; highlight of match; hit routing: chat → thread, message → thread `around=seq`,
  task → `/tasks`, file → `/artifact`, skill → `/integrations`, knowledge → `/bot-settings`; "result
  gone" toast VERIFIED `unified-search.tsx:1-3,62-191,229-360`, `packages/core/src/search-feed.ts:1-50`.
- **New-chat sheet** «محادثة جديدة»: «مجموعة جديدة» → `/new-group`, agents list, groups list, «إدارة
  الوكلاء» → `/agents` `new-chat-sheet.tsx:1-99`. (No agent creation UI: agents are created by Lonora from
  chat, `docs/agents-from-chat.md` — VERIFIED; `POST /agents` unused by clients.)

### 4.6 Updates tab — `app/(tabs)/updates.tsx`, `components/attention-view.tsx`
«يحتاج انتباهك»: `GET /attention/view` rows (kinds: trade_approval, settle_operation, secret_request,
mandate_card, broker_health, background_health, owner_question, task_review, agent_alert,
system_alert); each row «فتح المحادثة» → thread; opening decides nothing. VERIFIED
`attention-view.tsx:1-3,26,95`, `packages/contracts/src/attention.ts:115-140`. Mobile never posts
`/attention/seen` (VERIFIED by grep; web does).

### 4.7 Tasks tab — `app/(tabs)/tasks.tsx`
Lists `data.runs` of known agents (avatar working state, `runStatusText`), tap → thread from
`reportThread(run)` (question thread / origin conversation) `:308-350`, `lib/run-thread.ts:3-7`.
Empty: «لا توجد مهام محفوظة». It is a run list, not the Task system (comment "task pages arrive with
phase 4", `:1`).

### 4.8 Settings tab — `app/(tabs)/settings.tsx`
Owner initials + email; rows: «ما أعرفه عنك» → `/owner`; «الحساب» → `/account`; «التكاملات» →
`/integrations`; «الإشعارات والتواصل» → `/notify-settings`; «ما يعمل الآن» → `/running`; «المظهر»
(Dark/Light toggle, saved `lonora.theme`) VERIFIED `:54-90` (file lines), `lib/theme.tsx:34-49`.

### 4.9 Settings sub-pages
| Page | Content / actions | Endpoints | Evidence |
|---|---|---|---|
| Account | email; Server (→ `/server`); Language العربية/English (check mark); Usage: input/output/cached tokens; Logout (destructive) | `GET /usage/summary`, `POST /auth/logout` | VERIFIED `app/(settings)/account.tsx:12-93` |
| Integrations (Capabilities) | «النماذج» row; intro; built-in capabilities; trusted sources (remove/restore); MCP servers (review → tool preview with tools/writes/blocked, «never money»; trust read / trust write_nonfinancial; remove); skills (non-bundled; undo = revoke version); integrations (remove); «إعداد» opens web settings | `GET /capabilities`, `POST /trusted-sources/{id}/revoke|restore`, `POST /trusted-sources/mcp/{connection}/preview`, `POST /trusted-sources/mcp/{connection} {tier,digest}`, `GET+POST /agents/{id}/skills/revocations`, `DELETE /integrations/{id}`; `Linking.openURL(<server>/app?settings=integrations)` | VERIFIED `app/(settings)/integrations.tsx:27-263` |
| Models (read-only) | routing mode unified/custom with provider·model per capability; providers configured/not; «فتح إعدادات الويب» | `GET /settings/models`, `GET /providers`; opens `<server>/app?settings=models` | VERIFIED `app/(settings)/models.tsx:10-86` |
| Notifications and contact | `IncomingCallSettings` (below) + «الصوت» row | see 4.10 | VERIFIED `app/(settings)/notify-settings.tsx` |
| Voice (read-only) | GPT-Live configured/not; hint; open web voice settings | `GET /voice/status`; `<server>/app?settings=voice` | VERIFIED `app/(settings)/voice.tsx:9-58` |
| What is running | Stop all (disabled if empty/stale/stopping), per-agent groups of processes (command isolated LTR, started time), Stop per process; stale banner, unknown banner, empty text; polls every 4 s | `GET /workspace/running`, `POST /workspace/running/stop {pid,agent_id}`, `POST /workspace/running/stop-all` | VERIFIED `app/(settings)/running.tsx:11-174` |

### 4.10 Reach-me / incoming-call settings — `components/incoming-call-settings.tsx`
- Channel buttons: «أرسل لي تنبيهًا» notify / «راسلني» message / «اتصل بي» call (call disabled with no
  enrolled device) with hints; choosing call forces `action_required=true` `:132-150`.
- Device registration with passkey: password field → `POST /auth/devices/enrollment {password,name}` →
  passkey create (`react-native-passkeys`) → `POST /auth/devices/enrollment/verify` → refresh
  `GET /owner/profile` devices `:80-100`, `lib/device-proof.native.ts:1-35`. Unsupported device text.
- When channel = call: choose device; switches «Calls when my input is needed» (action_required),
  «Opportunity calls» (opportunities) `:176-204`.
- Quiet hours start/end (0–23, number pad); reply language (auto/ar/en + any stored tag) `:205-230`.
- Save → `PUT /owner/preferences {reply_language, reach_me}` (payload via `reachMePayload`, device
  timezone) `:101-124`, `lib/incoming-call.ts:54-73`.
- Strings come partly from `@lonora/core` `ownerProfileLabel` and `ownerActionText`.

### 4.11 Agents management — `app/agents.tsx`
Section «الوكلاء»: rows (avatar, name, role line, paused/active dot, chevron mirrored) → open chat;
«المجموعات»: rows with `agentsWord(count)`; empty «لا مجموعات بعد»; «إنشاء مجموعة» → `/new-group`;
skeleton while loading. VERIFIED `app/agents.tsx:27-123`.

### 4.12 New group / Group settings — `app/new-group.tsx`, `app/group-settings.tsx`
- New: name (≤80), member picker (`BotMemberPicker`), Create → `POST /groups/create {name, member_ids,
  participation:"mentions_or_lead"}` → thread `group.thread_id` VERIFIED `new-group.tsx:32-47`.
- Settings: name, members, read-only participation «بالإشارة أو القائد», Save → `PUT /groups/{id}
  {payload, version}` (optimistic version) VERIFIED `group-settings.tsx:40-52`, `lib/groups.ts:5-7`.
- Group thread resolution: `GET /groups/{id}` → `GET /threads/{state.thread_id}` or find in
  `GET /threads` or `POST /threads {group_id,title}` VERIFIED `lib/groups.ts:5-15`.

### 4.13 Agent settings (bot-settings) — `app/bot-settings.tsx`
- Avatar picker (face + colour, saved directly: `PATCH /agents/{id} {avatar,color}`) `:128-147`.
- Name + personal-agent badge; immutable trading pair row (fixed-market agents) `:148-158`.
- Field Name (≤80) `:159-167`.
- Market scope picker (general / default market / keep fixed) for root non-personal agents with
  `BrokerPairPicker` (account + symbol from `GET /trading/connections`, `GET /market/symbols?account_id=`)
  `:168-176`, `components/agent-market-picker.tsx`, `components/broker-pair-picker.tsx:28,53`.
- Mandate control (`AgentPermissions`, settings variant) `:177-187` — see §9.4.
- Model settings (`AgentModelSettings`): `GET /agents/{id}/model/summary`, choose primary / default
  (`PUT /agents/{id}/model {primary,expected_revision}`), ChatGPT plan "Manage usage" link
  `components/agent-model-settings.tsx:25-117`.
- Title (≤160), Description (≤2000, multiline), Instructions (≤16000) `:189-216`.
- Paused switch; «المهارات» → `/skills`; «المهام الدورية» → `/routine` `:217-237`.
- Memory (≤30000, versioned): `GET /agents/{id}/memory` → `PUT /agents/{id}/memory {content,version}`
  `:59-66,90-96`.
- Save → `PATCH /agents/{id} {name,title,description,instructions,paused, + market scope change with
  scope_revision}` `:71-103`. States: loading, `agentMissing`, saved «تم الحفظ», error.

### 4.14 Skills — `app/skills.tsx`, `components/skills/*`
- Catalog page: hint, Refresh, «إضافة مهارة» (create form), current catalog list (available /
  unavailable reason), «المزيد» paging by 50, exact-version block form, revocations list with reason
  VERIFIED `app/skills.tsx:33-60` + body.
- Create: identifier (pattern), title, purpose, version (semver ≤64), instructions → `POST /skills
  {agent_id, payload{name,content,enabled,manifest{…explicit activation, read_only, priority 50,
  context_budget 16000}}}` `components/skills/skill-create.tsx:30-80`.
- Details sheet: activation, dependencies, tools, version, instructions, enabled switch, Save
  (`PUT /skills/{id} {payload,version}`), built-ins read-only; Block version (reason: owner_revoked,
  regression, unsafe, superseded) `POST /agents/{id}/skills/revocations {skill_id,version,
  expected_revision,reason}`; Delete (confirm) `DELETE /skills/{id}` `skill-details.tsx:49-395`.
- Catalog endpoints: `GET /agents/{id}/skills/catalog?offset&limit=50`, `GET .../catalog/{skill}`,
  `GET /skills/{resource_id}`, `GET /agents/{id}/skills/revocations`.
- Availability codes (11) mapped to labels `components/skills/shared.ts:14-29`.
- Missing vs web: version history / restore (`/skills/{id}/versions|restore`) — VERIFIED absent.

### 4.15 Routines — `app/routine.tsx`, `lib/routine.ts`
List (title, «مرة واحدة» + time or cron/interval + timezone, enabled/paused, next run, Edit); Create
(agent picker when new, task text, mode interval minutes 1–525600 / cron (default `0 9 * * 1-5`) /
once (kept), timezone (device default), enabled switch); Save; Delete; History (runs → open
conversation). Endpoints: `GET /routines?agent_id=`, `POST /routines/{agent_id}`, `PUT /routines/{id}`,
`DELETE /routines/{id}`, `GET /routines/{id}/history`. Title derived from task (160 code points)
VERIFIED `lib/routine.ts:11-19`, `lib/routine-title.ts`, `app/routine.tsx` (grep lines 53-313).

### 4.16 «ما أعرفه عنك» owner knowledge — `app/owner.tsx`
Profile lines with origin («قلتَ»/«لاحظه {name}»/«سابقًا»), correct (inline field, bullet kept) or
delete → `POST /owner/profile/lines {version,text,replacement|null}`; learned wake habit
(`GET /app-opens` → «first_open», brief time) with forget → `DELETE /app-opens`; empty «nothingKnown»
VERIFIED `app/owner.tsx:12-221`, endpoints `:45,56,72,86`.

### 4.17 Artifacts / Artifact / Image
- Library: search field, agent filter chips, list (name, mime badge, size, agent, thread) →
  `/artifact`; empty / no results / retry. `GET /artifacts`, `GET /agents`, `GET /threads`
  VERIFIED `app/artifacts.tsx:33-150`.
- Viewer: `GET /artifacts/{id}` + `GET /artifacts/{id}/file` (bearer, bytes); image preview (tap →
  `/image` full screen), text/JSON/XML/YAML selectable monospace (first 1 MB, «previewTruncated»), HTML
  shown as source (native; web iframe sandboxed), PDF → "share to viewer"; Share via `expo-sharing`
  (file written to cache dir `lonora-artifacts/…`, cleaned up); «فتح المحادثة» VERIFIED
  `lib/artifacts.ts:1-140`, `app/artifact.tsx:20-190`, `app/image.tsx`.

### 4.18 Charts — `app/charts.tsx`, `components/chart-sheet.tsx`, `chart-renderer.tsx`, `candlestick-chart.tsx`
- Chart list for thread/agent (`GET /charts?thread_id=`), chip per chart «SYMBOL · TF», create
  (account from enabled `GET /trading/connections`, symbol from `GET /market/symbols?account_id=` —
  never auto-picks first; agent-bound account/symbol locked), 21 MT5 timeframes `1m…1mn`
  (`lib/charts.ts:4-27`), Save → `POST /charts {payload{account_id,symbol,timeframe,indicators:[],
  annotations:[]}}`. VERIFIED `app/charts.tsx:200-300`.
- Scene: `GET /charts/{id}/scene` (candles, quote, indicators series, annotations, revision/scene
  version), refresh button → `POST /charts/{id}/refresh`; live updates on `cloud_charts.scene_updated`;
  quote rows bid/ask/source; «chartUpdated · time»; «chartInitializing»; empty «chartEmpty».
- Renderer: WebView of `<server>/charts/render?locale=` (web `chart-render.tsx`); bridge messages
  `lonora.chart.ready` → app injects `{type:"lonora.chart.scene", scene, account_id, locale}`; page
  answers `lonora.chart.applied {chart_id,scene_version,data_revision}` or `lonora.chart.escape`;
  15 s timeout → native SVG `CandlestickChart` fallback; origin whitelist VERIFIED
  `components/chart-renderer.tsx:9-155`.
- Chart sheet (opened from `/chart` command, action menu «الشارتات», chart links `/charts?chartId=` in
  Markdown, visual action `open_chart`): modes rest / expanded / minimized, drag gesture, Android back;
  hiding never cancels a run or call VERIFIED `components/chart-sheet.tsx:35-123`.

### 4.19 Conversation (thread) — `app/thread.tsx` (1863 lines) and components

**Header** (`components/thread-header.tsx`): back; avatar (agent `BotAvatar` 28 px with live state, or
`GroupAvatar`); title (agent/group name); subtitle «{name} يكتب» in groups; tap title → agent/group
settings; call button (agents only) «اتصال بالوكيل»; actions button; safety pill (agents) VERIFIED
`app/thread.tsx:1420-1466`, `thread-header.tsx:13-94`.

**Action menu** (native sheet / modal fallback `components/action-menu.tsx`): الشارتات (chart sheet) ·
المهام الدورية (agents) · الملفات (`/artifacts?threadId`) · تجربة المحادثة (chat prefs sheet) · إعدادات
الوكيل/المجموعة VERIFIED `app/thread.tsx:1465-1503`.

**Run banner** (first of waiting_input / waiting_takeover / failed (background failures only for model or
quota family)): «{agent} · {status} · {plan limit | error text}» + buttons Manage usage (ChatGPT plan
limit → `https://chatgpt.com/settings/usage`), Cancel, Resume (takeover), Retry (newest retryable,
`retryableFailure`) → `POST /runs/{id}/cancel|resume|retry` VERIFIED `app/thread.tsx:1505-1580`.

**Agent live status strip** (`components/agent-live-status.tsx`, chat pref «حالة الوكيل التفصيلية» off by
default shows only problems/decisions/watch/task): status line (expand), watches with condition·until
and Cancel → `POST /watches/{id}/control {action:"cancel"}`, pending device authorization text, grant
review failed text, tasks with retry/reconcile/needs-review and Pause/Resume/Cancel → `POST
/tasks/control {task_id,action,expected_version}`, broker/market health lines VERIFIED `:110-196`.

**Transcript** (inverted `FlatList`, max width 792, gap 12): items from `conversationTimeline(messages +
outbox, approvals, owner actions, undrawn, receipts)` = `message | approval | owner_action | receipt`
VERIFIED `app/thread.tsx:937-948,1596-1785`.
- Time separators (new day or ≥15 min gap) `packages/core/src/time-separators.ts:6-15`.
- Grouping: same role+agent within 3 min `app/thread.tsx:1752-1760`.
- Streaming preview message `preview:<run>` with `TurnActivity` (observable steps only: queued,
  preparing, thinking, searching, reading, analyzing, executing, writing, learning, sending,
  waiting_input/external, completed, failed, cancelled; tool call rows; chat prefs «الخطوات» and
  «فتح الخطوات») `components/turn-activity.tsx:11`, labels `lib/i18n.ts:59-80`.
- Footer «رسائل أقدم» when ≥100 messages → `GET /threads/{id}/messages?before=<seq>` (page 100)
  `:1406-1418`; empty «waitingMessage»; header «جارٍ الإرسال».
- Jump-to-latest round button in its own band (never over cards) `:1784-1806`; hysteresis 120/64 px.
- Search/push landing: `?around=seq` loads `GET /threads/{id}/messages?around=` and flashes the
  message 1.7 s; «messageGone» if absent `:200-205,909-925,949-963`.

**Message bubble** (`components/message-bubble.tsx`): sender name in groups; command chip (task,
search, summary, skill name); quoted reply (tap → jump); tool result collapsible «نتيجة أداة»; rich
content (`NativeRichResponse`); voice note label «ملاحظة صوتية · m:ss» (no playback); call log
«مكالمة صوتية · m:ss» / «مكالمة فائتة» with tap-to-call-back; attachments (`ArtifactFileCard`, inline
authenticated images); «مُعدّلة» edited mark; reaction chips; outgoing states (uploading ring with
cancel, «لم تُرسل» failed with Retry, queued «بانتظار الشبكة»); peer (agent-to-agent) card; question
body; submit marks for GenUI sends VERIFIED `:58-338`.

**Message menu** (long-press; `components/message-menu.tsx`): six quick reactions 👍 ❤️ 😂 😮 😢 🙏
(`packages/contracts/src/domain.ts:45-47`), Reply, Copy text (toast), «تعديل وإعادة الإرسال» (owner plain
text only, `canEditAndResend`), «تحويل إلى مهمة» (`POST /tasks?agent_id=&thread_id= {title,
description}`); failed message → Retry / Delete; reactions list sheet (who reacted, tap own to remove)
VERIFIED `message-menu.tsx:1-191`, `lib/message-actions.ts:10-50`, `app/thread.tsx:1300-1380`.
Reaction endpoints: `PUT /threads/{t}/messages/{m}/reactions/{emoji}` / `DELETE
/threads/{t}/messages/{m}/reactions` (optimistic, rollback on failure).

**Composer** (`components/thread-composer.tsx`): text field «رسالة»; «+» attach sheet (Files, Photos
(system picker, `image/*`), web search row); web-search globe (tap = off) `PUT /threads/{id}/options
{web_search}`; send; Stop (cancels all active runs `POST /runs/{id}/cancel`); reply preview with
cancel; edit bar with cancel; attachment chips (remove) and upload rings (cancel); suggested reply chip
(agent's `suggested_reply`, `assist` pref); @mentions (agents, «@الكل» during collaboration) →
`mention_agent_ids`, `mention_all`, `collaboration_session_id`; «/» command list: مهمة, بحث, ملخص, شارت,
اتصال, مسح + enabled skills (`GET /skills?agent_id=`) VERIFIED `thread-composer.tsx:1-537`,
`lib/commands.ts:1-99`, `app/thread.tsx:316-334,981-1007,1183-1290`.
- Send body (`POST /threads/{id}/messages`): `{content, attachment_ids, reply_to, mention_agent_ids,
  mention_all, collaboration_session_id?, edited_from?, command?{name,argument,skill_id?},
  client_nonce}`; answer to a question: `{content, reply_to, input_answer{run_id,question_id,choice_id}}`
  VERIFIED `app/thread.tsx:1093-1104,1160-1176`.
- Attachments: ≤10 per message, ≤20 MB each (`packages/core/src/attachments.ts:2`), each uploads alone
  via XHR multipart `POST /artifacts/upload (file, thread_id)` with progress & cancel; a message sent
  while uploads run is posted after they finish; an upload failure returns text+files to the composer
  VERIFIED `lib/api.ts:182-239`, `app/thread.tsx:798-830,1213-1253`.
- Drafts (text, finished attachments, reply) persist per server/owner/thread across restarts
  `lib/draft-store.ts:1-5`.

**Offline queue (Q6)**: plain owner text whose send got no API answer (network error, bare 502/504
`request_failed`) becomes `queued` and is flushed automatically when reads succeed again; toast
«أُرسلت {n} رسائل كانت تنتظر»; answers, edits, card sends and voice never queue; failed ones offer Retry
/ Delete; stable `client_nonce` dedupes; acknowledged when the server returns a message with that nonce
VERIFIED `lib/outgoing-messages.ts:1-55,352-398`, `lib/lists-state.tsx:101-108`, `app/thread.tsx:860-880`.

**Clear chat** (command or list): confirm sheet → `POST /threads/{id}/clear` VERIFIED `app/thread.tsx:1009-1049`.

**Cards in the transcript** (see §9): Owner action card (settle, supervision_paused, secret,
trading_mode), Trade approval, Execution receipt, Peer card, Conversation question (choice buttons).

**Side reads of the snapshot**: `GET /threads/{id}`, `/threads/{id}/messages`, `/runs?thread_id=`,
`/peer-messages?thread_id=`, `/artifacts?thread_id=`, `/trading/approvals?thread_id=`,
`/threads/{id}/collaboration`, `/agents`, `/owner-actions?thread_id=`, `/trading/receipts?thread_id=`,
`/groups` VERIFIED `app/thread.tsx:340-400,488-505,672`.

### 4.20 Chat preferences sheet — `components/chat-prefs-sheet.tsx`, `lib/chat-prefs.ts`
Per device (survive sign-out): Steps (on), Steps open (off), Detailed agent status (off), Assist /
suggestions & mentions (on) VERIFIED `lib/chat-prefs.ts:8-13`, `chat-prefs-sheet.tsx:10-15`.

---

## 5. Sheets, menus, overlays (complete list)

| Sheet / menu | Trigger | File |
|---|---|---|
| New chat | Chats «+» | `components/shell/new-chat-sheet.tsx` |
| New list (2 pages) / edit list / pick chats / add to list | filter «+», chip menu, selection ⋮ | `components/shell/list-sheets.tsx` |
| List chip menu | long-press list chip | `list-sheets.tsx:380-410` |
| Selection ⋮ more | selection toolbar | `components/shell/selection.tsx:220-262` |
| Confirm clear / delete | selection, command, menu | `selection.tsx:60-110`, `app/thread.tsx:1009` |
| Emoji panel (recents, 8 sections, ar/en search) | 😊 in list name | `components/shell/emoji-panel.tsx` |
| Attach «إضافة إلى المحادثة» | composer «+» | `app/thread.tsx:1254-1287` |
| Thread action menu | header ⋮ | `components/action-menu.tsx`, `app/thread.tsx:1467` |
| Chat prefs | action menu | `components/chat-prefs-sheet.tsx` |
| Message menu / failed message / reactions list | long-press / chips | `components/message-menu.tsx` |
| Mandate (trading mode) modal | composer permission chip / settings row | `components/agent-permissions.tsx` |
| Safety pill sheet | header pill | `components/safety-pill.tsx` |
| Chart sheet (rest/expanded/minimized) | /chart, menu, links | `components/chart-sheet.tsx` |
| Avatar studio modal | avatar in bot-settings | `components/avatar-picker.tsx` |
| Broker account/symbol picker | bot-settings market scope | `components/broker-pair-picker.tsx` |
| Skill details | skills list item | `components/skills/skill-details.tsx` |
| Toast (one at a time, «تراجع» action holds while pressed then 2.4 s) | many | `components/shell/toast.tsx:1-2` |
| Heads-up banner | other-chat answer / urgent attention | `components/heads-up.tsx` |
| Voice overlay (full / minimized pill / error) | call | `components/voice-overlay.tsx` |
| Incoming call overlay | ringing call | `components/incoming-call.tsx` |

## 6. Gestures (complete)
- Tap row → open; long-press row → selection; tap in selection → toggle (`thread-row.tsx:192-193`).
- Pull-down on chat list → reveals filters + refresh (`chat-list.tsx:1-2,258`).
- Long-press filter chip (list) → list menu (`chat-list.tsx:95`).
- Long-press message → message menu; accessibility actions «رد»/«خيارات الرسالة» (`message-bubble.tsx:112-115`).
- Tap quote → jump to quoted message; tap reaction chips → reactors.
- Swipe up on heads-up (dy < −24) → dismiss; press-and-hold → pause timer (`heads-up.tsx:123,176-178`).
- Avatar: touch/pointer move → gaze follows for 1.5 s; tap → poke spring + face spin when idle
  (`bot-avatar.tsx:153-176`).
- Transcript drag → keyboard dismiss (`keyboardDismissMode="on-drag"`).
- Chart sheet drag (PanResponder) and hardware back (`chart-sheet.tsx`).
- Android hardware back closes expanded search (`app/(tabs)/index.tsx:154-163`).
- GenUI: Android haptic tick on controls (`components/genui/card.tsx:39-42`).

## 7. States matrix
- **Loading**: `<Loading/>` before session ready; skeleton rows on lists (`SkRows`); «جارٍ الاتصال» text in
  settings pages; thread `Loading` until first snapshot; artifact/chart spinners; GenUI skeleton while
  `building`.
- **Empty**: chats/unread/fav/list empty, archived empty, no groups, no tasks, no routines, no history,
  no artifacts/no results, chart empty, skills none / no revocations, running empty/unknown/stale,
  owner nothing known, thread «waitingMessage».
- **Error**: `ErrorNotice` per screen with `errorText()`; toasts for list actions; network strip
  offline; voice error overlay with close; run banner failures; card-level errors (owner action,
  approval) with re-read on conflict (`OWNER_ACTION_CHANGED`, decided-elsewhere re-read).
- **Offline queue**: per §4.19; list rows show «بانتظار الشبكة…»; network strip shows waiting count.
- **Stale**: GenUI «آخر تحديث HH:MM» after 120 s for texts starting «الآن»/"now"
  (`components/genui/card.tsx:35,137`); running page stale banner.

## 8. Heads-up, push and incoming-call behaviour

### 8.1 Heads-up banner — `components/heads-up.tsx`, `lib/heads-up.ts`
- Source A (owner WS): `message.created` with role assistant, in another thread than the open one,
  created after the app opened (−5 s slack; after reconnect only the last 15 s), not in quiet hours,
  row not muted/archived (`headsUpAllowed`), agent's in-app rule on; text = plain line ≤120 chars;
  groups show «{speaker}:» separately; empty content → «رسالة جديدة» VERIFIED `lib/heads-up.ts:23-58`,
  `heads-up.tsx:136-158`.
- Source B (shell `/attention` poll): `attentionAlwaysShows(importance)` (critical / action required)
  always shows, quiet hours included; placed on its agent/group row, broker-health items on the
  personal agent's row; text = summary or attention label VERIFIED `lib/heads-up.ts:60-83`.
- Rules refreshed: `GET /owner/profile` (reach_me quiet hours) and `GET /agents/notifications`
  (in_app per agent) at sign-in, foreground and ≤1/min VERIFIED `heads-up.tsx:29-75`.
- Display: 5.2 s, held while pressed, 2.4 s after release; slide spring from −160; tap or «رد» opens
  chat; swipe up dismisses VERIFIED `heads-up.tsx:91-127,176-292`.

### 8.2 Push (VISION 11.4) — `lib/push.native.ts`, `components/shell/notifications.ts`
- Only when the build has an Expo project id. Android channel `attention` (importance HIGH) created
  first (Android 13 permission prompt), permission requested if askable; random per-install device id
  `lonora.push.device`; register `PUT /push/devices/{device} {token (Expo push token), platform}`;
  permission denied → `DELETE /push/devices/{device}` VERIFIED `lib/push.native.ts:1-56`.
- Re-sync on every foreground and on push-token rotation `notifications.ts:13-28`.
- Tap → `/thread?id=<thread_id>&around=<int>`; last response cleared after handling; payload carries no
  money facts and no action buttons VERIFIED `lib/push.native.ts:66-95`, `notifications.ts:30-44`.
- Push kinds (server): trade approval, settle operation, secret request, mandate card, broker health,
  background health (6) VERIFIED `packages/contracts/src/attention.ts:36-63`, `VISION.md:845-860`.

### 8.3 Incoming call (foreground only) — `components/incoming-call.tsx`, `lib/incoming-call.ts`
- Polls every 3 s while active and no call is running: `GET /voice/incoming/policy` (enabled? device) →
  `GET /voice/incoming`; shows the first `ringing` unexpired call VERIFIED `:33-73`.
- Overlay: «لونورا يريد التحدث معك», reason, «رد» (accept) / «رفض» (reject) → `POST
  /voice/incoming/{id}/respond {action, device_id}`; accept + accepted & `execution_authorized:false` →
  `GET /agents/{agent_id}` → voice start with `incoming_call_id`; «الرد برسالة» hides it locally and opens
  the thread VERIFIED `:74-148`. Labels in `lib/incoming-call-labels.json` («limited»: background/closed-app
  calls not configured).

## 9. Fixed cards and trading controls

### 9.1 Owner action card — `components/owner-action-card.tsx` (spec from `packages/core/src/owner-actions.ts`)
- Kinds: `settle_operation`, `supervision_paused`, `secret`, `trading_mode` VERIFIED
  `packages/contracts/src/owner-actions.ts:5-10`; statuses pending/confirmed/cancelled/expired/superseded.
- Rendered from `ownerActionCard(row, locale)` → `{title, lines, hint, options (choices with details),
  secret form, signIn (ChatGPT), buttons, outcome, passkey}`; options persist the grant delegation choice
  via decision; buttons → `POST /owner-actions/{id}/decision {decision: confirm|cancel, outcome?
  (executed|not_executed|unknown), trading_mode?}` VERIFIED `owner-action-card.tsx:112-140`.
- Secret card: fields (secret or plain, role labels token/api_key/server_url/feed_url, required), values
  posted once to `POST /owner-actions/{id}/secret {values}` and cleared; agent learns only "saved"
  VERIFIED `owner-action-card.tsx:150-156,297-327`, `packages/core/src/owner-actions.ts:738`.
- ChatGPT plan sign-in on a secret/model card: Continue → `POST /owner-actions/{id}/chatgpt/start` →
  opens `authorization_url` in the browser → owner pastes the landing address
  (`http://127.0.0.1:1455/auth/callback…`) → `POST /owner-actions/{id}/chatgpt/finish`; "another account"
  VERIFIED `owner-action-card.tsx:159-176,329-375`, `packages/core/src/chatgpt-plan.ts:117-140`.
- Passkey: device enrollment inline if `device_registration_required` (`POST /auth/devices/enrollment`
  + verify). Server: no remaining card needs a passkey (`owner_action_passkey_not_needed`) VERIFIED
  `apps/api/src/lonora_api/routes/owner_actions.py:11,108-109`.
- «طلب جديد» on expired settle → `POST /owner-actions/{id}/renew`; «عرض الأحدث» scrolls to the newer card
  VERIFIED `app/thread.tsx:705-726`, `owner-action-card.tsx:416-420`.
- Trust frame when drawn inside a GenUI Slot («بطاقة ثابتة من Lonora») VERIFIED `components/genui/nodes.tsx:853-892`.

### 9.2 Trade approval card — `components/trade-approval.tsx`
Requests (action label, symbol, volume), fact rows (entry / at market, SL, TP, clear SL/TP, ticket),
agent's reason (labelled), tolerance/validity, Approve / Reject → `POST
/trading/approvals/{id}/decision {decision: approve|reject}`; on failure re-reads `GET
/trading/approvals?thread_id=`; decided states with broker words and result lines; also shown in the
voice overlay (last 5) VERIFIED `trade-approval.tsx:23-219`, `components/voice-overlay.tsx:73-151`.
Missing vs web: renew of an approval (`POST /trading/approvals/{id}/renew`) — VERIFIED absent.

### 9.3 Execution receipt — `components/execution-receipt.tsx`
Broker-confirmed facts only (ticket, action, volume, fill price / new values / cancel), agent's reason
labelled, owner's own order labelled; from `GET /trading/receipts?thread_id=` VERIFIED `:10-15`.

### 9.4 Mandate control (trading mode Full/Ask) — `components/agent-permissions.tsx`
Shown only when `showsTradingControl` (trading template or connected account) — no account, nothing
(Q9). Composer chip (shield = Ask, alert = Full) / settings row opens a modal: «الآن: …», mode line,
button for the other mode → requires the live Mandate card: `GET /owner-actions/mandate?agent_id=`
(read never raises), «show the card» `POST /owner-actions/mandate?agent_id=`, apply `POST
/owner-actions/{card}/decision {decision:"confirm", trading_mode}` → toast `modeChangeLine` (withdrawn
approvals count) VERIFIED `agent-permissions.tsx:27-120`, `lib/mandate-mode.ts`.

### 9.5 Safety pill — `components/safety-pill.tsx`
One pill per agent thread from `trading_readiness` (tone + line), sheet with per-account items; reads
`GET /trading/connections` for account labels VERIFIED `:1-40`.

### 9.6 Removed control (Amendment 1)
None. The global Stop control was removed by owner Amendment 1 (2026-11-12) and migration
`0150_remove_stop.py` VERIFIED `VISION.md:723-736`, `packages/db/migrations/versions/0150_remove_stop.py:1-56`.
Owner controls are: Mandate (Full/Ask per agent), agent pause (`PATCH /agents/{id} {paused}`), pause/
cancel of tasks and watches, broker connection, workspace Stop / Stop all.

---

## 10. GenUI v2 renderer — `components/genui/{card,nodes,host,theme}.tsx`

Contract (generated, do not edit): `packages/contracts/src/genui-catalog.ts`; document type
`packages/contracts/src/genui.ts`; validator `packages/core/src/genui/spec.ts`; expression evaluator
`packages/core/src/genui/expr.ts` + functions `packages/core/src/genui/functions.ts`; card markdown
`packages/core/src/genui/markdown.ts`; submit/lock rules `packages/core/src/genui/submit.ts`; doc
`docs/genui.md`.

### 10.1 Document (`UiDocument`, VERIFIED `genui.ts:36-53`)
`{v:2, kind (calculator|form|picker|chart|choice|checklist|quiz|timer|diagram|summary), title, sub?,
icon, mode? (observed|example|estimate), currency?, account_id?, agent_id?, facts{key:{value,source,
observed_at?,account_id?}}, state{}, calc{name: expr|literal}, blocks[], why?, fallback}`; part
`{type:"ui", document, building?, cut?}`.

### 10.2 Node types and props (VERIFIED `genui-catalog.ts:5-99`, renderer map `nodes.tsx:946-1007`)
| Node | Props (required*) | Native renderer function |
|---|---|---|
| Segmented | bind*, label*, options*, when | `Segmented` `nodes.tsx:162` |
| Select | bind*, label*, options*, when | `Select` `:239` (radio list) |
| Number | bind*, label*, hint, prefix, suffix, required, when | `NumberField` `:313` (Enter → primary send) |
| Slider | bind*, label*, min, max, step, show, when | `Slider` `:417` |
| Text | text*, tone, size, when | `TextNode` `:504` |
| Title | text*, when | `Title` `:518` |
| Markdown | text*, when | `MarkdownNode` `:529` (paragraphs, ul/ol, bold; links as text) |
| Note | text*, tone, icon, when | `Note` `:574` |
| Badge | text*, tone, icon, when | `Badge` `:552` |
| KeyValue | rows* (1–8), when | `KeyValue` `:608` |
| Stat | label*, value*, sub, trend, tone, icon, when | `Stat` `:642` |
| Button | label*, action, style, icon, full, disabled, when | `Button` `:704` |
| Divider | when | `Divider` `:846` |
| Row / Col | children*, when | `RowNode` `:747` / `Col` `:755` |
| Grid | children*, cols, when | `Grid` `:763` |
| Card | children*, title, icon, when | `Card` `:794` |
| More | children*, label, when | `More` `:814` (disclosure) |
| Slot | card* (`trade_approval|settle|mandate|secret`), record* | `Slot` `:853` (live fixed card in trust frame) |
| Delivery (server-only row) | channels (app|push|call) | `Delivery` `:893` (read-only checked rows) |

Options: scalar or `{value,label?,also?}`; tones `info|good|warn|bad|muted|accent`; icons = keys of
`packages/ui-tokens/src/icons.ts` (104 stroke paths, 24-unit viewBox, stroke 1.7) drawn by `CardIcon`
`nodes.tsx:56-71`.

### 10.3 Actions (VERIFIED `genui-catalog.ts:30-35`, `genui.ts:18-25`, `card.tsx:226-268`)
`send {intent, data?, lock?}` → `POST /threads/{id}/messages {ui_submit:{source_message_id, part,
path, values}, client_nonce}` immediately (never via offline queue) `card.tsx:158-161`, `app/thread.tsx:757-790`;
`go {route}` with routes market→`/charts`, tasks→`/tasks`, usage→`/account`, files→`/artifacts`,
agents→`/agents` `card.tsx:28-34`; `set {key,value}`, `toggle {key}`, `reset`, `copy {text}` (clipboard,
template-rendered), `open {url}` (https only). Lock/unlock: a locking send locks the part; «تعديل» →
`POST /threads/{t}/messages/{m}/ui-state/{part}/unlock` `card.tsx:270-280`. Marks «مُعدّلة» / «لم يُنفَّذ».

### 10.4 Behaviour
Fail-closed validation; `when` visibility; required check before send; controls disabled while
`building`, uncommitted or sending; locked cards keep only go/open/copy; `cut===0` shows `fallback`
text; footer: lock/unlock, cut notice, «لماذا؟» why panel (with observed time); stale text rule (120 s);
Android vibration tick; values persisted in `ui_state`; budgets (6 blocks, 560 px resting, 720 px hard)
are server-side VERIFIED `card.tsx:35-450`, `docs/genui.md:180-203`. Palette from the theme tokens
(`theme.ts`: accent, tone backgrounds, `slotFrame = mix(accent .55, line-strong)`) VERIFIED `theme.ts:52-74`.

Expression functions (VERIFIED `functions.ts:144-179`): Abs, Allocate, Avg, Ceil, Change, Clamp, Count,
Cumulative, DayLabel, Default, Fact, Filter, First, Floor, Fmt, If, Includes, Join, Last, Len, Max, Min,
Money, MovingAvg, Pct, Pick, Plural, Pow, Range, Round, Score, Signed, Sqrt, Sum, Take, Random.

---

## 11. Rich responses (v1 documents, Markdown, code, tables, images, charts)

- Message `rich_content {version:1, parts:[text | ui(v1 VisualDocument) | ui(v2 UiPart) | voice | call |
  command]}` VERIFIED `packages/contracts/src/visual-response.ts:130-141`. Dispatch: text → `Markdown`,
  v2 → `NativeUiCard`, v1 → `NativeVisualDocument` `components/native-rich-response.tsx:75-118`.
- **v1 node kinds** (all drawn, VERIFIED `native-rich-response.tsx:308-740`): column, row, grid, card,
  container, divider, text, heading (levels → font 22/20/18/16), badge, icon, metric, table (fields,
  rows, filter_key, horizontal scroll), list, progress, timeline, diagram (vertices/edges SVG), chart
  (`chart_kind` line|bar|pie, SVG, height 200), image (artifact id, authenticated), disclosure, tabs,
  button, select, checkbox, slider, input (text|number), form. Values: scalars, `{state}`, `{source}`
  (fact), `{op, args}` with 27 operators `visual-response.ts:4-33`. Actions: `follow_up {text}` (sends a
  message), `open_chart {resource_id}`, `open_artifact {resource_id}` `app/thread.tsx:1695-1709`.
  Mode ≠ observed shows a label; observed facts list their times. Local state persisted per
  owner+document in files (`lib/visual-state.ts`, ≤100 KB).
- **Charts/diagram geometry**: `components/native-rich-graphics.tsx:27-260` (pad 28, min/max with 0
  baseline, pie arcs, bar width 65 %, diagram label wrap 20 chars).
- **Markdown (native, `components/markdown.tsx`)**: fenced code blocks (language label, monospace, LTR,
  selectable), headings `#`–`###`, bullets `-`/`*` → «•», inline `**bold**`, `` `code` ``, links
  `[text](https://…)` and `[text](/charts?…)` (chart links open the chart sheet), signed numbers;
  direction per message (any Arabic letter → RTL) VERIFIED `markdown.tsx:1-146`. **Not supported natively**:
  tables, blockquotes, ordered lists, images, nested lists (VERIFIED by reading the parser; the web
  `conversation/Markdown.tsx:151` renders tables, quotes, lists; `packages/chat-ui/src/markdown-table.tsx`).
- Images: attachment cards fetch bytes with bearer (never credentials in URLs) `components/artifact-file-card.tsx:1`;
  duplicates hidden when a v1 document already shows the image `native-rich-response.tsx:58-73`.

---

## 12. Avatar — `components/bot-avatar.tsx`, `components/avatar-picker.tsx`, `components/group-avatar.tsx`, `packages/core/src/{trading-avatar-motion.js,avatar-motion.ts,avatar-state.ts,avatar-geometry.ts}`

### 12.1 What defines a Lonora avatar (VERIFIED)
| Parameter | Source | Values |
|---|---|---|
| Face (`Agent.avatar`) | `packages/contracts/src/domain.ts:25` | `orb` (the 4 signal bars) or one of 15 faces: face-smile, face-thoughtful, face-happy, face-wink, face-sleepy, face-surprised, face-angry, face-playful, face-excited, face-skeptical, face-dreamy, face-focused, face-worried, face-laugh, face-determined; unknown → `orb` (`trading-avatar-motion.js:62-86`) |
| Shell colour (`Agent.color`) | `domain.ts:26` | palette id/name/hex (11: white #FFFFFF, violet #8B5CF6 (default), green #10B981, orange #F97316, cyan #06B6D4, blue #3B82F6, yellow #EAB308, brown #8D6E63, red #EF4444, magenta #EC4899, gray #64748B) or any custom `#rgb/#rrggbb`; empty → palette colour chosen by FNV hash of identity (`avatar-geometry.ts:242-381`) |
| Identity (`Agent.id`) | `bot-avatar.tsx:61-62` | seeds deterministic personality (phase, direction, tempo, cycle, spin seconds, gaze frequencies/amplitudes) `trading-avatar-motion.d.ts:236-249` |
| State | `AvatarStateId` (20): thinking, executing, inspecting, writing, searching, working, listening, reviewing, waiting, angry, sending, speaking, success, error, warning, analyzing, learning, sleeping, celebrating, connecting | `trading-avatar-motion.d.ts:1-21`; mapping from run activity (`turnActivity().avatar`), WS connection (connecting), live state (`liveAvatarState`), voice (`avatarState`: connecting/speaking/listening/waiting/error) `avatar-state.ts:4-24`, `app/thread.tsx:1438-1452` |
| `trades_on_its_own` | `domain.ts:14` | gold ring `#f0c866` 2 px (inset −3) + crown badge (path `M4 7 7 9 10 4 13 9 16 7 14 14H6Z`) `bot-avatar.tsx:301-325` |
| paused / reduced motion / background | `bot-avatar.tsx:70-96` | static first frame |

No image avatar and no shape choice in the live renderer. `AVATAR_SHAPES` (hex, wedge, squircle, tablet,
pebble, blob, teardrop, cloud) and `organicAvatarPath` in `avatar-geometry.ts:16-225` are only
re-exported by `packages/ui-web/src/avatar-geometry.ts` — INFERRED legacy, not used by `BotAvatar`.

### 12.2 SVG geometry (VERIFIED `trading-avatar-motion.js:23-31`, `bot-avatar.tsx:197-300`)
- viewBox `22 22 356 356`; shell circle `cx200 cy200 r177` filled with the resolved colour hex.
- Shade overlay: radial gradient `cx34% cy27% r95%`: white α.40 @0, white α0 @.38, black α0 @.60, black
  α.42 @1.
- Content clipped to the sphere; visor rect `x78 y123 w244 h155 rx77.5` fill `#0d0d11`, transformed by
  gaze (`faceTransform(gx,gy,poke)` → tx, ty, rot, skewY, sx, sy around (200,200.5)) and turn
  (`avatarTurn(yaw)` → tx, scaleX, opacity).
- Glyph: N bars/particles from `AvatarMotion.frame(dt)` → `BarPose{cx,cy,L,th,k,w,o,r,g,b}`; each drawn
  as a stroked polyline `avatarBarPath` (segment points of an arc of curvature k, scaled by
  `GLYPH_SCALE = 1.1` around (200,200.5)), round caps, width `w×1.1`, rgb colour, opacity `o`
  `avatar-motion.ts:108-122`. Rest pose: 4 bars at x 140/180/220/260, width 26, centre y 200.5, floor
  241, heights 39/60/81/49.
- "Goo" filter (only when size ≥ 48): Gaussian blur 1.65 (faces: `FACE_TOKENS.render.gooBlur`) → alpha
  matrix `0 0 0 20 −9.5` → glow blur 5 (faces: `glowBlur`) with opacity → merge.
- Gloss: ellipse `cx150 cy82 rx86 ry38 rotate(−24)` radial white α.5→0, opacity .55.
- Facial tokens (stroke hierarchy primary 17.68, curved eye 14.144, mouth 11.44, brow 8.32, accent 7.54;
  eye half spacing 42; safe area 114.6,136.95,170.8×127.1) VERIFIED `docs/avatar-facial-geometry.md:15-33`.
- Motion: 30 fps; morph 0.95 s with 0.07 s stagger between signals (`MORPH`); idle (`waiting`)
  `idleAvatarPose` gaze + occasional full turn; tap reaction `faceReaction`; poke decays exp(−12 t).

### 12.3 Native rendering recipe (INFERRED for Flutter)
Port `poseAt / planMorph / morphSegment / loopSeconds / avatarPersonality / idleAvatarPose /
faceReaction / faceTransform / avatarTurn / segmentPoints` from `trading-avatar-motion.js` (1936 lines,
pure math, DOM only in `mount/markup`) to Dart, then paint with a `CustomPainter`: circle + radial
shade, clipped visor with matrix transform, stroked paths with `MaskFilter.blur` approximating the goo
filter, gloss ellipse, optional gold ring/crown. Alternative: run the JS sampler in a JS engine and
paint frames. Group avatar = clustered member avatars (`group-avatar.tsx`).

### 12.4 Avatar studio (mobile) — `components/avatar-picker.tsx`
Modal: live preview, face grid (16 with ar/en labels `lib/i18n.ts:6-31`), all 11 palette colours
(web shows only the first 7, `apps/web/src/shell/agent/AvatarSheet.tsx:14-15`), Reset (violet), Done /
Cancel; saves `PATCH /agents/{id} {avatar,color}` without touching other fields VERIFIED
`avatar-picker.tsx:11-80,253,315`.

---

## 13. i18n system (exact files and structure for the Dart port)

### 13.1 Mobile catalog
| File | Keys | Format |
|---|---|---|
| `apps/mobile/lib/i18n.ts` | 590 own keys + spreads `...shellLabels, ...shellExtraLabels` at `:978-979` | `export const labels = { key: ["<ar>", "<en>"], … } as const` (`:5`); index 0 = ar, 1 = en |
| `apps/mobile/lib/labels-shell.ts` | 176 keys, all `sh_` prefixed ("taken from the web catalog") | same tuple format, `export const shellLabels` |
| `apps/mobile/lib/labels-shell-extra.ts` | 2 keys (`sh_tickSent`, `sh_tickRead`) | same |
| `apps/mobile/lib/incoming-call-labels.json` | 16 keys × {en, ar} | `{ "en": {key: text}, "ar": {key: text} }` |
| `apps/mobile/lib/attention-labels.ts` | 29 attention codes → label keys; model-access reasons → `{provider}` labels | map + `attentionTitle()` |

VERIFIED counts by parsing (`^\s{2}key: [`), and `lib/i18n.ts:980-1023`.
- `translate(locale,key)` = `labels[key][locale==="ar"?0:1]` (`:982-984`); `Label = keyof typeof labels`.
- Placeholders: positional `{0}`, `{1}` and named `{count}`, `{name}`, `{provider}`, `{brief}`,
  `{firstOpen}`, `{q}`; `fill(template, ...values | {named})` (`:986-996`).
- Plurals: hand-written functions with Arabic count bands — `chatsWord` (1 / 2 / 3–10 / 11+),
  `waitingSentText` (same), `agentsWord` (1 / 2 / 3–10 / 11–99 / 100+) (`:997-1023`). GenUI has
  `Plural(count, one, two, few, many, zero)` and `arCount` (`packages/core/src/genui/functions.ts:283`).
- Error codes double as label keys (e.g. `broker_account_already_connected`, `skill_version_revoked`,
  `voice_permission_denied`, `request_failed`, `network`); see precedence in §2.2.
- Locale: default `ar`; stored `lonora.locale`; toggled on sign-in and in Account. `rtl = locale==="ar"`.

### 13.2 Shared text in `@lonora/core` (also ported to Dart — same words on web)
Pattern `{en:{…}, ar:{…}}` objects or `Record<code,{en,ar}>`, selected by `language(locale)` (`ar*` → ar):
`owner-actions.ts` (`ownerActionText`, card specs, `ownerActionError`), `owner-profile.ts`
(`ownerProfileLabel`, reach-me labels/hints, reply languages, `ownerProfileError`),
`financial-boundary.ts` (`financialBoundaryError`, operation/approval status, `runStatusText`),
`agent-permission-errors.ts`, `agent-status.ts`, `agent-model.ts`, `capabilities.ts`, `chatgpt-plan.ts`,
`trading-readiness.ts` (`tradingSafetyText`, `isolate`, `listSeparator` «، »), `turn-activity.ts`,
`order-line.ts`, `time-separators.ts`, `account-authority-labels.ts`, `trade-action-labels.ts`,
`composer-commands.ts` VERIFIED (grep of `ar:` in `packages/core/src`).

### 13.3 RTL and bidi rules (VERIFIED)
- The app does **not** flip native layout; each row mirrors manually (`flexDirection: rtl ?
  "row-reverse" : "row"`, `textAlign`) and chevrons are scaled `scaleX` (`lib/session.tsx:99-104`,
  `app/agents.tsx:73`). Flutter's `Directionality` mirrors automatically — port these as plain `Row`s.
- Content direction is per text: any Arabic letter → RTL, Latin-only → LTR, else interface
  (`lib/text-direction.ts:1-12`).
- Numbers, tickers and names inside sentences are isolated with FSI/PDI U+2068/U+2069
  (`packages/core/src/trading-readiness.ts:18-23`); command lines with LRI U+2066
  (`app/(settings)/running.tsx:35`); slash commands get an LRM `‎/` (`app/thread.tsx:1078-1083`).
- URLs, emails, server, code, tokens are forced LTR fields.
- Dates/numbers via `Intl` (`toLocaleString(locale)`, `formatTimeSeparator`), Latin digits for HH:mm
  in rows (`thread-row.tsx:25`).

### 13.4 Porting plan facts (INFERRED)
Generate ARB (`app_ar.arb`, `app_en.arb`) from the TS tuples (key → ar/en), translate `{0}` →
`{p0}` named ICU args, replace the plural helpers with ICU `plural` (Arabic `zero/one/two/few/many/
other` — note only `agentsWord` has an 11–99 "many" band), and port the `@lonora/core` text
modules as Dart maps keyed by the same codes so server error codes keep resolving.

---

## 14. Voice call flow (`lib/voice-session.tsx`, `lib/voice-transport.ts`, `lib/voice-device.native.ts`, `components/voice-overlay.tsx`)

1. Start (header call, `/اتصال` command, call-back on a call log, accepted incoming call). If a call
   exists → un-minimise. `GET /voice/status` → `transport_configured` else `voice_transport_unconfigured`
   VERIFIED `voice-session.tsx:155-168`.
2. Device: native modules `WebRTCModule` + `InCallManager` present else `voice_native_unavailable`;
   Android `RECORD_AUDIO` runtime permission else `voice_permission_denied`; `RTCPeerConnection({})`
   VERIFIED `voice-device.native.ts:6-22`.
3. Connect: mic `getUserMedia({audio:true})` → `InCallManager.start({media:"audio",auto:true})` +
   speakerphone → add track → data channel `oai-events` → offer → wait ICE complete (10 s) → `POST
   /voice/sessions {agent_id, thread_id, mode:"gpt_live", client_nonce, sdp, incoming_call_id?}` →
   `{session_id, sdp}` → set remote answer VERIFIED `voice-transport.ts:49-127`.
4. Live: data channel events `session.started` (connected), `session.output_audio.delta` /
   `session.output_transcript.delta` (speaking), `error`, `session.closed`; `getStats()` every 150 ms →
   input/output audio levels → phase listening/speaking (650 ms hold) VERIFIED `:62-80,153-176`.
5. Overlay: avatar (state from voice), 7-bar level meter in agent colour, Mute/Unmute (track disabled +
   `InCallManager.setMicrophoneMute`), End, Minimise (pill at top with avatar + name; auto-minimise on
   route change); pending trade approvals of the origin thread polled every 2 s (`GET
   /trading/approvals?thread_id=`, `GET /agents/{id}`) and decidable in the overlay VERIFIED
   `voice-session.tsx:95-153`, `voice-overlay.tsx:12-154`.
6. End: send `{type:"session.close"}` on the channel, wait ≤2.5 s for `session.closed`, then `DELETE
   /voice/sessions/{id}` (or `POST /voice/cancel-initialization {client_nonce}` if not created); stop
   tracks, InCallManager.stop, close peer; app to background ends the call (no background mic)
   VERIFIED `voice-transport.ts:186-238`, `voice-session.tsx:84-93`.
- Not in mobile (VERIFIED absent): live transcript, interrupt (`POST /voice/sessions/{id}/interrupt`),
  speaker selection, voice-note recording.

## 15. OTA / update logic (`lib/ota.ts`, `lib/ota-checker.ts`, `docs/mobile/ota.md`)
Native ON_LOAD check at launch; on every return to foreground a JS check at most every 10 min
(`interval` default `10*60*1000`), if `isAvailable` or `isRollBackToEmbedded` → `fetchUpdateAsync`
(download only); activation on the next cold launch; never reloads a live call/conversation; disabled on
web, dev and when Updates disabled VERIFIED `ota.ts:1-25`, `ota-checker.ts:1-33`, `docs/mobile/ota.md:5`.
Server: signed manifests (RSA, pinned cert), unknown runtime → 204, rollback directive VERIFIED `docs/mobile/ota.md:1-30`.

## 16. Deep links
- `lonora://connect?server=…&token=…` (§4.2).
- Any expo-router route is linkable via scheme `lonora://<route>?…` (e.g. `lonora://thread?id=…&around=…`)
  — INFERRED (expo-router default with `scheme: "lonora"`, `app.config.ts:27`).
- Push data `{thread_id, around}` → `/thread` (§8.2).
- Outbound links to web settings: `<server>/app?settings=models|voice|integrations`
  (`app/(settings)/models.tsx:171`, `voice.tsx:255`, `integrations.tsx:253`, `broker-pair-picker.tsx:99-103`).
- ChatGPT authorization URL and `https://chatgpt.com/settings/usage` open in the browser.

## 17. Theme and tokens used by mobile
`lib/theme.tsx` uses `reference.dark` / `reference.light` (`packages/ui-tokens/src/reference.ts`) as
`c.*` (bg, surface, raised, fill, line, text, muted, faint, primary, on-primary, accent `#22e3a8`,
accent-ink, bubble-in/out, red, amber, violet, glass…); older screens use `components/ui.tsx` legacy
`appearance` palette (`packages/ui-tokens/src/appearance.ts`); visual metrics `visual.ts`; first launch
follows device scheme, then saved choice VERIFIED `lib/theme.tsx:1-85`, `components/ui.tsx:1-43`.

---

## 18. Feature → endpoint map (mobile)

| Feature | Endpoints |
|---|---|
| Onboarding / auth | `GET/POST /onboarding`, `POST /auth/mobile/login`, `GET /auth/session`, `POST /auth/logout` |
| Shell data / inbox | `GET /agents`, `GET /groups`, `GET /threads/inbox`, `GET /chat-lists`, `GET /threads/settings`, `GET /runs`, `GET /attention`, `GET /attention/view`, `POST /app-opens` |
| Live events | `WS /ws/events` |
| Open chat | `POST /agents/{id}/conversation`; group: `GET /groups/{id}`, `GET /threads/{id}`, `GET /threads`, `POST /threads` |
| Thread prefs / lists | `POST /threads/prefs`, `POST /threads/{id}/read`, `POST /threads/{id}/clear`, `PUT /threads/settings`, `POST/PUT/DELETE /chat-lists…`, `PUT /chat-lists/{id}/members` |
| Search | `GET /search` |
| Conversation | `GET /threads/{id}`, `GET /threads/{id}/messages[?before|around|limit]`, `POST /threads/{id}/messages`, `GET /runs?thread_id=`, `POST /runs/{id}/cancel|resume|retry`, `GET /peer-messages?thread_id=`, `GET /threads/{id}/collaboration`, `PUT/DELETE …/reactions`, `PUT /threads/{id}/options`, `GET /skills?agent_id=`, `POST /tasks?agent_id=&thread_id=` |
| Attachments / files | `POST /artifacts/upload`, `GET /artifacts[?thread_id]`, `GET /artifacts/{id}`, `GET /artifacts/{id}/file` |
| GenUI | `POST /threads/{id}/messages` (`ui_submit`), `POST /threads/{t}/messages/{m}/ui-state/{p}/unlock` |
| Owner action cards | `GET /owner-actions?thread_id=`, `POST /owner-actions/{id}/decision`, `POST /owner-actions/{id}/secret`, `POST /owner-actions/{id}/renew`, `POST /owner-actions/{id}/chatgpt/start|finish`, `GET/POST /owner-actions/mandate?agent_id=` |
| Trading cards | `GET /trading/approvals?thread_id=`, `POST /trading/approvals/{id}/decision`, `GET /trading/receipts?thread_id=`, `GET /trading/connections` |
| Agent state | `GET /agents/{id}/state`, `POST /watches/{id}/control`, `POST /tasks/control` |
| Agent settings | `PATCH /agents/{id}`, `GET/PUT /agents/{id}/memory`, `GET /agents/{id}/model/summary`, `PUT /agents/{id}/model`, `GET /market/symbols?account_id=` |
| Skills | `GET /agents/{id}/skills/catalog[/{skill}]`, `GET/POST /agents/{id}/skills/revocations`, `GET/PUT/DELETE /skills/{id}`, `POST /skills` |
| Routines | `GET /routines`, `POST /routines/{agent}`, `PUT/DELETE /routines/{id}`, `GET /routines/{id}/history` |
| Groups | `POST /groups/create`, `PUT /groups/{id}` |
| Charts | `GET /charts`, `POST /charts`, `GET /charts/{id}/scene`, `POST /charts/{id}/refresh`, web page `/charts/render` |
| Owner knowledge | `GET/POST /owner/profile/lines`, `GET/DELETE /app-opens` |
| Notify / reach-me | `GET /owner/profile`, `PUT /owner/preferences`, `POST /auth/devices/enrollment[/verify]`, `GET /agents/notifications` |
| Push | `PUT/DELETE /push/devices/{device}` |
| Voice | `GET /voice/status`, `POST /voice/sessions`, `DELETE /voice/sessions/{id}`, `POST /voice/cancel-initialization`, `GET /voice/incoming/policy`, `GET /voice/incoming`, `POST /voice/incoming/{id}/respond` |
| Settings | `GET /usage/summary`, `GET /settings/models`, `GET /providers`, `GET /capabilities`, `POST /trusted-sources/{id}/revoke|restore`, `POST /trusted-sources/mcp/{c}[/preview]`, `DELETE /integrations/{id}`, `GET /workspace/running`, `POST /workspace/running/stop[-all]` |
| OTA | `GET /mobile/updates`, `GET /mobile/updates/assets/{file}` |

## 19. Observations / gaps in the Expo app (for parity planning)
- README "Current scope" still says provider/integration config, execution controls, boards,
  skills/scratchpad/knowledge editing and realtime voice are web-only (`apps/mobile/README.md:68`); skills
  management and native calls now exist (VERIFIED `app/skills.tsx`, `lib/voice-transport.ts`) — the README
  is partially outdated.
- No playback of voice notes, no recording, no camera (blocked), no Markdown tables, no
  `/attention/seen`, no `/threads/read-all`, no trade-approval renew, Tasks tab = runs only, no files
  editing, no knowledge/goals/scratchpad, no usage dashboard, no provider/broker/MCP setup, no owner
  profile form/revisions, no per-agent delivery rules, no accessibility/app-lock prefs (VERIFIED by
  endpoint grep; details in `lonora-web-inventory.md`).
