# Android parity with the Expo and web apps

Status of the native Android client (`apps/android`) against every capability listed in
[lonora-mobile-inventory.md](analysis/lonora-mobile-inventory.md) (Expo app, `apps/mobile`) and
[lonora-web-inventory.md](analysis/lonora-web-inventory.md) (web app, `apps/web`). Each row was checked in
the Android code (routes, screens, `lib/core/api`, state actions), not inferred from names.

Status: **done** (works against the real server API), **partial** (what is missing is named),
**missing**, **n/a** (web- or desktop-only, or ops-only).

## Summary

| Inventory | Rows | Done | Partial | Missing | n/a |
|---|---|---|---|---|---|
| Expo app (lonora-mobile-inventory.md) | 264 | 215 | 26 | 8 | 15 |
| Web app (lonora-web-inventory.md) | 251 | 174 | 28 | 10 | 39 |

## Expo app (lonora-mobile-inventory.md)

### By section

| Section | Done | Partial | Missing | n/a |
|---|---|---|---|---|
| 1 Build and release | 6 | 3 | 0 | 6 |
| 2.1 Runtime architecture | 1 | 0 | 0 | 1 |
| 2.2 Session and authentication | 9 | 1 | 0 | 0 |
| 2.3 Live data | 3 | 3 | 1 | 0 |
| 3 Route map | 23 | 1 | 0 | 0 |
| 4.1 Sign-in | 4 | 0 | 0 | 0 |
| 4.2 Connect deep link | 1 | 0 | 0 | 0 |
| 4.3 Change server | 1 | 0 | 0 | 0 |
| 4.4 Tabs shell | 1 | 1 | 0 | 0 |
| 4.5 Chats tab | 10 | 1 | 0 | 0 |
| 4.6 Updates tab | 1 | 0 | 0 | 0 |
| 4.7 Tasks tab | 1 | 0 | 0 | 0 |
| 4.8 Settings tab | 1 | 0 | 0 | 0 |
| 4.9 Settings sub-pages | 6 | 0 | 0 | 0 |
| 4.10 Reach-me / incoming-call settings | 4 | 0 | 1 | 0 |
| 4.11 Agents management | 1 | 0 | 0 | 0 |
| 4.12 Groups | 3 | 0 | 0 | 0 |
| 4.13 Agent settings | 9 | 0 | 0 | 0 |
| 4.14 Skills | 6 | 0 | 0 | 0 |
| 4.15 Routines | 1 | 0 | 0 | 0 |
| 4.16 Owner knowledge | 1 | 0 | 0 | 0 |
| 4.17 Files | 3 | 0 | 0 | 0 |
| 4.18 Charts | 3 | 1 | 0 | 0 |
| 4.19 Conversation | 20 | 4 | 0 | 0 |
| 4.20 Chat preferences | 0 | 1 | 0 | 0 |
| 5 Sheets and overlays | 16 | 2 | 2 | 0 |
| 6 Gestures | 9 | 1 | 0 | 1 |
| 7 States | 5 | 0 | 0 | 0 |
| 8.1 Heads-up | 4 | 0 | 0 | 0 |
| 8.2 Push | 1 | 1 | 2 | 0 |
| 8.3 Incoming call | 2 | 0 | 0 | 0 |
| 9.1 Owner action card | 5 | 0 | 0 | 1 |
| 9.2 Trade approval | 1 | 0 | 0 | 0 |
| 9.3 Execution receipt | 1 | 0 | 0 | 0 |
| 9.4 Mandate control | 0 | 1 | 0 | 0 |
| 9.5 Safety pill | 0 | 0 | 1 | 0 |
| 9.6 Removed control (Amendment 1) | 0 | 0 | 0 | 1 |
| 10 Generated cards (GenUI v2) | 6 | 0 | 0 | 0 |
| 11 Rich responses | 6 | 2 | 0 | 0 |
| 12 Avatar | 5 | 0 | 0 | 0 |
| 13 i18n | 6 | 0 | 0 | 0 |
| 14 Voice call | 6 | 0 | 0 | 1 |
| 15 OTA | 0 | 0 | 0 | 1 |
| 16 Deep links | 3 | 1 | 0 | 1 |
| 17 Theme | 1 | 0 | 0 | 0 |
| 18 Endpoint map | 19 | 2 | 1 | 1 |
| 19 Observations | 0 | 0 | 0 | 1 |

