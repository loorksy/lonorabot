# OpenMausBot: subscription sign-in (OpenAI, Anthropic) and API keys

Source: `milind-soni/OpenMausBot` at commit `140172d` (v0.1.182). All paths are repo-relative. Read-only study; nothing was executed.

OpenMausBot is a TypeScript (Node) server plus React web app. It does not call model APIs for subscription users itself. It drives the vendors' official CLIs (Codex, Claude Code) as engines, and adds one first-party OAuth client for ChatGPT plans. API keys are a separate path using plain HTTP drivers or the CLIs with an injected env key.

## 0. Summary table

| Flow | Protocol | Who holds tokens | Model call |
|---|---|---|---|
| (a) OpenAI API key | static bearer key, saved in app config | OpenMausBot `config.json` (mode 0600, plaintext JSON) | `POST {base}/chat/completions` or `/responses` (`server/drivers/openai-chat.ts`, `openai-responses.ts`) |
| (a) Anthropic API key | static key, saved in app config | same | Claude Code CLI with `ANTHROPIC_API_KEY` (+ optional `ANTHROPIC_BASE_URL`) in its env; CLI speaks Messages |
| (b1) ChatGPT plan, local machine | OAuth 2.0 auth code + PKCE (S256), loopback redirect, OpenAI "agent" client registration | OpenMausBot (`credentials.json` 0600 per account) | Codex CLI pointed at `https://api.openai.com/v1` with the plan access token, `wire_api="responses"` |
| (b2) ChatGPT plan, hosted/cloud server | `codex login --device-auth` (device code), run as a child process | Codex itself (`<CODEX_HOME>/auth.json`) | Codex CLI with its own login |
| (c) Claude Pro/Max | Official `claude auth login` driven with pipes; user pastes the code Anthropic shows | Claude Code itself (`.credentials.json` / Keychain) | Claude Code CLI; no OAuth client code in the repo |

## 1. API keys

### 1.1 User-visible steps
1. Settings, AI section: key catalog row for OpenAI (`sk-...`, link `https://platform.openai.com/api-keys`) or Anthropic (`sk-ant-...`, link `https://console.anthropic.com/settings/keys`). Defined in `src/components/keys/key-catalog.ts` (ids `openai`, `anthropic`; env names `OMB_OPENAI_API_KEY`, `OMB_ANTHROPIC_API_KEY`).
2. User pastes the key. A "test" button calls the server's key check (`test: "openai"` / `"anthropic"`).
3. Saved key shows only a configured flag and last four characters (admins only).
4. Anthropic only: a flag `everyClaudeBot` decides whether every Claude bot or only the "Claude (API key)" instance uses the key; the first key defaults it to off (`patch: ... everyClaudeBot: false`).
5. A phone paired with the server may write a key only (never a URL): `isPhoneKeyPatch` in `server/provider-key-check.ts`. Phone keys travel as HPKE-sealed envelopes (`server/phone-secret.ts`, test `phone-secret.test.ts`).

### 1.2 Validation endpoints (`server/provider-key-check.ts`, `checkProviderKey`)
- Anthropic: `GET https://api.anthropic.com/v1/models` with headers `x-api-key: <key>` and `anthropic-version: 2023-06-01`.
- OpenAI: `GET https://api.openai.com/v1/models` with `authorization: Bearer <key>`.
- OpenRouter uses `/api/v1/key` instead because its catalog is public.
- 401/403 -> `rejected`; other non-2xx -> `unexpected`; network error -> `unreachable`.
- The key is only sent over https (or http to loopback), `redirect: "manual"` so it is never replayed to another host (`keySafeUrl`, `isLoopback`).

```ts
const headers = input.provider === "anthropic"
  ? { "x-api-key": input.key, "anthropic-version": "2023-06-01" }
  : { authorization: `Bearer ${input.key}` };
const response = await fetchImpl(url, { headers, signal, redirect: "manual" });
```

