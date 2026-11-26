# Rakazo: how the model catalog is defined and shown

Repo: elie222/rakazo (TypeScript monorepo: `apps/api`, `apps/web`, `packages/{adapters,core,contracts}`). Studied read-only at HEAD (commit date 2026-11-26).

## 1. Short answer

- The model list is **not written in Rakazo's own source**. It is the **bundled registry of an npm dependency**, `@earendil-works/pi-ai` pinned at `1.6.0` (`packages/adapters/package.json`). The code calls `builtinModels()` from `@earendil-works/pi-ai/providers/all` and turns each registry model into a `PiCatalogEntry`. That dependency is not in the clone, so **the per-model data (price, context window, max output, wire protocol, thinking-level map) cannot be read from this repo**.
- Rakazo adds a small hand-written layer on top: `modelProviders` in `packages/adapters/src/models/model-provider-registry.ts` (recommended model per provider, subscription default model, sign-in metadata, hidden "unserved" ids, key-check URLs, deployment env defaults).
- The same catalog is served to every sign-in mode. Sign-in mode changes **which entries are available**, not the data. Mechanism: one provider id per plan, plus a per-model exclusion list.
- Runtime lists are fetched **on top of** the bundled list: ChatGPT/Codex per-account list (`https://chatgpt.com/backend-api/codex/models`) and each API-key provider's `GET {base}/models`. They are merged and filtered, never trusted blindly.
- Catalog updates ship **by code release** (bump the `pi-ai` version). There is no remote catalog file Rakazo itself hosts. Live probing is the only runtime update path.
- Custom models are allowed: an "openai-compatible" provider (any URL, user-entered ids), a "local" provider (operator-declared), and live-listed ids from a provider's models endpoint.

## 2. Catalog structure

### 2.1 Wire shape: `ModelCatalogEntry` (what the API returns and the UI renders)

`packages/contracts/src/models/model-connections.ts`, `ModelCatalogEntrySchema` (zod), abridged:

```ts
export const ModelCatalogEntrySchema = z.object({
  protocol: z.enum(["chat", "decisions"]).optional(),
  recommended: z.boolean().optional(),        // preselected for a new connection
  credentialIds: z.array(z.string()).optional(), // which connections can run it
  managed: z.boolean().optional(),            // served by deployment, no personal key
  creditOfferingId: Id.optional(),
  provider: z.string(), providerName: z.string().optional(),
  subscriptionName: z.string().optional(),    // "ChatGPT subscription" / "Claude subscription"
  id: z.string(), label: z.string(), billing: z.string(),
  auth: z.enum(["api-key", "oauth", "both"]).optional(),
  oauthLabel: z.string().optional(), authHint: z.string().optional(),
  subscription: z.boolean().optional(),
  signIn: ModelOAuthSignInModeSchema.optional(), // "device-code" | "auth-url"
  signInSetup: z.object({ label, url, note }).optional(),
  reasoning: z.boolean().optional(),
  thinkingLevels: z.array(ThinkingLevelSchema).optional(),
  defaultCapabilities: z.object({ images, reasoning, thinkingLevels }).optional(),
  images: z.boolean().optional(),             // vision
  contextWindow: z.number().int().min(1).optional(),
  maxTokens: z.number().int().min(1).optional(),
  placeholder: z.boolean().optional(),        // stand-in for "type your own id"
  catalogProbe: z.boolean().optional(),       // provider has a probeable /models URL
  routingFields: ..., dataRetentionControl: z.literal(true).optional(),
  endpointPresets: ..., live: z.literal(true).optional(), // not bundled, listed live
});
```

Fields asked about, mapped:

| Question | Field |
|---|---|
| id / display name | `id`, `label` (`catalogModelLabel()` rewrites upstream "(latest)" to "(auto-updates)") |
| provider | `provider`, `providerName` |
| context window / max output | `contextWindow`, `maxTokens` (from registry model card) |
| reasoning / effort levels | `reasoning`, `thinkingLevels` (from `getSupportedThinkingLevels(model)`); levels are `off, minimal, low, medium, high, xhigh, max` |
| capabilities | `images` (vision). **There is no `tools` flag**: every listed model is assumed to run agent tool calls. Instead `catalogModelServesAgents()` hides models that cannot. |
| pricing | **Not in the catalog entry.** Price lives on the registry model (`model.cost` with `input/output/cacheRead/cacheWrite` and optional `tiers`) and is used server-side only (credits, usage). |
| billing text | `billing` string (e.g. "Uses your Anthropic API key. Rakazo does not pay for model usage.") |