### Missing and partial

| Section | Capability | Status | Android today / what is missing |
|---|---|---|---|
| 1 Build and release | Orientation portrait / UI style light+dark | partial | lib/app/app.dart themeMode (system/light/dark); features/settings/appearance_screen.dart — Missing: portrait lock. There is no setPreferredOrientations and no screenOrientation in the manifest, so the app rotates. |
| 1 Build and release | Push plugin, default channel 'attention' | partial | lib/platform/notifications/local_notifications.dart (high-importance channels incl. attention); lib/platform/background/background_sync.dart — Missing: remote push. The server only accepts the old app's push tokens. Notifications are local, raised from a background check every 15 minutes at the earliest. |
| 1 Build and release | ABIs / min SDK (Android 7, API 24+) | partial | build.gradle.kts minSdk = 26 — Missing: Android 7.x support (API 24/25). Those phones cannot install the Android client. |
| 2.2 Session and authentication | Device-local storage (server, session, locale, theme, chat prefs, outbox, drafts, visual state) | partial | secure_store.dart, devicePrefs, localStore per server+owner (shell, thread cache, outbox), conversation/draft_store.dart (drafts) — Missing: v1 visual-document state is not saved. |
| 2.3 Live data | Shell poll every 5 s (agents, groups, inbox, chat-lists, settings, runs, attention, attention/view) | partial | lib/state/actions/shell_actions.dart RefreshShellAction — Same endpoints, but refreshed only on socket ready, debounced events, foreground and pull-to-refresh. Missing: a periodic poll, so if the WebSocket is blocked lists go stale. |
| 2.3 Live data | POST /app-opens on each foreground (morning-brief learning) | missing | Never called; owner_knowledge_screen.dart only does GET/DELETE /app-opens — The server no longer learns wake habits from this client. |
| 2.3 Live data | Thread snapshot on focus + 15 s fallback + 150 ms debounced refetch | partial | thread_actions.dart LoadThreadAction (open, foreground, socket ready); realtime.dart _scheduleThread 150 ms — Missing: the 15 s fallback poll. |
| 2.3 Live data | Agent live state GET /agents/{id}/state every 15 s while thread / bot-settings is focused | partial | agents/profile/agent_data.dart fetchAgentState, used by agent_profile_screen.dart and agent_settings_screen.dart — Read on open and on that agent's events, never polled, and never read in the conversation (the header avatar comes from runs and connection only). |
| 3 Route map | /new-group (members?, name?) | partial | /groups/new?members= NewGroupScreen — Missing: the 'name' prefill parameter. |
| 4.4 Tabs shell | Network strip: offline + waiting outbox count, then 'restored' for 2.2 s | partial | chats_screen.dart NetworkStrip (offline + networkWaitingText); conversation_screen.dart shows 'reconnected' — Missing: the 'restored' state on the chat list, which only shows offline. |
| 4.5 Chats tab | Custom lists: create/rename/members/move/delete (+undo), name-taken and max-length warnings, emoji panel | partial | chats/list_sheets.dart showListEditor (one sheet), showListMenu; chats_actions.dart Save/AddTo/Delete/RestoreChatListAction — Missing: reordering lists (PUT position is only used to restore after undo) and the emoji panel for list names. |
| 4.10 Reach-me / incoming-call settings | Device registration with passkey (POST /auth/devices/enrollment + verify) | missing | account_screen.dart lists passkey devices read-only ('set_passkeyElsewhere') — Enrolling needs Android credential support and server assetlinks that name only the old package. Once the old app is gone, a device can only be enrolled from another client. |
| 4.18 Charts | Chart sheet rest/expanded/minimized (from /chart command, menu, chart links, open_chart) | partial | Menu 'charts', Markdown /charts? links (rich/markdown_view.dart) and open_chart (visual_view.dart) open the /charts page — Missing: the overlay sheet with rest/expanded/minimized modes over the conversation, and the /chart command. |
| 4.19 Conversation | Header: back, live avatar, title, group typing subtitle, tap -> settings, call button, actions, safety pill | partial | conversation/conversation_header.dart — Missing: the group '{name} is typing' subtitle and the safety pill. Call moved into the actions menu; tapping the title opens the agent profile or group settings. |
| 4.19 Conversation | Agent live status strip: watches cancel, device authorization, grant review, tasks controls, broker/market health | partial | Not in the conversation. Status line and watches (pause/resume/cancel) in agent_profile_screen.dart; task controls on /tasks (tasks_data.dart POST /tasks/control) — Missing in the thread: the strip itself and the device-authorization, grant-review-failed and broker/market health lines. |
| 4.19 Conversation | Attachments <=10, <=20 MB, each uploaded alone with progress/cancel; a message sent mid-upload is posted after; failure returns text+files | partial | conversation_composer.dart _add/_upload (POST /artifacts/upload) — Missing: Send is disabled while uploads run, so the owner presses it again instead of the message being queued until uploads finish. |
| 4.19 Conversation | Offline queue: queued plain text, auto-flush, stable nonce, retry/delete, 'sent n waiting' toast | partial | SendMessageAction (queued when the API never answered), persisted outbox, FlushOutboxAction on socket ready / network change — Missing: the 'sent n waiting messages' toast after a flush (waitingSentText is unused). |
| 4.20 Chat preferences | Per-device steps, steps open, detailed agent status, assist | partial | conversation_header.dart showChatPrefsSheet; prefs_actions.dart SetChatPrefsAction — All four are saved, but 'detailed agent status' has no effect because there is no status strip. |
| 5 Sheets and overlays | Emoji panel (recents, 8 sections, ar/en search) | missing | - — List names are typed text only. |
| 5 Sheets and overlays | Mandate modal (composer permission chip / settings row) | partial | agents/settings/mandate_section.dart (settings row) — Missing: the composer permission chip. |
| 5 Sheets and overlays | Safety pill sheet | missing | Text helpers are ported (l10n/core/trading_readiness.dart) but no feature uses them — No per-thread readiness pill or per-account sheet. |
| 5 Sheets and overlays | Chart sheet (rest/expanded/minimized) | partial | /charts page — Missing: the overlay sheet modes (see 4.18). |
| 6 Gestures | Long-press message -> menu; accessibility actions 'reply' / 'message options' | partial | conversation_screen.dart onLongPress -> _messageMenu; LnTappable — Missing: a dedicated 'reply' accessibility action. Screen readers only get the generic long-press. |
| 8.2 Push | Register PUT /push/devices/{device}; DELETE on permission denied | missing | No call anywhere — The server's push path only accepts the old app's tokens. It needs a server contract for Android push. |
| 8.2 Push | Re-sync on foreground and token rotation | missing | - — There is no push token to sync (follows from the row above). |
| 8.2 Push | Push kinds (trade approval, settle, secret, mandate, broker health, background health) | partial | platform/background/poll_logic.dart pushAttentionCodes; background_sync.dart (GET /threads/inbox, /attention) — Shown as local notifications from a background check every 15 minutes or more. Missing: immediate delivery. |
| 9.4 Mandate control | Composer chip / settings row; GET+POST /owner-actions/mandate; decision with trading_mode; toast | partial | agents/settings/mandate_section.dart; profile/agent_data.dart fetch/raise/decideMandate — Missing: the composer chip (shield/alert). |
| 9.5 Safety pill | One readiness pill per agent thread + per-account sheet | missing | Agent profile shows the mode line and unresolved count only (agent_profile_screen.dart) — No pill or sheet in the conversation. |
| 11 Rich responses | v1 local state saved per owner+document (<=100 KB) | partial | visual_view.dart _state (widget memory) — Missing: saving the state across restarts. |
| 11 Rich responses | Images with bearer bytes; duplicate hidden when a v1 document shows it | partial | rich/artifact_image.dart; message_widgets.dart AttachmentView — Missing: hiding the attachment when a v1 document already draws the same image. |
| 16 Deep links | Any route linkable via lonora://<route>?… (e.g. lonora://thread?id=…&around=…) | partial | deep_links.dart locationFor maps connect, thread/<id>, agent/<id>, chats — Missing: the query form lonora://thread?id=…&around=… (lands on chats) and the other routes. |
| 18 Endpoint map | Shell data / inbox endpoints + POST /app-opens | partial | shell_actions.dart — Missing: POST /app-opens. |
| 18 Endpoint map | Notify / reach-me endpoints incl. POST /auth/devices/enrollment[/verify] | partial | me/me_data.dart, settings_core_data.dart, heads_up_controller.dart — Missing: device enrollment and verify. |
| 18 Endpoint map | PUT/DELETE /push/devices/{device} | missing | - — Waits for an Android push contract on the server. |