### 1.3 Storage
- Config schema `server/config.ts` line ~312: `anthropic: { key, url, everyClaudeBot }`, `openai: { key }`. Env overrides: `OMB_ANTHROPIC_API_KEY`, `OMB_OPENAI_API_KEY` (config.ts ~723-726).
- Saved with `writeFileAtomic(p, JSON.stringify(disk, null, 2), { mode: 0o600 })` (config.ts ~990). NOT encrypted at rest: file permissions only. (Under the desktop app the parent holds keys in an "encrypted store" and passes them by env; `server/credential-env.ts`, `operatorEnvKey`. I did not read that store.)
- Hints: `server/key-hint.ts` returns last4 only for keys of at least 12 chars; `withoutKeyHints` strips them for non-admin sessions.
- Workspace key env names are stripped from every spawned engine process (`stripWorkspaceCredentialEnv`, `WORKSPACE_CREDENTIAL_ENV` in `server/credential-env.ts`), so a bot's shell cannot read them.

### 1.4 How a request is made with the key
- OpenAI key: `server/drivers/openai-chat.ts` posts `${apiUrl}/responses` or `${apiUrl}/chat/completions` with `authorization: Bearer <key>` and `content-type: application/json` (line ~290-293). Default route is Chat Completions; if OpenAI answers that function tools with reasoning are unsupported, `server/drivers/openai-responses.ts` (`createModelRoutes`, `ModelRouteRefused`) moves that model forward chat -> responses -> chat-reasoning-off, never looping. `/responses` is only tried on `api.openai.com/v1` (`isOpenAIAddress`).
- Anthropic key: `server/anthropic-key-env.ts` `anthropicKeyEnv()` returns `{ ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL? }`, injected into Claude Code's environment. The CLI makes the Messages API call. `server/claude-endpoints.ts` builds custom-endpoint instances the same way (`ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_API_KEY`, `ANTHROPIC_DEFAULT_*_MODEL`).
- Guard against accidental billing flips: `server/drivers/claude.ts` ~134 deletes an inherited `ANTHROPIC_API_KEY` unless it was injected on purpose ("would flip a subscription login to pay-as-you-go"); `server/drivers/codex.ts` ~228 deletes `OPENAI_API_KEY` for the same reason. `PROVIDER_CREDENTIAL_ENV` documents this intent.

### 1.5 Key errors
- `server/key-rejections.ts`: in-memory set of `url + sha256(key)[:32]` marks (key never retained). `rejectsKey(status, body)` treats 401 as rejected, and 400/403 only when the body says invalid/revoked/expired key, never when it mentions quota/billing/credits/rate limit. UI text: "The provider rejected this key. Change it in Settings -> AI."
- Missing key for a key-only Claude instance: `NO_ANTHROPIC_KEY` in `server/drivers/claude.ts` (~904, 1803).

## 2. ChatGPT / Codex subscription

There are two distinct implementations, chosen by `chatgptAccountSignsInByDevice` (`server/drivers/codex-account-home.ts`): device code where the server is hosted (`hostedWorkspaceConfigured` or `cloudHomeConfigured`), otherwise the first-party browser OAuth.

### 2.1 (b1) Browser OAuth with PKCE: `server/drivers/chatgpt-plan-auth.ts` (`ChatGptPlanAuthController`)

