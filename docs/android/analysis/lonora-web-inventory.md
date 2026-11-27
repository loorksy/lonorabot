# Lonora Web (`apps/web/src`) — capabilities the Expo app lacks, i18n catalog and design tokens

Purpose: list every owner capability of the web client that the Expo companion does not offer (so the
native Android app can preserve **all** Lonora capabilities), with entry point, screens/dialogs,
actions, states, API endpoints (under `/api`) and security gating. Also: the web i18n catalog and
`packages/ui-tokens`.

Legend: **VERIFIED** = read in the cited file (`path:line`); **INFERRED** = deduced. Mobile parity:
✅ present in Expo, ◐ partial / read-only, ✗ absent (by endpoint grep over `apps/mobile`).

Why it matters (VERIFIED `VISION.md:801-803`): in Lonora Cloud "the owner uses the native app … Once the
app offers every owner capability of the web client (section 13), the web client may be switched off".

---

## 1. Web architecture facts

- **Route model**: four roots `chats | updates | tasks | settings` and inner pages `agents, agent, identity,
  trades, group, recovery, artifacts, archived, market, trading, routines, knowledge, knowledge-edit, memory,
  goals, new-goal, new-schedule, task, new-task, skills, skill, new-skill, file-edit, new-group, owner,
  running, lab (dev), call, incoming, accessibility, chat-prefs, notify-settings, voice-settings,
  communication, integrations, providers, provider, models, mcp, broker, broker-account, usage,
  usage-detail, storage, privacy`; chat routes `/app/<agentId>` and group; aliases board→tasks,
  notifications/activity→updates, account→settings, capabilities→integrations, search→/app VERIFIED
  `apps/web/src/shell/routes.ts:1-73`. Page → component mapping VERIFIED `apps/web/src/shell/pages.tsx:221-345`.
  `?settings=<tab>` on any route opens the moved settings page (`pages.tsx:479`) — the Expo app links here.
- **Auth**: cookie session `POST /auth/login` (returns csrf), `GET /auth/session`, `POST /auth/logout`;
  mutating requests send `X-CSRF-Token` from cookie `lonora_csrf` VERIFIED `lib/auth.ts:5-17`,
  `lib/api.ts:50-56,148-153`. Server dependency `require_owner` (bearer or cookie; CSRF for cookie
  writes; ensures the personal agent) on all 188 owner routes VERIFIED
  `apps/api/src/lonora_api/middleware/auth.py:16-27`.
- **Live data**: Server-Sent Events `GET /api/events/stream?cursor=&live=true` (mobile uses `WS /ws/events`)
  VERIFIED `lib/events.ts:46`.
- **Shell reads**: `/agents`, `/groups`, `/threads/inbox`, `/chat-lists`, `/threads/settings`, `/runs`,
  `POST /app-opens` VERIFIED `shell/Shell.tsx` (grep), `shell/Shell.tsx:95`.
- **Agents are created only from chat** by Lonora (`agent_create` tool); no client calls `POST /agents`
  VERIFIED `docs/agents-from-chat.md:1-30`, grep.

---

## 2. Page map with mobile parity

| Web page (route) | Component | Mobile |
|---|---|---|
| Chats list, archived, unified search, custom lists, selection | `shell/lists/*` | ✅ |
| Updates «يحتاج انتباهك» | `shell/domain/UpdatesPages.tsx:15-17` (`GET /attention/view`) + seen (`providers/AttentionProvider.tsx:75` `POST /attention/seen`) | ◐ (no seen) |
| Tasks root (Task system) | `shell/domain/TasksPages.tsx:50-328` | ✗ (mobile shows runs) |
| Settings root | `shell/settings/SettingsRoot.tsx:286-430` | ◐ |
| Agents | `shell/AgentsPage.tsx` | ✅ |
| Agent info | `shell/agent/AgentPage.tsx:60-381` | ◐ |
| Identity & model | `shell/agent/IdentityPage.tsx:21-340` | ◐ |
| Trades (positions, order log) | `shell/agent/TradesPage.tsx:87-445` | ✗ |
| Outage & recovery | `shell/agent/RecoveryPage.tsx:38-171` | ✗ |
| Group page / new group | `shell/agent/GroupPage.tsx:40-361` | ◐ |
| Files (text files) / file edit | `shell/domain/FilesPages.tsx:21-266` | ◐ (read/share only) |
| Market | `pages/Market.tsx` (legacy surface) | ✗ |
| Trading | `pages/Trading.tsx` (legacy surface) | ✗ |
| Scheduled tasks (routines + watches) / new schedule | `shell/domain/SchedulesPages.tsx:272-514` | ◐ (routines only) |
| Knowledge (notes, links) / edit | `shell/domain/GoalsKnowledgePages.tsx:116-246` | ✗ |
| Memory (legacy: profile, long-term memory + revisions + semantic, skills catalog, scratchpad) | `pages/Knowledge.tsx`, `KnowledgeSection.tsx`, `MemoryRevisions.tsx`, `SkillsSection.tsx`, `ScratchpadSection.tsx` | ◐ (memory text only) |
| Goals / edit goal | `shell/domain/GoalsKnowledgePages.tsx:24-115` | ✗ |
| Task details / new task | `shell/domain/TasksPages.tsx:143-328` | ✗ |
| Skills / skill edit / new skill (versions, restore) | `shell/domain/SkillsPages.tsx:87-348` | ◐ (no versions/restore) |
| Owner profile | `shell/settings/OwnerPage.tsx:74-465` | ◐ (lines + habit only) |
| What is running | `shell/settings/RunningPage.tsx` | ✅ |
| Accessibility / Storage / Privacy (app lock) | `shell/settings/DevicePages.tsx:25-314`, `AppLock.tsx`, `lock-state.ts` | ✗ |
| Chat experience | `conversation/ChatPrefsPage.tsx` | ◐ (no Send-with-Enter, wallpaper) |
| Notifications & contact / per-agent «communication» | `shell/settings/NotifyPages.tsx:57-472` | ◐ |
| Voice settings | `pages/VoiceSettingsOverlay.tsx` | ◐ (read-only) |
| Integrations | `shell/settings/IntegrationsPage.tsx:124-852` | ◐ |
| Model providers / provider form | `shell/settings/ConnectionPages.tsx:582-822` | ✗ |
| Models (routing) | `shell/settings/ModelsPage.tsx:57-338` | ◐ (read-only) |
| Add MCP | `shell/settings/ConnectionPages.tsx:823-956` | ✗ |
| Link broker / trading account | `shell/settings/ConnectionPages.tsx:89-580` | ✗ |
| Usage / usage detail | `shell/settings/UsagePage.tsx:20-650` | ◐ (totals only) |
| Call page / incoming call page | `shell/call/CallPages.tsx:171-609` | ◐ |
| Lab (dev only) | `shell/Lab.tsx` | n/a |

