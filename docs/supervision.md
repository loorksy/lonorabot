Superseded by VISION.md

# Supervision: Lonora sees everything, peers stay private

Lonora, the Personal Agent, supervises every agent by default. It reads their work and
memory on demand, messages them and pauses or resumes their work. The owner sees every
grant and revokes any of them with one tap. Any agent becomes "supervises X and Y" from
one sentence of the owner. A supervisor never trades for the agents it supervises, never
uses their grant, never lifts a brake and never edits their memory or instructions.
Agents without a grant stay as private from each other as before (wall 5 of correction 1).

## Grants

`ln_supervision_grants` (migration `0041_supervision_grants`, `lonora_db/supervision.py`)
holds one row per supervisor and supervised agent: `created_via` (`default`, `owner_ui`,
`owner_message`, `owner_card`), the owner message that asked for it, the agent that
recorded it, `created_at`, and `revoked_at` / `revoked_via`. At most one grant per pair is
active; a revoked grant stays as the record of what was allowed. Rows cascade with
either agent.

Migration 0063 (mandate 14.3.18.4 and .6) revoked every grant whose supervisor is not
Lonora (`revoked_via` empty) and made delegated, child and supervisor-template agents
ordinary team agents, each with `agent.updated`; a bound account and symbol became one
plain line of the agent's OPERATING.md that names the account as the owner knows it
(broker · login · server once the broker verified the connection as it now is, else its
provider and account number). A pause such an agent set on its own (`source='agent'`)
ended and its work resumed through each item's own control: an unpaused agent with
`agent.updated`, and a Task by its shape below, read from the Task as it was locked
(after its thread and the Run that failed it, as `resume_failure` locks them, then its
Run, as `control_task` does), each Task it changed with `task.updated` (version + 1).
"Its Run" is the newest live Run among the 20 newest Runs of the Task's agent in the
Task's thread, the one `control_task` reads; it has "no live Run" when none of them is
live. "Woken" is one Run of the Task's agent in the Task's thread
(`ln_tickets.thread_id`, not its origin), queued with fixed server text naming the Task
(trigger `owner_card`, a stable id, so never twice) after every hold had ended, so an
agent a supervisor paused was woken too. The text says the Task is no longer held and
asks the agent to read it (`task_inspect`); it offers a resume (`task_control`) only
where the live resume takes the Task from the wake, and otherwise says that
`task_control` cannot resume it from there and asks the agent to tell the owner in one
line what it was doing and whether it should go on. An agent still paused by the owner
or Lonora was not woken (`create_run` refuses a paused agent); its Task stayed as its
shape left it, for the owner, or the agent once it runs again, to resume where the live
resume takes it. "Taken" and "refused" are the live resume's (`task_control`), for the
agent and the owner alike, with no hold left.

- Work neither paused nor asked to pause (`work_paused`), among it a Task that had
  failed or waited to retry since: the hold was only released, as `control_work`
  releases a stale one; the Task stayed as it was and no one was woken. It is resumed
  as it would be without the hold.
- An ended Task, completed or cancelled (among them one the migration's grant
  revocation stopped), or failed with no failure the retry resumes: only released, a
  pause still asked of it left as it was, which never takes effect (a checkpoint ends
  the Run of an ended Task); the live resume refuses it (`task_terminal`).