### 2.2 Server-side entry: `PiCatalogEntry`

`packages/adapters/src/runtime/pi/models/pi-models.ts`. Same fields plus `PiCatalogAuth = "api-key" | "oauth" | "both"`. Built once and cached in `buildPiCatalog()`:

```ts
const models = registerOpenAiCompatibleCatalog(
  registerLocalProvider(applyPiModelCompatibility(builtinModels())));
for (const provider of models.getProviders()) {
  const apiKey = Boolean(provider.auth.apiKey);
  const oauthAuth = loadProviderOAuth(provider.id);
  const auth = apiKey && oauth ? "both" : oauth ? "oauth" : "api-key";
  ...
  for (const model of providerModels) {
    const thinkingLevels = getSupportedThinkingLevels(model);
    entries.push({ provider: provider.id, id: model.id,
      recommended: isRecommendedCatalogModel(provider.id, model.id),
      label: catalogModelLabel(model.id, model.name, modelIds),
      reasoning: Boolean(model.reasoning), thinkingLevels,
      images: model.input.includes("image"),
      contextWindow: model.contextWindow, maxTokens: model.maxTokens, ... });
```

### 2.3 Rakazo's own provider overlay: `modelProviders`

`packages/adapters/src/models/model-provider-registry.ts`. Interface `ModelProviderDefinition` fields: `displayName`, `subscriptionName`, `recommendedModel`, `subscriptionModel {id, thinkingLevel}`, `unservedModels`, `keyCheck`, `deployment {keyEnv, defaultModel}`, `hostCredentials`, `signIn {mode, loginLabel, hint, billing, setup}`, `routingFields`, `media`. Relevant entries:

```ts
"openai-codex": {                       // ChatGPT subscription
  displayName: "OpenAI Codex",
  recommendedModel: "gpt-6.1-sol",
  subscriptionModel: { id: "gpt-6.1-sol", thinkingLevel: "low" },
  signIn: { mode: "device-code", loginLabel: "Sign in with ChatGPT", hint: "ChatGPT Plus/Pro", ... } },
openai:   { recommendedModel: "gpt-6-luna", media: { images: openAIImages, ... } },
anthropic: {
  recommendedModel: "claude-haiku-5-5",
  subscriptionModel: { id: "claude-opus-5-5", thinkingLevel: "low" },
  deployment: { keyEnv: "ANTHROPIC_API_KEY", defaultModel: "claude-sonnet-5" },
  signIn: { mode: "auth-url", loginLabel: "Sign in with Claude", hint: "Claude Pro/Max / key", billing: "" } },
openrouter: { recommendedModel: "anthropic/claude-haiku-5.5", deployment: {... "anthropic/claude-haiku-5.5"} },
google: { recommendedModel: "gemini-4-hydrogen", unservedModels: ["gemini-2.5-flash", ...] },
```

## 3. OpenAI and Anthropic model ids

**What I could not do:** list every id the catalog "currently ships". The ids come from `builtinModels()` in the external package `@earendil-works/pi-ai@1.6.0` (see `pnpm-lock.yaml`), which is not part of the clone and must not be installed here. So the complete list is **not recoverable from this repo**. Below are ids the repo itself proves are shipped (asserted by tests that require `builtinModels().getModel(...)` and `listPiCatalog()` to contain them) or names as defaults. Treat it as a lower bound.

Provider ids: `openai` (API key), `openai-codex` (ChatGPT subscription), `anthropic` (API key and Claude subscription share one provider id), plus the same models reached through `openrouter`, `azure`, `amazon-bedrock`, `opencode`, `vercel-ai-gateway`.

Confirmed by `packages/adapters/src/runtime/pi/models/pi-current-models.test.ts` ("ships %s/%s natively"):

- `openai`: `gpt-6.2-sol`, `gpt-6.2-astra`
- `openai-codex`: `gpt-6.1-sol`, `gpt-6.2-sol`, `gpt-6.2-astra` (all with efforts `minimal, low, medium, high, xhigh, max`, image input)
- `anthropic`: `claude-fable-5-2`, `claude-sonnet-5-5` (efforts `low, medium, high, xhigh, max`, image input)
- Bedrock Anthropic: `anthropic.claude-sonnet-5-5` (+ `us.`/`eu.`/`global.` prefixes), `global.anthropic.claude-fable-5-2`, `in.anthropic.claude-opus-5`, `in.anthropic.claude-sonnet-5`, `in.anthropic.claude-haiku-4-5-20251001-v1:0`
- Bedrock OpenAI: `openai.gpt-6-luna`, `gpt-6-sol`, `gpt-6.1-sol` (+ prefixes)
- OpenRouter: `anthropic/claude-fable-5.2`; opencode: `claude-haiku-5-5`, `claude-sonnet-5-5`