---

## 3. Capabilities the Expo app lacks — feature by feature

Format per feature: **Entry** · **Screens/dialogs** · **Actions** · **States** · **Endpoints** · **Gating**.

### 3.1 Market (quotes, instruments, calendar, watches, chart workspace)
- Entry: `/app/market` (legacy surface) VERIFIED `shell/pages.tsx:256-262`; GenUI `go market`.
- Screens: broker account select, `SymbolSearch`, `MarketOverview`, `MarketQuote`, `ChartWorkspace`
  (TradingView-style with drawings/studies `lib/tradingview-*.ts`), `MarketWatch` (watch source: price,
  indicator, position, account changes, economic calendar; period), `EconomicCalendar`; simulation notice
  VERIFIED `pages/Market.tsx:1-62`, `components/market/MarketWatch.tsx:55-154`.
- Endpoints: `GET /market/instruments?account_id=`, `GET /market/symbols?account_id=`,
  `GET /market/instrument?account_id=&symbol=`, `GET /market/quote?…`, `GET /market/candles?…&timeframe=`,
  `GET /market/calendar`, `GET/POST /watches` (resource), `GET /integrations`; live `market.quote_updated`
  events VERIFIED `lib/market.ts:3-16`, `components/market/EconomicCalendar.tsx:20`. Server also has
  `WS /ws/market` (unused by both clients — VERIFIED grep).
- Gating: owner session; read-only market data; watches carry no authority (`shell/domain/api.ts:67`).
- Mobile: ◐ charts (scene) + symbol list only.

### 3.2 Voice
- Entry: chat header Call, agent page «اتصال», `/app/call`, incoming `/app/incoming/:callId`,
  voice settings overlay VERIFIED `shell/call/CallPages.tsx:1-27,171,477,516`.
- Screens: full call screen (timer mm:ss, 4-bar wave from real levels, fold to strip, call strip on every
  screen, folded call in its own chat (hang up, mute), speaker/output selection via `setSinkId`, live
  transcript), incoming page (agent, reason, رد · رفض · «الرد برسالة»), Q58 no-provider sheet VERIFIED
  `CallPages.tsx:30-170,307-400,401-476,516-609`.
- Voice notes: hold mic 350 ms, slide 110 px to cancel, 70 px up to lock; ≤120 s, 44 peaks; upload then
  message `{voice:{artifact_id,duration,peaks}}` (server transcribes); one-at-a-time playback
  VERIFIED `conversation/Composer.tsx:513-523,1205-1420`, `conversation/Voice.tsx:6-40`,
  `packages/contracts/src/visual-response.ts:104-114`.
- Endpoints: `GET /voice/status`, `POST /voice/sessions` (`mode:"gpt_live"`, SDP), `GET /voice/sessions/{id}`
  (snapshot), `POST /voice/sessions/{id}/interrupt`, `DELETE /voice/sessions/{id}`,
  `POST /voice/cancel-initialization`, events `voice.transcript`, `GET /voice/incoming[/policy]`,
  `POST /voice/incoming/{id}/respond`, `POST /artifacts/upload` VERIFIED `lib/voice.ts:13-15,196-201,239-285`,
  `hooks/useVoice.ts:217,251,362`. Server-only: `POST /voice/sessions/{id}/transcript`, `WS /ws/voice`.
- Gating: owner session; a call never authorises execution (`IncomingCall.execution_authorized:false`,
  `apps/mobile/lib/incoming-call.ts:12`); reach-me channel «call» needs an enrolled passkey device.
- Mobile: ◐ (calls without transcript/interrupt/speaker; no voice notes).

### 3.3 Tasks (the Task system) and boards/tickets
- Entry: Tasks root tab; chat menu «مهمة جديدة»; tools sheet «مهمة جديدة»; `/app/tasks/:id`, `/app/new-task`.
- Screens: list «نشطة · مجدولة · مكتملة» with four status words; details (agent, due, completion criterion,
  view conversation, Pause/Resume, «تحديد كمكتملة», Delete with confirm); create (title ≤160, responsible
  agent, what is needed ≤16000, due time default 18:00, completion criterion ≤2000) VERIFIED
  `shell/domain/TasksPages.tsx:32-328`.
- Endpoints: `GET /tasks`, `GET /tasks/{id}`, `POST /tasks?agent_id=&thread_id=`, `POST /tasks/control
  {task_id,action:pause|resume|cancel,expected_version}`, `POST /tasks/{id}/complete {expected_version}`,
  `DELETE /tickets/{id}`, `POST /agents/{id}/conversation` (thread for a new task) VERIFIED
  `shell/domain/api.ts:42-57`, `TasksPages.tsx:193,300`.
- Boards: `pages/Board.tsx` (resources `/boards`, `/tickets`, `POST /tickets/{id}/start`) is not mounted
  anywhere (only the alias `board → /app/tasks`) VERIFIED grep `shell/pages.tsx`, `routes.ts:66`. INFERRED
  dead legacy; no port needed beyond Tasks.
- Gating: owner session; «complete» stops work, approves nothing (`shell/domain/api.ts:55`).
- Mobile: ✗ (only `POST /tasks` from a message and task controls inside the live-status strip).

### 3.4 Skills
- Entry: agent page «المهارات», tools sheet, `/app/skills?agent=`, `/app/skills/:id`, `/app/new-skill`.
- Screens: skills list, editor (title, tool choice among three real tools + the skill's own, content,
  enabled), «سجل الإصدارات» with «الرجوع إلى الإصدار N» + undo; legacy catalog `SkillsSection`, `SkillCard`,
  `RevokeVersion`, `CreateSkill`, `SkillEditor` (delete) VERIFIED `shell/domain/SkillsPages.tsx:18-348`.
