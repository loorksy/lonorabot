# W-SWEEP study: the official MCP Python SDK in place of Lonora's MCP client, and other library reuse

Basis:
- Lonora at `integration/batch-14` 3f371259.
- The SDK wheels `mcp` 2.3.0, `mcp-types` 2.3.0 and `httpx2` 2.16.2, unzipped and read. Nothing was imported or run.
- Two research agents did the reading. I checked the key claims myself: the SDK's metadata and licence, the dead `oauth.py`, the pinned protocol version, the DNS-rebinding gap and the plural bug.

## Verdict

Adopt the SDK **only for what Lonora lacks**: newer protocol versions, OAuth and cancellation. It would delete about 150-175 lines (`transport.py`, the JSON-RPC framing in `connector.py`, `oauth.py`). It would add 100-150 lines of glue, and the 490 lines of policy stay.

The cost is a second HTTP stack. `mcp` 2.x depends on `httpx2`, not on our `httpx` 0.28, so our `httpx.MockTransport` tests and client code do not plug in. The SDK is also weaker than Lonora on several limits that we would have to re-impose. If OAuth is not wanted soon, **step 0 alone (delete the dead `oauth.py`) is the only clear win today.**

## 1. Feature comparison

| Feature | Lonora | SDK 2.3.0 | Verdict |
|---|---|---|---|
| Protocol version | Only `2025-06-18`, which it sends and requires (`connector.py:44,49`, `transport.py:49`) | Offers 2025-11-25 and accepts 2024-11-05 through 2025-11-25 (`mcp_types/version.py`, `client/session.py`) | Lonora fails against 2025-11-25-only servers |
| stdio | Refused at four layers (`transport.py:111-121`, `lonora_tools/mcp.py:120`, `routes/mcp.py:24`, `routes/trusted_sources.py:101`) | `stdio_client` always passes HOME, LOGNAME, PATH, SHELL, TERM and USER, even with `env={}` | Lonora stricter. Keep the refusal; never use `stdio_client`. |
| Streamable HTTP | POST, a fresh session per call, JSON or SSE reply, session id, 202 for notifications | Standing GET stream, `Last-Event-ID` resumption, DELETE on close | SDK fuller; matters little with a session per call |
| Legacy SSE | None | `client/sse.py` | SDK only |
| OAuth | Static bearer only. `oauth.py` (PKCE) is dead: nothing imports it. | Discovery (RFC 9728 and 8414), PKCE S256, dynamic registration, refresh, RFC 8707 `resource` | Lonora missing |
| tools/list pages | Cursor loop capped at 10 pages and 200 tools; refuses duplicate names, repeated cursors and oversized schemas (`connector.py:65-110`) | One page per call; no limits | Lonora stricter. Keep its checks. |
| Cancellation and progress | `asyncio.timeout` per phase and request; no `notifications/cancelled` | Sends `notifications/cancelled`; progress; ping | SDK better |
| Server requests (sampling, elicitation, roots) | Silently dropped, so the server waits | Refused with an error; not advertised | SDK better |
| JSON-RPC errors | Strict framing; remote text never surfaces (`mcp_protocol_error`) | `str(MCPError)` is the remote message | Lonora stricter. Map errors to codes. |
| Session id, redirects, size | Session id ≤256 printable ASCII; no redirects; 2 MiB total; identity encoding only | Session id unchecked and logged at INFO; follows same-origin 307/308 itself; 1 MiB per SSE event but no total; gzip by default | Lonora stricter |

## 2. What must stay on top of the SDK, and where it hooks in

- **Pinned schema hash and "a changed tool waits"** (`policy.py:20-29,98-102`; `lonora_tools/mcp.py` `tool_state` and `execute`).
  - Hash the raw `inputSchema` from `list_tools()`. A byte-exact round-trip test is required, or every pinned hash changes.
  - Never use `Client`'s response cache.
