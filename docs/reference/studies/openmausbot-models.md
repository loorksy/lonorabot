# OpenMausBot: how the model list is defined, shown and picked

Repo studied (read only): `openmausbot` checkout, HEAD `140172d` (2026-11-26, v0.1.182). OpenMausBot is a TypeScript app that does not call model APIs itself for its main engines: it drives CLIs (Claude Code, Codex, Cursor, Grok, Kimi, Antigravity, ...) and OpenAI-compatible HTTP endpoints. So "the model catalog" is really several layers, one per engine, with one shared remote-updatable manifest on top.

## 1. Short answer

- There is **no single in-code list**. There are four sources:
  1. A **bundled JSON manifest** (`server/model-manifest/model-manifest.json`), validated by zod at load, which is a fixed pre-installed list for `claude`, `cursor`, `grok`, `kimi`, `antigravity`, plus a price table. It is **refreshed from GitHub raw** at runtime (remote file, hourly).
  2. A **hard-coded TypeScript constant** for OpenAI/Codex: `STATIC_CODEX_MODELS` in `server/drivers/codex-catalog.ts`. It is only a fallback; the real list comes live from `codex app-server` (`model/list`).
  3. **Live discovery** from the engine itself: Codex app-server, Pi RPC `get_available_models`, ACP engines, gateway `GET {base}/models`, local Ollama-style hosts.
  4. A **models.dev snapshot** (`server/model-catalog/models-dev.snapshot.json`, 220 providers) with its own fetch/cache store (`server/model-catalog/catalog.ts`). In this checkout I found **no importer** of `ModelCatalogStore`/`catalogEntries` outside tests, the build script and the bundler, so I could not confirm it feeds a picker today (see section 9).
- Fields on a picker row (`ModelCatalog` in `server/contracts.ts`): `id`, `label`, `custom`, `loaded`, `provider`, `contextWindow`, `variants`, `effortLevels`, `orgBlocked`, `needsCliUpdate`, `local`. There is **no max output, no tools/vision flags and no price on a picker row**. Prices live in a separate table (`prices` in the manifest). tools/vision/reasoning flags exist only in the models.dev snapshot rows.
- Default: a per-engine `default` field, plus a cross-engine ranking for new bots (Claude account, then ChatGPT plan, then Gemini, Grok, others).
- Custom models are allowed (extras from `settings.json`, `~/.codex/config.toml`, gateway `/models`, typed ids).

## 2. Catalog structure (excerpts)

### 2.1 Manifest schema: `server/model-manifest/schema.ts`

```ts
export const MANIFEST_ENGINES = ["claude", "cursor", "grok", "kimi", "antigravity"] as const;
const model = objectOf({
  id: modelId(engine),
  name: label(120),
  aliases: z.array(modelId(engine)).max(20).optional(),
  status: z.enum(["current", "legacy"]),
  contextWindow: z.number().int().positive().max(100_000_000).optional(),
  minCliVersion: z.string().regex(CLI_VERSION).optional(),
  variants: z.array(objectOf({ id: ..., label: label(40) })).max(20).optional(),
});
return objectOf({ default: modelId(engine), models: z.array(model).min(1).max(200) })
  .superRefine(... "the default must be a current model" ...)
// manifest = { version: 1, updatedAt, engines: { claude, cursor?, ... }, prices?: Record<id, {inputPerMillion, cachedInputPerMillion?, outputPerMillion, asOf, source, changes?[]}> }
```

Rules worth noting: `id` is validated per engine by regex (`ENGINE_MODEL_ID`) because it reaches a command line; the id `default` is reserved; ids and aliases must be unique per engine; the default must be `status: "current"`; `legacy` models stay valid in saved bots but are not offered for new picks (`engineCatalogFrom` in `server/model-manifest/bundled.ts` filters `status === "current"`).

### 2.2 Manifest data: `server/model-manifest/model-manifest.json` (`updatedAt` 2026-11-24T06:00:00Z)

```json
{"id": "claude-fable-5-2", "name": "Claude Fable 5.2", "status": "current", "contextWindow": 1000000, "minCliVersion": "2.1.321"}
{"id": "claude-opus-5-5[1m]", "name": "Claude Opus 5.5 (1M)", "status": "current", "contextWindow": 1000000}
{"id": "gemini-3.8-flash", ..., "aliases": ["gemini-3.8-flash-high", ...], "variants": [{"id":"low","label":"Low"}, ...]}
```