- Endpoints: `GET /skills?agent_id=`, `GET /skills/{id}`, `POST /skills`, `PUT /skills/{id}`,
  `DELETE /skills/{id}`, `GET /skills/{id}/versions`, `POST /skills/{id}/restore {version,expected_version}`,
  `GET /agents/{id}/skills/catalog[/{skill}]`, `GET/POST /agents/{id}/skills/revocations` VERIFIED
  `shell/domain/api.ts:88-103`, `pages/SkillsSection.tsx`, `components/skills/*`.
- Mobile: ◐ (no versions/restore).

### 3.5 Scratchpad
- Entry: `/app/memory` (legacy Knowledge page) tab «Scratchpad» VERIFIED `pages/Knowledge.tsx:15-63`.
- Actions: add (title, content), edit (title, content, enabled), delete; versioned resource
  VERIFIED `pages/ScratchpadSection.tsx:9-203`.
- Endpoints: `GET /scratchpad?agent_id=`, `POST /scratchpad`, `PUT /scratchpad/{id} {payload,version}`,
  `DELETE /scratchpad/{id}` (generic resource router) VERIFIED `apps/api/src/lonora_api/routes/scratchpad.py:5`,
  `routes/__init__.py:11-71`, `lib/rpc.ts:2-15`.
- Mobile: ✗.

### 3.6 Knowledge editing (memory, semantic memory, notes, links, goals)
- Long-term memory editor with attributed change log and one-tap revert per change; semantic memory
  config (enable + global OpenAI embedding model), add a semantic knowledge note VERIFIED
  `pages/KnowledgeSection.tsx:22,62,104,118-207`, `pages/MemoryRevisions.tsx:21-117`.
- Knowledge page (Q40): notes (title, content) and links (title, URL, content); edit page VERIFIED
  `shell/domain/GoalsKnowledgePages.tsx:116-246`.
- Goals: agent goal list + edit (light goals) VERIFIED `GoalsKnowledgePages.tsx:24-115`.
- Endpoints: `GET/PUT /agents/{id}/memory`, `GET /agents/{id}/memory/revisions`,
  `POST /memory/revisions/{id}/revert`, `GET/PUT /memory/semantic/config`, `POST /agents/{id}/memory/semantic
  {text}`, `GET /agents/{id}/knowledge`, `POST /agents/{id}/knowledge/notes`, `PUT
  /agents/{id}/knowledge/notes/{note}`, (`DELETE …/notes/{note}` server only), `POST/PUT /knowledge-links`,
  `GET/POST/PUT /agent-goals` VERIFIED `shell/domain/api.ts:71-86`, `routes/knowledge.py`, `routes/memory.py`.
- Mobile: ◐ (memory text edit only).

### 3.7 Connections and integrations
- Entry: Settings «التكاملات» (count of linked accounts/providers/MCP) VERIFIED `SettingsRoot.tsx:25,359-365`.
- Order: trading accounts → AI providers → servers and repositories → news and channels → skills
  VERIFIED `IntegrationsPage.tsx:124-128`.
- **Trading account link** (`/app/broker`): provider MetaApi (fields `account_id`, `api_key` secret,
  `region`) or «Simulation with an imported snapshot» (`account_id` + snapshot JSON); «اختبار الاتصال»
  is a read-only round trip; account page (hero, balance, type, symbols grid, agents count, disconnect)
  VERIFIED `ConnectionPages.tsx:41-88,89-231,232-490,491-580`. Endpoints: `POST /trading/connections`,
  `POST /trading/connections/test`, `GET /trading/connections`, `GET /trading/accounts/{id}`,
  `GET /market/symbols?account_id=`, `DELETE /trading/connections/{id}`, `POST
  /trading/connections/{id}/simulation {snapshot}` VERIFIED `ConnectionPages.tsx:128,186-189,239,244,301,540`,
  `components/trading/BrokerConnection.tsx:35`. Lonora Cloud: account number + server + password via the
  Secret card (`VISION.md:784-803`).
- **RSS feeds**: add `POST /integrations {payload{type:"news_feed",name,url,enabled}}`, remove
  `DELETE /integrations/{id}` VERIFIED `IntegrationsPage.tsx:372-380` and sheet `:383-430`.
- **Feed domains** (trusted sources): `POST /trusted-sources {kind:"feed_domain",identifier}`, revoke/restore
  VERIFIED `IntegrationsPage.tsx:294-300`.
- **Telegram**: bot token → `POST /integrations/secrets {name:"telegram-bot",value}` → `POST /integrations
  {payload{type:"telegram",name,secret_id,deliver_to_agent_id,enabled}}`; delivers the same alerts a
  push carries; owner replies reach the chosen agent as owner messages and never decide a card
  VERIFIED `IntegrationsPage.tsx:124-128,454-467`.
- **MCP servers** (§3.18), **skills undo** (revocations), capability report `GET /capabilities`.
- Mobile: ◐ (review/trust/revoke/remove only; no add flows).

### 3.8 Provider and model routing configuration
- Providers list (`/app/providers`): providers with a key + ChatGPT plan row (account, "Using ChatGPT plan",
  Manage usage, sign out) VERIFIED `ConnectionPages.tsx:582-690`.
- Provider form (`/app/provider/:id`): provider (openai, anthropic, deepseek, zai, openrouter,
  openai_compatible), API key show/hide, «اختبار الاتصال» (`POST /providers/{id}/test`, nothing stored),
  save `PUT /providers/{id}/credential {api_key}` VERIFIED `ConnectionPages.tsx:692-822`,
  `packages/contracts/src/models.ts:3-10`.
- ChatGPT sign-out: `POST /providers/openai_chatgpt/sign-out` → `{signed_out,revoked}` VERIFIED
  `packages/core/src/chatgpt-plan.ts:141-176`, `ConnectionPages.tsx:671`.
- Models page (`/app/models`): routing mode `unified | custom`; per capability `conversation, reasoning,
  research, vision, realtime_voice, stt, tts, background`; voice routes use OpenAI speech models
  (`gpt-live-1`, `gpt-live-1-mini`, …); Lonora's fixed model list per connected provider
  (`GET /providers/{p}/models`), listed models with verified metadata VERIFIED `ModelsPage.tsx:19-57,57-338`,
  `lib/model_routing.ts:2-13`, `lib/model_catalog.ts`, `VISION.md:835-840`.