Named in code or tests as defaults or used ids (not proof of full catalog membership): `gpt-6-luna` (OpenAI recommended), `claude-haiku-5-5` (Anthropic recommended), `claude-opus-5-5` (Anthropic subscription default), `claude-sonnet-5` (Anthropic deployment default), `gpt-6.1-sol` (Codex), `gpt-6-sol`, `gpt-6-astra`, `claude-opus-5`, `claude-sonnet-4-5`, `claude-opus-4-5`, `claude-haiku-4-5`, `gpt-5.3-codex`, `gpt-5.3-codex-spark` (hidden for ChatGPT sign-in, see 4.2), `gpt-4o`, `gpt-4.1`.

Not found: any in-repo table of prices or context windows for these models. One test pins Bedrock prices (`us.openai.gpt-6.1-sol` input 2.2 / output 11 per M tokens, with a tier above 272000 input tokens) only to show they come from the registry.

## 4. Control flow

### 4.1 Building the list (server)

1. `listPiCatalog()` (`pi-models.ts`) lazily runs `buildPiCatalog()` once and caches it. It calls `applyPiModelCompatibility(builtinModels())` (`pi-model-compat.ts`: clamps unsendable Google thinking levels, disables Bedrock strict mode for one Haiku id, turns off the `developer` role for non-OpenAI providers, canonicalizes provider ids), then `registerLocalProvider` and `registerOpenAiCompatibleCatalog` to add the "local" and "openai-compatible" providers.
2. Per provider it merges registry data with `modelProviders[provider]`: display name, `signIn` metadata, `recommended` flag, routing fields, and `auth` ("both" when the provider has an API-key auth and an OAuth login).
3. It fills `hiddenCatalogKeys` via `catalogModelServesAgents()`: `:batch` ids on OpenRouter, zero-price OpenCode free tier, and each provider's `unservedModels` (e.g. retired Gemini 2.5, Groq llama ids).
4. `listPiCatalog()` applies `RAKAZO_MODEL_PROVIDER_ALLOWLIST` (`model-provider-allowlist.ts`): providers outside the comma list are removed from catalog, runs, and imports.
5. If `PI_DEFAULT_MODEL` names an OpenRouter id missing from the registry, one extra entry is prepended ("Configured via PI_DEFAULT_MODEL").

### 4.2 Does it differ by sign-in mode?

- Separate providers per plan: `openai-codex` (ChatGPT sign-in, device code) vs `openai` (API key). `anthropic` is one provider; its entries have `auth: "both"` and `signIn.mode = "auth-url"`.
- `catalogModelAvailableForAuth()` in `pi-catalog-availability.ts` is the only static per-auth filter: `OPENAI_CODEX_CHATGPT_SUBSCRIPTION_EXCLUDED_MODEL_IDS = {"gpt-5.3-codex-spark"}` is hidden when the credential is `oauth`, or when disconnected and the provider offers only OAuth. An API key can still use it.
- `listAvailablePiCatalog(authByProvider, authByModel)` applies this per entry using the credential that would actually serve it (per-model override, then provider preference, then "disconnected").
- Everything else (efforts, context window, vision) is identical across modes for a given provider.
- Subscription default differs from key default: `subscriptionSignInChoice()` in `model-selection.ts` swaps an untouched `recommendedModel` for `subscriptionModel` (Anthropic: `claude-opus-5-5` at `low`; Codex: `gpt-6.1-sol` at `low`).
- User-facing statement of the rules: `docs/model-subscriptions.md` (ChatGPT sign-in under provider "OpenAI Codex", Claude sign-in under "Anthropic"; API keys are separate API billing; available models can differ from the ChatGPT app).
- Sign-in mechanics: `pi-oauth.ts` (`SUBSCRIPTION_SIGN_IN_PROVIDERS`, `CHATGPT_OAUTH_PROVIDER="openai-codex"`, `ANTHROPIC_OAUTH_PROVIDER="anthropic"`), `pi-chatgpt-device-code.ts`, `pi-anthropic-oauth.ts` (PKCE authorize at `claude.ai/oauth/authorize`, user pastes the code), web hook `apps/web/src/lib/models/use-model-oauth-signin.ts`. Routes: `models.beginOAuth / submitOAuthCode / completeOAuth / finishOAuth / cancelOAuth` in `apps/api/src/routes/models.ts`.

