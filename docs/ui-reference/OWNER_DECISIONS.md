# Reference UI — owner decisions

Recorded 2026-11-09 from the owner's answers to the questions in `CAPABILITY_MAP.md` (OQ numbering there maps to Q numbering here as noted). These decisions are binding for phases 2–6. Where the owner wrote "approve", the map's recommendation is adopted as written there.

## Standing rules the owner restated

- **Vocabulary**: keep the reference's own terms everywhere; do not introduce new terminology (Q19).
- **Agents and groups are never deleted**: only their conversation history is hidden for the owner (Q1, Q44). The server's `DELETE /api/agents/{id}` and `DELETE /api/groups/{id}` get no UI.
- **Lonora is the only channel to the owner**: no Telegram or other external delivery channels to the owner (Q53). Inbound Telegram to an agent stays as the server has it, with the row reworded.
- **The agent has access to every tool** and may use them; the UI shows the results in the reference's visual language (Q37).
- **The team decides UI questions itself** (2026-11-09): within the reference's look, these decisions and the money-safety invariants, Claude and its agents make UI decisions and record the reason. The owner is asked only when the reference and an owner decision or a money-safety invariant genuinely conflict.
- **The agent decides the shape of each answer** (2026-11-09): text only, text with an interface, or an interface only, chosen every turn from what the owner will do with the answer. No keyword router, no forced interface, no separate classifier call. The behaviour follows Open Intelligent UI (github.com/thesysdev/open-intelligent-ui); the look is the reference's generative UI.
- **Skills and prompts are written in English only** (2026-11-10): every instruction text the model reads (skills, playbooks, constitution, prompt blocks such as `<lonora_answer_shape>`, worked examples and counter-examples) is English, with no Arabic examples; the model understands any language. Owner: «بنسبة للskills لايجب ان يكون به اي مثال عربي كله انجليزي لن الllm يفهم اي لغة». The model still answers in the owner's language. Not covered by this rule, so they stay Arabic: what the owner sees (UI strings, server-composed bubbles and notices, the reference's terms in the catalogs), the evaluation's owner messages (they stand for what the owner types), and server-side matching data (instrument names, owner-text checks).
- **Generated cards speak the owner's language** (2026-11-10): the agent writes every word of a generated card (title, labels, options, hints, lead line) in the language the owner writes in, whatever it is, Arabic, English or any other; no fixed card labels are imposed from a catalog. Owner: «بنسبة للبطاقات الوكيل يستطيع وضع لغة المستخدم التي يتحدث به حتى لو سرلنكية». The app's own chrome around a card (its buttons, the lock line, «لماذا هذه الواجهة؟») stays in the app's interface language, and the reference's terms (Q19) govern that chrome.
- **No Alpaca** (2026-11-10): the owner does not need the Alpaca broker at all («لي Alpaca لا داعي نهائين ولانحتاجه»). The broker form offers MetaApi and «تجريبي» (the simulation provider) only. MetaApi is the default and opens preselected; «تجريبي» is the secondary choice (owner: «لكن metaapi افتراضي»).
- **No further built-in brokers** (2026-11-10): the owner reaches other brokers and platforms through MCP connections, and later through plugins, so Lonora adds no other broker by default («المستخدم يستطيع استخدام اي وسيط او منصة عبر ربط mcp فا لاداعي لنضيف وسيط او اكثر افتراضي و لاحقاً نضيف بلوجن لي اي منصة متاح الاتصال معه»). The money-safety rule is unchanged. An MCP tool that can place a trade or move money is refused, as it has been since Wave 1.5 (`docs/trusted-sources.md`): through MCP an agent reads, analyses and acts without financial effect. A platform that should trade arrives as a plugin behind the single executor, the way MetaApi works today, so the signed grant, limits, approval cards, Stop and reconciliation apply to it. The owner approved this design on 2026-11-10 («طبعا موافق على اقتراحك»).
- **Fresh start, no legacy data** (2026-11-10): Lonora is being built as a new system, with no agents or data that must be carried over; if needed, the database is created fresh as for a new project («نحن نبني نظام جديد يعني لايوجد وكلاء كانو يعملون او اي شيء لو لو فيه نعيد قاعدة المشروع وكانه جديد»). Migrations stay correct and reversible on a fresh database, but they need not settle or convert legacy runtime data (for example former Shadow agents). The first production install starts from an empty database.
- **Future**: Lonora may become a hosted product in the style of myclaw.ai; keep the auth layout extensible for that, but do not build multi-user now (Q46). When the mobile app is built, do not forget push notifications and the notification permission flow (Q10).

## Phase 2 — layout, lists, sheets

