# Tool execution runtime

`lonora_agent.tool_loop` drives every Run: it executes the assistant's tool
calls, checkpoints each result, merges owner steering and decides when a turn
ends. This page describes how a tool-call block is executed and how the loop
ends at a limit. The model still decides what to call and when to stop; the
runtime only enables concurrency and enforces effect, authority and budget
boundaries.

| Module | Responsibility |
| --- | --- |
| `tool_loop.py` | The one loop: its phases in order, checkpoints, steering, model turns, limits and the final report |
| `loop_restore.py` | Checkpoint restore and resume, including checkpoints written by earlier releases |
| `tool_block.py` | One tool-call block: segments, intent, receipts, approval and wait routing, results in call order |
| `loop_outcomes.py` | Outcomes that end a pass: final answers after the stop gates, waits, owner attention |
| `tool_dispatch.py` | One call under the receipt, reconciliation and crash-replay rules |
| `tool_intent.py` | Per-call intent markers and closing of unexecuted proposals |
| `tool_batch.py` | Ordered parallel/serial segments and bounded concurrent execution |
| `tool_guardrails.py` | Checkpointed loop guardrail controller |
| `runtime_notices.py` | Placement and wording of runtime notices |
| `stop_gates.py` | Bounded completion nudges for Task work |
| `tool_exposure.py` | The Run's frozen native tool set, remembered tools |
| `lonora_tools.registry` | Exposure, `tool_call` bridge, discovery, availability, dispatch |
| `lonora_tools.base.Tool` | `parallel_safe`, `poller`, `timeout_seconds`, `toolset`, `eager`, `availability` |

## Capability exposure and discovery

The model decides which capability to use; exposure only decides which input
schemas travel natively with each request. It never grants or removes
authority: `ToolRegistry.execute` runs any registered tool the Run is
permitted to call, whichever path the call took.

**Eager working set as Tool metadata.** Every `Tool` declares a `toolset` (its
capability family, which is also the operating-policy chapter that governs it;
the loader fills it from the module) and the exposure profiles that receive it
eagerly (`Tool.eager`). A Run's profiles come from its agent and kind:

| Profile | Applies to | Eager tools |
| --- | --- | --- |
| `core` | every Run | `tool_environment`, `tool_call`, `skills_list`, `skill_view`, `wait_for_input`, `memory_read`, `memory_write`, `session_search` |
| `market` | agent bound to a broker account, and the owner's Personal Agent (it reads every owned account and analyzes directly when no specialist exists) | `list_accounts`, `market_quote`, `market_candles`, `market_instrument`, `market_snapshot`, `market_sessions`, `account_read`, `chart_snapshot`, `market_decision_record`, `market_decision_history`, `watch_create`, `watch_list`, `watch_cancel`, `trade_execute`, `trade_close_positions` |
| `research` | every other agent | `web_search`, `web_fetch`, `artifact_read`, `economic_calendar_read` (only when the owner configured a calendar source) |
| `coordination` | the Personal Agent, and any agent while it holds a supervision grant; not a trading identity's Task Run (`docs/supervision.md`) | `agent_inspect`, `peer_send`, `web_search` |
| `task` | durable Task Runs | `task_wait`, `task_step_update` |

