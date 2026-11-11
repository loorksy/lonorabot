# Part 1.9 — Model and provider layer (map)

Repository `/home/user/lonorabot`, HEAD `9f5b1da`. Read-only audit. Every citation is `path:line` relative to the repo root.
"UNSURE:" marks what could not be confirmed from the code alone.

## 0. What matters most for the owner's complaint

1. **A failed model turn never produces an agent reply; it produces an error card whose text is chosen by a coarse "family", not by the code.** Every `model_*` code that is not billing/rate/timeout falls into family `model` (`packages/core/src/lonora_core/runtime_failure.py:50`), and the web card then shows one fixed sentence, "The model provider could not be reached. Try another model or retry shortly." (`apps/web/src/conversation/Cards.tsx:81`; Arabic «تعذّر الوصول إلى مزوّد النموذج. جرّب نموذجًا آخر أو أعد المحاولة بعد قليل.» `apps/web/src/i18n/locales/ar/messages.po:7335-7336`). That sentence is shown for a rejected API key, a model the key may not use, a safety refusal, a cut-off reply, an unreadable reply and an over-long context alike. The precise per-code strings in `apps/web/src/lib/user_error.ts:88-109` are only reached for family `other` (`apps/web/src/conversation/Cards.tsx:82`), which no `model_*` code can be. Details in §6.
2. **Malformed tool-call JSON and an empty provider reply are both classified as `invalid_response`** and, after one retry and the fallback chain, fail the whole Run with `model_response_invalid` (§7, §8). There is no "repair the arguments / ask the model again with the parse error" step in this layer.
3. **No request sets temperature, tool choice, parallel tool calls or any reasoning/thinking control**; all are provider defaults (§3). The doc says so for reasoning (`docs/provider-resilience.md:298-299`).
4. **Optional guidance, including the tool inventory, is shed first when a request is tight** (`packages/adapter-kit/src/lonora_adapter_kit/context.py:306-311`; the inventory is inserted as such optional guidance at `packages/agent-runtime/src/lonora_agent/model_runtime.py:66-75`). A model that lost its inventory is more likely to say it cannot do something. The model is told by an omission notice only if that notice itself fits (`packages/adapter-kit/src/lonora_adapter_kit/context.py:349-352`).
5. **The runtime's own "empty answer" notice tells the model that asking is an acceptable exit**: "Provide the substantive result or ask a necessary clarification with wait_for_input." (`packages/agent-runtime/src/lonora_agent/runtime_notices.py:96-99`).
6. Nothing in this layer produces `symbol_not_found` / `broker_account_not_found`; those are tool results, outside Part 1.9. This layer's contribution to the complaint class is items 1-5 plus the mobile fallback string in §6.3.

## 1. Providers that exist

- Five provider ids, fixed in the contract: `ProviderId = Literal["openai", "anthropic", "deepseek", "zai", "openrouter"]` (`packages/contracts/src/lonora_contracts/model_routing.py:9`).
- Production registry `PROVIDERS` maps those ids to adapter classes (`packages/providers/src/lonora_providers/registry.py:9-15`); an unknown id raises `provider_not_supported` (404) (`packages/providers/src/lonora_providers/registry.py:20-21`).
- Adapters:
  - Anthropic-native adapter, base URL and version header at `packages/adapters/src/lonora_adapters/models/anthropic.py:92` and `:95`.
  - One OpenAI-compatible adapter (`packages/adapters/src/lonora_adapters/models/openai_compatible.py:67`) subclassed four times with only a base URL each: `packages/adapters/src/lonora_adapters/models/openai.py:10`, `deepseek.py:10`, `zai.py:10`, `openrouter.py:10`.
- Credentials per provider: the stored secret first, else environment / `.env` variable `LONORA_<PROVIDER>_API_KEY`, else `model_not_configured` (409) (`packages/providers/src/lonora_providers/credentials.py:14-23`).
- `packages/adapters/src/lonora_adapters/registry.py:8-12` registers only channel adapters (telegram, webhook); it is not a model registry.
- Model catalogs are discovered per provider and stored in settings under `catalog:<provider>` (`packages/providers/src/lonora_providers/discovery.py:9-18`, `packages/providers/src/lonora_providers/catalog.py:12-18`). Only the OpenRouter catalog reports capabilities and marks entries `verified` (`packages/adapters/src/lonora_adapters/models/openai_compatible.py:144-157`); the Anthropic listing gives window and output cap but no capabilities (`packages/adapters/src/lonora_adapters/models/anthropic.py:160-173`); the other OpenAI-compatible listings give neither capabilities nor an output cap (`packages/adapters/src/lonora_adapters/models/openai_compatible.py:167-170`).
- Concrete model identifiers are configured by the owner in settings (`model_routing`, `model_backups`, `agent-model:*`, `model_allowed`), not in code. The only model ids hard-coded in this layer are the family tables in `packages/providers/src/lonora_providers/model_windows.py:27-58` and `:64-100`, the price table `packages/core/src/lonora_core/model_pricing.py:44`, and the voice defaults in `packages/voice/src/lonora_voice/voice_notes.py:31` and `packages/voice/src/lonora_voice/routing.py:20-21`.

## 2. How a model is chosen

### 2.1 Capabilities and the global route

- Capabilities: conversation, reasoning, research, vision, realtime_voice, stt, tts, background (`packages/contracts/src/lonora_contracts/model_routing.py:12-20`).
- `RoutingPolicy` has mode `unified` (one model) or `custom` (a route per capability) (`packages/contracts/src/lonora_contracts/model_routing.py:28-33`).
- `select_model`: audio capabilities always read `routes`; otherwise `custom` reads `routes[capability]` and `unified` reads `policy.unified`; the four text capabilities fall back to `unified`; nothing selected raises `model_not_configured` (`packages/core/src/lonora_core/model_routing.py:13-25`). Vision in `custom` mode has no fallback to `unified` (the fallback set at `packages/core/src/lonora_core/model_routing.py:16-22` omits it).

### 2.2 The candidate chain (router)

`GlobalModelRouter.route` builds, in order (`packages/providers/src/lonora_providers/router.py:177-184`):

