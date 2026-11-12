Superseded by VISION.md

# Provider resilience and model flexibility

How a model request survives provider failures, and how an Agent's work
survives an outage that outlasts one request. The model still decides what to
do; this layer only decides which configured model answers and when to try
again. None of it repeats an external effect: a model request has none, every
executed tool call keeps its recorded result, and an interrupted call keeps its
in-flight marker for the existing replay and reconciliation rules
(`docs/tool-execution-runtime.md`).

## Failure taxonomy

Adapters turn every provider failure into one `ModelProviderError`
(`lonora_adapter_kit/model_errors.py`). Its `reason` drives recovery; its `code`
stays one of the stable codes Runs, Tasks and clients already read.

| Reason | Typical source | Code |
| --- | --- | --- |
| `auth` | 401, `authentication_error`, `invalid_api_key`, a 403 with invalid-key wording | `model_credentials_rejected` |
| `permission` | Anthropic `permission_error`, any other 403 without billing, content or invalid-key wording | `model_access_denied` |
| `billing` | 402, `insufficient_quota`, "credit balance", "exceeded your current quota" | `model_billing_exhausted` |
| `rate_limit` | 429, `rate_limit_error` | `model_rate_limited` |
| `overloaded` | 503/529, `overloaded_error`, overload wording on 429 | `model_provider_unavailable` |
| `server_error` | other 5xx, `api_error`, untyped stream error events | `model_provider_unavailable` |
| `timeout` | read/connect timeout, 408/504 | `model_provider_unavailable` |
| `connection` | transport errors, a stream that closed before its end marker | `model_provider_unavailable` |
| `context_overflow` / `payload_too_large` | "prompt is too long", `context_length_exceeded`, 413 | `context_limit_exceeded` |
| `model_not_found` | 404, `not_found_error`, "the model … does not exist" | `model_endpoint_unavailable` |
| `content_policy` | content filters, `refusal`/`content_filter` stops | `model_content_blocked` |
| `output_limit` | "max_tokens … > N, which is the maximum", "at most N completion tokens" | `model_request_rejected` |
| `truncated` | `max_tokens`/`length` stop with tool calls or no text | `model_output_truncated` |
| `format_error` | other 4xx | `model_request_rejected` |
| `invalid_response` | malformed body or stream | `model_response_invalid` |

Classification order: a decisive provider type or code, then the HTTP status
refined by the message, then message patterns. `Retry-After` (seconds or an
HTTP date), `retry-after-ms` and "try again in Ns" wording become `retry_after`
on transient reasons only. Provider message text is never stored on the error.