- Endpoints: `GET /providers`, `PUT /providers/{p}/credential`, `POST /providers/{p}/test`,
  `GET /providers/{p}/models`, `GET/PUT /settings/models` (saving re-queues replies that failed for lack of
  a model `routes/model_router.py:16-42`). Server-only: `PUT /settings/models/backups`,
  `GET/PUT /settings/models/context`.
- Per-agent model: `GET /agents/{id}/model/summary`, `PUT /agents/{id}/model {primary,fallbacks,
  expected_revision}` (Identity page, `AgentModelCard`) — mobile ✅ via `AgentModelSettings`.
- Gating: owner session; keys write-only (never read back). Mobile: ◐ read-only.

### 3.9 Financial execution controls
- **There is no global OFF/ON switch and no global stop control any more.** Amendment 1 (2026-11-12)
  removed that switch, its cards and every related endpoint; migration `0150_remove_stop` deletes its
  stored row and attention items
  VERIFIED `VISION.md:723-736`, `packages/db/migrations/versions/0150_remove_stop.py:1-56`. (`VISION.md:196-210`
  section 4.8 describing Stop is void.)
- The owner's controls now: (1) **Mandate** per agent Full/Ask — chip beside the composer and agent
  settings sheet; reads `GET /owner-actions/mandate?agent_id=` (never raises), raises `POST
  /owner-actions/mandate?agent_id=`, applies `POST /owner-actions/{card}/decision {decision:"confirm",
  trading_mode}`; "Only the Mandate card can set Full" VERIFIED `conversation/PermissionMenu.tsx:16-39,185-236`
  (mobile ✅). (2) **Trade Approval** Approve/Reject `POST /trading/approvals/{id}/decision` (mobile ✅) and
  **renew** `POST /trading/approvals/{id}/renew` (mobile ✗) VERIFIED `components/trading/TradeApprovals.tsx:98`,
  `conversation/Conversation.tsx:840`. (3) **Settle uncertain operation** (owner action, ✅). (4) **Agent
  pause** «إيقاف الوكيل/تشغيل» `PATCH /agents/{id} {paused}` VERIFIED `AgentPage.tsx:83,175-177` (mobile ✅ via
  switch). (5) **Pause/cancel tasks and watches** (§3.3, §3.17). (6) **Broker connection** delete
  (refused while an operation is unresolved, `VISION.md:658`). (7) **Workspace Stop / Stop all** (✅).
- **Owner's own orders**: Trading page ticket (`TradeActionCard`: symbol, buy/sell/pending types, volume,
  price, SL, TP) and agent Trades page (edit stop & target, close trade, check close result) post
  `POST /trading/execute` with a client-held operation id per ticket action until the journal settles
  it; order log from `GET /trading/journal`; account summary/positions/orders from
  `GET /trading/accounts/{id}` VERIFIED `pages/Trading.tsx:1-92`, `components/trading/TradeActionCard.tsx:1-30`,
  `components/trading/useTicketAction.ts:11-108`, `shell/agent/TradesPage.tsx:87,266-440`, `lib/trading.ts:9-14`.
  Server `POST /trading/execute` (owner session, relayed broker or trading service) VERIFIED
  `apps/api/src/lonora_api/routes/trading.py:97-106`.
- **Recovery page** «التعطل والاستعادة»: broker session state, since, last successful read, reason,
  operations awaiting confirmation, execution state, try again (`GET /trading/accounts/{id}`) VERIFIED
  `shell/agent/RecoveryPage.tsx:38-167`.
- Gating: owner session; every risk-increasing agent request in Ask needs a Trade Approval with tolerance;
  drifted cards cannot be approved; GenUI/Telegram/push/calls can never approve, settle or switch a mode
  VERIFIED `VISION.md:465-482`, `docs/genui.md:8-9,141-142,226-227`.
- Mobile: ✗ for owner orders, trades page, recovery, renew.

### 3.10 Usage dashboard
- Entry: Settings «الاستهلاك» (`/app/usage`), per-agent `/app/usage-detail/:agentId`.
- Screens: period tabs day/week/month; chart (hour buckets for day, day buckets for week/month); month
  card (month-to-date spend + linear projection, **no limit**); previous-window comparison; ranking by
  agent (→ detail) and by model; unpriced request counts; CSV export VERIFIED `UsagePage.tsx:20-23,84-117,513-571`,
  `packages/contracts/src/usage.ts:1-60`.
- Endpoints: `GET /usage/series?period=&agent_id=`, `GET /usage/rank?…`, `GET /usage/export.csv?…`;
  server also `GET /usage/agents`, `GET /usage/summary` (mobile uses summary).
- Mobile: ◐ (token totals only).

### 3.11 Trusted sources
- Entry: Integrations (feed domains, MCP server trust, skill sources); capability report.
- Actions: add feed domain `POST /trusted-sources {kind,identifier}`; revoke/restore
  `POST /trusted-sources/{id}/revoke|restore`; MCP trust preview + approve tier (`read` /
  `write_nonfinancial`) `POST /trusted-sources/mcp/{connection}/preview`, `POST /trusted-sources/mcp/{connection}
  {tier,digest}`; «Approve the new schema» when a trusted server's tools changed (`needs_review`)
  VERIFIED `IntegrationsPage.tsx:147-246,294-300`, `routes/trusted_sources.py`. Server `GET /trusted-sources`
  unused (report via `/capabilities`). VISION: other trust (GitHub skill sources) is the owner's typed
  message in chat, no card (`VISION.md:490`).
- Mobile: ◐ (revoke/restore/trust; no add).

### 3.12 Account authority (signed grants)
- Server routes exist: `GET/POST /agents/{id}/account-authorities`, `POST /account-authorities/{id}/challenge`,
  `POST /account-authorities/verify` (WebAuthn proof), `POST /account-authorities/{id}/revoke` VERIFIED
  `apps/api/src/lonora_api/routes/account_authority.py:1-80`; helper in `packages/core/src/account-authority.ts:147-151`.
- No web or mobile UI calls them (VERIFIED grep). VISION phase 3 deletes grants/limits (Mandate replaces
  them) `VISION.md:672-680`; live-status shows «grant review failed» / pending device authorization lines
  (`apps/mobile/components/agent-live-status.tsx:139-144`). INFERRED: do not port a grant UI.