- **Financial-tool refusal** (`policy.py:120-414` `financial_tool`, re-checked in `execute`). This is independent of the SDK.
- **No environment passthrough.** Keep the stdio refusal (see the table).
- **Secret redaction of results** (`tool_results.py`, `lonora_security.secrets.redact`). Unaffected, but there is new log exposure: `httpx2` logs request URLs at INFO, and the SDK logs URLs and session ids. A server address can now carry a key, so set the `httpx2` and `mcp` loggers to WARNING (today `configure_logging` quiets only `httpx`).
- **Timeouts and caps.** Keep the `asyncio.timeout` wrappers and pass `read_timeout_seconds`. Put the 2 MiB cap, identity encoding, the refusal of compressed replies and the no-redirect rule in a custom `httpx2.AsyncBaseTransport`.
- **SSRF.** `streamable_http_client(url, http_client=...)` accepts an injected `httpx2.AsyncClient`, so the guard sits in that transport and checks every request. That includes SDK-followed redirects and OAuth discovery and token calls. Pin the resolved IP there: today's guard has a DNS-rebinding gap (section 6).
- **Trusted-source policy** (`lonora_db/trusted_sources.py`; operator declarations in `policy.py`). It sits above the client and is unaffected.

## 3. Licence and dependency weight

- **Licence:** `mcp` and `mcp-types` are MIT (Copyright 2024 Anthropic, PBC); `httpx2` is BSD-3.
- **New packages:** `mcp`, `mcp-types`, `httpx2`, `httpcore2`, `sse-starlette`, `truststore`. starlette, uvicorn, pydantic, PyJWT, jsonschema and anyio are already present.
- **Weight:** `import mcp` loads the server modules too.
- **Pinning:** use exact pins and treat every upgrade as its own reviewed PR. The 2.x API is still moving: TODOs in `session.py`, and a 2026-07-28 stateless mode. Use `ClientSession` directly, not `Client(mode="auto")`.
- **Async model:** anyio on asyncio. Task groups must open and close in the same task, so the facade holds an `AsyncExitStack`. Today's `open_connector` already opens and closes in one task. An outer `asyncio.timeout` cancelling an anyio task group needs its own test.

## 4. Risks, and what the SDK does not give us

- No limits on tool count, cursor, length, name or total reply; no session-id checks; remote error text exposed; same-origin redirects followed automatically.
- No allow-list, endpoint or schema pinning, money rules or effect receipts. All of that stays ours.
- Its OAuth awaits the redirect and callback inside one request flow. A web app where the owner approves later needs a database-backed `TokenStorage` and a split flow.
- It brings new behaviour that needs deliberate choices: a standing GET stream, reconnects, and output-schema validation that can raise in `call_tool`.

## 5. Step plan (one PR each; new path first, old path deleted last)

Tests that stay green throughout:
- all of `tests/test_mcp_boundary.py`, `tests/test_mcp_configuration.py`, and the MCP and money tests in `tests/test_trusted_sources.py`
- `tests/test_connection_tests.py::test_mcp_test_is_remote_only_and_broker_test_refuses_a_linked_account`
- `tests/check_mcp_directory.py`, `check_trusted_sources.py`, `check_simple_lonora.py`. These patch `HttpMcpTransport`: keep that seam name, or migrate them in the switch PR.

0. **Delete the dead `adapters/mcp/oauth.py`** (54 lines; no SDK needed). Proof: no import; the full gate.
1. **Pinned `mcp`/`httpx2` and a `GuardedTransport`.** It validates every request with an IP pin, refuses redirects, uses identity encoding, caps at 2 MiB and refuses compressed replies; it also quiets the loggers. Tests: httpx2 versions of the bounded-failure and compressed-reply tests; a private address refused before any connection; a redirect refused; the URL key absent from logs.
2. **`SdkMcpConnector`** with the same interface (`initialize`, `tools`, `execute`, `close`): `ClientSession` plus `streamable_http_client(http_client=guarded)`. It reuses the `connector.py:65-110` checks and maps `MCPError` and timeouts to the existing codes. Tests: the malformed-protocol, duplicate-name, unbounded-description, phase-budget and SSE-result tests, run against both connectors; a byte-exact schema-hash test; a "remote error text never surfaces" test.
3. **Switch the two call sites** (`lonora_tools/mcp.py` `open_connector`, `routes/connection_tests.py`) to one factory. Test: `tools/call` is sent at most once on timeout (a cancel notification, never a resend).
4. **Delete** `HttpMcpTransport`, `decode_response` and `McpConnector.call`. Keep the stdio refusal and its test.
5. **Optional: OAuth** through `OAuthClientProvider`, with database-backed `TokenStorage` and a split callback. Tests: state mismatch, refresh, `resource`, discovery through the guard.

