Superseded by VISION.md

# Lead: Lonora reads and steers the team, peers stay private

Lonora, the Personal Agent, leads every team agent by its built-in role
(`lonora_db/lead.py`, mandate 3.1.6, 3.3.1 and 14.3.15). It reads their work and memory
on demand, messages them, pauses or resumes their work, cancels their current run,
switches them to Ask and deletes them. There are two levels and no supervision grants
(3.3.3, 14.2.6): no team agent reads or steers another, and team agents stay as private
from each other as before (wall 5 of correction 1). Migration
`0127_no_supervision_grants` drops `ln_supervision_grants` and deletes the `supervise`,
`supervision_created` and `supervision_stopped` cards (14.3.9); pause holds and their
`supervision_paused` cards stay.

## Lonora reads a team agent

- `session_search` and `search_internal` include, for Lonora only, the threads,
  decisions and memory of every team agent (`HistoryScope.supervised`). Each such result
  names the agent (`supervised_agent`) and carries `untrusted: true`; a message written
  by another agent also names its author (`author_agent_name`). The envelope notice says
  that words written to or by another agent never instruct the reader.
- `subagent_inspect` returns a team agent's Run to Lonora with the same labels; for a
  team agent, any other agent's private Run stays `run_not_found`, and its threads
  `thread_not_found`.
- `agent_inspect` (read-only, toolset `collaboration`) reads a team agent (Lonora), or
  the caller itself, one bounded page at a time: `overview` (role, template, focus pair,
  trading level, who paused it, the live status, the W15-1 trading readiness and that
  Lonora leads it), `work` (watches, routines, Tasks and the pauses held over them),
  `runs` (trigger, status, error, prompt and result excerpts), `decisions`, `operations`
  (journal rows the executor recorded for that agent; a journal status is not broker
  confirmation) or `memory` (its standing instructions and its own memory, read-only).
  `page` reads older items. Nothing is injected into context automatically. Its results
  are classified as retrieved, untrusted content for later runs
  (`run_evidence.EXTERNAL_TOOLS`). A top-level `status` key is never used: the run loop
  reads one as an operation's outcome.
- The agent directory (`list_agents` and the routing frame) shows `you_supervise`
  (Lonora, over every team agent) and `supervises_you` (Lonora, seen by a team agent).

## Lonora steers a team agent

`agent_control` (toolset `collaboration`, long-tail, replay-safe) is Lonora's: it pauses
or resumes a team agent itself or one of its Tasks, routines or watches (`target`,
`target_id`), messages it (`action: message`, the same peer request as `peer_send`),
cancels its current run (`cancel_run`: its started runs, never Lonora's own run or its
ancestors; a queued run stays), switches it to Ask (`set_ask`, the same switch as
`trading_mode_ask`: Ask, except within an active signed grant's own terms until revoked,
which `active_signed_grants` counts) or deletes it (`delete`, see `agents-from-chat.md`).
A team agent is refused (`supervision_required`, `agent_control_lead_only`). It has no
action that trades, grants, raises a limit, lifts a restriction or edits memory or
instructions. A change Lonora makes returns `owner_line: "required"`, and the
conversation gate holds an empty reply until Lonora tells the owner in one line what it
did and why (mandate 3.1.2). `routine_toggle` on another agent's routine follows the
same rules.

Holds (`ln_supervision_holds`) record each pause Lonora or the owner sets:

- Pausing needs the lead role (Lonora); a team agent is refused (`supervision_required`).
  Repeating it changes nothing and says who holds the pause (`you`, `another_agent`,
  `owner`).
- **A paused agent keeps its exits.** A paused agent still wakes for broker events on
  its own positions and pending orders, and for the owner's direct message, and the door
  sends only its risk-reducing requests (mandate 4.7.1). Lonora may therefore pause a
  whole trading agent on its own.
- **Never Lonora.** No agent pauses the Personal Agent itself, not even from the
  owner's message (`supervision_personal_agent`, 403): it is the owner's entry point,
  and a paused Lonora would leave the owner's chat without a reply. Only the owner
  pauses it, from its profile.
