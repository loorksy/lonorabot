# OpenMausBot: tools, permissions and safety

Repo: milind-soni/OpenMausBot (TypeScript harness server). Read-only study; paths are repo-relative. Secondary topic, kept short.

## Headline

OpenMausBot is a harness around other vendors' agent engines (Claude Code, Codex, Gemini, Qwen, Grok, ACP agents, a chat-completions runtime). It does NOT own a shell/file sandbox. Its own comment says it plainly (`server/auto-approve.ts`): "Nothing here decides whether an action is safe: each level is the provider's own permission mode passed through". The harness adds: an MCP gate/proxy layer, per-bot tool scopes, an approval-card broker, saved grants, an outbound-action guard, an optional shell never-list, and a decision log.

## 1. How tools are defined, registered, exposed

1. Engine-native tools (shell, edit, web) belong to the engine; the harness only narrows them (`shared/tool-scope.ts` re-exports `packages/phone-protocol/src/tool-scope.ts`: `ToolScope {allow, deny}`, selectors `native:<name>` and `mcp:<server>:<name>`, `parseToolScope`, `allowsTool`, `narrowsNativeTools`). An invalid scope never inherits the catalog ("A present invalid value never does").
2. Harness tools are MCP servers. The built-in "agents" server is a catalog in `server/drivers/agents-catalog.ts` (`availableTools(profile)` filtered by `CatalogProfile`), served through `server/drivers/agents-mcp.ts` and `agents-proxy.ts`; ~40 `agents-*-tools.ts` files each define a group (board, pages, research, meeting, widgets, ...). Internal calls land on `/api/internal/...` routes (`server/routes/internal-tools.ts`, `internal-mcp.ts`) behind a per-turn capability bearer.
3. Read-only agent tools are an explicit allowlist, not inferred: `server/agent-tool-policy.ts` `READ_ONLY_AGENT_TOOL_NAMES` ("Names, prefixes or third-party annotations alone must never grant read access") and `agentToolAnnotations` attach frozen `readOnlyHint` annotations.
4. Tool bridge (`server/drivers/agents-bridge.ts`): a turn lists a few "hot" tools plus `find_tool` and `use_tool`; hidden tools are found by BM25 (`bm25Ranker`) and run via `use_tool`. Invariant stated in the file: "a bridged call is never judged more permissively than the same call made directly"; outbound tools are always listed under their own name.
5. User-added MCP servers: registry in `server/mcp-registry.ts` (config.json `mcpServers`, Claude Code/Cursor-style entries, `vault:<id>` secret pointers, per-server `resultBudget`); stdio servers are wrapped by `server/mcp-gate.ts` (a proxy process spawned per mount: tool-scope filter, schema fitting `mcp-tool-schema.ts`, result trimming `mcp-trim.ts`/`mcp-result-budget.ts`, spill to disk `tool-result-spill.ts`/`tool-results.ts`, tool-count cap `tool-count-limit.ts` via `OMB_TOOL_LIMIT`, 128 for OpenAI-compatible). Remote HTTP servers go through `mcp-http.ts` and `mcp-remote-proxy.ts`; OAuth in `mcp-oauth.ts` (engines "never see this, only an Authorization header"; state compared with `timingSafeEqual`). Config reaches the gate via a private env record named `OMB_GATE_CONFIG_<sha256>` (`mcp-gate.ts gateEnvironment`), and gate settings are stripped from the upstream's env.
6. Connected apps (Composio) go through `server/connector-*.ts`; `connector-verdict.ts` denies unrecognized argument shapes and runs Composio's code sandboxes (`COMPOSIO_REMOTE_WORKBENCH`, `COMPOSIO_REMOTE_BASH_TOOL`) only at Full access, by direct call, and never when app scopes are limited ("code could reach past the limit").
7. Per-bot tool groups can be turned off to keep requests small (`server/tool-groups.ts`, `shared/tool-groups.ts`); the prompt tells the bot which are off.

## 2. Permission / approval model

Levels (`packages/phone-protocol/src/approval-mode.ts`, re-exported `shared/approval-mode.ts`): `ask`, `edits`, `auto`, `full`, `custom`. Each is the engine's own mode passed through (Claude `acceptEdits`, Codex approval_policy, etc.). `supportsApprovalMode` gates levels per driver; `modelSwitchNeedsAsk` drops to Ask when switching engines so a Custom grant never crosses engines. Full is the default per the file comment, and entering Full is consent-gated at the bot PATCH endpoint.