User-visible steps:
1. Settings -> Engines -> add a ChatGPT account (`POST /api/instances/chatgpt-accounts`, `server/routes/instances.ts` ~170, creates `chatgpt-<uuid>` with `config.authMode = "chatgpt-plan"`).
2. Click "Continue with ChatGPT" (`src/components/DeviceSignIn.tsx` with `browserPkce`). The UI calls `POST /api/instances/:id/auth/start`, receives `authorizationUrl`, opens it in a browser, and polls `GET /api/instances/:id/auth/status?flowId=...`.
3. On OpenAI's page the user signs in and chooses whether to share plan usage ("allow plan usage" consent). Copy: "Sign in on OpenAI's page and choose whether to share plan usage. Your password stays with OpenAI; credentials stay on this computer." (`engineSetup.chatgpt.security`).
4. Browser is redirected to a one-shot loopback listener; the server exchanges the code; the account shows "Using ChatGPT plan" with a "Manage usage" link to `https://chatgpt.com/settings/usage` (`ChatGptPlanStatus.tsx`).
5. The route refuses `auth/start` unless the request comes from the machine itself (not proxied, not a paired phone): "Continue with ChatGPT on the computer running ...". So the loopback redirect works only on the local machine; remote/hosted servers use device code (2.2).

Control flow (numbered):
1. `begin()`: private dir (0700), read saved `credentials.json`, get a per-host id from `providers/chatgpt-plan/host-id.json` (`urn:uuid:<uuid>`, under a file lock).
2. Generate `state`, `nonce`, `verifier` = 32 random bytes base64url each.
3. Start an HTTP server on `127.0.0.1:0`; redirect URI `http://127.0.0.1:<port>/auth/callback`.
4. Build authorize URL `https://auth.openai.com/api/accounts/authorize`:
```ts
client_id: clientId ?? "dynamic_agent_client", ext_agent_host_id: hostId,
...(clientId ? {} : { agent_name_hint: "openmausbot" }),
response_type: "code", redirect_uri, scope: SCOPES,
resource: "https://api.openai.com/v1", state, nonce,
code_challenge_method: "S256", code_challenge: sha256(verifier) // base64url
```
   Scopes: `openid profile email offline_access resource.invoke chatgpt.tokens.use.direct`. `login_hint` is the saved email; `prompt=consent` is added when a previous login lacks the direct scope.
5. Client ID is NOT hard-coded. The literal placeholder `dynamic_agent_client` is sent on first sign-in plus the host id and name hint; OpenAI "issues" a client id which comes back as a `client_id` query parameter on the callback and is then saved and reused (`complete()`: `params.get("client_id")`). The test fixture uses `oaiapp_fixture_account_1`, which suggests real ids look like `oaiapp_...` (inference, not confirmed). A saved id of `dynamic_agent_client` is rejected on read.
6. Callback handler checks: Host header equals redirect host, path `/auth/callback`, GET, state equal via `timingSafeEqual`, no duplicate params, flow not yet consumed; then closes the server and calls `complete()`.
7. `complete()`: reject `error` param; fetch JWKS `GET https://auth.openai.com/.well-known/jwks.json`; `POST https://auth.openai.com/api/accounts/oauth/token` (form body) with `grant_type=authorization_code, client_id, code, code_verifier, redirect_uri, resource`.
8. `tokenSet()` requires `token_type: bearer`, `0 < expires_in <= 86400`, an `id_token`, `scope`, and a refresh token when the direct scope was granted.
9. `identity()` verifies the id token with `jose` `jwtVerify` (issuer, audience = client id, RS256/ES256, `sub/exp/iat`, nonce, `azp` for multi-audience). A returning account must keep the same `sub`.
10. Under the lock, save `{ clientId, hostId, subject, email, tokens: { access, refresh, id, scopes, expiresAt, earliestRefreshAt? } }`. If the `chatgpt.tokens.use.direct` scope is missing, the flow ends `failed` with CONSENT text: "ChatGPT plan usage is not enabled. Continue with ChatGPT in Settings and allow plan usage, or explicitly choose another provider."

Storage: `<DATA_DIR>/providers/chatgpt-plan/<sha256(instanceId)>/credentials.json`, mode 0600, dir 0700, symlinks refused, atomic writes, plaintext JSON (not encrypted). Cross-process lock file `.credentials.lock` (fail closed: an abandoned lock is never broken, so a rotated refresh token is never reused).

