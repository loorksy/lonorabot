# Lonora's model list, the Responses API, and Sign in with ChatGPT — specification

**Status: Confirmed by the owner (VISION Amendment 4, 2026-11-26).** The owner's words:
«نحتاج الى اضافة نظام استخدام اشتراك openai و anthropic مباشر بدل api key و يمكن اضافة api key ايظن مثل rakazo و
OpenMausBot و بدل ان تكون موديلات مفتوحة تجلب تلقائيا يجب ان تكون قائمة المودلات الموجودة في lonora مثبتة مسبقا مثل
rakazo», then «بنسبة لي قائمة المودلات الثابتة استخدم نفس قائمة rakazo». This changes no trading path and nothing in
VISION section 6.

Sources studied (read only): Rakazo (`elie222/rakazo` at 10973b5), OpenMausBot (`milind-soni/OpenMausBot` at 140172d), the
model data Rakazo pins (`@earendil-works/pi-ai` 1.6.0, MIT), OpenAI's Sign in with ChatGPT documentation
(`https://developers.openai.com/siwc`), and Anthropic's legal and compliance page
(`https://code.claude.com/docs/en/legal-and-compliance`).

---

## 1. Decisions

| # | Decision | Why |
|---|---|---|
| M1 | Lonora's model list is **Rakazo's list**: the chat models of `@earendil-works/pi-ai` 1.6.0, the package Rakazo pins, for the providers Lonora supports, filtered as Rakazo filters them for agents (`catalogModelServesAgents`: OpenRouter `:batch` ids are dropped; Rakazo hides no other ids of these providers). | The owner's order. Rakazo itself keeps no list in its own source; this package is its list. |
| M2 | The list is **checked in as data**: `packages/providers/src/lonora_providers/models.json`, written by `scripts/import_model_catalog.py` from the unpacked package. It changes only with a Lonora release. Lonora reads **no provider's model list**, except the owner's own OpenAI-compatible endpoint, whose models are by nature the owner's (Rakazo probes such an endpoint the same way). | A reviewable diff for every model, price or limit change (Rakazo's own weakness: its list is hidden in a dependency). |
| M3 | Providers and their list: `anthropic` ← pi `anthropic`; `openai` ← pi `openai`; **`openai_chatgpt`** (new, the ChatGPT plan) ← pi `openai-codex`; `deepseek` ← pi `deepseek`; `zai` ← pi `zai`; `openrouter` ← pi `openrouter`; `openai_compatible` ← the owner's endpoint. | One provider id per billing channel, as Rakazo does (`openai` key vs `openai-codex` sign-in). |
| M4 | Defaults when the owner has chosen nothing (they replace `PREFERRED_FAMILIES`): `anthropic` → `claude-sonnet-5-5`; `openai` → `gpt-6.2-sol`; `openai_chatgpt` → `gpt-6.1-sol` (Rakazo's subscription default); `deepseek` → `deepseek-v4-pro`; `zai` → `glm-5.3`; `openrouter` → `anthropic/claude-sonnet-5.5`; `openai_compatible` → the first model its server lists. A default is only ever a model in the list. | A trading agent needs a strong model; Rakazo's cheaper "recommended" models are for its chat app. |
| M5 | **OpenAI calls use the Responses API** (`POST /v1/responses`), with an API key and with the ChatGPT plan. DeepSeek, Z.ai, OpenRouter and the owner's endpoint keep Chat Completions; Anthropic keeps the Messages API. | pi-ai marks every OpenAI model `openai-responses`; several listed models (the `-pro` and `codex` models) answer only there; the ChatGPT plan accepts only `/v1/responses`. |
| M6 | **Sign in with ChatGPT** follows OpenAI's official "ChatGPT plan usage in your open-source app" flow, as OpenMausBot does (`server/drivers/chatgpt-plan-auth.ts`): dynamic client registration with `client_id=dynamic_agent_client`, PKCE, the public `https://api.openai.com/v1/responses` endpoint. Lonora never uses the Codex CLI's client id or `chatgpt.com/backend-api` (Rakazo does both; VISION 12.2 keeps them prohibited). | The official route; Lonora is open source (Apache-2.0) and self-hosted per owner. |
| M7 | **No Claude subscription sign-in.** Anthropic keeps API keys only. | Anthropic: "Anthropic does not permit third-party developers to offer Claude.ai login into their own applications, or to route requests through Free, Pro, Max, or Ultra plan credentials on behalf of their users." Rakazo's Claude sign-in uses Claude Code's client id; copying it would break those terms and put the owner's Claude account at risk. |
| M8 | **Lonora Cloud:** `LONORA_CHATGPT_SIGN_IN` (default `on`). The control plane writes `off` into each customer's installation until OpenAI approves Lonora Cloud through its interest form for "paid or remotely hosted" apps. Self-hosted installations keep it on. | OpenAI's docs: plan usage is self-serve for open-source and locally hosted apps; paid or remotely hosted apps must apply. |

---

## 2. The model list

### 2.1 Data (`models.json`)

One JSON object, keyed by Lonora provider id, written by the import script with sorted keys and a header:

```json
{
  "source": "@earendil-works/pi-ai@1.6.0 (the list Rakazo pins)",
  "providers": {
    "anthropic": [
      { "id": "claude-sonnet-5-5", "name": "Claude Sonnet 5.5", "wire": "anthropic-messages",
        "context_window": 1000000, "maximum_output_tokens": 128000,
        "input": ["text", "image"], "reasoning": true,
        "cost": { "input": 2, "output": 10, "cache_read": 0.2, "cache_write": 2.5 } }
    ]
  }
}
```

- Only entries with `"type": "chat"` are taken (no classifier or image models).
- `wire` is the pi `api` field (`anthropic-messages`, `openai-responses`, `openai-codex-responses`, `openai-completions`).
  Lonora uses it only to check that each provider's entries are served by that provider's adapter: an import that
  brings a wire the adapter does not speak fails.
- `cost` is US dollars per million tokens, as pi-ai has it. A missing or all-zero price stays "unknown", never free.
- OpenRouter entries keep OpenRouter's own ids (`anthropic/claude-sonnet-5.5`).

### 2.2 Module

`packages/providers/src/lonora_providers/catalog.py` becomes the one reader:

- `listed_models(provider) -> list[ModelDescriptor]`: the shipped entries as `ModelDescriptor` with `verified=True`,
  `capabilities` = `text` + `tools` (Rakazo runs every listed model with agent tools) + `vision` when `input` has
  `image` + `reasoning` when `reasoning` is true, `context_window`, `maximum_output_tokens`, and
  `source = "lonora_model_list:pi-ai@1.6.0"`.
- `read_catalog(db, provider)`: the shipped list for every provider except `openai_compatible` (its stored, discovered
  list) and `openai_chatgpt` (the shipped list less the models the signed-in account does not offer, section 4.7).
- `store_catalog` survives only for `openai_compatible`.

### 2.3 Consumers to change

Everything that today calls `adapter.discover()` or reads `catalog:<provider>` for a fixed provider moves to the list:
`discovery.py` (owner endpoint only), `default_model.py` (the M4 defaults; no live discovery), `router.py`
(descriptors from the list), `routes/providers.py` (`GET /providers/{p}/models` returns the list; `POST .../discover`
only for the owner endpoint), `routes/connection_tests.py` and the Secret card's key check (section 2.4),
`db/agent_models.py` (`catalog_models`, `catalog_has`, `model_label`), `tools/models.py`, the `agent_create`,
`subagent_spawn` and `consult_model` gates (unchanged logic, new source), `context.py` (window and output from the
list, so `capacity_source` is the list instead of "unknown"), and `core/model_pricing.py` (prices from the list for
every provider, `PRICES_AS_OF` the package version).

A migration deletes the stored `catalog:<provider>` rows of the fixed providers (downgrade: nothing to restore; the
list is in the code).

An agent whose saved model is no longer in the list keeps it (Rakazo: "saved choices never vanish"); the pickers list
only listed models, and `model_request` accepts only listed models of connected providers.

### 2.4 Checking a key without reading a list

The Secret card and `POST /providers/{p}/test` still check a typed key before saving it, without storing anything the
provider lists: `GET {base}/models` with the key, where 2xx means accepted, 401/403 rejected, anything else "could not
check, saved anyway" (today's behaviour). The answer's content is ignored. For the owner endpoint the list is read and
stored as today.

### 2.5 The import script

`scripts/import_model_catalog.py --package DIR` reads `DIR/dist/providers/data/{anthropic,openai,openai-codex,deepseek,zai,openrouter}.json`
(the unpacked tarball, read as data: nothing in it is run), applies M1 and M3, and rewrites `models.json`. A test pins
the shape and a few ids per provider, and that every entry's `wire` matches its provider's adapter.
`THIRD_PARTY_NOTICES.md` names the package and its MIT licence.

---

## 3. The Responses adapter

`packages/adapters/src/lonora_adapters/models/openai_responses.py`, `OpenAIResponsesAdapter(BaseModelAdapter)`, used
by `openai` (API key) and `openai_chatgpt` (section 4). The request:

- `POST {base}/responses`, `stream: true`, `store: false` (the turn's history is sent each time; nothing is kept at
  OpenAI);
- `instructions`: the system messages joined (the ChatGPT plan rejects `role: system` items);
- `input`: user and assistant messages as `{role, content}` with `input_text` / `input_image` parts; an assistant's tool
  calls as `{type: "function_call", call_id, name, arguments}`; tool results as
  `{type: "function_call_output", call_id, output}`;
- `tools`: `{type: "function", name, description, parameters, strict: false}` (`strict: false` keeps optional
  arguments optional, as OpenMausBot notes). For `openai_chatgpt` the function tools go inside one
  `{type: "namespace", name: "lonora", description, tools}` entry, as the plan's preview limits require;
- `max_output_tokens` for `openai` only (the plan rejects it, and `temperature`, `metadata`, `user`, `truncation`,
  `prompt_cache_retention`, `previous_response_id`).

The stream: `response.output_text.delta` → `on_delta`; `response.output_item.done` with `type: function_call` → a tool
call (arguments parsed as JSON); `response.completed` → usage (`input_tokens`, `output_tokens`,
`input_tokens_details.cached_tokens`) and success; `response.incomplete` with `max_output_tokens` → TRUNCATED;
`response.failed` / `error` → the error taxonomy (section 4.8). A stream that ends without `response.completed` is
`interrupted_stream`. The adapter keeps the two invariants every adapter keeps: a cut-off reply never yields tool calls,
and nothing is retried that could repeat an external effect (a model request has none).

`discover()` is not used for `openai` any more (section 2). A live check of one short turn with one tool call against
`api.openai.com` with the deployment's API key is part of the acceptance (section 6).

---

## 4. Sign in with ChatGPT

### 4.1 What the owner sees

1. The owner asks Lonora to use their ChatGPT plan, or picks ChatGPT on the provider list. The agent opens the Secret
   card with `target: model_provider`, `name: openai_chatgpt`. VISION 7.2 and 10.3 stay: it is the Secret card, with a
   sign-in in place of the key field. No new card kind.
2. The card says «استخدم اشتراك ChatGPT» / "Use your ChatGPT plan": eligible requests use the owner's ChatGPT Plus or
   Pro plan, managed in ChatGPT settings. The button reads **Continue with ChatGPT** (OpenAI's label).
3. The browser (a Custom Tab on Android) opens OpenAI's sign-in. The owner signs in, names the app if asked, and allows
   plan usage.
4. OpenAI then sends the browser to `http://127.0.0.1:1455/auth/callback?...`. Lonora runs on a server, not on the
   owner's phone, so that page does not open. The card's second step says so before it happens: «ستصل إلى صفحة لا
   تفتح. انسخ عنوانها كاملاً من شريط العنوان والصقه هنا» / "You will reach a page that does not open. Copy its whole
   address from the address bar and paste it here." OpenAI's own guide for self-hosted VMs describes the same
   situation: the loopback callback reaches the device that runs the browser, not the server.
5. The card settles «متصل: name@example.com» / "Connected: …". The agent is woken and says in one line which models
   became available.
6. Wherever the ChatGPT plan answers, the model line reads "Using ChatGPT plan" with **Manage usage**
   (`https://chatgpt.com/settings/usage`). The provider entry has **Sign out**.

### 4.2 Protocol (OpenAI's documentation, `siwc/token-sharing-open-source`)

- **Host id:** `urn:uuid:<uuid4>`, created once per installation and kept in `ln_settings["chatgpt_host_id"]`
  (an identifier, not a secret).
- **Authorize:** `https://auth.openai.com/api/accounts/authorize` with `client_id` (`dynamic_agent_client` the first
  time, then the issued `oaiapp_…` id), `agent_name_hint=Lonora` (first time only), `ext_agent_host_id`,
  `response_type=code`, `redirect_uri=http://127.0.0.1:1455/auth/callback` (never `localhost`; the same in the
  exchange), `scope=openid profile email offline_access resource.invoke chatgpt.tokens.use.direct`,
  `resource=https://api.openai.com/v1`, fresh `state` and `nonce`, PKCE `S256`. A returning account adds
  `id_token_hint` and `login_hint`; re-enabling plan use after a decline adds `prompt=consent`.
- **Callback (pasted):** `code`, `state`, and on first registration the issued `client_id`. Lonora checks: the address
  is `http://127.0.0.1:1455/auth/callback`, each parameter once, `state` equal in constant time, no `error`
  (`access_denied` → "not approved"), the issued id is not `dynamic_agent_client` and equals the pending one on a
  returning sign-in.
- **Exchange:** `POST https://auth.openai.com/api/accounts/oauth/token`, form: `grant_type=authorization_code`,
  `client_id` (issued), `code`, `code_verifier`, `redirect_uri`, `resource`. No client secret. `invalid_grant` keeps the
  issued id for the next attempt so no second client is registered.
- **ID token:** verified against `https://auth.openai.com/.well-known/jwks.json` (RS256/ES256), issuer
  `https://auth.openai.com`, audience = the issued id, `exp`, `iat`, the saved `nonce`; `sub` is the account. A
  returning sign-in must return the same `sub`.
- **Permission:** the granted scopes must include `chatgpt.tokens.use.direct`; without it the sign-in is kept but plan
  use is off, and the card says how to allow it.
- **Refresh:** before the access token's last minute, `POST …/oauth/token` with `grant_type=refresh_token`, the issued
  id, the refresh token, `resource`; never before `earliest_refresh_at`. Refresh tokens rotate: refreshes are
  serialized by a Postgres advisory lock per credential, the stored copy is re-read inside the lock, and the new token
  set replaces the old one in the same transaction. `invalid_grant`, `invalid_refresh_token`, `token_expired`,
  `refresh_token_expired`, `refresh_token_invalidated`, `refresh_token_reused` → the tokens are cleared (the issued id
  and host id stay) and the owner is asked to sign in again; any other failure keeps the tokens.
- **Sign out:** `POST` the `revocation_endpoint` from `https://auth.openai.com/.well-known/openid-configuration` with
  `token=<refresh>`, `token_type_hint=refresh_token`, `client_id`; HTTP 200 is success. The tokens are cleared even when
  revocation fails, and the owner is told it was not confirmed (they can disconnect Lonora in ChatGPT settings).

### 4.3 Storage

- The credential is one encrypted `ln_secrets` row, scope `provider`, name `openai_chatgpt`, value a JSON string:
  `client_id`, `subject`, `email`, `host_id`, `id_token`, `access_token`, `refresh_token`, `scopes`, `expires_at`,
  `earliest_refresh_at`. Scope `provider` keeps it out of the workspace (`workspace_values` serves only the workspace
  scope): agents and their scripts never receive it.
- The redaction scan (VISION 7.2.6) must know the access, refresh and ID tokens as separate values.
- A pending sign-in (state, nonce, PKCE verifier, client id, expiry 15 minutes) is one encrypted row, scope `provider`,
  name `openai_chatgpt_pending`, replaced by each new start and deleted when it finishes.
- `ln_settings["model_provider:openai_chatgpt"]` is the router record, as for keys.

### 4.4 Server

- `POST /api/owner-actions/{card_id}/chatgpt/start` → `{authorization_url, expires_at}`.
- `POST /api/owner-actions/{card_id}/chatgpt/finish` with `{address}` → settles the card (the same settle, router
  record, default model and wake as the key path in `routes/secret_cards.py`).
- `POST /api/providers/openai_chatgpt/sign-out`.
- `ProviderCredentials.connection("openai_chatgpt")` returns a fresh access token and `https://api.openai.com/v1`; the
  adapter calls it once per request.
- With `LONORA_CHATGPT_SIGN_IN=off`, the card offers no sign-in, the routes answer `chatgpt_sign_in_unavailable`, and
  the agent tells the owner to use an OpenAI API key.

### 4.5 Clients

The web card (`OwnerActionCard`) and the Android card (`owner-action-card.tsx`) show the two steps, the paste field
(masked, never echoed, cleared on submit), the connected account, and the errors of section 4.8, in Arabic and
English, from shared logic in `packages/core`. The web settings list shows the connection, "Using ChatGPT plan",
**Manage usage** and **Sign out**.

### 4.6 Guards

`tests/test_model_access_guard.py` keeps failing on the Codex CLI client id, `chatgpt.com/backend-api`,
`/backend-api/`, `.codex/auth.json`, Claude Code's client id and every Claude subscription marker. It allows
`auth.openai.com` only in the ChatGPT sign-in module, and only the official paths above (`/api/accounts/authorize`,
`/api/accounts/oauth/token`, `/.well-known/jwks.json`, `/.well-known/openid-configuration`).
`tests/test_model_providers.py` gains `openai_chatgpt` and the Responses path.

### 4.7 Which ChatGPT models are available

The list for `openai_chatgpt` is fixed (M1, M3). After sign-in, and at most every 15 minutes while it is used, Lonora
reads `GET https://api.openai.com/v1/models` with the access token and keeps the slugs with `visibility: "list"`; a
listed model the account does not offer is shown as not available with this plan. Models the account names but the
list does not hold are not added (M2). A model ChatGPT refuses for the account at run time is added to a per-account
refused set until the next sign-in (OpenMausBot's `refusedModels`).

### 4.8 Errors

| ChatGPT answer | Lonora |
|---|---|
| `subscription_sharing_usage_limit_exceeded` (429) | billing reason (`model_billing_exhausted`): the router falls back to the next model; the owner sees "ChatGPT plan limit reached" with **Manage usage** |
| `subscription_sharing_user_not_eligible` (403), `subscription_sharing_route_not_supported`, `chatpass_v2_*` | permission (`model_access_denied`) |
| `subscription_sharing_invalid_user` (401), terminal refresh error | auth (`model_credentials_rejected`); sign in again |
| `subscription_sharing_unsupported_capability` (400) | format error (`model_request_rejected`), with `error.param` in the log |
| `subscription_sharing_usage_unavailable`, `subscription_sharing_user_unavailable` (503), a 503 before the stream | overloaded (transient, backoff) |

Provider text is never shown or logged; only the code.

---

## 5. Texts that change with this (VISION 0.4)

VISION.md (Amendment 4), `docs/cloud/DECISIONS.md` (D6, D41), `docs/cloud/PLAN.md`, `docs/cloud/JOURNEY.md`, README
(both languages), `docs/provider-resilience.md`, `docs/context-budgeting.md`, `docs/context-engine.md`,
`docs/agents-from-chat.md`, `packages/agent-runtime/resources/system/lonora.md` (then
`scripts/check_policy_distribution.py`), the docstrings that say "any model of a connected provider's catalog", and
`.github/workflows/model-catalog-update.yml` (deleted: it asks a provider for its list). The floorplan map gains the new
files and its recent work.

## 6. Acceptance

1. `pytest` (full), `tests/run_foundation_checks.py`, `scripts/build.sh`, Lingui, the web and mobile Playwright suites.
2. The list: every provider's pickers show exactly the shipped entries; no request goes to any `/models` except the
   key check and the owner endpoint.
3. Responses: fake-server tests for text, tool calls, images, usage, truncation, failure events and cut-off streams;
   one live turn with one tool call on `api.openai.com` with the deployment's key.
4. ChatGPT sign-in: fake OpenAI (authorize, token, JWKS, revoke, models, responses) tests for first registration,
   returning sign-in, declined plan use, state and client-id mismatches, a different account, refresh with rotation
   under two concurrent callers, terminal and transient refresh failures, sign-out with and without confirmed
   revocation, and each error code of 4.8. No live ChatGPT account exists here; the first live sign-in is the owner's.