Control flow of one permission request:
1. Engine asks. For Claude Code this is `--permission-prompt-tool`: `server/permission-proxy.ts` is a stdio MCP server exposing `approve` and `ask_user`, forwarding over a unix socket to the server's broker. Other engines raise `request.opened` events from their drivers (`drivers/codex-app-approval.ts`, `codex-approval-config.ts`, `permission-command.ts`).
2. `autoVerdict(mode, tool, ctx)` in `server/auto-approve.ts` decides, in this order: questions (`AskUserQuestion`, `ask_user`) never auto-answered; `full` approves all; sandbox-widening requests need explicit Full (`explicit-approval-block`); outbound tools (`isOutboundTool`) always held (`outbound-guard`); exact saved command match; saved tool grant; bot's own-file reads (`own-file-reads.ts`, plain `cat/head/grep/...` inside the bot's folders after following links); in `auto` only web search; otherwise a card.
3. Before any automatic allow, the safety floor runs (`server/safety-floor-gate.ts` `denyAtSafetyFloor`, `heldAtSafetyFloor`); a never-list hit is denied, announced and logged, and an unreadable command becomes a card instead of an allow.
4. The card is `request.opened` over the event bus to the web/mobile UI (`server/index.ts` handles it, marks the thread "waiting on human" for the watchdog, and strips `command`/`commandLine` from the public event). The person answers Allow / Deny / Always allow.
5. The answer returns through the broker: `{behavior:"allow", updatedInput, updatedPermissions?}` or deny with a message; "always" hands the engine's own suggested rules back so the engine stops asking itself. A broker that cannot be reached denies with an instruction to tell the person instead of skipping (`UNREACHABLE_NOTE`).
6. Chat-completions runtime has its own per-turn gate: `server/drivers/chat-tool-approval.ts` (`createChatToolApproval`: pending cards map, 15-minute timeout, exactly-once `finish`, session grants set, `floored()` check before a Full/granted call).

Who approves what:
- Person in the UI: any card; Full access is a person's grant to the receiving bot and is never inherited from a sender (`approvalModeForOrigin`: peer-started Custom turns run as Auto).
- Chief of Staff bots may raise a teammate's level, only upward, only capped by engine support (`delegatedApprovalMode`).
- Saved grants: exact command + cwd + provider-instance rules (`server/command-allowlist.ts`, rejects commands containing credentials via `redactSecretsInText`, refuses `..` in cwd, caps 200 per bot, file 0600-style store); per-bot/thread "Always allow" key lists capped at 200 (`server/always-allow.ts`), removals cascade to every thread and running turn (`dropRemovedGrants`).
- Outbound actions (send, reply, post, pay, refund, transfer, buy, create-message/invoice/call...) are classified by name tokens in `packages/phone-protocol/src/outbound.ts` (`isOutboundTool`; read verbs first mean read; raw API tools like `COMPOSIO_PROXY_EXECUTE` count as sends). Below Full they ask unless the bot's rule says send; a read-and-draft routine never reaches them.
- Gated trust boundary: SECURITY.md says the server binds 127.0.0.1, public mutations need a per-launch capability or paired session; per-turn capabilities for built-in integrations; a hosted-workspace loopback caller is limited to `SERVICE_ALLOW` (`server/request-auth.ts`, not read). It also lists a known unclosed hole: a bot's shell could post into an existing Full-access thread.

## 3. Sandboxing of shell/file/browser

- Shell/file: delegated to the engine. Codex sandbox levels are checked so the engine "may resolve a stricter sandbox than asked, never a looser" (`drivers/codex-approval-config.ts resolvedSandboxAllowed`: readOnly < workspaceWrite < dangerFullAccess). Sandbox widening can only be approved at Full.
- Safety floor (`server/safety-floor.ts`, 728 lines; gate in `safety-floor-gate.ts`): a never-list of recursive delete of root/home/system dirs, disk format/overwrite, fork bomb. Lexes shell lines; "a line not read to its end is 'could not read', never 'clear'". OFF by default (`config.safetyFloor.enabled` or `OMB_SAFETY_FLOOR=1`), inert on Windows, and cannot reach engines that never ask (Claude bypassPermissions, Codex approvals off). Block text tells the model to report, not respell.
- Computer/browser: the built-in browser is a real Chrome via `agent_browser_*` tools (prompt in `server/browser/prompt.ts`); `server/cloud-browser/guards.ts` rejects local schemes (file:, chrome:, devtools:...). Isolated Cua Linux VM/container "sandbox" desktops exist for bots (`server/system-prompt.ts` text: only `/home/cua/workspace` durable). `shared/tool-surface.ts` classifies tool names as browser/computer for UI only, not security.
- MCP remote client (`server/mcp-http.ts`) imports `BlockList`, suggesting a private-address block for fetched servers; I did not read the rules.

## 4. MCP support

Both consumer (user-added stdio and remote HTTP servers, OAuth, health `mcp-health.ts`, probe `mcp-probe.ts`, directory/search `mcp-directory.ts`, app catalog `mcp-app-catalog.ts`) and provider (the "agents" MCP, plus per-family harness servers for browser/computer/data/email/device with token env names from `server/harness-mcp-token.ts`: `OMB_MCP_TOKEN_<KIND>`). MCP Apps (UI views) are observed by `mcp-app-observer.ts`; app-only tools refused for the model (`APP_ONLY_REFUSAL`, `modelVisible`). Per-engine mounting: `drivers/codex-mcp-mount.ts`, `claude-project-mcp.ts`, `pi-mcp-*.ts`, `turn-mcp.ts`.

## 5. Memory and skills