Refresh (`accessToken()`), all under the lock:
- Return the stored access token if it has more than 60 s left.
- If `earliestRefreshAt` is in the future: return it while still valid, else "cannot refresh yet".
- Otherwise fetch JWKS first, then `POST .../oauth/token` with `grant_type=refresh_token, client_id, refresh_token, resource`.
- Terminal errors `invalid_grant, invalid_refresh_token, token_expired, refresh_token_expired, refresh_token_invalidated, refresh_token_reused` delete the tokens (keep the registration) and surface "Continue with ChatGPT in Settings to use your ChatGPT plan."
- `invalid_client` -> "ChatGPT did not accept this app registration."
- Other errors keep the account: "could not renew access right now ... saved account has not been removed."
- If the rotated response cannot be verified, tokens are deleted because the old refresh token is already consumed.

Revocation (`signOut()`): discovery `GET {issuer}/.well-known/openid-configuration` -> `revocation_endpoint` (must be same origin), `POST` with `token, token_type_hint=refresh_token, client_id`, one retry on 5xx; then always delete local tokens. If remote revocation is unconfirmed it throws code `chatgpt_revocation_unconfirmed`: "Signed out locally, but remote revocation was not confirmed. Disconnect OpenMausBot in ChatGPT Settings -> Usage to end access there."

HTTP hygiene (`request()`): `redirect: "error"`, 15 s timeout, 1 MiB response cap, generic error text with no body echo.

Model request with the token: the controller does not call the Responses API. `server/drivers/codex.ts` (create, ~1436-1450 and ~407-437) obtains `planAuth.accessToken()` and starts Codex with `chatgptPlanCodexArgs()` (`server/drivers/codex-plan-token.ts`):
```ts
"-c", 'model_provider="openai_chatgpt_plan"',
"-c", 'model_providers.openai_chatgpt_plan.base_url="https://api.openai.com/v1"',
"-c", 'model_providers.openai_chatgpt_plan.wire_api="responses"',
"-c", "model_providers.openai_chatgpt_plan.requires_openai_auth=false",
"-c", 'cli_auth_credentials_store="ephemeral"', "-c", "features.tool_search=false",
```
- Token delivery, old Codex: env var `OPENMAUSBOT_CHATGPT_TOKEN` via `env_key` (excluded from the agent shell via `extendShellExclusions`).
- Token delivery, Codex 0.165.0 or later (`renewsToken`): `auth.command` = this app's own runtime running `server/drivers/chatgpt-plan-token-command.ts`, `refresh_interval_ms=30000`, `timeout_ms=60000`. The command connects to a per-run local socket/named pipe bridge (`server/drivers/chatgpt-plan-token-bridge.ts`, secret `OMB_CODEX_AUTH_SECRET`, compared with `timingSafeEqual`, 60 s socket timeout) which calls `accessToken()` so the token is refreshed while a long Codex run continues. No OAuth credentials cross the command line.
- Request shape: OpenAI Responses API (`wire_api="responses"`), websockets off. The repo sets no custom `chatgpt-account-id` or user-agent for model calls; Codex builds the request. The only place this repo sets `ChatGPT-Account-Id` is the usage read (2.4).
- Model list: `GET https://api.openai.com/v1/models` with `Authorization: Bearer <token>`, parse `models[].{slug, display_name, visibility}`, keep `visibility === "list"` (`models()`). Note this is the plan-scoped catalog shape (`slug`), not the public API shape.

Errors and plan limits:
- 401/403 from /models: "ChatGPT did not authorize model access. Check this account's plan permissions in ChatGPT Settings."
- A model that /models lists but ChatGPT refuses ("The 'gpt-6.1-sol' model is not supported when using Codex with a ChatGPT account.") is remembered per account in `refused-models.json` via `refuseModel()` (called from `codex.ts` ~279) and hidden until sign-in/out.
- Expiry of the flow: 15 min (`LIFETIME`).

### 2.2 (b2) Device code: `server/drivers/codex-device-auth.ts` + `server/drivers/device-auth.ts`

