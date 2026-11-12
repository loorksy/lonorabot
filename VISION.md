# Lonora Execution Mandate

**Status:** Binding. Non-negotiable. Issued by the owner.
**Supersedes:** `VISION.md`, `docs/lonora-specs/MANDATE_CORRECTIONS.md`, and every document, spec, plan, owner-decision log, system prompt, constitution file, test expectation or code comment that conflicts with it.

---

## 0. How to read this document

1. This mandate is an order, not a proposal. Implementers do not reopen any decision in it. Questions about *how* to implement go to the owner. Questions about *whether* are already answered here.
2. **MUST**, **MUST NOT** and **MAY** are used in their RFC 2119 sense.
3. Every clause is binding. Unmarked clauses restate decisions the owner made explicitly. Clauses marked **[Adopted]** were proposed during the design conversation and are adopted by the owner's issuance of this mandate. They are equally binding, and they are the first candidates if the owner revises.
4. When anything in the repository contradicts this mandate, the mandate wins. Contradicting code is rewritten or deleted in the phase that section 15 assigns to it, in the order of section 14.1. Until then it keeps working, and no change may extend it. Documents and prompts describe the system as it behaves at each commit. Text describing behavior that is not built yet is added in the change that builds it.

---

## 1. What Lonora is

Lonora is a **delegated trading agent**: a professional AI trader that the owner authorizes to trade the owner's accounts, so that the owner can wake up and find profit in the account.

It combines three things:

- **The agent philosophy of Grok Bot and Rakazo.** An agent with its own environment, tools, memory, skills, routines and secrets. It is given an outcome in plain language and works toward it on its own.
- **A specialization in trading.** First-class market, account and execution tools, and the judgment of a professional trader.
- **The proactivity of Claude Duet.** The agent comes to the owner with what matters, keeps working while the owner is away, and reports. Claude Duet refuses to trade or move money; Lonora exists to fill that gap.

Lonora is **not** a rule engine, a risk lecturer, an advisor that hedges every sentence, or an administration system for permissions. If a feature makes the agent talk about trading instead of trading, it is wrong.

---

## 2. Core principles

- **P1. The agent is the owner's delegate.** In Full mode it decides everything a trader decides (section 5). There are no caps, quotas, money limits, activity budgets, cooling-off periods, risk disclaimers, or refusals to take a view.
- **P2. Lonora enforces correctness and the owner's own controls, never judgment.** The system enforces only these things against an agent:
  - the invisible safety core (section 6);
  - Stop (4.8);
  - the agent's mode (4.1);
  - the owner's pauses (4.7);
  - the structure rules of 3.2.2 and 3.3.1;
  - position ownership (3.3.4).

  Nothing else limits a trading decision.
- **P3. Build an environment, not features.** There are millions of things an owner may ask for. Lonora does not build a feature per request. It gives agents general primitives (terminal, network, secrets, time, memory, interface) and lets the model compose them.
- **P4. One engine.** Every agent runs on Lonora's single agent engine. Claude Code, the Claude Agent SDK and every other agent harness MUST NOT be used as Lonora's engine. This binds Lonora's own code and deployment. It does not limit which command-line tools an agent runs in its workspace (7.1).
- **P5. Chat is the control surface.** The owner talks; agents act and answer.
  - **Inside a conversation:** every element is the agent's chosen presentation (section 10), except the five fixed cards.
  - **Outside conversations,** the app has only:
    - the Stop control;
    - the agent and conversation list;
    - the "needs your attention" view (11.7);
    - the "What I know about you" view (8.4);
    - the "What is running" view (7.1.5);
    - sign-in.

  Everything else is done from chat.
- **P6. Proactive by default.** Agents bring results, questions and reports to the owner without being asked.
- **P7. Nothing built stays switched off.** A built feature is switched on or completed (section 13).
- **P8. Model providers use API keys only** (section 12).

---

## 3. Agents: one lead and a team

### 3.1 Lonora, the lead agent

Lonora always exists and is the owner's first point of contact.

1. **Lonora trades** like any other agent, under its own mode (section 4).
2. **Lonora leads the team.** On its own judgment, without asking first, it MAY:
   - create agents;
   - give them responsibilities and instructions;
   - edit their methods;
   - pause and resume them;
   - cancel their current run;
   - delete them.

   It tells the owner in one line what it did and why.
   - **Instruments and accounts** Lonora assigns to an agent are instructions in the agent's method. The execution door never binds an agent to an account or symbol.
   - **A new agent** uses Lonora's current model until the owner assigns another (12.3).
   - **Deleting an agent:**
     - its open positions and pending orders transfer to Lonora;
     - its pending Trade Approval cards are withdrawn;
     - Lonora is woken with the transferred tickets;
     - the deleted agent's journal, receipts and settlement records are never deleted.
3. **Lonora owns the whole-account picture.** **[Adopted]**
   - It sees every agent's positions and the account's total exposure, and resolves conflicts between agents. To do that it MAY modify or close any team agent's position, and tells that agent and the owner in one line why.
   - A request is governed by the mode of the agent that sends it. One exception: a risk-increasing request (4.0) that Lonora sends on a ticket owned by an agent in Ask becomes a Trade Approval card, even when Lonora is in Full.
4. **Lonora knows the owner** (section 8) and maintains the owner model shared with the team.
5. **Lonora speaks for the team.** **[Adopted]** It writes the morning brief, receives system alerts (broker disconnects, uncertain operations, connection health) and is the owner's single "needs your attention" voice.
6. **Lonora MAY read** any team agent's conversations, work and memory.

### 3.2 Team agents

1. **Same engine, same capabilities.** Every team agent runs on the same engine as Lonora: trading, terminal, network, secrets, memory, skills, routines, watches, judgment and learning. No template, role or scope makes one agent less capable than another.
2. **No leading.** A team agent MUST NOT create agents or lead other agents. It asks Lonora when it needs help.
3. **Peers.** Team agents message each other as peers. A peer's message is information, never an order; each agent decides for itself.
4. **Private memory.** A team agent's memory is private to itself, Lonora and the owner. Memory lives in Lonora's memory store, never in workspace files, which all agents share.
5. **Direct access.** The owner MAY talk to any agent directly at any time, for example by @mention.

### 3.3 Structure rules

