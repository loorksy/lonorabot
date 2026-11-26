# Rakazo: connecting OpenAI and Anthropic (API keys, ChatGPT sign-in, Claude sign-in)

Source: https://github.com/elie222/rakazo, commit 10973b57d0df6a35e2019b4739ce98c6aecfded3 (read only). All paths are repo-relative. No secret values were read or are quoted; the client IDs below are public identifiers hard-coded in the source.

## 0. Summary

| Flow | Provider id in Rakazo | Protocol | Where it lives |
|---|---|---|---|
| (a) API key | `openai`, `anthropic` (and any catalog provider) | Paste key, optional live check, stored encrypted | `apps/api/src/routes/models.ts` (`connect`), `apps/api/src/models/model-credentials.ts`, `packages/adapters/src/models/model-connect.ts` |
| (b) ChatGPT/Codex subscription | `openai-codex` | OAuth device-code flow (OpenAI `deviceauth`), server side, web polls | `packages/adapters/src/runtime/pi/models/pi-chatgpt-device-code.ts` |
| (c) Claude Pro/Max subscription | `anthropic` (same id as the key provider) | OAuth authorization code + PKCE (S256), manual paste-back of the code, optional desktop loopback capture | `packages/adapters/src/runtime/pi/models/pi-anthropic-oauth.ts` |

Both subscription flows are present and shipped. Both are third-party-client OAuth using the public client IDs of the official CLIs (Codex CLI, Claude Code). Rakazo does not drive an official CLI for them. A separate, self-host-only route does drive the official `claude` CLI (section 6).

Important limit of this study: the token **refresh** HTTP call and the **model request** itself (base URL, headers, Responses vs Messages) are performed inside the external dependency `@earendil-works/pi-ai` 1.6.0 (`packages/adapters/package.json`), whose source is not in the repo. Rakazo calls `oauth.refresh(...)` and `oauth.toAuth(...)` on it (section 5). See section 11 for what could not be found.

## 1. Architecture in one paragraph

Browser/desktop/mobile call oRPC procedures `models.beginOAuth`, `submitOAuthCode`, `completeOAuth`, `finishOAuth`, `cancelOAuth` (`apps/api/src/routes/models.ts`). The API process holds the in-flight sign-in in a class `PiOAuthLogins` (`packages/adapters/src/runtime/pi/models/pi-oauth.ts`) that runs a per-provider "login function" (device code for ChatGPT, paste-back PKCE for Claude), mirrors state to a `ModelOAuthSession` row so any API process can report/finish/cancel it, and on success calls a `persist` callback that serializes the credential, encrypts it (`EncryptedSecretStore`, AES-256-GCM) and writes a `Secret` row plus a `UserModelCredential` row. At run time the stored secret is decrypted, refreshed under a Postgres advisory lock if it expires within 5 minutes, and handed to pi-ai through a request-scoped credential store.

## 2. (a) API keys

### User-visible steps
1. Settings -> Models (or onboarding), pick the provider (OpenAI, Anthropic, OpenRouter, ...), choose "paste an API key" (web: `apps/web/src/components/models/ProviderSettingsForm.tsx`; the Anthropic card shows a "Sign in with Claude" button plus "Or paste an API key", see the comment in `model-provider-registry.ts`: `// Button + "Or paste an API key" already explain the choices`).
2. Submit. The server validates, stores, selects a default model.

### Control flow
1. `models.connect` (`apps/api/src/routes/models.ts`) records analytics via `startModelConnect(..., "api_key", ...)` then calls `connectModelCredential`.
2. `createModelConnector().verifyModelConnection` (`apps/api/src/models/model-credentials.ts`):
   - `assertModelProviderAllowed(input.provider)` (deployment allowlist), then `buildModelConnectPlaintext` (`packages/adapters/src/models/model-connect.ts`) builds the plaintext.
   - `assertHeaderSafeApiKey` (`packages/contracts/src/models/model-provider.ts`) rejects anything outside printable ASCII `^[\x21-\x7e]+$`.
   - When the key is new or routing changed: `verifyCatalogProviderApiKey` (`packages/adapters/src/runtime/pi/models/pi-models.ts`) does a GET to the provider's read-only `keyCheck` URL if the registry defines one (`model-provider-registry.ts`: `keyCheck` exists for OpenRouter, Google, DeepSeek; none for `openai` or `anthropic`). 401/403 means rejected (`const unauthorized = async (response) => response.status === 401 || response.status === 403`). Transport errors are swallowed, never forwarded (they could contain the key).
   - Then `deps.modelConnectionCheck` = `verifyModelServesAgents` (`packages/adapters/src/models/model-connect-check.ts`) sends one minimal real agent request (max 1024 tokens) and aborts at the first `start` event. Blocking failure kinds: `auth, access, model, key, credit, spending`; rate limits/outages/timeouts pass.
