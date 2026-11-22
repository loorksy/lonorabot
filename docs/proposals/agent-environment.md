# Lonora Agent with Claude Code's philosophy — gap analysis and proposals

**Status: Proposed.** The owner asked that the Lonora agent work like Claude Code: connect to anything and do anything.
This document compares what exists, names the gaps and proposes changes. VISION P4 still holds: Claude Code and the
Agent SDK are never Lonora's engine. What is adopted is the philosophy: **a few general primitives on a real computer,
composed by the model**, which is VISION P3 ("build an environment, not features").

---

## 1. Claude Code's primitives against Lonora's tools (126 registered in `packages/tools/src/lonora_tools/`)

| Claude Code primitive | Lonora today | Status |
|---|---|---|
| Shell, foreground and background | `workspace_run`, `workspace_processes`, `workspace_stop`; 10-minute foreground limit, background processes unlimited, the owner sees and stops them ("What is running") | Equal |
| Read and write files | `workspace_file_read`, `workspace_file_write` | Equal |
| Exact in-place edit | None; an agent rewrites the file or uses `sed` | **Gap G1** |
| Find files, search contents | Through the shell (`rg`, `find`) | Enough |
| Web search and fetch | `web_search`, `web_fetch`, `web_browse` (self-hosted SearXNG and a headless browser) | Equal |
| Subagents | `subagent_spawn`, `subagent_inspect` (`LONORA_MAXIMUM_SUBAGENTS`, default 4) | Equal |
| Task tracking | `task_start`, `task_step_update`, `task_wait`, `task_inspect`, `task_control` (durable) | Ahead (durable) |
| Ask the user | `wait_for_input`, `owner_action_propose`, `owner_call_request` | Equal |
| Skills | `skills_list`, `skill_view`, `skill_save`, `skill_package_*`, `skill_repository_inspect`, versions and restore | Ahead (versioned) |
| MCP | `mcp_connections`, `mcp_tools`, `mcp_execute`, `mcp_trust` (remote, OAuth, owner trust) | **Gap G2**: tools are called through a generic executor, not as first-class tools; stdio servers are workspace processes only |
| Deferred tool discovery | The registry's stable `tool_call` bridge (Hermes-style, `registry.py`) | Equal |
| Memory | `memory_read`/`write`, knowledge notes, owner profile | Ahead |
| Scheduling | `routine_*`, `watch_*` | Ahead (Claude Code has none built in) |
| Secrets | Generic Secret card, injection as `NAME` and `/run/secrets/NAME`, redaction of every returned byte | Ahead |
| Permission prompts | None for the environment (the agent is the owner's delegate); money follows Full/Ask (§4) | Lonora is more autonomous by design |
| Hooks | None; routines, watches and owner methods cover automation | Not proposed (P3) |
| Network reach | TLS/HTTP/SSH by host name; bare IPs and other client-first protocols refused (`packages/workspace/src/lonora_workspace/relay.py`) | **Gap G3** |
| Scripts calling the app | `lonora` workspace CLI: read commands, `wake`, `notify` | **Gap G4**: the order commands of VISION §7.3 are not built |

**Conclusion.** Lonora already is a Claude-Code-style agent with a computer, plus trading, memory, scheduling and
secrets. Four gaps stop it from being "anything":

---

## 2. Proposals

### G1 — `workspace_file_edit`
Exact string replacement (match must be unique unless `replace_all`), several edits applied atomically, a unified diff
returned, the same redaction of returned bytes, the same Unix-user ownership. Rationale: long files edited precisely
without rewriting them; fewer tokens; fewer mistakes.

### G2 — MCP tools as first-class tools
- Tools of a trusted remote MCP server join the registry as named tools with their own schemas, discoverable through the
  `tool_call` bridge, instead of only through `mcp_execute`. Trust tiers, receipts and the financial-tool classifier of
  `docs/mcp-boundary.md` are unchanged (money still moves only through the door).
- **Local (stdio) MCP servers:** a supervised MCP host in the workspace starts a server under the requesting agent's
  Unix user and exposes its tools through the same bridge after the owner's trust message. The server never runs as the
  Gateway user (the current rule) and never receives broker-destination secrets.
- Plugin bundles (skills + MCP servers installed together) and a skills catalogue installable from chat, as in nanobot
  (`nanobot/agent/plugins.py`, `nanobot/webui/skills_marketplace.py`), are the second step (cloud decision D35).

### G3 — Reaching any server
Today the relay refuses bare IP addresses and client-first protocols other than TLS, HTTP and SSH. That covers every
HTTPS/WebSocket API, but not, for example, a database or a VPS addressed by IP. Proposal (decision A1): the owner may
allow a **specific destination** (`host:port` or `IP:port`) by a typed chat message, the way `trust_source` works today
(VISION §10.3 table); the relay then passes that destination with any protocol. Never allowed, whatever the owner says:
private and link-local ranges (cloud metadata), Lonora's own services, MetaApi, door venues' trading hosts, and in
Lonora Cloud the cloud domain. Rationale: "any server" for the owner's real needs without turning every workspace into
an open tunnel (VISION §7.2.3 stays the guarantee against MetaApi; the relay is defence in depth).

### G4 — Complete the workspace CLI
Build `lonora trade|close|modify|cancel` exactly as VISION §7.3.2–7.3.6 specify (execution door, `--key` idempotency,
exit codes 0/10/20/30/77), in `packages/cli/lonora` and `apps/api/src/lonora_api/cli/app.py`. This is VISION phase 4's
"done when". It lets the programs agents leave running in the workspace (watchers, webhook listeners, schedulers)
read and trade the MT5 accounts through the door, which the workspace otherwise cannot reach (VISION §7.1.4, §7.2.3).

### G5 — Coding and other agents as workspace tools
VISION §12.2 already lets an agent install and run any command-line tool with API keys the owner provided. That
includes coding agents (for example Claude Code's CLI) used as a tool for a coding task inside the workspace. Rules:
API keys only, never a subscription login (§12.2); the tool runs as the agent's Unix user like any command; it is never
Lonora's engine (P4). Proposal: a help-centre recipe and a skill that delegates a coding task to such a CLI and reviews
its result.

---

## 3. What stays closed by design

These are the mandate's guarantees, not missing features:
- the invisible safety core (VISION §6) and the execution door for money;
- broker and door-venue keys never in the workspace (§7.2.3); MetaApi and door venues unreachable from it (§7.1.4);
- financial MCP tools never trusted (`docs/mcp-boundary.md`);
- secrets redacted from everything returning to the model, chat, logs and memory (§7.2.6);
- one engine (P4).

---

## 4. Decisions for the owner

| ID | Decision | Recommendation |
|---|---|---|
| A1 | Owner-allowed destinations for any protocol (G3) | Yes, per destination by typed message, with the never-allowed list |
| A2 | First-class MCP tools and stdio MCP host (G2) | Yes, after G4 |
| A3 | `workspace_file_edit` (G1) | Yes |
| A4 | Coding-agent recipe and skill (G5) | Yes |
| A5 | Order of work | G4 → G1 → G2 → G3 → G5 |