Used for the built-in Codex instance and for hosted servers (own `CODEX_HOME` per account: `chatgptAccountHome`).
1. `DeviceAuthController.start()` runs `codex login status` first (`CODEX_DEVICE_SIGN_IN.status`). Signed in -> done; "other" (API key login) -> refuse to replace it; signed out -> continue.
2. Runs `codex login --device-auth` with pipes, `NO_COLOR=1`, cwd = credential home, one login per canonical home at a time (`authenticatingHomes` set).
3. Output is parsed by `deviceSignInPrompt("codex", ...)` in `shared/device-sign-in.ts`: only the page `https://auth.openai.com/codex/device` is accepted (regex `^https://auth\.openai\.com/codex/device/?$`) and a code shaped `^[A-Z0-9]{4,8}-[A-Z0-9]{4,8}$`. Anything else is never turned into a link. The UI re-checks the same rules.
4. User opens the page and enters the code. Codex polls OpenAI itself and writes `<CODEX_HOME>/auth.json` (OpenMausBot never sees the endpoints or tokens).
5. On exit 0, `codex login status` must match `^logged in.*chatgpt\b` -> `succeeded`.
6. Sign-out: `codex logout`, then status must read signed-out.
- Timeouts: 30 s for the CLI to show a code, 15 min lifetime. Failure texts map CLI output to safe sentences (`loginFailure`): old CLI needs `npm install -g @openai/codex@latest`; "Enable device-code login in your ChatGPT security settings or ask your workspace admin to allow it."; expired code.
- Status reading: `server/drivers/codex-login.ts` (`readCodexLogin`, `codexLoginCheck`): reads `auth.json` presence/JSON, falls back to `codex login status`; "Without a login Codex still runs a turn and fails only after a minute of reconnects", so a pre-turn check returns "missing".