- A Task the live resume hands to the retry (`retry_control`: a failure, and failed,
  waiting to retry, or paused while waiting to retry), paused or asked to pause: a
  pause asked of it (`record_failure` keeps the ask) was withdrawn, as `resume_failure`
  refuses any control asked; nothing else changed. Its agent was woken, with a resume
  offered, only when the live retry then takes it (`resume_failure`): the Task waiting,
  failed or paused, with no control asked; its failed Run still failed, of the same
  lease, agent and thread; a failure the retry resumes (the owner's to resume, the
  automatic retry's, or a financial reconciliation); an attempt left; and no broker
  outcome of that Run still unknown (a journal row reserved, submitted or ambiguous by
  its lease or its execution). The agent or the owner then resumes it, also from the
  wake, and the retry itself resumes one waiting to retry once it is due. Otherwise no
  one was woken, and it is refused as it would be without the hold: a terminal failure,
  one to plan anew until it is revised, another status, or a failed Run since changed
  (`task_cannot_resume`, `task_run_mismatch`); a reconciliation outside Lonora, or a
  broker outcome still unknown until it is reconciled (`task_reconciliation_required`);
  no attempt left, or another control asked (`task_retry_limit`).
- A paused Task, or one asked to pause, whose Run held the owner's question resumed as
  `control_task`'s resume resumes it, the work and not the question
  (`release_attention`): the question was cancelled, the Run queued without its lease,
  the Task queued, the ask and the owner-attention wait cleared. No one was woken: the
  work runs.
- A paused Task whose Run waited for takeover was queued again with its Run, as the live
  resume does, also one that had failed before. No one was woken: the work runs.
- Any other paused Task (none the retry's): its Run neither waited for takeover nor held
  the owner's question (it was queued, held by a worker or waiting for another answer,
  or the Task's own Run waited behind a newer Run of its agent), or it had no live Run
  (its Run was cancelled, as the owner's stop of that Run leaves it, or failed with no
  failure recorded). The live resume refuses it (`task_cannot_resume`,
  `task_run_not_found`), and no live control resumes a paused Task with no live Run. It
  stayed as it was, and its agent was woken with no resume offered: from the wake it is
  refused, the wake's own Run being its newest live Run (`task_cannot_resume`). After
  the wake it is taken once its newest live Run waits for takeover: its own Run behind a
  newer Run of its agent once that one ends, or its own queued or working Run at its
  next checkpoint. Until then it is refused (`task_cannot_resume`); with no live Run it
  is refused for good (`task_run_not_found`), and the owner can only mark it completed.
- Any other Task asked to pause, its Run held by a worker, queued again, or waiting for
  another answer (a Trade Approval or the owner's input) or for takeover: the ask was
  withdrawn, so it never takes effect with no hold. The live resume refuses this shape
  (`task_cannot_resume`) and leaves the ask, but nothing waits to be resumed: the Run
  goes on and reads no pause at its next checkpoint. No one was woken.
- A Task asked to pause with no live Run left (its Run cancelled, as the owner's stop of
  that Run leaves it): the ask was withdrawn and its agent was woken with no resume
  offered. It is refused from the wake (`task_cannot_resume`) and for good after it
  (`task_run_not_found`), as the same Task never paused; the owner can only mark it
  completed.

A pause the owner asked for (`owner_message`) became the owner's (`owner`); the owner's
pauses and Lonora's stayed.

- **Default.** The migration gives each owner's Personal Agent a `default` grant over
  every other agent. A Personal Agent created later supervises every agent that already
  exists (`ensure_personal_agent`), and every agent created afterwards is supervised by
  it from its creation (`agents.create_agent`, so the owner's form, `agent_create`, child
  agents and fixtures all get it). A revoked default grant is not recreated.
- **From one sentence.** `supervision_change` (toolset `collaboration`, long-tail)
  grants or revokes supervision for `supervisor_id` (default: the caller) over
  `supervised_ids`. Oversight for the calling agent itself, or over the Personal Agent,
  is always a `supervise` card the owner taps, never set straight from a Run, so no
  private memory or owner chat is read before the owner sees the grant. In a Run that
  answers the owner's message ("خلي وكيل المراقبة يشرف على وكيل الذهب ووكيل الفضة", said
  to Lonora) it grants at once, records the message as the source and
  raises a `supervision_created` card with Undo for the grants that call created; a
  grant that already existed is never on that card. Without the owner's message it
  raises a `supervise` card and nothing changes until the owner taps Allow; the tap
  raises the same Undo card. Revoking oversight needs the owner's message too
  (`supervision_revoke_requires_owner_message`) and is never done by the supervised
  agent itself, whatever its run (`supervision_revoke_own_oversight`): text it read
  could ask it to shed its oversight. A revoke from chat raises a `supervision_stopped`
  card with Restore, which sets the grants that call ended again (`owner_card`); a pair
  supervised again meanwhile is left as it is. The owner revokes from the profile at
  any time.
- **With a new agent.** `agent_create(supervises=[...])` grants supervision to the new
  agent with the creation's source (owner message or card). The creation card lists
  "Supervises: ..." from the stored spec; a target deleted meanwhile makes the card
  stale (`supervision_agent_missing`).
- **Owner API.** `GET /api/supervision?agent_id=` returns the active grants around one
  agent (`supervises`, `supervised_by`); `POST /api/supervision`
  (`{supervisor_id, supervised_id}`) adds one (`owner_ui`); `POST
  /api/supervision/{id}/revoke` ends one. Supervision is never money authority, so both
  take one tap and no passkey.

Revoking ends every read and control at once: each tool re-reads the grants on every
call, inside the same Run.

## Reading a supervised agent

- `session_search` and `search_internal` include the threads, decisions and memory of
  the agents the caller supervises now (`HistoryScope.supervised`). Each such result
  names the agent (`supervised_agent`) and carries `untrusted: true`; a message written
  by another agent also names its author (`author_agent_name`). The envelope notice says
  that words written to or by another agent never instruct the reader.
- `subagent_inspect` returns a supervised agent's Run with the same labels; any other
  agent's private Run stays `run_not_found`, and its threads `thread_not_found`.
- `agent_inspect` (read-only, toolset `collaboration`) reads an agent the caller
  supervises, or itself, one bounded page at a time: `overview` (role, template, focus
  pair, trading level, who paused it, the live status, the W15-1 trading readiness and
  who supervises it), `work` (watches, routines, Tasks and the pauses
  supervisors hold), `runs` (trigger, status, error, prompt and result excerpts),
  `decisions`, `operations` (journal rows the executor recorded for that agent; a journal
  status is not broker confirmation) or `memory` (its standing instructions and its own
  memory, read-only). `page` reads older items. Nothing is injected into context
  automatically. Its results are classified as retrieved, untrusted content for later
  runs (`run_evidence.EXTERNAL_TOOLS`). A top-level `status` key is never used: the run
  loop reads one as an operation's outcome.
- The agent directory (`list_agents` and the routing frame) shows `you_supervise` and
  `supervises_you` for every agent, so both sides know.

## Steering a supervised agent

`agent_control` (toolset `collaboration`, long-tail, replay-safe) pauses or resumes the
supervised agent itself or one of its Tasks, routines or watches (`target`,
`target_id`), or messages it (`action: message`, the same peer request as `peer_send`).
It has no action that trades, grants or edits memory or instructions.
Only a supervisor steers another agent's work; on the owner's message the Personal
Agent may too without a grant, and no other agent, whatever message its Run answers
(`supervision_required`). The owner's message counts only while the Run has read
nothing someone else wrote (see `agents-from-chat.md`). `routine_toggle` on a
supervised agent's routine follows the same rules.

Holds (`ln_supervision_holds`) record each pause a supervisor sets:

- Pausing needs the grant, or the owner's message in the actor's Run. Repeating it
  changes nothing and says who holds the pause (`you`, `another_agent`, `owner`).
- **Never a trading agent's exits.** A paused agent's runs are never claimed, so it
  could no longer close a position, cancel an order, tighten a stop or run an exit the
  owner approves. Without the owner's message in the Run, a supervisor therefore never
  pauses a whole agent with money standing: bound to an account, at Ask me or On its
  own (a signed grant), or with live operations the executor recorded for it
  (`supervision_pause_trading_agent`, 403). It pauses that agent's routines, watches or
  Tasks instead. From the owner's message the whole-agent pause stands.
- **Never Lonora.** No agent pauses the Personal Agent itself, not even from the
  owner's message (`supervision_personal_agent`, 403): it is the owner's entry point,
  and a paused Lonora would leave the owner's chat without a reply. Only the owner
  pauses it, from its profile. Reading it, messaging it and pausing its
  routines, watches or Tasks stay open to a supervisor.
- On its own initiative only the supervisor that set a hold lifts it, while it still
  supervises; a hold set from the owner's message needs the owner's message again
  (`supervision_resume_needs_owner_message`). A Run that answers the owner's message
  lifts any supervisor's hold, whichever agent it is (the paused agent itself through
  `routine_toggle`, `watch_resume` or `task_control`, or any supervisor through
  `agent_control`); it is released as the owner's (`released_by='owner'`). The
  owner's own pause and the agent's own pause stay with them
  (`supervision_resume_not_yours`).
- **The owner's own pause is a hold too.** When the owner pauses or cancels work that
  no supervisor holds (the agent's switch, a routine switched off, the watch list's
  Pause or Cancel, a Task's Pause, an Undo), `owner_takes_over` records a hold with
  `source='owner'` and no holder (migration `0043_owner_held_pauses`). The paused agent
  is refused its own resume (`work_paused_by_owner`) in a wake and from the owner's
  message alike, exactly as for a supervisor's hold the owner took over: only the
  owner's own Resume lifts it. Before, such a pause left no record, so `watch_resume`,
  `routine_toggle` and `task_control` undid the owner's stop on the agent's own
  initiative.
- **A deleted supervisor's pauses stay.** Deleting an agent first makes every live
  hold it holds the owner's (`owner_holds_for`); the row keeps the paused work and its
  card (`holder_agent_id` becomes null, `ON DELETE SET NULL`), so the work stays paused,
  its card keeps offering Resume, and the paused agent cannot lift it. Nothing resumes
  without the owner.
- **Downgrades keep the owner's choices.** The downgrade of `0043_owner_held_pauses`
  refuses while the owner holds a live pause (a holder-less hold has no place in the
  earlier schema), and the downgrade of `0041_supervision_grants` refuses while a grant
  the owner set (not `default`) or revoked, or any live hold, exists: dropping them
  would bring a revoked default back on the re-upgrade (Lonora reading an agent the
  owner took away from it) or resume paused work. A refused downgrade changes nothing.
- **The owner's pause is the owner's.** The owner pausing work a supervisor holds (the
  agent's switch, the routine's switch, the watch list's Pause or Cancel, the Task's
  Pause, an Undo) keeps the hold and makes it the owner's (`source='owner'`, the
  supervisor kept for attribution): from then on only the owner lifts it; the
  supervisor and the paused agent are refused (`supervision_resume_not_yours`,
  `work_paused_by_owner`), even from the owner's message. The owner resuming or
  cancelling the work releases it. Saving a form
  with the switch unchanged (renaming a paused agent, editing a paused routine's
  schedule) takes nothing over: the Web and Mobile forms send the switch with every
  save. An owner-held pause is not a pause the supervisor holds for the cycle rule.
- The paused agent never resumes held work on its own initiative
  (`work_paused_by_supervisor`); it can still cancel it, which only narrows and keeps
  the hold. A watch it cancelled stays cancelled when its supervisor resumes: the
  resume only ends the hold (`stays_cancelled_by_the_agent`). A hold on work that is no
  longer paused is stale and released.
- **The owner sees who did it.** Every pause raises a `supervision_paused` card in the
  paused agent's conversation: "Paused by <supervisor>", the agent, and what (the whole
  agent, or a routine, watch or Task with its own short label, isolated), "from your
  message" when it was. Resume is the owner's own resume of that work, whoever holds
  it; Keep paused dismisses the card. Once the pause ends anywhere the card stops
  offering Resume, and a tap only settles it (`supervision_pause_ended`); a watch past
  its expiry is resumed from the watch list after moving its expiry (`watch_expired`).