A Run's tool scope (`ToolScope`, `run_scope` in `lonora_tools/base.py`) narrows
the members: an observe-only wake keeps every non-financial member (no financial
effects), and a helper (subagent) keeps the read-only members plus
`workspace_execute` and `artifact_create`. The eager set
is at most `EAGER_SCHEMA_BUDGET` (26,950) characters of serialized schema for
every profile combination (largest today: the Personal Agent's conversation
with coordination, 26,929, and market Task Runs, 26,923; a market conversation
about 25,600; a general conversation about 9,000), against
about 97,500 for the whole catalog. `tests/test_tool_discovery.py` enforces the
budget, so adding an eager tool fails fast when it does not fit. The budget rose
from 24,000 to 24,800 when the core set gained ranked history recall
(`session_search`) and granular memory operations (see
`docs/agent-memory-and-recall.md`); the literal `search_internal` left the core
set. It rose to 25,700 when the market set gained `market_snapshot` (one call
replaces a quote read plus a candle read per timeframe for a first look at a
market) and the DST-correct `market_sessions` clock, while `market_structure`
left it: the snapshot reports swing structure per timeframe with the same rule,
and exact anchors and lines are a follow-up through `tool_call` (and a remembered
tool once used). `PROMOTED_SCHEMA_BUDGET` gave up the same 900 characters, so
the worst-case native set is unchanged. It rose to 26,950 when the market set
gained the counterparts of what it already offered: `watch_list` and
`watch_cancel` beside `watch_create`, and `trade_close_positions` beside
`trade_execute`. A Run that may create a watch or open a position lists, stops
and closes the same way, so an exit is never the harder tool to find (offering
a tool authorizes nothing: every call is still validated).
`PROMOTED_SCHEMA_BUDGET` gave up the same 1,250 characters (4,100 to 2,850),
which those three tools no longer need from it; it still holds `trade_execute`
beside two reads for an agent that is not a market agent. Owner restrictions and monetary limits
are shown in the permission frame on every turn, so `trade_restriction_create`
and `trade_restriction_list` stay long-tail. A tool whose backend is not
configured reports it through `availability`: `economic_calendar_read` without
an enabled calendar integration, `market_candles_to_workspace` without workspace
access.

**Remembered tools.** After a call to a tool outside the profile's eager set
succeeds, the loop records it in `ln_agent_tool_usage` (migration 0035; per
agent, the 16 most recent, with a use count; best effort, never retried, never
part of the call's observation: a failed write, such as a deadlock or a deleted
agent, is logged and the Run continues unchanged). Narrowed Runs record
nothing: a helper Run carries its parent's agent id, and observe-only wakes are
automated, so neither displaces the agent's own tools. When the agent's next
Run starts, its most recent remembered tools are promoted into that Run's
native set, at most `MAX_PROMOTED_TOOLS` (6) and `PROMOTED_SCHEMA_BUDGET`
(2,850 characters); tools that are unavailable,
out of scope or larger than the remaining budget are skipped. A follow-up turn
therefore calls the long-tail tool it used last time directly. The native set
is bounded by about 29,800 characters in the worst case.

**Frozen per Run.** The set is chosen once, when the Run first enters the loop,
and stored in the checkpoint as `tool_exposure` (`profiles`, `native`,
`promoted`, `unavailable`). Every model turn of the Run, restarts and Task
slices included, sends byte-identical tool definitions and the same capability
inventory text, so the provider's reusable prompt prefix is not invalidated by
discovery. A checkpoint written by an earlier release keeps every schema it had
already shown (its `discovered_tool_names`, called and pending tools) in its
native set; `discovered_tool_names` is then removed.

**The `tool_call` bridge** (adapted from Hermes Agent `tools/tool_search.py`,
MIT). Discovering a tool no longer adds it to the native array. The model reads
the exact schema with `tool_environment` and calls
`tool_call {"name": <exact name>, "arguments": {...}}`. `model_turn` resolves
each well-formed bridge call into the real call, with the model's own call id,
immediately after the provider returns and before anything else sees it: the
financial-truth gates, the parallel planner, guardrails, inflight markers,
receipts and reconciliation, approvals, the persisted transcript, policy
chapter selection, progress events and task recovery all observe exactly the
call a direct invocation would have produced. A financial tool reached through
the bridge therefore passes every check a direct call passes, and an
interrupted bridged mutation is `tool_execution_uncertain` like any other.
Arguments given as a JSON string or omitted are normalized; anything that does
not name one registered tool (unknown name, a bridge tool, unexpected keys,
non-object arguments) stays a `tool_call` and fails in its handler with
`tool_call_target_unknown`, `tool_call_target_invalid` or
`tool_arguments_invalid` without dispatching anything. The reply truth gates
(no prose beside a proposed financial call; failure summaries beside
`task_wait`) read every target a call proposes, through the bridge whether or
not it resolved (`proposed_names`: flattened or unexpected keys, non-object
arguments, a nested bridge, a `calls` batch, any letter case), and the
tool-less limit report resolves its reply the same way. A malformed bridged
trade therefore never publishes "done" in chat, in a `task_wait` update or as
the final report.