### 3.13 Device authority (passkeys)
- Web: «الجهاز» in Notifications & contact — register this device (account password + WebAuthn
  `navigator.credentials.create`), choose the device a call rings VERIFIED `NotifyPages.tsx:89-110,286-311`.
- Endpoints: `POST /auth/devices/enrollment {password,name}`, `POST /auth/devices/enrollment/verify`;
  server-only `GET /auth/devices/config` (rp id, android/ios configured), `GET /auth/devices`,
  `DELETE /auth/devices/{id}` (revoking stops authorities bound to the device) VERIFIED
  `routes/device_authority.py:21-60`.
- Native passkeys need the Android asset-links fingerprints (`passkey_android_fingerprints`) — INFERRED
  from `routes/device_authority.py:24-28`.
- Mobile: ✅ enrollment (react-native-passkeys); ✗ list/revoke (neither client).

### 3.14 Collaboration
- Both clients read `GET /threads/{id}/collaboration` and show peer cards (`GET /peer-messages?thread_id=`);
  web shows `CollaborationMarker` and offers «@الكل» while a session is open; round-limit error text
  VERIFIED `conversation/Conversation.tsx:153,205`, `conversation/Composer.tsx:258-349`,
  `lib/user_error.ts:29-30`. `GET /collaboration/{session_id}` unused.
- Mobile: ✅ (equivalent).

### 3.15 Opportunities
- Server `GET /trading/opportunities[/{id}]` unused by clients (VERIFIED grep). Owner-facing: attention
  policy switch «Notify me about confirmed opportunities» (`PUT /attention/policy {opportunities}`) and reach-me
  «Opportunity calls» VERIFIED `NotifyPages.tsx:189-200`, `apps/mobile/components/incoming-call-settings.tsx:176-204`.
- Mobile: ◐ (opportunity calls only; no attention policy).

### 3.16 Performance
- Server `GET /agents/{id}/performance` and `GET /trading/decisions[/{id}]` unused by both clients
  (VERIFIED grep). VISION 5.5.6 weekly report is posted in chat. INFERRED: no screen to port.

### 3.17 Watches
- Entry: agent page «المراقبات», chat menu «Watches» sheet, schedules page (conditional schedules), Market
  watches.
- Actions: create conditional watch (price level above/below, until), pause/resume/cancel (+ undo toast)
  VERIFIED `AgentPage.tsx:95-159`, `conversation/sheets/WatchesSheet.tsx:15`, `SchedulesPages.tsx:230-299,385-510`.
- Endpoints: `GET /watches?agent_id=`, `POST /watches`, `POST /watches/{id}/control {action:pause|resume|cancel}`.
- Mobile: ◐ (cancel only, from the live-status strip).

### 3.18 MCP
- Add MCP (`/app/mcp`): remote Streamable HTTP only, no per-agent allow list; name, `https://` URL,
  auth none/token; token stored first as a secret; «Test» lists tools and blocked tools; new server
  lands as «غير معتمد» until approved VERIFIED `ConnectionPages.tsx:823-956`.
- Endpoints: `POST /integrations/secrets {name:"mcp-<name>",value}`, `POST /mcp {payload{name,url,secret_id,
  enabled}}`, `POST /mcp/test`, `GET /mcp` (count), trust via §3.11.
- Mobile: ◐ (trust/remove only).

### 3.19 Workspace
- «ما يعمل الآن» (both ✅). Files of the workspace/agents: text-only list (Q36), new text file, upload,
  edit, delete VERIFIED `FilesPages.tsx:18-266`. Endpoints: `GET /artifacts[?agent_id]`, `POST
  /artifacts/upload (file, agent_id?)`, `GET /artifacts/{id}/file`, `PUT /artifacts/{id}/text
  {expected_version,name,content}`, `DELETE /artifacts/{id}` VERIFIED `shell/domain/api.ts:105-125`.
- Server-only: `GET /secrets`, `DELETE /secrets/{id}` (the only secret deletion route, `VISION.md:645`).
- Mobile: ◐ (files read/share only).

### 3.20 Onboarding and auth flow
- Intro slides once per device, e-mail+password sign-in, «انتهت جلستك» (session expired), first-run
  bootstrap (setup token from `https://<host>/#token=…`, removed from history at start) VERIFIED
  `shell/settings/AuthFlow.tsx:12-24`, `lib/setup-link.ts:1-30`, `lib/bootstrap.ts:1-4`.
- Endpoints: `GET/POST /onboarding`, `POST /auth/login`. Mobile ✅ (`lonora://connect` instead of `#token`).