- **Cycle rule.** An agent cannot pause an agent that holds an active pause over it: a
  live hold on it or its work (`supervision_cycle`). The owner's
  message in the Run wins over the rule. Observing and messaging stay free in every
  direction.
- Every pause and resume of another agent is a `supervision.intervention`
  event recorded for both agents.
- Lock order: cards, then the work (agent, routine or watch row), then its hold, then
  the conversation, and the Run's lease last, the order the owner's card decision and
  message admission take. `agent_control` and a supervised `routine_toggle` take the
  owner-actions lock first.

## Exposure

A new exposure profile `coordination` holds `agent_inspect`, `peer_send` and
`web_search`. The Personal Agent gets it in every conversation Run, and any agent gets it
while it holds a supervision grant. A trading identity's Task Run leaves it out: core,
market and task already fill the eager budget (25,678 of 25,700 after the phase 2
integration), and these tools stay one `tool_call` away. The Personal Agent's
conversation set is 25,684 of 25,700 (25,695 on the slice branch).
`web_fetch`, `artifact_read` and `economic_calendar_read` (the rest of the research
profile) do not fit and are promoted after first use like any remembered tool.
`web_search`'s description was shortened to make room; its meaning is unchanged.

## Owner surfaces

- **Cards** (`packages/core/src/owner-actions.ts`, Web and Mobile): `supervise` ("Let it
  supervise?": the supervisor, "Supervises: ...", what a supervisor may and may never do;
  Allow / Not now), `supervision_created` ("Supervision set", Undo / Keep it),
  `supervision_stopped` ("Supervision stopped", Restore / Keep it) and
  `supervision_paused` ("Paused by a supervisor", Resume / Keep paused). Names and the
  paused item's label are server facts, isolated for RTL, and every line starts with a
  word in the owner's language; the confirmation line is fixed text
  (`owner_action_supervise`, `owner_action_supervision_created`,
  `owner_action_supervision_stopped`, `owner_action_supervision_paused`).