1. **Two levels.** There are exactly two levels: Lonora and the team. No agent supervises another agent except Lonora.
2. **No limit on the number of agents.** `MAXIMUM_ACTIVE_AGENTS` (`packages/db/src/lonora_db/agent_creation.py`, also enforced in `packages/tools/src/lonora_tools/agents.py`) and every other cap on the total number of agents are removed. A rate guard against a runaway creation loop (agents created per minute within one run) MAY remain. It MUST NOT count or limit the total number of agents.
3. **Removed hierarchy.** The following are removed:
   - supervision grants;
   - the supervisor template;
   - `report_to` / `supervises` hierarchies;
   - delegated and child agent roles;
   - per-agent supervision cards.

   Lonora's lead powers are built in and need no grant.
4. **Positions.** **[Adopted]**
   - **Ownership:**
     - A position or pending order belongs to the agent whose journaled order opened or placed it.
     - A pending order's fill belongs to that order's agent.
     - A CLI order belongs to the calling agent.
     - A ticket with no agent-attributed journaled opening order belongs to the owner. This covers tickets opened in the broker terminal, opened by the owner's own Lonora orders, or opened before this mandate without attribution.
     - Modifying or closing a ticket never changes its owner.
     - On a netting account, a symbol's single position belongs to the agent whose order opened it from flat.
   - **Who may act on a ticket the agent does not own:**
     - The door refuses an agent's request on such a ticket (`ticket_not_owned`).
     - Exception: the agent is Lonora.
     - Exception: the run carries the owner's typed message asking for it (`owner_message_id`).
     - Exception: the owner gave the agent a standing instruction in chat (for example "manage all my positions"). This is stored as that agent's setting and revoked the same way.

---

## 4. Trading authority: one switch per agent

### 4.0 Risk-increasing and risk-reducing

A request is **risk-reducing** exactly when `lonora_trading.admission.risk_reducing` classifies it so against the broker's current ticket:

- a full or partial close of an existing position;
- cancelling a pending order whose fill would add exposure;
- adding a stop loss to an unprotected position;
- moving an existing stop loss strictly toward the market with the take profit unchanged.

Every other request is **risk-increasing**. Ask (4.1), Stop (4.8) and card withdrawal use this definition and no other.

### 4.1 The two modes

Each agent has exactly one trading mode:

- **Full** (Arabic UI «وكّله»): the agent executes on its own and reports afterwards.
- **Ask** (Arabic UI «يستأذن»): every risk-increasing request becomes a fixed Trade Approval card (10.3). Risk-reducing requests need no approval.

There is no third level. "No trading", "analysis only" and the analysis/supervised/autonomous ladder are removed.

### 4.2 Changing the mode

1. **Setting Full.** Only the owner's tap on the fixed Mandate card sets an agent to Full. There is no passkey, no signature, and no envelope of markets, actions or duration.
2. **Setting Ask.** Any agent MAY switch itself to Ask. Lonora MAY create an agent in Ask, or switch any team agent to Ask, on its own judgment, and tells the owner in one line. Switching to Ask needs no confirmation.
3. **When the door reads the mode.** The door reads the mode at send, under the per-agent authority lock (`packages/db/src/lonora_db/authority_lock.py`).
   - A risk-increasing request not yet sent when its agent switches to Ask is refused with `trade_approval_required`; the agent may raise a card.
   - Switching an agent to Full withdraws its pending Trade Approval cards and wakes it with fixed text to decide again under Full.
   - A card is never executed because of a mode change.

### 4.3 Defaults **[Adopted]**

1. **Lonora** starts in Ask, and offers its Mandate card during onboarding.
2. **An agent the owner asks for** starts in the mode the owner named. A request for "full authority" shows the Mandate card for that agent. If the owner named no mode, the agent starts in Ask.
3. **An agent Lonora creates on its own judgment** copies Lonora's mode at the moment of creation, unless Lonora creates it in Ask.
4. **Later changes** to Lonora's mode never change another agent's mode.

### 4.4 Removed

The following are removed entirely:

- passkey-signed `AccountAuthority` grants;
- Custom/Full delegation envelopes, grant durations and action budgets;
- per-account money limits;
- owner execution caps;
- time-boxed trading restrictions and pauses;
- trading goals and goal step plans;
- activation reviews;
- the planned owner-signed automatic-reduction rule (D2 in `MANDATE_CORRECTIONS.md`). It was never built, and it is not the `emergency_stop` flag, which stays.

Exact code is listed in 14.2.

### 4.5 Full mode keeps working while the owner is away

1. **Start.** Switching an agent to Full starts one continuous account-management task for that agent, covering every connected account. It replaces the per-grant task that `finish_activation` (`packages/auth/src/lonora_auth/account_authority.py`) creates today.
2. **End.** Switching the agent to Ask, pausing it, or deleting it ends that task. Stop does not.
3. **What ending does not do.** Ending the task never cancels the agent's own watches, routines and timers. It never stops the agent from managing its open positions and pending orders in Ask mode.

### 4.6 Kept

The owner's own pause of a specific piece of work is kept: an agent, routine, watch or task the owner paused stays paused until the owner resumes it (4.7).

### 4.7 Pauses

1. **What a paused agent does.** A paused agent takes no new work.
   - It wakes only for its own open positions and pending orders.
   - It may send only risk-reducing requests.
   - Its routines, watches and timers are held.
2. **Who lifts a pause.** Only the owner lifts a pause the owner made. Lonora lifts only pauses Lonora made.

### 4.8 Stop

1. **One control.** Stop is one global control, always visible in the app. It is not a card.
2. **What it is.** Stop is the stored `TradingControl.emergency_stop` flag, checked by `require_trading` (`packages/core/src/lonora_core/trading_control.py`), and nothing else.
   - `TradingControl.enabled`, the "trading not started" state, and the `resume_trading` card are removed.
   - A new install starts not stopped.
3. **While stopped:**
   - The door refuses every risk-increasing request from any agent or the CLI.
   - No Trade Approval card containing a risk-increasing request can be created.
   - Risk-reducing requests remain allowed. Agents keep analyzing and managing.
   - **[Adopted]** An explicit order the owner types in chat is executed as the owner's own order.
4. **Pressing Stop:**
   - It withdraws every pending card that contains a risk-increasing request. A withdrawn card never returns; on its next wake the agent decides whether to ask again.
   - It does not cancel or change orders already resting at the broker.
   - It does not affect orders the owner places outside Lonora.
5. **Resume** is one tap on the Stop control itself.

---

## 5. The agent's mind: judgment

### 5.1 The model decides

Instrument, direction, entry, size, number of positions, stop loss, take profit, adding, reducing, hedging, exits, and whether to trade at all are the agent's decisions.