## Web app (lonora-web-inventory.md)

### By section

| Section | Done | Partial | Missing | n/a |
|---|---|---|---|---|
| 1. Web architecture facts | 3 | 2 | 0 | 1 |
| 2. Page map | 26 | 6 | 0 | 1 |
| 3.1 Market | 7 | 2 | 0 | 0 |
| 3.2 Voice | 6 | 1 | 2 | 0 |
| 3.3 Tasks | 3 | 1 | 0 | 1 |
| 3.4 Skills | 4 | 0 | 0 | 0 |
| 3.5 Scratchpad | 1 | 0 | 0 | 0 |
| 3.6 Knowledge editing | 4 | 0 | 0 | 0 |
| 3.7 Connections and integrations | 8 | 0 | 0 | 0 |
| 3.8 Provider and model routing | 5 | 0 | 0 | 1 |
| 3.9 Financial execution controls | 14 | 0 | 0 | 0 |
| 3.10 Usage dashboard | 3 | 0 | 0 | 0 |
| 3.11 Trusted sources | 4 | 0 | 0 | 1 |
| 3.12 Account authority | 0 | 0 | 0 | 1 |
| 3.13 Device authority | 1 | 0 | 1 | 1 |
| 3.14 Collaboration | 4 | 0 | 0 | 0 |
| 3.15 Opportunities | 2 | 0 | 0 | 1 |
| 3.16 Performance | 0 | 0 | 0 | 1 |
| 3.17 Watches | 2 | 1 | 0 | 0 |
| 3.18 MCP | 2 | 0 | 0 | 0 |
| 3.19 Workspace | 2 | 0 | 0 | 1 |
| 3.20 Onboarding and auth | 3 | 0 | 1 | 0 |
| 3.21 Other web-only owner capabilities | 8 | 7 | 1 | 1 |
| 4. Security gating | 10 | 0 | 2 | 0 |
| 5. Web i18n catalog | 4 | 1 | 0 | 0 |
| 6. Design tokens | 2 | 4 | 1 | 2 |
| 7. Endpoint coverage | 46 | 3 | 2 | 25 |
| Billing (not in inventory) | 0 | 0 | 0 | 1 |