A reason read only from wording on a generic response (a plain 400/422, or an
untyped error event mid-stream) is marked `inferred`. It still selects the
recovery and allows fallback, but it never benches beyond a transient
cooldown: a fault in one request (a stale `tool_call_id` that "does not
exist", a parameter named `billing_id`) must not take a model or key offline
for every Agent. The patterns are narrow for the same reason: a missing model
needs the word "model" in the phrase, and bare "billing" or "authentication"
is not enough.

## No model configured is not an outage

`model_not_configured` means there is nothing to ask: no route, no backup, no model
the owner allowed, or no key for any of them. It is a state of the installation, not
a provider failure, and it is never shown as one.

- **A new installation answers.** When a text request has no candidate at all and a
  provider key exists, the router chooses a model once and records it as the unified
  route in `model_routing` (`lonora_providers/default_model.py`), so Settings show it
  and the owner changes it there like their own choice. Providers are taken in registry
  order; each one's own catalog is read (and stored), and the first family of
  `PREFERRED_FAMILIES` that catalog lists is taken: the exact id, else its newest dated
  snapshot. An id the provider does not list is never chosen, so a stale preference
  chooses nothing rather than a model that does not exist. Speech routes, a
  consultation's named models, and reads of the route (the model card, `model_list`)
  never choose. An owner's own route, backup or allowed model is never replaced, and
  custom routing is never filled in. A search that chose nothing is not repeated for
  60 seconds, and concurrent first requests choose once.
- **Nothing to choose.** No key, or no listed family: the Run fails with
  `model_not_configured`. The Web error card then reads «لم يُضبط نموذج بعد» with the
  existing notice («اربط مزودًا واختر نموذجًا…») and one action that opens the model
  settings, where the provider keys are; Mobile shows the same state in its Run line.
  The outage card («النموذج غير متاح حاليًا») is for a provider that could not be reached.
- **A provider that cannot be asked** while the default is being chosen is passed over
  for the next one; if none gives a model, its own classified failure is raised, so an
  outage backs off and retries like any other, and a rejected key reads as a rejected
  key.
- **What failed is answered.** When the owner saves a provider key, the global routes,
  the backups or the allowed models, and a conversation now has a model (with a key and
  no routing the default is chosen at that moment), every conversational reply that
  failed with `model_not_configured` in the last 48 hours and was not retried yet is
  queued again
  (`run_retry.retry_unconfigured`), oldest message first, under the same rules as the
  owner's own retry (never a Run with a financial operation or one that started other
  work). The owner no longer has to find and tap each card: before, each failed message
  needed its own tap, and a message whose retry had failed again stayed unanswered. A
  failure the conversation has moved past (a later message there was answered or is
  being answered) stays history, and so does an older one: an instruction from days ago
  is not carried out because a key was saved. A reply of an agent that holds a signed
  grant in force is never queued this way: a late instruction to it could move money
  without a card, so it waits for the owner's own retry.
- **Installing.** `scripts/install.sh` writes no provider key; keys arrive through
  Settings or the environment (`LONORA_<PROVIDER>_API_KEY`). Whichever way they arrive,
  the first request chooses.

## One request: retries, fallback and cooldown

`GlobalModelRouter.complete` tries an ordered, de-duplicated chain of at most
six candidates:

1. the model the Run was started on (a helper's chosen model, see below);
2. the Agent's own primary model (the owner's Fixed choice, or the Agent's own in
   Automatic);
3. the global route for the capability;
4. the Agent's fallbacks;
5. the global backups (`model_backups`);
6. for an Automatic Agent, the other models the owner allowed (`model_allowed`).

Each candidate is admitted against its own window (unchanged from
`docs/context-engine.md`). Per reason (`lonora_providers/resilience.py`):

| Reason | Same-provider retries (another candidate left / alone) | Then | Bench |
| --- | --- | --- | --- |
| rate limit | 0 / 2 | fall back | until `Retry-After`, else 30 s doubling |
| overloaded, server error | 1 / 2 | fall back | 20 s doubling |
| connection | 1 / 2 | fall back | 15 s doubling |
| timeout | 0 / 1 | fall back | 30 s doubling |
| auth, billing | none | fall back | 15 min, every model of that key (credential fingerprint) |
| permission, model not found | none | fall back | 15 min, that model for that key only |
| content policy, format, invalid response | none (invalid: 1) | fall back | none |
| context overflow | none | raised to the Run (compact and retry) | none |

Benches rest only on decisive evidence (a status such as 401, 402, 403 or
404, or a typed provider code); an `inferred` reason benches nothing unless
it is transient. A 403 that only refuses one model (Anthropic
`permission_error`, "does not have access to this model") benches that model
for that key, so an Agent preference pointing at a model the key cannot use
never takes the provider offline for other Agents or other models.

Waits use jittered exponential backoff (1 s, 2 s, … capped at 8 s, plus up to
half again as jitter) or the provider's `Retry-After` when it is at most 20 s.
A longer declared wait is not slept through: the candidate is benched until
then and the Run's own backoff takes over. A benched candidate is skipped by
later requests in the same process; a replaced API key has a new fingerprint
and is tried at once. The bench is process-local and short by design; it is a
circuit breaker, not configuration.