3. `persistModelCredential` -> `prepareModelCredential`: `deps.secrets.put(plaintext, {...})` encrypts, then a `Secret` row and `UserModelCredential` row (`packages/db/prisma/schema.prisma`: `model UserModelCredential { provider, label, secretId ... }`, `model Secret { kind, ciphertext ... }`).

### Stored shape (`packages/adapters/src/models/model-secret.ts`)
`StoredModelSecret` is a union: `{kind:"api_key", key, maxTokens?, accountId?, gatewayId?, projectId?, region?, zeroDataRetention?, models?}`, `{kind:"oauth", credential}` or `{kind:"oauth", reconnectRequired:true}`, `{kind:"openai_compatible", baseUrl, apiKey?, headers?, ...}`. A bare API key serializes as the raw string (no JSON) when it has no extra settings: `if (... && !models.models) return secret.key;`. `parseModelSecret` treats any non-JSON as `api_key`. Billing label derives from kind: `oauth: "subscription", api_key: "api_key", openai_compatible: "custom_endpoint"`.

### Request use
`resolveRuntimeModel` (`packages/adapters/src/runtime/pi/pi-runtime-models.ts`) passes `modelConfig.apiKey` to pi-ai when `modelConfig.oauth` is absent. Only OpenRouter may fall back to a deployment env key (comment: "Handing it to another provider would ship our key to a vendor it was not issued for"). Deployment-wide keys exist per provider via `deployment: { keyEnv: "ANTHROPIC_API_KEY", defaultModel: ... }`.

### Note on providers
`openai` = platform API key (separate billing). `openai-codex` = the ChatGPT-subscription provider; it is registered with `signIn.mode: "device-code"`. Docs: `docs/model-subscriptions.md` says an OpenAI API key "uses separate API billing, not your subscription allowance". `pi-catalog-availability.ts` shows `openai-codex` can also be used with an API key for models the subscription cannot call (`OPENAI_CODEX_CHATGPT_SUBSCRIPTION_EXCLUDED_MODEL_IDS = new Set(["gpt-5.3-codex-spark", ...])`, "API-key auth still can").

## 3. (b) ChatGPT / Codex subscription sign-in (device code)