Why discovered schemas are not appended mid-Run: the tool definitions lead the
cached prompt prefix, so each append invalidated the whole cache, policy
prefix included, and cost an extra model round before the first use. Accuracy
is preserved instead by returning the exact input schema in the discovery
result (it stays in the transcript), validating the target's own Pydantic
contract on execution with bounded, repairable issues, and promoting tools
that were actually used into the next Run's native set.

**Discovery.** `tool_environment` keeps the BM25 catalog search adapted from
Hermes, now with up to 12 results (`MAX_SEARCH_RESULTS`). Results carry their
input schemas up to 16,000 characters in total; later results list their
required fields and are inspected with an exact `tool_name`. Every entry states
`invoke` (`direct` for this Run's native tools, otherwise `tool_call`),
`available` and, when unavailable, `unavailable_reason`.

**Availability.** A Tool may declare an availability check. Checks are
presentation only and fail open: an error never hides a capability, and the
handler remains authoritative.

| Tool | Unavailable when | Code |
| --- | --- | --- |
| `web_search` | no SearXNG URL and no enabled Brave integration with a secret | `research_provider_not_configured` |
| `web_browse` | no browser service URL | `browser_unconfigured` |
| `workspace_*` | no analytical workspace | `workspace_unconfigured` |
| `workspace_execute`, `skill_package_validate` | no analysis host bridge | `workspace_execution_unconfigured` |
| `mcp_execute` | no operator declaration and no MCP server the owner trusted (or the operator's deny override) | `mcp_tool_not_authorized` |
| `trade_execute`, `trade_close_positions`, `goal_step_execute` | Run of an agent whose current permission is analysis | `agent_analysis_only` |

Unavailable tools stay out of the native set, are listed under
`unavailable_now` in the capability inventory and are marked in discovery
results. The Run's availability snapshot is frozen with its exposure;
`tool_environment` re-checks the tools it returns. A check shared by several
tools runs once per snapshot. The permission check is presentation only: every
financial handler rechecks current permission before it prepares or sends, so
an analysis-only agent is not offered a trade it cannot place, and a permission
raised later in the Run still works through `tool_call`.

**Registry facts outside the registry.** The policy routing map in
`resources/system/manifest.json` is exported from `Tool.toolset`. The
remaining name sets that cannot import the registry (`FINANCIAL_CALLS`,
`FINANCIAL_REPLAY_TOOLS`, `CHECKPOINT_TOOLS`, skill `CAPABILITY_TOOLS`) are
checked against registry metadata by `tests/test_capability_exposure.py`.

## Concurrent reads, serial effects

Each assistant tool-call block is split into ordered segments (adapted from
Hermes Agent `agent/tool_dispatch_helpers.py::_plan_tool_batch_segments`, MIT).
A call joins a parallel segment only when the server registry says it is
read-only, not financial and `parallel_safe`. Contiguous admissible calls run
together with `asyncio.gather` under a semaphore of four
(`MAXIMUM_PARALLEL_TOOLS`); a lone read stays serial. Every other call is a
barrier executed alone: mutations, financial operations, waits
(`wait_for_input`, `task_wait`), `group_silence`, the skill instruction tools
(they change the instruction authority used by later calls), `web_browse` (the
shared browser service renders at most two pages at once for every Run and
fails fast when busy) and unknown names.
A later call never crosses an earlier barrier. `tool_environment` reports each
tool's class as `batch_execution` (`parallel_read` or `serial`). Calls made
through the `tool_call` bridge are planned by the tool they name.

Results are observed, appended and checkpointed in the original call order,
whatever order the handlers finish in. Owner steering is checked before every
segment and merged only after a complete tool-result block. A fatal error
(stale lease, revoked skill authority, cancellation) cancels the sibling
handlers before it propagates; owner cancellation therefore still stops work.
Each handler opens its own database session through `ToolContext.db`; no
session is shared between concurrent handlers.

If a read in a parallel segment needs a scheduled read retry, the results of
the later reads in that segment are discarded and those reads re-run with it;
only a completed prefix of the block is ever checkpointed.

## Intent markers and crash recovery

Before a handler can cross an effect boundary the loop persists intent in
`environment.inflight_calls` (one entry per call). A serial call also writes
the single `environment.inflight` slot used by earlier releases, so a rolled
back worker cannot replay a mutation it does not see in the new set. A
parallel read segment marks all of its calls in one checkpoint.

On recovery, every call in either marker (and in `legacy_pending`) is treated
as interrupted:

- read-only calls re-run;
- replay-safe handlers run again and reconcile their own receipt;
- any other interrupted mutation becomes `tool_execution_uncertain` and is
  never resent.

Receipts, ambiguous financial route records and same-operation reconciliation
keep their priority over all of this. Checkpoints written by the previous
single-slot code resume unchanged.

A failed call's observation is `{ok: false, code, class, retryable, hint}` plus `recovery`;
`class` is one of input, resolution, connection, permission, provider, internal
(`environment.error_class`, from the recovery category). An operation the executor
refused or the broker failed (`status` failed or rejected) is `ok: false` too; a read
that returns the record of such an operation has itself succeeded and is not touched.
The owner's rejection of a card (`trade_approval_rejected`) and an agent whose level
does not trade (`agent_analysis_only`, `shadow_execution_forbidden`) are of class
permission.

Every failure has a `hint`: the tool's own when it wrote one, else the general sentence
of its recovery category (`environment.RECOVERY_HINTS`). A general hint says no more
than is known: an outcome that is not known says so and forbids both "failed" and "went
through"; a permission hint says not to look for another way, and the sentence for an
unclassified refusal says a rule or the owner's decision is respected; a connection
failure is offered for another try only on a read, and a read that failed three times
says it is not tried again. A handler that returns its own sentence under `recovery` has
it carried as the `hint` (the structured block takes the `recovery` key), and a next step
a handler names itself is kept in the block.

A tool writes its own fields by raising `ToolRefusal` (`lonora_core.user_error`), whose
`details` `tool_dispatch` forwards: authored text and the account's own data, never
exception text. Today: `tool_arguments_invalid` carries its `issues`; a symbol the
account does not list (`symbol_not_found`, `symbol_ambiguous`) carries the account's
`candidates`, a `hint` and `next_actions` (`docs/market-analysis.md`, Instrument
resolution); a new order whose size the contract cannot take (`volume_out_of_range`,
`volume_step_mismatch`) is refused by `trade.require_order_size` before any card and
before the executor, with the contract's `limits`. That check runs on a first attempt
only (`trade.never_recorded`): a call that already has an approval card or a journal
entry (after the owner's approval, after a restart, or to reconcile an unknown outcome)
is answered from its record. A partial close is never checked there: an exit is the
executor's alone. A broker rate limit (`broker_rate_limited`) is a transient read
failure: a read is retried after a short wait like a dropped connection.

**What the model reads.** The Run record keeps the whole envelope. The request to the
model carries every tool result through `failure_view`: a `code` of ours becomes
`reason` with its words spelled out ("symbol not found"), and the recovery labels
likewise. That covers a failure, an outcome not yet known and a result that only notes
why nothing was done (`no_positions`); a `code` that is not a machine label, such as one
an outside tool returns, is left alone, and a `reason` the result already gives is kept
after the code's words. Tool names stay exact. A reply cannot repeat a machine code the
model never read; the gates, the scorer and the logs still read the codes in the record.
The background summary and the context sections that list earlier failures still read
the record and are not covered by this view.

**Where the class comes from.** `classify()` names the codes it knows. For a refusal it
does not name, `tool_dispatch` passes the status the tool raised (`http_status`, read and
removed by `observe`): forbidden is `permission`, an invalid request is `input`, and four
families of conflict say what they are (a confirmation or a reconciliation that is
required, the mandate's own terms or a pause, an order on the wrong side). Any other conflict stays as it
was: a state conflict says nothing a model can act on, and a count that is full (helpers,
pins, retries) is not a rule of the owner's. A `broker_` code keeps its class, and a
named code never changes with its status. A class the tool wrote itself
(`ToolRefusal.details`) decides the category, the next step and the hint together, and a
not-found result that carries `candidates` points at them (`follow_hint`).

## Names in place of ids

An id argument also takes what the owner calls the thing. `lonora_tools.resolve.resolve`
answers one of four ways from the list the calling tool already has, so nothing outside
the caller's reach is ever offered: the id itself; the one item a name fits; several
(`<kind>_ambiguous`, never chosen between); none (`<kind>_not_found` with the nearest
names, or what exists). Names fold as the owner's search does (`lonora_core.search_fold`).
What a name may do depends on the call:

| Call | One item fits |
|---|---|
| A read (`use="any"`) | It is used, and the result says so under `reference_resolution`. |
| A stop of the caller's own item (`use="exact"`) | Used only when the name is exactly its name. |
| Anything else (`use="refuse"`) | Refused with the item and `next_actions: [{repeat_with: {<argument>: <id>}}]`. |

| Reference | Where | Named by | Acts on a name |
|---|---|---|---|
| Account | `market_binding.named_account`, before validation, for every market tool | account number, account name, broker | reads only; an order, a watch, a goal or a grant is refused with the account |
| No account named | `prepare_market_arguments`, for an agent with no market of its own and a tool that requires one | | the agent's own, its one signed, or the owner's only account as before; with several and none of those, `broker_sessions_ambiguous` with the accounts |
| Position or order ticket | `trade.require_ticket`, only for a ticket `trade_execute` itself named | its symbol | never: the refusal lists the tickets; first attempt only; a batch built from the account's own list is never checked |
| Watch | `market_watch.named_watch` | symbol, "symbol condition level", prompt | cancel and pause on an exact name, among watches the action still applies to; resume and update never |
| Routine | `routine.named_routine` | title, prompt | switching off on an exact title; switching on never |
| Task | `tasks.named_task` | title | `task_inspect` only |
| Agent | `supervision.named_agent` | name, among this agent and those it supervises now | `agent_inspect` only; `agent_control` never |

A change is never pointed at something the call did not name, an exit is never held back
by a resolver (a ticket is only checked for existing, on a first attempt, and a failed
read leaves the request to the executor), and nothing new wakes an agent: switching a
watch or a routine back on always needs its id.

## Dispatch deadlines

`ToolRegistry.execute` wraps the handler in a per-tool deadline:
`Tool.timeout_seconds`, or 45 s for reads and 90 s for mutations by default.
Long-running tools declare their own (`web_browse` 60 s, `mcp_tools` 75 s,
`mcp_execute` 120 s). Financial tools are never
wrapped and the registry rejects a deadline on one: they own broker deadlines,
and cancelling after send would create ambiguity. A read deadline is the
existing `tool_read_timeout` observation (with the normal bounded read retry);
an interrupted mutation is `tool_execution_uncertain`.

## Loop guardrails

The guardrail controller (adapted from Hermes Agent `agent/tool_guardrails.py`,
MIT) replaces the old `repeated_tool_call` Run failure, which fired after the
effect had already run. Its JSON state lives in the Run checkpoint
(`tool_guardrails`), so restarts and compute slices cannot reset it; real owner
input and external wakes start a new epoch. A new epoch also expires exhausted
read-only route records (`expire_read_routes`), so a quote refused while the market
was closed can be read again after a wake; ambiguous effect routes stay blocked
until reconciled.

| Signal | Warn | Block / halt |
| --- | --- | --- |
| Same call, same arguments, failing | 2nd failure | route exhaustion (existing, 3 failures) |
| Same tool failing with any arguments | 3rd failure | halt at 8 |
| Identical read returning an identical result | 2nd repeat | block at 5, halt after 2 ignored blocks |
| Identical consecutive read and result (non-poller) | 3rd | halt at 5 |
| Identical effect: a mutating or financial call with identical arguments, whatever it returned | 2nd | the 6th is blocked before its handler runs; halt on the next repeat |
| Identical A/B… cycle of 2–4 calls | 3 laps | halt at 5 laps |

The identical-effect streak ignores results on purpose: every financial result
carries a fresh operation identity, so only the arguments show that the same
effect is being requested again (for example a provider that duplicates one
`trade_execute` call in a block). Observations between the repeats do not
break the streak; a different effect does. The previous release failed the
Run on the 6th identical success, after that effect had run; now at most five
identical effects execute per review epoch and the 6th is a synthetic
`guardrail_blocked` observation. An approval wait is not an execution; the
approved dispatch of the same call counts once. Nor is a reconciliation: an
identical call on an ambiguous financial route replays the SAME durable operation
through the blocked route and sends nothing, so dispatch marks its result
`_runtime_reconciled` and the streak neither counts nor refuses it (the same-tool
failure bound still ends an endless reconciliation loop).

A warning is attached to that tool result as a `runtime_notice`. A block
returns a synthetic `{"ok": false, "code": "guardrail_blocked", "executed":
false}` observation without running the handler. A halt finishes the turn
gracefully (below). Status tools used while monitoring (`runtime_status`,
`task_inspect`, `account_read`, `market_quote`, `trade_record_read`,
`watch_list`, …) set `Tool.poller` and are exempt from no-progress detection;
their genuine failures still count. A completed mutation resets the failure
counters, because the next retry is a new experiment.

## Graceful limits

The round budget counts model turns. Calls proposed in a turn execute only
when another round follows it, so the budget warnings count the turns, the
current one included, whose tool calls will still run ("2 model rounds whose
tool calls will execute remain", then "the last model round whose tool calls
will execute"). The last budgeted turn of the final slice is never offered
tools: it is the final report described below, so no proposal is wasted.

When the round budget of an earlier slice is exhausted, Task Runs take another
continuation slice as before and run the carried calls there. When no slice
remains, or a guardrail halts, the loop closes any unexecuted proposals as
`tool_call_not_executed` (cancelling any linked approval), adds a final
runtime notice and makes one tool-less model call (the Hermes grace call). The model is told to report only verified results, name
unresolved or unverified operations without calling them successful, and give
next steps. The financial-truth rewrite in `model_runtime` still applies, and
any call the provider proposes anyway is ignored. If the model is unavailable
for this call, a short deterministic notice in the owner's language is used
instead of failing the Run. The reply is checkpointed as
`limit_exit` before it is returned, so a restart commits the same text without
another model call. It is committed with `exit_reason` (`tool_round_limit` or
`guardrail_halt`) and `reply_outcome: "limited"` in the Run metadata.

Outside a Task the Run is then `completed` so the owner sees the report, but its
work is not: every outcome consumer reads `lonora_db.runs.outcome_status`, which is
`limited` for such a Run. A legacy ticket goes to `waiting` (with the report and
its `exit_reason`) and can be started again, never to `done`; a delegating parent
or peer receives `<peer_outcome status='limited'>`; a collaboration participant is
recorded as failed with the exit reason, and a limited synthesis never completes
the collaboration.

Owner input that arrives at a limit is a new request: it supersedes unexecuted
proposals and starts one new bounded budget (`rounds` returns to zero and the
slice counter to one; `prior_attempt_rounds` keeps the total).

Owner steering and limits close only calls that never started
(`tool_call_superseded` / `tool_call_not_executed`). A non-read-only call whose
in-flight marker survived a restart may already have crossed its effect boundary,
so `close_pending` answers it as dispatch answers an interrupted call:
`tool_execution_uncertain`, with its route marked ambiguous for reconciliation and
any linked approval left in place.

## Task completion: nudges, then owner attention

A finite Task with declared steps that are not completed, and a continuous
Task answering in prose instead of saving a wait, receive at most two bounded
nudges (`stop_gates.py`). Plan revisions and owner input start a new review
epoch. When the nudges are spent, or a Task reaches its final limit, the loop
keeps the best held answer and hands it to the owner instead of failing the
Run:

- the answer is posted to the work thread as a pending input request
  (`kind: owner_attention`) and the Run becomes `waiting_input` with its
  checkpoint intact;
- the Task becomes `waiting` with `waiting_reason: owner_attention` and phase
  `needs_attention`, and `task.attention_required` raises an action-required
  `task_review` attention item;
- the message starts with the runtime's own account of what is unfinished, in
  the owner's language (the declared steps not completed yet, that no
  monitoring wait was saved, or that the work stopped at a limit or a
  repeating loop), followed by the held answer as the latest report, so a held
  answer that claims completion is never the owner's only report;
- the attention item carries `task_id` and the Task's `work_thread_id`, and
  agent live state reports `action_required` with
  `task_attention_required`;
- the owner's reply in the work thread resumes the same checkpoint. The Task
  controls work too: the snapshot offers `can_resume`, and `resume` or `revise`
  cancels the unanswered question and requeues the same Run; the loop then
  starts a new review epoch (a new budget when the limit was reached) and tells
  the model in a runtime notice that the owner resumed or revised the work.
  Pause and cancel work as for any waiting Task.

At a limit or a guardrail halt, a finite Task whose declared steps are all
recorded complete with evidence completes with the final report instead;
work without declared steps has nothing that proves completion and goes to
owner attention. `complete_run` still refuses incomplete steps and unsaved
continuous work, so unfinished work is never marked completed.

## Runtime notices

Provider adapters hoist every system message into one prefix, so runtime
nudges are never appended as mid-run `role=system` text. A notice (completion
check, empty answer, budget warning, guardrail guidance, final report request)
is attached to the latest tool result as `runtime_notice`, or appended as a
trailing `user` message with `context_origin="tool_observation"` and a
`<runtime_notice>` JSON body. Context governance keeps it bound to the block
before it, it never becomes the owner-request anchor, and the financial-truth
scanners do not treat it as a new owner request. An empty provider turn is not
kept as an empty assistant message.

## Model provider failures

A model turn whose every candidate failed does not fail the Run at once. A
transient failure schedules the same checkpoint again through the read-retry
worker release (`environment.retry.reason_code = "model_provider_retry"`) with
a growing backoff; a provider-proven context overflow tightens admission and
compacts before one bounded retry. After a failure streak the owner is told:
finite Task work waits for owner attention, a continuous Task keeps retrying
at the capped interval (with one `task_degraded` notification) and is held
only after hours of outage, and other Runs fail with the provider code. An
owner message that arrives during the failed turn clears the backoff. Nothing
executed is repeated. See `docs/provider-resilience.md`.

## Context compaction

Long Runs stay within their model's window through a persisted compaction view
that never rewrites the checkpoint: old tool results are pruned to their effect
identities and a stored-result reference, and only then is the middle
summarized. The routing frame re-reads unresolved operations, approvals and
watches from the database every turn. See `docs/context-engine.md`.