### 3.21 Other web-only owner capabilities (not in the requested list, needed for parity)
| Capability | Entry / UI | Endpoints | Mobile |
|---|---|---|---|
| Owner profile form (name, form of address, time zone, preferences) + change log with Restore | Settings › Profile | `GET/PUT /owner/profile`, `PUT /owner/preferences`, `GET /owner/profile/revisions?limit=50`, `POST /memory/revisions/{id}/revert`; lines `GET/POST /owner/profile/lines`; habit `GET/DELETE /app-opens` VERIFIED `OwnerPage.tsx:84-192` | ◐ |
| Notifications: in-app banner, text preview, sounds (device prefs), quiet hours with minutes («Mute at night», From/To), «Urgent always arrives» | Notifications & contact | `PUT /owner/preferences {reach_me}`, `GET/PUT /attention/policy` VERIFIED `NotifyPages.tsx:67-233`, `packages/contracts/src/notifications.ts:1-17` | ◐ (hours only, no banner prefs) |
| Per-agent delivery rules (in-app messages, agent calls, daily limit) | `/app/communication/:agentId` | `GET /agents/notifications`, `GET/PUT /agents/{id}/notifications {in_app,calls,daily_limit}` VERIFIED `NotifyPages.tsx:385-467`, `notifications.ts:19-25` | ✗ (read only for heads-up) |
| Accessibility (text size 0–4 ×0.9…1.32, higher contrast, reduced motion) | Settings | device-local VERIFIED `DevicePages.tsx:25-110`, `device-prefs.ts:50` | ✗ |
| Storage & data (space used, clear) | Settings | device-local `DevicePages.tsx:114-195` | ✗ |
| Privacy: app lock (4-digit code, PBKDF2 210 000 iterations, biometric via platform authenticator, auto-lock after leaving, 5 wrong tries → 30 s cooldown), hide message text in notifications | Settings | device-local VERIFIED `DevicePages.tsx:196-310`, `AppLock.tsx:18-60`, `lock-state.ts:3,46,67-104` | ✗ |
| Agent status & safety sheet (status line, task controls, per-account safety) | chat header status | `GET /agents/{id}/state`, `POST /tasks/control` VERIFIED `conversation/sheets/AgentSheet.tsx:29-146,385` | ◐ (strip + pill) |
| Group page: purpose, lead, member check rows | group header | `PUT /groups/{id}`, `POST /groups/create` VERIFIED `GroupPage.tsx:40,165,227,267` | ◐ |
| Identity page: name, role/title, model, trading account + pair, linked symbol | agent page | `PATCH /agents/{id}`, `PUT /agents/{id}/model` VERIFIED `IdentityPage.tsx:21,125,155-335` | ✅ (bot-settings) |
| Composer extras: camera, drag & drop, paste, voice notes, `/settings`, Send with Enter, schedule from tools sheet | composer | `POST /artifacts/upload`, `POST /threads/{id}/messages` VERIFIED `conversation/ToolsSheet.tsx:13,131-237`, `Composer.tsx:616,916,1007,1030` | ◐ |
| Mark all read | list menu | `POST /threads/read-all` VERIFIED `shell/lists/api.ts:17` | ✗ |
| Agent error card with provider failure family; order sheet (timeline, evidence, broker ticket); agent steps | conversation cards | (data from runs/journal) VERIFIED `conversation/Cards.tsx:26-550` | ◐ |
| Markdown tables, quotes, lists, mentions, bare links | message text | — VERIFIED `conversation/Markdown.tsx:6-266`, `packages/chat-ui/src/markdown-table.tsx` | ✗ tables/quotes |
| New version bar / maintenance page | global | `GET /version`, `GET /health` VERIFIED `shell/UpdateBar.tsx:7-17`, `shell/StatePage.tsx:109-116` | ✗ (OTA instead) |
| Attention mark seen | attention row open | `POST /attention/seen {notification_id}` VERIFIED `providers/AttentionProvider.tsx:75` | ✗ |
| Chat wallpaper | chat prefs | device-local `conversation/wallpaper.ts` | ✗ |
| Install PWA / keyboard shortcuts / desktop rail | settings / desktop | — | n/a |

---

## 4. Security gating summary

| Gate | Where enforced | Evidence |
|---|---|---|
| Owner session (single owner; bearer for native, HttpOnly cookie + CSRF for web) | every owner route via `require_owner` (188 uses) | VERIFIED `middleware/auth.py:16-27` |
| Password step-up + passkey (WebAuthn) for device enrollment | `POST /auth/devices/enrollment` body `DeviceEnrollment{password,name}`; verify proof | VERIFIED `routes/device_authority.py:39-58`, `apps/mobile/components/incoming-call-settings.tsx:80-100` |
| Calls ring only an enrolled device; call channel requires a device | reach-me policy | VERIFIED `apps/mobile/lib/incoming-call.ts:48-73` |
| Owner-action confirmation: tap (no passkey needed now) | `owner_action_passkey_not_needed` | VERIFIED `routes/owner_actions.py:11,108-109` |
| Mode switch only via the live Mandate card | `/owner-actions/mandate` + decision | VERIFIED `PermissionMenu.tsx:32-39` |
| Trade approvals: owner session, exact request, tolerance/drift | `/trading/approvals/{id}/decision` | VERIFIED `routes/trading.py:133-136`, `VISION.md:465-482` |
| Cards/GenUI/push/Telegram never approve, settle or switch a mode | design rule | VERIFIED `docs/genui.md:8-9,141-142`, `IntegrationsPage.tsx:124-128`, `apps/mobile/lib/push.native.ts:66-70` |
| MCP trust tiers: read / write_nonfinancial only; "never money" | trust preview | VERIFIED `apps/mobile/app/(settings)/integrations.tsx:134-152` |
| Secrets write-only (Secret card / integrations secrets); agent learns "saved" | `POST /owner-actions/{id}/secret`, `POST /integrations/secrets` | VERIFIED `VISION.md:466`, `packages/core/src/owner-actions.ts:738` |
| Connection/agent deletion refused while an operation has no confirmed outcome | `prepare_delete` | VERIFIED `VISION.md:658` |
| App lock (device-local, not a server gate) | web only | VERIFIED `shell/settings/lock-state.ts:3` |
| No global stop control / no trading OFF switch | removed | VERIFIED `VISION.md:723-736` |

---

## 5. Web i18n catalog

- Library: Lingui 6 (`@lingui/core`, `@lingui/react` macros `t\`…\``, `<Trans>`, `t({message, context})`).
- Files: `apps/web/src/i18n/locales/ar/messages.po` and `apps/web/src/i18n/locales/en/messages.po`
  (gettext PO; 1637 `msgid` each) VERIFIED `wc`/`grep -c '^msgid'`.
- Config: `apps/web/lingui.config.ts` — locales `ar, en`, **sourceLocale `en`** (msgids are English
  source strings), catalogs path `src/i18n/locales/{locale}/messages`, extraction includes
  `src`, `packages/ui-web/src`, `packages/chat-ui/src` VERIFIED.
- Runtime: `apps/web/src/i18n/config.ts` loads both catalogs, default `ar` unless
  `localStorage["lonora.locale"]==="en"`; `applyDirection` sets `<html lang>` and `dir="rtl|ltr"`
  VERIFIED `config.ts:1-12`, `direction.ts:1-4`.
- Format: ICU MessageFormat in msgids/msgstrs — positional `{0}` with extractor comments
  (`#. placeholder {0}: list.name`), named `{provider}`, plurals
  `{count, plural, one {…} two {…} few {# …} many {# …} other {# …}}` (Arabic uses all five categories),
  `msgctxt` for homographs (e.g. "order state", "agent status", "goal") VERIFIED `ar/messages.po:1-30,158-175,452,538,543`.
- Bidi helper: `isolated(value)` wraps in U+2068/U+2069 after stripping embedded controls VERIFIED
  `direction.ts:5-8`.