1. `run_choice` — the model a Run was started with (a helper's chosen model);
2. the Agent's own `preference.primary`;
3. the global route for the capability (skipped silently when unconfigured, `packages/providers/src/lonora_providers/router.py:163-168`);
4. the Agent's `preference.fallbacks` (at most 3, `packages/contracts/src/lonora_contracts/model_routing.py:53`);
5. the global backups (`model_backups` setting, `packages/providers/src/lonora_providers/router.py:169`, `:182`);
6. for an Automatic agent (or one with no record) the owner's added models (`packages/providers/src/lonora_providers/router.py:173-175`).

Then: de-duplicated by (provider, model) (`packages/providers/src/lonora_providers/router.py:198-208`), cut to `MAXIMUM_CANDIDATES = 6` (`packages/providers/src/lonora_providers/router.py:60`, `:209`), and an empty chain raises `model_not_configured` (409) (`packages/providers/src/lonora_providers/router.py:210-211`). A caller may replace the chain with `choices` (`packages/providers/src/lonora_providers/router.py:159-160`); `consult_model` does (`packages/tools/src/lonora_tools/consult.py:149-157`).

An Agent's own model (and the run choice) is dropped for a capability it does not serve: text capabilities always use it; vision uses it unless the catalog *verifies* it as text-only; speech never (`packages/providers/src/lonora_providers/router.py:88-98`, `:203-206`). Because only OpenRouter entries are ever `verified` (§1), a text-only model at any other provider is still sent images.

### 2.3 Per-agent preference; no per-thread preference

- The record is per agent: mode `automatic` or `fixed`, a primary, up to 3 fallbacks (`packages/contracts/src/lonora_contracts/model_routing.py:45-53`, `:66`, `:119-124`). The router reads it on every request (`packages/providers/src/lonora_providers/router.py:171-176`).
- There is no per-thread model preference. `docs/thread-preferences.md` describes read cursor, mute, archive, pin, chat lists and search only (`docs/thread-preferences.md:8-9`); the router takes `owner_id` and `agent_id`, never a thread id (`packages/providers/src/lonora_providers/router.py:141-149`).
- The agent can read and change its own model with two tools (`packages/tools/src/lonora_tools/models.py:373-398`):
  - `model_list` (read-only): mode, the model answering now, the allowed list, connected providers, and catalog matches for a query (`packages/tools/src/lonora_tools/models.py:173-186`).
  - `model_request`: an Automatic agent's switch to an allowed model applies at once (`packages/tools/src/lonora_tools/models.py:267-272`); a change the owner's own message names applies at once (`packages/tools/src/lonora_tools/models.py:276-282`); everything else raises a one-tap owner card and returns `"owner_must_tap": True` (`packages/tools/src/lonora_tools/models.py:294-318`).
  - Refusals returned to the model as codes: `model_provider_not_connected` with "Nothing changed. The owner adds this provider's key in Model settings; until then choose one of the allowed models." (`packages/tools/src/lonora_tools/models.py:218-224`); `model_not_in_catalog` with the closest real ids and "Nothing changed. Retry with the exact provider and model of one of these, or find others with model_list." (`packages/tools/src/lonora_tools/models.py:199-209`); `model_switch_limit` after `MAXIMUM_SWITCHES_PER_RUN = 3` (`packages/tools/src/lonora_tools/models.py:64`, `:329-335`); `model_request_agent_forbidden` (403, raised, not returned) when a non-personal agent targets another agent (`packages/tools/src/lonora_tools/models.py:243-245`).
  - These refusals carry a `recovery` sentence and concrete alternatives, i.e. a safe next step; they are the good pattern in this layer. The owner card for a model outside the allowed list is an owner decision, not a money-safety rule.
  - Owner-named matching is on Latin letter/digit words only (`packages/core/src/lonora_core/model_routing.py:42`, `:65-78`); the doc admits an Arabic transliteration falls back to the card (`docs/provider-resilience.md:292-295`). For an Arabic-writing owner this means "غيّر النموذج إلى أوبس" yields a card instead of the switch.

### 2.4 Vision routing switch

Any request whose messages carry images is re-labelled `Capability.VISION` before routing (`packages/agent-runtime/src/lonora_agent/model_runtime.py:99-100`; same rule for the loop's own planning at `packages/agent-runtime/src/lonora_agent/tool_loop.py:174-175`).

## 3. Request shape

### 3.1 OpenAI-compatible providers (four of five)

- Endpoint `POST /chat/completions` (`packages/adapters/src/lonora_adapters/models/openai_compatible.py:93`, `:186`).
- Payload keys are exactly: `model`, `messages`, `stream` (`:79-83`), the output budget as `max_completion_tokens` for the `openai` provider and `max_tokens` for the others (`:84-86`), and `tools` as `{"type": "function", "function": {name, description, parameters}}` when any are offered (`:87-90`). Streaming adds `stream: true` and `stream_options: {"include_usage": true}` (`:179`).
- Not sent: `temperature`, `top_p`, `tool_choice`, `parallel_tool_calls`, `strict`, any reasoning/effort field. A search of `packages/adapters/src/lonora_adapters/models` and `packages/providers/src` for those names finds none; the payload construction above is the complete list. Parallel tool calls are therefore neither enabled nor disabled by Lonora: whatever the provider defaults to applies, and the adapters accept several calls in one reply (`:105-112`, `:222-227`), up to 32 in a stream (`:212`).
- Tool results are sent as `role: "tool"` with `tool_call_id` (`:25-27`); assistant tool calls are re-serialised with `json.dumps(call.arguments)` (`:28-36`). Images become `image_url` parts (`:21-24`). Adjacent user turns are merged into one (`:44-64`).

### 3.2 Anthropic-native provider

- Endpoint `POST /messages` (`packages/adapters/src/lonora_adapters/models/anthropic.py:124`, `:190-192`).
- Payload keys are exactly: `model`, `max_tokens` (the router's budget, else 8192), `messages`, `system` (`:107-112`), and `tools` as `{name, description, input_schema}` (`:113-121`); streaming adds `stream: true` (`:191`).
- Not sent: `temperature`, `tool_choice`, `thinking`, any beta header (headers are only `x-api-key` and `anthropic-version`, `:95`).
- System messages are joined into one string (`:62`); the leading `<lonora_operating_policy>` block (and an adjacent visual block) is marked `cache_control: ephemeral` (`:71-87`). Tool results become `tool_result` blocks in a user turn (`:28-35`), tool calls `tool_use` blocks (`:54-57`), images base64 or URL `image` blocks (`:39-53`). Same-role turns are merged (`:58-61`).

### 3.3 Streaming

- The main agent turn always streams: `model_turn` passes `on_delta` (`packages/agent-runtime/src/lonora_agent/model_runtime.py:174-185`).
- The three other callers do not stream (no `on_delta`): history summary (`packages/agent-runtime/src/lonora_agent/context_engine.py:647-654`), in-run compaction (`packages/agent-runtime/src/lonora_agent/context/compaction.py:144-151`), `consult_model` (`packages/tools/src/lonora_tools/consult.py:149-157`). Those are capped at `NON_STREAM_OUTPUT_TOKENS = 16384` (`packages/providers/src/lonora_providers/router.py:62`, `:410-411`).
- Streamed text is not published raw: financial truth gates and privacy redaction run on the final text (`packages/agent-runtime/src/lonora_agent/model_runtime.py:225-248`), and incremental publishing is disabled while a financial result is unverified (`:106-109`). Needed for safety.

### 3.4 Reasoning / thinking

Not configured anywhere (doc: "Reasoning/thinking controls (effort, thinking budgets) are not configured per adapter." `docs/provider-resilience.md:298-299`). The adapters also do not read any reasoning output: the OpenAI-compatible parser reads only `content` and `tool_calls` (`packages/adapters/src/lonora_adapters/models/openai_compatible.py:100-103`, `:198`, `:204`), the Anthropic parser only `text` and `tool_use` blocks (`packages/adapters/src/lonora_adapters/models/anthropic.py:127`, `:133-137`). `Capability.REASONING` is only a routing label.
UNSURE: whether any configured reasoning-style model requires its reasoning field to be echoed back on tool-call turns; if one does, this adapter cannot do it.

### 3.5 Max output tokens

- Policy default `output_tokens = 16384` (`packages/contracts/src/lonora_contracts/model_context.py:10`, `:22`).
- Per request: `min(policy, window // 4)` then `min(…, documented maximum or UNKNOWN_OUTPUT_TOKENS = 8192)` (`packages/providers/src/lonora_providers/context.py:71-72`; `packages/contracts/src/lonora_contracts/model_context.py:13`). The documented maximum is the catalog's `maximum_output_tokens`, else the family table (`packages/providers/src/lonora_providers/context.py:40-44`; table `packages/providers/src/lonora_providers/model_windows.py:64-100`).
- A learned per-model cap (after a provider rejected a budget) lowers it for the life of the process (`packages/providers/src/lonora_providers/router.py:406-409`, `:455`).

### 3.6 Temperature

Never set (see 3.1, 3.2). Provider default.

## 4. Context window handling per model

- Window source order: catalog `context_window` → conservative family table → unknown (`packages/providers/src/lonora_providers/context.py:66-70`). Family match is the longest key at an id boundary (`packages/providers/src/lonora_providers/model_windows.py:103-111`); table at `:27-58`.
- Input budget = window − output reservation − safety, where safety = `max(policy.safety_tokens (1024), window // 50)` (`packages/providers/src/lonora_providers/context.py:73-74`; default `packages/contracts/src/lonora_contracts/model_context.py:24`). Unknown window → `maximum_input_tokens = 64000` (`packages/contracts/src/lonora_contracts/model_context.py:9`, `:19`). An optional owner ceiling applies to every model (`packages/providers/src/lonora_providers/context.py:75-76`).
- Token counting is an offline estimate: a cached tiktoken encoding, exact only for the `openai` provider, +20% for every other provider, UTF-8 byte count when the cache is absent (`packages/adapter-kit/src/lonora_adapter_kit/tokenization.py:40-61`). Each image is charged a flat `image_tokens = 8192` (`packages/contracts/src/lonora_contracts/model_context.py:25`; `packages/adapter-kit/src/lonora_adapter_kit/context.py:131`). Each tool schema is charged its token count + 64 (`packages/providers/src/lonora_providers/context.py:117`).
- Admission is redone for every candidate from the original messages (`packages/providers/src/lonora_providers/router.py:393-402`).
- What admission does when the request does not fit (`govern_context`): mandatory system text and the newest owner message must fit or it raises `context_limit_exceeded` (413) (`packages/adapter-kit/src/lonora_adapter_kit/context.py:276-277`, `:291-292`); the newest tool exchange is bounded and must still fit (`:294-300`); optional runtime guidance is shed whole (`:306-311`); context data is shed by section (`:313-318`); older history is dropped newest-first-kept and replaced by omission notices (`:319-348`). Tool schemas alone exceeding the budget also raise `context_limit_exceeded` (`packages/providers/src/lonora_providers/context.py:118-119`).
- In-run compaction starts at `compaction_ratio = 0.75` of the input budget (`packages/contracts/src/lonora_contracts/model_context.py:29`; `packages/providers/src/lonora_providers/context.py:88`).
- Provider-proven overflow: `context_overflow` / `payload_too_large` do not fall back (`packages/providers/src/lonora_providers/resilience.py:87-88`); the Run multiplies its admission scale by `OVERFLOW_SCALE = 0.7`, at most `MAXIMUM_OVERFLOW_RETRIES = 3` times, floor `MINIMUM_INPUT_SCALE = 0.3`, and retries at once (`packages/agent-runtime/src/lonora_agent/model_recovery.py:42-43`, `:166-173`; `packages/providers/src/lonora_providers/context.py:19`; `packages/agent-runtime/src/lonora_agent/tool_loop.py:524-527`). After that the Run fails with `context_limit_exceeded`.

## 5. Retries, timeouts, backoff, failover (exact numbers)

### 5.1 HTTP

- One `httpx` client per adapter instance: `timeout=httpx.Timeout(90, connect=15)`, no redirects (`packages/adapters/src/lonora_adapters/models/base.py:62-64`). 90 s is httpx's per-operation timeout (read/write/pool), 15 s for connect; there is no overall deadline for a streamed reply in this layer.
- The adapter is created per candidate and closed after it (`packages/providers/src/lonora_providers/router.py:291`, `:329-330`).
- Stream guards: a line over 1,000,000 characters, streamed text over 120,000 characters, tool-call arguments over 120,000 characters, or more than 32 calls → `invalid_response` (`packages/adapters/src/lonora_adapters/models/base.py:109-110`; `packages/adapters/src/lonora_adapters/models/openai_compatible.py:200-201`, `:212-213`; `packages/adapters/src/lonora_adapters/models/anthropic.py:210-211`, `:216-217`). A stream that ends without its end marker → `connection` with type `stream_incomplete` (`packages/adapters/src/lonora_adapters/models/base.py:32-34`; `openai_compatible.py:214-215`; `anthropic.py:225-226`).

### 5.2 Inside one request (router) — table `RECOVERY`

`Recovery(retries while another candidate remains, retries when last candidate, fallback, transient, bench seconds, bench scope)` (`packages/providers/src/lonora_providers/resilience.py:60-71`, table `:75-97`):

| Reason | retries / alone | fallback | transient | bench | line |
|---|---|---|---|---|---|
| auth | 0 / 0 | yes | no | 900 s, whole credential | `:76` |
| billing | 0 / 0 | yes | no | 900 s, whole credential | `:77` |
| permission | 0 / 0 | yes | no | 900 s, model+credential | `:79` |
| rate_limit | 0 / 2 | yes | yes | 30 s | `:80` |
| overloaded | 1 / 2 | yes | yes | 20 s | `:81` |
| server_error | 1 / 2 | yes | yes | 20 s | `:82` |
| timeout | 0 / 1 | yes | yes | 30 s | `:83` |
| connection | 1 / 2 | yes | yes | 15 s | `:84` |
| unknown | 1 / 1 | yes | yes | 15 s | `:85` |
| context_overflow, payload_too_large | 0 / 0 | **no** | no | none | `:87-88` |
| model_not_found | 0 / 0 | yes | no | 900 s, model+credential | `:89` |
| content_policy | 0 / 0 | yes | no | none | `:90` |
| format_error | 0 / 0 | yes | no | none | `:91` |
| output_limit, truncated | 0 / 0 (after one correction/boost) | yes | no | none | `:93-94` |
| invalid_response | 1 / 1 | yes | no | none | `:95` |
| not_configured | 0 / 0 | yes | no | none | `:96` |

- Wait between same-provider retries: `min(1 s × 2^(attempt−1), 8 s)` plus up to 50% jitter (`packages/providers/src/lonora_providers/resilience.py:102-103`, `:137-147`), or the provider's `Retry-After` plus up to 10% (max 1 s) jitter when it is at most `MAXIMUM_INLINE_WAIT_SECONDS = 20` (`packages/providers/src/lonora_providers/resilience.py:101`; `packages/providers/src/lonora_providers/router.py:369-374`). A longer declared wait is not slept: the candidate gives up (`router.py:371-372`, `:461-466`).
- `Retry-After` parsing: seconds or HTTP date, `retry-after-ms`, or "retry after / try again in N" wording; capped at 3600 s; only attached for rate_limit, overloaded, server_error, timeout (`packages/adapter-kit/src/lonora_adapter_kit/model_errors.py:276-280`, `:284-331`, `:488-495`).
- Bench (process-local cooldown): `bench_seconds × 2^min(streak−1, 8)`, or the provider's `Retry-After`, capped at `MAXIMUM_BENCH_SECONDS = 900` (`packages/providers/src/lonora_providers/resilience.py:104`, `:206-215`). A benched candidate is skipped without a call (`packages/providers/src/lonora_providers/router.py:282-290`). A reason inferred only from wording never benches unless transient (`resilience.py:201-205`). Success clears the benches (`resilience.py:217-219`).
- Output corrections, each once per candidate: a `truncated` error or a cut-off text reply is retried with `max(current × 2, 8192)` bounded by the model maximum (or 2 × 8192 when unknown), the window left, and 32768 when not streaming (`packages/providers/src/lonora_providers/router.py:63`, `:101-123`, `:442-449`, `:467-472`); an `output_limit` rejection is retried with the provider's stated limit or half, never below `MINIMUM_OUTPUT_TOKENS = 128` (`router.py:65`, `:450-457`).
- When the chain is exhausted the router raises a transient failure in preference to a permanent one, with the shortest positive wait; otherwise the first real failure; a merely unconfigured backup never wins (`packages/providers/src/lonora_providers/router.py:344-367`).
- A reply that needed recovery records `provider_recovery` and `route_failures` in its metadata (`packages/providers/src/lonora_providers/router.py:332-340`, `:487-488`); these are diagnostics, not shown to the owner by this layer.

### 5.3 Across requests (Run-level recovery)

`plan_failure` (`packages/agent-runtime/src/lonora_agent/model_recovery.py:155`) is called when `model_turn` raises (`packages/agent-runtime/src/lonora_agent/tool_loop.py:517-523`):

- Non-transient → `Decision("raise")` (`model_recovery.py:174-175`): the Run fails with the code (`tool_loop.py:560`; `packages/agent-runtime/src/lonora_agent/executor.py:310-312`).
- Transient (rate_limit, overloaded, server_error, timeout, connection, unknown, or codes `model_provider_unavailable` / `model_rate_limited`, `packages/providers/src/lonora_providers/resilience.py:119`, `:130-134`) → the same checkpoint is retried later; the Run returns to `queued` and `run.retry_scheduled` is emitted (`tool_loop.py:528-552`; `executor.py:261-304`).
- Backoff profiles `(base, cap, escalate_after)`: conversation `(10 s, 60 s, 3)`, work `(30 s, 900 s, 6)`, continuous Task `(30 s, 900 s, 6, hold after 12 h)` (`model_recovery.py:59`, `:61`, `:63`). Delay = `min(base × 2^(failures−1), cap)` + up to 25% jitter, raised to the provider's hint up to 2 × cap (`model_recovery.py:140-152`).
- Which profile: Task runs → work or continuous; a conversation Run and a helper it delegated → conversation; other work triggers → work (`tool_loop.py:197-220`).
- Escalation at the streak threshold (`model_recovery.py:187-194`): a Task run waits for owner attention with reason `model_unavailable` (`tool_loop.py:553-559`); any other Run re-raises and fails (`tool_loop.py:560`). A continuous Task is notified once and keeps retrying until the outage has lasted 12 h (`model_recovery.py:188-197`; `tool_loop.py:536-545`).
- So a conversation Run fails on its 3rd consecutive transient failure: two waits of roughly 10-12.5 s and 20-25 s plus the router's own retries. The doc's "fails honestly within about a minute" (`tool_loop.py:201-203`) is consistent with those numbers.
- The final tool-less report turn at a work limit swallows a model failure and substitutes a fixed text (`tool_loop.py:261-285`); see §8.

## 6. Error classification and what the owner sees

### 6.1 Classification

- Every provider failure becomes one `ModelProviderError(reason)`; the reason maps to a stable code and API status (`packages/adapter-kit/src/lonora_adapter_kit/model_errors.py:80-99`, `:102-127`). Provider message text is never stored (`:13-16`), so no secret or request echo can leak through this error. Needed for safety (never print secrets).
- Order: a typed provider code/type (`:249-268`, `:466-470`), else HTTP status refined by wording (`:411-452`, `:471-472`), else wording alone for an untyped in-stream error, defaulting to `server_error` (`:473-478`). Plain 4xx without a recognised wording → `format_error` (`:447-451`).
- Transport: `httpx.TimeoutException` → `timeout`, any other `httpx.HTTPError` → `connection` (`packages/adapters/src/lonora_adapters/models/base.py:19-25`).
- Stop reasons: `refusal` / `content_filter` → `content_policy`; `max_tokens` / `length` / `model_context_window_exceeded` with tool calls or no text → `truncated`; with text only → kept and flagged `output_truncated` (`packages/adapters/src/lonora_adapters/models/base.py:42-55`; sets at `packages/adapter-kit/src/lonora_adapter_kit/model_errors.py:513-515`).

### 6.2 Reason → code → what the web conversation shows

The Run row stores `error_code` and a `failure` family (`packages/db/src/lonora_db/runs.py:466-470`). Family rule: provider reason `billing` → quota, `rate_limit` → rate, `timeout` → timeout (`packages/core/src/lonora_core/runtime_failure.py:31-35`, `:41-42`); else by code: `model_billing_exhausted` → quota, `model_rate_limited` → rate, `*_timeout` → timeout, any `model_*` or `context_limit_exceeded` → model, else other (`runtime_failure.py:27-28`, `:36`, `:43-52`).

Card title and text per family (`apps/web/src/conversation/Cards.tsx:69-83`):

| Family | Title | Text |
|---|---|---|
| quota | "The model provider's quota ran out" | "The model provider refused the request for quota on its account. Add credit with the provider, choose another model, or retry once it resets." |
| rate | "Too many requests in a short time" | "Many requests were sent within a minute. Wait a little, then try again." |
| timeout | "The reply timed out" | "The reply did not arrive in time; the connection may be weak." |
| model | "The model is not available right now" | "The model provider could not be reached. Try another model or retry shortly." |
| other | "The agent could not reply" | `userError({ code: run.error_code })` |

Arabic for the `model` family: title «النموذج غير متاح حاليًا» (`apps/web/src/i18n/locales/ar/messages.po:7331-7332`), text «تعذّر الوصول إلى مزوّد النموذج. جرّب نموذجًا آخر أو أعد المحاولة بعد قليل.» (`:7335-7336`); timeout «انتهت مهلة الرد» (`:7412-7413`); other title «تعذّر على الوكيل الرد» (`:7099-7100`).

Resulting owner-visible text per reason on the web card:

| Reason | Code (`model_errors.py`) | Family | Accurate? |
|---|---|---|---|
| auth | `model_credentials_rejected` (`:81`) | model | No: key rejected, shown as "could not be reached … retry shortly" |
| permission | `model_access_denied` (`:82`) | model | No |
| billing | `model_billing_exhausted` (`:83`) | quota | Yes |
| rate_limit | `model_rate_limited` (`:84`) | rate | Yes |
| overloaded / server_error / connection / unknown | `model_provider_unavailable` (`:85-86`, `:88`, `:98`) | model | Yes |
| timeout | `model_provider_unavailable` (`:87`) | timeout | Yes |
| context_overflow / payload_too_large | `context_limit_exceeded` (`:89-90`) | model | No: the specific text "This message is too large to process, even after older history was summarized. Shorten it or send fewer attachments; the conversation is kept." (`apps/web/src/lib/user_error.ts:217-220`) is not used by the card |
| model_not_found | `model_endpoint_unavailable` (`:91`) | model | Roughly |
| content_policy | `model_content_blocked` (`:92`) | model | No: specific text "The model provider’s safety system withheld this answer." (`user_error.ts:98-99`) not used |
| format_error / output_limit | `model_request_rejected` (`:93-94`) | model | No |
| truncated | `model_output_truncated` (`:95`) | model | No |
| invalid_response | `model_response_invalid` (`:96`) | model | No: see §7, §8 |
| not_configured | `model_not_configured` (`:97`) | model | No: specific text "Connect a provider and choose a global model in Settings." (`user_error.ts:88-89`) not used |

Doc vs code: `docs/provider-resilience.md:164-166` says "Clients show the owner-visible codes (`model_billing_exhausted`, `model_content_blocked`, `model_output_truncated`, `model_access_denied`, ...) in English and Arabic." On the web conversation card the code wins: those codes (except billing) all render the single `model`-family sentence (`apps/web/src/conversation/Cards.tsx:81`, family from `packages/core/src/lonora_core/runtime_failure.py:50`). The per-code strings exist (`apps/web/src/lib/user_error.ts:88-109`) but the card only calls `userError` for family `other` (`Cards.tsx:82`).
UNSURE: whether another web surface (settings, connection test) shows the per-code strings for the same codes; only the conversation card was traced.

The card offers Retry for every family except `other`, and "Change the model" / "View usage" buttons (`apps/web/src/conversation/Cards.tsx:84`, `:96-110`). So for a non-technical owner a rejected key, a blocked answer and a broken reply all look like "try again", which cannot succeed for the first two.

### 6.3 Mobile

The mobile thread shows `run.error_code` through `errorText` (`apps/mobile/app/thread.tsx:849`), which looks the code up in the label table and otherwise returns `request_failed` (`apps/mobile/lib/session.tsx:174-176`): «تعذر تنفيذ الطلب. حاول مرة أخرى.» (`apps/mobile/lib/i18n.ts:574`). The label table has `model_access_denied`, `model_billing_exhausted`, `model_content_blocked`, `model_output_truncated`, `model_endpoint_unavailable`, `model_provider_unavailable`, `model_credentials_rejected` (`apps/mobile/lib/i18n.ts:595-619`), e.g. «مزود النموذج غير متاح حاليًا. حاول مجددًا بعد قليل.» (`:616`). A search of `apps/mobile` finds no label for `model_rate_limited`, `model_not_configured`, `model_request_rejected`, `model_response_invalid` or `context_limit_exceeded`; those show the generic «تعذر تنفيذ الطلب. حاول مرة أخرى.». This is the "it did not work" class of message with no cause and no next step.

### 6.4 Tasks

- Held Task after escalation: «هذه المهمة معلّقة لأن كل النماذج المهيأة غير متاحة منذ مدة رغم المحاولات المتكررة؛ تقدّمها محفوظ ولم يُكرَّر أي إجراء.» (`packages/agent-runtime/src/lonora_agent/runtime_notices.py:163-168`).
- Task recovery classes by code: transient (auto-retry) `model_provider_unavailable`, `model_rate_limited`, `model_endpoint_unavailable` (`packages/db/src/lonora_db/task_recovery.py:21-24`); plan-level `model_request_rejected`, `context_limit_exceeded` (`:25-33`); owner-level `model_not_configured`, `model_credentials_rejected`, `model_access_denied`, `model_billing_exhausted`, `model_content_blocked`, `model_output_truncated`, `model_response_invalid` (`:34-49`).
- Note: `model_response_invalid` and `model_output_truncated` are owner-level for a Task (`:43-44`), so a single malformed provider reply that survives one retry and the fallback chain parks background work for the owner. Automatic retries never resend an unresolved financial call (`docs/provider-resilience.md:156-161`; replay set at `packages/db/src/lonora_db/task_recovery.py:50`). Needed for safety.

### 6.5 Unclassified exceptions

Anything that is not a `LonoraError` fails the Run with `runtime_error` (`packages/agent-runtime/src/lonora_agent/executor.py:313-315`) → family `other` → title "The agent could not reply" with no Retry button (`apps/web/src/conversation/Cards.tsx:74`, `:96`). One path from this layer can reach it: the OpenAI-compatible parser reads `usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)` (`packages/adapters/src/lonora_adapters/models/openai_compatible.py:122`, `:231`); if a provider sends `"prompt_tokens_details": null` this raises `AttributeError`, which the `except (KeyError, IndexError, ValueError, TypeError)` at `:130` and `except (KeyError, TypeError, ValueError)` at `:235` do not catch, and the router only catches `LonoraError` (`packages/providers/src/lonora_providers/router.py:310`, `:438`). The same holds for a null `delta` at `:197-198`.
UNSURE: whether any of the four OpenAI-compatible providers actually sends those fields as null; the code path is certain, the trigger is not confirmed.

## 7. Malformed tool call / invalid JSON arguments

- OpenAI-compatible, non-stream: `json.loads(call["function"]["arguments"])` inside a `try` whose `except (KeyError, IndexError, ValueError, TypeError)` raises `invalid_response()` (`packages/adapters/src/lonora_adapters/models/openai_compatible.py:105-112`, `:130-131`).
- OpenAI-compatible, stream: fragments are concatenated per index (`:204-211`) and parsed once at the end with `json.loads(call["arguments"])` (`:222-227`); failure → `invalid_response()` (`:235-236`). An empty arguments string (a call with no parameters sent as `""`) is not valid JSON and takes the same path; the Anthropic adapter handles the equivalent case explicitly (`packages/adapters/src/lonora_adapters/models/anthropic.py:236-238`), the OpenAI-compatible one does not. A fragment whose `id`, `name` or `arguments` key is present but null makes `+=` raise `TypeError` (`openai_compatible.py:208-211`) → also `invalid_response`.
  UNSURE: whether a configured provider sends empty-string arguments or null fragment fields; if one does, every such turn fails as below.
- Anthropic: `json.loads(block["partial_json"])` (`packages/adapters/src/lonora_adapters/models/anthropic.py:233-239`) → `invalid_response()` on failure (`:255-256`).
- Arguments that parse to something other than an object fail `ToolCall.arguments: dict[str, Any]` validation (`packages/adapter-kit/src/lonora_adapter_kit/types.py:8-11`); UNSURE: this relies on the validation error being a `ValueError` subclass so the same `except` catches it — not executed here.
- A reply cut off at the output budget never yields tool calls: `truncated` is raised before any argument is parsed (`packages/adapters/src/lonora_adapters/models/base.py:51-53`), then boosted once (§5.2). Needed for safety: an incomplete financial tool input must never execute.
- Recovery for `invalid_response`: one retry on the same model, then the next candidate, no bench, not transient (`packages/providers/src/lonora_providers/resilience.py:95`). If the chain is exhausted the Run fails with `model_response_invalid` (`packages/adapter-kit/src/lonora_adapter_kit/model_errors.py:96`); `plan_failure` raises at once because it is not transient (`packages/agent-runtime/src/lonora_agent/model_recovery.py:174-175`).
- What is missing: the model is never shown its own malformed call and asked to correct it. The bad reply is discarded in the adapter, so no assistant turn and no tool error reaches the transcript; the only recovery is "ask again identically" once. When the chain holds a single model (a `unified` policy with no backups, agent fallbacks or added models) that is two attempts total (`retries_alone = 1`, `packages/providers/src/lonora_providers/resilience.py:95`), then a failed Run and the `model`-family card of §6.2.
- Schema-level validation of well-formed arguments happens later in the tool registry (outside Part 1.9).

## 8. Empty reply handling

Three layers, in order:

1. **Adapter**: a reply with no text and no tool calls is `invalid_response` (`packages/adapters/src/lonora_adapters/models/openai_compatible.py:114-115`, `:218-219`; `packages/adapters/src/lonora_adapters/models/anthropic.py:139-140`, `:243-244`). Same recovery and same owner outcome as §7. A model that returns only reasoning output with empty content lands here because reasoning fields are not read (§3.4).
2. **Tool loop**: a reply that is empty *after* the runtime's own processing (text blanked by a gate, redaction, or projection) in a conversational Run appends the notice "No answer was provided for the selected request. Provide the substantive result or ask a necessary clarification with wait_for_input. Do not invent results." and takes another model turn (`packages/agent-runtime/src/lonora_agent/tool_loop.py:573-579`; text `packages/agent-runtime/src/lonora_agent/runtime_notices.py:96-99`). The round was already counted (`tool_loop.py:566`). Conversational = every trigger except routine, webhook, created, tickets, watch (`packages/core/src/lonora_core/run_state.py:33-34`). For those non-conversational triggers an empty reply is accepted and recorded as `"reply_outcome": "silent"` (`tool_loop.py:603-605`).
3. **Final report at a work limit**: if the tool-less report turn fails or is empty, the fixed text is used: «توقفت قبل إنهاء العمل لأن هذه الجولة بلغت حدّها، ولم يُنفَّذ أي إجراء بعد ذلك. اطلب مني المتابعة عندما تريد الاستئناف.» (`packages/agent-runtime/src/lonora_agent/tool_loop.py:273-284`; text `packages/agent-runtime/src/lonora_agent/runtime_notices.py:132-139`). This is a stop-and-ask-the-owner message by construction.

## 9. Token / cost accounting and budgets that can stop a run

- Usage per reply is normalised to `TokenUsage(input_tokens, output_tokens, cached_tokens)` (`packages/contracts/src/lonora_contracts/usage.py:9`), read from `prompt_tokens` / `completion_tokens` / `prompt_tokens_details.cached_tokens` (`packages/adapters/src/lonora_adapters/models/openai_compatible.py:119-123`) or `input_tokens` / `output_tokens` / `cache_read_input_tokens` (`packages/adapters/src/lonora_adapters/models/anthropic.py:144-148`).
- One usage row per model call, with run, provider, model, tokens and the request's context-budget diagnostics (`packages/llm-usage/src/lonora_llm_usage/models.py:7-13`; `packages/llm-usage/src/lonora_llm_usage/store.py:7-23`). Written after the main turn (`packages/agent-runtime/src/lonora_agent/model_runtime.py:204-216`), summaries (`packages/agent-runtime/src/lonora_agent/context_engine.py:655`), compaction (`packages/agent-runtime/src/lonora_agent/context/compaction.py:152`) and consultations (`packages/tools/src/lonora_tools/consult.py:158`). A failed attempt writes no usage row (the write follows a successful `router.complete`).
- Cost is computed at read time from a list-price table dated `PRICES_AS_OF` (`packages/core/src/lonora_core/model_pricing.py:25`, `:44`, `:95`); models without a price count as `unpriced_requests` (`packages/contracts/src/lonora_contracts/usage.py:22-33`).
- **No token or money budget stops a run.** Doc: "There is no spend cap, budget or limit anywhere (owner decisions D4 and Q22) … nothing here ever blocks a request." (`docs/usage-dashboard.md:4-6`); code agrees: the router and `model_turn` contain no usage check (`packages/providers/src/lonora_providers/router.py:240-342`; `packages/agent-runtime/src/lonora_agent/model_runtime.py:173-190`), and the quota card comment says "Lonora sets no spend cap; the refusal is the provider's own quota." (`apps/web/src/conversation/Cards.tsx:77`).
- Limits that *do* stop or bound work, all counted in rounds or calls, not tokens:
  - Model rounds per run: `maximum_rounds` default 24 (`packages/agent-runtime/src/lonora_agent/runtime.py:8`), times `MAXIMUM_SLICES = 4` for Task runs (`packages/agent-runtime/src/lonora_agent/continuation.py:20`; `packages/agent-runtime/src/lonora_agent/tool_loop.py:467-468`). The last budgeted turn is forced to be a tool-less report (`tool_loop.py:471-485`); a warning notice is added when 2 or fewer executable rounds remain (`tool_loop.py:114`, `:486-488`).
    UNSURE: whether a deployment overrides the default 24; only the constructor default was traced.
  - `consult_model`: 3 per run, then `consult_budget_exhausted` with `"next_action": "decide_with_current_evidence"` (`packages/tools/src/lonora_tools/consult.py:31`, `:109-115`).
  - `model_request`: 3 applied switches per run (`packages/tools/src/lonora_tools/models.py:64`).
  - Per-request size limits (§4) end in `context_limit_exceeded` after three tightening retries.

## 10. Vision and audio input

### Vision

- `ModelMessage.images` is a list of URLs / data URLs (`packages/adapter-kit/src/lonora_adapter_kit/types.py:25`); both adapter families serialise it (§3.1, §3.2).
- Sources of images: the owner's attachments are set on the newest owner message (`packages/agent-runtime/src/lonora_agent/context/builder.py:278-283`); images the agent asked to look at with `artifact_read(view_image=true)` are resolved per request, never stored in the checkpoint (`packages/agent-runtime/src/lonora_agent/context/image_observations.py:17-29`, `:67-70`), at most `MAX_OBSERVATION_IMAGES = 4` and 20 MiB total per request, 5 MiB each (`image_observations.py:13-14`, `:84-88`; `packages/tools/src/lonora_tools/artifacts.py:103`). Older ones are replaced by a notice that says no pixels were supplied (`image_observations.py:113-135`). An image that cannot be loaded is reported to the model as `status: "unavailable"` with a raw `code` (`image_observations.py:98-102`).
- Any image in the request switches the capability to vision (§2.4). In `custom` routing with no vision route and no usable agent model, backups or added models, the chain is empty and the turn fails with `model_not_configured` (§2.1, §2.2) → `model`-family card (§6.2), even though the cause is "no vision model chosen".
- A model that cannot see images is only excluded when its catalog entry is verified text-only (§2.2). Otherwise the provider's rejection is a plain 4xx → `format_error` → fallback, no bench (`packages/providers/src/lonora_providers/resilience.py:91`).

### Audio

- Chat model requests carry no audio: `ModelMessage` has text, images and tool fields only (`packages/adapter-kit/src/lonora_adapter_kit/types.py:14-25`).
- Owner voice notes are transcribed before the agent's Run is admitted, by a separate step that uses only the `openai` provider's key and a fixed model order (the owner's STT route if it is on that provider, then two defaults) (`packages/voice/src/lonora_voice/voice_notes.py:31-40`, `:65-75`). No key, missing file or provider failure settles the note as failed (`voice_notes.py:59-68`, `:73-75`; module docstring `:6-7`). The transcription call has a 90 s timeout and maps every failure to `voice_transcription_failed` (`packages/adapters/src/lonora_adapters/voice/stt.py:21-36`), with no retry beyond trying the next model.
- STT/TTS routes must both be on the `openai` provider or `voice_provider_unsupported` is raised (`packages/voice/src/lonora_voice/routing.py:8-13`); the realtime voice model is restricted to two ids or `voice_model_unsupported` (`routing.py:16-23`).
- Consequence for an owner whose only connected provider is not that one: voice notes cannot be transcribed at all. What the owner sees for a failed note is outside Part 1.9.

## 11. The fake / scripted model adapter used by tests

- `ScriptedModelAdapter` (`packages/adapters/src/lonora_adapters/models/fake.py:9-37`): constructed with `replies: list[ModelReply]`; each `complete` call records the messages in `self.requests`, pops the next reply, sends its whole text as one delta when streaming, and raises `scripted_model_exhausted` (500) when the list is empty (`fake.py:12-31`). It ignores `model`, `tools` and `max_output_tokens`, cannot raise a provider error, and `discover` returns `[]` (`fake.py:33-34`). It is not in the production registry (`packages/providers/src/lonora_providers/registry.py:9-15`).
- It is not what the test suite uses: a search of `tests/` for `ScriptedModelAdapter` finds no import. Tests define their own doubles at one of two seams:
  - **Adapter seam (keeps the real router: retries, fallback, bench, admission).** `GlobalModelRouter` accepts `factory`, `sleep`, `clock`, `jitter` (`packages/providers/src/lonora_providers/router.py:127-139`). The fullest double is `Scripted` + `FakeAdapter` in `tests/test_provider_resilience.py:570-620`: scripts are keyed by model id, each a list of outcomes; an outcome is a `ModelReply`, a `LonoraError` to raise, or a callable receiving `max_output_tokens`; the last outcome repeats (`tests/test_provider_resilience.py:567`, `:584-590`); calls and sleeps are recorded (`:604-605`, `:611-612`). To script a tool-calling turn, return `ModelReply(tool_calls=[ToolCall(id=…, name=…, arguments={…})])` (`packages/adapter-kit/src/lonora_adapter_kit/types.py:8-11`, `:28-33`); to script a failure, put `ModelProviderError(FailureReason.X, retry_after=…)` in the list (`packages/adapter-kit/src/lonora_adapter_kit/model_errors.py:111-127`). A simpler per-provider variant is `ScriptedAdapter` in `tests/check_agent_model_choice.py:41-56`.
  - **Router seam (bypasses the provider layer).** An object with `complete(capability, messages, tools, *, on_delta, on_attempt, **_)` returning `(ModelReply, ModelSelection)` is cast to the router, e.g. `ScriptedRouter` in `tests/check_streaming.py:169-189`, which calls `on_attempt` then feeds chunks to `on_delta`. Tools that inspect the router tolerate such doubles with `getattr(context.router, "credentials", None)` (`packages/tools/src/lonora_tools/models.py:117-119`) and `getattr(context.router, "route", None)` (`packages/tools/src/lonora_tools/consult.py:116-118`).
- Gap relevant to this audit: neither seam can express a *malformed* provider reply (bad JSON arguments, empty content, null fields), because both return already-parsed `ModelReply` objects. Those paths can only be exercised through the real adapters with an injected `httpx.AsyncClient` (constructor parameter `client`, `packages/adapters/src/lonora_adapters/models/base.py:59-65`).
  UNSURE: whether existing tests do that for the cases in §7; not searched exhaustively.

## 12. Doc vs code summary

| Topic | Doc | Code | Verdict |
|---|---|---|---|
| Owner-visible error text | "Clients show the owner-visible codes (…) in English and Arabic." `docs/provider-resilience.md:164-166` | Web card shows one sentence per family; all non-billing/rate/timeout `model_*` codes share it (`apps/web/src/conversation/Cards.tsx:76-83`; `packages/core/src/lonora_core/runtime_failure.py:50`). Mobile lacks labels for five codes (§6.3). | Code wins; doc overstates. |
| Retry table | Lists no row for `unknown` (`docs/provider-resilience.md:65-74`) | `unknown`: 1 / 1 retries, fallback, transient, 15 s bench (`packages/providers/src/lonora_providers/resilience.py:85`) | Code wins; doc incomplete. |
| Candidate chain, six candidates | `docs/provider-resilience.md:51-60` | `packages/providers/src/lonora_providers/router.py:60`, `:177-184` | Agree. |
| Backoff numbers (1→8 s, 20 s inline wait) | `docs/provider-resilience.md:83-84` | `packages/providers/src/lonora_providers/resilience.py:101-103` | Agree. |
| Output default 16,384; 8,192 when unknown | `docs/provider-resilience.md:100-104` | `packages/contracts/src/lonora_contracts/model_context.py:10`, `:13` | Agree. |
| Run backoff 10 s/60 s, 30 s/15 min; escalate after 3 / 6; 12 h hold | `docs/provider-resilience.md:136-137`, `:143-145`, `:154-155` | `packages/agent-runtime/src/lonora_agent/model_recovery.py:59-63` | Agree. |
| Overflow scale 0.7, floor 0.3, three times | `docs/provider-resilience.md:123-125` | `packages/agent-runtime/src/lonora_agent/model_recovery.py:42-43`; `packages/providers/src/lonora_providers/context.py:19` | Agree. |
| No spend cap | `docs/usage-dashboard.md:4-6`; `docs/provider-resilience.md:264-267` | No usage check in the request path (§9) | Agree. |
| Per-thread model preference | Not described; `docs/thread-preferences.md` is about list state only (`:8-9`) | None exists (§2.3) | Agree (absent in both). |
| Reasoning controls | "not configured per adapter" `docs/provider-resilience.md:298-299` | No such payload key (§3) | Agree. |

## 13. Safety labels for refusals found in this layer

- Truncated reply never yields tool calls (`packages/adapters/src/lonora_adapters/models/base.py:51-53`): needed for safety.
- Provider message text never stored on errors (`packages/adapter-kit/src/lonora_adapter_kit/model_errors.py:13-16`): needed for safety (secrets / request echo).
- Text blanked when a financial call is proposed, and replaced while a financial result is unverified (`packages/agent-runtime/src/lonora_agent/model_runtime.py:225-232`): needed for safety (no premature success claim).
- Automatic Task retry never resends an unresolved financial call (`packages/db/src/lonora_db/task_recovery.py:50`; `docs/provider-resilience.md:156-161`): needed for safety.
- Model choice grants no authority (`packages/contracts/src/lonora_contracts/model_routing.py:46-50`): needed for safety.
- Not safety-driven, and therefore candidates for change without touching any money rule: the single `model`-family sentence (§6.2), missing mobile labels (§6.3), no self-correction turn for malformed tool calls or empty replies (§7, §8), the uncaught null-field paths (§6.5), shedding the tool inventory before other content (§4), the "ask a necessary clarification" wording of the empty-answer notice (§8), Latin-only model-name matching (§2.3), and vision routing that fails as `model_not_configured` (§10).