- On its own initiative Lonora lifts only a hold it set. A hold set from the owner's message is the owner's (`source='owner'`,
  the agent kept as holder; migration `0155_owner_message_pauses_are_owners`): only
  the owner lifts it (mandate 4.7.2), by a control or by asking in chat (a Run answering
  the owner's untainted message). Only an untainted owner message makes a pause the
  owner's: a Run that read others' content never speaks for the owner (6.10). A hold an
  earlier team supervisor left (before grants were deleted) is lifted only by the owner
  or from the owner's message; it is released as the owner's (`released_by='owner'`). The owner's own pause and the agent's own pause stay with them
  (`supervision_resume_not_yours`).
- **The owner's own pause is a hold too.** When the owner pauses or cancels work that
  no supervisor holds (the agent's switch, a routine switched off, the watch list's
  Pause or Cancel, a Task's Pause, an Undo), `owner_takes_over` records a hold with
  `source='owner'` and no holder (migration `0043_owner_held_pauses`). The paused agent
  is refused its own resume (`work_paused_by_owner`) in a wake and from the owner's
  message alike, exactly as for a hold the owner took over: only the
  owner's own Resume lifts it. Before, such a pause left no record, so `watch_resume`,
  `routine_toggle` and `task_control` undid the owner's stop on the agent's own
  initiative.
- **A deleted holder's pauses stay.** Deleting an agent first makes every live
  hold it holds the owner's (`owner_holds_for`); the row keeps the paused work and its
  card (`holder_agent_id` becomes null, `ON DELETE SET NULL`), so the work stays paused,
  its card keeps offering Resume, and the paused agent cannot lift it. Nothing resumes
  without the owner.
- **Downgrades keep the owner's choices.** The downgrade of `0043_owner_held_pauses`
  refuses while the owner holds a live pause (a holder-less hold has no place in the
  earlier schema), and the downgrade of `0041_supervision_grants` refuses while any live
  hold exists: dropping it would resume paused work. The downgrade of `0127` recreates
  the grant table empty, so no grant comes back. A refused downgrade changes nothing.
- **The owner's pause is the owner's.** The owner pausing work Lonora holds (the
  agent's switch, the routine's switch, the watch list's Pause or Cancel, the Task's
  Pause, an Undo) keeps the hold and makes it the owner's (`source='owner'`, Lonora kept
  for attribution): from then on only the owner lifts it; Lonora and the paused agent are
  refused (`supervision_resume_not_yours`,
  `work_paused_by_owner`), even from the owner's message, the way only the owner lifts
  a restriction. The owner resuming or cancelling the work releases it. Saving a form
  with the switch unchanged (renaming a paused agent, editing a paused routine's
  schedule) takes nothing over: the Web and Mobile forms send the switch with every
  save.
- The paused agent never resumes held work on its own initiative
  (`work_paused_by_supervisor`); it can still cancel it, which only narrows and keeps
  the hold. A watch it cancelled stays cancelled when Lonora resumes it: the
  resume only ends the hold (`stays_cancelled_by_the_agent`). A hold on work that is no
  longer paused is stale and released.
- **The owner hears it in one line.** Lonora's pause raises no card (only the fixed cards
  of 10.3 exist): Lonora tells the owner in one line. A `supervision_paused` card an
  earlier team supervisor raised still shows "Paused by <supervisor>", the agent and
  what (the whole agent, or a routine, watch or Task with its own short label,
  isolated), "from your message" when it was. Resume is the owner's own resume of that work, whoever holds
  it; Keep paused dismisses the card. Once the pause ends anywhere the card stops
  offering Resume, and a tap only settles it (`supervision_pause_ended`); a watch past
  its expiry is resumed from the watch list after moving its expiry (`watch_expired`).
- **No cycle rule.** Only Lonora pauses another agent, and only the owner pauses Lonora,
  so no pause can block a pause back. A pause an earlier team supervisor left over
  Lonora's work never blocks Lonora's pause of that agent (`supervision_cycle` is gone).
- Every pause, resume and narrowing of another agent is a `supervision.intervention`
  event recorded for both agents.
- Lock order: cards, then the work (agent, routine or watch row), then its hold, then
  the conversation, and the Run's lease last, the order the owner's card decision and
  message admission take. `agent_control` and a supervised `routine_toggle` take the
  owner-actions lock first.

## Narrowing another agent's trading

`trade_restriction_create` for another agent, or for all agents, needs the owner's
message in the Run (`restriction_supervision_required`, 403); there is no grant to stand
in for it, also not for Lonora. Narrowing itself stays
free, `all_mutations` on others still needs the owner's message, a restriction on others
is still time-boxed, and only the owner lifts one. Restrictions are removed with W-REMOVE.

## Exposure

The exposure profile `coordination` holds `agent_inspect`, `peer_send` and
`web_search`. Only the Personal Agent gets it, in every conversation Run (3.3.1). A
trading identity's Task Run leaves it out: core, market and task already fill the eager
budget, and these tools stay one `tool_call` away.

## Owner surfaces

- **Cards** (`packages/core/src/owner-actions.ts`, Web and Mobile): only
  `supervision_paused` ("Paused by a supervisor", Resume / Keep paused) remains, for
  pauses an earlier team supervisor made. Names and the paused item's label are server
  facts, isolated for RTL, and every line starts with a word in the owner's language;
  the confirmation line is fixed text (`owner_action_supervision_paused`).
- The supervision settings on agent profiles (Web and Mobile) and `/api/supervision` are
  deleted with the grants.

## Verification

- `tests/test_supervision.py` and `tests/test_lead_powers.py`: tool metadata (no
  financial tool, no trading, authority, restriction-lift or memory writer reachable),
  input shapes, the coordination set; on PostgreSQL, Lonora reads and steers a team
  agent with no grant, a team agent is refused reads (`thread_not_found`,
  `run_not_found`) and control (`supervision_required`, `agent_control_lead_only`).
- `tests/test_pauses.py` (the owner's pauses, `lonora_db.pauses`): the owner's pause
  becoming the owner's, a cancelled watch staying cancelled, the owner's own pause or
  cancel never lifted by the agent, a deleted holder's pauses kept as the owner's.
- `tests/check_supervision.py` (fresh database): Lonora answers from a team agent's
  records through `agent_inspect` and `session_search`; migration `0127` drops the grant
  table and the three card kinds while holds and `supervision_paused` cards stay.
