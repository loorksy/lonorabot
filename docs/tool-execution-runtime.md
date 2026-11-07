# Tool execution runtime

`lonora_agent.tool_loop` drives every Run: it executes the assistant's tool
calls, checkpoints each result, merges owner steering and decides when a turn
ends. This page describes how a tool-call block is executed and how the loop
ends at a limit. The model still decides what to call and when to stop; the
runtime only enables concurrency and enforces effect, authority and budget
boundaries.

| Module | Responsibility |
| --- | --- |
| `tool_loop.py` | Orchestration, checkpoints, steering, waits, limits |
| `tool_dispatch.py` | One call under the receipt, reconciliation and crash-replay rules |
| `tool_intent.py` | Per-call intent markers and closing of unexecuted proposals |
| `tool_batch.py` | Ordered parallel/serial segments and bounded concurrent execution |
| `tool_guardrails.py` | Checkpointed loop guardrail controller |
| `runtime_notices.py` | Placement and wording of runtime notices |
| `stop_gates.py` | Bounded completion nudges for Task work |
| `lonora_tools.base.Tool` | `parallel_safe`, `poller`, `timeout_seconds` contract flags |

## Concurrent reads, serial effects

Each assistant tool-call block is split into ordered segments (adapted from
Hermes Agent `agent/tool_dispatch_helpers.py::_plan_tool_batch_segments`, MIT).
A call joins a parallel segment only when the server registry says it is
read-only, not financial and `parallel_safe`. Contiguous admissible calls run
together with `asyncio.gather` under a semaphore of four
(`MAXIMUM_PARALLEL_TOOLS`); a lone read stays serial. Every other call is a
barrier executed alone: mutations, financial operations, waits
(`wait_for_input`, `task_wait`), `group_silence`, the skill instruction tools
(they change the instruction authority used by later calls) and unknown names.
A later call never crosses an earlier barrier. `tool_environment` reports each
tool's class as `batch_execution` (`parallel_read` or `serial`).

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

## Dispatch deadlines

`ToolRegistry.execute` wraps the handler in a per-tool deadline:
`Tool.timeout_seconds`, or 45 s for reads and 90 s for mutations by default.
Long-running tools declare their own (`web_browse` 60 s, `mcp_tools` 75 s,
`mcp_execute` and `market_strategy_research` 120 s). Financial tools are never
wrapped and the registry rejects a deadline on one: they own broker deadlines,
and cancelling after send would create ambiguity. A read deadline is the
existing `tool_read_timeout` observation (with the normal bounded read retry);
an interrupted mutation is `tool_execution_uncertain`.

## Loop guardrails

The guardrail controller (adapted from Hermes Agent `agent/tool_guardrails.py`,
MIT) replaces the old `repeated_tool_call` Run failure, which fired after the
effect had already run. Its JSON state lives in the Run checkpoint
(`tool_guardrails`), so restarts and compute slices cannot reset it; real owner
input and external wakes start a new epoch.

| Signal | Warn | Block / halt |
| --- | --- | --- |
| Same call, same arguments, failing | 2nd failure | route exhaustion (existing, 3 failures) |
| Same tool failing with any arguments | 3rd failure | halt at 8 |
| Identical read returning an identical result | 2nd repeat | block at 5, halt after 2 ignored blocks |
| Identical consecutive call and result (any non-poller tool) | 3rd | halt at 5 |
| Identical A/B… cycle of 2–4 calls | 3 laps | halt at 5 laps |

A warning is attached to that tool result as a `runtime_notice`. A block
returns a synthetic `{"ok": false, "code": "guardrail_blocked", "executed":
false}` observation without running the handler. A halt finishes the turn
gracefully (below). Status tools used while monitoring (`runtime_status`,
`task_inspect`, `account_read`, `market_quote`, `trade_record_read`,
`watch_list`, …) set `Tool.poller` and are exempt from no-progress detection;
their genuine failures still count. A completed mutation resets the failure
counters, because the next retry is a new experiment.

## Graceful limits

When the round budget is exhausted, Task Runs first take another continuation
slice as before. When no slice remains, or a guardrail halts, the loop closes
unexecuted proposals as `tool_call_not_executed` (cancelling any linked
approval), adds a final runtime notice and makes one tool-less model call (the
Hermes grace call). The model is told to report only verified results, name
unresolved or unverified operations without calling them successful, and give
next steps. The financial-truth rewrite in `model_runtime` still applies, and
any call the provider proposes anyway is ignored. If the model is unavailable
for this call, a short deterministic notice in the owner's language is used
instead of failing the Run. The reply is checkpointed as
`limit_exit` before it is returned, so a restart commits the same text without
another model call. It is committed with `exit_reason` (`tool_round_limit` or
`guardrail_halt`) in the Run metadata.

Owner input that arrives at a limit is a new request: it supersedes unexecuted
proposals and starts one new bounded budget (`rounds` returns to zero and the
slice counter to one; `prior_attempt_rounds` keeps the total).

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
- the owner's reply resumes the same checkpoint; pause, revise and cancel work
  as for any waiting Task.

`complete_run` still refuses incomplete steps and unsaved continuous work, so
unfinished work is never marked completed.

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
