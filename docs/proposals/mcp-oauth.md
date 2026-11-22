# MCP sign-in with OAuth — specification

**Status: Proposed; the need is confirmed by the owner (D45, 2026-11-22: «يلزم MCP OAuth»).** Remote MCP servers that
accept only an OAuth sign-in cannot be connected to Lonora today. This specifies how Lonora signs in to them, following
the MCP authorization specification (revision 2026-07-28). It changes no trading path.

---

## 1. Today (in the code)

| Part | State |
|---|---|
| Saving a server | The Secret card's `mcp_server` target saves the address and an optional token, then creates the connection (`apps/api/src/lonora_api/routes/secret_cards.py`) |
| Sending a credential | `HttpMcpTransport` sends that token as a static `Authorization: Bearer` header (`packages/adapters/src/lonora_adapters/mcp/transport.py`) |
| OAuth | `pkce_pair`, `authorization_url` and `exchange_code` in `packages/adapters/src/lonora_adapters/mcp/oauth.py`, **called by nothing**. No discovery, no client registration, no callback, no refresh, no `resource` parameter, no `iss` check |
| Protocol | The client speaks only `2025-06-18` (`initialize` handshake and `Mcp-Session-Id`, `connector.py`, `transport.py`) |

The helpers are built but off, which VISION §13 forbids. This specification completes them.

## 2. What the owner sees

1. The owner asks to connect a server (the address only). The agent opens the Secret card as today.
2. If the server answers `401` with an OAuth challenge, the card does not ask for a token. A **sign-in card** appears in
   the conversation instead: the server's name and address, the sign-in provider's address (its issuer), and the scopes
   asked for.
3. The owner taps «تسجيل الدخول». The provider's page opens in the browser (a Custom Tab in the Android app). The owner
   signs in there and approves. Lonora never sees the provider password.
4. The browser returns to the owner's own Lonora. The card settles as "connected" and the agent is woken to say so.
5. The tools still run only after the owner trusts the server (`mcp_trust`, `docs/mcp-boundary.md`). **Signing in is
   not trust.** The read tier, the non-financial write tier and the financial-tool classifier are unchanged.

When a sign-in expires, or the server asks for more scopes, the agent opens a new sign-in card. Lonora never widens
the scopes silently.

## 3. Design

### O1 — Discovery (MCP authorization, "Authorization Server Discovery")
- On `401`, parse `WWW-Authenticate`. Use its `resource_metadata` URL when present; otherwise request the well-known
  Protected Resource Metadata URIs (RFC 9728) in the order the specification gives.
- From the metadata's authorization server, fetch its metadata by both mechanisms the specification requires: OAuth
  Authorization Server Metadata (RFC 8414) and OpenID Connect Discovery, each tried at the paths the specification lists.
  Validate each document as RFC 8414 §3.3 and OIDC Discovery §4.3 require.
- Refuse a server whose metadata does not offer `S256` in `code_challenge_methods_supported`.
- Every fetch goes through `validate_public_url`, over HTTPS, with redirects off and a size limit, as the MCP transport
  does today.

### O2 — Client registration (each installation is its own OAuth client)
Lonora follows the specification's priority order:
1. **Client details the owner entered** for that provider on a Secret card (client ID and, if issued, a client secret).
2. **Client ID Metadata Document**, when the provider sets `client_id_metadata_document_supported`. The installation
   serves its own document at a public HTTPS path of its address (for example
   `https://ahmad.lonora.app/oauth/client-metadata.json`), with `client_id` equal to that URL, `client_name` "Lonora"
   and its callback in `redirect_uris`.
3. **Dynamic Client Registration** (RFC 7591, deprecated by the specification but still offered by many providers),
   when the metadata has a `registration_endpoint`, with the right `application_type`.
4. Otherwise the sign-in card says the provider needs client details, and the agent opens a Secret card for them.

The rules for credentials:
- Client credentials are stored per issuer, never reused with another authorization server, and registered again when
  the authorization server changes (specification requirement).
- An installation without a public HTTPS address (self-hosted on a home network) cannot serve the document, so it uses
  item 1 or 3. The browser reaches its callback on the home network.

### O3 — The sign-in
- PKCE with `S256` (the existing `pkce_pair`).
- The `resource` parameter (RFC 8707) is sent in the authorization request and in every token request, set to the
  server's canonical URL.