Other engines in the manifest: cursor (default `auto`, 5 rows), grok (default `grok-4.7`, 3 rows), kimi (default `kimi-code/k3`, 4 rows), antigravity (default `gemini-3.8-flash`, with thinking-level `variants`). The `[1m]` suffix is Claude Code's switch for the 1M context.

### 2.3 Runtime picker shape: `server/contracts.ts` `interface ModelCatalog`

```ts
export interface ModelCatalog {
  default: string;
  options: Array<{ id: string; label: string; custom?: boolean; loaded?: boolean;
    provider?: string; contextWindow?: number; variants?: ModelVariantOption[];
    effortLevels?: readonly EffortLevel[]; orgBlocked?: true; needsCliUpdate?: string; local?: LocalModelFacts; }>;
}
```

### 2.4 Price entry (manifest `prices`, keyed by model id or `vendor/model`)

```json
"gpt-6-sol": {"inputPerMillion": 2, "cachedInputPerMillion": 0.2, "outputPerMillion": 10, "asOf": "2026-11-20", "source": "https://developers.openai.com/api/docs/pricing"}
```
61 entries. `changes[]` lets a price change on a date (`listPriceFor` in `server/model-prices.ts` picks the one in effect). Used for cost estimates only (`estimatePriceFor`, `ledgerCost`), never in the picker.

### 2.5 models.dev row (`server/model-catalog/trim.ts` `CatalogModel`)

```ts
{ id, name, tool_call: true, reasoning: boolean, attachment: boolean,
  modalities: { input: string[] }, release_date?, limit?: { context: number }, cost?: { input?, output? }, status?: "alpha"|"beta" }
```
This is the only place with reasoning / attachment (vision) / modalities flags. No max output is kept (`limit` is context only).

## 3. Model ids shipped today

### Anthropic

Picker list (Claude Code engine, manifest `engines.claude`, default `claude-sonnet-5`):
`claude-fable-5-2`, `claude-fable-5-1`, `claude-fable-5`, `claude-opus-5-5`, `claude-opus-5-5[1m]`, `claude-opus-5`, `claude-sonnet-5-5`, `claude-sonnet-5` (default), `claude-haiku-5-5`, `claude-haiku-4-5`. (All `current`; no `legacy` rows.)

Price table also has: `claude-haiku-4-5-20251001`, plus OpenRouter-style `anthropic/claude-fable-5.2`, `.5.1`, `.5`, `claude-opus-5`, `claude-sonnet-5`, `claude-haiku-4.5`.

models.dev snapshot `anthropic` provider (taken 2026-09-30): `claude-fable-5`, `claude-fable-5-1`, `claude-haiku-4-5`, `claude-haiku-4-5-20251001`, `claude-opus-4-5`, `claude-opus-4-5-20251101`, `claude-opus-4-6`, `claude-opus-4-7`, `claude-opus-4-8`, `claude-opus-5`, `claude-opus-5-5`, `claude-sonnet-4-5`, `claude-sonnet-4-5-20250929`, `claude-sonnet-4-6`, `claude-sonnet-5`, `claude-sonnet-5-5`.

### OpenAI

Hard-coded fallback `STATIC_CODEX_MODELS` in `server/drivers/codex-catalog.ts`, default `gpt-5.6-sol`:
`gpt-6.2-astra`, `gpt-6.2-sol`, `gpt-6-astra`, `gpt-6-sol`, `gpt-6-luna` (these five labeled "(availability unverified)"), `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.3-codex-spark`. Comment: "Only used when live discovery fails; these rows do not establish account access."

Price table (manifest) OpenAI ids: `gpt-6-luna`, `gpt-6-sol`, `gpt-6.2-astra`, `gpt-6.2-sol`, `gpt-6.1-sol`, `gpt-6.1-terra`, `gpt-6-astra`, `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.3-codex` (plus `openai/...` aliases). The Cursor manifest list also carries `gpt-5.3-codex`.

