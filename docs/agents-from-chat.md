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
| `responsibility` | What the owner asked it to do. Stored as its instructions; a short form is its directory description. Text that states authority ("trade without approval") is refused (`agent_responsibility_authority_claim`), like operating notes. |
| `market` | Trading template only, and required there: the focus pair as the broker names it |
| `account_id` | Only when the owner chose among several accounts |
| `model` | Optional, one of the owner's configured models (the router's conversation routes); otherwise the result lists them (`agent_model_not_allowed`) |
| `report_to` | Up to five existing agents it reports important findings to |

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
  recorded as its source.
- **Otherwise** (a wake, a routine, a peer request): nothing is created. The tool raises
  a `create_agent` owner action card in the conversation ("Create an agent?", Create /
  Not now). The owner's tap runs the same creation in the owner's session
  (`created_via = owner_card`); a repeated proposal returns the card already shown.

### Limits and duplicates

- At most `MAXIMUM_ACTIVE_AGENTS` (20) active persistent agents per owner (not paused;
  temporary helpers do not count) and at most `MAXIMUM_CREATIONS_PER_RUN` (3) creations
  or creation cards per run (`agent_limit_reached`, `agent_create_run_limit`). Both are
  re-checked under the owner's creation lock, and the cap again when a card is tapped.
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
it reports to ("Report important findings to Gold agent (agent id …) with
peer_send."), and tell each agent it reports to who reports to it. A note that would not
fit, or that the memory guard refuses, is skipped; the link itself stays.

After creating, the creating agent hands the new agent its first task with `peer_send`
and confirms in one line what was created and what is still missing.

## The result card and Undo

Every creation raises one `agent_created` card in the creating conversation (source
`system`, one per agent, seven days): the agent's name and template, its focus pair (the
account named when the owner has several), its trading level, whom it reports to, and
what Undo does now. The responsibility text, which a model wrote, is never shown.

| Card | Buttons | Undo does |
| --- | --- | --- |
| Agent created | Undo / Keep it | remove the agent when it has done nothing yet (no run, watch, routine, task, grant, approval or child); otherwise pause it, keeping its work |
| Create an agent? | Create agent / Not now | (creates it, then raises the result card) |

Undo is the owner's delete (`lonora_db.agent_creation.delete_agent`, the same function
as `DELETE /api/agents/{id}`: refused while a trade is uncertain, grants and approvals
settled first, financial records kept) or a pause. Deleting an agent anywhere settles its
pending Undo card. The confirmation line in the conversation is fixed text
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
- The owner cancels, pauses or resumes any watch with `POST /api/watches/{id}/control`
  (`{"action": "cancel" | "pause" | "resume"}`), from the status line's watch list.
- `routine_toggle` pauses or resumes only the agent's own routines (supervised agents'
  routines come with W15-6).

## The status line

The live state (`GET /api/agents/{id}/state`) counts only watches that are watching
now (enabled, not expired, before their expiry) and lists up to six of them
(`watches`: kind, market, condition, level, indicator, metric, expiry; never the prompt).
Web and Mobile render one shared line (`packages/core/src/agent-status.ts`): while the
agent waits on its watches, "Monitoring XAUUSD until 17:00 · 2 more" /
«يراقب XAUUSD حتى 17:00 · 2 أخرى», otherwise the plain state (Working, Waiting for you,
Paused). Opening it shows each watch's condition and expiry with Cancel. Between runs
the header avatar follows the same phase: watching while monitoring, asleep while
paused, a warning while it needs the owner. The Market page's watch list shows each
watch's agent, condition and expiry. A focus pair is labelled permanent only for legacy
fixed-market agents.

## Not in this slice

- Supervision grants and `supervises` (W15-6): a supervisor-template agent is created
  with *No trading* and its role in its notes, but reads other agents' private work only
  once W15-6 adds the visible supervision grant.
- The ladder defaults for existing agents and the grant card (W15-3): new agents get
  their level written explicitly here; existing agents are unchanged.

## Verification

- `tests/check_agent_create.py` (PostgreSQL, simulation broker, scripted provider): an
  owner message creates a flexible root trading agent at Ask me with no grant; replays and
  retries add nothing; the result card shows server facts; a research agent's link and
  notes; the per-run and per-owner limits (a repeat still answers); a creation card
  without an owner message and its single creation; Undo removes or pauses; two matching
  accounts ask one question; watches steered only by their agent and by the owner's route;
  `routine_toggle` limited to own routines; a scripted Arabic turn through the normal
  runtime creates one news agent, one supervisor and one link, and a restarted worker
  replaying the turn under new call ids adds nothing.
- `tests/test_agent_create.py`: catalog lookup, templates and levels, input rules, the
  responsibility guard, the receipt key, tool metadata and scopes, card lifetimes and
  fixed confirmations, active watches.
- `tests/web/agent-create.test.ts` (tsx): both cards in English and Arabic, Undo's two
  outcomes, the status line, watch conditions, the avatar, Web/Mobile parity.
