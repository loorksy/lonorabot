Superseded by VISION.md

# Creating and steering agents from chat

Wave 1.5 slice W15-4 (corrections 17, 23 and 24). "Create a gold agent", "create a
news agent that reports to the gold agent" and "stop watching gold" all work inside
the conversation, with no form. Nothing here creates money authority: a grant is
only ever signed by the owner.

## `agent_create`

One tool (toolset `collaboration`, long-tail, not financial, replay-safe) backed by the
same creation function as `POST /api/agents` (`lonora_db.agents.create_agent`), through
the creation service `lonora_db.agent_creation.create_root_agent` and
`lonora_agent.collaboration.agent_create.create_from_spec`.

| Input | Meaning |
| --- | --- |
| `template` | `trading`, `general`, `research` or `supervisor` |
| `name` | Display name; a name another agent already has gets the first free number ("Gold agent 2") |
| `responsibility` | What the owner asked it to do. Stored as its instructions; a short form is its directory description. Text that states authority ("trade without approval") is refused (`agent_responsibility_authority_claim`), like operating notes. Both creation cards show it word for word ("Its task: …"), so the owner sees the standing instruction a tap keeps. |
| `market` | Trading template only, and required there: the focus pair as the broker names it |
| `account_id` | Only when the owner chose among several accounts |
| `model` | Optional, one of the owner's configured models (the router's conversation routes); otherwise the result lists them (`agent_model_not_allowed`) |
| `report_to` | Up to five existing agents it reports important findings to |
| `supervises` | Up to ten existing agents it supervises, granted with the creation's source (`docs/supervision.md`) |

Every new agent is an independent root: `parent_id` null, `scope_mode` flexible, role
`specialist` with a focus pair and `general` without one (the `ln_agent_flexible_root`
and `ln_agent_general_scope` constraints hold). The ladder is written explicitly, never
left to a default: the trading template starts at *Ask me* (`supervised`, every trade is
an approval card) and every other template at *No trading* (`analysis`). No
`AccountAuthority` row is ever created; *On its own* still needs the owner's signed
grant.

### The focus pair

The market is looked up in the broker catalog of the owner's enabled accounts: the exact
name, else a single case-only match, else names that only add a broker suffix
(`XAUUSD.r`, `XAUUSDm`, `XAUUSD.pro`; `XAUUSDT` is another instrument and does not
match). The only connected account is used without asking. When two accounts or two
symbols match, nothing is created: the result lists the candidates
(`agent_market_ambiguous`) and the agent asks the owner one focused question with
`wait_for_input`, then calls again with the chosen `account_id` and exact market. The
connection version is recorded and re-checked when the agent is created.

### Owner message or card

- **The run answers the owner's message** (a `user` or `group` run, the same rule as
  `trade_restriction_create`): the agent is created at once, and that message is
  recorded as its source. The owner's message stands for the owner's intent only while
  the Run has read nothing someone else wrote (`restrictions.owner_message_id`): once a
  tool returned third-party or other-agent content into the Run (a web page, search
  excerpt, feed, MCP result, peer's memory, stored file or another model; the list the
  context engine labels untrusted, recorded per Run by the registry) or another agent's
  message reached it, it is treated like a wake and raises the card instead. The same
  rule governs every tool that acts on the owner's word: supervision, `agent_control`,
  the owner profile and reach-me, model switches, narrowing other agents and lifting a
  hold. Supervision over Lonora (`supervises` naming the Personal Agent) is always a card.
- **The responsibility it writes stays its writing.** The new agent's instructions are
  the responsibility the creating agent wrote; while they still match it
  (`instructions_sha256` in the origin record) the context shows them as a labelled
  `responsibility` section (`agent_authored`), never in the system role. The owner
  editing them in the agent's settings makes them the owner's. The `report_to` notes
  quote the agent names as data, and agent names and responsibilities lose Unicode
  direction controls at the contract layer (`strip_bidi_controls`; `isolate()` drops
  them too), so a chosen name cannot reorder a card or pill line.
- **Otherwise** (a wake, a routine, a peer request): nothing is created. The tool raises
  a `create_agent` owner action card in the conversation ("Create an agent?", Create /
  Not now). The owner's tap runs the same creation in the owner's session
  (`created_via = owner_card`); a repeated proposal returns the card already shown.