- Scopes come from the `WWW-Authenticate` challenge's `scope` if present, otherwise from `scopes_supported`.
- `state` is random, single-use, expires after 10 minutes, and is bound to the card, the owner and the connection.
- The issuer is recorded before redirecting. The callback validates `iss` (RFC 9207) as the specification requires,
  before the code is sent to any token endpoint. On a mismatch nothing from the response is shown or used.
- The callback is a route on the installation's own address (`/api/mcp/oauth/callback`). It accepts only a pending
  `state`; anything else is refused.

### O4 — Tokens
- The access token and refresh token are stored in the encrypted store as `integration` secrets of that connection. They
  are never workspace secrets, so no script can read them. They are never shown to the model, the conversation or any
  log, and redaction applies to them as to every secret.
- Every request to the server carries the access token in the `Authorization` header, never in the URL, and only to the
  server it was issued for (no passthrough, specification requirement).
- Refresh happens before expiry, and once on a `401`, under one lock per connection so a rotating refresh token is not
  used twice. If refresh fails (`invalid_grant`), the connection shows "sign-in needed" and the agent opens a new sign-in
  card.
- A `403` with `insufficient_scope` triggers step-up. A sign-in card asks for the added scopes, with a retry limit.
- When a connection is removed, its tokens are revoked (RFC 7009, where the provider offers it) and deleted.
- These tokens sign in to MCP servers only. They never sign in to a model provider (VISION §12; the guard in
  `tests/test_model_access_guard.py` stays).

### O5 — Protocol revisions
Servers built on revision `2026-07-28` are stateless: no `initialize`, no `Mcp-Session-Id`, `server/discover`, and the
version carried in `_meta`. The client gains that revision and keeps `2025-06-18` (and `2025-11-25`) for older servers,
choosing by `server/discover` and falling back to `initialize`. This is what makes "any MCP server" true beyond sign-in.

## 4. Lonora Cloud

- Each customer installation is its own OAuth client. Its callback and metadata document are on the customer's own
  domain, so authorization codes and tokens reach only that installation.
- The operator and the control plane never see a code, a token or a client secret (Amendment 3, item 3). Nothing here
  is a hosting hook: self-hosted installations with a public address work the same way.
- The workspace denial list (Amendment 3, item 11) is unchanged. Sign-in runs in the Gateway, not in the workspace.

## 5. Clients

The sign-in card is a fixed owner card in the web client and in the native app (Phase M, PM-T3). The app opens the
provider's page in a Custom Tab and returns to the conversation when the card settles.

## 6. Decisions for the owner

| ID | Decision | Recommendation |
|---|---|---|
| O-A | Registration order | Owner-entered details, then Client ID Metadata Document, then Dynamic Client Registration (the specification's order) |
| O-B | Add the stateless protocol revision (O5) in the same work | Yes: many new servers will use it |

## 7. Stages

| Stage | Content | Done when |
|---|---|---|
| S1 | O1 discovery and O2 registration | Tests against a fake server and authorization server: challenge header and well-known fallbacks, both metadata orders, metadata validation, the installation's metadata document, Dynamic Client Registration fallback, client details per issuer; the SSRF tests still pass |
| S2 | O3 sign-in, the sign-in card (web) and the callback | State single-use and expiring; `iss` mismatch refused; PKCE and `resource` sent; tokens stored encrypted and absent from conversation, events and logs (redaction test); the card settles and the agent is woken |
| S3 | O4 token use | Bearer on every request; refresh under a lock; one retry on `401`; step-up card on `insufficient_scope`; "sign-in needed" on `invalid_grant`; revocation on delete |
| S4 | O5 protocol revisions | A `2026-07-28` server and a `2025-06-18` server both connect and list tools |
| S5 | The card in the Android app; docs | Sign-in completes on a physical device; `docs/mcp-boundary.md` and `docs/trusted-sources.md` describe the built behaviour and this proposal is marked "Shipped" |
| S6 | A real provider | A public MCP server that requires OAuth connects end to end, signs in, lists tools and is trusted |

## 8. Mandate check

Sign-in is the owner's own act on the provider's page; tokens stay in the owner's encrypted store (§7.2). Trust remains
the owner's typed message, and financial tools stay untrusted (`docs/mcp-boundary.md`). Money still moves only through
the execution door (§6), and trading stays MetaTrader-only (Amendment 2). Model access stays API keys (§12). This
completes built code that is off (§13).
