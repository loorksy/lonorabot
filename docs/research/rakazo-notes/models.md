# rakazo: model/provider layer, reliability and observability

Source: `/home/user/elie222/rakazo` at commit `cd7e20e5da754d8d8deaf2780671ed34a38e2241`.
All paths are relative to that repo root. "(implemented)" = I opened the code at that line.
"(stated)" = docs only. Nothing here was executed; no test suite was run.

Short answer for the Lonora complaint, before the detail: this layer makes *provider* failures
invisible or polite (retry, switch model, short human error sentence with the raw text hidden
in a details field). In the files read for this section I found nothing that makes the agent
try a different approach after a *tool* failure; a test shows a thrown tool error being handed
back to the model as the tool result (`packages/testkit/src/pi-offline.test.ts:488-524`; shown
by a test only, the runtime code path that does this was not opened here). See section 7.

---

## 1. Providers, models, roles, configuration

### 1.1 Where the model list comes from

- The catalog is not maintained by rakazo. It is the bundled registry of the third-party
  `@earendil-works/pi-ai` package ("Pi"): `builtinModels()` plus two rakazo-registered
  providers (a deployment "local" provider and a per-user "openai-compatible" provider)
  (`packages/adapters/src/pi-models.ts:277-283`, `packages/adapters/src/pi-runtime-models.ts:32-38`) (implemented).
  I did not count the providers in the bundled registry (needs running code): unsure of the number.
- A weekly GitHub workflow bumps the pinned Pi packages so new/removed models arrive as a PR
  (`.github/workflows/model-catalog-bump.yml:3-9`) (implemented as workflow config).
- rakazo keeps small hand-written overlays on top of the registry:
  - a "recommended" model per provider for new connections, 8 entries
    (`packages/adapters/src/pi-models.ts:57-66`);
  - a list of bundled ids that providers refuse, hidden from pickers but kept if already saved
    (`packages/adapters/src/pi-models.ts:72-111`);
  - label cleanup for "latest" alias ids (`packages/adapters/src/pi-models.ts:363-385`).
- "Live catalog": for some providers the model list is also probed from the provider with the
  user's key and cached. `RAKAZO_LIVE_MODEL_CATALOG=off` disables it
  (`packages/adapters/src/pi-live-cache.ts:1-4`). The ChatGPT-subscription ("Codex") list has
  fixed bounds: 12 s fetch timeout, 15 min TTL, 60 s failure TTL, 1.5 s read wait, stale data
  allowed up to 4 h (`packages/adapters/src/pi-codex-catalog.ts:24-39`) (implemented, constants only read).

### 1.2 Ways to connect a model

1. **Deployment default (operator env).** `PI_DEFAULT_PROVIDER` defaults to `openrouter`;
   default model ids are `anthropic/claude-haiku-5.5` (openrouter), `claude-sonnet-5`
   (anthropic), `deepseek-flash` (deepseek); `PI_DEFAULT_MODEL` overrides
   (`packages/adapters/src/deployment-model.ts:6`, `:36-65`) (implemented; same table in
   `docs/self-host-models.md:13-17`). Keyless host credentials (Bedrock, Vertex, local) need the
   explicit opt-in `PI_DEFAULT_CREDENTIALS=host` plus an explicit model
   (`packages/adapters/src/deployment-model.ts:51-58`).
   An unknown provider gets no key rather than another vendor's key (`deployment-model.ts:38-43`),
   and only OpenRouter may fall back to the OpenRouter env key at run time
   (`packages/adapters/src/pi-runtime-models.ts:117-124`).
   **Doc/code disagreement:** `docs/self-host-billing.md:36-37` says "The default OpenRouter model
   is Luna 6", while the code default is `anthropic/claude-haiku-5.5` (`deployment-model.ts:6`).
   Possibly the hosted service overrides it by env; unsure.
2. **User API key** for a catalog provider. The key is verified on save, but only a key the
   provider actively rejects blocks saving; a slow provider does not
   (`packages/adapters/src/pi-models.ts:177-178`).
3. **Subscription sign-in (OAuth)** for four providers: ChatGPT (device code), GitHub Copilot
   (device code), xAI SuperGrok/X Premium (device code), Claude Pro/Max (auth URL)
   (`packages/adapters/src/pi-oauth.ts:28-63`). The Claude flow uses a hard-coded OAuth client id
   and Anthropic's authorize/token URLs (`packages/adapters/src/pi-anthropic-oauth.ts:5-16`).
   I did not read the remaining ~1,100 lines of `pi-oauth.ts` (refresh, locking).
4. **Operator "local" provider**: an OpenAI-compatible server (Ollama, LM Studio, llama.cpp, MLX),
   default URL `http://127.0.0.1:11434/v1`, default context window 32,768, default max output
   4,096 (`packages/adapters/src/pi-local-provider.ts:11-30`). Env names in
   `docs/self-host-models.md:69-80` (stated).
5. **Per-user OpenAI-compatible endpoint** with three wire protocols: `chat-completions`
   (default), `responses`, `anthropic-messages`
   (`packages/adapters/src/pi-openai-compatible-provider.ts:84-98`). Private/loopback targets are
   refused unless `MCP_ALLOW_PRIVATE_ENDPOINT=true` (`docs/self-host-models.md:119-124`) (stated;
   I did not read the SSRF checks in code).

### 1.3 Model roles

- There are exactly three roles: `main`, `approval`, `computer`
  (`packages/contracts/src/model-roles.ts:7`). There is **no** "small/decision", "vision" or
  "voice" role. Vision is a capability flag on a model (`images`): a model whose catalog entry
  has `images === false` is not accepted for the `computer` role
  (`packages/contracts/src/model-roles.ts:29-32`); voice is configured separately
  (`docs/self-host-models.md:243-257`, stated).
- Each role stores `primary` plus an ordered `backups` list; each entry may carry its own
  thinking level and a specific connection id (`packages/contracts/src/model-roles.ts:9-19`).
  At most 10 backups, each model+connection once (`packages/contracts/src/model-connections.ts:124-141`).
- Defaults when the member chose nothing (`packages/adapters/src/model-roles.ts:25-42`):
  `approval` → the deployment auto-review checker if configured, else none; `computer` → none
  ("No computer model means the main model works the screen itself", `model-roles.ts:36`);
  `main` → owner's saved default, else the env deployment model.
- Member choice wins; the deployment fills what is empty (`packages/adapters/src/model-roles.ts:50-68`).

### 1.4 Per-bot / per-run selection

`selectConfiguredModel` (`packages/adapters/src/model-roles.ts:94-137`) resolves in this order:
bot/run override (only if a credential for it exists or it is the deployment-funded provider)
→ member's main model → deployment default. An override whose connection is missing is dropped
silently and its thinking level is dropped with it (`model-roles.ts:131-136`). Routines can pin
their own model (`packages/adapters/src/model-selection.ts:870-890`; docs `docs/models.md:36-40`).

Thinking level: a reasoning-capable model never starts at "off"; the default is `medium`,
because some endpoints reject effort "none" (`packages/adapters/src/pi-runtime-models.ts:40-52`).

### 1.5 A pattern worth noting: loose-name resolution with candidates in the error