### User-visible steps (web: `apps/web/src/components/models/SubscriptionSignInSteps.tsx`)
1. Optional setup step: "Turn on device code sign-in in ChatGPT security settings" with link `https://chatgpt.com/#settings/Security`, note "Workspace accounts need an admin to turn this on." (`model-provider-registry.ts`, `openai-codex.signIn.setup`).
2. Click "Sign in with ChatGPT" -> card shows "Get a sign-in code", then "Enter this code at auth.openai.com/codex/device" with the user code and a "Copy code and open" button (opens the page from the user's own click, so browsers do not block the tab).
3. A "Waiting for you to sign in" step polls; "The code expires in about N minutes", "Get a new code" restarts.
4. On approval the connection appears with the account email as label (from the JWT; `oauthCredentialEmail`).

### Protocol: OAuth device authorization, OpenAI's `deviceauth` variant, then authorization_code exchange
Constants (`pi-chatgpt-device-code.ts`):
```ts
const AUTH_BASE_URL = "https://auth.openai.com";
const USER_CODE_URL = `${AUTH_BASE_URL}/api/accounts/deviceauth/usercode`;
const DEVICE_TOKEN_URL = `${AUTH_BASE_URL}/api/accounts/deviceauth/token`;
const TOKEN_URL = `${AUTH_BASE_URL}/oauth/token`;
const VERIFICATION_URI = `${AUTH_BASE_URL}/codex/device`;
const DEVICE_REDIRECT_URI = `${AUTH_BASE_URL}/deviceauth/callback`;
// Public OAuth client identifier used by the Codex CLI. This is not a client secret.
const CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann";
```
No scopes are sent anywhere in this flow (the code request body is only `{client_id}`). No refresh/revoke/userinfo URL appears in this file (refresh is in pi-ai; identity is decoded locally from the access token JWT).

### Control flow (`createChatGptDeviceCodeLogin`)
1. `POST USER_CODE_URL` JSON `{ client_id: CLIENT_ID }`, 8 s timeout (`CODE_REQUEST_TIMEOUT_MS`), up to 3 attempts, retrying only transient errors (5xx, 408, 429, dropped connection, 400 `request_failed`). Response gives `device_auth_id`, `user_code`, `interval`.
2. `interaction.notify({type:"device_code", userCode, verificationUri, intervalSeconds, expiresInSeconds: 900})`. `PiOAuthLogins` turns this into `{mode:"device-code", userCode, verificationUri, expiresInSeconds}` for the client (`httpsAuthorizationUrl` enforces https).
3. Poll `POST DEVICE_TOKEN_URL` JSON `{device_auth_id, user_code}` every `interval` seconds (min 1 s, default 5 s) until 15 min (`CHATGPT_DEVICE_CODE_TTL_SECONDS`). Pending is signalled by error code `deviceauth_authorization_pending`, or any 403/404 without a refusal code:
```ts
if (error.code === "deviceauth_authorization_pending") return { status: "pending" };
if (error.code === "slow_down") return { status: "slow_down" };
// The person has not approved the code yet, unless the answer names a refusal.
if ((response.status === 403 || response.status === 404) && !(error.code && REFUSALS.has(error.code)))
  return { status: "pending" };
```
   `slow_down` adds 5 s (RFC 8628 3.5). `access_denied` and `expired_token` end the wait. Transient failures during polling are logged and ignored (`"model sign-in poll failed; still waiting"`), which is an intentional deviation from the runtime's own flow that "ends the sign-in on the first 5xx".
4. Approved poll returns `{authorization_code, code_verifier}` (the server generated the PKCE pair, the client never sees it).
5. Token exchange `POST TOKEN_URL`, `application/x-www-form-urlencoded`: `grant_type=authorization_code, client_id, code, code_verifier, redirect_uri=DEVICE_REDIRECT_URI`. Retried only on an answer that says the provider failed, never on a timeout or cut-off body, because the code is single use.
6. `credentialOf` requires `access_token`, `refresh_token`, numeric positive `expires_in`; builds `{type:"oauth", access, refresh, expires: Date.now()+expires_in*1000}` and demands an account id: `oauthCredentialAccountId` reads `chatgpt_account_id` from the access-token JWT claim namespace `https://api.openai.com/auth` (`model-auth-resolution.ts`). No account id => "Device sign-in returned a credential with no account." The id is stored as `accountId` on the credential.

Redirect URI: `https://auth.openai.com/deviceauth/callback` (only used in the exchange; no user redirect happens).

### Hardening worth noting
- Error bodies are never quoted: `errorCode` keeps only a value matching `/^[a-z_]{1,64}$/`. `SignInHttpError` message is "Device sign-in {step} failed (status N, code)".
- Responses capped at 64 KiB (`readBoundedJsonResponse`).

## 4. (c) Claude Pro/Max subscription sign-in (authorization code + PKCE, paste-back)

### User-visible steps
1. Settings -> Models -> Anthropic -> "Sign in with Claude" (registry: `signIn: { mode: "auth-url", loginLabel: "Sign in with Claude", hint: "Claude Pro/Max / key", billing: "" }`).
2. Card: "Sign in at claude.ai" with an "Open claude.ai" button (opened from the user's click).
3. On the Anthropic page, approve. Browser web/mobile: Anthropic's page shows a code; user pastes it in "Paste the code it shows you" and presses Submit. Desktop app: a loopback listener captures the code automatically, so no paste (section 4.3).
4. "Start over" restarts.
Docs (`docs/model-subscriptions.md`): "You need a Claude Pro or Max plan. Usage counts against your plan's limits." and a link to Anthropic's "authentication and credential rules".

### Protocol and endpoints (`pi-anthropic-oauth.ts`)
```ts
const AUTHORIZE_URL = "https://claude.ai/oauth/authorize";
const TOKEN_URL = "https://platform.claude.com/v1/oauth/token";
const LOOPBACK_REDIRECT_URI = "http://localhost:53692/callback";
const CODE_PAGE_REDIRECT_URI = "https://platform.claude.com/oauth/code/callback";
const SCOPES =
  "org:create_api_key user:profile user:inference user:sessions:claude_code user:mcp_servers user:file_upload";
// Public OAuth client identifier used by Claude Code. This is not a client secret.
const CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e";
```
- Authorize URL query: `code=true, client_id, response_type=code, redirect_uri, scope, code_challenge (S256), code_challenge_method=S256, state`. Note `state` is set to the PKCE **verifier** itself (`state: verifier`), mirroring Claude Code's quirk. The verifier is `randomBytes(32).toString("base64url")`.
- Redirect URI: `LOOPBACK_REDIRECT_URI` when the client is the desktop app (it listens), otherwise `CODE_PAGE_REDIRECT_URI` (Anthropic shows the code). Chosen by the client's `codePage` flag: web sends `codePage: !desktopBridge()?.oauth.open` (`apps/web/src/lib/models/use-model-oauth-signin.ts`); mobile always sends `codePage: true` (`apps/mobile/lib/auth/use-subscription-sign-in.ts`).
- Token exchange `POST TOKEN_URL`, **JSON** body:
```ts
body: JSON.stringify({
  grant_type: "authorization_code", client_id: CLIENT_ID, code: authorization.code,
  state: authorization.state ?? verifier, redirect_uri: redirectUri, code_verifier: verifier,
}),
```
  headers only `accept` and `content-type: application/json`; 30 s timeout; response capped at 64 KiB.
- Pasted input is parsed leniently (`parseAuthorizationInput`): full redirect URL, `code#state`, `code=...&state=...`, or bare code. A `state` that is present and differs from the verifier throws "OAuth state mismatch." before any exchange.
- Result: `{type:"oauth", access, refresh, expires: Date.now() + expires_in*1000 - 5*60*1000}` (5-minute safety margin baked into `expires`).
- No authorize-time client secret, no userinfo call, no revoke call. The account label comes from `oauthCredentialEmail`, which only works if the access token is a JWT with an email claim; for Claude it will usually be absent, so the label falls back to `login.label` or the provider name (`saveSignIn` in `routes/models.ts`).

### 4.3 Desktop loopback capture (`apps/desktop/src/main/auth/browser-auth.ts`, `oauth-callback.ts`)
- `openBrowserAuth` requires the authorize URL to be `https:` without userinfo and, when `redirect_uri` is set, requires `http:` + loopback host + explicit port >= 1024 + no query/hash + a `state`. It starts a `node:http` server on `127.0.0.1` and `::1` (for `localhost`) and reports `{code, state}` to the renderer.
- Renderer (`apps/web/src/lib/platform/desktop.ts`): `oauthStateOf(url)` extracts `state`; `onDesktopOAuthCallback(listener, expectedState)` drops callbacks whose state differs. The captured code goes through the same `submitOAuthCode` path as a paste.

### Server side of the paste-back (`PiOAuthLogins`)
- `begin()` (called by `models.beginOAuth`): for `mode === "auth-url"` providers and when a handoff store exists, it pre-generates the verifier (`randomBytes(32).toString("base64url")`) and stores `{provider, credentialId, modelId, ..., codePage, verifier}` **encrypted** (`handoff.secrets.put(..., { ephemeral: true })`) in `ModelOAuthSession.ciphertext`, so a different API process (after a deploy or behind a load balancer) can receive the pasted code and finish the exchange (`resume`).
- `submit(loginId, actor, code, persist)` resolves the pending `manual_code` prompt of the login function; `claim()` makes one process own the exchange.
- Expiry of a pasted-code sign-in: `PASTED_CODE_TTL_SECONDS = 15 * 60`.

## 5. Token storage, refresh, expiry, revocation

### Storage
- Credential object (pi-ai `OAuthCredential`): `{type:"oauth", access, refresh, expires, accountId?}` serialized by `serializeModelSecret`. Bare credential JSON when no settings, or `{kind:"oauth", credential, maxTokens?, models?}`. `parseModelSecret` also accepts the legacy bare credential (`parsed.type === "oauth"`).
- Encrypted by `EncryptedSecretStore` (`packages/adapters/src/secrets/secrets.ts`): format `v2:` + base64(salt16 | iv12 | tag16 | ciphertext), key = `scrypt(encryptionKey, salt, 32, N=16384,r=8,p=1)`, cipher `aes-256-gcm`, AAD = the record id (so a ciphertext cannot be moved to another row). Legacy format: SHA-256 key, no AAD, still readable. Alternatives selected by env in `secret-store-factory.ts`: `SECRET_STORE=infisical` (remote refs `infisical:...`). Env values can be envelope-wrapped with KMS (`wrapped-env.ts`, `key-provider-factory.ts`, `MASTER_KEY_PROVIDER=aws-kms`).
- DB: `secrets` table (`Secret.ciphertext`, `kind`, `userId`, `spaceId` null for model credentials) and `user_model_credentials` (`provider, label, secretId`). Model credentials are per user, account-wide across Spaces (queries filter `spaceId: null`).
- Redaction list for logs: `secretValuesToRedact` returns `[access, refresh]` for OAuth.

### Refresh
- Trigger: when `credential.expires - now < MIN_OAUTH_VALIDITY_MS` (5 min) (`resolveModelAuth` in `model-auth-resolution.ts`). It calls `oauth.refresh(credential, signal)` where `oauth = loadProviderOAuth(provider)` = pi-ai's provider `auth.oauth` (`builtinModels().getProvider(id).auth.oauth`). The actual refresh endpoint and body are inside pi-ai (not in this repo). Special case: `loadProviderOAuth("openai")` returns undefined ("keep subscription sign-in on Codex").
- Because providers rotate refresh tokens, a due refresh runs under a Postgres transaction-scoped advisory lock, per secret (`resolveStoredModelAuth` in `models/model-credential-refresh.ts`: `withRefreshLock(prisma, tx => advisoryLock(tx, "model-credential", secretId), ...)`, plus an in-process `withModelCredentialLock`). The stored copy is re-read inside the lock so an instance that lost the race adopts the already-rotated token. Refresh HTTP timeout 15 s (`REFRESH_REQUEST_TIMEOUT_MS`). A failure after the save still commits it ("the provider spent the old token").
- Mid-run refresh: `PiRuntimeCredentialStore.modify()` (`pi-credentials.ts`) serializes refreshes per run and publishes the new credential back via `persistRefreshedModelCredential` (`updateStoredModelSecret`), which refuses to overwrite a newer stored token (`if (stored.expires > next.expires) return null`).
- Background "kick": `kickModelCredentialRefresh` is fired when the usage panel finds an expired token (`apps/api/src/routes/content.ts` passes `refreshExpiredCredential`); concurrent kicks per secret collapse; 30 s bound.
- Account-switch guard: a refreshed token whose `chatgpt_account_id` differs from the stored one is not persisted; the credential is retired (`oauthAccountChange`, reason `account-changed`, error `OAUTH_ACCOUNT_CHANGED_ERROR`).

### Expiry / revocation handling
- Terminal refresh failures are classified by `terminalOAuthRefreshErrorMarker`: markers `invalid_grant, refresh_token_expired, refresh_token_reused, refresh_token_invalidated` (plus a Kimi one) **and** a terminal HTTP status 400/401/403 in the error chain, and no 5xx anywhere in the chain (a gateway 5xx quoting a marker is vetoed). Only then is the credential retired.
- Retirement = replace the secret with a marker, not delete the connection: `retireToReconnectMarker` writes `{kind:"oauth", reconnectRequired:true, ...keptSettings}` (settings such as per-model config survive) via `retireModelCredential` with a fence (`matchesFailedOAuthSecret`: only if the stored access/refresh/expires still equal the failed ones). Run error shown: `OAUTH_RECONNECT_REQUIRED_ERROR = "The sign-in token expired or was revoked. Connect that model provider again."` ("Worded so `isModelCredentialRejected` moves a run to its backup model."). `listModelCredentials(... runnable:true)` hides `reconnectRequired` connections.
- Transient refresh failures never retire the credential.
- Disconnect (`models.disconnect` in `routes/models.ts`): first `oauthLogins.cancelProvider(...)` so a finishing sign-in cannot resurrect the credential, then deletes `UserModelCredential` rows, role choices and the secret. **Rakazo never calls a provider revoke endpoint**; none exists in the code (searched `revoke`: only the error message text).

## 6. Using the token for a model request

What the repo shows:
- Request-scoped credential store: `credentialStoreForRequest` -> `new PiRuntimeCredentialStore(provider, toOAuthCredential(oauth.credential), persist, retire, refresh)`; `modelsForRequest` builds `builtinModels({ credentials: store })`. `resolveRuntimeModel` sets `apiKey = undefined` when `modelConfig.oauth` exists; pi-ai resolves the bearer through the store (`resolveModelAuth` -> `oauth.toAuth(credential)` returns `{apiKey}`; if empty: "Subscription sign-in did not produce a usable token. Sign in again.").
- Codex backend: Rakazo itself calls `GET https://chatgpt.com/backend-api/codex/models?client_version=0.169.1` (`pi-codex-catalog.ts`, `fetchCodexCatalog`) with:
```ts
headers: {
  authorization: `Bearer ${accessToken}`,
  "chatgpt-account-id": accountId,
  originator: "rakazo",
  accept: "application/json",
},
redirect: "error",
```
  Keeps only entries with `visibility === "list" && supported_in_api`. This is used to pick a default model and to clear a static exclusion (`codexLiveListsModel`). `subscriptionModel: { id: "gpt-6.1-sol", thinkingLevel: "low" }` for Codex and `{ id: "claude-opus-5-5", thinkingLevel: "low" }` for Anthropic are the models a new subscription sign-in preselects.
- `provider-request-shape.test.ts` constructs an `openai-responses` model with `Authorization: Bearer` and `chatgpt-account-id` headers, evidence that Codex runs use the **Responses API** shape and a `chatgpt-account-id` header. Compute residency: `codexComputeResidency(accessToken)` reads claim `chatgpt_compute_residency` ("Forwarded unvalidated so future regions work without a client update").
- Anthropic: the repo contains no code that sets `anthropic-beta`, a `user-agent`, or a base URL for model calls; those are pi-ai's. The only `anthropic-beta` use is the usage read (section 8): `"anthropic-beta": "oauth-2025-04-20"`. Anthropic custom endpoints also support `apiProtocol: "anthropic-messages"` (`openai_compatible` kind); the runtime uses the Messages API for Anthropic, but the exact call is not in this repo.
- Self-host alternative that does drive an official CLI: `providers/cli-model/claude-code/*` runs the user's own `claude` CLI per turn (`docs/self-host-models.md`: "Rakazo never reads, stores, forwards or refreshes your Claude sign-in, and every request to Anthropic is the CLI's own"). Hard limits: source checkout only, same OS user, one account on the server and no billing (`personal-cli-runtime.ts`, `cli-models/personal-access.ts`), env allowlist excludes `ANTHROPIC_API_KEY`, optional `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token` behind `RAKAZO_CLAUDE_CODE_SETUP_TOKEN=1`. The model object has `cost: 0` so cost is recorded as unknown.

## 7. API shape per route (what is verified vs inferred)
- ChatGPT subscription: Responses API shape with `chatgpt-account-id` (test evidence). Base URL not in repo (pi-ai); the Codex catalog host `chatgpt.com/backend-api/codex` is the only ChatGPT-backend URL in the repo.
- Claude subscription: Messages API (inferred from provider type; not visible in repo).
- API keys: standard provider APIs through pi-ai; protocol per provider; OpenAI-compatible endpoints support `apiProtocol` (`ModelApiProtocolSchema`) including `anthropic-messages`.

## 8. Usage / limit display (`packages/adapters/src/billing/plan-limits.ts`)
`PlanLimitsReader` reads subscription allowances with the member's own token, surfaced by `usage.limits` in `apps/api/src/routes/content.ts` and rendered by `apps/web/src/components/billing/PlanUsage.tsx`.
```ts
// Claude
getJson(fetchImpl, "https://api.anthropic.com/api/oauth/usage", {
  authorization: `Bearer ${credential.access}`, "anthropic-beta": "oauth-2025-04-20" })
// ChatGPT
getJson(fetchImpl, "https://chatgpt.com/backend-api/wham/usage", {
  authorization: `Bearer ${credential.access}`, "chatgpt-account-id": accountId, originator: "rakazo" })
```
- Claude parse: windows `five_hour` -> "session", `seven_day` -> "week", fields `utilization` (percent) and `resets_at`. ChatGPT parse: `rate_limit.primary_window` / `secondary_window` with `used_percent`, `limit_window_seconds`, `reset_at`; period from window length (<= 1 day session, <= 8 days week, else month).
- Cache: fresh 60 s, failure retry 15 s, stale 30 min then dropped, max 512 entries; errors never surface (they may carry account details); API-key and `reconnectRequired` connections return nothing; expired token triggers a background refresh instead of a read.

## 9. Error handling
- Sign-in end reasons: `signInFailure` (`pi-oauth-ended.ts`) reduces the provider error to a fixed reason (`expired`, `timed_out`, `provider_refused`) and class (`denied`, `invalid_code`, `unavailable`, `rate_limited`, `rejected`, `other`). User-visible texts never quote provider text: "Sign-in was declined. Start again.", "That code did not work. Start again.", "Sign-in is unavailable right now. Try again in a minute.", "This code expired. Start again." (`MODEL_SIGN_IN_EXPIRED_ERROR`).
- Provider down at begin: `isTransientModelError`/`isSignInRetryRequest` -> `ClientError("SERVICE_UNAVAILABLE")` and `markExpectedFailure()`.
- Plan without access: (1) static exclusion list for ChatGPT-subscription-only models (Codex Spark) plus live catalog override; the connect step rejects with `validateModelAuthAvailability` message unless the live catalog lists it; (2) runtime classification in `packages/core/src/runs/run-error.ts`: 401/invalid key -> `kind:"auth"` ("Your model provider rejected the API key. Check your connection settings."), 403/not-available/terms -> `kind:"access"` ("Your model provider denied access to this model.", `recovery:"model"`), rate/credit kinds, context kinds; a pasted PAT is recognized ("personal access tokens are not supported"). `docs/model-subscriptions.md` also warns: "A sign-in option alone does not establish permission for every Rakazo workload."
- Fallback: a rejected credential moves the run to the configured backup model (`isModelCredentialRejected`); fallback can use a separately billed key when the subscription limit is hit (docs).
- Save failures: `SIGN_IN_SAVE_FAILED = "Could not save the sign-in. Try again."`, `SIGN_IN_INTERRUPTED`, `SIGN_IN_NOT_FOUND`; refusals the user can act on (`ModelSignInError`, `ModelProviderNotAllowedError`) keep their text.
- Sign-in lifecycle robustness: one active sign-in per (user, space, provider, credential) scope, newer replaces older; leases (30 s, renewed every 10 s) so a dead process reads as "interrupted"; outcomes retained 1 h in `model_oauth_sessions`; abandoned rows swept on every begin.

## 10. Terms of service / official vs unofficial
- No code comment claims the OAuth routes are sanctioned. Both client IDs are commented only as public IDs "used by the Codex CLI" / "used by Claude Code". The ChatGPT calls send `originator: "rakazo"` (identifies itself, not as Codex CLI) but the `client_version` is pinned to the Codex CLI version `0.169.1`.
- Docs hedge explicitly: `docs/model-subscriptions.md` links OpenAI's authentication doc and Anthropic's "authentication and credential rules" (`https://code.claude.com/docs/en/legal-and-compliance#authentication-and-credential-use`) and says "Your use remains subject to Anthropic's terms". For Copilot/Grok: "check the provider's current terms, eligible clients, and included models".
- The only route described as "official" is the self-host `claude` CLI (Rakazo never touches tokens). Deployments can disable providers via the allowlist (`model-provider-allowlist.ts`, `assertModelProviderAllowed`).
- Plan billing text for ChatGPT: "Uses your OpenAI subscription. Rakazo does not pay."; Claude: no billing copy.

## 11. What I could not find
- The OAuth **refresh** endpoint, body and headers for both providers (inside `@earendil-works/pi-ai` 1.6.0, not vendored).
- The model-request base URLs and headers actually sent for ChatGPT (beyond `chatgpt-account-id`/`originator` seen elsewhere) and for Claude (`anthropic-beta`, `user-agent`, system-prompt requirements): not in this repo.
- Any token revoke endpoint call: none exists; disconnect only deletes local copies.
- Any userinfo/profile endpoint: identity is decoded from JWT claims only.
- The Anthropic flow's behaviour regarding Anthropic's rules on third-party use of Claude Code client ID: no comment or guard in code beyond the doc links.
- Not read in full: `pi-oauth.ts` lines 540-1210 (resume/claim/cancel/handoff internals were skimmed), the mobile hook beyond its header, `PlanUsage.tsx`, onboarding hooks.

## 12. Tests that cover these flows
- `packages/adapters/src/runtime/pi/models/pi-anthropic-oauth.test.ts`: concurrent paste-back flows, code-page redirect URI, state mismatch rejection, oversized/streamed token response caps, request deadline.
- `packages/adapters/src/runtime/pi/models/pi-chatgpt-device-code.test.ts`: waits through provider errors/cut bodies, refusal handling (also as 403), OAuth-code-only error extraction, unfamiliar pending codes, account id from top-level claim, already-expired credential, `slow_down`, expiry, retries (code request and token exchange, no retry on cut-off exchange), cancellation.
- `packages/adapters/src/runtime/pi/models/pi-oauth.test.ts` and `pi-oauth.postgres.test.ts`: `PiOAuthLogins` lifecycle, handoff across processes (Postgres).
- `packages/adapters/src/runtime/pi/models/pi-oauth-ended.test.ts`: failure classification.
- `packages/adapters/src/runtime/pi/models/model-sign-in-log.test.ts`: sign-in log events.
- `packages/adapters/src/runtime/pi/models/pi-credentials.test.ts`: runtime credential store: serialized refresh, terminal retirement, transient non-retirement, account-change retirement, stale-fence skipping.
- `packages/adapters/src/models/model-credential-refresh.test.ts`: lock/connection release around concurrent settings saves.
- `packages/adapters/src/runtime/pi/models/pi-codex-catalog.test.ts`, `pi-live-catalog.test.ts`, `pi-catalog-availability.test.ts`: Codex catalog parsing, availability exclusions.
- `packages/adapters/src/billing/plan-limits.test.ts`: Claude/ChatGPT limit parsing, caching, allowlist, expired token.
- `packages/adapters/src/models/model-connect.test.ts`, `model-connect-check.test.ts`, `model-provider-conformance.test.ts`, `model-credentials`-related `apps/api/src/models/model-credentials.test.ts`, `router-model-credentials.test.ts`: API-key connect, key check, provider registry conformance.
- `packages/adapters/src/runtime/provider-request-shape.test.ts`: request shape capture including the `chatgpt-account-id` header redaction.
- `packages/core/src/runs/run-error.test.ts`: auth/access/rate/credit error classification.
- `packages/adapters/src/providers/cli-model/claude-code/provider.test.ts`: the official-CLI route.
- Web: `apps/web/src/lib/models/use-model-oauth-signin.test.tsx` (codePage true on web, flow), `apps/web/e2e/settings/model-settings.spec.ts`. Desktop: `apps/desktop/src/main/auth/browser-auth.test.ts`, `oauth-callback.test.ts`. Contracts: `packages/contracts/src/index.test.ts` (`ModelOAuthBeginSchema` mode checks).

## 13. What Lonora should copy / avoid

Lonora: Python (FastAPI) server, React web, Expo mobile. Rakazo is TypeScript, so copy the design, not the code.

Copy
1. Keep a provider-agnostic `StoredModelSecret` union (`api_key | oauth | reconnectRequired`) serialized to one encrypted blob. The `reconnectRequired` marker that preserves per-model settings is a good pattern: never delete a connection on a dead refresh, flip it to "reconnect" and keep the user's choices.
2. Encrypt with AES-256-GCM, per-record random salt/IV, record id as AAD (`secrets.py` with `cryptography`'s `AESGCM`; derive the key with scrypt or HKDF from a server master key; allow KMS wrapping later).
3. Device-code for ChatGPT is the right shape for a server: the server runs the whole flow (usercode -> poll -> token exchange), and the web/mobile client only shows a code and polls a `complete` endpoint. Copy its resilience rules: keep polling through 5xx/network blips until the code TTL (15 min), honor `slow_down`, never retry a spent single-use authorization code after a timeout, keep only fixed OAuth error names from provider bodies, cap response size.
4. For Claude, paste-back PKCE (redirect to Anthropic's code page, user pastes) works on web and Expo with no loopback listener. Verify `state` before the exchange; store the verifier server-side (encrypted, ephemeral) so any API worker can finish it.
5. One sign-in per scope with replace-on-new, a lease so a dead worker reads as "interrupted", and persisted outcomes so a slow client can still read the result. In FastAPI use a `model_oauth_sessions` table and `asyncio` tasks; poll from the client.
6. Refresh discipline: refresh when `expires - now < 5 min`; take a Postgres advisory lock per credential (`pg_advisory_xact_lock(hashtext(secret_id))`) and re-read the stored copy inside the lock, because refresh tokens rotate and two workers would burn each other. Persist the rotated token in the same transaction. Classify terminal failures conservatively (OAuth error name AND 400/401/403, never with a 5xx in the chain).
7. Guard against account switches on refresh (compare `chatgpt_account_id` before saving).
8. Show plan usage by calling the providers' usage endpoints with the user's token and cache it (60 s fresh, 30 min stale): `GET https://api.anthropic.com/api/oauth/usage` and `GET https://chatgpt.com/backend-api/wham/usage`. Treat parse failures as "unknown", never as an error banner.
9. Never echo provider error text to users or logs; map to fixed reasons/classes. Redact `access` and `refresh` in every log.
10. Connect-time verification for API keys: ASCII-only key check, optional read-only key-check URL, then one minimal real request that aborts at first byte; block only on auth/access/model/credit kinds.
11. Put an allowlist of enabled providers in config and enforce it server-side on connect and on listing.
12. Keep the registry data-driven (login label, hint, setup link, recommended model per provider) so web and Expo render the same steps.

Avoid or decide deliberately
1. Using the Claude Code and Codex CLI public client IDs from a third-party app. Rakazo does it and hedges only in docs. Decide the legal position first; Anthropic's rules on third-party use of subscription OAuth tokens are the main risk. If Lonora wants a lower-risk Claude route, prefer the self-host official-CLI mode or API keys, and keep the subscription route behind a config flag that can be turned off without a release.
2. `state = PKCE verifier` (Rakazo copies Claude Code's behavior, so the verifier is exposed in the authorize URL and desktop callbacks). If the provider tolerates it, use a separate random state.
3. Depending on an external library (pi-ai) for refresh and request headers: Lonora should own the refresh call (endpoint, body, headers) and a small provider table so behavior is testable in Python. This repo's tests can't pin that because it is hidden in the dependency.
4. No provider revoke on disconnect. Lonora should call the provider's revoke endpoint when one exists, or at least say in the UI that access is only removed locally.
5. Complexity of the multi-process handoff: do it only if Lonora runs several API workers. A single-process in-memory session plus a DB row for restart recovery is enough to start.
6. Sending `client_version` pinned to a Codex CLI version and `originator` are fragile coupling to an undocumented backend; keep them in one constant and expect to bump them.
7. Static model exclusions for subscription tiers (e.g. Codex Spark): prefer the live per-account catalog (`/backend-api/codex/models`) as the source of truth, with the static list as fallback only.