When every candidate fails, a transient failure is reported in preference to
a permanent one, carrying the shortest wait after which a candidate leaves its
bench; an unconfigured backup never hides the primary's real failure. A reply
that needed recovery records `provider_recovery` (for example
`retried_overloaded`, `output_boosted`) and `route_failures` in its provider
metadata.

## Output budget and truncation

The default `output_tokens` is 16,384. Each request asks for that, bounded by
the model's documented maximum (the catalog's `maximum_output_tokens`, which
the Anthropic Models API now provides together with the window, else a family
table in `model_windows.py`), by a quarter of the window, and by 8,192 when no
maximum is known. Requests without streaming stay at or below 16,384.

Adapters read the stop reason before trusting any tool input:

- `max_tokens`/`length` with tool calls, or with no text, raises `truncated`.
  Incomplete tool JSON is never parsed into a call. The router retries once
  with a larger budget (double, at least 8,192, within the model maximum and
  the window left after the input), then falls back.
- A cut-off text answer is retried once the same way; if it is still cut off
  it is returned with `output_truncated: true` rather than failing the turn.
- A rejected budget (`output_limit`) is retried once with the provider's stated
  maximum (or half), which is remembered for that model in the process.
- `refusal`/`content_filter` stops raise `content_policy`.

## A Run that outlasts the router

`lonora_agent/model_recovery.py`, on the fenced Run checkpoint
(`state["model_recovery"]`):

- **Context overflow proven by the provider.** The Run's admission scale is
  multiplied by 0.7 (floor 0.3, at most three times), the context engine
  compacts against the tightened limits and the turn is retried at once.
  Further turns of the Run keep the scale.
- **Transient failure.** The same checkpoint is scheduled again through the
  existing worker release: `environment.retry = {not_before, reason_code:
  "model_provider_retry", code, attempt}`, the Run returns to `queued`, and the
  claimant skips it until the deadline. Owner input clears the deadline, as it
  does for read retries, including a message that arrives while the failed
  turn is still being retried inside the router (it is stored as steering,
  and the release then drops the deadline so the message is answered at once;
  the failure streak is kept). The partial reply preview of the failed turn is
  withdrawn (`run.reply_committed` with phase `discarded`), and
  `run.retry_scheduled` carries the reason and code. The wait grows from 10 s
  (conversation, capped at 60 s) or 30 s (work, capped at 15 min), with jitter,
  and never undercuts the provider's or bench's stated wait.
- **Who waits decides the profile.** A conversation Run, and a subagent it
  delegated (the conversation waits for its result), uses the conversation
  profile; the root of the delegation chain is followed through
  `parent_run_id`. A subagent of Task or background work uses the work profile.
- **Escalation.** After 3 consecutive transient failures of a conversation Run,
  it fails with the provider's code, which the owner sees in the chat. After 6
  for background or finite Task work, Task Runs wait for owner attention
  (`task.attention_required`, reason `model_unavailable`), resumable from the
  same checkpoint with a fresh streak; other work Runs fail with the code. A
  successful model turn resets the streak. The failed turn never counts as a
  round.
- **Continuous Tasks keep monitoring.** A continuous Task is not held at the
  streak threshold: the owner gets one `task.degraded` event (attention code
  `task_degraded`, importance `important_change`, superseded once the Run
  recovers or the Task stops) and the Run keeps retrying at the capped 15-minute
  interval. It waits for owner attention only once the outage has lasted 12
  hours, or at once for a non-transient reason (rejected key, billing, access).
- **Task recovery.** If a Task Run does fail with `model_provider_unavailable`
  or `model_rate_limited`, a continuous Task (or any Task in automatic retry
  mode) retries automatically within its attempt limit, but only when every
  call without a result is a read or a checkpoint. An unresolved financial call
  (even one with no journal row yet) or any other mutation waits for the owner
  or for reconciliation; the automatic path never resends it.
- **Status.** The agent live state projects a model backoff as its own
  `runtime_waits` kind, `model_retry` (reason `model_provider_retry`), distinct
  from a tool `read_retry`. Clients show the owner-visible codes
  (`model_billing_exhausted`, `model_content_blocked`, `model_output_truncated`,
  `model_access_denied`, ...) in English and Arabic.