models.dev snapshot `openai` provider: `gpt-4.1`, `gpt-4.1-mini`, `gpt-4o`, `gpt-4o-2024-08-06`, `gpt-4o-2024-11-20`, `gpt-4o-mini`, `gpt-5`, `gpt-5-mini`, `gpt-5-nano`, `gpt-5-pro`, `gpt-5.1`, `gpt-5.2`, `gpt-5.2-pro`, `gpt-5.3-codex`, `gpt-5.3-codex-spark`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.4-nano`, `gpt-5.4-pro`, `gpt-5.5`, `gpt-5.5-pro`, `gpt-5.6`, `gpt-5.6-luna`, `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-6-astra`, `gpt-6-luna`, `gpt-6-sol`, `gpt-6.1-sol`, `gpt-daybreak-blue-latest`, `gpt-daybreak-red-latest`, `gpt-realtime-2.1`, `o3`, `o3-pro`.

Note: the OpenAI list actually shown to a ChatGPT-plan user is whatever `codex app-server` returns, not the static list.

## 4. Control flow: how the list reaches the picker

### 4.1 Claude engine (manifest-driven)

1. `server/model-manifest/bundled.ts` imports `model-manifest.json`, parses it with `parseModelManifest(..., { strict: true })` and throws at load if invalid. This is the fixed, pre-installed list (`BUNDLED_MODEL_MANIFEST`).
2. `server/model-manifest/manifest.ts` `ModelManifestStore` starts with that bundle. `current()` reads the disk cache once (`<DATA_DIR>/providers/model-manifest/model-manifest.json`), and uses it only if its `updatedAt` is not older than the bundle ("A release can correct a model before the next successful fetch").
3. `startModelManifestRefresh()` (called from `server/harness/registry.ts`) runs a background refresh after launch settles, then every `MANIFEST_TTL_MS` (1 h). `GET /api/instances` (`server/routes/instances.ts`) also fires `modelManifest().refreshOnDemand()` (5 min TTL) without waiting.
4. `download()` fetches `MODEL_MANIFEST_URL` = `https://raw.githubusercontent.com/milind-soni/OpenMausBot/main/server/model-manifest/model-manifest.json` with `redirect: "error"`, 10 s timeout, 512 KB cap, then `parseModelManifest` (non-strict: unknown fields ignored so new fields do not freeze old installs; any real error rejects the whole file). A download with a lower `updatedAt` than the current copy is ignored. On a change, listeners fire and the file is saved atomically. Kill switch: env `OMB_DISABLE_MODEL_MANIFEST_FETCH=1`.
5. `currentEngineCatalog("claude")` converts the manifest section to a `ModelCatalog` (`engineCatalogFrom`: only `current` models; `contextWindow` and `variants` carried; name becomes `label`).
6. `server/drivers/claude.ts` `readClaudeModelCatalog()` starts from that list and appends **extras** from Claude Code's `settings.json` and env (`claudeModelExtras` in `server/drivers/claude-model-extras.ts`: `availableModels`, `customModels`, `extraModels`, `ANTHROPIC_MODEL`, `ANTHROPIC_CUSTOM_MODEL_OPTION(_NAME)`, `ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU}_MODEL`). Non-official ids are flagged `custom: true`. Ids must match `CLAUDE_MODEL_ID`.
7. `mergeLocalInject` adds models served by local hosts (Ollama etc.), then two filters annotate rather than remove rows:
   - `withCliVersionGate` (manifest.ts) sets `needsCliUpdate: "<minCliVersion>"` when the installed `claude` CLI is older than the model's `minCliVersion`; if the default is gated, the default moves to the first usable non-custom model.
   - `withOrgBlocks` (`server/drivers/claude-model-access.ts`) reads `modelAccessCache` from Claude Code's own account config (`.claude.json` / `.config.json`) and sets `orgBlocked: true` on models the organization turned off (`entitled: false`, fail open; skipped on Bedrock/Vertex/Foundry env).
8. The result is cached per instance by `server/startup-model-catalog.ts` (`<DATA_DIR>/providers/engine-models/<instanceId>.json`, fresh for 6 h and same build stamp) so a restart shows the last list immediately and refreshes in the background (`openStartupModelCatalog`).

Cursor, Grok, Kimi and Antigravity drivers read `currentEngineCatalog("<engine>")` from the same manifest (e.g. `server/drivers/acp/grok.ts` `get models()`, `server/drivers/antigravity.ts`).

### 4.2 Codex / OpenAI engine (live list, static fallback)