- **The owner answers a card in chat** ("yes, create it"): that run answers an owner
  message, so it creates the agent, and every pending creation card for the same
  template and name closes (`agent_already_created`, "This agent was already created").
  The same happens to another agent's card when one card is tapped. A card whose agent
  exists by then (same template and name) is settled with that reason instead of
  creating a second one, and a new proposal for it returns `agent_already_exists` with
  the agent.

### Limits and duplicates

- At most `MAXIMUM_ACTIVE_AGENTS` (20) active persistent agents per owner (not paused;
  temporary helpers do not count) and at most `MAXIMUM_CREATIONS_PER_RUN` (3) creations
  or creation cards per run (`agent_limit_reached`, `agent_create_run_limit`). Both are
  re-checked under the owner's creation lock, and the cap again when a card is tapped.
  The owner's own «وكيل جديد» form (`POST /api/agents/create`, `created_via` `owner_ui`)
  is not capped, as the owner's form never was.
- A crash-replayed call returns the agent it created (its id is the call's resource id).
  A retry under a new call id for the same owner message, template and name returns the
  same agent (an effect receipt), also after a worker restart that lost the transcript.
  Repeats are answered before the limits are counted. After the owner's Undo removed
  it, the same message never creates it again (`agent_create_undone`).
- Locks are taken in the order the owner's card decision takes them: owner action cards,
  then creation, then the conversation, then the run fence.

### Provenance and peer links

Each created agent has an origin record (`ln_settings`, key `agent-origin:<hash>`; no
migration): template, `created_via` (`owner_ui`, `owner_message`, `owner_card`), the
creating agent, the owner message, run and card, and `report_to`. The same fields are the
`agent.created` event payload; the owner's own form (`POST /api/agents`) now emits it
too, with `owner_ui`. `report_to` is the peer link: `list_agents` shows each agent's
`template` and `reports_to`.

Operating notes (`OPERATING.md`, fixed server text, attributed to the owner's request
and revertible like any memory change) tell the new agent its template's role and whom
it reports to ("Report important findings to Gold agent."), and tell each agent it
reports to who reports to it ("News agent reports important findings to you."). The
notes name agents, never ids or tool names: `list_agents` holds the link. A note that
would not fit, or that the memory guard refuses, is skipped; the link itself stays. The
origin record keeps the exact lines it added (`link_notes`).

When the agent is deleted (Undo or the owner's delete,
`lonora_agent.collaboration.agent_create.delete_created_agent`), the lines its creation
wrote into the agents it reports to are removed, and agents that reported to it lose
that link and their "Report … to it" line. An agent locked by another change at that
moment is skipped rather than waited on; its line stays visible and revertible.

After creating, the creating agent hands the new agent its first task with `peer_send`
and confirms in one line what was created and what is still missing. When the owner
created it from a card, the tap queues one run (trigger `agent_created`, run id derived
from the card) for the proposing agent in the card's conversation, with fixed server
text naming only the new agent's id, so it sends that first task. Undo before that run
starts cancels it. It is not an owner turn: an `agent_create` in it raises a card.

## The result card and Undo

Every creation raises one `agent_created` card in the creating conversation (source
`system`, one per agent, seven days): the agent's name and template, its focus pair (the
account named when the owner has several), its trading level, whom it reports to, its
stored task (isolated and labelled, "Its task: …" / «مهمته: …»), and what Undo does now.
The money sentence follows the live level: "No money authority: every trade waits for
your tap" at Ask me, "It does not trade" at No trading, and "It trades on its own only
inside the grant you signed" once the owner signed a grant while the card was pending.

| Card | Buttons | Undo does |
| --- | --- | --- |
| Agent created | Undo / Keep it | remove the agent when it has done nothing yet (no run, watch, routine, task, grant, approval or child); otherwise pause it, keeping its work |
| Create an agent? | Create agent / Not now | (creates it, then raises the result card) |

Undo is the owner's delete (`lonora_db.agent_creation.delete_agent`, the same function
as `DELETE /api/agents/{id}`: refused while a trade is uncertain, grants and approvals
settled first, financial records kept) or a pause. Deleting an agent anywhere settles its
pending Undo card, except one the owner is tapping at that moment: the delete never
waits for that tap (which takes the agent's lock after the card's), and the tap then
finds the agent gone ("This agent was already removed"). The confirmation line in the conversation is fixed text
(`owner_action_create_agent`, `owner_action_undo_deleted`, `owner_action_undo_paused`).

## Steering watches and routines

- `watch_cancel`, `watch_pause`, `watch_resume` and `watch_update` (toolset `market`,
  long-tail, replay-safe) act only on the calling agent's own watches; another agent's
  watch reads as not found (`market_watches_not_found`).