## Choosing a model per agent (W15-10)

The owner picks a model per agent, or lets Lonora choose, from chat or from the agent's
settings, on Web and Mobile. Choosing a model never grants authority: permissions,
approvals and every execution boundary stay the agent's whatever model answers. A switch
changes only the agent's model record; tool results, memory, Tasks, grants, uncertain
operations and the Run checkpoint are untouched, nothing is repeated, and the next model
turn simply asks the new model (the router reads the record on every request).

### The record

`GET/PUT /api/agents/{agent_id}/model` stores one record per agent, owner-scoped, in
`ln_settings` under `agent-model:<sha256(owner:agent)>` (no migration):

| Field | Meaning |
| --- | --- |
| `mode` | `automatic`: Lonora chooses; the agent starts on the owner's default model and may switch itself among the allowed models. `fixed`: the owner chose one model; only the owner changes it. |
| `preference` | `{primary, fallbacks (≤3)}`: in Automatic, the agent's own current choice (or none) |
| `chosen_by`, `chosen_by_agent_id` | `owner` (settings or a card) or `agent` (`model_request`), and the agent that made a switch; none until anyone chose |
| `previous` | The mode and models before the last change (what Undo restores, with who had chosen them) |
| `revision`, `changed_at` | Optimistic concurrency (`expected_revision`) and when it changed |

A record written before modes existed reads as Fixed when it has a primary (the owner
chose it through the E4 API) and Automatic otherwise. The same choice again changes
nothing (no revision, no event, and no card ends). A `PUT` that omits `fallbacks` keeps
the agent's current fallbacks behind the new primary; an explicit list replaces them.
Choosing Automatic sends the agent back to the owner's default model: on Web and Mobile
an Automatic agent on a model someone set offers "Back to your default model", and
choosing Automatic again while already Automatic changes nothing. Every change emits
`agent.model.updated` with the mode,
model, who chose it and how (`owner_settings`, `model_request`, `owner_card`,
`owner_undo`). `GET …/model/summary` is what the model card shows: the record, the model
answering now, the allowed models, the models a Fixed choice can pick (text models in the
catalogs of providers with a key) and this agent's usage over 30 days.

### The allowed list

The models an agent may choose on its own are the owner's global text routes and backups
plus the models the owner added (`model_allowed`, at most 20): `GET/PUT
/api/settings/models/allowed` returns `{routed, added}`, and the Web Model settings lists
them with Add and Remove. The routing chain, in order: the Run's own model (a helper's
chosen model), the agent's primary, the global route, the agent's fallbacks, the global
backups, then, for an Automatic agent only, the owner's added models. A Fixed agent never
falls back on the additions; a request without an agent (an in-run summary) keeps the
global routes.

### `model_list` and `model_request`

`model_list` (read-only) gives the agent the facts it needs before it switches: its mode,
who chose, the model answering now, the allowed models as provider, exact id and name,
and the connected providers. With `query` ("Opus", "gpt-5") it also returns up to six
catalog entries of the connected providers that share the most words with the query,
allowed ones first among equals, each marked `allowed`. `agent_id` reads another of the
owner's agents (the model choice is not private memory).

`model_request` (toolset `intelligence`, long-tail, replay-safe, not available to
helpers) takes `model` (or none: back to the owner's default), `fixed` (`true`: keep this
model, only the owner changes it; `false`: Lonora may switch again; omitted: the current
mode stays, so a Fixed agent stays Fixed) and `agent_id` (Lonora only, for another agent).

- **The agent's own switch** applies at once: to itself, while it is and stays Automatic,
  to an allowed model, in any Run.
