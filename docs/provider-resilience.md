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
| `auth` | 401/403, `authentication_error` | `model_credentials_rejected` |
| `billing` | 402, `insufficient_quota`, "credit balance" | `model_billing_exhausted` |
| `rate_limit` | 429, `rate_limit_error` | `model_rate_limited` |
| `overloaded` | 503/529, `overloaded_error`, overload wording on 429 | `model_provider_unavailable` |
| `server_error` | other 5xx, `api_error`, untyped stream error events | `model_provider_unavailable` |
| `timeout` | read/connect timeout, 408/504 | `model_provider_unavailable` |
| `connection` | transport errors, a stream that closed before its end marker | `model_provider_unavailable` |
| `context_overflow` / `payload_too_large` | "prompt is too long", `context_length_exceeded`, 413 | `context_limit_exceeded` |
| `model_not_found` | 404, `not_found_error` | `model_endpoint_unavailable` |
| `content_policy` | content filters, `refusal`/`content_filter` stops | `model_content_blocked` |
| `output_limit` | "max_tokens … > N, which is the maximum", "at most N completion tokens" | `model_request_rejected` |
| `truncated` | `max_tokens`/`length` stop with tool calls or no text | `model_output_truncated` |
| `format_error` | other 4xx | `model_request_rejected` |
| `invalid_response` | malformed body or stream | `model_response_invalid` |

Classification order: a decisive provider type or code, then the HTTP status
refined by the message, then message patterns. `Retry-After` (seconds or an
HTTP date), `retry-after-ms` and "try again in Ns" wording become `retry_after`
on transient reasons only. Provider message text is never stored on the error.

## One request: retries, fallback and cooldown

`GlobalModelRouter.complete` tries an ordered, de-duplicated chain of at most
six candidates:

1. the Agent's own primary model (owner-chosen, see below);
2. the global route for the capability;
3. the Agent's fallbacks;
4. the global backups (`model_backups`).

Each candidate is admitted against its own window (unchanged from
`docs/context-engine.md`). Per reason (`lonora_providers/resilience.py`):

| Reason | Same-provider retries (another candidate left / alone) | Then | Bench |
| --- | --- | --- | --- |
| rate limit | 0 / 2 | fall back | until `Retry-After`, else 30 s doubling |
| overloaded, server error | 1 / 2 | fall back | 20 s doubling |
| connection | 1 / 2 | fall back | 15 s doubling |
| timeout | 0 / 1 | fall back | 30 s doubling |
| auth, billing | none | fall back | 15 min, keyed by credential fingerprint |
| model not found | none | fall back | 15 min |
| content policy, format, invalid response | none (invalid: 1) | fall back | none |
| context overflow | none | raised to the Run (compact and retry) | none |

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
  does for read retries. The partial reply preview of the failed turn is
  withdrawn (`run.reply_committed` with phase `discarded`), and
  `run.retry_scheduled` carries the reason and code. The wait grows from 10 s
  (conversation, capped at 60 s) or 30 s (work, capped at 15 min), with jitter,
  and never undercuts the provider's or bench's stated wait.
- **Escalation.** After 3 consecutive transient failures of a conversation Run,
  it fails with the provider's code, which the owner sees in the chat. After 6
  for background or Task work, Task Runs wait for owner attention
  (`task.attention_required`, reason `model_unavailable`), resumable from the
  same checkpoint with a fresh streak; other work Runs fail with the code. A
  successful model turn resets the streak. The failed turn never counts as a
  round.
- **Task recovery.** If a Task Run does fail with `model_provider_unavailable`
  or `model_rate_limited` and no call is unresolved, a continuous Task (or any
  Task in automatic retry mode) retries automatically within its attempt limit
  instead of waiting for the owner.

## Per-Agent model preference

`GET/PUT /api/agents/{agent_id}/model` stores
`{primary, fallbacks (≤3), expected_revision}` for one Agent, owner-scoped, in
`ln_settings` under `agent-model:<sha256(owner:agent)>`, the same storage
pattern as the per-Agent approval preference, so no schema migration was
needed. The preference only orders candidates; it never grants authority, and
permissions, approvals and every execution boundary stay the Agent's. It
applies to conversation, reasoning, research and background turns, and to
vision unless the catalog verifies the model as text-only. In-run summaries
keep the global background route. An unreadable record degrades to the global
routes.

## Second opinion: `consult_model`

A read-only tool (intelligence chapter) that sends a bounded evidence pack the
Agent writes (question ≤ 4,000 characters, evidence ≤ 24,000) to another
configured model: one named by the Agent from its candidates, or the first
candidate that is not the model it is using. The consulted model gets no
tools, no conversation and no authority; markup in the pack is made inert.
The critique (≤ 8,000 characters) returns as an advisory observation. At most
three consultations per Run; usage is recorded with `purpose: consult_model`.
Nothing waits for agreement and nothing executes on its advice.

## Limits and follow-ups

- Benches, learned output limits and same-provider retries are per process;
  several workers may each probe a failing provider once.
- There is no UI yet for the per-Agent model preference (API only). Like the
  per-Agent approval preference, its settings row is not removed when the
  Agent is deleted (it is unreachable afterwards). A typed column on
  `ln_agents` would need a migration and is left as a follow-up.
- Reasoning/thinking controls (effort, thinking budgets) are not configured
  per adapter.
- Spend budgets per Agent or owner are still not enforced before a request;
  `consult_model` is bounded per Run only.
- The output family table must follow provider documentation as models change.

Attribution: the taxonomy and classification order adapt Hermes Agent
`agent/error_classifier.py`, the bench adapts `agent/fallback_cooldown.py`, and
the retry delays adapt `agent/retry_utils.py` (see `THIRD_PARTY_NOTICES.md`).
