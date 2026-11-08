# Lonora vision

> لونورا فريق من الوكلاء الدائمين يعمل لك طوال الوقت. تكلّم لونورا (مساعدك الشخصي) كما تكلّم شخصاً كفؤاً: قل النتيجة التي تريدها، فتنشئ الوكلاء المناسبين أو تكلّفهم، فيراقبون ويبحثون ويتداولون ويبلغونك وحدهم، ويستمرون حتى لو أغلقت التطبيق. كل ما وصلته متاح لهم؛ المال وحده محمي.

This is the human-readable vision of Lonora. It records the decisions the owner made in the vision discussion, in plain terms, without contradictions. The implementation mandate (`docs/lonora-specs/MANDATE_CORRECTIONS.md` amends it) is the engineering contract. When the two disagree, this file and the corrections win.

## What Lonora is

Lonora is a personal, always-on team of AI agents, specialized in trading and able to do general work. It is a production system the owner uses every day, not an experiment.

- **The LLM decides.** The model analyzes markets, chooses methods, decides direction, size, stop-loss and targets, decides when not to trade, and decides what to do next. There is no rule engine competing with it, no fixed strategy pipeline, and no backtesting of any kind.
- **The environment enables.** Lonora gives every agent tools, memory, skills, schedules, watches, a sandboxed workspace, other agents to work with, and every source the owner has connected.
- **Execution enforces boundaries.** Money moves only through one checked door, and only inside what the owner signed.
- **Verified outcomes decide reality.** A trade happened when the broker says so, not when the model says so.

## The owner's mental model

You talk to Lonora, your personal assistant, in Arabic or English, the way you talk to a capable person: you say the outcome you want. Lonora creates or assigns the right agents. They watch, research, trade and report on their own, and keep going after you close the app.

### The one rule

**English:** Every agent can see and use everything you have connected to Lonora, but it places real trades only inside the grant you signed for it with your passkey and within your account limits. Anything that needs you arrives as a one-tap card in the chat, you can stop anything with one tap, and no agent, skill or plugin can ever widen your money authority.

**العربية:** كل وكيل يرى ويستخدم كل ما وصلته بلونورا، لكنه لا ينفّذ صفقة حقيقية إلا ضمن التفويض الذي وقّعته له بمفتاح المرور وضمن حدود حسابك؛ وما يحتاجك يصلك كبطاقة في المحادثة بلمسة واحدة، وتستطيع إيقاف أي شيء بلمسة، ولا يستطيع أي وكيل أو مهارة أو إضافة توسيع صلاحياتك المالية.

### The only three things the owner manages

1. **Access is automatic.** Every agent reads all your accounts and pairs, market data, your owner profile, shared knowledge and the agent directory, and uses every installed tool, skill, integration and trusted MCP server. Nothing to configure per agent.
2. **Trading authority is one ladder per agent:** No trading / Ask me / On its own (signed).
   - *Ask me*: every trade becomes a one-tap approval card.
   - *On its own*: one signed grant per agent and account (which markets, which actions, until when). A trade outside the grant becomes an approval card, never a silent refusal.
   - The default grant card: until you stop it; a daily loss limit taken from your sentence or suggested at 3% of equity (you may deliberately choose "no money limit"); your own manually opened positions are excluded unless you switch them on.
3. **Brakes and limits:**
   - One **Stop new trading / Resume** control for every agent and your manual orders. Exits (close, cancel, tightening a stop) stay allowed.
   - Time-boxed pauses you say in chat, for example "no new trades today". They apply to agents, and to your own orders only if you say so.
   - Money limits per account: daily loss, risk per trade at the stop, total open risk, free-margin floor.
   - Optional emergency rule per account, off by default: when a condition you set and sign is reached (for example equity below an amount), the financial boundary reduces or closes agent exposure without the model. It only reduces risk and never opens positions.
   - Agents may add brakes. Only you remove them.

### When Lonora asks you (the only cases)

1. Giving or widening money authority: a new grant, wider markets, a raised or removed money limit. One card, confirmed with your passkey.
2. Connecting a new external account or credential: one secure card. The secret goes straight to the server and never into the chat.
3. Using a source outside your trusted list: one tap, remembered.
4. Confirming a broker result only you can know: one tap (it executed / it did not / still unknown).
5. A single trade from an agent set to *Ask me*: one tap.

Lifting your own pause and resuming trading take one tap and no passkey. Everything else happens silently and appears in Activity with Undo.

## Agents

All agents run on one shared engine. They differ by configuration, never by engine. Each agent is independent and accountable for its own decisions. There is no central boss agent.