### 5.2 Kinds of judgment

Agents MUST be taught and allowed to use the full range of a professional trader's judgment. The following are examples of judgment the agent may choose, never rules it must follow:

- **Entry:** enter, wait or skip. Not trading is a decision.
- **Scaling in:** open additional positions with a move that is working.
- **Secure, then add:** move a winning position's stop to break-even or better, then open the next one.
- **Several concurrent positions** in one or more instruments.
- **Management:** trail stops, take partial profit, extend targets on strong momentum, and exit early when the reason for the trade is broken.
- **Sizing:** the agent sets size per trade from its own reading of the setup and of its results.
- **Portfolio awareness:** exposure across instruments and across the team.
- **Timing:** sessions and events that suit its method.
- **Self-scheduling:** setting its own watches and timers to wake itself (for example "wake me at 2,425 to consider adding").

### 5.3 Voice

1. **How it talks.** An agent speaks like a decisive professional trader. Every sentence carries a number, a position, a decision or a question.
2. **What it never says.** No risk disclaimers, no "trading involves risk", no "this is not financial advice", no emotional language, no reassurance, no filler, and no refusal to give a view.
3. **Honesty.** It never states a profit the account does not show, and never claims an execution the broker has not confirmed.

### 5.4 Full picture on every wake

Each time an agent wakes it receives:

- its own positions, orders, exposure, and realized and floating P&L;
- the whole team's open positions and pending orders, grouped by symbol and by currency (each leg of a pair, and the quote currency of other instruments);
- high-impact calendar events in the next 24 hours for those currencies;
- whether Stop is in force.

Judging correlation is the agent's job.

### 5.5 Learning loop **[Adopted]**

1. **Closed trades.** A trade is closed when its position's volume reaches zero at the broker, whatever the cause.
2. **Self-review.** The broker event wakes the position's owner (3.3.4), which writes a short self-review to its memory.
3. **Judgment labels.** Each order carries a judgment label the agent chooses (for example `scale_in` or `secure_then_add`), stored beside the request (14.3.9).
4. **Statistics.** The system computes, per label, the count and net realized P&L from broker-confirmed closes, and gives them to the agent on wake. The agent adapts its methods from its own results.
5. **Versions.** Every write to a method or skill creates a version. The owner, Lonora or the agent may revert to any version.
6. **Weekly report.** Each agent posts a weekly report in its own conversation (results, what it learned, what it changed) on the first morning brief after the weekly market close. Lonora summarizes the reports in that brief.

### 5.6 Owner methods

A strategy the owner gives in any form (a message, a PDF, a file) becomes the agent's method or skill. The agent applies it and refines it from results.

### 5.7 Trading code **[Adopted]**

1. **Writing code.** Agents MAY write Expert Advisors, MQL4/MQL5, Pine Script and any other trading code.
2. **Code an agent runs itself** lives in the workspace and sends its orders through `lonora trade`, so those orders are journaled and verified.
3. **Code deployed for the owner.** When the owner asks in chat for code to be deployed on the owner's own terminal or VPS, the agent deploys it. Lonora then:
   - records the deployment;
   - reports that terminal's trades from broker history;
   - tells the owner once that orders placed by that code are outside the execution door's guarantees.

### 5.8 System prompt

1. **Rewrite.** The core prompt (`packages/agent-runtime/resources/system/lonora.md`) is rewritten around trading, not governance.
2. **Deleted text.** Every chapter and line about grants, limits, restrictions, goals and supervision is deleted. Procedural detail belongs in tool descriptions, not the core prompt.
3. **Identity line.** Line 16 keeps only "You are not Grok, Claude or ChatGPT". "A coding assistant", "an unrestricted desktop operator", and every rule forbidding the environment of section 7 are removed.
4. **Code-deliverable bans.** The bans in `constitution/identity.md` and in `prompts/genui_v2.md` line 5 are removed.
5. **Trading policy.** `constitution/trading-policy.md` is rewritten, not deleted, because `skills/loader.py` requires it. Its ladder, grant, limit, restriction and goal text is replaced.
6. **Manifest.** `resources/system/manifest.json` (`manual_sha256`, `bootstrap_sha256`, `tool_policies`) is regenerated in the same change that edits `lonora.md` or the bootstrap files, or that removes a chapter or a tool.
7. **Per-turn frame.** The replacement for the permission frame (`packages/agent-runtime/src/lonora_agent/context/permissions.py`) still gives the agent its current mode and the Stop state on every turn.

---

## 6. The invisible safety core (preserve exactly)

These are correctness guarantees. They never limit what the agent decides, only how an order is sent and verified. They are never shown to the owner as rules. They MUST be preserved through every refactor in this mandate.

1. **One execution door.** `ExecutionService.execute` (`packages/trading/src/lonora_trading/execution.py`) is the only caller of `broker.execute`. Every order from any tool, agent, or the `lonora` CLI goes through it.
2. **Journal and idempotency.** Every operation is reserved in the trading journal, with a server-derived operation id and request fingerprint, before it is sent.
3. **Never resend an uncertain order.** An operation whose outcome is unknown is reconciled with the broker, never sent again.
4. **Broker truth.** Nothing is called filled, closed or done without broker evidence.
5. **Preflight broker checks,** at planning and again at send:
   - account match;
   - trading allowed;
   - ticket existence;
   - quote freshness (`ExecutionPolicy.quote_max_age_seconds` and `account_max_age_seconds` stay);
   - stop levels.
6. **Send serialization and the stale-target check.**
   - Sends are serialized per account.
   - Today there are two stale-target checks: `require_account_execution` on the grant path, and `require_approved_target_current` (`packages/db/src/lonora_db/trade_approvals.py`) on the approval path. They become one door check that runs for every agent-originated close or modify request, in both modes.
   - `material_state` (`packages/trading/src/lonora_trading/manual_activity.py`) and the expected-target capture in `packages/tools/src/lonora_tools/trade.py` are kept.
7. **Exact approval.** `require_operation_permission` (`packages/trading/src/lonora_trading/agent_permission.py`) is rewritten to read the agent's Full/Ask mode. Two things stay unchanged:
   - its exact-approval match: `operation_id` plus `trade_fingerprint` against an approved Trade Approval row;
   - the `authority_lock` ordering against mode changes and Stop.