### 4.3 Per-request catalog the API returns

`models.list` (`apps/api/src/routes/models.ts`) -> `chatCatalog(actor)` -> `catalogForSpace()` in `apps/api/src/routes/context.ts`:

1. `modelCredentialAuthKindsForSpace()` finds, per provider and per model, which credential kind (`oauth` / `api_key` / `openai_compatible` / `disconnected`) and which secret id governs it.
2. `listAvailablePiCatalog(auth...)` gives the static, auth-filtered base.
3. `codexLiveCatalogsForSpace()` and `providerLiveCatalogsForSpace()` fetch live lists in parallel (4.4).
4. `applyCodexLiveCatalog()` then `applyProviderLiveCatalog()` merge them; `withLiveModelSettings()` adds per-connection settings.
5. Credit offerings (hosted credits) append or restrict entries; the `approval` role also gets `decisionModelCatalog()`.
6. `offeredCatalog(merged, selected)` drops hidden models **except** ones the account already saved (bot, routine, role choice, deployment default, per-credential preference), via `savedCatalogSelections()`. Saved choices never vanish.
7. `withServingConnections()` stamps `credentialIds` when two accounts of one provider can run different models.

### 4.4 Runtime fetches from providers (merge and filter)

**ChatGPT/Codex per-account list** (`pi-codex-catalog.ts`):
- `GET https://chatgpt.com/backend-api/codex/models?client_version=0.169.1` with bearer plus `chatgpt-account-id`. Never refreshes tokens; an expired bearer returns no list.
- `parseCodexCatalog()` keeps only `visibility === "list" && supported_in_api`; any malformed item rejects the whole response. Reads `slug`, `supported_reasoning_levels[].effort`, `context_window`, `input_modalities`, `additional_speed_tiers`.
- `CodexCatalogCache` (SWR): TTL 15 min, failure TTL 1 min, wait 1.5 s, stale answers allowed 4 h, 256 entries.
- `applyCodexLiveCatalog()`: ignored unless it shares at least one slug with the bundled list ("untrusted" otherwise). A bundled entry is kept only if the account lists it (this can restore Codex Spark for an account that has it). Unknown live slugs are added via `liveCatalogEntry()`. Live context window, image input and efforts overwrite the entry's.

**API-key providers** (`pi-live-catalog.ts`, `pi-live-cache.ts`):
- Only providers whose registry models share one pinned HTTPS base URL on an `openai-completions` or `openai-responses` API get `catalogProbe` (`pinnedCatalogProbeBaseUrl()`); the probe is `GET {base}/models` with the user's key. Cache: TTL 6 h, failure 10 min, deadline 5 s, stale max 24 h. The key is decrypted only to probe; cache identity is secret id plus a ciphertext hash.
- Trust rule `trustedProviderModels()`: a live list is used only if it contains at least 25% of that provider's bundled ids.
- Retired bundled ids the live list omits are dropped (unless saved). New live ids are added only if `isChatModelId()` passes (regex excludes embed, whisper, tts, image, audio, realtime, moderation, rerank, video, etc.).
- A new live id inherits capabilities from its closest sibling (`liveModelSibling()` in `pi-live-model.ts`: longest common id prefix; same family only if the ids differ by a date or `latest` suffix, else text-only, reasoning off, default context window 262144). Marked `live: true`.
- Kill switch: `RAKAZO_LIVE_MODEL_CATALOG=off` (`liveModelCatalogEnabled()`; an invalid value stops startup).

### 4.5 Defaults