- **Profiles** (Web `SupervisionSettings`, Mobile `supervision-settings`, labels in
  `packages/core/src/supervision.ts`): every agent's settings list whom it supervises and
  who supervises it, each with where the grant came from and one-tap Stop. Lonora's
  profile ("Lonora supervises your agents") also lists the agents it no longer
  supervises, with Supervise.

## Not in this slice

- Per-agent private sharing other than supervision (a scoped knowledge store) is Wave 2.
- The rest of the research profile and the `collaboration_*` tools in the Personal
  Agent's eager set (spec item 6): its conversation set is 25,684 of the 25,700 budget
  after integration, so a longer eager description there breaks the budget test. Open
  item for the acceptance slice: trim other eager descriptions, or set an explicit,
  owner-approved budget.

## Verification

- `tests/test_supervision.py`: tool metadata (no financial tool, no trading, authority
  or memory writer reachable), input shapes, the coordination set and
  card texts; on PostgreSQL, a peer without a grant still gets `thread_not_found`,
  `run_not_found` and `supervision_required`; a grant opens labelled reads of threads,
  decisions, runs and memory (an injected instruction stays inside a labelled record);
  revocation closes them inside the same Run; holds, the cycle rule and the owner's
  message overriding it; a rename that keeps the switch leaves the supervisor's hold; a
  bound agent and an Ask me agent refused a whole-agent pause on a routine wake and
  paused from the owner's message; Lonora never paused by another agent; the pause card
  with its facts, Resume as the owner's own and its stale settle; the owner's pause
  becoming the owner's (supervisor and agent refused, the cycle rule no longer counts
  it); the owner's message lifting a supervisor's pause through the paused agent and
  through another agent; a cancelled watch staying cancelled; supervision from a card
  and from a sentence
  with Undo; the supervised agent refused revoking its own oversight and a revoke from
  chat restored from its card; the Personal Agent's default grant on a new agent.
- `tests/check_supervision.py` (fresh database): the migration seed, its idempotence and
  round trip, a Personal Agent created after other agents, a later agent; a real Run in
  which Lonora answers "what did the gold agent do and why did it skip London" from the
  records through natively offered `agent_inspect` and `session_search`, with nothing of
  the gold agent in its context beforehand, refused after the owner revokes the grant.
- `tests/web/supervision.test.ts` (the supervise, Undo, Restore and pause cards in
  Arabic and English) and Playwright `supervision` (Web and Mobile, Arabic and English):
  the cards, the profile rows, Stop and Supervise.