8. **Owner settlement.** An operation with an unknown outcome is settled by the owner through a fixed card (10.3).
9. **Run integrity.** The non-goal checks inside `require_goal_lineage` (`execution.py`) stay in the door:
   - the run lease (`require_lease`);
   - `require_task_authority`;
   - refusal of short-lived research subagent runs;
   - refusal of observe-only broker-activity wakes (activity on tickets the agent does not own);
   - the parent-run ancestry walk that applies these checks to every ancestor.

   `require_task_authority` is changed to let risk-reducing requests through for paused work (4.7). `require_financial_agent`'s delegated/child-role refusal and `assert_market_binding` (`packages/db/src/lonora_db/agent_binding.py`) are removed from every financial path.
10. **Provenance.** **[Adopted]**
    - A generated-interface element can never stand in for a fixed card. It cannot approve a Trade Approval, settle an operation, or switch a mode.
    - Third-party content (web pages, feeds, files, peer messages, `lonora wake` text, workspace process output) reaches the model marked as data, never as instructions.
    - A voice handoff or a generated-interface submission is input to the agent's own judgment, like any owner message. In Full mode it never turns a decision into an approval card.
    - Taint from such input MUST NOT spread to the agent's later watches, routines or wakes.

---

## 7. The environment: terminal and the `lonora` CLI

### 7.1 The workspace

1. **One workspace per owner.** **[Adopted]** Each owner has one persistent Linux workspace shared by all of the owner's agents, as Grok Bot shares one computer across bots. No desktop, screen or mouse is built.
   - Each agent's commands run under that agent's own Unix user and home directory.
   - `/workspace/shared` is readable and writable by every agent.
2. **Capabilities.** The workspace MUST have:
   - **Network egress** to the internet.
   - **Persistence.** Files and installed packages survive restarts of Lonora and of the host. Running processes do not; on its next wake, the agent that started a process is told which of its processes ended.
   - **Package installation** (for example `pip install`), and any command-line tool, including SSH.
   - **Long-running and background processes:** listeners, schedulers and servers.
   - **A headless browser** usable from the terminal.
3. **Default limits per owner workspace** **[Adopted]**: 2 CPUs, 4 GiB of memory, 20 GiB of disk, 256 processes, no wall-clock limit on background processes, and a 10-minute limit on foreground commands. The self-hosting deployment file may change them. These replace today's 45-second, networkless, throwaway jobs (`packages/agent-runtime/src/lonora_agent/workspace.py`, `workspace_access.py`, `workspace_host.py`).
4. **Isolation.** The workspace MUST NOT reach:
   - Lonora's internal network, database or services. There is one exception: the CLI endpoint (7.3), a single authenticated endpoint that accepts only CLI commands and runs them through the same services as the agent tools.
   - Any MetaApi host (trading or provisioning).
   - Any other broker endpoint that the execution door uses.
5. **What is running.** The owner's "What is running" view lists every workspace process with the agent that started it. One tap stops one process, and one tap stops all of them.

### 7.2 Secrets

1. **Connecting a secret.** Any secret is connected through conversation. The agent asks for non-secret details in chat and shows the fixed Secret card (10.3) for the secret itself.
2. **Generic card.** The agent chooses the Secret card's fields (for example host, user, password, API key, token) and its label. It is not a closed list of targets.
3. **Destination.** The destination of a Secret card is set by the server tool that raises it, never by the agent's choice of fields. There are two destinations:
   - **workspace:** usable by agents in the workspace;
   - **broker:** a broker account password and the MetaApi token.

   A broker-destination value is readable only by the execution door and by MetaApi provisioning. It never enters the workspace.
4. **Ownership and use.** Secrets belong to the owner. Any agent may use any workspace secret by name. The Secret card records the requesting agent for display only. Existing per-agent secrets (`apps/api/src/lonora_api/routes/agent_secrets.py`) are migrated to owner scope.
5. **Injection.** A command that names a secret receives it as the environment variable `NAME` and as the file `/run/secrets/NAME`.
6. **Redaction.** Lonora MUST NOT place a secret's value in model context, chat, logs or memory.
   - Every byte that returns from the workspace to the model, chat, logs or memory (command output, file reads, tool results) is scanned.
   - Each stored secret value, together with its base64, hex and URL-encoded forms, is replaced by `[secret:NAME]`.
   - A program that transforms a value in any other way can defeat this; that is accepted.
   - Test: a command that prints a secret, or its base64 form, returns `[secret:NAME]`.

### 7.3 The `lonora` CLI

1. **Purpose.** A `lonora` command inside the workspace connects scripts to Lonora. It calls the same services as the agent tools and adds no second implementation of any logic.
2. **Command set:**

   ```
   lonora price <symbol> [--account <id>]
   lonora candles <symbol> <timeframe> <count> [--account <id>]
   lonora account [--account <id>]
   lonora positions [--account <id>]
   lonora orders [--account <id>]
   lonora trade buy|sell|buy_limit|sell_limit|buy_stop|sell_stop <symbol> <lots> [--price ..] [--sl ..] [--tp ..] [--tolerance ..] [--label ..] [--account <id>] [--key ..] --reason "..."
   lonora close <ticket> [--volume ..] [--key ..] --reason "..."
   lonora modify <ticket> [--price ..] [--sl ..] [--tp ..] [--tolerance ..] [--key ..] --reason "..."
   lonora cancel <order> [--key ..] --reason "..."
   lonora wake <agent-handle> "<text>"
   lonora notify "<text>"
   ```

   - Volume is in lots.
   - `--account` is required when more than one account is connected.
   - Symbols are the broker's symbols.
3. **Identity.**
   - Lonora issues every agent its own CLI token and injects it as `LONORA_AGENT_TOKEN` into every command that agent starts. Child and background processes inherit it.
   - The endpoint maps the token to exactly one agent and acts with that agent's identity and mode.
   - A call without a valid token is refused with exit code 77, and nothing is sent.
   - Only the agent's own Unix user can read its token.
   - Deleting an agent revokes its token.
4. **Orders.** `trade`, `close`, `modify` and `cancel` go through the execution door. They are journaled, broker-verified, shown in reports, and turned into a Trade Approval card when the calling agent is in Ask. A CLI order is the calling agent's own order and is not "unauthenticated input" (6.10).
5. **Idempotency.** `--key <k>` makes a repeated command the same operation: the server derives the operation id from the calling agent and `k`. Without `--key`, each invocation is a new operation.
6. **Output and exit codes.** Every command writes one JSON object to stdout. Exit codes:

   | Code | Meaning |
   |---|---|
   | 0 | Executed and confirmed by the broker |
   | 10 | Trade Approval card raised. The card id is in the output, and the command returns at once |
   | 20 | Refused, nothing sent. The reason code is in the output |
   | 30 | Outcome unknown. It is reconciled per 6.3 and MUST NOT be resent; repeating with the same `--key` returns its current state |
   | 77 | Identity refused |