1. New connection preselects `recommendedModel` via `defaultCatalogModelId()` (model-selection.ts): recommended entry among the provider's offered and auth-available entries, else the first. Web side: `pickCatalogModelId()` in `packages/core/src/models/model-providers.ts` (saved id, then its basename for aggregator-prefixed ids, then recommended, then first).
2. Subscription sign-in uses `subscriptionModel` (4.2); new ChatGPT accounts go through `resolveCodexOAuthDefaultModel()`, which keeps the requested model if that account lists it, else the account's recommended or first.
3. Deployment-wide default for members with no model: `resolveDeploymentModel()` in `deployment-model.ts` reads `PI_DEFAULT_PROVIDER` (default `openrouter`), `PI_DEFAULT_MODEL`, and the key env named in `modelProviders[x].deployment` (default models: OpenRouter and Anthropic as listed in 2.3). An admin can override at runtime in Settings -> Models -> Default for everyone (`apps/api/src/models/deployment-model-settings.ts`, `DeploymentSettings` row), allowed only when model credits are not in use. Docs: `docs/self-host-models.md`.
4. Per-purpose "roles" (main, approval, computer, image, video): `effectiveModelRole()` / `deploymentModelRole()` in `model-roles.ts` fall back from the member's choice to the deployment's. `models.setDefault` in `routes/models.ts` saves the main model after `prepareStoredModelAuth` checks.
5. Thinking level: `clampCatalogThinkingLevel()` (`model-providers.ts` in core) maps a requested level to the nearest supported one (higher first, then lower); `off` becomes null.

### 4.6 How a user or agent picks a model

- **User, web UI:** model settings pages (`apps/web/src/pages/model-settings/*`, `apps/web/src/pages/shell/composer/composer-model-picker.tsx`; not read in detail) call `models.list` / `models.forRole`. `connectedModelOptions()` (`apps/web/src/lib/models/model-catalog.ts`) wraps `connectedModelChoices()` from core and localizes entries. Popular providers rank first (`POPULAR_MODEL_PROVIDER_IDS = openai-codex, anthropic, openai, openrouter, google`). The composer picker visibility is a local preference (`composer-model-picker-preference.ts`, localStorage key `rakazo.composerModelPicker`, "on"/"off").
- **Free-form server model list:** `FoundModelPicker.tsx` shows ids found on a custom server with search.
- **Agent/bot:** per-bot `modelProvider`, `modelId`, `thinkingLevel`. Agent tools call `resolveModelChoice()` (`model-choice.ts`) which takes a loose name ("Claude Sonnet", "gemini flash", `provider/id`) and matches it only against `connectedModelChoices()` (models this user can actually run). Ranking: exact id first; else every word must appear; ties go to the bot's current provider, then the plainest family, then the newest version. Ambiguity returns an error listing up to 5 candidates for the agent to ask about. Used by `packages/adapters/src/bots/own-bot-settings.ts` (a bot changing its own model or effort) and `packages/adapters/src/tools/fleet-tools.ts` (spawning a child bot). Then `validateBotModelChange()` re-validates credential, auth restrictions, and allowed thinking levels. There is no tool that lists the catalog for the agent beyond this resolver's error messages.
- **Validation at run time:** `connectionServesModel()` (model-selection.ts): a bundled model passes unless auth-restricted; an unbundled id must appear in that connection's live list (or be a saved selection); a pinned provider with no connection fails with "Connect that model provider first".

### 4.7 Custom and other models

- `openai-compatible` provider (`pi-openai-compatible-provider.ts`): catalog stand-in entry has `placeholder: true` and `endpointPresets`; the user types a URL and key, the server probes `GET /models` (`probeOpenAiCompatibleModels`), and stores per-model settings (images, reasoning, thinkingLevel, maxTokens) in the encrypted secret. Defaults when the server reports nothing: context 262144, max tokens 4096 (`DEFAULT_MODEL_CONTEXT_WINDOW`, `DEFAULT_MODEL_MAX_TOKENS`); images and reasoning assumed on for public hosts, off for private hosts (`compatibleModelDefaults()`). Private/loopback URLs are gated by deployment policy; keyed URLs must be HTTPS.
- `local` provider: operator-declared via `RAKAZO_LOCAL_MODELS`.
- Host-credential providers (Bedrock, Vertex, Claude Code CLI, OpenCode CLI, Antigravity CLI) need no key in the UI.
- Live-listed ids not in the bundle are allowed for probeable providers (4.4). An id outside the bundle is accepted when the provider has a live catalog that lists it (or it is a saved selection); `connectionServesModel()` returns true for ids no live catalog could list.

### 4.8 How the catalog is updated