Owner: none of this is in W-SWEEP's area. It belongs to whoever holds MCP and trusted sources (W-ENV / the trusted-sources owner in `maps/TEAM.md`).

## 6. Other places where an established library would replace custom code with the same safety

Ranked by value against risk. Already dependencies, so not proposed: croniter, tiktoken, jsonschema, pwdlib, webauthn, PyJWT, cryptography, Lingui.

1. **Feed DTD and entity refusal → `defusedxml`** (PSF, pure Python, no dependencies).
   - Custom code: `adapters/market/news_feed.py`, about 25 lines. A byte scan plus encoding reasoning refuses UTF-16 and UTF-32 bodies outright.
   - With `defusedxml.ElementTree.fromstring(body, forbid_dtd=True)`, refusal happens at the parser, whatever the encoding. Legitimate UTF-16 feeds then parse.
   - Keep: the 2 MiB cap, the item and length bounds, HTTPS-only links, the `public_get` SSRF pin.
   - Caveat: its last release was 2021. It is stable and recommended by the Python docs, but quiet. A stdlib alternative is an expat `StartDoctypeDeclHandler` that raises (about 8 lines).
   - Test: `test_feeds_parse_bounded_untrusted_text_and_refuse_entities`, plus a new valid UTF-16 feed case.
2. **RSS/Atom extraction → `feedparser`** (BSD-2, maintained, one dependency).
   - It replaces about 65 lines and parses many more date formats, `content:encoded`, RSS 0.9x and encoding detection.
   - Hazards found in its source: given a string it fetches URLs itself, bypassing our SSRF guard; it tries `open()` on its input as a local path; and it falls back to a loose parser that expands entities.
   - Safe only if it always gets `io.BytesIO(body)` and the DTD refusal (item 1) stays as a pre-check. Medium risk.
3. **`web_fetch` HTML-to-text → `beautifulsoup4`** (MIT, one dependency). The alternative is `trafilatura` (Apache-2.0, heavy: lxml, htmldate, justext…).
   - Custom code: `lonora_tools/search.py` `TextParser`, 17 lines. It always decodes as UTF-8, ignoring the charset; it keeps navigation text; and it hides only `script` and `style`.
   - Keep: the 2 MiB cap, the 24,000-character cut and the `untrusted_content` shape.
   - No test covers the extraction today, so fixture tests come first.
4. **Mobile Arabic plurals → `Intl.PluralRules("ar")`** (platform, no dependency), or reuse core's existing CLDR-correct `arCount` (`packages/core/src/genui/functions.ts`).
   - `apps/mobile/lib/i18n.ts` `chatsWord`, `waitingSentText` and `agentsWord` use `count <= 10`, which is wrong from 101 up: 103 takes the singular instead of the CLDR "few" form. I verified this at batch-14.
   - This is a real Arabic-first defect (section 17). It is W-MOBILE's area.

Dropped after checking: the SSRF-safe `public_http.py` (no maintained async library pins the IP while keeping SNI), the indicators (small; TA libraries pull in C or pandas), the rate limiter (deliberately shared password bucket), retry/backoff (a domain policy), mobile markdown (deliberately strict), and websocket reconnect (the libraries are unmaintained).

## 7. A security finding along the way (not a library question)

**DNS rebinding in `web_fetch`**: `lonora_tools/search.py` `fetch` runs `validate_public_url(url)` and then lets `httpx.AsyncClient` resolve the hostname again. A name that answers public on the first lookup and private on the second reaches an internal address.
- `public_get` (`lonora_security/public_http.py`) already pins the validated IP, and `web_fetch` should use it.
- The same unpinned pattern is in `lonora_tools/browser.py:45` and `adapters/channels/webhook.py:16`.
- `lonora_security/network.py` does not refuse multicast, while `public_http.py` does.

The research tools were my area in #101, so I can take this one-function fix (`web_fetch` onto `public_get`, with a rebinding test) when the PR freeze lifts, or hand it to its owner.
