Superseded by VISION.md

# Creating and steering agents from chat

Mandate 3.1.2, 3.2.2 and 3.3: Lonora creates agents on its own judgment, without asking
first, and tells the owner in one line what it created and why. The team is flat: no
template, no hierarchy, no cap, no creation card. "Stop watching gold" works inside the
conversation too.

## `agent_create`

One tool (toolset `collaboration`, long-tail, not financial, replay-safe), backed by the
creation service `lonora_db.agent_creation.create_root_agent` and
`lonora_agent.collaboration.agent_create.create_from_spec`. Only Lonora (role
`personal`, `lonora_db.lead`) may call it. A team agent's call is refused
(`agent_create_lead_only`) with the way to ask Lonora: `peer_send`, which is also how a
team agent passes on the owner's request for an agent.

| Input | Meaning |
| --- | --- |
| `name` | Display name; a name another agent already has gets the first free number ("Gold agent 2") |
| `responsibility` | Its responsibilities and instructions. Stored as its instructions; a short form is its directory description. Text that states authority ("trade without approval") is refused (`agent_responsibility_authority_claim`), like operating notes. |
| `market` | An instrument to assign, as the broker names it |
| `account_id` | An account to assign, or the one the owner chose among several |
| `mode` | The mode the owner named (`full` or `ask`), or `ask` to create it in Ask |

Every new agent is a flat team agent: `parent_id` null, `scope_mode` flexible, role
`general`, `template` null, no account or symbol binding. It uses Lonora's current model
(a copy of Lonora's assignment, attributed to Lonora) until the owner assigns another.
No grant and no `AccountAuthority` row is ever created.

### The assigned market is a method instruction

The market is looked up in the broker catalog of the owner's enabled accounts: the exact
name, else a single case-only match, else names that only add a broker suffix
(`XAUUSD.r`, `XAUUSDm`, `XAUUSD.pro`; `XAUUSDT` is another instrument and does not
match). The only connected account is used without asking. When two accounts or two
symbols match, nothing is created: the result lists the candidates
(`agent_market_ambiguous`) and Lonora asks the owner one focused question with
`wait_for_input`, then calls again with the chosen `account_id` and exact market. The
connection version is recorded and re-checked when the agent is created.

What was assigned is written into the new agent's method (`OPERATING.md`) as fixed server
text around the broker's names: `Lonora assigned you "XAUUSD.r" on the account "…" to
trade.` The account is named by its verified broker label, else by its connection id.
The execution door never binds the agent to it (3.1.2).

### The mode (4.3)

- **In a turn the owner typed** (the run answers the owner's typed message,
  `owner_words.owner_typed_message`, read whatever else the run read): it starts in Ask,
  also when Lonora creates it on its own judgment in that turn (a conservative reading
  of 4.3.3: text the run read can only ever make it Ask). When the owner asked for full
  authority (`mode: full`), its Mandate card is shown in the conversation; only the
  owner's tap sets Full.
- **On a wake or a routine** (no owner turn): it copies Lonora's mode at that moment,
  unless Lonora creates it in Ask (`mode: ask`). An agent created in Full starts its continuous account-management task
  at once (`lonora_db.management_task.ensure_management_task`, 4.5.1). Later changes to
  Lonora's mode never change the new agent's.
- **The responsibility Lonora writes stays its writing.** While the new agent's
  instructions still match it (`instructions_sha256` in the origin record), the context
  shows them as a labelled `responsibility` section (`agent_authored`), never in the
  system role. The owner editing them in the agent's settings makes them the owner's.
  Agent names and responsibilities lose Unicode direction controls at the contract layer
  (`strip_bidi_controls`).

### Limits and duplicates

- There is no limit on the number of agents (mandate 3.3.2). The one rate guard against
  a runaway creation loop is at most `MAXIMUM_CREATIONS_PER_RUN` (3) creations per minute
  within one run (`agent_create_run_limit`, `CREATION_WINDOW`), checked under the owner's
  creation lock; it never counts the owner's agents.
- A crash-replayed call returns the agent it created (its id is the call's resource id).
  A retry under a new call id for the same owner message and name returns the same agent
  (an effect receipt), also after a worker restart that lost the transcript. After the
  owner had it deleted, the same message never creates it again (`agent_create_undone`).
- Locks are taken in the order the owner's card decision takes them: owner action cards,
  then creation, then the new agent's authority lock, then the conversation, then the
  run fence.

### Provenance

Each created agent has an origin record (`ln_settings`, key `agent-origin:<hash>`):
`created_via` (`owner_message` or `lead`), the creating agent, the owner message and run,
and the mode it started in. The same fields are the `agent.created` event payload; the
owner's own `POST /api/agents` emits it too, with `owner_ui`. Agents created before the
flat team may carry `report_to` links and their notes; deleting such an agent removes
them (`lonora_agent.collaboration.agent_create.delete_created_agent`).

After creating, Lonora hands the new agent its first task with `peer_send` and tells the
owner in one line what it created and why. There is no creation or Undo card (only the
five fixed cards of 10.3 exist): undoing a creation is "delete it" in chat.

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

## Verification

- `tests/check_agent_create.py` (PostgreSQL, simulation broker, scripted provider): the
  owner's request for full authority creates a flat agent in Ask with its Mandate card,
  its market in its method and Lonora's model; replays and retries add nothing; on its
  own judgment Lonora's agents copy its mode (Full starts the continuous task) or start in
  Ask; three creations per run; a team agent is refused and told to ask Lonora; two
  matching accounts ask one question; 25 active agents and one more; watches steered only
  by their agent and by the owner's route; `routine_toggle` limited to own routines; a
  scripted Arabic turn through the normal runtime creates one agent, once across a worker
  restart; no grant and no creation card.
- `tests/test_agent_create.py`: catalog lookup, the flat input contract, the method note,
  the responsibility guard, the receipt key, tool metadata and scopes, no creation card
  kind, active watches.
- `tests/web/agent-create.test.ts` (tsx): the status line, watch conditions, the avatar,
  Web/Mobile parity.
- `tests/check_task_environment_wait.py`: a Task waiting on its own watch reads as
  monitoring (`market_watch`), a timer or broker wait does not.
