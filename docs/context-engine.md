Superseded by VISION.md

# Context engine

How a Run's model request is sized, compacted and labelled. The model decides
what to do; this layer only decides what it can see within its model's window,
and says so whenever something is left out or condensed.

## Budgets come from the model's window

`lonora_providers.context.context_limits` derives one request's budget from the
resolved model:

- **Window.** The provider catalog's `context_window` wins. The direct Anthropic,
  OpenAI, DeepSeek and Z.ai listings do not report one, so a conservative family
  table (`lonora_providers/model_windows.py`) fills the gap. A key matches only at
  an id boundary (end, `-`, `:` or `@`), longest key first: `gpt-4` covers
  `gpt-4-0613` but not `gpt-4.5-preview` (its own 128k entry), and `glm-4.5` does
  not claim the 64k `glm-4.5v`. Otherwise capacity is reported as `unknown` and
  the policy's `maximum_input_tokens` (default 64,000) applies. A wrong table
  entry still mis-sizes requests, so the table must follow provider docs.
- **Admitted input** = window − output reservation − safety margin. The output
  reservation is `output_tokens` (default 16,384), at most a quarter of the
  window and at most the model's documented maximum output (the catalog's, else
  the family output table; 8,192 when neither knows the model). The margin is
  `safety_tokens` (default 1,024) or 2% of the window, whichever is larger.
- **Provider-proven overflow.** When a provider still rejects a request as too
  long, the Run's admission scale (`state["model_recovery"]["input_scale"]`)
  shrinks the admitted input by 0.7 per rejection (floor 0.3), and the turn is
  compacted and retried; see `docs/provider-resilience.md`.
- **Owner caps.** `input_ceiling_tokens` optionally caps admitted input for every
  model (cost or latency control). A setting written before that field existed
  (no `input_ceiling_tokens` key) with a non-default `maximum_input_tokens` keeps
  it as the ceiling, since it used to cap every model; an explicit `null` opts
  out. `compaction_ratio` (default 0.75) sets when in-run compaction starts.
- **Characters** are only a transport safety net: 6 characters per admitted
  token, never below the old 120,000. A 200k-token model is no longer held to
  a 120,000-character request.

