# External integration authority

Owner-saved MCP endpoints remain in the existing connection directory. Their
advertisements and `readOnlyHint` annotations are untrusted metadata. Saving or
enabling a connection does not authorize its tools. External finance remains
unsupported: broker mutations use Lonora's existing typed trading path.

Only an operator-reviewed `McpToolDeclaration` can authorize an HTTP read operation.
The actual API/Gateway setting `LONORA_MCP_DECLARATIONS` is a JSON array, empty by
default and limited to 128 unique owner/connection/tool identities. It is deployment
configuration, not an owner resource field, remote manifest, chat instruction or
Agent-editable setting. Each immutable declaration binds:

- Exact owner and saved connection ID.
- Canonical HTTPS endpoint SHA-256, including path and query.
- Exact advertised tool name and canonical input-schema SHA-256.
- Effect `read_only` and credential scope `integration`.

Review endpoint ownership, the remote service's actual behavior, accepted inputs
and the dedicated credential before declaring a tool. A declaration is explicit
trust in the operator-reviewed service; schema validation cannot prove what a
remote server does. Never declare a generic trade executor, shell, credential
exporter or permission manager as a harmless reader.

`lonora_adapters.mcp.policy.endpoint_sha256` fingerprints an HTTPS resource,
normalizing origin spelling, default port and empty path. It rejects credentials,
fragments and unsupported ports. `schema_sha256` hashes UTF-8 canonical JSON with
sorted keys, compact separators and no NaN. Generate these hashes from the
reviewed endpoint/schema locally; never include credentials in URLs or configuration.
Schema or endpoint drift requires a new operator review, not automatic acceptance.

Execution checks owner, enabled configuration, dedicated credential purpose and
the endpoint/name declaration before decryption or connection initialization.
It then discovers the actual tool, matches its schema digest and validates input
using JSON Schema 2020-12. References are currently unsupported, preventing network
resolution and recursive schemas. Schema depth/size and argument size are bounded.
Changed configuration during discovery blocks the call. Discovery reports
`execution_allowed` separately from advertisements and cannot grant permission.

Both resource save and runtime use reject broker/Agent-purpose credential refs.
Credentials stay server-side. Owner-supplied stdio commands are disabled before
discovery or execution: environment filtering alone cannot isolate a process
running as the Gateway user. Existing records remain listable. A future stdio
implementation needs a real isolated transport with reviewed dependencies and
explicit permissions; the analytical workspace is not an unrestricted substitute.

The HTTP path retains public-network validation, TLS and disabled redirects,
bounds response bytes and whole-request time, rejects compressed responses before
decompression, validates JSON-RPC IDs/results and
bounded paginated discovery, and closes initialized resources on failure. Remote
errors and `isError` are failures with stable secret-free codes. Protocol messages,
submitted values and remote error text are never interpolated into exceptions.
Timeouts do not trigger a blind resend. `mcp_execute` retains its existing
non-read-only runtime classification; this change does not expand subagent
authority merely because a reviewed remote operation is a reader.

Tests use scripted transports and disposable PostgreSQL. They prove policy and
failure boundaries, not the behavior or availability of an unconfigured third
party. No production integration is enabled or declared by these tests.