- Relationship to mobile: `apps/mobile/lib/labels-shell.ts` copies the shell words "from the web catalog
  (apps/web/src/i18n)" VERIFIED `labels-shell.ts:1`; core text modules are shared by both.
- Port: the PO files are the most complete owner-facing catalog (1637 entries); keys are English source
  strings, not ids → INFERRED: generate Dart ARB ids from a stable hash or a curated mapping.

---

## 6. Design tokens (`packages/ui-tokens`)

- `src/reference.ts` (canonical, from `docs/ui-reference/Lonora-Desktop-37.html`): font stack
  `system-ui, -apple-system, "Segoe UI", "Noto Sans Arabic", Tahoma, Arial, sans-serif`; weights 400/600/700;
  type px xs 12, sm 14, md 16, lg 20, xl 28; textScale [0.9, 1, 1.1, 1.2, 1.32]; radius sm 10, md 16,
  lg 24, pill 999, tail 6, bar 33, composer 26; blur `blur(20px) saturate(160%)`; motion ease
  `cubic-bezier(0.22,1,0.36,1)`, spring `cubic-bezier(0.3,1.35,0.5,1)` VERIFIED `reference.ts:7-20`.
  - **Dark (default)**: bg #0b0c10, surface #15161b, raised #1b1d23, fill #23252c, fill-2 #2c2f37,
    line #23252c, line-strong #343741, text #f7f5ef, muted #8b919e, faint #6a707c, primary #f7f5ef,
    on-primary #0b0c10, **accent #22e3a8**, accent-ink #22e3a8, on-accent #05271c, wave-accent #0fa678,
    bubble-in #15161b, bubble-out #23262e, red #ff8a91, danger-fill #e5484d, amber #f2c46b, violet #a99aff,
    glass rgba(11,12,16,.72), glass-bar/card/pop, glass-line, stage #050608, viz-dim/ink, thumb, shadows
    `hi`, `raise`, `float-shadow` VERIFIED `reference.ts:21-63`.
  - **Light overrides**: bg #f7f5ef, surface/raised #ffffff, fill #ece9e1, line #e3dfd5, text #0b0c10,
    muted #5d6270, primary #0b0c10, accent-ink #087a57, bubble-out #eae7df, red #c0392b, amber #9a6a00,
    violet #6c55ba … VERIFIED `reference.ts:65-100`.
  - High-contrast (dark/light) and opaque-glass fallbacks VERIFIED `reference.ts:101-131`.
- `src/appearance.ts` (legacy shadcn names, used by older web screens and mobile `components/ui.tsx`):
  dark background #0b0c0e, foreground #ececee, card #141518, primary #f1f1ef, chat-user #22242b,
  muted-foreground #85858a, destructive #ef4444, border #1e2026, ring/link/status-working #3b82f6,
  success #4ecb71, warning #e9c46a, overlay rgba(4,4,5,.72), radius 0.75rem; light counterparts
  VERIFIED `appearance.ts:1-77`.
- `src/visual.ts` (native rich-response metrics): space 6/10/16, radius 8/12/16, border 1, font small 12,
  body 14, label 13, heading [22,20,18,16], metric 24, line body 22/small 18, touch 44, control font 16 /
  height 44, panel padding 12, chart height 200, content width 728, column minimum 144 VERIFIED `visual.ts:1-15`.
- `src/icons.ts`: `ICON_PATHS` — 104 named 24-unit stroke paths (back, chev, plus, chat, layers, user(s),
  bot, task, settings, search, phone, mic, send, more, file, chart, trend, clock, shield, check(s),
  close, eye, download, bell, globe, moon, key, folder, book, cpu, bolt, plug, server, nodes, volume,
  edit, …, rss, device, hourglass, scale, branch); also the GenUI icon vocabulary VERIFIED `icons.ts:1-135`,
  `docs/genui.md:44-45`.
- `src/brand.ts`: name Lonora, slug/scheme `lonora`, applicationId `ai.lonora.mobile`, defaultLocale `ar`,
  workspacePath `/app` VERIFIED `brand.ts:1-8`.
- Generated CSS `reference.css`, `tokens.css` via `pnpm --filter @lonora/ui-tokens generate`; mapping doc
  `packages/ui-tokens/TOKENS.md` VERIFIED.

---

## 7. Backend endpoint coverage (all routes; W = web uses, M = mobile uses)

Source: route decorators in `apps/api/src/lonora_api/routes/*.py`, `websocket/*.py` (prefix `/api`),
generic resource routers `routes/__init__.py:11-71` (`GET ''`, `POST ''`, `GET/PUT/DELETE /{id}`) for
`/agent-goals, /knowledge-links, /skills, /artifacts, /boards, /charts, /groups, /integrations, /mcp,
/peer-messages, /scratchpad, /tickets, /watches`.