1. `server/drivers/codex-catalog.ts` `readCodexModelCatalog(env, fetch, cli)` first calls `readCodexAppServerModelCatalog(cli, env)`: spawns `codex app-server`, JSON-RPC `initialize`, then paged `model/list` (`limit: 100`, follows `nextCursor`), 8 s timeout.
2. Each row: hidden rows dropped, `displayName` becomes label, `supportedReasoningEfforts` becomes per-model `effortLevels` (ordered by `EFFORT_LEVELS`), `isDefault` picks the default, advertised Fast service tiers become extra rows `"<id>+<tier>"` with label `"<name> · Fast"`.
3. If the app-server gives nothing, `STATIC_CODEX_MODELS` is used and the catalog is marked `unconfirmedModelCatalog` so it is re-read at next start.
4. `catalogAround()` merges user config: `~/.codex/config.toml` (`model`, `model_provider`, `[model_providers.*]`), `*.config.toml` profiles, `model-catalogs/*.json` display names, and a live `GET {base_url}/models` probe (1 s timeout) per configured provider. Those rows get id `"<provider>::<model>"` and `custom: true`. The config's own `model` becomes the default if it is in the list.
5. Official rows force provider `openai` (`decodeCodexSelection`) so a local provider cannot swallow a bare id.

### 4.3 Differences by sign-in mode

- Engine metadata has `access: "subscription" | "custom" | "api"` (`EngineAccess` in `server/contracts.ts`; e.g. `openai-compat.ts` is `api`, `pi.ts`/`acp/custom.ts` are `custom`, `muse-code.ts` is `subscription`). It controls how the picker rail groups the engine, not which models appear.
- **Claude subscription (CLI login)**: manifest list + extras + org blocks + CLI gate (4.1).
- **Claude with a direct/gateway API key or endpoint**: `config.endpointModels` replaces the manifest list: `endpointModelCatalog()` gives rows `{ id, label: id, custom: true }`, default = first. Official Anthropic URL uses the manifest list (`officialModels(false)` in `server/agent-endpoint-models.ts`); a gateway is queried with `discoverAgentEndpointModels()` (`GET <base>/v1/models`, HTTPS or loopback only, no redirects, 2 MB and 1000-id caps, id filtered by `CLAUDE_MODEL_ID`, the id `default` rejected; errors become 400 with actionable text). A saved explicit model (`ANTHROPIC_MODEL`) is never replaced by discovery (`hasExplicitModel`).
- **Claude managed / company**: `config.managedModels` from `OMB_HOSTED_MODELS` JSON (`server/hosted-models.ts`, zod schema `{anthropic: string[], openai: string[], openrouter: string[]}`), shown as `{ id, label: id }`; any turn on a model not in the list throws `HOSTED_MODEL_SELECTION_ERROR`.
- **Codex ChatGPT plan** (`authMode: "chatgpt-plan"`, `provider openai_chatgpt_plan`): the live app-server list, which reflects the plan. **Codex direct API endpoint**: official OpenAI URL uses `STATIC_CODEX_MODELS`; a gateway is discovered via `/models`.
- A leaked `OPENAI_API_KEY` is deleted from the Codex child env so a ChatGPT login is not silently switched to pay-as-you-go (`server/drivers/codex.ts`, "A leaked API key silently flips...").

## 5. Effort / reasoning levels

- Type `EffortLevel` and `EFFORT_LEVELS` (`low, medium, high, xhigh, max`) in `packages/phone-protocol/src/wire.ts` (re-exported from `shared/wire.ts`).
- Engine default set: `capabilities.effortLevels` in the adapter (`server/drivers/claude.ts` ~L1923, `codex.ts` ~L1543, all five levels).
- Per-model override: `option.effortLevels` (Codex fills it from `supportedReasoningEfforts`).
- `offeredEffortLevels(instance, model)` (`packages/phone-protocol/src/effort-levels.ts`) prefers model levels, then instance capabilities, then adapter capabilities. A saved effort that is no longer offered is dropped, the model kept (`selectDefaultModelSelection` in `server/default-model-selection.ts`).
- Antigravity uses `variants` (thinking levels) instead; the web picker expands each variant into its own row (`modelChoices` in `src/lib/model-choices.ts`).

## 6. How the default is chosen