7. **`lonora wake`** starts a run of the agent with that @handle in its own conversation, naming the calling agent, with the text marked as data.
8. **`lonora notify`** posts the text in the calling agent's own conversation as that agent's message. It sends a push only under 11.4.

---

## 8. Knowing the owner **[Adopted, except 8.1 which is the owner's]**

1. **Learning from behavior.** Lonora learns the owner from behavior, not only from what the owner says:
   - when the owner wakes and reads;
   - how the owner reacts to drawdowns;
   - which positions the owner closes manually, and when;
   - the owner's preferred report length;
   - quiet days and hours.
2. **Replaced rules.** The rule that the owner profile records only what the owner said is replaced. It lives in the `USER.md` guidance in `lonora.md` and in the `owner_profile_requires_owner_message` and `owner_preferences_require_owner_message` gates in `packages/tools/src/lonora_tools/memory.py`. Lonora writes its behavioral observations to the owner profile. Reach-me settings still change only on the owner's typed message.
3. **Shared model.** The owner model is shared with the team, and it drives the timing, tone, length and content of reports.
4. **"What I know about you".** One view lets the owner read and correct everything Lonora has learned.

---

## 9. Brokers

1. **MetaApi is the broker link.**
2. **Connecting from chat.** **[Adopted]**
   - The owner says "connect my account".
   - The agent asks in chat for the account number and the server, and uses a broker-destination Secret card for the trading (master) password.
   - The owner enters a MetaApi API token once. It is created once at metaapi.cloud when the owner opens a MetaApi account.
   - After that the owner never visits metaapi.cloud and never copies an account id: Lonora provisions and deploys each account itself through the MetaApi provisioning API.
3. **Managing from chat:** listing, disconnecting, rotating credentials, enabling and disabling connections. Credential rotation for MetaApi goes through provisioning, not through `BrokerSessionRepository.update` (`packages/db/src/lonora_db/broker_sessions.py`).
4. **Proactive health.** Lonora reports a rejected token, an undeployed account or a lost connection, and offers to fix it.
5. **Other venues.** **[Adopted]**
   - MetaApi accounts are traded only through the execution door.
   - Another venue gets a door adapter when one is built.
   - Until then, an agent MAY trade a venue the owner connected by calling its API from the workspace, when the owner asks for it.
   - Lonora reports those orders from the venue's own history, and tells the owner once that the venue is outside the door's guarantees.

---

## 10. Interface: clay and five fixed cards

### 10.1 Clay

1. **One design system.** Lonora has one fixed design system: tokens, typography, colors and components. Agents compose structure and content freely from its component catalog, like clay. Agents never write CSS, colors or fonts.
2. **No fixed types for content.** There are no fixed card types for analysis, reports, questions, suggestions, briefs, comparisons or plans. The agent draws whatever it needs.
3. **GenUI v2 is the default.**
   - It becomes the default in the same change that makes the mobile v2 renderer pass the parity check of 10.1.5.
   - The live-evaluation gate in `packages/agent-runtime/src/lonora_agent/skills/visual_policy.py` is removed.
   - At the end of Phase 2, `LONORA_GENUI_V2` is deleted, and v1 remains only to render stored v1 messages.
4. **Size budgets stay as they are,** including the 560 px resting height (`RESTING_LIMIT` in `packages/agent-runtime/src/lonora_agent/genui_compile.py`).
5. **Parity.** The server contract, the vocabulary taught to the model, the web renderer and the mobile renderer MUST accept the same component set. Mobile MUST render v2 natively; a text fallback on mobile is not acceptable.

### 10.2 Trusted slots

1. **Placement.** An agent MAY place any fixed card inside its own composition, as a trusted slot that references a real server record. The agent chooses only where the slot sits. The server supplies every word, number and button in it.
2. **Protection.** A slot can never be hidden, folded, relabelled or restyled by the agent. It carries a trust frame the agent cannot imitate.
3. **Fallback row.** A fixed card's standalone row appears only when no message embeds that record as a slot. A slot and its row act on the same record; a second tap shows the record's current state.
4. **Removed prompt rule.** The rule "never put a card in the same reply as an approval or owner-action card" (`packages/agent-runtime/resources/prompts/genui_v2.md` line 5) is removed. That line is rewritten to match 10.2 and 10.3.

### 10.3 The five fixed cards