| # | Decision |
|---|---|
| Q1 (OQ2) | «مسح» / «حذف» on any conversation, agent or group, = hide the history for the owner on the server (visibility cursor), keeping the thread, grants and ledger. Agents and groups are never deleted from the UI: the agent and the group stay with their members; only the chat history is hidden. The server's `DELETE /api/agents/{id}` and `DELETE /api/groups/{id}` get no UI. (Revised 2026-11-09 by the owner: «المجموعات والوكلاء لا يمكن حذفهم، يُحذف سجل الدردشات فقط».) |
| Q2 (OQ3) | One grey tick = accepted by the server. Two accent ticks = the agent's run started on that message. Exposed per message and on the inbox `last_message`. |
| Q3 (OQ7) | Pins, mute, archive, favourites, marked-unread, custom lists and keep-archived live on the server per owner (`ln_thread_prefs`, `ln_chat_lists`), shared by web and mobile. |
| Q4 (OQ6) | Mute suppresses message heads-ups, sounds and the badge only. Critical / action_required attention items always show. Archive behaves the same. |
| Q5 (OQ8) | Unified search: files = artifacts; knowledge = agent memory + semantic notes labelled by agent; skills = installed skills. Owner-wide search reads every agent's memory; agents never do. |
| Q6 (OQ1) | Offline queue auto-flushes only plain messages that received no server response and carry no approval, input answer or owner decision; those stay «failed» with manual retry under the same client_nonce. |
| Q7 (OQ9) | English is enabled in the language row now. |
| Q8 (OQ5) | Groups gain `purpose` (≤160) and `lead_agent_id`; the lead answers when no agent is mentioned. |
| Q9 (OQ4) | The creation template (trading / general / research / supervisor) is persisted on `Agent` and the client type derives from it, with role/scope_mode as fallback. `POST /api/agents/create` takes the same input as the `agent_create` tool. |
| Q10 (OQ10) | Browser notification permission and phone-notification settings are hidden until a push channel exists. Mic and camera permission sheets ship. Revisit for the mobile app. |

## Phase 3 — conversation

| # | Decision |
|---|---|
| Q11 (OQ11) | ResolveCard «غير معروف» follows the server: settle as unknown, release the hold, never resend. Add the optional switch «أوقف الصفقات الجديدة اليوم» on the card, creating an owner restriction. If a cleaner design emerges (even dropping the switch), the owner asked for the best implementation. |
| Q12 (OQ12) | Owner-action cards stay in the conversation, rendered with the reference's `.oa` / `.oa-line` styling and OwnerActionSheet field layouts, and are also openable as sheets from the permission chip and the agent page. |
| Q13 (OQ13) | Server lifetimes for cards; countdown shown only on resolve cards and only under one hour. |
| Q14 (OQ14) | The AgentSheet «التداول» row shows the global brake («إيقاف الصفقات الجديدة» / «استئناف»); «تعليق الصفقات الجديدة» for one agent is an agent-scoped owner restriction. Per-agent state comes from `trading_readiness`. |
| Q15 (OQ15) | Lifting a limit-born restriction stays one tap; the limit itself is passkey-protected. |
| Q16 (OQ16) | Money limits use the server's fields (amounts in account currency for daily loss and free margin, equity % for trade/open risk) in the reference's old → new layout. |
| Q17 (OQ17) | Full delegation as the server defines it: Lonora and flexible agents get «كامل» = all pairs on the account. A fixed-pair agent's «كامل» means full delegation on its own pair only (all actions, until stopped, manual positions included). |
| Q18 (OQ18) | Mandate defaults follow D1 in the reference's layout; «التشغيل دون حد مالي» is the server's `money_limit=none` choice. |
| Q19 (OQ19) | The permission ladder is trading-only. General agents show the «لا يتداول» badge; non-financial approvals go through the existing cards. Keep the reference's terms. |
| Q20 (OQ55) | General agents never pay or send on the owner's behalf. A general agent is a research-and-answer agent (search, answer questions, reports), like a general chat assistant. Remove «دفع» and «إرسال» from the general ladder texts. |
| Q21 (OQ20) | Edit-and-resend = cancel the pending run and send a new message linked to the original (`edited_from`); the original collapses as superseded with «مُعدّلة». |
| Q22 (OQ21) | No spend cap (D4): show month-to-date usage and projection without blocking; error cards reflect the provider's actual error family. |
| Q23 (OQ22) | The agent emits a ≤60-char `suggested_reply` for conversational answers only, never after cards. |
| Q24 (OQ23) | Voice notes: audio uploaded as an artifact, transcribed on the server with the configured provider, transcript stored as message content; the silent-recording fallback is dropped. |
| Q25 (OQ24) | Dictation: browser speech API first; a professional server-side transcription path (provider-based, inspired by Hermes/Rakazo-grade open-source approaches) as the upgrade. |
| Q26 (OQ25) | Reactions: owner and agent. The agent reacts only when it judges it fitting, not on every message (needs a `message_react` tool with that policy). |
| Q27 (OQ26) | Generative UI: add `why` and a non-financial `submit {intent, data}` action rendered as a quoted user message; Quiz/Timer count as light personal tasks. |
| Q59 (2026-11-09) | Generated-UI choices (Chips) render as the current reference's rows (`.ux-picks` / `.ux-pick`, radio or check rows), not the older pill chips; segmented controls stay. Owner: "B اعتمد المرجع الحالي". |
| Q28 (OQ27) | No emoji button in the composer; quick reactions keep the six fixed emojis; the emoji panel lives only in the new-list sheet. |
| Q29 (OQ28) | An @mention of another agent in a direct chat starts a collaboration session; the guest answers under its own name and colour. |
| Q30 (OQ29) | Order timeline shows the server's operation states under the reference's names, with partial quantity from the result. The owner's own modify/close buttons are the owner's direct order through the executor. |
| Q31 (OQ30) | Undo for an extended watch; no undo for a tightened stop. |
| Q32 (OQ31) | Trade approvals gain `expires_at` (30–60 min), lazily settled; expired cards show «طلب جديد». |
| Q33 (OQ32) | Per-chat web search is a persisted thread option the agent reads. |
| Q34 (OQ33) | Calls are logged as bubbles in the thread (direction, duration, missed). |
| Q35 (OQ34) | «حالة الوكيل التفصيلية» is a per-device preference, off by default; the alert capsule always shows problems. |
| Q36 (OQ56) | Fenced code blocks are allowed as explanation with «نسخ الكود»; refusing code as a deliverable stays agent policy (D5). «الملفات» holds text files only; `.json` skill import is data. |

