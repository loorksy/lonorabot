# Supervision: Lonora sees everything, peers stay private

Corrections 1, 3 and 15 (`docs/lonora-specs/MANDATE_CORRECTIONS.md`) and `VISION.md`:
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

- **Default.** The migration gives each owner's Personal Agent a `default` grant over
  every other agent. A Personal Agent created later supervises every agent that already
  exists (`ensure_personal_agent`), and every agent created afterwards is supervised by
  it from its creation (`agents.create_agent`, so the owner's form, `agent_create`, child
  agents and fixtures all get it). A revoked default grant is not recreated.
- **From one sentence.** `supervision_change` (toolset `collaboration`, long-tail)
  grants or revokes supervision for `supervisor_id` (default: the caller) over
  `supervised_ids`. In a Run that answers the owner's message ("خلي وكيل المراقبة يشرف
  على وكيل الذهب ووكيل الفضة") it grants at once, records the message as the source and
  raises a `supervision_created` card with Undo for the grants that call created; a
  grant that already existed is never on that card. Without the owner's message it
  raises a `supervise` card and nothing changes until the owner taps Allow; the tap
  raises the same Undo card. Revoking another agent's oversight needs the owner's
  message too (`supervision_revoke_requires_owner_message`); the owner revokes from the
  profile at any time.
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
  who supervises it), `work` (watches, routines, Tasks, active goals and the pauses
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
It has no action that trades, grants, raises a limit, lifts a restriction or edits
memory or instructions. A supervisor narrows the agent's trading with
`trade_restriction_create` and its `agent_id`. `routine_toggle` on a supervised agent's
routine follows the same rules.

Holds (`ln_supervision_holds`) record each pause a supervisor sets:

- Pausing needs the grant, or the owner's message in the actor's Run. Repeating it
  changes nothing and says who holds the pause.
- Only the supervisor that set a hold lifts it, while it still supervises. A hold set
  from the owner's message is lifted only from the owner's message again
  (`supervision_resume_needs_owner_message`). The owner's own pause, the agent's own and
  another supervisor's stay (`supervision_resume_not_yours`).
- The owner pausing or resuming the same work (the agent's switch, the routine form, the
  watch list, Task controls, an Undo) takes the hold over: it becomes the owner's.
- The paused agent cannot resume work a supervisor paused
  (`work_paused_by_supervisor`); it can still cancel it, which only narrows. A hold on
  work that is no longer paused is stale and released.
- **Cycle rule.** An agent cannot pause, or narrow with a restriction, an agent that
  holds an active pause over it: a live hold on it or its work, or a pause that agent
  recorded on its own initiative that still binds it (`supervision_cycle`). The owner's
  message in the Run wins over the rule. Observing and messaging stay free in every
  direction.
- Every pause, resume and narrowing of another agent is a `supervision.intervention`
  event recorded for both agents.

## Narrowing another agent's trading

`trade_restriction_create` for another agent now needs the owner's message in the Run
or a grant over that agent; for all agents, the owner's message or a grant over every
other agent (`restriction_supervision_required`, 403). It also passes the cycle rule.
Narrowing itself stays free, `all_mutations` on others still needs the owner's
message, a restriction on others is still time-boxed, and only the owner lifts one.

## Exposure

A new exposure profile `coordination` holds `agent_inspect`, `peer_send` and
`web_search`. The Personal Agent gets it in every conversation Run, and any agent gets it
while it holds a supervision grant. A trading identity's Task Run leaves it out: core,
market and task already fill the eager budget (25,689 of 25,700), and these tools stay
one `tool_call` away. The Personal Agent's conversation set is 25,695 of 25,700.
`web_fetch`, `artifact_read` and `economic_calendar_read` (the rest of the research
profile) do not fit and are promoted after first use like any remembered tool.
`web_search`'s description was shortened to make room; its meaning is unchanged.

## Owner surfaces

- **Cards** (`packages/core/src/owner-actions.ts`, Web and Mobile): `supervise` ("Let it
  supervise?": the supervisor, "Supervises: ...", what a supervisor may and may never do;
  Allow / Not now) and `supervision_created` ("Supervision set", Undo / Keep it). Names
  are server facts, isolated for RTL; the confirmation line is fixed text
  (`owner_action_supervise`, `owner_action_supervision_created`).
- **Profiles** (Web `SupervisionSettings`, Mobile `supervision-settings`, labels in
  `packages/core/src/supervision.ts`): every agent's settings list whom it supervises and
  who supervises it, each with where the grant came from and one-tap Stop. Lonora's
  profile ("Lonora supervises your agents") also lists the agents it no longer
  supervises, with Supervise.

## Not in this slice

- An explicit "lift a supervisor's hold" card: the owner resumes the work itself, which
  takes the hold over.
- Per-agent private sharing other than supervision (a scoped knowledge store) is Wave 2.

## Verification

- `tests/test_supervision.py`: tool metadata (no financial tool, no trading, authority,
  restriction-lift or memory writer reachable), input shapes, the coordination set and
  card texts; on PostgreSQL, a peer without a grant still gets `thread_not_found`,
  `run_not_found` and `supervision_required`; a grant opens labelled reads of threads,
  decisions, runs and memory (an injected instruction stays inside a labelled record);
  revocation closes them inside the same Run; holds, the owner taking over, the cycle
  rule and the owner's message overriding it; restricting another agent without a grant
  or owner message is 403; supervision from a card and from a sentence with Undo; the
  Personal Agent's default grant on a new agent.
- `tests/check_supervision.py` (fresh database): the migration seed, its idempotence and
  round trip, a Personal Agent created after other agents, a later agent; a real Run in
  which Lonora answers "what did the gold agent do and why did it skip London" from the
  records through natively offered `agent_inspect` and `session_search`, with nothing of
  the gold agent in its context beforehand, refused after the owner revokes the grant.
- `tests/web/supervision.test.ts` and Playwright `supervision` (Web and Mobile, Arabic and
  English): the cards, the profile rows, Stop and Supervise.