### Missing and partial

| Section | Capability | Status | Android today / what is missing |
|---|---|---|---|
| 1. Web architecture facts | Route model: roots chats\|updates\|tasks\|settings and inner pages | partial | lib/app/routes.dart, lib/app/router.dart: tabs /chats, /market, /me, /attention; pushed /tasks, /routines, /agents, /agent/:id[/settings\|/memory\|/skills], /groups/new, /groups/:id/settings, /files[/:id[/image]], /charts, /search, /me/knowledge, /settings/* — updates = /attention, settings = Me tab, tasks is a pushed page. No Android route for trades, recovery, trading, accessibility, storage, privacy (lab is dev-only). |
| 1. Web architecture facts | Shell reads (/agents, /groups, /threads/inbox, /chat-lists, /threads/settings, /runs) + POST /app-opens | partial | lib/state/actions/shell_actions.dart — All reads done (plus /attention, /attention/view). POST /app-opens is never sent, so Android opens do not feed the waking-habit learning. |
| 2. Page map | Settings root | partial | /me lib/features/me/me_screen.dart — Has account/profile, What I know, running, chat experience, notifications, integrations, models, voice, language, appearance, usage, files, about, sign-out. No Accessibility, no Privacy/app lock; Storage is only «Clear cache». |
| 2. Page map | Agent info page | partial | /agent/:id lib/features/agents/agent_profile_screen.dart — Message, Call, settings, memory/knowledge, skills, routines, files, charts, Mandate (read-only), watches, pause, delete. No Trades link (page absent). |
| 2. Page map | Market (legacy surface) | partial | /market market_screen.dart, symbol_sheet.dart, watch_sheet.dart; /charts lib/features/charts/charts_screen.dart — Quotes, symbols, calendar, watches, positions done; chart workspace has no owner drawing/studies (3.1). |
| 2. Page map | Accessibility / Storage / Privacy (app lock) | partial | Me › Clear cache (lib/features/me/me_actions.dart); system text scale and disable-animations honoured via MediaQuery — No in-app text size/contrast/reduced-motion, no space-used view, no app lock. |
| 2. Page map | Chat experience | partial | showChatPrefsSheet in lib/features/conversation/conversation_header.dart (from Me and the chat menu); prefs in lib/state/actions/prefs_actions.dart — Steps/steps-open switches work. 'Detailed status' is stored but unused; '@ suggestions' drives a suggested-reply chip, not an @ list. Send with Enter is desktop-only; no wallpaper. |
| 2. Page map | Call page / incoming call page | partial | lib/features/voice/call_overlay.dart, incoming_call.dart, voice_api.dart, voice_transport.dart — No live transcript, no interrupt; minimized pill only returns to the call. |
| 3.1 Market | Chart workspace with drawings/studies | partial | /charts lib/features/charts/charts_screen.dart, candle_chart.dart, charts_data.dart — Draws stored scene (candles, indicators, all drawing kinds), crosshair, range, refresh, POST /charts. Owner cannot draw or add/remove studies. |
| 3.1 Market | GenUI 'go market' entry | partial | lib/features/rich/genui/ui_card.dart _route — 'market' opens /charts, not the /market tab. |
| 3.2 Voice | Full call screen: timer, level wave, fold to strip on every screen, folded call in its own chat (hang up, mute) | partial | lib/features/voice/call_overlay.dart (CallPage, CallPill) — Timer, level meter, Speaker/Mute/End/Minimize, pill on every screen. Pill only reopens the call; no hang-up/mute on the strip or inside the chat (End call is on the ongoing notification). |
| 3.2 Voice | Live transcript (voice.transcript, GET /voice/sessions/{id}) | missing | — — No transcript event handling or session snapshot read. |
| 3.2 Voice | Interrupt (POST /voice/sessions/{id}/interrupt) | missing | — |
| 3.3 Tasks | Entry: Tasks root, chat menu «مهمة جديدة», tools sheet «مهمة جديدة», /tasks/:id, /new-task | partial | /tasks from Me; message menu «تحويل إلى مهمة» (conversation_actions.dart CreateTaskFromMessageAction) — No «مهمة جديدة» in the conversation menu or attach sheet; no deep link to a single task. |
| 3.13 Device authority | Register this device (password + passkey) | missing | account_screen.dart shows 'not available in this app yet' (set_passkeyElsewhere) — Needs Credential Manager and Android asset-links. |
| 3.17 Watches | Entry: agent page, chat menu Watches sheet, schedules, Market | partial | agent_profile_screen.dart, routine_board.dart, market_screen.dart — No Watches sheet in the conversation menu. |
| 3.20 Onboarding and auth | Intro slides once per device | missing | — |
| 3.21 Other web-only owner capabilities | Accessibility (text size, higher contrast, reduced motion) | partial | System text scale + disable-animations honoured via MediaQuery — No in-app controls; no high-contrast palette. |
| 3.21 Other web-only owner capabilities | Storage & data (space used, clear) | partial | Me › Clear cache (me_actions.dart) — No space-used breakdown. |
| 3.21 Other web-only owner capabilities | Privacy: app lock + hide message text in notifications | partial | notifications_screen.dart set_preview switch — Text hiding done; app lock (code, biometric, auto-lock, cooldown) missing. |
| 3.21 Other web-only owner capabilities | Agent status & safety sheet (status line, task controls, per-account safety) | partial | agent_profile_screen.dart status line (GET /agents/{id}/state) — No chat-header sheet; 'detailed status' pref unused; controls live in /tasks and cards. |
| 3.21 Other web-only owner capabilities | Composer extras: camera, drag & drop, paste, voice notes, / commands, Send with Enter, schedule from tools sheet | partial | conversation_composer.dart (camera, photos, files, web search, voice notes, @mentions, / commands) — Missing: tools-sheet entries (new task, schedule, trading). |
| 3.21 Other web-only owner capabilities | Agent error card (failure family), order sheet, agent steps | partial | conversation_timeline.dart runFailure, run_rows.dart (retry, steps) — Error card and steps done; order sheet (timeline, evidence, broker ticket) missing. |
| 3.21 Other web-only owner capabilities | New version bar / maintenance page | partial | lib/platform/updates/* (in-app update/manifest); about_screen.dart GET /version; api_error.dart 'maintenance' code — No maintenance overlay polling /health. |
| 3.21 Other web-only owner capabilities | Chat wallpaper | missing | — — Cosmetic. |
| 4. Security gating | Password step-up + passkey for device enrollment | missing | — — Enrollment not built (3.13). |
| 4. Security gating | App lock (device-local) | missing | — |
| 5. Web i18n catalog | Owner catalog (Lingui PO, 1637 entries, English msgids) | partial | assets/l10n/ar.json, en.json (815 keys, from apps/mobile) + per-feature *_strings.dart reusing web wording — PO catalog not imported wholesale; web-only strings exist only where a feature ported them. |
| 6. Design tokens | reference.ts font stack, weights, type scale, textScale, radii, blur, motion | partial | lib/design/tokens.dart, theme.dart — Android uses its own scale and platform font, not ui-tokens values. |
| 6. Design tokens | Dark palette (bg #0b0c10, accent #22e3a8 …) | partial | lib/design/tokens.dart LnPalette.dark — Different values (bg #141414, brand #8D8CF5). |
| 6. Design tokens | Light overrides | partial | LnPalette.light — Different values. |
| 6. Design tokens | High-contrast and opaque-glass fallbacks | missing | — |
| 6. Design tokens | visual.ts rich-response metrics | partial | lib/features/rich/visual/visual_view.dart — Chart height 200 matches; other metrics come from lib/design. |
| 7. Endpoint coverage | POST /auth/devices/enrollment[/verify] | missing | — |
| 7. Endpoint coverage | GET /market/instruments\|instrument\|quote\|candles\|calendar | partial | market_data.dart — /market/instruments list not called. |
| 7. Endpoint coverage | GET /voice/sessions/{id}, POST …/interrupt | missing | — |
| 7. Endpoint coverage | POST /app-opens, GET/DELETE /app-opens | partial | owner_knowledge_screen.dart (GET/DELETE) — POST never sent. |
| 7. Endpoint coverage | GET /version, GET /health | partial | settings_core_data.dart (GET /version, About) — /health (maintenance overlay) not used. |