- Cancel and pause keep the record (`enabled` false, state code `watch_cancelled` or
  `watch_paused`), so `watch_resume` undoes a cancel. A watch past its expiry resumes only
  after `watch_update` moves the expiry; a later expiry revives an expired watch.
  `watch_update` changes only the expiry and the level; the condition, market and prompt
  stay. Repeating an action changes nothing.
- A watch that stops for any reason (cancel, pause, replacement, quarantine, the end of
  its Task) drops `evaluation_status` and `next_check` from its state, so nothing stored
  reads as a live evaluation. A stopped watch is not polled, and a Task waiting on it is
  not woken by a trigger from before the stop.
- Cancelling or completing a Task (from the Task controls, `task_control`, «تحديد
  كمكتملة», or revoking the grant behind an account-management Task) stops the watches
  that Task's Runs created (`state.task_id`): `enabled` false, state code `task_terminal`,
  with a `market_watches.updated` event. The owner's request counts at once, also while
  a worker still holds the Run. A watch that was already paused or cancelled is settled
  too, and resuming a watch of an ended Task is refused (`watch_task_ended`): it could
  only poll and stop itself when it fired. A paused or failed Task keeps its watches;
  revoking the grant ends its management Task even when that Task had failed. A stopped
  watch is also not evidence for an opportunity thesis (`thesis_watch_unconfirmed`).
- The owner cancels, pauses or resumes any watch with `POST /api/watches/{id}/control`
  (`{"action": "cancel" | "pause" | "resume"}`), from the status line's watch list.
- `routine_toggle` pauses or resumes the agent's own routines, and the routines of an
  agent it supervises under the supervision hold rules (`docs/supervision.md`).

## The status line

The live state (`GET /api/agents/{id}/state`) counts only watches that are watching
now (enabled, not expired, before their expiry) and lists up to six of them
(`watches`: kind, market, condition, level, indicator, metric, expiry; never the prompt).
Web and Mobile render one shared line (`packages/core/src/agent-status.ts`): while the
agent waits on its watches (also when a Task's work waits on one of its own watches; that
watch is named first), "Monitoring XAUUSD until 17:00 · 2 more" /
«يراقب XAUUSD حتى 17:00 · 2 أخرى», otherwise the plain state (Working, Waiting for you,
Paused). Opening it shows each watch's condition and expiry with Cancel. Between runs
the header avatar follows the same phase: watching while monitoring, asleep while
paused, a warning while it needs the owner. The Market page's watch list shows each
watch's agent, condition and expiry. A focus pair is labelled permanent only for legacy
fixed-market agents.

## Not in this slice

- Supervision grants and `supervises` are W15-6 (`docs/supervision.md`): a
  supervisor-template agent reads other agents' private work only through the visible
  supervision grant.
- The ladder defaults for existing agents and the grant card (W15-3): new agents get
  their level written explicitly here; existing agents are unchanged.

## Verification

- `tests/check_agent_create.py` (PostgreSQL, simulation broker, scripted provider): an
  owner message creates a flexible root trading agent at Ask me with no grant; replays and
  retries add nothing; the result card shows server facts; a research agent's link and
  notes; the per-run and per-owner limits (a repeat still answers); a creation card
  without an owner message and its single creation, its task on the card and the
  proposer's first-task run; a yes in chat to a pending card creates one agent and closes
  the card (also another agent's card); Undo removes the creation's notes and links; the
  owner's delete never deadlocks with an Undo tap; Undo removes or pauses; two matching
  accounts ask one question; watches steered only by their agent and by the owner's route;
  `routine_toggle` limited to own routines; a scripted Arabic turn through the normal
  runtime creates one news agent, one supervisor and one link, and a restarted worker
  replaying the turn under new call ids adds nothing.
- `tests/test_agent_create.py`: catalog lookup, templates and levels, input rules, the
  responsibility guard, the receipt key, tool metadata and scopes, card lifetimes and
  fixed confirmations, active watches.
- `tests/web/agent-create.test.ts` (tsx): both cards in English and Arabic, Undo's two
  outcomes, the money sentence by live level (a signed grant included), the task line,
  the already-created line, the status line, watch conditions, the avatar, Web/Mobile
  parity.
- `tests/check_task_environment_wait.py`: a Task waiting on its own watch reads as
  monitoring (`market_watch`), a timer or broker wait does not.