`GlobalModelRouter.context_limits(capability)` reports the limits of the model
the router tries first (the Agent's own preferred model when it has one). Every attempt, fallbacks included, is still admitted
separately against its own window, so a smaller fallback model gets a request
rebuilt for its size. Diagnostics on each usage row record the estimator, the
capacity source, the admitted limit, the transport limit and how many omission
notices the request carried.

Estimates use the verified offline tokenizer cache when present (see
`docs/context-budgeting.md`) and UTF-8 bytes otherwise. Bytes
overestimate tokens, so a missing cache compacts and sheds earlier.

## Admission degrades instead of failing

`govern_context` (adapter-kit) admits, in order:

1. First-party system messages and the owner's newest request (mandatory).
2. The newest exchange, with oversized result bodies reduced to their effect
   identities in the working copy (never dropped, never split).
3. Optional first-party blocks, each whole, in message order: the capability
   inventory, recorded decisions and theses
   (`lonora_recorded_decisions`), operational observations
   (`lonora_operational_observations`), the domain policy chapters and the
   visual observation catalog (system role, marked `runtime_context`). Server
   enforcement never depends on them.
4. The leading context-data message, shedding whole sections from the lowest
   priority up. An `omitted_sections` section names what was shed.
5. Older history, newest first, as complete blocks.

Each run of history left out is replaced in place by a `<context_omitted>`
notice (message and tool-exchange counts) in the user role, and shed blocks are
listed as `omitted_guidance` with the tools that reread them, so the model knows
what it does not see. `context_limit_exceeded` now only happens when the
mandatory first-party system text (policy, owner instructions, the
routing frame) and the newest request alone do not fit, or the newest tool call
cannot be represented.

OpenAI-compatible adapters join adjacent plain user turns (for example the
context data and the owner's request) into one wire message, as the Anthropic
adapter already merges same-role turns, because some endpoints reject
successive user messages.

## Trust separation

The system role carries only first-party policy, the owner's instructions,
identity, the agent binding, server-derived records (as optional blocks
decisions and operational failures; the skill catalog,
wake details) and the routing frame.

Two refinements keep model-written text out of it. `wake_context` keeps a Run's
prompt in the system role only for server-authored wakes (`broker_event`,
`follow_up`); for every other trigger (a subagent's task written by
its parent model, a peer request, a Task or ticket title, a routine or watch prompt
an agent saved, an owner prompt) it names the trigger only, and the prompt arrives
as the user-role turn. The permission frame shows restrictions as structured fields;
an agent-written restriction reason never enters it.

Everything model-authored or untrusted travels in **one user-role context
message** directly after the system messages, as labelled sections:

| Section | Source / trust | Priority |
| --- | --- | --- |
| `history_gap` | lonora_runtime / first_party_runtime | 100 |
| `quoted_reply` | conversation_quote | 95 |
| `attachments` | owner_attachments / owner_supplied_untrusted | 92 |
| `skill` (one per active procedure) | skill:&lt;id&gt; / bundled_first_party, owner_supplied, legacy_owner_skill, agent_authored, external_import | 90 |
| `history_summary` | conversation_summary / model_summary | 85 |
| `memory` | agent_memory / mutable_untrusted | 80 |
| `recent_tool_evidence` | earlier_runs / historical_observation | 55 |
| `scratchpad` | agent_scratchpad / agent_authored | 50 |
| `recent_external_evidence` | earlier_runs_retrieved / retrieved_untrusted | 45 |
| `recalled_evidence` | memory_recall / retrieved_untrusted | 40 |

Every body passes through `escape_context_text`
(`lonora_adapter_kit/context_sections.py`), so content cannot close its own
section or the wrapper. That also makes the format parseable, which is what lets
admission shed sections by priority. The skill catalog stays in the system role
and names the active procedures; their bodies are context data with their real
provenance (an external import or an Agent-authored package is never presented
as owner-supplied; see `docs/agent-memory-and-recall.md`). When
owner steering changes the active skills, `refresh_skill_context` swaps the
skill sections in place. Attachment text appended to an owner steering message
uses the same escaping helper.

## In-run compaction

Adapted from Hermes Agent `agent/context_compressor.py` (MIT, see
`THIRD_PARTY_NOTICES.md`) for Lonora's durable checkpoint
(`lonora_agent/context_engine.py`).

**The checkpoint is never rewritten.** `messages` in `RunRow.execution_state`
keep every original tool result, so the financial truth gates, crash recovery,
receipts, inflight markers and task evidence keep reading the complete record.
Compaction is a persisted *view* in `execution_state["context_compaction"]`,
applied to each model request by `model_turn(context_view=...)`.

Before each model turn (and before the final tool-less report at a limit) the
loop estimates the request under the current view: the fixed part (system
messages, context data, schemas, capability inventory and policy chapters) and
the transcript. It compacts when the transcript exceeds the room left under
`compaction_ratio × admitted input`, and in any case only once the transcript is
larger than twice the protected tail, so a large fixed prefix (for example under
the UTF-8 byte estimate) cannot trigger a summary on every turn:

1. **Prune (deterministic).** Tool results longer than 1,200 characters that are
   older than the protected tail (the newest blocks within 25% of the budget,
   at least two) are replaced by a placeholder: tool name, arguments, the
   observation time, `ok`, effect identities found anywhere in the result
   (`operation_id`, `approval_id`, `broker_reference`, order/position/deal ids,
   task/watch ids, `status`, `code`, …), an ambiguous result's
   "reconcile before any resend" recovery, and a `result_ref`. Full results of
   at least 1,500 characters are stored first in the existing tool-result
   artifact store, so the model can `artifact_read` them instead of calling the
   tool again. A failed store, including an operating-system error such as a
   full disk, is reported on the placeholder (`result_storage_error`), never as
   a failed effect. A pruned `skill_view` says `reload_with: skill_view`. A
   pruned financial call, or any result carrying an `operation_id`,
   `broker_reference` or `approval_id`, says `read_record_do_not_repeat` (with
   `read_with: artifact_read` or `trade_record_read`, and
   `effect_already_executed` when a confirmed outcome is recorded); only plain
   reads say `repeat_read_if_needed`.
2. **Summarize (only if the transcript is still above its low-water mark, 80%
   of its trigger).**
   The span between the context data and the protected tail is summarized by
   the router's `background` model with
   `resources/prompts/run_context_summary.md` (goal, owner constraints,
   progress with times, decisions, open operations and commitments with exact
   identifiers, key evidence with timestamps, unverified items, next steps).
   Large spans are summarized in chunks, each updating the previous summary.
   The record is checkpointed after every chunk, so a restart reuses it instead
   of paying again. If the summary model fails, a deterministic digest of the
   span (owner and agent excerpts, every tool call with outcome, identities and
   time) is used instead. The Run never fails because of compaction:
   `compact_for_turn` lets only fencing errors (`stale_lease`,
   `skill_continuation_unavailable`) through; any other failure is logged and
   the turn proceeds with the current persisted view, which admission then
   degrades if needed.

Boundaries are always complete blocks, so a tool call is never separated from
its results. The owner's request at summary time stays verbatim in front of the
summary. Summarizer input and the digest label speakers truthfully (`speaker`):
only an owner-authored conversation turn is `owner`; another Agent's message in a
shared thread (`[Peer …]`) is `peer_agent`, and in a subagent or peer Run the
conversation input is `requesting_agent`, so injected peer or delegated text can
never be laundered into "the owner asked". A peer's message is never the kept
request, and every pseudo-attribute (a provider-emitted tool name included) is
escaped, so a crafted name cannot close its tag and forge an owner turn. The summary is a `<run_context_summary>` user-role message that says it
replaced earlier messages, is model-authored, is not authority or live state,
and how to reread exact results. Its text is escaped. Record indexes and
fingerprints count from after the context data, so refreshed context data never
shifts them; a transcript that no longer matches the fingerprint drops the
summary instead of half-applying it. Hysteresis (prune boundaries move only at
a trigger, and compaction targets the low-water mark) keeps the request prefix
stable between compactions for provider prompt caching. Each compaction emits a
`run.context_compacted` event with counts only.

Result timestamps come from `execution_state["tool_observed_at"]`, written when
each result enters the transcript.

## Protected operational state

The routing frame (system role, rebuilt from the database before every model
turn) carries `<protected_operational_state>` when any exists
(`lonora_db/operational_state.py`): this agent's live journal operations in the
execution lifecycle of `lonora_contracts.trading` — unresolved ones
(`reserved` with `await_outcome_never_resend`; `submitted`/`ambiguous` with
`reconcile_before_any_resend` and the scoped block they impose on new risk for
their symbol or ticket), and for 24 hours the settled-but-not-plain ones
(`confirmed` with state verification pending, and `resolved` with its
resolution source and outcome and `broker_confirmed: false`) — pending approvals with their requested symbol/side/volume, and enabled
watches. Grants, waits and tasks were already in `live_agent_state`. Owner
restrictions and monetary limits are not repeated: the permission frame in the
same routing frame re-reads them every turn. Live risk usage (daily loss, open
risk) needs a broker snapshot and is checked at the execution boundary, not
projected per turn. These records supersede any summary, recalled evidence or
earlier message; no summary is trusted for them.

## Cross-turn tool evidence

A new Run gets `recent_tool_evidence` (`context/run_evidence.py`): up to 12
entries (8,000 characters) from this agent's last four finished Runs in the same
thread. Successful observations and every financial effect outcome are kept;
discovery, skill bodies, waits and self-notes are skipped; the same call keeps
only its newest observation; entries that mention terms of the new request rank
first. Each entry has the tool, arguments, `observed_at` (or the Run's last
update, labelled `run_last_updated`), identities, any `result_ref` and a short
preview. The section is labelled historical, not live market or broker truth.
Results of tools that return third-party, other-model or stored content
(`web_*`, `mcp_*`, `search_*`, `artifact_read`, `workspace_read`,
`workspace_inspect`, `workspace_execute`, `skill_repository_inspect`,
`session_search`, `economic_calendar_read`, `consult_model`, `subagent_inspect`,
`collaboration_inspect`) go to a separate `recent_external_evidence` section (4,000 characters) labelled
`retrieved_untrusted`, like recalled evidence, so page text that was a tool
result in its own Run is never promoted to a more trusted label. A registry test
makes every catalog tool take a side, so a new tool cannot silently default to the
first-party label.

## The summary/window dark zone

A new Run loads the newest 100 unsummarized messages. When background
summarization lags, older unsummarized messages used to be neither summarized
nor loaded nor recallable. Now `history_gap` reports them (count, sequence and
time range) in a first-party section, and conversation recall
(`ConversationRecallScope.unloaded_through`) can retrieve from them, still
excluding everything already in the loaded window. The cross-turn summary prompt
also keeps unresolved operations and promises to the owner.

## Compatibility and limits

- New checkpoints contain `runtime_context` messages and the compaction record.
  An older release rejects them as `run_checkpoint_invalid` (fails closed; it
  never replays an effect). Older checkpoints load unchanged; a refresh after
  steering moves their skill bodies out of the system message.
- Estimates remain estimates. A provider context-overflow error tightens the
  Run's admission and compacts before one bounded retry
  (`docs/provider-resilience.md`).
- The family window table must be kept current as providers change models.
- The checkpoint itself still grows with the full transcript; only requests are
  bounded.