- Per engine: manifest `default` (must be `current`), or Codex's `isDefault`, or `config.toml`'s model, or the first row (`defaultModel()` in `server/default-model-selection.ts`). `withCliVersionGate` and `withOrgBlocks` move a blocked default to the first usable row.
- For a new bot: `selectDefaultModelSelection(instances, preferred, context)`:
  1. If a saved preference exists and its engine is available, enabled, signed in and the model is listed, keep it (dropping an unsupported effort). If not, return `{instanceId:"", model:""}` which sends the user to setup and never silently to another provider.
  2. Otherwise rank engines with `rankAis` (`shared/ai-ranking.ts`): Claude account (tier 0), ChatGPT/Codex (1), Gemini/Antigravity (2), Grok (3), other (4), OpenCode free fallback (5, only if nothing else answered). `access: "custom"` drops an engine to tier 4.
  3. Prefer an engine whose test message answered (`context.answered`); on an enrolled desktop a personal engine beats a Company one.
  4. The model is that engine's `default`.
- Fixed model per call is never guessed: a thread whose model is missing from its catalog keeps it, "engines run IDs their catalog does not list" (`server/thread-model.ts`).

## 7. How a user or agent picks a model

- User (web UI): the picker reads each instance's `models.options` (`src/lib/model-choices.ts`, `src/components/model-picker-reasoning.ts`); selection is `ModelSelection = { instanceId, model, effort?, variant? }` (`sameModelSelection` in `shared/thread-model.ts`). A thread runs on its bot's model unless the user picked another in that thread; `POST /api/bots/:id/threads/follow-model` (`server/routes/thread-models.ts`) moves own-model threads back.
- Typed ids: OpenCode accepts a typed `provider/model` (`withTypedModels`).
- Agent: `GET /api/internal/models` (`server/routes/internal-models.ts` `modelMenu()`) gives the bot a compact menu (cap 8 per engine, whole list if 12 or fewer, 20 across a `search`), only models that pass the same `refusal` check as `start_thread`, with `efforts`, blocked models and why (`orgBlocked`, `needsCliUpdate`), and unavailable engines with how to connect. A bot opens a thread on another model via `start_thread`. To change a bot's default it uses the model request flow: `server/model-requests.ts` builds a card ("Change ...'s default AI and model?") that the owner approves; `autoApply` and `validateModel` are server-owned; existing threads keep their model.
- Company workspaces: `hostedModelPolicy().allows/select` restrict choices to assigned ids.

## 8. Context window, pricing, other metadata

- Context window: on a row when known (`contextWindow` in manifest; Pi sets it from RPC). Otherwise `modelContextWindow()` in `server/model-context-window.ts` guesses from the id by regex (Claude 200k, `[1m]`/5.5/Fable 5.2 1M, `gpt-5*`/o3/o4 272k, `gpt-4.1` 1M, gemini 1M, `grok-4.7` 500k, other grok 256k).
- Pricing: manifest `prices` with `asOf`, `source`, dated `changes`; operator overrides (`PriceList` in `server/prices.ts`) win over list prices; reported provider cost wins over both (`ledgerCost` in `server/model-prices.ts`).
- Capabilities (tools/vision): not on picker rows. Engine-level `capabilities` flags exist on adapters (`images`, `nativeImageInput`, `effortLevels`, ...). Per-model flags exist only in the models.dev snapshot.

## 9. How the catalog is updated

- **Code release**: editing the bundled JSON ships with each app build, and the bundle wins over an older cache.
- **Remote file**: the same JSON on GitHub `main`, hourly; "To add a model: edit model-manifest.json, bump `updatedAt`, open a PR" (header of `schema.ts`). CI runs `scripts/check-model-manifest.mjs` (strict schema, all five engines present, non-empty prices, size under 128 KB, and with `--against <rev>` refuses a changed file whose `updatedAt` did not move forward).
- **Live per engine**: Codex app-server, Pi `get_available_models` (`server/drivers/pi-catalog.ts` `piCatalogFromFrame`, ids `provider/id`, all `custom`), ACP engines, gateways.
- **models.dev**: `scripts/build-model-catalog.mjs` produces `server/model-catalog/models-dev.snapshot.json` (current, tool-calling, text-input models only; any string containing `{` or `}` dropped because OpenCode expands `{env:..}`; max 150 KB gzip). `ModelCatalogStore` (`server/model-catalog/catalog.ts`) picks the newest of own cache (`providers/model-providers/models-dev.json`), OpenCode's `~/.cache/opencode/models.json`, and the bundled snapshot; refreshes from `https://models.dev/api.json` at most daily with ETag; env `OMB_DISABLE_MODEL_CATALOG_FETCH=1`. `server/model-catalog/presets.ts` pins base URLs for recommended providers (OpenRouter, Fireworks, ...) "so a catalog refresh can never change where a newly pasted key is sent".