| Area | Endpoint | W | M |
|---|---|---|---|
| Auth | `POST /auth/login` | W | (web build) |
| | `POST /auth/mobile/login`, `GET /auth/session`, `POST /auth/logout` | W (session, logout) | M |
| Onboarding | `GET/POST /onboarding` | W | M |
| Devices | `POST /auth/devices/enrollment[/verify]` | W | M |
| | `GET /auth/devices/config`, `GET /auth/devices`, `DELETE /auth/devices/{id}` | — | — |
| Account authority | `/agents/{id}/account-authorities`, `/account-authorities/{id}/challenge|revoke`, `/account-authorities/verify` | — | — |
| Agents | `GET /agents`, `GET /agents/{id}`, `PATCH /agents/{id}`, `POST /agents/{id}/conversation` | W | M |
| | `POST /agents`, `DELETE /agents/{id}`, `GET /agents/{id}/permissions`, `GET /agents/{id}/performance` | — | — |
| Agent state / delivery / model | `GET /agents/{id}/state` | W | M |
| | `GET /agents/notifications` | W | M |
| | `GET/PUT /agents/{id}/notifications` | W | — |
| | `GET /agents/{id}/model/summary`, `PUT /agents/{id}/model` | W | M |
| | `GET /agents/{id}/model` | — | — |
| Memory / owner | `GET/PUT /agents/{id}/memory` | W | M |
| | `GET /agents/{id}/memory/revisions`, `POST /memory/revisions/{id}/revert`, `GET/PUT /memory/semantic/config`, `POST /agents/{id}/memory/semantic` | W | — |
| | `GET /owner/profile`, `PUT /owner/preferences`, `GET/POST /owner/profile/lines` | W | M |
| | `PUT /owner/profile`, `GET /owner/profile/revisions` | W | — |
| Knowledge | `GET /agents/{id}/knowledge`, `POST/PUT /agents/{id}/knowledge/notes[/{n}]`, `/knowledge-links`, `/agent-goals` | W | — |
| | `DELETE /agents/{id}/knowledge/notes/{n}` | — | — |
| Skills | `/skills` resource, `GET /agents/{id}/skills/catalog[/{s}]`, `GET/POST /agents/{id}/skills/revocations` | W | M |
| | `GET /skills/{id}/versions`, `POST /skills/{id}/restore` | W | — |
| Scratchpad / boards / tickets | `/scratchpad` | W | — |
| | `/boards`, `POST /tickets/{id}/start` | (legacy unmounted) | — |
| | `DELETE /tickets/{id}` | W | — |
| Threads | `GET /threads/inbox`, `POST /threads/prefs`, `GET/PUT /threads/settings`, `POST /threads`, `GET /threads/{id}`, `PUT /threads/{id}/options`, `POST /threads/{id}/read|clear` | W | M |
| | `GET /threads` (list) | — | M |
| | `POST /threads/read-all` | W | — |
| | `DELETE /threads/{id}`, `PATCH /threads/{id}/prefs` | — | — |
| Messages | `GET/POST /threads/{id}/messages`, reactions PUT/DELETE, `…/ui-state/{p}/unlock` | W | M |
| Chat lists | `GET/POST /chat-lists`, `PUT/DELETE /chat-lists/{id}`, `PUT /chat-lists/{id}/members` | W | M |
| Runs | `GET /runs`, `POST /runs/{id}/cancel|resume|retry` | W | M |
| | `POST /runs`, `GET /runs/{id}` | — | — |
| Tasks | `POST /tasks`, `POST /tasks/control` | W | M |
| | `GET /tasks`, `GET /tasks/{id}`, `POST /tasks/{id}/complete` | W | — |
| Routines | `GET /routines`, `POST /routines/{agent}`, `PUT/DELETE /routines/{id}` | W | M |
| | `GET /routines/{id}/history` | — | M |
| Watches | `POST /watches/{id}/control` | W | M |
| | `GET /watches`, `POST /watches` | W | — |
| Groups | `POST /groups/create`, `/groups` resource | W | M |
| Peer / collaboration | `GET /peer-messages`, `GET /threads/{id}/collaboration` | W | M |
| | `GET /collaboration/{session}` | — | — |
| Artifacts | `GET /artifacts`, `GET /artifacts/{id}`, `GET /artifacts/{id}/file`, `POST /artifacts/upload` | W | M |
| | `PUT /artifacts/{id}/text`, `DELETE /artifacts/{id}` | W | — |
| Charts | `/charts` resource, `GET /charts/{id}/scene`, `POST /charts/{id}/refresh` | W | M |
| Market | `GET /market/symbols` | W | M |
| | `GET /market/instruments|instrument|quote|candles|calendar` | W | — |
| | `WS /ws/market` | — | — |
| Trading | `GET /trading/connections`, `GET /trading/approvals`, `POST /trading/approvals/{id}/decision`, `GET /trading/receipts` | W | M |
| | `POST/DELETE /trading/connections`, `POST /trading/connections/test`, `POST /trading/connections/{id}/simulation`, `GET /trading/accounts/{id}`, `POST /trading/execute`, `GET /trading/journal`, `POST /trading/approvals/{id}/renew` | W | — |
| | `GET /trading/opportunities[/{id}]`, `GET /trading/decisions[/{id}]` | — | — |
| Owner actions | `GET /owner-actions`, `GET/POST /owner-actions/mandate`, `POST /owner-actions/{id}/decision|renew|secret`, `POST /owner-actions/{id}/chatgpt/start|finish` | W | M |
| | `POST /owner-actions/{id}/challenge` | — | — |
| Providers / models | `GET /providers`, `GET /settings/models` | W | M |
| | `PUT /providers/{p}/credential`, `POST /providers/{p}/test`, `GET /providers/{p}/models`, `POST /providers/openai_chatgpt/sign-out`, `PUT /settings/models` | W | — |
| | `PUT /settings/models/backups`, `GET/PUT /settings/models/context` | — | — |
| Integrations / MCP / trust | `GET /capabilities`, `DELETE /integrations/{id}`, `POST /trusted-sources/{id}/revoke|restore`, `POST /trusted-sources/mcp/{c}[/preview]` | W | M |
| | `POST /integrations`, `POST /integrations/secrets`, `POST /trusted-sources`, `GET/POST /mcp`, `POST /mcp/test` | W | — |
| | `GET /trusted-sources`, `GET /secrets`, `DELETE /secrets/{id}` | — | — |
| Attention | `GET /attention`, `GET /attention/view` | W | M |
| | `POST /attention/seen`, `GET/PUT /attention/policy` | W | — |
| Usage | `GET /usage/summary` | — | M |
| | `GET /usage/series|rank|export.csv` | W | — |
| | `GET /usage/agents` | — | — |
| Voice | `GET /voice/status`, `POST /voice/sessions`, `DELETE /voice/sessions/{id}`, `POST /voice/cancel-initialization`, `GET /voice/incoming[/policy]`, `POST /voice/incoming/{id}/respond` | W | M |
| | `GET /voice/sessions/{id}`, `POST /voice/sessions/{id}/interrupt` | W | — |
| | `POST /voice/sessions/{id}/transcript`, `PUT /voice/incoming/policy`, `WS /ws/voice` | — | — |
| Push | `PUT/DELETE /push/devices/{id}` | — | M |
| App opens | `POST /app-opens`, `GET/DELETE /app-opens` | W | M |
| Workspace | `GET /workspace/running`, `POST /workspace/running/stop[-all]` | W | M |
| Search | `GET /search` | W | M |
| Events | `GET /events/stream` | W | — |
| | `WS /ws/events` | — | M |
| | `GET /events` | — | — |
| System | `GET /version`, `GET /health` | W | — |
| | `GET /ready`, `POST /webhook` | — | — |
| Mobile OTA | `GET /mobile/updates[/assets/{f}]` | — | M (native) |