When the bot is asked to switch model by a loose name ("Claude Sonnet"), `matchModelChoice`
requires every spoken word to appear in the model name, then ranks by current provider, plainest
family, newest version (`packages/adapters/src/model-choice.ts:68-111`). If the match is
ambiguous the tool result lists up to 5 candidates with their exact ids
(`model-choice.ts:15`, `:134-141`):

> `"<query>" matches several models. Ask the user which one, or pass its id as model: <provider/id (label)>, ...`

If nothing connected matches, it names which provider to connect (`model-choice.ts:153-159`).
This is the same shape as Lonora's "XAUUSD not found → the broker calls it XAUUSDm" problem:
the tool error itself carries the nearest real names, so the model can retry without asking.

---

## 2. Fallbacks, retries, and what the user sees

### 2.1 Error classification (the foundation)

`packages/adapter-kit/src/model-errors.ts` defines three error classes: `TransientModelError`
(clears on its own), `ModelAccountError` (user must fix key/credit/plan/model), `ModelOutputError`
(empty reply, malformed tool call, cut output) (`model-errors.ts:3-31`). Anything unclassified
stays a plain `Error` = server fault.

Classification is done by walking the error object up to depth 4, collecting `message/code/type`
strings and HTTP statuses, and also parsing statuses out of free text
(`model-errors.ts:33-66`). Three predicates:

- `isRetryableProviderUnavailable` — may advance to a backup: 408, 429, any 5xx, explicit
  account exhaustion on 400/402/403, the ChatGPT usage-limit sentence, and status-less text such
  as rate limit / overloaded / capacity. Never for 401, plain 400/403, aborts, context-length
  errors, invalid-request errors (`model-errors.ts:107-168`).
- `isModelCredentialRejected` — 401 or key/token wording (`model-errors.ts:95-105`).
- `isTransientModelError` — the subset that is worth retrying on the *same* model: excludes 402,
  exhausted accounts, quotas that reset hours later, subscription/billing limits; keeps
  per-minute rate limits (`model-errors.ts:170-196`).

### 2.2 Same-model retry and backoff (implemented)

All in `packages/adapters/src/pi-runtime-fallback.ts`, function `fallbackAwareModelStream` (`:303`).

- Backoff delays: 2 s, 8 s, 20 s → at most 3 delayed retries of an ordinary transient failure
  (`:61`, `:669`, `:677-686`). This path is reached only when no backup model could be resolved
  (`:647-663`).
- Retries share one time budget with the request: default 120,000 ms, env
  `MODEL_STREAM_TIMEOUT_MS` (`packages/adapters/src/pi-runtime-limits.ts:6`, `:47-54`;
  budget check at `pi-runtime-fallback.ts:462-468`, `:677`).
- Other timeouts: connect 30,000 ms; stream idle (silence after headers) 180,000 ms; SDK-level
  retries default 1, env-configurable 0–5 (`pi-runtime-limits.ts:8-15`, `:26-30`). An idle
  timeout is retried at most once per call, after 2 s, with the time window renewed; a second
  idle timeout in the same call is not retried (`pi-runtime-fallback.ts:664-675`). Note the
  120,000 ms figure is described in code as a per-attempt wait for response headers that "does
  not cap active streaming duration" (`pi-runtime-limits.ts:5`); the fallback code reuses it as
  the window for same-model retries (`pi-runtime-fallback.ts:449-452`).
- When backups are configured the SDK's own retry is turned off (`maxRetries: 0`) so "a hung
  model is not waited on twice" (`pi-runtime-fallback.ts:511-513`).
- Only transient errors retry the same model (`:660-663`).
- A retry or switch happens **only if nothing visible was produced yet** (no text delta, no tool
  call). Events are buffered until the first visible output, so the user never sees a discarded
  attempt (`:117-132`, `:529-536`, `:831-844`). A call that has only produced thinking counts
  as "nothing visible", so if it then fails it can be retried from scratch with the thinking
  discarded (`:113-116`). (The cut-reply continuation in 2.4 is the separate case that acts
  *after* visible text.)
- Tested offline: a dropped stream then a 503 after a tool call are retried with delays
  `[2000, 8000]` and the tool effect runs exactly once
  (`packages/testkit/src/pi-offline.test.ts:56-112`).

### 2.3 Switching to a backup model (implemented)

- Trigger: provider failure with no visible output, and one of: provider-reported context limit
  too small for the mandatory prompt, `isRetryableProviderUnavailable`, or
  `isModelCredentialRejected` (`pi-runtime-fallback.ts:633-642`). Backup is tried **before**
  same-model retry (`:647-659` then `:662`).