## Phase 4 — agent and domain pages

| # | Decision |
|---|---|
| Q37 (OQ36) | Chart: the reference's look with real candles; agent annotations and indicators rendered as read-only overlays in the same visual language. The agent keeps full access to all chart tools. |
| Q38 (OQ37) | «إيقاف الوكيل» is hidden on Lonora's page with no explanatory line; kept for other agents. |
| Q39 (OQ38) | Routines gain `title` and one-shot `run_at`; «عند تحقق شرط» creates a market watch with a prompt; the notification channel is owner-wide. |
| Q40 (OQ39) | Knowledge: notes → semantic notes; links → new `link` entry. The documents list may be dropped if it adds nothing. |
| Q41 (OQ40) | Trading agents show trading goals (plans) in the reference's list style; non-trading agents get light goals if the page is wanted for them. |
| Q42 (OQ41) | Avatar editor keeps the reference layout with Lonora's avatar shapes. |
| Q43 (OQ52) | Tasks gain `due_at` and `completion_criteria`. |
| Q44 (OQ57) | No agent deletion in the UI. Only history hiding (Q1). |
| Q45 (OQ54) | Activity is a server projection over durable events and receipts (`GET /api/activity`); the client never invents entries. |

## Phase 5 — settings, onboarding

| # | Decision |
|---|---|
| Q46 (OQ35) | Ship: intro slides, e-mail + password sign-in, «انتهت جلستك», and the first-run bootstrap step in the same `#auth` layout. Phone/OTP, sign-up and forgot-password stay out of production. Keep the layout extensible for a future hosted product. |
| Q47 (OQ42) | Quiet hours in minutes. Per-agent notification preferences exist (a small per-agent delivery-rules record). |
| Q48 (OQ43) | No privacy data actions (export / reset / delete account) in the UI at all. |
| Q49 (OQ44) | No support or bug-report sheets. |
| Q50 (OQ45) | No terms or privacy pages. |
| Q51 (OQ46) | App lock with 4-digit PIN; biometric unlock through a real WebAuthn platform credential, hidden where unavailable. |
| Q52 (OQ49) | Broker form: the server's fields (token, account id, region) in the reference layout; «تجريبي» = the simulation provider. Real adapters only. |
| Q53 (OQ50) | No delivery channels to the owner other than Lonora. Telegram remains an inbound agent channel with its row reworded. |
| Q54 (OQ51) | Remove the «حول» section. Show the Lonora version at the bottom of the settings sections. «دليل الواجهات» and the HTML download are dev-only. |
| Q55 (OQ53) | Drop the per-agent MCP allow list. |
| Q56 (OQ58) | MCP: remote servers only (like any global AI agent); no local/stdio option shown. |
| Q57 (OQ47) | Shadow trading is removed entirely. The other homeless server features are recorded as follow-ups (API-only, nearest sheet, or retire) and decided per feature later. |

## Phase 6 — calls

| # | Decision |
|---|---|
| Q58 (OQ48) | Call button is shown disabled when no voice provider is configured; tapping it shows a warning with a button that opens the voice provider settings. |