## 10. Custom / other models

Allowed in every layer: Claude `settings.json` extras and `ANTHROPIC_CUSTOM_MODEL_OPTION`; Codex `config.toml` providers; gateway `/models` discovery; typed ids; local hosts; custom ACP/Pi engines. Custom rows carry `custom: true` and are skipped by the CLI-version gate.

## 11. What I could not find

- No evidence that `ModelCatalogStore`/`catalogEntries`/`PROVIDER_PRESETS` are imported by routes or UI in this checkout (only tests, scripts and the bundler reference them). It may be used by an engine file I did not search exhaustively, or be groundwork.
- No max-output-tokens field anywhere in the catalogs.
- No per-model tools/vision capability in the picker data.
- I did not read the ext.openai / ext.anthropic / ext.google / ext.openrouter nodes (the floorplan lists no files for them), nor the Gemini or OpenCode-Go catalog code.
- The web picker components were only skimmed (`src/lib/model-choices.ts`), not read end to end.

## 12. What Lonora should copy / avoid

Lonora is a Python (FastAPI) server, React web, Expo mobile trading assistant. It calls provider APIs directly (no CLIs), so some of this transfers differently.

Copy:
1. **One versioned JSON manifest with a strict schema** (`id`, `name`, `status current|legacy`, `contextWindow`, `aliases`, `default` that must be current). In Python use a Pydantic model, loaded at import so a bad bundled file fails the build. Add `max_output`, `capabilities: {tools, vision, reasoning}`, `effort_levels`, `access: [subscription, api_key]` fields that OpenMausBot lacks.
2. **Bundled copy + optional remote copy with `updatedAt` compare**: newest wins, remote parse is lenient for unknown fields, a stale CDN copy never resurrects a removed model, size cap, no redirects, timeout, kill switch env var, atomic disk cache. A CI check that refuses a changed manifest without a newer `updatedAt`.
3. **`legacy` status**: keep old ids valid for saved agents and threads but hide them from new picks.
4. **Separate price table with `asOf`/`source`/dated `changes`**, used for estimates only; reported provider cost wins. Fits Lonora's cost ledger and per-agent usage.
5. **Default selection that never silently switches provider**: a saved choice that is unavailable gives "set up" state, not a different provider (`selectDefaultModelSelection`). The new-agent default should come from a ranked, availability-checked list.
6. **Per-model effort levels falling back to engine defaults** (`offeredEffortLevels`), and dropping an unsupported saved effort while keeping the model.
7. **Live discovery only as a merge layer**: static list first (instant), live list refines it, a persisted last-good cache for fast start, "unconfirmed" marker so a failed discovery is retried. For API-key mode call the provider's `GET /models`, filter ids by regex, cap count and bytes.
8. **Annotate, do not delete, unusable models** (`orgBlocked`, `needsCliUpdate`): the picker shows why. Lonora equivalent: "not on your plan / key", "needs newer app".
9. **Agent-facing compact model menu** with the same refusal check as the action that uses it, and a model-change request that becomes an owner-approval card. This lines up with Lonora's existing `model_request` / agent_model card work.
10. **Pinned provider base URLs** separate from any refreshed catalog, so a catalog update can never redirect a user's key.

Avoid:
1. Do not spread the list across many files (manifest JSON, a TS constant for OpenAI, per-driver lists, models.dev snapshot, price table). One source of truth per provider and mode.
2. Do not hard-code OpenAI ids in code with an "availability unverified" label; put them in the manifest with a verified flag instead.
3. Do not guess context windows with id regexes (`modelContextWindow`); store them in the manifest and fail visibly when unknown.
4. Do not ship an unused second catalog (models.dev store here appears unwired). Pull it in only when a picker needs provider breadth.
5. Do not mix sign-in modes into one list silently: for Lonora make the catalog `access`-aware (subscription OAuth vs API key) so a subscription-only model is not offered under an API key and vice versa. OpenMausBot gets this implicitly from the CLI, which Lonora will not have.
6. Do not fetch the catalog from a raw GitHub branch of a third party without signature or pinning. If Lonora adds a remote manifest, host it on its own domain, keep the strict-validate-then-fallback pattern, and consider signing it, since a bad edit reaches every install within hours.
7. Trading note: never let a remote list or a live `/models` answer change the model of a running trading agent mid-run; only apply on the next run, and record the model id on each decision and order for audit.