- Each backup is resolved lazily and skipped with a recorded reason if: the saved connection no
  longer matches; no credential (a backup never borrows the primary's or the process-wide key);
  model missing from catalog; conversation would not fit its context window; request needs
  images and it cannot see them; image count over its limit; thinking level unsupported
  (`:362-443`, `:238-301`).
- Context fit is judged on what the backup's own pruning policy would send. When no such
  policy prepared the context, a safety margin of `max(256, 10% of input tokens)` is added; when
  the policy did prepare it, no extra margin is used (`:246-280`).
- On switch the run row is updated with the new provider/model, guarded by the run lease
  (`packages/adapters/src/executor.ts:1879-1900`); the backup keeps its own thinking level
  (`packages/adapters/src/pi-runtime.ts:504-522`); earlier thinking blocks are dropped from the
  request (`pi-runtime-fallback.ts:100-105`, `:314-320`).
- Start-of-run variant: if the main model has no connection or its sign-in was refused, the run
  starts on the first backup that resolves, unless the run was pinned to a model; logged as
  `model.primary_unavailable.backup_used` (`packages/adapters/src/run-model-start.ts:41-60`).
- Docs describe this loosely as "if the main model fails or hits a limit, the bot moves to the
  next one" (`docs/models.md:24-26`). The code is narrower (see trigger above): a 400 invalid
  request, or a failure after text has started, does not switch.

### 2.4 Other self-repairs inside one model call (implemented, same file)

The first two items below share a per-run counter capped at `MAX_SELF_RECOVERIES_PER_RUN = 3`
(`pi-runtime-fallback.ts:134`, checks at `:700`, `:743`, `:782`, `:811`). The last four are not
counted against it; each is guarded by its own flag instead (`sizingFailure` `:534`, `:577`,
`:598`; `thinkingLevelMap` `:609`; `dropThinkingBlocks` `:624`).

- Output budget spent with nothing visible → one repeat with doubled `maxTokens` (within the
  model card ceiling), or one thinking level lower (`:186-216`, `:806-824`).
- Reply cut mid-way by the limit or by a dropped connection → the text already shown is kept and
  the runtime asks the model to continue; overlap of up to 240 characters is de-duplicated
  (`:134-176`, `:691-721`, `:766-805`). Only where the caller supplied `cutReplies`; the code
  comment says subagents do not (`:78-82`). The "ask to continue" step itself lives outside
  this file and was not opened (unverified).
- Provider reports a smaller context window than the catalog → shrink and resend (`:537-582`).
- OpenRouter says the account can only afford N output tokens → cap and resend (`:583-602`).
- Endpoint rejects `reasoning_effort` and lists accepted values → narrow and resend
  (`:604-618`; parser in `packages/adapters/src/pi-runtime-models.ts:232-267`).
- Provider rejects replayed thinking signatures → drop thinking blocks for the rest of the run
  (`pi-runtime-fallback.ts:619-632`).

### 2.5 Routines (scheduled runs)

- A routine run that fails with `TransientModelError` can be retried once, 12 minutes later (a
  retry is never retried again) (`packages/adapters/src/run-routines.ts:33`, `:68-75`). Per the
  doc comment this is only for a run stopped "before it posted a message or called a tool"
  (`:52-56`), and there is a 30-minute window constant for skipping the retry when the next
  occurrence is near (`:35-36`). I read the function only to line 80.
- A routine failing on an account-type refusal backs its schedule off: 5 min base, doubling,
  max 24 h, or until the reset time the provider named (itself capped at 24 h ahead)
  (`packages/adapters/src/routine-backoff.ts:8-10`, `:33-64`, `:73-95`).

### 2.6 What the user sees

- The runtime throws one classified error. If every backup was tried/skipped, the message is a
  JSON envelope `{modelFallbackVersion:1, primaryError, backups:[{provider, modelId, status,
  reason}]}` (`packages/core/src/run-error.ts:162-173`; assembled at
  `packages/adapters/src/pi-runtime.ts:1160-1181`). The run's overall class is the *worst* of
  its parts (`packages/adapters/src/pi-runtime-errors.ts:107-129`).
- `normalizeRunError` turns stored text into `{summary, details, recovery, resetAt, kind}`
  (plus `period`, `status`, `providerMessage`) (`packages/core/src/run-error.ts:223-249`). For
  provider errors the summary is a short fixed sentence and the raw provider text stays in
  `details`; for some app-generated errors the summary is the stored text itself (`:291-299`).
  `recovery` is optional and at most one of `connection` / `model` / `plan` ("the one action
  that fixes the failure", `:226-231`); transient failures carry none. How the client renders
  it (e.g. as a button) was not read (unverified). Examples of summaries (all implemented at
  the cited lines):
  - "{provider} is rate limiting requests. Try again shortly." (`run-error.ts:400`)
  - "{provider} reached its monthly credit limit." + " Resets {date}." (`run-error.ts:133-152`, `:438`, `:460`)
  - "{provider} rejected the API key. Check your connection settings." (`run-error.ts:325`)
  - "{provider} is overloaded right now. Try again in a moment." (`run-error.ts:528`)
  - "{provider} took too long to respond. Try again." (`run-error.ts:544`)
  - "The model returned an unusable response. Try again." (`run-error.ts:548`)
  - With backups: "{summary} Your backup models also failed." / "... No backup model was usable
    for this request." (`run-error.ts:274-289`)
  - Stored text "Internal server error" → "Something went wrong. Try again." (`run-error.ts:300-302`)
  - Provider text that matches no rule → "The model provider returned an error." (`run-error.ts:382`)
- Out of credit on the hosted plan: "Not enough model credits. Add credits in Billing or connect
  your own API key." (`run-error.ts:42-43`); operator cap: "Usage limit reached. Contact support
  to continue." (`run-error.ts:46`); no model: "Connect a model in Settings before running bots."
  (`run-error.ts:35`).
- Server faults are scrubbed before being stored for the user: stack frames removed, server file
  paths replaced by `[path]`, database errors replaced by "Internal server error"
  (`run-error.ts:76-110`).
- Secrets in provider messages are regex-redacted (`sk-…`, `Bearer …`, JWTs, `api_key=…`)
  (`packages/adapters/src/pi-runtime-errors.ts:68-84`).
- Note: the failure text is derived from the error stored on the run
  (`packages/adapters/src/run-turn.ts:1040`, `:1059-1071`), not written by the agent. In the
  failure path I read (`run-turn.ts:1035-1110`) there is no model turn in which the agent
  "explains" a provider failure; I did not check every caller, so "never" is unverified. A
  failed delegated bot-to-bot request returns "Could not complete the delegated request:
  {message}" to the requesting bot (`run-turn.ts:1100-1106`). I did not read the web/mobile
  components that render the summary.

---

## 3. Cost accounting

### 3.1 Per-call usage records (implemented)

- Every model invocation goes through `observedPiStream` ("Guard and account every actual model
  invocation, including tools, failures and subagents", `packages/adapters/src/pi-usage.ts:324-348`).
  Each call gets a UUID `callId` and emits a `usage` event (`pi-usage.ts:351-369`).
- Stored as one `UsageRecord` row per call with: space, bot, user, run, provider, model, input /
  output / cacheRead / cacheWrite / cacheWrite1h / reasoning / total tokens, `costUsd`,
  `costSource`, `pricingVersion`, `pricingSnapshot`, `usageSource`, unique `callId`,
  `operationKind` (default "answer"), `parentRunId`, `agentId`
  (`packages/db/prisma/schema.prisma:2004-2042`; write at `packages/db/src/usage.ts:45-61`,
  idempotent via `skipDuplicates`).
- Calls are bucketed: a call that uses or follows history-search tools is "retrieval" instead of
  "answer" (`pi-usage.ts:303-322`).
- For OpenAI- and Anthropic-style APIs (excluding providers whose id starts with `google`) the
  raw SSE usage frames are read by a wrapping `fetch` to know which fields the provider really
  reported (vs. zero-filled) (`pi-usage.ts:29-36`, `:218-219`, `:447-449`).
- The UI shows "runs, tokens and cost by model" under Settings → Usage (`docs/models.md:46-48`, stated).

### 3.2 Hosted credits: reserve → settle → reconcile (implemented)

Applies only when the deployment's key pays; "a personal connection never reaches this boundary"
(`packages/adapters/src/model-credit-observer.ts:13`).

- **Before each call** (`pi-usage.ts:427-446`, reservation precedes `started = true`): compute a worst-case cost = input-token estimate × highest input-side
  rate + max output tokens × highest output rate, across all pricing tiers, with 1-hour cache
  writes at 2× (`pi-usage.ts:627-657`). A model with no positive price is *refused* (not treated
  as free): "This model has no reliable price. Connect your own API key to use it."
  (`pi-usage.ts:641-647` returns `undefined`; `packages/adapters/src/model-credit-observer.ts:24-25`
  turns that into `NaN`; `packages/db/src/model-credits.ts:115-116` throws; the same check also
  refuses a single-call estimate above $10,000).
- That amount is atomically debited from the organization balance inside one transaction with
  `SELECT … FOR UPDATE`; if the balance is too small the call throws
  `MODEL_CREDITS_EXHAUSTED_ERROR` before any request is sent
  (`packages/db/src/model-credits.ts:100-160`). Amounts are integer micro-dollars (`:19`).
- With an observer, SDK retries are off: "Each guarded reservation covers one HTTP attempt, not
  hidden SDK retries." (`pi-usage.ts:450-457`).
- **After the call**: the hold is settled to actual cost, refunding the difference
  (`model-credits.ts:162-201`). If cost is unknown the hold stays: "Unknown usage leaves a visible
  hold; no timeout can invent a zero-cost result" (`model-credits.ts:203`).
- **Reconciler** (background): picks 5 pending holds per pass, first due 5 minutes after the
  reservation, re-leases each for 120 s; an attempt is treated as the last one once 5 earlier
  attempts are recorded (`reconciliationAttempts >= 5`, so about 6 in total); first asks the provider for the cost
  by request id (OpenRouter only: `packages/adapters/src/deployment-model.ts:68-73`), then falls
  back to its own token count priced at the model's cheapest rates (full rates if the user
  stopped the call), never more than was held
  (`packages/adapters/src/model-credit-reconciler.ts:15-19`, `:99-125`, `:133-187`;
  `model-credits.ts:155`). I read lines 1–200 of 305 of the reconciler.

### 3.3 Caps, and what happens at the cap

- **Operator per-user cap**: CLI `model-credit-cap.js set <email> <total-usd> | clear | status`
  (`apps/api/src/cli/model-credit-cap.ts:1`, `:14-19`), range $0–$10,000
  (`packages/db/src/model-credit-cap.ts:38-39`). It is a lifetime total with no reset
  (`docs/self-host-billing.md:80`, stated). Enforced inside the reservation transaction: if
  committed spend + this reservation > cap, throw "Usage limit reached. Contact support to
  continue." (`packages/db/src/model-credit-cap.ts:17-30`; `model-credits.ts:132-133`). Cap
  changes are written to an audit table (`model-credit-cap.ts:47-58`).
- Because the check uses the worst-case estimate, a call can be refused before the displayed
  remainder reaches zero, and calls already admitted can exceed the cap
  (`docs/self-host-billing.md:82-84`, stated; consistent with the code above).
- **Balance exhausted**: the call fails before being sent; the run fails with the
  "Not enough model credits…" sentence (section 2.6). For non-hosted (own-key) use, an
  "exhausted account" response from the provider triggers the backup chain but not same-model
  retry (`packages/adapter-kit/src/model-errors.ts:84-93`, `:111`, `:179-180`).
- There is no per-run or per-day token/cost budget in the files I read. There is a per-run
  *tool-call* budget (`host.toolCallBudget.exceeded`, `packages/adapters/src/pi-runtime.ts:1141`);
  I did not trace its limit — it belongs to the run-loop section.
- `packages/core/src/spending.ts` is unrelated to model cost: it parses prices on checkout pages
  for the bot's *purchase* spending limit (`packages/core/src/spending.ts:19-37`, `:67-88`).
  I did not read `packages/db/src/spending.ts` or `packages/adapters/src/spending-gate.ts`.

---

## 4. Prompt caching

- `packages/adapters/src/pi-cache-retention.ts` only decides which cache-retention *request
  preference* to send. Default when nothing is configured: `"short"` for `openai-responses`,
  `openai-completions`, `anthropic-messages`; nothing for other APIs (`:7-14`). `"long"` is only
  sent when explicitly requested. On Anthropic-style endpoints it is accepted unless the model's
  compat data says `supportsLongCacheRetention === false`, and it means 1-hour cache writes; on
  OpenAI-style endpoints it needs `supportsLongCacheRetention === true`. Unsupported
  combinations throw (`:26-43`, `:46-60`).
  The comment is explicit that this "cannot promise cache reuse or provider billing behavior" (`:4`).
- 1-hour cache writes are priced at 2× in the pre-call reservation (`pi-usage.ts:652`).
- Cache read/write tokens are stored per call (`schema.prisma:2019-2021`).
- "Cache-aware context": a connection may declare `cacheCapabilities.retentionMs`; the runtime
  then predicts `likely-warm` / `likely-cold` from the time since the last request and keeps the
  same history prefix while warm instead of re-selecting context
  (`packages/adapters/src/context-selection.ts:44`, `:713`, `:829-836`; described in
  `docs/self-host-models.md:157-174`). I read only those lines of `context-selection.ts`.
- `packages/adapters/src/pi-live-cache.ts` is **not** prompt caching, despite the name: it is a
  stale-while-revalidate cache for provider model *lists* (`pi-live-cache.ts:9-23`).

---

## 5. Observability

### 5.1 Structured logs (`packages/logging`, ~3,300 lines incl. tests)

- Structured logs to stdout, JSON by default in production and "pretty" in development;
  `LOG_LEVEL` default `info`; optional Axiom sink; optional Sentry for `error` logs
  (`docs/self-host-observability.md:8-15`, `:67-74`, stated; files named `axiom-sink.ts`,
  `console-sink.ts`, `sentry.ts` exist under `packages/logging/src/`, not opened).
- Context (job id, job type, trace id, span id, plus payload-derived fields such as `run.id`)
  is carried by `AsyncLocalStorage` and merged into every line
  (`packages/logging/src/context.ts:4-18`; job bindings `packages/logging/src/jobs.ts:91-99`,
  `run.id` mapping at `jobs.ts:17`; merge at `packages/logging/src/logger.ts:87`).
- **Redaction is on by default in the logger itself** (`packages/logging/src/logger.ts:88-92`):
  - any binding (at any nesting depth) whose key is one of 23 content names (`prompt`, `message`, `content`, `text`,
    `input`, `output`, `stdout`, `stderr`, `arguments`, `query`, `headers`, `email`, …) is
    replaced by `[Redacted]`, as is any key matching
    `password|secret|token|authorization|cookie|credential|apikey`
    (`packages/logging/src/redaction.ts:1-27`, `:113-125`);
  - free text has emails, bearer tokens, `key=value` secrets, `sk-…` keys, JWTs, home-directory
    user names and shared-page links removed (`redaction.ts:67-111`).
  Consequence: content logged under those key names is dropped, so logs are not a record of
  the conversation. This is by key name only: text logged under another key still appears after
  the free-text scrub, e.g. `run.failed` logs the user-facing error text under `reason`
  (`packages/adapters/src/run-turn.ts:1083-1088`). I did not audit all call sites, so "logs
  never contain user content" is unverified.

### 5.2 What is recorded per run and per tool call (implemented)

- `run.execution_started` with timing fields (`packages/adapters/src/executor.ts:432-434`).
- Per tool call: log line `agent.tool.completed` with run/space/thread/bot ids, tool name,
  outcome, duration — and a thread event of the same type with payload
  `{name, executionId, durationMs, outcome: succeeded|error|paused, error?, contentTypes?}`
  (`packages/adapters/src/tool-completion-audit.ts:60-103`, `:105-129`). Arguments and results
  are not in this payload (it can also carry `frameId`, `capturedAt`, `width`, `height` for
  screenshots, `:85-101`). A separate helper, `toolCompletionOutcome`, treats a command that
  returned normally but exited non-zero as failed (`tool-completion-audit.ts:45-58`); the audit
  payload's own `outcome` field does not look at the exit code (`:73`). I did not trace where
  `toolCompletionOutcome` is used.
- `agent.tool.refused` logs only a refusal *code*, never the sentence the model read
  (`tool-completion-audit.ts:158-183`, log call at `:176`).
- `run.loop_guard_stopped` with tool, reason (`repeated_calls` | `over_limit_actions`), count,
  consecutive failures (`tool-completion-audit.ts:185-207`). (The loop guard itself is outside
  my section.)
- `run.failed`: logged at **warn** when the cause is a provider outage, account problem, bad
  model output, sandbox rate limit or a spent computer allowance — "not server faults" — and at
  **error** for everything else (`packages/adapters/src/run-turn.ts:1073-1097`). That `error`
  logs go to Sentry is from the docs (`docs/self-host-observability.md:69-70`, stated).
- Model layer lines: `model.backup.unavailable` (type/code/status only — "Never log the message:
  credential diagnostics can quote the key", `pi-runtime-fallback.ts:429-438`),
  `model.context_limit.reduced|refused` (`:557-567`), `model.output_reservation.reduced` (`:591-597`),
  `model.primary_unavailable.backup_used` (`run-model-start.ts:56-60`).
- A rough grep found 435 `getLogger().<level>(` call sites on a single line in non-test `.ts`
  under `packages/` and `apps/` (multi-line calls not counted, so this is a lower bound).

### 5.3 Traces (optional, off by default)

- Enabled only if `OTEL_EXPORTER_OTLP_ENDPOINT` is set; otherwise the OTel SDK is never loaded
  (`packages/adapters/src/pi-telemetry.ts:8-23`). A bad config must not fail a run (`:20-23`).
- Span tree: `rakazo.agent.run` (bot id, run id, routine id) → `pi.ai.request` per model call
  (`pi-telemetry.ts:24-34`; `pi-usage.ts:370-378`) → `pi.agent.tool` span per tool execution
  (`packages/adapters/src/pi-runtime-tools.ts:489-494`, implemented; also
  `docs/self-host-observability.md:99-102`).
- Attributes are an **allowlist** of 18 names (ids, provider, model, stop reason, token counts,
  cost, tool name, tool success); anything else is dropped
  (`packages/adapters/src/pi-telemetry-otel.ts:14-34`, `:42-52`).
- Prompt, response, tool arguments and tool results are exported only with
  `OTEL_CAPTURE_CONTENT=true` (`pi-telemetry.ts:57-69`, `pi-telemetry-otel.ts:35-48`, `:148`).
  Exception messages/stacks are never attached to spans (`pi-telemetry-otel.ts:115-118`).
- Export is batched with a 2 s export timeout (`pi-telemetry-otel.ts:141-143`).

### 5.4 How an operator debugs a failed run (pieced together; partly unsure)

1. The run is finalized with the sanitized error text (`run-turn.ts:1040`, `:1059-1071`);
   `normalizeRunError` yields `summary` and `details` (one line per model when backups were
   involved) (`run-error.ts:284-288`). Client rendering not read.
2. Log line `run.failed`; the warn form carries class name, reason and active model
   (`run-turn.ts:1083-1088`). Correlation by `run.id` through the log context is assumed from
   `packages/logging/src/jobs.ts:17`, not traced for this job (unverified).
3. Thread events `agent.tool.completed` give the tool-by-tool sequence with outcome and duration.
   Users can optionally see this as a "tool activity" card; it is **off by default** "so chats
   stay clean", and the setting only changes rendering (`docs/tool-activity.md:8`, `:22-23`, stated).
4. `usage_records` rows by `runId` show each model call's tokens and cost
   (`packages/db/prisma/schema.prisma:2013-2024`, `:2041`).
5. If tracing is on, the span tree; with `OTEL_CAPTURE_CONTENT=true`, full content.
- `docs/troubleshooting.md` has two sections and one error code (`MCP_OAUTH_REDIRECT_MISMATCH`,
  `docs/troubleshooting.md:6`, `:30-34`); it is not a general run-debugging guide. I found no
  operator document that describes the steps above; the list is my reconstruction.

---

## 6. Tests and evaluations

### 6.1 Volume (tracked files, counted with `git ls-files`)

- 1,591 `*.test.ts(x)` files in total; 427 under `packages/adapters`; 113 under `packages/testkit`.
- 148 `*.postgres.test.ts`, 4 `*.docker.test.ts`, 2 `*.canary.test.ts`, 1 `*.e2e.test.ts`.
- 124 Playwright `*.spec.ts` files under `e2e/` directories (119 in `apps/web/e2e`).

### 6.2 Vitest setup

- One root config, 10 include globs, two projects: files that mock/stub/change env run isolated,
  the rest share a module graph per worker (`vitest.config.ts:7-33`, `:84-87`). Test timeout
  30 s, hook timeout 60 s (`vitest.config.ts:82-83`).
- Setup file forces offline emulators regardless of the developer's `.env`:
  `AGENT_RUNTIME=scripted`, `SANDBOX_PROVIDER=fake`, `WAKEUP_DRIVER=memory`, live model catalog
  off, media/paid services disabled, connector and email keys deleted, OTel endpoint deleted
  (`packages/testkit/src/pin-test-env.ts:24-55`). The provider pins are skipped when
  `VERIFY_PROVIDERS` is set (`:28`), database URLs are kept when `VERIFY_DATABASE` is set
  (`:44-47`), and the OTel/Axiom deletions are unconditional (`:49-55`).
- Rule text: "Keep tests deterministic and offline by default." (`AGENTS.md:14`);
  `pnpm test` = "Scripted runtime, fake sandbox, in-memory wakeup — no live connector or
  model-provider calls." (`CONTRIBUTING.md:29`).

### 6.3 What `packages/testkit` provides

- Its public export is tiny (`packages/testkit/src/index.ts:1-7`); the value is in the harness
  files and CLIs it contains.
- **Model emulator** (`packages/testkit/src/model-emulator.ts`, 218 lines): a loopback
  OpenAI-compatible HTTP/SSE server. The real agent loop and HTTP transport run against it. Each
  scripted step has an `expect(request)` assertion and a response of type `text`, `tool(s)`,
  `error` (status + message), `disconnect`, or `hold` (`model-emulator.ts:19-37`, `:39-52`).
  `assertComplete` must be called so unconsumed or unexpected steps fail the test (`:54-59`).
- The fakes themselves live in `packages/adapters/src` (e.g. `scripted-runtime.ts`,
  `fake-sandbox.ts`, `fake-browser.ts`, `fake-terminal.ts`, `email-emulator.ts`,
  `billing-emulator.ts`). The scripted runtime is a full `AgentRuntime` implementation with
  `capabilities.scripted: true` (`packages/adapters/src/scripted-runtime.ts:22-31`).
- Conformance tests: files named `*-conformance.test.ts` exist in `packages/adapters/src` for
  sandbox, browser, billing, email, secret store, key provider, cloud agent, paid services,
  payment wallet (seen in a file listing; **not opened** — I cannot say what they assert).
- CLIs: `evals.ts`, `flows.ts`, `canary.ts`, `computer-replay.ts`, `topology.ts`, `harness.ts`
  and others under `packages/testkit/src/cli/` (listing only).

### 6.4 Layers (condensed from `docs/agent-verification.md:9-18`, stated; commands confirmed in `package.json:26-38`)

The "Paid?" column is my reading of `docs/agent-verification.md:20-24` ("Default and PR tests
never require paid inference"), not a column in the source table.

| Layer | Real | Fake | Paid? |
|---|---|---|---|
| `pnpm test` | product functions | scripted agent, sandbox | no |
| `pnpm test:pi` | real agent loop + HTTP/SSE | loopback model, tool effects | no |
| `pnpm test:integration` | API, Postgres, executor, agent loop | model, sandbox | no |
| `pnpm test:computer-replay` | agent loop, Docker Chromium | model | no |
| `pnpm test:evals --live` | product + real model | sandbox, connected services | yes |
| `pnpm test:computer`, `test:flows` | real model + real computer | fixture site / simulated user | yes |

"Missing live credentials mean **not run**, not a passing model evaluation."
(`docs/agent-verification.md:25`).

### 6.5 CI (`.github/workflows`, 21 workflow files)

- `ci.yml` on push to main and on PRs (`ci.yml:2-5`): production build (`ci.yml:49-66`), lint
  (PRs only) + typecheck (`ci.yml:95-123`), unit tests in 6 shards with a 20-minute timeout
  (`ci.yml:163-194`), Postgres journeys in 6 shards with a 15-minute timeout
  (`ci.yml:276-285`, run line `:332`), plus small Python/Node script tests (`ci.yml:132-160`). On PRs only
  affected packages may run (`ci.yml:195-200`).
- `playwright.yml`: web e2e in 6 shards (`playwright.yml:48-55`, `:176`); "against the emulated
  API" is from `CONTRIBUTING.md:31` (stated).
- `nightly-verification.yml` (02:23 UTC daily) runs only the Playwright workflow for screenshots
  (`nightly-verification.yml:3-20`); no live model.
- `computer-replay.yml` on PR and manual (`computer-replay.yml:3-15`, `:43`);
  `topology-verification.yml` manual only (`topology-verification.yml:3-4`, `:24-26`).
- **No workflow runs a real-model evaluation.** Stated explicitly: "Live evaluations run only
  through an explicit local CLI invocation. They are not scheduled by the nightly workflow."
  (`docs/agent-verification.md:227-228`). I read the trigger and `run:` lines of 6 of the 21
  workflows, not the rest. Checker's addition: a grep of all 21 workflow files for
  `test:evals`, `test:flows`, `test:canary`, `test:computer` (other than
  `test:computer-replay`) and `--live` found no match, which supports the claim for those
  commands. Workflows such as `review-bot.yml` and `issue-triage.yml` were not opened and may
  call a model for other purposes (unverified).

### 6.6 Are there behavioural evals of the agent?

Two different things exist; keep them apart.

**(a) Deterministic scripted scenarios (run in CI).** They prove the *plumbing*, not the model's
judgement — the docs say so: "A scripted response can prove that a tool call executes correctly;
only a real model can demonstrate that it chooses a useful action for a natural request"
(`docs/agent-verification.md:5-7`). Relevant cases in `packages/testkit/src/pi-offline.test.ts`:
- provider drop + 503 after tool work → retried, effect not replayed (`:56-112`);
- "returns tool failure to the model and continues without claiming a successful write"
  (`:488-524`): the tool throws "Fixture write denied", the next model request must contain that
  text as the tool result, and the scripted model then says "The file could not be saved."
  This verifies the error *reaches* the model. It does **not** test recovery: the scripted model
  gives up, and that is the expected outcome of the test;
- provider rejection, interrupted SSE, cancel of a quiet stream, two isolated connections
  (`:526`, `:556`, `:573`, `:608`).

**(b) Real-model evals (manual, paid, not in CI).** `pnpm test:evals --live --provider … --model …
--trials 3` (`docs/agent-verification.md:212-218`). 16 task cases in `EVAL_CASES`
(`packages/testkit/src/evals/cases.ts:166-524`, 16 `id:` entries counted; the docs also say
"16-case suite", `docs/agent-verification.md:240-241`; ids such as `file-create`, `inbox-triage`,
`retrieved-injection`, `crm-update`, `uncertain-write`, `remember-preference`,
`release-routine`), plus separate suites for deliberation, group chat, routing, silence,
initiative, memory, recall, connected apps, long history (headings at
`docs/agent-verification.md:283-681`; not read in detail).
- Grading reads effects (files, service records, persisted state), not the model's claim: "A
  model's claim of completion is not sufficient. Cases do not receive repair prompts or coaching
  after a failure." (`docs/agent-verification.md:259-262`).
- Prose is judged by an LLM with a versioned rubric, never by keywords/regex (`AGENTS.md:15`;
  `docs/agent-verification.md:278-281`).
- Failures are categorised as agent outcome / product error / provider failure / harness failure
  / incomplete (`docs/agent-verification.md:269-270`).
- Recorded baseline: 45/45 over 15 cases × 3 trials on one model after harness fixes; the first
  run was 41/45 and all 4 failures were harness faults (`docs/agent-verification.md:230-234`, stated).
- Two cases inject a **tool fault** (found by grep; other suites in
  `packages/testkit/src/evals/` were not read in full):
  - `uncertain-write`: the CRM write returns an ambiguous outcome, and the grader requires that
    the agent list the records after it and that exactly one note and one write exist
    (`packages/testkit/src/evals/cases.ts:410-438`).
  - `apps-restricted-file` (connected-apps suite): the mail emulator rate-limits
    `search_threads` once with a 2 s retry time; the grader requires a successful
    `search_threads` after the `rate_limited` error, an attempt on the linked file that ends in
    `permission_denied`, and (by rubric) a reply that says the file could not be opened instead
    of answering from last year's file (`packages/testkit/src/evals/apps.ts:41-42`, `:273-300`;
    fault shape `packages/testkit/src/apps/app-emulator.ts:40`; described in
    `docs/agent-verification.md:656-660`). So this case grades retry after a transient tool
    error, and honest reporting of a hard failure; it does not grade finding another route.
- I found no eval where a tool returns "not found" and the agent is graded on discovering
  the right identifier by itself (the Lonora XAUUSD → XAUUSDm situation). This rests on a grep
  of `packages/testkit/src/evals/*.ts` for recover/retry/fail/fault wording, not on reading
  every suite (unverified as an absence claim).
  The eval sandbox also "returns an explicit error for model shell commands instead of pretending
  to run them" (`docs/agent-verification.md:252-255`), so shell-recovery behaviour is not covered there.
- `docs/evals/*` (3 files, 371 lines) are about conversation-history context strategies and a
  page-browser benchmark (headings only read: `docs/evals/history-findings.md:1-139`,
  `docs/evals/page-browser-bench.md:1`). Not about failure recovery.

---

## 7. What Lonora can take from this area

1. **Classify provider errors once, in one function, into 3 classes + "unknown = our bug"**
   (`packages/adapter-kit/src/model-errors.ts:3-31`; ranking in
   `packages/adapters/src/pi-runtime-errors.ts:128-147`). Drive retry, fallback, log level and
   user text from that single classification.
2. **Never show provider text to the owner.** Map to a short fixed sentence + at most one
   action, keep raw text in a details field (`packages/core/src/run-error.ts:223-232`). For
   Lonora the sentences would be Arabic and the "details" hidden entirely for a non-technical owner.
3. **Retry only before anything visible was sent**, buffer until then
   (`pi-runtime-fallback.ts:831-844`). Small fixed backoff (2/8/20 s) inside one time budget.
4. **Log failures the user can fix at warn, real faults at error** (`run-turn.ts:1073-1097`).
5. **Make tool errors carry the candidates** (`model-choice.ts:134-141`). This is the cheapest
   direct fix for "symbol not found": the broker tool should return the closest existing symbols
   in the error, as rakazo does for model names.
6. **Write a real eval for the complaint.** rakazo's `uncertain-write` and `apps-restricted-file`
   cases show the form: inject a fault in a fake service, grade on recorded calls and final
   state, not on prose (`cases.ts:410-438`; `packages/testkit/src/evals/apps.ts:273-300`). I
   found no "wrong identifier → find the right one" case in rakazo (grep only); Lonora would
   have to write it.
7. One per-call usage row keyed by a unique call id (`schema.prisma:2004-2042`) is enough for a
   single-owner product; the reserve/settle/reconcile ledger is not needed (see below).

---

## Weaknesses and risks seen in this area

- **Error classification by regex over English provider prose.** Long alternations decide
  whether to retry, switch model, or tell the user to pay
  (`packages/adapter-kit/src/model-errors.ts:74-82`, `:102`, `:131`, `:165`, `:190`;
  `packages/core/src/run-error.ts:383-411`). Each provider wording change can misroute a failure.
  The many special cases in comments (e.g. "OpenAI's per-minute limits link to billing",
  `model-errors.ts:193`) show how this grew. Lonora should classify on HTTP status and structured
  codes first and keep the text rules few.
- **`fallbackAwareModelStream` is one ~560-line closure** with many mutable locals (e.g.
  `buffered`, `retries`, `recoveredIdle`, `sizingFailure`, `startedAt`, `firstRetryableError`,
  `lengthRecovered`, `outputBudget`, `thinkingOverride` at `:445-457`, plus per-attempt
  `sawVisibleOutput`, `restart`) and a `restart` loop (`packages/adapters/src/pi-runtime-fallback.ts:303-861`). It handles retry,
  fallback, context shrink, output cap, reasoning-effort narrowing, thinking-signature drop and
  cut-reply continuation together. Hard to reason about and to change safely.
- **Vendor-specific patches inside the generic layer**: Groq request windows, OpenRouter
  affordable-output parsing, OpenCode session errors, ChatGPT usage-limit sentence
  (`pi-runtime-fallback.ts:29-32`, `:537-602`; `pi-runtime-errors.ts:86-94`;
  `model-errors.ts:120-121`). This contradicts the stated rule that vendor translation belongs
  only in adapters (`AGENTS.md:5`) only in spirit: these files are themselves inside
  `packages/adapters` (and `packages/adapter-kit`), so it is not a literal violation. It is
  maintenance cost.
- **Credit ledger complexity.** Reserve/settle/lots/expiry/reconciler with row locks and a
  multi-attempt reconciliation state machine (`packages/db/src/model-credits.ts:100-201`;
  `packages/adapters/src/model-credit-reconciler.ts:99-187`). Justified for a multi-tenant paid
  service; pure overhead for a single-owner agent.
- **Worst-case reservation can refuse a call the balance could actually pay for**, and admitted
  calls can exceed the cap (`pi-usage.ts:627-657`; `docs/self-host-billing.md:82-84`).
- **Unknown-priced models are refused on hosted credits** (`pi-usage.ts:641-647`) — correct for
  billing, but it is a hard failure the user sees as an error.
- **No per-run or per-day spend limit for own-key users** in the files read; the only caps are
  hosted-credit balance and the operator lifetime cap (`packages/db/src/model-credit-cap.ts:17-30`).
  A looping agent on the owner's own key is bounded only by other mechanisms outside this section.
- **Silent downgrade of a bot's model override.** If the override's connection is gone, the run
  uses the main/deployment model and drops the thinking level without telling anyone
  (`packages/adapters/src/model-roles.ts:105-136`).
- **Subscription OAuth relies on a hard-coded third-party client id and consumer sign-in
  endpoints** (`packages/adapters/src/pi-anthropic-oauth.ts:5-16`;
  `packages/adapters/src/pi-codex-catalog.ts:21-22` pins a ChatGPT backend URL and client
  version). These are not public API contracts and can break or be disallowed without notice.
- **Catalog depends on a weekly dependency bump of a third-party registry**
  (`.github/workflows/model-catalog-bump.yml:3-9`) plus hand-kept lists of refused ids
  (`pi-models.ts:72-84`). Model ids go stale between bumps.
- **Logs redact all content by key name** (`packages/logging/src/redaction.ts:2-26`). A field
  innocently named `message`, `text`, `query` or `input` is always `[Redacted]`. Safe, but it
  means logs alone cannot explain *why* the agent did something; an operator needs the database
  or content-capturing traces. Secret redaction by regex (`redaction.ts:67-85`;
  `pi-runtime-errors.ts:68-80`) is best-effort and can miss unusual key formats.
- **Tool-activity audit has no arguments or results** (`tool-completion-audit.ts:60-103`), so
  "which symbol did it ask for?" is not answerable from the audit event.
- **Agent-quality evals are manual and paid, never in CI** (`docs/agent-verification.md:20-25`,
  `:227-228`). A prompt change that makes the agent give up more often would not be caught by
  any automated gate. The only committed baseline is 15 cases × 3 trials on one model (`:230-234`).
- **The offline tool-failure test (`pnpm test:pi`) encodes "give up" as the expected behaviour**
  (`packages/testkit/src/pi-offline.test.ts:506`, `:523`). Fine as a transport test, but it is
  not evidence that the product recovers from tool failures.
- **Very large test surface** (1,591 test files; 6+6 CI shards, `ci.yml:163-170`, `:276-283`).
  Expensive to keep green; not a model for a small product.

## Not read / unsure

- Not read (or only grepped for a few lines): `packages/adapters/src/pi-oauth.ts` beyond lines
  23–63; `pi-live-catalog.ts` and `pi-codex-catalog.ts` beyond signatures/constants;
  `model-selection.ts` beyond its function list; `pi-openai-compatible-provider.ts` beyond lines
  84–98 (SSRF/private-endpoint checks taken from docs only); `model-credit-reconciler.ts`
  lines 200–305; `pi-usage.ts` lines 37–300 and 470–612; `context-selection.ts` (3 lines);
  `packages/db/src/spending.ts`, `packages/adapters/src/spending-gate.ts`; `model-credit-lots.ts`.
- Not read: the `*-conformance.test.ts` files; `packages/testkit/src/evals/runner.ts`,
  `judge.ts`, `report.ts`; the body of `docs/context-and-evals-tasks.md` (906 lines, headings
  only); most of `docs/agent-verification.md` after line 282; `docs/evals/*` bodies; 15 of the 21
  workflow files; Playwright configs and specs.
- Unsure: how many providers/models the bundled Pi registry contains (not counted).
- Unsure: whether the user is told when a run silently switched to a backup model. The run row's
  model columns are updated (`executor.ts:1888-1897`); I did not look for a UI notice.
- Unsure: where the user-facing run error summary is rendered (web/mobile code not read), and
  whether any chat channel (messaging apps) shows the same summary.
- Unsure: the size of the per-run tool-call budget (`pi-runtime.ts:1141`); not traced.
- Unsure: the docs/code difference on the default OpenRouter model
  (`docs/self-host-billing.md:36-37` vs `deployment-model.ts:6`) — may be an env override on the
  hosted service rather than a real contradiction.
- The 435 logger-call count (re-run by the checker: 435) and the "two evals inject a tool
  fault" finding come from greps, not from reading every file; treat both as approximate.

## Verification log

Independent check of this file against the repository at commit
`cd7e20e5da754d8d8deaf2780671ed34a38e2241` (HEAD confirmed). Nothing was executed except
read-only listing/grep/count commands; no test suite was run.

**Citations checked:** all backticked `path:line` / `:line` citations in the original text
(286 by a pattern count of the original file; `:line` continuations of a preceding path are extra) were opened at the cited lines. Counts were re-run: 1,591 test
files, 427 / 113 per package, 148 / 4 / 2 / 1 by suffix, 124 / 119 Playwright specs, 21
workflows, 435 logger call sites, 218 lines in `model-emulator.ts`, 3,327 lines in
`packages/logging/src`, 371 lines in `docs/evals/*`, 18 allow-listed span attributes, 8
recommended-model entries, 10 vitest include globs — all matched. Line numbers were right
almost everywhere; the errors found were in wording and scope, listed below.

**Corrections made (before -> after):**

1. Intro: "It does not contain anything that makes the agent try a different approach after a
   tool failure" -> scoped to "in the files read for this section", and marked as shown by a
   test only.
2. 1.3: vision "required for the `computer` role" -> a model with `images === false` is not
   accepted for it (that is what `model-roles.ts:29-32` says).
3. 2.2: "at most 3 retries" -> at most 3 delayed retries of an ordinary transient failure, and
   only when no backup resolved. "An idle timeout gets one extra retry" -> an idle timeout is
   retried at most once per call (2 s delay, window renewed). Added that the 120,000 ms constant
   is documented in code as a per-attempt header wait. "Thinking-only output is discarded and
   retried" -> it counts as nothing visible, so a failed call can be retried from scratch.
4. 2.3: "a safety margin of max(256, 10%)" -> the margin applies only when no context policy
   prepared the backup's context (`:277-279`).
5. 2.4: "Bounded by MAX_SELF_RECOVERIES_PER_RUN = 3" for all six items -> only the
   output-budget and cut-reply recoveries use that counter; the other four have their own
   one-shot flags. Added that cut-reply continuation is absent for subagents and that the
   "ask to continue" step was not opened.
6. 2.5: routine retry "is retried once" -> "can be retried once", with the two extra conditions
   visible in the file (no message/tool call yet; next occurrence not near). Added the 24 h cap
   on a provider-named reset.
7. 2.6: `run-error.ts:223-251` -> `:223-249`; "`recovery` is exactly one of ..., i.e. one
   button" -> optional, at most one; rendering unverified. "Fallback of last resort: Something
   went wrong" -> that sentence is only for the stored text "Internal server error"; the
   default for unmatched provider text is "The model provider returned an error." (`:382`).
   "The agent never gets a turn to explain a provider failure" (no citation) -> cited the
   failure path read and marked "never" unverified.
8. 3.1: raw SSE usage reading -> added the exclusion of `google*` providers (`pi-usage.ts:449`).
9. 3.2: added the code path from an unknown price to the refusal; fixed the quotation to the
   exact wording; "up to ~5 attempts" -> last attempt once 5 earlier attempts are recorded.
10. 4: "`long` is only sent if ... the adapter supports it" -> on Anthropic-style endpoints it
    is accepted unless compat says `supportsLongCacheRetention === false`.
11. 5.1: "JSON to stdout" -> JSON in production, pretty in development (docs). "25 content
    names" -> 23 (counted `redaction.ts:3-25`). "run id" in log context -> cited the mapping.
    "logs never contain what the user asked or what a tool returned" -> softened: redaction is
    by key name; `run.failed` logs error text under `reason`.
12. 5.2: "A shell command that ... exited non-zero counts as failed" -> true of the helper
    `toolCompletionOutcome`, but the audit payload's `outcome` ignores the exit code.
    `run.failed` warn list -> added the spent computer allowance; "(-> Sentry)" marked stated.
13. 5.3: "I did not find/open the tool span call site" -> found and cited
    (`pi-runtime-tools.ts:489-494`); span name `pi.agent.tool.*` -> `pi.agent.tool`.
14. 5.4: added citations to steps 1, 2 and 4; step 2's correlation marked unverified.
    Troubleshooting doc: "exactly one error code" -> two sections, one error code.
15. 6.2: "Opt-out only via VERIFY_PROVIDERS" -> also `VERIFY_DATABASE`; OTel/Axiom deletions
    are unconditional; range `:24-50` -> `:24-55`.
16. 6.4: marked the "Paid?" column as the analyst's inference.
17. 6.5: "build, lint + tsc (`ci.yml:95-123`)" -> build cited at `:49-66`, lint is PR-only,
    "tsc" -> typecheck; script tests `:134-160` -> `:132-160`; Playwright "emulated API"
    marked stated. Added a grep over all 21 workflows supporting "no real-model eval in CI".
18. 6.6 (the main factual error): "The one case that injects a tool fault is
    `uncertain-write` ... only the case above matched" -> refuted. `apps-restricted-file`
    (`packages/testkit/src/evals/apps.ts:273-300`) injects a rate limit and grades the retry.
    The "no wrong-identifier eval" statement is now marked as a grep-based, unverified absence
    claim. Section 7 item 6 and the "Not read / unsure" note updated to match.
19. Weaknesses: "about ten mutable flags" -> named the locals with a citation; the
    `AGENTS.md:5` remark now says the files are inside `packages/adapters`, so it is not a
    literal violation; "5-attempt" -> "multi-attempt"; "The CI tool-failure test" -> "the
    offline tool-failure test (`pnpm test:pi`)" because I did not confirm which CI job runs it.

**Remaining doubts:**

- Absence claims rest on greps or on a limited set of files: no per-run/per-day cost budget; no
  "wrong identifier -> find the right one" eval; no agent turn that explains a provider failure;
  no model call in the workflows that were not opened.
- Behaviour described from code comments rather than traced code: that the runtime "asks the
  model to continue" a cut reply; that `error` logs reach Sentry; that every log line of a run
  carries `run.id`.
- The docs/code difference on the default OpenRouter model ("Luna 6" in
  `docs/self-host-billing.md:36-37` vs `anthropic/claude-haiku-5.5` in `deployment-model.ts:6`)
  is confirmed as text; its cause is unknown.
- How clients render `summary` / `recovery`, and whether the user is told about a switch to a
  backup model, were not checked (web/mobile code not opened).
- Whether `pi-offline.test.ts` runs in a CI unit shard was not confirmed (it matches the vitest
  include glob `packages/*/src/**/*.test.{ts,tsx}`, `vitest.config.ts:9`, so probably yes).
- Statements the original marks "(stated)" were checked against the docs only, not against code.