### 2.3 Plan token read for usage and CLI logins
`server/plan-usage.ts` `readCodexCredential` reads `<CODEX_HOME>/auth.json` (`tokens.access_token`, `tokens.account_id`, expiry). Plans signed in through the browser OAuth have no `auth.json`, so they are marked `noUsage` (comment: reading `~/.codex/auth.json` would report another account's limit).

### 2.4 Usage display
`server/plan-usage.ts`: `GET https://chatgpt.com/backend-api/wham/usage` with `Authorization: Bearer <access_token>`, `Accept: application/json`, and `ChatGPT-Account-Id: <account_id>` when present. Parsed by `parseCodexUsage` into a 5-hour window, weekly window, extra named limits, per-model windows, plan label (`plan_type`) and a credits flag. 8 s timeout, 45 s cache. 401/403 -> "sign in again" row; 5xx/network -> "could not reach". UI: `src/components/EngineUsage.tsx`.

## 3. (c) Claude Pro/Max subscription: drive the official CLI, no OAuth in the repo

Header comment of `server/drivers/claude-login-auth.ts`:
```
// Signs the server's Claude Code CLI in from Settings: the unmodified `claude auth login` runs with
// pipes, only its sign-in link is shown, the pasted code goes to its stdin, and `claude auth status
// --json` confirms. Anthropic permits an end user signing in to the unmodified binary with their own
// subscription, even where a platform hosts it, and forbids flows that intermediate claude.ai
// credentials: hence no OAuth client code in this repository.
```
So the Claude subscription route is deliberately the CLI route. There is no client ID, scope, redirect URI, token or refresh endpoint anywhere in the repo for Claude login (verified by grep: no `claude.ai/oauth` or token URL use). Those live inside Claude Code.

User-visible steps (`src/components/ClaudeSignIn.tsx`):
1. Claude card -> "Sign in". UI calls `POST /api/instances/:id/auth/start`.
2. Server spawns `claude auth login` (with `BROWSER=true` on non-Windows so no browser opens on the server; `NO_COLOR=1`; env from the instance incl. `CLAUDE_CONFIG_DIR`). First it runs `claude auth status --json`: if already `loggedIn: true` it succeeds without replacing the login.
3. Server scans stdout/stderr for the first `https://` link whose host is `claude.com`, `claude.ai`, `console.anthropic.com`, `platform.claude.com` (or subdomains), https only, no userinfo (`claudeSignInLink`, `claudeLoginPrompt`). The same allow-list is duplicated client-side.
4. User opens the link, signs in with their Pro/Max account, and Anthropic's page displays a code (sometimes `code#state`).
5. User pastes it. `POST /api/instances/:id/auth/complete {flowId, code}`; `claudeLoginCode` allows `^[A-Za-z0-9_\-#.:]{8,1024}$`; the server writes `code\n` to the CLI's stdin.
6. When the CLI exits, `claude auth status --json` must say `loggedIn: true` (exit 0). A failed login maps output matching `invalid|expired|denied|rejected` to "Anthropic did not accept that code. Start sign-in again and paste the whole code it shows."
7. Timeouts: 30 s for the link, 60 s after the code, 15 min flow lifetime. One login per `CLAUDE_CONFIG_DIR` at a time (`authenticatingHomes`).

Sign-out: `claude auth logout`, then status must not be `in`. `ClaudeLoginController.signOut` refuses while a login is waiting.

Status: `server/drivers/claude-auth-status.ts` `claudeAuthStatus` runs `claude auth status --json` (8 s timeout): `loggedIn`, `email`, `orgName`, `authMethod === "api_key"` become the account badge. Only `loggedIn: false` counts as signed out; a timeout says nothing (Keychain prompts).

Token storage and refresh: owned by Claude Code (file `<CLAUDE_CONFIG_DIR or ~/.claude>/.credentials.json` or macOS Keychain service `Claude Code-credentials[-<sha256(dir)[:8]>]`). OpenMausBot never refreshes or revokes Claude tokens. For team clouds, `server/engine-homes/sign-ins.ts` and `layout.ts` copy `.credentials.json` between per-audience homes (`syncSignIn`, newest settled copy wins) so a refreshed token is kept.

Model request: the Claude Code CLI makes the call (Messages API); the repo only reads CLI JSON frames. No `anthropic-beta`, `user-agent` or Authorization header is set for turns.

Usage display (reads the CLI's token directly, the one place OpenMausBot touches it): `server/plan-usage.ts` `readClaudeCredential` reads `claudeAiOauth.accessToken` and `expiresAt` from `.credentials.json` (or Keychain via `security find-generic-password -s ... -w` on macOS, 5 s timeout), skips an expired token, then:
```ts
GET https://api.anthropic.com/api/oauth/usage
Authorization: Bearer <accessToken>
Accept: application/json
anthropic-beta: oauth-2025-04-20
```
Parsed by `parseClaudeUsage` (`five_hour`, `seven_day`, per-model `seven_day_opus/sonnet`, spend/extra usage, `subscription_type`). 401/403 -> "sign in again". An instance with `usageMeter: false` is not read.

Errors and limits at turn time:
- `server/drivers/claude-auth-recovery.ts`: Claude Code frames with `error: "authentication_failed"` (synthetic `<synthetic>` api-error message) or text matching `OAuth ... expired|revoked` (`claudeOAuthExpired`) are held back until the process stops and then rejected as `TurnAuthenticationRefusedError` so the UI shows a sign-in prompt instead of a chat reply. `api_error: "usage_limit_reached"` or a `rate_limit` + usage text -> `TurnUsageLimitRefusedError` with reset time and scope.
- `server/drivers/claude-limits.ts`: reads `rate_limit_info` (`status: "rejected"`, `rateLimitType` `five_hour | seven_day | seven_day_opus | seven_day_sonnet | overage`, `resetsAt`, `isUsingOverage`, `errorCode: credits_required`). Only an account-wide window holds the whole engine; a per-model weekly window or exhausted extra-usage credits leave other models usable. User text: "...switch account / choose another model", with local-timezone reset.
- Plan without access: Claude Code's own "does not support this model; version X or newer is required" is detected (`claudeVersionTooOld`); `claude-model-access.ts` handles model access (not read in depth).
- Multiple accounts: each added Claude account is its own instance with its own `CLAUDE_CONFIG_DIR` (`server/claude-accounts.ts`; removing an entry never deletes the dir or signs out).

## 4. Documentation / terms-of-service comments found
- `claude-login-auth.ts` header (quoted above): treats subscription use as permitted only through the unmodified binary operated by the end user; forbids intermediating claude.ai credentials. This is the one explicit policy statement.
- `chatgpt-plan-auth.test.ts` describes its flow as "official ChatGPT plan OAuth". The agent-registration parameters (`ext_agent_host_id`, `agent_name_hint`, `resource`, `chatgpt.tokens.use.direct`) look like an OpenAI-supported third-party path, but I found no doc in the repo citing the OpenAI program or its terms. I could not verify that from the repository alone.
- UI copy states the ChatGPT plan is separate from "MausBot Cloud" and from API-key billing (`engineSetup.chatgpt.description`).

## 5. What I could not find
- No Anthropic OAuth code, client id, scopes, redirect, refresh or revoke endpoint (by design, see section 3).
- No hard-coded OpenAI client id for the plan flow (issued dynamically; only the placeholder `dynamic_agent_client`).
- No at-rest encryption of API keys or ChatGPT tokens beyond file mode 0600 (the desktop "encrypted store" was not read).
- No explicit OpenAI terms-of-service reference in code.
- No `userinfo` endpoint use; identity comes from the verified id token.
- No model-request headers (`chatgpt-account-id`, `originator`, `user-agent`, `anthropic-beta`) set by the repo for turns; Codex and Claude Code add their own.
- `server/provider-auth-sessions.ts`, `server/routes/logins.ts` and `server/routes/cli-login.ts` were read in part: `logins.ts` is about website logins for bots and `cli-login.ts` is the `openmausbot login` terminal pairing, neither is model-provider auth.

## 6. Tests covering these flows
- ChatGPT plan OAuth: `server/drivers/chatgpt-plan-auth.test.ts` (PKCE exchange, identity/JWKS, state and callback hardening, consent missing, refresh serialization across controllers and processes, terminal vs temporary refresh failure, revocation unconfirmed, abort in flight, refused models), `server/drivers/chatgpt-plan-token-bridge.test.ts`, `server/drivers/codex-plan-token.test.ts`, `server/chatgpt-plan-api.test.ts`, `src/components/ChatGptPlanSignIn.interaction.test.ts`.
- Codex device/login: `server/drivers/codex-device-auth.test.ts`, `codex-login.test.ts`, `codex-shared-home.test.ts`, `codex-identity.test.ts`, `src/components/DeviceSignIn.test.ts`, `server/testing/fake-codex-login-cli.ts` (fixture).
- Claude: `server/drivers/claude-login-auth.test.ts`, `claude-auth.test.ts`, `claude-auth-recovery.test.ts`, `claude-accounts.test.ts`, `server/claude-account-api.test.ts`, `server/claude-endpoints.test.ts`, `src/components/ClaudeSignIn.test.ts`, `ClaudeSignIn.interaction.test.ts`, `server/testing/fake-claude-cli.ts`.
- Flow ownership and routes: `server/provider-auth-sessions.test.ts`, `provider-auth-stale.test.ts`.
- API keys: `server/provider-key-check.test.ts`, `provider-key-flow.test.ts`, `key-hint.test.ts`, `key-rejections.test.ts`, `key-rejected.e2e.test.ts`, `server/phone-secret.test.ts`, `src/components/SettingsModal.keys.dom.test.ts`.
- Engine homes: `server/engine-homes/sign-ins.test.ts`, `layout.test.ts`.

## 7. What Lonora should copy / avoid

Lonora is a Python (FastAPI) server, React web, Expo mobile trading assistant. Different constraint: it is a hosted multi-user product where one server serves many people, so the CLI-on-the-server model of OpenMausBot does not transfer directly.

Copy:
1. The security discipline of the OAuth client (`chatgpt-plan-auth.ts`): S256 PKCE, `state` compared constant-time, nonce, one-shot callback, id-token verification against JWKS with issuer/audience/subject pinning, `redirect: "error"`, response size and time caps, refusal to swap to a different account `sub`. All of this ports to `authlib` or `httpx` + `python-jose`/`PyJWT` on FastAPI.
2. Refresh-token rotation safety: take a lock, fetch JWKS first, never reuse a consumed refresh token, delete tokens when a rotated successor cannot be verified, keep the account on transient errors. In Python use a DB row lock (`SELECT ... FOR UPDATE`) per connection, not a file lock.
3. Strict allow-lists for what the server shows as a sign-in link (host regex, https only, no userinfo) and re-checking them in the client; also never echo provider response bodies in errors.
4. Mapping CLI/provider failures to a few safe sentences, and classifying auth-expired vs usage-limit separately (`claude-auth-recovery.ts`, `claude-limits.ts`): an expired login must prompt re-sign-in, a limit must show reset time and not block other models.
5. Key hygiene for API keys: validate with `GET /v1/models` (Anthropic `x-api-key` + `anthropic-version: 2023-06-01`; OpenAI Bearer), https-only and `redirect=manual`, store only a last-4 hint (>=12 chars), remember rejection by hash not by value, and treat quota/billing responses as not-a-bad-key (`rejectsKey`).
6. Strip provider keys from any env passed to tools/subprocesses; and delete inherited `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` where a subscription login is intended, so billing never flips silently.
7. Per-account credential isolation and a "never replace a working login" check before starting a new one.
8. The two-route model for OpenAI: loopback browser OAuth where the user's machine is the server, device code otherwise. For Lonora (web and Expo mobile), device code or a hosted redirect URI on the Lonora domain is the natural fit; loopback only works for a local desktop build.
9. Usage meter reads (`wham/usage`, `api/oauth/usage`) as optional, cached (45 s), failure-tolerant rows.

Avoid:
1. Do not implement a Claude Pro/Max OAuth client in Lonora. OpenMausBot's own header says Anthropic forbids flows that intermediate claude.ai credentials. A hosted multi-user server holding subscribers' Claude tokens is exactly that case. Offer Anthropic via API key only (or via the user's own Claude Code on their own machine), and say so in the UI.
2. Do not run a shared server-side `claude`/`codex` CLI login for many end users; OpenMausBot is single-owner software. Per-user CLI homes on a shared host are heavy and risky.
3. Do not hard-code or reuse another product's client id. OpenMausBot's ChatGPT flow works only because OpenAI issues a client per agent host (`dynamic_agent_client` + `ext_agent_host_id`); I could not confirm that program is open to Lonora. Treat the ChatGPT-plan route as unverified until OpenAI confirms terms for a third-party hosted trading product, and ship API keys first.
4. Do not store tokens or API keys as plaintext JSON with only file mode 0600 on a multi-tenant server. Encrypt at rest (envelope encryption with a KMS or Fernet/AES-GCM key held outside the DB) and keep per-user rows.
5. Do not parse a CLI's terminal output to get a link or code in a hosted setting unless unavoidable; it is brittle across CLI versions (this repo carries many version-specific regexes).
6. Do not let a bot or agent tool see provider tokens: keep them out of the agent's environment (their bridge exists only to hand a short-lived token to one Codex process).
7. For trading, keep provider credentials entirely separate from broker credentials and from the trade-approval path, so a leaked model token cannot authorize an order.