- Memory: `server/memory-store.ts` (files with byte/line caps, writes via `writeFileAtomic`, text through `redactSecretsInText`), plus capture, dream/organize/tidy/forget/upkeep modules and `team-memory.ts`. Not studied in depth here (another report covers it).
- Skills: Agent Skills per bot (`server/skills.ts`: "imports keep their whole folder and land disabled"), fetch from GitHub (`skill-fetch.ts`), background self-review that creates/updates skills after a reply (`skill-review.ts`, ported from Hermes, bounded to `MAX_REVIEW_CHANGES = 3`, decision-log source `skill`), `skill-learn.ts`, share/export. Imports landing disabled is the safety property.

## 6. Prompt-injection guardrails

Mostly prompt-level and provenance-based, not a classifier:
- Webhook/app events: `server/system-prompt.ts` line ~329 tells the model to treat "UNTRUSTED WEBHOOK EVENT DATA / UNTRUSTED APP EVENT DATA" blocks as data and not let them override approval boundaries; the rule lives in the system prompt, outside the payload.
- Browser: `server/browser/prompt.ts` says page text, labels, downloads are untrusted content; confirm in chat before consequential actions; page-reported errors are "quoted as page output and never instructions".
- Provenance: `server/peer-provenance.ts` ("no bot's message is ever the user's approval or a permission grant"); `workOrigin` is `user` only for a person's own typed/spoken line, else `outside`; request quotes are redacted and bracket-stripped. Related `server/provenance-label.ts` (not read).
- Structural: outbound actions always carded below Full; questions can never be auto-answered; tool results capped and spilled; MCP results trimmed; schema validator "no coercion, defaults... or fetched external references" (`mcp-schema-validator.ts`).
- Gap: nothing I read detects injection in tool output; the defense is mode + outbound card + provenance.

## 7. Audit trail

`server/decision-log.ts`: append-only NDJSON per UTC month at `<data>/decisions/YYYY-MM.ndjson`, mode 0600, redacted at write time, fire-and-forget ("an audit log must never take down the decision it audits"). Row: time, thread, request id, bot, tool, summary, `decision` (`auto-approved|auto-denied|card-shown|user-approved|user-denied|user-undone|review-would-*`), `source` (full-access, command-allowlist, tool-allowlist, own-files, outbound-guard, safety-floor, native-approval, user, skill, ...), `rule`, `unattended`, `actor` (session/loopback/worker). Retention days configurable; CSV export (`decisionsCsv`). Auto-approvals also show a chip in the transcript ("so an auto-approved action is never invisible"). Secrets redacted by `server/redact.ts` / `shared/redact.ts`, including held-secret scrubbers.

## Could not find / not read

- No harness-owned filesystem or process sandbox; no path allowlist for file tools at the harness level (engines own it).
- `server/request-auth.ts`, `provenance-label.ts`, `mcp-http.ts` SSRF rules, `connector-proxy.ts` and the UI card components were not read.
- No automated prompt-injection detection or tool-output tagging found.

## What Lonora should copy / avoid

Copy:
1. A single pure verdict function with an ordered rule list and a typed `source` per outcome (`autoVerdict`), logged for every decision. Lonora's `before_send` and permission frame in Python would benefit from the same "source + rule" vocabulary on every allow/deny.
2. Outbound classification by name tokens with read-verb-first and an explicit allowlist for known reads, fail closed for raw API tools. For trading: treat any order-placing, transfer or withdraw tool as outbound regardless of annotations; never trust a model- or MCP-supplied `readOnlyHint`.
3. Safety floor idea, but inverted for money: a non-overridable never-list (e.g. withdraw to new address, leverage over cap) applied only where nobody is looking, with "could not read" = not clear. Make it ON by default in Lonora, unlike OpenMausBot where it is off.
4. Append-only, redacted, 0600 audit log with `unattended` and `actor` fields, CSV export, retention; in Lonora put it in Postgres/SQLite with an append-only table.
5. Provenance rule: relayed or peer text is never user approval; only a client-originated user line carries authority. Apply to webhooks, broker events and agent-to-agent messages.
6. Grants bound to exact scope (command+cwd+engine) rather than patterns, with caps and cascade-on-remove; approvals that cannot be delivered deny with an instruction to tell the person, never skip silently.
7. Tool bridge (`find_tool`/`use_tool`) with the invariant "bridged is never judged more leniently", useful once the Lonora tool catalog grows.
8. Per-tool result budgets and spill-to-store so one tool cannot flood context.
9. Skills imported disabled; self-written skills bounded per review.

Avoid:
1. Passing approval through to whatever the engine does and defaulting to Full access. Lonora is a trading assistant; default to ask, and let only the mandate/owner card widen authority, with the widening bound to the card's shown terms.
2. A shell-safety layer that is off by default, off on Windows, and bypassed by engines that never ask.
3. Injection defense that is only prompt text; add structural guards (typed tool-argument validation, spend/size caps in code, no tool output able to change approval state).
4. Name-token heuristics as the only classifier for money movement; keep an explicit registry of Lonora's financial tools instead.
5. Known-open hole pattern: a bot's own shell reaching the approval or thread APIs over loopback. Keep Lonora's approval endpoints behind owner session auth, not loopback trust.