- **A change the owner asked for** applies at once only when the server can tie it to the
  owner's words: the Run answers an owner message (a `user` or `group` trigger) and that
  message, or one the owner added while the Run worked, names the requested model (its id,
  its catalog name, or a distinctive word of either such as "Opus"; words many names
  share such as "pro", "flash" or a vendor name do not count). That is how a Fixed agent
  changes model or Lonora sets another agent's model from chat. The event records the
  owner's message (`source_message_id`); the record says the agent set it (`chosen_by:
  agent`).
- **Everything else** raises an `agent_model` owner card (`docs/owner-actions.md`): a
  model outside the allowed list, always, even when the owner named it (confirming adds it
  to the list, so it is one tap once); a change to an agent the owner fixed, a change to
  another agent or a mode change that the owner's words do not name (an unrelated chat
  message, text the agent read on a page or from a tool). Nothing changes until the tap,
  and a repeated request returns the card already shown.
- A provider without a key is `model_provider_not_connected`; a model no connected
  catalog lists is `model_not_in_catalog`, with the `closest` real entries to retry with
  (a guess such as `claude-opus` finds the exact Opus ids); another agent's model from
  anyone but Lonora is `model_request_agent_forbidden`. At most three switches apply per
  Run (`model_switch_limit`).
- Every switch that applies raises an `agent_model_changed` card with Undo in the
  conversation. A newer switch replaces it and ends the pending `agent_model` requests
  about the same agent (`model_changed_again`), so a later tap cannot override the newer
  choice. Undo restores the earlier mode and models with who had chosen them.

### Helpers and second opinions

`subagent_spawn(task, model)` starts a temporary helper on one of the allowed models
(otherwise `subagent_model_not_allowed`). The model is stored in the helper Run's
metadata, reaches its `ToolContext.run_model` at dispatch, and leads the router chain,
with the agent's own chain behind it. `consult_model` asks one of the agent's routed
models or any allowed model other than the one answering. Both record usage as before.

### Usage per agent (owner decision D4)

There is no spending cap. `GET /api/usage/agents?days=30` sums the recorded requests per
agent and per model (tokens in, out and cached, requests, last use); the Web usage
settings list it per agent and each agent's model card shows its own line. Budget
enforcement is not planned (D4).

## Second opinion: `consult_model`

A read-only tool (intelligence chapter) that sends a bounded evidence pack the
Agent writes (question ≤ 4,000 characters, evidence ≤ 24,000) to another
allowed model: one named by the Agent from its candidates or the owner's allowed
list, or the first candidate that is not the model it is using. The consulted model gets no
tools, no conversation and no authority; markup in the pack is made inert.
The critique (≤ 8,000 characters) returns as an advisory observation. There is
no per-Run budget (mandate P1): the Agent decides how often a second opinion is
worth a model request. Usage is recorded with `purpose: consult_model`.
Nothing waits for agreement and nothing executes on its advice.

## Limits and follow-ups

- Benches, learned output limits and same-provider retries are per process;
  several workers may each probe a failing provider once.
- A `task_degraded` notification is in-app only (important changes are not
  sent to external channels) and offers no action beyond opening the Agent's
  conversation.
- Like the per-Agent approval preference, the model record is not removed when
  the Agent is deleted (it is unreachable afterwards). A typed column on
  `ln_agents` would need a migration and is left as a follow-up.
- A change the owner asked for applies at once only when the owner's words name the
  model; a name the server does not recognize (an Arabic transliteration such as
  "أوبس") falls back to the one-tap card. The switch is non-financial, visible and has
  Undo.
- The Fixed picker lists every discovered model of a connected provider; catalogs
  that do not report capabilities (OpenAI) include non-chat models.
- Reasoning/thinking controls (effort, thinking budgets) are not configured
  per adapter.
- There is no spend cap (owner decision D4); usage is shown per agent.
  `model_request` is bounded per Run only.
- The output family table must follow provider documentation as models change.

Attribution: the taxonomy and classification order adapt Hermes Agent
`agent/error_classifier.py`, the bench adapts `agent/fallback_cooldown.py`, and
the retry delays adapt `agent/retry_utils.py` (see `THIRD_PARTY_NOTICES.md`).