- Bundled data: bump `@earendil-works/pi-ai` in `packages/adapters/package.json` (a code release). Rakazo tests (`pi-current-models.test.ts`) assert specific new ids ship, which is how a bump is verified. No remote catalog JSON is fetched by Rakazo for the model list.
- Rakazo-only changes (recommended model, retired ids, sign-in copy): edit `modelProviders` in `model-provider-registry.ts`.
- Between releases: live probing (4.4) adds and retires ids for connected accounts, with 6 h / 15 min caches.
- Hosted-credit offerings come from `modelCreditOfferings()` (deployment configuration, `packages/adapters/src/model-credits/offerings.ts`, not read) and require a price: `creditsCanPriceModel()` uses `maximumModelCallCost(model.cost, 0, 0)`, which treats all-zero rates as "unknown price" and refuses to reserve a call.

## 5. Not found / not read

- The full model list and any price table (lives in `@earendil-works/pi-ai`, outside the clone).
- `packages/adapters/src/model-credits/offerings.ts`, `apps/web/src/pages/model-settings/*` and the composer picker components were located but not read.
- No `tools`/function-calling capability flag exists in the catalog entry; tool support is assumed.
- No per-model "knowledge cutoff" or "release date" field in the entry.

## 6. What Lonora should copy / avoid

Lonora: Python FastAPI server, React web, Expo mobile; subscription sign-in (OpenAI, Anthropic) plus API keys, and a fixed pre-installed catalog.

Copy
1. **A fixed catalog in code, one typed entry shape.** Define one dataclass/Pydantic model (id, label, provider, auth modes, context window, max output, thinking levels, vision, price per M tokens) in a single Python module and serve it from one `/models` endpoint; the web and mobile clients render it and never hard-code ids. Rakazo's `ModelCatalogEntry` is a good field list; add a `tools` flag and `price` explicitly, which Rakazo lacks in the entry.
2. **Separate provider ids per billing channel** (`openai` key vs `openai-codex`/ChatGPT sign-in; one `anthropic` with `auth: both`) and a small per-model "not available with this sign-in" exclusion set, rather than duplicating catalogs per mode.
3. **A provider overlay table** next to the data: `recommended_model`, `subscription_model` (+ default effort), `unserved_models`, `key_check_url`. Keep "what we know about a provider" separate from the model list so a model bump does not touch it.
4. **Default choice rules:** recommended entry among those the credential can run, else first; swap in the subscription default only when the user left the key default untouched; clamp effort to the nearest supported level instead of erroring.
5. **Never let saved choices vanish.** Hide retired or unservable models from pickers but keep any model a bot, routine, or role already uses, so edits still work and runs fail with a clear "connect/choose another model" message.
6. **Agent model picking through one loose-name resolver** limited to models the user can actually run, with deterministic ranking and an "ambiguous, ask the user" error listing candidates. Revalidate after resolving.
7. **If live lists are added later**, copy the safety rules: a small allow-regex for chat ids, a "trust only if it overlaps >=25% of the bundled list" check, SWR cache with failure TTL and stale cap, bounded response size, never refresh tokens on the catalog path, key never in cache identity, one env kill switch.
8. **Price unknown is not free:** treat a missing or all-zero price as "cannot reserve/spend" (Rakazo's `maximumModelCallCost`), important for a trading assistant's cost caps.

Avoid
1. **Do not depend on a third-party package for the model data without a local override.** Rakazo cannot show or review its own list in-repo; Lonora should keep the list as reviewable data (a Python module or JSON checked in, with a test that asserts each shipped id) so a price or limit change is a visible diff.
2. **Do not copy the breadth** (about 25 providers, Bedrock/Vertex host credentials, media providers, credits, per-space overrides, role choices). Lonora only needs OpenAI and Anthropic, sign-in vs key, one default, and per-agent override.
3. **Avoid the heavy catalog-assembly pipeline** (`catalogForSpace` merges auth kinds, Codex live list, provider live lists, credits, saved selections, serving connections per request). Start with static list filtered by the user's connected credential kinds; add live probing only for ChatGPT accounts if plan-specific models matter.
4. **Avoid alias labels from upstream** ("latest" marker): Rakazo needs `catalogModelLabel()` to fix misleading names; write labels by hand in Lonora.
5. **Anthropic subscription sign-in uses a public CLI OAuth client id** (`pi-anthropic-oauth.ts` carries the Claude Code client id and scopes). Check provider terms before relying on that path in a product; API keys are the safer fallback.
6. **Keep trading-safety in mind:** model choice for an autonomous trading agent should be owner-controlled; copy the "agent may only choose among connected, allowed models and the change is validated" rule, and consider requiring owner approval to switch an agent that has trading authority.