| Card | When | Rules |
|---|---|---|
| **Trade Approval** | A risk-increasing request from an agent in Ask, or the case in 3.1.3 | Bound to the exact request. Shows symbol, side, volume, entry, stop loss, take profit, tolerance, and the agent's reason (labelled as the agent's words). Approve or Reject. See 10.3.1. |
| **Secret** | Any credential | Fields chosen by the agent; destination set by the server (7.2.3). Values go straight to the encrypted store; the agent learns only "saved". |
| **Execution Receipt** | Every operation the broker confirms, in either mode and from any path (tool, CLI, Lonora, the owner's own Lonora orders) | Broker-confirmed facts only. Fills: ticket, action, volume, fill price. Modifications: ticket and new values. Cancels: ticket. Plus the agent's reason (none for the owner's own orders). The agent can never draw "confirmed" itself. |
| **Settle Uncertain Operation** | An operation whose outcome is unknown | Executed / Not executed / Unknown. Recorded in the journal. |
| **Mandate** | Switching an agent between Full and Ask | Shows the agent's current mode, read live, and one button for the other mode. A tap applies the mode the button showed at the moment of the tap. |

The global **Stop** is a permanent control, not a card.

#### 10.3.1 Trade Approval validity **[Adopted]**

1. **Tolerance.**
   - Every request that raises a Trade Approval card carries `tolerance`: a price distance in the symbol's price units, declared in the trade tool or with `--tolerance` in the CLI.
   - A risk-increasing request in Ask without a tolerance is refused with `tolerance_required`.
   - The reference price is the executable side (ask for a buy, bid for a sell) at the moment the card is created.
2. **Drift.** The server watches the quote. The first quote outside reference ± tolerance marks the card `drifted`. A drifted card cannot be approved, and the requesting agent is woken with fixed server text naming the card.
3. **Ending a card.** A card has no time limit. It ends only by Approve, Reject, drift, withdrawal by the agent (when its reason no longer holds), withdrawal by Stop, or withdrawal by a mode change. This replaces the fixed 45-minute lifetime (`APPROVAL_LIFETIME` in `trade_approvals.py`).

#### 10.3.2 Mapping of today's owner-action kinds

| Today's kind | Becomes |
|---|---|
| `connect_credential` | the Secret card |
| `resolve_operation` | Settle Uncertain Operation |
| `resume_trading` | the Stop control's Resume |
| `grant_authority`, `set_account_limits`, `lift_restriction`, the supervision kinds | deleted, together with their features |
| `trust_source` (feed domains, MCP servers, GitHub skill sources) | the owner's typed message in chat, checked by `owner_message_id`; no card |
| `agent_model`, `agent_model_changed` | the owner's typed message assigns the model (12.3) |
| `watch_changed`, `stop_tightened` notices | the agent's own composition |

---

## 11. Proactivity

1. **Morning brief.**
   - It is sent every day, from Lonora.
   - It covers: the account change since the last brief, what each agent did and its result, open positions, pending approvals, upcoming events, and an explicit "nothing else needs you" when that is true.
   - **[Adopted]** The time is learned from the owner's behavior. Until Lonora has seen the owner open the app on at least 3 days, the brief is sent at 07:00 in the owner's time zone. The brief posts every day; 11.5 does not apply to it.
2. **Receipts.** After every operation the broker confirms, an Execution Receipt is posted (10.3).
3. **Weekly report** per agent (5.5.6).
4. **Reaching the owner when the app is closed** is required. **[Adopted]**
   - Each of these sends one mobile push when created:
     - a pending Trade Approval card;
     - a Settle Uncertain Operation card;
     - a Secret card an agent is waiting on;
     - a Mandate card an agent proposed;
     - a broker health problem (9.4).
   - Execution Receipts and reports do not send a push.
   - Push goes through the Expo push service, with credentials the owner configures once in the deployment.
   - The owner MAY enable other channels, for example Telegram.
5. **Silence when there is nothing.** A scheduled or background run with nothing new posts nothing.
6. **Routine output** goes to the agent's own conversation, never into a new chat per routine.
7. **Attention view.** Lonora keeps one unified "needs your attention" view across all agents.
8. **What wakes an agent:** owner messages, broker events, its own watches, routines and timers, and workspace scripts (`lonora wake`).

---

## 12. Model providers

1. **API keys only.** Model access uses API keys only, through the existing adapters and router: Anthropic, OpenAI, DeepSeek, OpenRouter, Z.ai and OpenAI-compatible endpoints. Lonora makes no assumption about the plan behind a key.
2. **Prohibited:**
   - subscription logins or OAuth tokens of any AI platform (Claude Pro/Max/Ultra, ChatGPT, Grok or others);
   - reuse of another vendor's CLI client id;
   - calls to private vendor endpoints;
   - running Claude Code or the Claude Agent SDK as Lonora's engine.

   An agent MAY install and run any command-line tool in its workspace, with API keys the owner provided.
3. **Assignment.** The owner assigns any available model to any agent from chat.

---

## 13. Nothing built stays off

1. **On or completed.** Every feature that is built but switched off is switched on or completed. That includes features disabled by default, unwired, unrouted, unregistered, unrendered, or never loaded for the model. A survey of the repository found these kinds:
   - features off in configuration;
   - server capabilities with no screen in the app;
   - GenUI components and actions the server accepts but the clients do not render;
   - mobile screens missing where web and the server have them;
   - half-built paths;
   - prompts, playbooks and references that never reach the model.

   Each is checked and switched on or completed in the phase that touches its area.
2. **Deletion.** Code is deleted only when this mandate removes it (14.2), or when a newer implementation in the repository has already replaced it.
3. **GenUI v2** is the first case (10.1.3).
4. **Not features.** Owner controls (Stop, the Mandate card) are not features, and this rule does not "switch them on".

---

## 14. Removal plan and what must survive it

### 14.1 Order of work

1. **Order.** Add the new path first, move what must survive, then delete the old path. A deletion never lands before its replacement works.
2. **Core regression tests.** These MUST pass after every step:
   - `tests/check_trading.py`
   - `tests/check_execution_recovery.py`
   - `tests/check_broker_recovery.py`
   - `tests/check_account_recovery.py`
   - `tests/check_broker_orders.py`
   - `tests/test_broker_effect_verification.py`
   - `tests/test_execution_records.py`
   - `tests/test_preflight_identity.py`
   - `tests/test_metaapi_reconciliation_history.py`
   - `tests/test_tool_execution_core.py`
   - `tests/test_financial_admission.py`
3. **Assertions.** An assertion about a removed feature (grants, limits, restrictions, goals, supervision) is removed in the same change that removes the feature. No assertion about 6.1–6.9 is removed or weakened.
4. **Clients and dispatchers.** The web and mobile clients, and the gateway dispatchers of removed features, are updated in the same change as their API. For example:
   - web: `AgentPermissions.tsx`, `SupervisionSettings.tsx`, `MandateSheet.tsx`, `LimitsSheet.tsx`, `components/goals`;
   - mobile: `account-authority-settings.tsx`, `supervision-settings.tsx`, `bot-settings.tsx`;
   - gateway: `dispatch_activation_reviews`, `owner_cards.py`.

### 14.2 Removed

1. **Grants and delegation:**
   - `AccountAuthority` grants and passkey signing for trading;
   - `lonora_contracts/account_authority.py`;
   - `GrantDelegation` and `grant_authority` in `lonora_contracts/owner_actions.py`;
   - `full_delegation_available` in `lonora_db/owner_actions.py`;
   - `lonora_core/delegation_words.py`;
   - `lonora_db/account_authority.py` and `lonora_auth/account_authority.py`, after 14.3.2 and 14.3.3;
   - `lonora_db/activation_review.py`;
   - the dead `lonora_trading/delegation.py`.

   The `AuthorityAction` trade-action literal moves to `lonora_contracts/trading.py` first.
2. **Execution caps and money limits:**
   - From `ExecutionPolicy` (`lonora_contracts/execution_quality.py`, enforced in `lonora_trading/exposure.py`), these fields go: `max_positions`, `max_pending_orders`, `max_symbol_direction_volume`, `max_spread`, `max_entry_drift_stop_fraction`, and `risk`.
   - The money limits go: `lonora_trading/risk_limits.py`, `lonora_contracts/risk_limits.py`, `routes/execution_policy.py`, and the `set_account_limits` card.
   - `quote_max_age_seconds`, `account_max_age_seconds`, and the health checks in `evaluate_execution` stay.
3. **Restrictions:**
   - `lonora_trading/restrictions.py`, `lonora_tools/restrictions.py` (after 14.3.5), `lonora_db/trading_restrictions.py`, `lonora_contracts/trading_restrictions.py`, `routes/trading_restrictions.py`;
   - the tools `trade_restriction_create` and `trade_restriction_list`;
   - the `lift_restriction` card.

   `AdmissionBlocked` moves to `admission.py` first.
4. **Trading goals:**
   - `lonora_trading/goals.py`, `goals_market.py`, `goals_targets.py`, `goal_broker.py`;
   - `lonora_db/trading_goals.py`, `lonora_db/goal_scope.py`;
   - `lonora_contracts/trading_goal.py`;
   - `lonora_tools/trading_goal.py`, `routes/trading_goals.py`;
   - agent-runtime `context/goals.py`;
   - the web `components/goals` and `lib/goal-status.ts`;
   - the `trading-goal` skill (`resources/skills/trading-goal`) and the `autonomous-trading-goal` playbook (`resources/playbooks/autonomous-trading-goal`);
   - the `policy:goals` prompt chapter.

   The non-trading agent goals (`lonora_contracts/agent_goals.py`, `lonora_db/agent_goals.py`, `routes/agent_goals.py`) are kept.
5. **The entry-thesis gate** on opportunities inside the execution door. Opportunities themselves stay as agent memory.
6. **Supervision:** supervision grants, the supervisor template, delegated and child agent roles, agent templates that limit capability, and the cap on the number of agents.
7. **Owner-action card kinds** per 10.3.2.
8. **Prompt governance:** the governance chapters of the system prompt, and the permission frame in `context/permissions.py` (replaced per 5.8.7).
9. **Old vision documents:** `VISION.md` and `MANDATE_CORRECTIONS.md` are replaced by this mandate.

### 14.3 Must be moved or kept before the code around it is deleted

1. **Stale-target checks.** The two checks are merged into one door check (6.6).
2. **`account_authority.py` contents.** `management_target`, `provisional_voice` (needed only as 6.10 allows), `authority_snapshot` and `lonora_opened` move out of `lonora_trading/account_authority.py` before that file is deleted. `lonora_opened` becomes the basis of position ownership (3.3.4).
3. **The continuous account-management task.**
   - `stop_management_task` and the `account_management_id` recovery path (`is_continuous_task` in `db/tasks.py`, and `task_recovery.py`) are kept.
   - The task is re-keyed per agent.
   - It is started on the switch to Full and stopped on the switch to Ask, on pause, or on delete (4.5).
4. **Run integrity checks** per 6.9.
5. **Anti-injection helpers.**
   - `owner_message_id`, `mark_external_content`, `external_content_seen`, `external_content_key` and `OWNER_TRIGGERS` move together to a surviving module (for example `lonora_tools/provenance.py`).
   - `owner_message_id` no longer gates Lonora's lead actions (3.1.2, 3.1.3) or its behavioral owner-profile writes (8.2).
   - It still gates requests on tickets the agent does not own (3.3.4), reach-me settings, trusting a source, and model assignment.
6. **The owner pause.**
   - These stay: `owner_takes_over`, `refuse_held`, `owner_resumes`, `live_hold`, `work_paused`, `release_hold`, `owner_holds_for`, and the `SupervisionHoldRow` table (`packages/db/src/lonora_db/supervision.py`). They move to a surviving module before supervision grants are deleted.
   - Callers include `db/tasks.py`, `db/market_watches.py`, `db/agents.py`, `db/agent_creation.py` and `automation/service.py`.
7. **Exits while paused.** `money_standing` is rewritten without the permission ladder. Pausing an agent that holds positions never stops its risk-reducing requests (4.7).
8. **Card kinds.** Each owner-action kind is mapped per 10.3.2 before it is removed. Trust for news feeds (`packages/tools/src/lonora_tools/feeds.py`, `lonora_db/trusted_sources.py`), MCP servers (`tools/mcp.py`) and GitHub skills (`skills/lifecycle.py`, `skills/access.py`) keeps working.
9. **Stored payloads.**
   - Every stored payload validated by a contract with `extra="forbid"` is migrated before a field is added to or removed from that contract. That covers:
     - `ExecutionPolicy` and limits;
     - the `TradeRequest` inside trading-journal rows and Trade Approval rows;
     - `PermissionRecord`;
     - `MarketWatch` and `Routine` (`goal_id` / `step_id`);
     - owner-action rows of removed kinds;
     - agent rows with role `delegated` or template `supervisor`.
   - For every unresolved journal row (`reserved`, `submitted`, `ambiguous`), `trade_fingerprint` and the operation-id derivation MUST give the same value before and after the change.
   - The agent's reason, tolerance and judgment label are stored beside the request, and are excluded from the fingerprint and from the operation id. Two sends that differ only in reason are the same operation.
   - Test: a journal row left `ambiguous` before the migration reconciles after it without a resend or an idempotency conflict.
10. **Stop.** `TradingControl.emergency_stop` and `require_trading` stay (4.8).
11. **Connections and secrets.** The connection enable/disable path, and `DELETE /secrets/{secret_id}` (`routes/agent_secrets.py`, the only route that deletes a stored secret), stay.
12. **Data files and tests.**
    - The literal data-file paths in `pyproject.toml` and `packages/agent-runtime/pyproject.toml` are updated in the same change that removes a skill, playbook or prompt chapter.
    - So are the tests that list them (`tests/test_skill_runtime.py`, `tests/test_capability_exposure.py`).
    - So is the manifest (5.8.6).
13. **Approval-flow behavior.** The behavior documented in `docs/account-authority.md` (the exact-request match, and reusing the card already raised for the same request in one run) moves into a surviving document before that file is deleted.
14. **Goal decoupling.**
    - Watches, routines, runs and context builders are decoupled from trading goals before goal code is deleted: `db/market_watches.py`, `db/routines.py`, `lonora_market/watchers.py`, `db/runs.py` (`bind_goal_run`), `db/obligations.py` (`settle_orphaned_goal`), agent-runtime `context/builder.py` and `collaboration/outcome_return.py`, `gateway/service.py` (`recover_goals`, removed in the same change as goals), and `tools/supervision.py`.
    - The `gateway/service.py` goals step is removed only in the same change that removes goals.
15. **Lonora's lead powers.**
    - `personal_agent_id` moves out of `db/supervision.py` to a surviving module.
    - Lonora's read and control access to every team agent is rebuilt as a built-in role check. This covers memory sessions (`packages/memory/src/lonora_memory/sessions.py`), tool exposure (`tool_exposure.py`), the agent directory, and `collaboration/subagents.py`.
    - `grant_default` and `seed_personal_grants` are removed from agent creation in the same change.
16. **Delete safety.** `prepare_delete` (`packages/db/src/lonora_db/obligations.py`) and its refusal to delete an agent, conversation or connection while an operation has no confirmed outcome stay. Its grant, goal and card steps are removed in the same change as those features.
17. **Status line.** `lonora_db/trading_readiness.py` is rewritten without delegation, restrictions and money limits, so that the agent status line (section 17) survives.
18. **Migration of existing data** **[Adopted]**, done in one step before the old permission code is deleted:
    1. Every agent's mode becomes Ask, whatever its stored level or grants. No agent becomes Full without the owner's tap.
    2. For each agent that had an active, unexpired grant, Lonora shows that agent's Mandate card once, with one line naming the old grant.
    3. Active grants are revoked, and their management tasks are stopped.
    4. Delegated, child and supervisor agents become ordinary team agents: the parent link and role are removed, and their bound account and symbol are written into their method as instructions.
    5. Pending Trade Approval rows keep their stored expiry; new rows have none.
    6. Active restrictions, goals and supervisor-held pauses end. Owner-held pauses stay.
    7. Positions are attributed from the journal per 3.3.4.
    8. A stored control with `emergency_stop=true` or `enabled=false` becomes stopped. An install with no stored control becomes not stopped.

---

## 15. Phases

| Phase | Scope | Done when |
|---|---|---|
| 1 | Adopt this mandate | This mandate is committed as `VISION.md`. Every other document that contradicts it starts with the line "Superseded by VISION.md". The prompt and constitution keep no rule that the code no longer enforces. |
| 2 | GenUI v2 as the default, with the mobile v2 renderer and full parity | v2 renders natively on web and mobile with the same component set; the 560 px budget is unchanged; `LONORA_GENUI_V2` is deleted |
| 3 | Trading authority, then removal per section 14: the Full/Ask switch, the Mandate card, Trade Approval with reason and tolerance, Execution Receipt, continuous work in Full, Stop | Section 4 behaves as written; the core tests (14.1) pass; no grant, limit, restriction or goal code remains |
| 4 | Workspace, secrets and the `lonora` CLI | Section 7 behaves as written; an order sent from the CLI is journaled and verified like a tool order |
| 5 | The agent's mind: the trader prompt, judgment, the full picture on wake, the learning loop, the weekly report | Section 5 behaves as written |
| 6 | Lonora as lead, the flat team, the owner model | Sections 3 and 8 behave as written |
| 7 | Proactivity: the morning brief, push, silence, the unified attention view, routine output in the agent's conversation | Section 11 behaves as written |
| 8 | Broker connection from chat, with MetaApi provisioning | Section 9 behaves as written |

Dormant features (section 13) are switched on or completed in the phase that touches their area.

---

## 16. Acceptance scenario

**Setup.** Run on a MetaApi demo account. The test harness induces the connection drop and the price drift, and compresses time where a step needs it. A step that depends on a model's choice passes when the harness presents the situation and the agent acts within its authority, without asking, and explains in one line. Which choice it makes is not asserted.

1. **Connecting.** The owner says "I have an MT5 account at my broker, trade it". Lonora asks for the account number and server, shows the Secret card for the password, provisions the account through MetaApi, and reports the balance.
2. **Creating agents.** The owner says "make a gold agent with full authority, a news agent, and a euro agent that asks me first". Lonora creates them. The gold agent's Mandate card is shown, and the owner taps it. The euro agent starts in Ask.
3. **Strategy.** The owner uploads a strategy PDF. The gold agent turns it into its method.
4. **Overnight:**
   - The news agent tells the others about a central-bank speech.
   - The gold agent opens a position, and the broker confirms it with an Execution Receipt. The agent later moves its stop to break-even and takes partial profit.
   - A connection drop during a close is reconciled without a resend.
   - The euro agent's request waits as a Trade Approval card, and a push reaches the owner's phone. When price drifts outside the tolerance, the agent re-evaluates and asks again.
5. **Morning.** Lonora's brief shows the account change, each agent's actions and results, the pending approval with its reason, and the day's events.
6. **Stop.** The owner presses Stop. No new risk-increasing order is sent through Lonora. The gold agent tightens its stop, and the pending approval is withdrawn. The owner presses Resume.
7. **After a week.**
   - Each agent posts its report with what it learned and what it changed.
   - When the harness presents a team problem, Lonora creates, pauses or deletes an agent without asking, and explains why in one line.

---

## 17. Carried over unchanged

- The model decides. There is no rule engine and no fixed strategy pipeline.
- There is no backtesting or simulation gate on strategies.
- Arabic and right-to-left come first. Agents reply in the owner's language.
- Normal views show no raw tool names, ids, JSON or internal wrappers.
- Each agent has one plain status line, built from what is really happening.
- Runs are durable, with checkpoints, recovery after restarts, and model fallback.
- Lonora is self-hosted for a single owner. Multi-user hosting is out of scope.

---

## Owner amendments

### Amendment 1 (2026-11-12): no Stop control

The owner decided that Lonora has no Stop control at all («لا داعي لزر إيقاف أبداً، بدون زر إيقاف»). Every clause about Stop is void:

- P2 (the Stop item) and P5 (the Stop control);
- 4.0 (Stop in its list), 4.5.2 ("Stop does not"), and 4.8 entirely;
- 5.4 (whether Stop is in force) and 5.8.7 (the Stop state; the mode stays);
- 6.7 (the ordering against Stop; the ordering against mode changes stays);
- 10.3 ("The global Stop is a permanent control"), 10.3.1.3 (withdrawal by Stop) and 10.3.2 (`resume_trading` is deleted with its feature);
- 13.4 (Stop), 14.3.10 and 14.3.18.8;
- step 6 of section 16.

`TradingControl` (`enabled` and `emergency_stop`), `require_trading`, the "trading not started" state, the `resume_trading` card and every Stop control on web and mobile are removed in phase 3, with their text, clients and assertions (14.1.3, 14.1.4). The owner's controls are the Mandate card (4.1, 4.2), the pause of an agent or a piece of work (4.6, 4.7) and the broker connection (9.3).