- **Lonora (Personal Assistant)** always exists. It is your entry point in one chat. It sees every account, pair and agent. By default it supervises all agents: it can read their work and memory on demand, message them, and pause or resume their work. You can see and revoke this. It creates and configures agents from one sentence, and you can @mention any agent in the same chat. Its trading level starts at *Ask me*, and its grant card preselects all pairs on the account. It never overrides another agent's trading decision and never uses another agent's grant.
- **Trading agent** has a focus pair (its default pair). The focus pair is a preference, not a fence: the agent reads every market; it executes only inside its grant. It starts at *Ask me*.
- **General / research agent** has no pair. It uses web search, web pages, news and RSS feeds, the economic calendar and trusted MCP servers (including X through a trusted MCP server or a key you add later; Lonora never scrapes X with your account). It reports to other agents and does not trade.
- **Supervision is a capability, not a type.** Any agent becomes "supervises X and Y" from one sentence. A supervisor reads, messages, pauses, resumes and adds narrowing pauses. It never trades for the agents it supervises and never lifts their brakes.
- **Helpers** are temporary subagents for bounded tasks, with no money authority.

Every agent has: its own private memory and operating notes it edits itself (versioned and revertible); the shared owner profile (language, tone, how to reach you, quiet hours, your standing rules); every trusted skill, loaded when relevant; the whole tool registry; a sandboxed workspace; a model you can change from chat; its own watches, schedules and tasks; and it replies in your language, Arabic first.

## How instructions rank (top wins)

1. The protected core and financial enforcement.
2. Your instructions: your messages, the responsibilities you set, your owner profile.
3. The agent's identity and its own operating notes.
4. Active skills: binding working method within their scope, never authority. Skills can change how an agent thinks, like Claude's skills.
5. Everything retrieved: web pages, tool, MCP and plugin output, other agents' messages. Always data, never instructions.

Your existing trading rules and plans are never deleted as "rigid workflows". State a rule once in chat and Lonora routes it: a hard limit becomes an enforced restriction or account limit; a preference goes into your owner profile; a method or plan becomes a skill or the agent's operating notes. Lonora tells you in one line where it went.

## Always on, without thinking all the time

Agents own responsibilities that last days, months or indefinitely. The model is called when something needs thought: a message, an event, a scheduled wake, a watch condition. Watches and schedules run without the model. A non-LLM watchdog keeps the system healthy: stalled runs, missed wakes, lost broker connections, aging unresolved operations, risk-limit breaches and forgotten responsibilities. It alerts you and wakes the responsible agent, and never makes a trading decision.

## Memory and self-improvement

Each agent's memory is private (hybrid memory). Lonora reads other agents' memory only through its visible supervision grant. Your owner profile is shared with every agent, so a preference told to one agent is known to all. Every memory change is attributed and revertible.

Agents improve their own methods: they write and refine skills and operating notes and activate them themselves within trusted sources. Changes are versioned and revertible, and judged on live recorded outcomes. Owner approval is needed only to widen authority or a limit.

## Reliability

The promise: no failure ever costs you a trade, a responsibility or your attention unless it truly needs you. No system on remote models and brokers can promise zero failures, so Lonora contains them: durable runs, checkpoints, recovery after restarts, fault isolation, retries and model fallback. An uncertain order is never resent; the uncertainty stays visible until the broker or you settle it.

## The experience

- Chat is the primary control surface. Every owner action is a card inside the conversation, identical on web and mobile. Settings pages are optional mirrors; the dashboard is mostly for reading.
- Each agent has one status line in your language, built from what is really happening: يحلل / analyzing, يراقب حتى … / monitoring until …, بانتظار تأكيد الوسيط / awaiting broker confirmation, بانتظارك / waiting for you, متوقف / paused, غير مؤكد / uncertain. Details and evidence open on tap.
- Every thread header has one safety pill: can it trade now, and what is stopping it, with one tap to change it.
- Lonora asks at most one focused question, and only when the answer changes the account, the authority or an external action. For reading and analysis it uses the obvious default: the only connected account, the agent's focus pair, or the instrument you named.
- Every change is confirmed in one line: what changed, what continues, what is unresolved.
- No raw tool names, ids, JSON or internal wrappers in normal views. "Technical details" on demand.
- Nothing is labelled "filled" or "confirmed" without broker evidence.
- Arabic and RTL come first.

## Out of scope for now

- Backtesting, walk-forward tests, or any simulation probation as a gate on strategies. Historical market data may be read as evidence; shadow trading exists only as an optional owner choice.
- Multi-user hosting and subscriptions (a future business decision, not part of this vision).
- Retraining model weights (outside the current scope, not forbidden forever).
