# Rakazo study: tool surface and self-extension

Repo: `/home/user/elie222/rakazo` at commit `cd7e20e5da754d8d8deaf2780671ed34a38e2241`. All paths are relative to that repo root. "(implemented)" = read in code at the cited line. "(stated)" = only read in docs. Tool descriptions are quoted from the model-facing schema, which is the same text the model reads.

## 0. Shape of the surface in one paragraph

All built-in tools are declared as plain JSON-schema objects in one array, `builtinAgentTools`, in `packages/adapters/src/builtin-tools.ts:248-1915` (88 entries; counted by the `name:` lines in that range), plus 3 agent-to-agent tools in `agentConnectionTools` (`packages/adapters/src/builtin-tools.ts:1918-1964`). Execution is a name-to-handler map built from per-family handler files (`packages/adapters/src/run-tools.ts:41-59`); any name not in the map goes to the cloud-agent handler if it starts with `cloud_agent_`, otherwise to the connector (MCP / app integration) handler (`packages/adapters/src/run-tools.ts:61-65`). Calls that reach `applyTool` pass through one dispatcher that applies refusals, argument resolution, an approval gate and an audit record (`packages/adapters/src/run-tools.ts:95-193`); a few names are answered earlier inside the runtime (`ask_user` at `packages/adapters/src/pi-runtime-tools.ts:551-563`, an unknown `use_tool` name at `:105-113`), so "every call" would be too strong. Which of the 88 a given run is offered is decided per run by a filter chain (`packages/adapters/src/run-tool-selection.ts:98-217`), and which of the offered ones are shown to the model with full schemas is decided by a second split, "core" vs "deferred" (`packages/adapters/src/builtin-tool-bridge.ts:21-56`, `:85-92`).

## 1. Full tool list by group

"Def" = line of the tool definition in `packages/adapters/src/builtin-tools.ts`. "Handler" = where it executes. A tool marked **core** is listed to the model with its schema whenever the run is offered it at all (section 2.4 filters first); **deferred** is reachable only through `find_tool` / `use_tool` (section 2).

### 1.1 Shell / exec

| Tool | Purpose | Def | Handler / limits |
|---|---|---|---|
| `shell` (core) | Run a command in the bot's own computer | `:459` | `packages/adapters/src/run-tools-computer.ts:373`. Timeout default 5 min, env `SANDBOX_COMMAND_TIMEOUT_MS`, hard max 60 min (`packages/core/src/sandbox-command.ts:1-9`). Output published to the UI is the last 16,000 chars (`packages/contracts/src/events.ts:412`, used at `packages/adapters/src/run-tools-computer.ts:416`). A command that goes quiet is returned to the model while still running: after 1 s of silence if the output looks like a device-code sign-in prompt, otherwise after 10 s (`packages/adapters/src/shell-command-stream.ts:14`, `:20`), with the notice "Still running. Tell the user any one-time code or sign-in URL in the output." (`packages/adapters/src/shell-command-stream.ts:44-45`). |
| `user_computer_shell` (core, only if the user's desktop is connected) | Run a command on the user's own machine | `:472` | `packages/adapters/src/run-tools.ts:51`; offered only when `userComputer` is true (`packages/adapters/src/run-tool-selection.ts:190`). Same timeout function (`packages/adapters/src/run-tools-user-computer.ts:177`). |

The tool description itself tells the model how to survive the timeout: "A command is stopped after a few minutes, so on Linux or macOS start longer work ... as its own statement `nohup <command> < /dev/null > <log> 2>&1 &`" (`packages/adapters/src/builtin-tools.ts:461`).

### 1.2 Files

| Tool | Purpose | Def | Handler / limits |
|---|---|---|---|
| `list_files` (core) | List the bot's home | `:409` | `packages/adapters/src/run-tools-files.ts:83` |
| `read_file` (core) | Read UTF-8 text, paged by line `offset`/`limit` | `:418` | `packages/adapters/src/run-tools-files.ts:89`; file size cap for model reads 250,000 bytes (`packages/adapters/src/workspace-file-tools.ts:31`) |
| `write_file` (core) | Write a UTF-8 file | `:432` | `packages/adapters/src/run-tools-files.ts:95` |
| `attach_file` (core) | Attach a workspace file to the chat; same `name` = new version of the same artifact | `:445` | `packages/adapters/src/run-tools-files.ts:130`; attachment cap 10 MB by default; the comments there say the per-message limit is configurable up to a hard ceiling (`packages/contracts/src/attachments.ts:1-4`; ceiling value not read) |
| `open_path` (deferred) | Open a file/URL in its GUI app | `:541` | `packages/adapters/src/run-tools-computer.ts:525` |

### 1.3 Code

There is no dedicated "run code" tool. Code runs through `shell` (e.g. `python3 -c`, `uv run --with <package>`), as the system prompt says (`packages/adapters/src/run-instructions.ts:139`, `:144`). Delegated coding goes to cloud coding agents (1.15).

### 1.4 Browser (page-level, element refs)

| Tool | Purpose | Def | Limits |
|---|---|---|---|
| `browser_navigate` (core) | Open a URL in the browser on the bot's computer | `:332` | Handler `pageBrowserTool` (`packages/adapters/src/run-tools.ts:58`). Refused if the computer has no page browser (`packages/adapters/src/run-tools.ts:158-162`). |
| `browser_snapshot` (core) | Accessibility-style snapshot with refs `e1, e2…`; optional `query` (max 200 chars) | `:344` | `packages/adapters/src/browser-tools.ts:30` |
| `browser_act` (core) | Act on refs. Kinds: click, fill, type, upload, fill_secret, fill_card, fill_pay_token, fill_code | `:356` | Kinds at `packages/adapters/src/browser-tools.ts:20-29`; max 24 actions per call (`packages/adapters/src/tool-loop.ts:49`); max 10 upload files (`packages/adapter-kit/src/types.ts:1211`) |

### 1.5 Computer / desktop GUI

| Tool | Purpose | Def | Limits |
|---|---|---|---|
| `computer_observe` (core) | Screenshot of the bot's desktop | `:274` | `packages/adapters/src/run-tools-computer.ts:326`; refused when the model cannot take images (`packages/adapters/src/run-tools.ts:163-165`) |
| `computer_act` (core) | Up to 24 ordered actions (click, move, down, up, type, key, scroll, wait, focus) | `:280` | 24-action cap with an instructive error (`packages/adapters/src/computer-tools.ts:32-34`); loop guard after 3 consecutive unchanged visual actions (`packages/adapters/src/computer-tools.ts:10`) |
| `launch_app` (deferred) | Launch/raise a GUI app | `:551` | `packages/adapters/src/run-tools-computer.ts:562` |
| `request_takeover` (core) | Ask the human to take the screen (CAPTCHA, passkey, payment) | `:564` | `packages/adapters/src/run-tools-messaging.ts:234` |
| `user_computer_observe`, `user_computer_act` (deferred) | Look at / act in one app on the user's own machine via accessibility rows | `:485`, `:498` | `packages/adapters/src/run-tools.ts:52-53`; 24 actions max (`packages/adapters/src/host-screen.ts:4`) |
| `enter_computer_mode` / `leave_computer_mode` | Only when the run request carries a separate `computerModel` (`packages/adapters/src/pi-runtime.ts:276`, `:299`): hand a GUI goal to that model inside the same run | not in builtin-tools.ts | `packages/adapters/src/pi-runtime-computer-mode.ts:97-130`. Outside computer mode, the 10 screen tools in `COMPUTER_MODE_TOOLS` throw "Enter top-level computer mode before using computer tools" (`packages/adapters/src/pi-runtime-computer-mode.ts:13-24`, `packages/adapters/src/pi-runtime-tools.ts:497-502`). |

### 1.6 Web search / fetch

| Tool | Purpose | Def | Limits |
|---|---|---|---|
| `web_search` (core) | Titles, URLs, snippets | `:784` | Default 5 results, max 10 (`packages/adapters/src/web-limits.ts:1-2`). Handler `packages/adapters/src/run-tools-integrations.ts:153`. |
| `web_fetch` (core) | Readable text of a public page, no JavaScript | `:801` | Default 8,000 chars, max 50,000, min 100; `offset` up to 5 MiB so a cut page can be continued (`packages/adapters/src/web-limits.ts:3-7`). The truncation marker tells the model the next offset: "[Content truncated; continue with offset N]" (`packages/adapters/src/web-limits.ts:29-45`). |

Provider: default is "keyless-http", which scrapes DuckDuckGo's HTML form (`packages/adapters/src/keyless-http-web.ts:25`, `:43-45`; selection in `packages/adapters/src/web-provider-factory.ts:12-13`). Alternatives `parallel` and `keenable` via `WEB_PROVIDER` (`packages/adapters/src/web-provider-factory.ts:24-26`).

SSRF rules (implemented, `packages/adapters/src/web-ssrf.ts`):
- only `http:`/`https:`; no credentials in the URL; optional port allowlist (`:64-73`);
- hostname blocked if internal name, cloud-metadata host, or a literal non-public IP (`:96-100`); DNS results must all be public (`:87-92`);
- the check is repeated at connect time by a custom dispatcher, so a DNS answer that changes between check and connect is still refused (`:187-190`);
- redirects are followed manually, each hop re-validated, max 5 (`:18`, `:238`, `:243`, `:255-259`);
- one 15 s deadline for the whole chain including body read (`:16`, `:191-192`); 5 MiB default body cap (`:17`); search responses capped at 1 MiB (`packages/adapters/src/keyless-http-web.ts:96`).

### 1.7 Messaging the user, other people, email, calls

| Tool | Purpose | Def | Limits |
|---|---|---|---|
| `ask_user` (core) | One multiple-choice question, 2-4 tappable options | `:585` | question ≤240 chars, detail ≤4,000, option ≤80 (`:591-597`); handled inside the runtime (`packages/adapters/src/pi-runtime-tools.ts:551-561`) |
| `message_user` (core) | Short mid-turn progress line | `:605` | 500 chars default, silently cut; env `RAKAZO_MESSAGE_USER_MAX_CHARS` (`packages/adapters/src/user-progress.ts:8`, `:77-82`). Not offered to background runs (`packages/adapters/src/run-tool-selection.ts:177-185`). |
| `call_user` (deferred) | Ring the user for a voice call | `:1451` | only if phone calls enabled, not in group/channel/background (`packages/adapters/src/run-tool-selection.ts:194-199`) |
| `end_call` (core) | Hang up a live call | `:1432` | only on a voice-call turn (`packages/adapters/src/run-tool-selection.ts:186`) |
| `claim_email_address` (deferred) | Give the bot a permanent `name@` address | `:1058` | only in the owner's own chat when the server receives mail and no address exists (`packages/adapters/src/run-tool-selection.ts:140-144`, `:189`) |
| `send_email` (core) | Plain-text mail from the bot's own address | `:1074` | 10 recipients, 20,000 chars body, 50/day per bot, 200/day per owner (`packages/adapters/src/run-tools-email.ts:274-278`) |
| `read_email` (core) | List/read inbox; can wait up to 120 s for a matching mail (e.g. sign-up code) | `:1094` | `packages/adapters/src/run-tools-email.ts:13`; text paged at 8,000 chars (`:15`) |
| `delete_email` (deferred) | Delete received mail | `:1127` | 50 ids (`packages/adapters/src/run-tools-email.ts:19`) |
| `connect_agent`, `respond_agent_connection`, `message_agent` | Standing connection and messages to another person's agent | `:1920`, `:1936`, `:1948` | offered only for chat-linked bots with cross-space communication on (`packages/adapters/src/run-tool-selection.ts:84-96`) |

### 1.8 Scheduling / routines / task tracking

| Tool | Purpose | Def | Limits |
|---|---|---|---|
| `schedule_create` (core) | Reminder or recurring job; exactly one timing method (cron, every/unit, runAt, delayMinutes, delaySeconds, or `watch`) | `:1389`, schema `:211-220` | Max 50 active routines per bot (`packages/adapters/src/schedule-tools.ts:456`). `watch` polls files / a shell command / a read-only connected tool every 5-1440 min **without a model** and only runs the bot on change (`:159-183`). |
| `schedule_list` (core), `schedule_update`, `schedule_cancel` (deferred) | Manage routines | `:1395`, `:1400`, `:1421` | handlers start at `packages/adapters/src/run-tools-tasks.ts:209` (`schedule_create`) and `:250` (`schedule_cancel`); list/update between them not opened line by line |
| `task_catalog` (deferred) | Read-only inventory of real open tasks, routines, skills and exposed tools | `:1225` | description: "Call it before claiming a task or skill exists" (`:1227`) |
| `scratchpad_list/add/update/complete/remove` (deferred) | Open-work items that outlive a turn | `:1232-1289` | title ≤200, notes ≤4,000 (`packages/adapters/src/scratchpad-tools.ts:8-9`) |
| `board_tickets`, `ticket_get/create/update/comment` (deferred) | Ticket board | `:1300-1373` | only if ticket board enabled (`packages/adapters/src/run-tool-selection.ts:175-176`) |

The `schedule_create.prompt` description is worth reading in full; it explains to the model that "This prompt is all a future run knows" and that one-off decisions must be written as conditions (`packages/adapters/src/builtin-tools.ts:121-125`).

### 1.9 Memory and history

| Tool | Purpose | Def | Limits |
|---|---|---|---|
| `remember` (core) | One short fact per call into a per-bot note; edit by `old_text` | `:759` | whole memory holds 4 KB (`packages/contracts/src/domain.ts:842`) |
| `save_shared_memory` (deferred) | Replace a Space-wide document all bots read | `:771` | 4,000 chars (`packages/adapters/src/builtin-tools.ts:1967`) |
| `save_memory`, `recall_memory` (core), `forget_memory` (deferred) | Semantic memory; only when a memory provider is configured | `:1184`, `:1196`, `:1207` | comment at `:1180-1182`; recall limit 5 (`packages/adapters/src/history-compaction.ts:50`, passed at `packages/adapters/src/run-tools-memory.ts:175`) |
| `search_history` (core) | Literal keyword search of earlier messages, max 5 hits (description `:990`) | `:988` | up to 5 query variants (`:1001-1007`); offered only when history retrieval is enabled (`packages/adapters/src/run-tool-selection.ts:200-201`) |
| `read_history` (core) | Read around an earlier message | `:1139` | same gate (`packages/adapters/src/run-tool-selection.ts:200-201`) |

### 1.10 Pages

`save_page` (deferred) — save a dashboard/report as JSX source against a page kit; `{"help": true}` returns the kit guide; edits are find/replace applied all-or-nothing (`packages/adapters/src/builtin-tools.ts:702-722`). Max 50 edits per call (`packages/adapters/src/run-tools-pages.ts:14`). Handler `packages/adapters/src/run-tools-pages.ts:337`.

### 1.11 Secrets

| Tool | Purpose | Def |
|---|---|---|
| `request_secret` (core) | Show a masked card to collect a credential: API key bound to one HTTPS origin, website login (1-8 labelled fields; limit at `packages/contracts/src/bot-secrets.ts:276`, `:311`), shell "command variable", payment card, contact, or one-time code | `:626`, description `:46-50` |
| `generate_secret` (deferred) | Create and save a random password the model never sees | `:638` |
| `list_secrets` (deferred) | Names/destinations only, never values | `:644` |
| `secret_request` (deferred) | Authenticated HTTPS request; backend injects the credential only at its saved origin | `:650` |
| `forget_secret` (deferred) | Remove a credential | `:656` |

Limits (implemented): `secret_request` refuses any URL whose origin differs from the saved one (`packages/adapters/src/bot-secrets.ts:1009-1012`), 30 s deadline (`:1014`), 1 MB response (`:1056`), 20,000 chars returned (`:1068-1069`); 100 credentials per vault scope (`:604`, counted at `:606`; the doc words this as "Each user can save up to 100 credentials per bot", `docs/bot-secrets.md:35`, stated; how a vault scope maps to bot and user was not read). The doc gives the same 30 s / 1 MB / 20,000 numbers (`docs/bot-secrets.md:31`).

### 1.12 Purchases and paid services

| Tool | Purpose | Def | Limits |
|---|---|---|---|
| `request_purchase`, `purchase_status`, `paid_request` (deferred) | Buy via the user's wallet; the user approves every purchase in the wallet app | `:922`, `:951`, `:962` | offered only if the user connected a wallet (`packages/adapters/src/run-tool-selection.ts:50`, `:171`); `reason` must be ≥100 chars (`:939-943`) |
| `service_search`, `service_call` (core) | Find and call pay-per-call data services | `:824`, `:837` | only if the deployment configured paid services (`packages/adapters/src/run-tool-selection.ts:174`); ≤ USD 2 per call, 1.2x markup, result ≤50,000 chars (`packages/adapters/src/paid-service-tools.ts:20-24`) |

### 1.13 Media generation and plot

| Tool | Purpose | Def |
|---|---|---|
| `generate_image`, `generate_video` (deferred) | Prompt ≤4,000 chars; offered only if the deployment has a media model; not in background runs | `:250`, `:261`; gating `packages/adapters/src/run-tool-selection.ts:172-173`, `:183-184` |
| `render_plot` (deferred) | Observable Plot JSON spec to PNG; `{"charts": true}` lists runnable examples | `:662`; PNG rasterised with sharp, flattened on white (`packages/adapters/src/plot-tool.ts:6-13`) |

### 1.14 Fleet / other bots / subagents

| Tool | Purpose | Def |
|---|---|---|
| `run_subagent` (core) | Short helper inside the turn, or `background: true` for a separate helper run | `:1540`. Max 4 in parallel, no nesting (`packages/adapters/src/pi-runtime-subagent.ts:32`, `:53`). A background helper only gets 9 read-only tools (`packages/adapters/src/run-tool-selection.ts:71-81`). |
| `spawn_bot`, `archive_bot`, `create_space` (deferred) | Create/archive a full bot, propose a new space | `:1586`, `:1797`, `:1569` |
| `message_bot`, `handoff_to_bot` (deferred) | Async message / stage hand-off to another bot | `:1814`, `:1846`; ≤4 files (`packages/contracts/src/attachments.ts:3`, used as `maxItems` at `packages/adapters/src/builtin-tools.ts:1832`, `:1870`) |
| `list_fleet`, `create_group`, `update_group`, `organize_bot`, `set_child_instructions`, `set_child_bot_model`, `create_child_routine` (deferred) | Manage other bots | `:1692-1791`; offered only when the bot has `fleetManagement` and the owner started the run (`packages/adapters/src/run-tool-selection.ts:168-169`) |

### 1.15 Cloud coding agents

`cloud_agent_launch`, `cloud_agent_status`, `cloud_agent_reply`, `cloud_agent_cancel` (deferred) — `packages/adapters/src/builtin-tools.ts:857-911`. Dropped entirely when no provider is configured (`packages/adapters/src/cloud-agent-tools-select.ts:11-18`). Prompt ≤100,000 chars, ≤5 images, repository must be an HTTPS URL (`packages/adapters/src/cloud-agent-tools.ts:23-36`).

### 1.16 Integrations / MCP

| Tool | Purpose | Def |
|---|---|---|
| `connect_app` (core) | Post an inline "connect" card for an app from the connector catalog, then wait | `:574` |
| `add_mcp_server` (deferred) | Register a remote MCP server from details the user gave; posts an approval card | `:725` |
| connector tools (dynamic) | Tools from connected apps (Composio, Pipedream), MCP servers, OpenAPI/GraphQL "installed" sources | routed by `connectorTool` (`packages/adapters/src/run-tools-integrations.ts:35-80`) |
| `<prefix>_search_tools`, `<prefix>_load_tool`, `<prefix>_execute_tool` | Catalog wrappers that replace a source's tools when it has more than 20 | `packages/adapters/src/lazy-tool-catalog.ts:51-120` |

MCP response cap 16 MiB (`packages/adapters/src/mcp-response-limit.ts:4`); MCP discovery timeout 20 s (`packages/adapters/src/mcp-connector.ts:102`). Tool-result text reaching the model is clipped at 12,000 chars generally (`packages/adapters/src/pi-runtime-limits.ts:69-73`).

### 1.17 Skills

`skill_read` (core), `skill_create`, `skill_update`, `skill_delete` (deferred) — `packages/adapters/src/builtin-tools.ts:1472-1528`; handlers `packages/adapters/src/run-tools-tasks.ts:262-318`. Details in section 3.1.

### 1.18 Settings-from-chat, feedback

| Tool | Purpose | Def |
|---|---|---|
| `update_bot` (core) | Read (no fields) or change the bot's own name, description, instructions (paged with `instructions_offset`), avatar (`color`, `artifact_id`, `use_attached_image`), notifyOnFinish, dailyCheckIns, model, thinkingLevel, readAloud, voice; with `bot_id` it updates another bot's profile in the space instead | `:1620-1689` |
| `update_preferences` (core) | Read or change the user's timezone and marketing-email opt-in, nothing else | `:1879` |
| `feedback` (deferred) | Bug report to the server operators, only when the user asks | `:1898`; 5 per hour per user, description ≤2,000 chars (`packages/adapters/src/run-tools-feedback.ts:15`, `packages/contracts/src/builtin-tools.ts:20`) |

### 1.19 Cross-cutting guards on every call

- Per-bot disabled list: "This tool is disabled for this bot." (`packages/adapters/src/run-tools.ts:141-143`).
- Loop guard: same tool + same arguments failing 6 times in a row, or 25 near-identical calls (also the limit for an identical call that keeps succeeding), ends the run with a fixed text starting "I got stuck calling ..." (`packages/adapters/src/tool-loop.ts:7`, `:38`, `:39-42`; the text is used when the run is finalized at `packages/adapters/src/run-turn.ts:634-638`). Four consecutive over-limit action batches end it the same way (`packages/adapters/src/tool-loop.ts:45-47`).
- Optional per-turn tool-call fuse `MAX_TOOL_CALLS_PER_TURN`, unlimited by default (`packages/adapters/src/pi-runtime-tools.ts:65-71`).
- A run is marked "tainted" after any tool for which `toolResultTaintsRun(name)` is true (`packages/adapters/src/run-tools.ts:91`; which tools those are was not read, the function lives in `@rakazo/core`). A tainted run is then refused account-preference writes with "... blocked for the rest of this run because it read outside content", unless the owner already approved that change (`packages/adapters/src/run-tools-preferences.ts:33-41`).

## 2. Dynamic loading and discovery

There are two separate mechanisms, one for built-ins and one for connector tools.

### 2.1 Built-ins: `find_tool` / `use_tool`

- A fixed set of 34 names is "core" (`packages/adapters/src/builtin-tool-bridge.ts:21-56`). Every other built-in offered to the run is "deferred" (`:80-82`).
- If at least one tool is deferred, two bridge tools are appended to the listed set (`:85-92`).
- `find_tool` description: "Get the parameters of built-in tools not in your tool list, including ones your instructions name. Call this before use_tool. Pass names for exact tools or query to search." followed by the names of all deferred tools grouped by area, without schemas (`:115`). Areas: secrets, bots, tasks, skills, schedules, memory, media, cloud agents, purchases, email, other (`:60-78`, `:105`).
- `find_tool` takes up to 5 exact `names` or a `query`; a query returns the top 3 matches with full schemas (`:14`, `:118-120`, `:141-158`). Ranking is deterministic word-prefix matching: name weight 3, group 2, description 1, parameter names appended to the description (`packages/adapters/src/lazy-tool-catalog.ts:576-607`, `packages/adapters/src/builtin-tool-bridge.ts:98-100`). The doc calls this "keyword/BM25" (`docs/settings-from-chat-tasks.md:128-129`); the code is not BM25.
- `use_tool` unwraps to the real tool before the gate, so approvals, audit and UI activity name the real tool (`packages/adapters/src/pi-runtime-tools.ts:93-124`). Unknown name: "`<name>` is not available. Use a name find_tool lists." (`:113`).
- The listed tool set is meant not to change during a run: the code comment says the listed tools "stay small and never change mid-run" (`packages/adapters/src/builtin-tool-bridge.ts:17-19`), and the design doc gives this as the reason the prompt cache survives (`docs/settings-from-chat-tasks.md:129-130`, stated). I did not trace every call site to confirm no mid-run change. Computer mode (1.5) swaps tool sets between the main and computer model (`packages/adapters/src/pi-runtime.ts:547-549`); how that interacts with this claim is unverified.

**How many tools are in the prompt.** A test pins one configuration: for an owner chat with no graphical computer, history retrieval on, no semantic memory, 23 tools are listed (21 core + `find_tool` + `use_tool`) and their JSON definitions must stay ≤ 32,579 bytes (`packages/adapters/src/builtin-tool-bridge.test.ts:31-63`, options at `:12-21`). With a graphical computer the five core screen/page tools are added (`computer_observe`, `computer_act`, `browser_navigate`, `browser_snapshot`, `browser_act`; `packages/adapters/src/builtin-tool-bridge.ts:32-36`), and further core names appear only when their feature is on (`recall_memory`/`save_memory`, `service_*`, `read_email`/`send_email`, `end_call`, `user_computer_shell`). I did not find a test that pins the largest case; by counting the core set an upper bound is 34 + 2 built-ins, plus connector tools (unverified whether all 34 can be offered in one run; e.g. `end_call` needs a voice-call turn). Runs can also list fewer than 23: a "created" run is offered only 2 tools (2.4). Docs/code disagreement: the design doc says the core set is "~12-15 tools" (`docs/settings-from-chat-tasks.md:123`); the code has 34 names.

### 2.2 Connector tools: per-source lazy catalog

- Threshold: each connector lists its tools directly if it has ≤ 20, otherwise replaces them with three wrapper tools (`DIRECT_TOOL_LIMIT = 20`, `packages/adapters/src/lazy-tool-catalog.ts:10`; applied in `packages/adapters/src/mcp-connector.ts:422-424`, `packages/adapters/src/installed-connectors.ts:193-194`, `packages/adapters/src/pipedream-connector.ts:219-225`). The Composio connector does not use this wrapper; it returns whatever its session reports (`packages/adapters/src/composio-connector.ts:591-597`) — unsure how many tools that is in practice.
- `<prefix>_search_tools`: empty query lists tool names by source; `group` lists one source; `query` returns up to 10 hits with id, name, description (≤500 chars), readOnly (`packages/adapters/src/lazy-tool-catalog.ts:11`, `:19`, `:154-223`). If the whole name index fits in 200 names and 2,048 bytes it is embedded in the search tool's description, so the model sees every tool name without calling anything (`:13-14`, `:58-61`, `:502-506`).
- `<prefix>_load_tool` returns one tool's schema (schema must be ≤100,000 bytes, `:12`, `:325-328`); `<prefix>_execute_tool` validates arguments against that schema and runs it (`:330-349`).
- Forgiving lookups: a source name typed as the query is treated as a group filter (`:167-174`); group match is case-insensitive (`:257-263`); `load`/`execute` accept `group:name`, `group/name`, `group__name`, `group.name` instead of the opaque id when unambiguous (`:275-299`, `:301`).
- Failure text steers the next step: "No tool matches every word. Try other words or pass group. Built-in tools are not in this catalog." (`:221`); partial matches are still returned with the list of sources (`:217-222`).
- The system prompt also adds a line naming connected plugins and telling the model to prefer them over the browser or web search (`packages/adapters/src/executor.ts:1513-1516`).

### 2.3 `cloud-agent-tools-select.ts`

Only a static on/off filter: the four `cloud_agent_*` tools are removed when no provider is configured (`packages/adapters/src/cloud-agent-tools-select.ts:11-18`). No discovery logic.

### 2.4 Per-run selection (what is even offered)

`selectBuiltinToolsForRun` removes tools by run type (`packages/adapters/src/run-tool-selection.ts:98-217`). Notable rules:
- the first "created" run gets only `ask_user` and `update_bot` (`:64`, `:165`);
- runs arriving through an external messaging channel lose schedule, skill, memory, scratchpad, ticket and `task_catalog` tools (`:202-215`);
- `update_preferences` and `feedback` only on owner-started runs (`:170`).
A runtime that emits a tool name it was not offered is still checked at dispatch (comment and check at `packages/adapters/src/run-tools.ts:144-157`).

## 3. Self-extension

### 3.1 Skills

- Format: a `SKILL.md` (frontmatter name + description, markdown body). Limits: content 100,000 chars, name 80, description 2,000 (`packages/adapters/src/skill-tools.ts:21-23`).
- Catalog injection: up to 50 skills, one line each, are put in the system prompt with the rule "When a skill matches the user's request, call skill_read for that name and follow it immediately. Prefer matching skills over improvising multi-step recipes." (`packages/core/src/agent-skill.ts:125-136`). Bodies are loaded on demand with `skill_read`, including reference files by exact stored path (`packages/adapters/src/skill-tools.ts:137-167`).
- **Can the bot write its own skills? Yes** (implemented). `skill_create` writes a row with `source: "user"` in the bot's space (`packages/adapters/src/skill-tools.ts:169-224`). The prompt tells it when: "Create a skill with skill_create when a multi-step task is worth repeating (or when asked). After creating one, mention /Name so the user can open it." (`packages/core/src/agent-skill.ts:133`). The tool description adds: "Do not include account names, channels, or inboxes — those belong in a routine." (`packages/adapters/src/builtin-tools.ts:1490`).
- **Can it edit/delete? Only user-created skills that live in its own space alone.** Built-in and plugin skills are refused ("Builtin and plugin skills are read-only.", `packages/adapters/src/skill-tools.ts:243-245`); a skill shared with other spaces is refused ("A skill available in other spaces can only be changed by the user.", `:89-99`, `:297`).
- Skill tools are not offered in runs flagged `messagingChannelRun` (`packages/adapters/src/run-tool-selection.ts:202-204`); non-owner chat runs get only the built-in skills in the catalog and no taught skills (`packages/adapters/src/executor.ts:1517-1518`).
- Unsure whether `skill_create` needs an approval; I did not read the approval gate.
- Built-in skills: two. "Interrogate" (adversarial review) and "Rakazo" (product help: an index of 22 doc URLs with the instruction to `web_fetch` the page before answering and "Never invent menus, buttons, or steps the page doesn't show") (`packages/adapters/src/builtin-skills.ts:3-35`, `:45-68`). The prompt says to read that skill before answering how-to questions about the product (`packages/adapters/src/run-instructions.ts:398`).
- User-side: skills library, "New skill", add from GitHub or a plugin; "Skills added from GitHub or a plugin are instructions only. Any scripts they include are not run." (`docs/skills.md:13-26`, stated).

**Teach by demonstration** (docs `docs/skills.md:34-49`; code as cited):
- The user records on the bot's screen; captured events are pointer, key, clipboard, snapshot, scroll (`packages/core/src/teach-playbook.ts:1-12`). Only printable characters and 11 special keys without modifiers are captured (`packages/core/src/teach-recording.ts:8-29`). Recording TTL 10 min, env `TEACH_RECORDING_TTL_MS` (`packages/core/src/teach-recording.ts:1-6`).
- The playbook is built by a plain function over the event list (`buildPlaybookFromRecording`), with no model call in that function; whether a later step rewrites it with a model was not checked: steps are strings like "Click left button at (x, y)." / "Type \"...\"." (`packages/core/src/teach-playbook.ts:43-56`, `:84-120`; called at `packages/adapters/src/teaching-session.ts:224`). Events flagged sensitive lose key/text (`packages/core/src/teach-playbook.ts:14-20`); typed text matching `password|secret|token|api[_-]?key` becomes "[redacted input]" (`:72-78`).
- Fixed defaults in every playbook: approval boundary "Do not send messages, spend money, publish content, or delete data without explicit user approval." and failure handling "If a step fails or the expected screen is not visible, stop and ask the user before retrying." (`packages/core/src/teach-playbook.ts:38-41`).
- A draft card is posted when the session completes (`packages/adapters/src/teaching-session.ts:459-461`); the user edits and saves (stated, `docs/skills.md:45-47`). Up to 20 saved taught skills are indexed in the prompt (`packages/adapters/src/executor.ts:1519-1531`). A taught skill takes over only when the message contains an invocation verb (run/use/do/repeat/perform/execute) plus the whole skill name (`packages/core/src/teach-playbook.ts:207-225`).

### 3.2 Installing software in its computer

- Docker computer: unprivileged Debian bookworm, persistent home `/home/rakazo`, **no sudo, no `apt` at runtime, no `pip`**; Python packages via `uv tool install` / `uv run --with`; listed as installed: `git`, `ssh`, `curl`, `jq`, `unzip`, `rg`, `fd`, `file`, `sqlite3`, ImageMagick, a graphical browser ("Chromium by default"), `gh`, `pdftotext`, `pandoc`, `openpyxl`. This is my paraphrase of system-prompt text that is added only when the computer kind is `docker` (`packages/adapters/src/run-instructions.ts:125`, `:130`, `:139`); the prompt also says there is no cron, Docker daemon or running systemd (`:139`). The image itself was not read.
- Persistence: what is under the home persists (uv tools, shims, cache); "System packages installed outside the workspace are lost when moving to another provider" (`docs/computer-runtime.md:127-129`, stated). The user has "Update computer" and "Reset computer" buttons (`docs/computer.md:49-51`, stated).
- npm: I found no statement in the prompt about `npm`/`node` in the bot's computer. Unsure whether node is in the image (image not read).
- The prompt includes small recovery hints of the kind Lonora lacks: "If `python` is not found, retry with `python3`. A command-syntax refusal is not a filesystem permission error; continue ordinary file work with supported tools." (`packages/adapters/src/run-instructions.ts:144`).

### 3.3 Writing its own scripts / tools

- Scripts: yes, with `write_file` + `shell` in the persistent home. There is no mechanism that turns a bot-written script into a new named tool in the tool list. The nearest things are (a) a skill that documents how to run the script, (b) a routine with `watch.kind: "command"`, which runs a shell command on a timer "without a model or per-run approval" and wakes the bot only when output changes (`packages/adapters/src/builtin-tools.ts:159-162`).
- The docker-computer prompt says "interpreter heredocs are blocked by the desktop guard" (`packages/adapters/src/run-instructions.ts:144`); the guard code was not read.

### 3.4 MCP servers

- **Bot-initiated:** `add_mcp_server` accepts only remote transports (`streamable_http`, `sse`) and only "details the user provided" ("Do not invent endpoints", `packages/adapters/src/builtin-tools.ts:727`). stdio is refused: "Bots can't add local (stdio) MCP servers. Ask an admin to add it in Settings." (`packages/adapters/src/mcp-server-tool.ts:135-140`). The endpoint goes through an SSRF check and a no-credential-in-URL check (`:148-153`); ≤32 headers (`:14`, `:42`); credentials go to the encrypted secret store, and only header *names* are stored on the server row (`:163-175`, `:201`).
- The server row is created at once but its tools reach the bot only after the user presses Approve/Authorize on an `mcp_approval` card in chat (`packages/adapters/src/mcp-server-tool.ts:207-217`; docs `docs/integrations.md:63-64`). The tool result tells the model exactly what to do next: "An approval card is in the chat. End your turn with one short sentence asking the user to approve it there; ... You will be told when they connect it." (`packages/adapters/src/mcp-server-tool.ts:255-256`).
- **User-initiated:** Integrations "+" → MCP server / OpenAPI / GraphQL / Executor / From GitHub; auth choice No auth / Bearer / API-key header (`docs/integrations.md:27-34`, stated).
- **Admin only:** local stdio servers ("A stdio server runs with the API's and worker's own access, so only admins add or change one.", `apps/api/src/mcp-servers.ts:103-110`). npm-published stdio servers are installed once into a managed directory with a 180 s timeout instead of `npx -y` on every start (`packages/adapters/src/mcp-package-installer.ts:1-10`, `:33`).

### 3.5 Plugins

(stated, `docs/build-a-plugin.md`; limits confirmed in code where cited)
- The doc describes a plugin as two JSON files (`plugin.json`, `mcp.json`) in a public GitHub repo pointing at a hosted HTTPS MCP server, plus optional `skills/<name>/SKILL.md` (`docs/build-a-plugin.md:5-6`, `:17-48`, `:78-91`). The `examples/plugins/hello-world` directory has `plugin.json` and `skills` but no `mcp.json` (directory listing only), so `mcp.json` appears to be optional; unverified in code. "Rakazo reads the plugin files; it never runs code from the repository." (`:6`).
- No secrets in plugin files; `${VAR}` placeholders are rejected (`:75-76`). Hooks, rules, local MCP execution, skill scripts and binaries are not supported (`:144-145`).
- Size limits: 200 files, 4,000,000 bytes total, 40 reference files per skill (`packages/adapters/src/plugin-connectors.ts:62`, `:65`, `:80`; doc `:146-148`).
- Installs are pinned to a commit (`docs/build-a-plugin.md:109`, `:150-151`).
- Installed by the user in Integrations; I found no bot tool that installs a plugin. `examples/plugins/` holds `hello-world` (skills only) and `mcp-server`.

### 3.6 Connecting new accounts / services

- **The bot can start it; the user finishes with one tap.** `connect_app({app})` looks the app up in the managed connector catalogs, and if found and not connected posts a connect card in the thread, de-duplicated against pending cards in the last 50 messages (`packages/adapters/src/connect-app.ts:11`, `:22-51`, `:59-73`). Results are short state strings for the model: "This app is already connected and its tools are available." (`:49`), "Connection card shown. Wait for the user to connect the app." (`:104`), or the error "No such app is available in the connector catalog." (`:45`).
- Prompt rule: "Use connect_app when an app needs connecting or the user asks to connect one, then wait for them." (`packages/adapters/src/run-instructions.ts:312-313`). Tool description: "Then wait for the user instead of directing them elsewhere." (`packages/adapters/src/builtin-tools.ts:576`).
- User side: "The bot posts a card in the chat; choose **Connect** or **Sign in** and finish signing in with the app." (`docs/integrations.md:7-8`, stated). A connected app is available to every bot in the space (`docs/integrations.md:15-16`, stated). The catalog exists only if the operator configured one (`docs/integrations.md:18-21`, stated).
- A stale connection gives the model a concrete instruction: "The X connection is no longer active. Ask the user to reconnect X." (`packages/adapters/src/composio-connector.ts:611-614`).
- Services with only an API key or a website login: `request_secret` card (section 1.11; `docs/integrations.md:72-75`).
- `packages/adapters/src/agent-connections.ts` is about agent-to-agent connections (`connect_agent` etc.), not app accounts; only its tool schemas were read.

### 3.7 Bot secrets (docs `docs/bot-secrets.md`)

- The model never receives a secret value; it holds a name. HTTP use is by backend injection at the exact saved origin (`docs/bot-secrets.md:21-31`; implemented `packages/adapters/src/bot-secrets.ts:1009-1012`).
- Website logins are typed by the page browser only while the page is on the saved HTTPS origin, hidden fields only into password inputs; "Fills need no approval: saving the login is the approval" (`docs/bot-secrets.md:103`, stated).
- "Command variables" are exported into the bot's shell as env vars and the doc is explicit that this is not a boundary: "A command variable is a convenience for the bot, not a boundary against it" (`docs/bot-secrets.md:56`, `:64`, stated).
- One-time codes: user types the code into a card; the bot never sees it and fills it with `fill_code` (`docs/bot-secrets.md:159`, stated).
- The request card has a "Save to Vault" switch only the user can turn off (`docs/bot-secrets.md:87`, stated).

### 3.8 Importing an agent (docs `docs/import-an-agent.md`, stated)

Settings → General → Import an agent. From an OpenClaw/Hermes folder or backup, or from any other assistant by pasting its reply to a provided prompt (`docs/import-an-agent.md:6-25`). Instructions, memory, skills, model, MCP servers, scheduled jobs and (opt-in) API keys map to their Rakazo equivalents (`:31-39`). "Anything that runs code or acts on its own (skills, MCP servers, routines) starts unticked" (`:41`). Only admins may import stdio MCP commands: this rests on an interface comment, "only admins add stdio servers" (`apps/api/src/agent-import.ts:82-83`); the enforcing code was not read (unverified as implemented). Importer code otherwise not read.

### 3.9 Settings from chat

- `update_bot` on itself (implemented, `packages/adapters/src/run-tools-fleet.ts:255-398`): no fields = read current settings plus the models and thinking levels it may pick (`:312-323`); with fields it changes profile fields (name, description, avatar, notifyOnFinish, dailyCheckIns per the schema, `packages/adapters/src/builtin-tools.ts:1625-1688`), model, thinkingLevel, readAloud, voice (`:328`), and instructions. With `bot_id` set it goes to a different path that updates another bot (`:258-262`). A change to model/thinkingLevel/readAloud/voice posts a "Settings updated" card carrying before/after values (`:362-369`); the design doc says this card has an undo (`docs/settings-from-chat-tasks.md:95-97`, stated). Instruction writes are compare-and-set against the text the model started the attempt with (`:370-378`), and a held change needs owner approval (`:263-266`).
- Prompt rule: "Change a setting only when the user asks for that change; when you have no instructions yet and your job becomes clear, set your name, description and instructions yourself. Never claim a change without the tool." (`packages/adapters/src/run-instructions.ts:376`).
- `update_preferences`: strictly `timezone` and `marketingEmails`; any other key returns "Only timezone and marketingEmails can change here; X stay in the app's settings." (`packages/adapters/src/run-tools-preferences.ts:9-11`, `:21-25`); owner-started runs only (`:15-16`); helpers cannot write (`:31-32`).
- What the bot may **not** change from chat (stated design decision): "A bot never widens its own powers from chat: credentials, disabled tools, fleet management, cross-space communication, computer mode and approval preferences stay UI-only." (`docs/settings-from-chat-tasks.md:50-52`). Consistent with the code: none of those fields exist in the `update_bot` schema (`packages/adapters/src/builtin-tools.ts:1625-1688`).
- The same doc records why this was built: "Model changes never succeed today: the bot says it can't, or guesses which model it runs." (`docs/settings-from-chat-tasks.md:11-12`).

## 4. Observations relevant to Lonora's complaint (inference, not a claim about Rakazo's results)

1. Rakazo has no generic "try harder" tool. What it does consistently is make tool results say the next step in plain words: a state ("already connected"), an instruction ("Wait for the user"), or a concrete alternative ("Try other words or pass group", "retry with `python3`", "Send the first 24 or fewer now"). Citations: `packages/adapters/src/connect-app.ts:49`, `:104`; `packages/adapters/src/lazy-tool-catalog.ts:221`; `packages/adapters/src/run-instructions.ts:144`; `packages/adapters/src/computer-tools.ts:34`. For the XAUUSD case the equivalent would be a symbol-not-found result that lists near matches or says "search the broker's symbol list first".
2. Lookups are forgiving on purpose (case-insensitive group, several id spellings, prefix then substring match: `packages/adapters/src/lazy-tool-catalog.ts:238-243`, `:257-263`, `:275-299`). The same idea applied to broker symbols (exact, then prefix, then substring) would have found `XAUUSDm`.
3. When the human is needed, the bot posts a card and stops, instead of explaining a procedure (`connect_app`, `request_secret`, `request_takeover`, `mcp_approval`). This keeps technical steps out of the chat text.
4. "Never claim a change without the tool" and `task_catalog` ("Call it before claiming a task or skill exists") are prompt-level defences against invented capabilities (`packages/adapters/src/run-instructions.ts:376`, `packages/adapters/src/builtin-tools.ts:1227`).

## Weaknesses and risks seen in this area

- **Very large surface.** 88 built-ins + 3 + bridge + catalog wrappers, declared in one 1,977-line file (`packages/adapters/src/builtin-tools.ts`), with a roughly 120-line function, mostly one boolean filter, deciding what each run sees (`packages/adapters/src/run-tool-selection.ts:98-217`). For one owner and one bot most of the fleet, ticket, group, space and agent-connection tools are dead weight.
- **Prompt cost is still high after deferral.** In the one configuration the test pins, 23 tools are listed and their definitions may be up to 32,579 bytes (whether that JSON is re-sent on every model call depends on the provider and caching; not checked) (`packages/adapters/src/builtin-tool-bridge.test.ts:31-63`); the design doc's own target was ~12-15 tools (`docs/settings-from-chat-tasks.md:123`).
- **Huge single descriptions.** The `request_secret` description is one paragraph covering six credential kinds and many rules (`packages/adapters/src/builtin-tools.ts:46-50`); `browser_act` similar (`:357`). Hard to maintain and easy for a weaker model to misread.
- **Three-step indirection for rare tools** (`find_tool` then `use_tool`; search/load/execute for connectors). A model that forgets the first step gets an error and may conclude the capability does not exist; the code already needs special cases for this (`packages/adapters/src/pi-runtime-tools.ts:113`, `packages/adapters/src/lazy-tool-catalog.ts:275-299`). `find_tool` returns only the top 3 (`packages/adapters/src/builtin-tool-bridge.ts:14`).
- **Name collision workaround.** Catalog wrapper names must not start with `mcp_` because, per the code comment, one provider's OAuth endpoint rejects such requests with a misleading "out of extra usage" error (`packages/adapters/src/lazy-tool-catalog.ts:46-50`). Fragile provider-specific knowledge in generic code.
- **Default web search scrapes DuckDuckGo HTML** (`packages/adapters/src/keyless-http-web.ts:25`, `:43-45`). Liable to break or be rate-limited; `web_fetch` runs no JavaScript (`packages/adapters/src/builtin-tools.ts:803`).
- **Taught skills are raw pixel coordinates.** Steps are "Click left button at (x, y)" from the recording (`packages/core/src/teach-playbook.ts:43-56`); they break when the layout or window size changes. The default failure rule is "stop and ask the user before retrying" (`packages/core/src/teach-playbook.ts:40-41`), which is the opposite of what Lonora's owner wants. Redaction of typed text is a keyword regex (`:74-78`).
- **Command variables are readable by the bot's shell** by design (`docs/bot-secrets.md:64`); filled browser fields can be read through the browser's debugging port (`docs/bot-secrets.md:161`). The docs say so, but it is a real exposure.
- **`watch.kind: "command"` runs a shell command on a timer with no model and no per-run approval** (`packages/adapters/src/builtin-tools.ts:162`). Cheap, but an unattended exec path created by the model.
- **Loop guard ends the run with a canned "I got stuck calling ..." text** (`packages/adapters/src/tool-loop.ts:7`, `:38`). Safe, but it is a give-up message shown to the user; the thresholds are 6 identical failures / 25 similar calls (`:38`, `:42`); my opinion is that this can use many calls before stopping.
- **`message_user` silently truncates at 500 chars** and the description has to shout about it in capitals (`packages/adapters/src/builtin-tools.ts:608`).
- **No apt/sudo in the default computer** (`packages/adapters/src/run-instructions.ts:139`): the bot cannot install system packages; anything outside the home is lost on provider change (`docs/computer-runtime.md:127`).
- **Docs drift.** "~12-15 tools" vs 34; "BM25" vs prefix scoring (`docs/settings-from-chat-tasks.md:123`, `:128-129` vs `packages/adapters/src/builtin-tool-bridge.ts:21-56`, `packages/adapters/src/lazy-tool-catalog.ts:576-607`).
- **External dependence for app connections.** The connect-card flow needs a managed catalog (Composio or Pipedream) configured by the operator (`docs/integrations.md:18-21`); without it `connect_app` returns "No such app is available in the connector catalog." (`packages/adapters/src/connect-app.ts:45`).

## Not read / unsure

- The approval gate (`packages/adapters/src/run-tool-gate.ts`, `run-tool-request.ts`): which tools need user approval by default (e.g. `skill_create`, `spawn_bot`, `shell`, `send_email`) is not established here.
- `packages/adapters/src/fleet-tools.ts` (1,389 lines), `media-generation-tools.ts`, `paid-service-tools.ts` bodies, `workspace-file-tools.ts` body, `browser-tools.ts` body, `run-tools-secrets.ts`, `run-tools-pages.ts`, `run-tools-memory.ts`, `run-tools-messaging.ts`, `run-tools-user-computer.ts`: only constants, handler locations and schemas were read.
- `apps/api/src/agent-skills.ts` and `apps/api/src/taught-skills.ts`: only grepped; the GitHub skill import, draft-card Save/Test/Add-to-routine endpoints are taken from docs.
- `packages/adapters/src/agent-connections.ts` not read beyond its tool schemas.
- Import-an-agent implementation (`apps/api/src/agent-import.ts`) read at two lines only.
- `infra/sandboxes/computer` image: not read, so the list of preinstalled software rests on the system-prompt text, and whether `node`/`npm` exist is unknown.
- Composio connector: how many tools a session exposes and whether it has its own meta-search tools is unsure (only `discoverTools` and the start of `execute` were read).
- Which tools a non-background subagent receives was not checked.
- The maximum listed-tool count with every optional feature on is my count from the core set, not a tested number.
- `examples/plugins/*` file contents not opened; only directory listing.
- Whether the "Settings updated" undo is implemented in the clients was not checked (card payload only).

## Verification log

Independent check of every `path:line` citation above against the checkout at commit `cd7e20e5da754d8d8deaf2780671ed34a38e2241`. Each cited line or range was opened; no test suites were run.

**Citations checked:** about 420 `path:line` references in the body as it now stands (counting each `:line` shorthand that follows a path as one; counted with a regex, so approximate), across roughly 70-90 files (regex count of distinct paths, approximate). Most matched as written; the ones that did not are corrected below. A few long ranges that only locate a block (for example `builtin-tools.ts:1692-1791`) were checked at their start and end lines, not read in full. Counts re-derived by hand: 88 built-in tool `name:` lines in `builtin-tools.ts:248-1915`; 3 agent-connection tools; 34 core names; 23 listed tools in the pinned test; 9 background-helper tools; 10 computer-mode tools; 22 doc URLs in the product-help skill; 11 special teach keys.

**Corrections made (before -> after):**

1. Section 0: "Every call passes through one dispatcher" -> "Calls that reach `applyTool` ..."; `ask_user` and an unknown `use_tool` name are answered inside the runtime first (`pi-runtime-tools.ts:551-563`, `:105-113`).
2. Section 1 intro: "core is always listed" -> listed only when the run is offered the tool at all.
3. `attach_file`: "cap 10 MB" -> 10 MB default, configurable per the comments at `contracts/src/attachments.ts:1-4`.
4. Computer mode: uncited "only when a separate computer model is configured" -> cited to `pi-runtime.ts:276`, `:299`.
5. SSRF line numbers: `:63-72` -> `:64-73`; `:86-91` -> `:87-92`; `:254-257` -> `:255-259`.
6. `search_history` / `read_history`: added the missing gate (offered only when history retrieval is enabled, `run-tool-selection.ts:200-201`) and the citation for "max 5 hits" (`builtin-tools.ts:990`).
7. Schedule handlers: range `:209-250` (which ended at the start of `schedule_cancel`) -> the two lines actually opened.
8. `recall_memory` limit 5: added the call site `run-tools-memory.ts:175` (the constant alone did not show it applies to the tool).
9. `request_secret` "1-8 fields": had no citation -> `contracts/src/bot-secrets.ts:276`, `:311`.
10. Credential limit: "100 per bot per user (implemented)" -> code counts per vault scope (`bot-secrets.ts:604`, `:606`); "per bot per user" is the doc's wording (stated).
11. `message_bot`/`handoff_to_bot` 4-file limit: added where the constant is used (`builtin-tools.ts:1832`, `:1870`).
12. `update_bot` field list: added `color`, `artifact_id`, `use_attached_image`, `instructions_offset`, and `bot_id` (updates another bot); section 3.9 "Model/thinking/voice changes post a card" -> model/thinkingLevel/readAloud/voice (`run-tools-fleet.ts:328`), and noted the `bot_id` path (`:258-262`).
13. Loop guard: added that 25 also applies to identical calls that keep succeeding, the over-limit rule (4 batches), and where the stop text ends the run (`run-turn.ts:634-638`).
14. Taint: "a run that has read outside content is marked tainted ... cannot change preferences" -> depends on `toolResultTaintsRun` (not read); preference writes are refused unless the owner already approved; range `:35-41` -> `:33-41`.
15. "The listed tool set never changes during a run" -> stated intent (code comment `builtin-tool-bridge.ts:17-19` plus doc); not traced; computer-mode tool swapping noted as unverified interaction.
16. Tool-count paragraph: "by default" / "pinned minimum" -> "one pinned configuration"; "ceiling 34 + 2" -> upper bound, unverified that all 34 can co-occur; noted that "created" runs list only 2.
17. Lazy catalog: `:166-173` -> `:167-174`.
18. Skills in channel runs: `:203-204` -> `:202-204`, wording tied to the `messagingChannelRun` flag.
19. Teach playbook: "deterministically ..., not by a model" -> no model call in the builder function; later rewriting not checked.
20. Section 3.2: "told to the model verbatim" -> paraphrase of prompt text added only for `docker` computers (`run-instructions.ts:125`); "Chromium" -> "a graphical browser (Chromium by default)"; added no cron / Docker daemon / systemd.
21. Section 3.3: heredoc guard "on some computers" -> as the docker-computer prompt states it.
22. Plugins: "A plugin is two JSON files" -> doc's description; the `hello-world` example has no `mcp.json` (directory listing), so that file looks optional (unverified in code).
23. Import: "Only admins may import stdio MCP commands (implemented)" -> rests on an interface comment at `apps/api/src/agent-import.ts:82-83`; enforcement not read.
24. Weaknesses: "110-line boolean filter" -> roughly 120 lines (`:98-217`); the `mcp_` quotation was not verbatim -> reworded to match the comment at `lazy-tool-catalog.ts:46-50`; "up to 32,579 bytes ... per model call" -> per-call resend not checked; "high enough to burn tokens" marked as opinion.

**Confirmed without change (spot list):** handler map and fallback routing (`run-tools.ts:41-65`); dispatch-time refusals (`:141-165`); every per-run selection rule cited from `run-tool-selection.ts`; shell timeouts (5 min default, 60 min max) and 16,000-char UI output; 1 s / 10 s quiet-return constants and the notice text; web limits (5/10 results; 8,000/50,000/100 chars; 5 MiB offset) and the truncation marker; SSRF constants (15 s, 5 MiB, 5 redirects); email limits (10 recipients, 20,000 chars, 50/day, 200/day, 120 s wait, 8,000-char page, 50 ids); 50 routines; 4 KB memory; 4,000-char shared memory; paid-service limits; 4 parallel subagents, no nesting; cloud-agent limits; MCP 16 MiB / 20 s; 12,000-char tool-result clip; `DIRECT_TOOL_LIMIT = 20` and its three call sites; Composio connector not using the wrapper; all quoted prompt and error strings in sections 2, 3.1, 3.4, 3.6 and 4; skill limits; teach-recording constants and default approval/failure text; `add_mcp_server` stdio refusal, header cap and approval card; `connect_app` results and 50-message de-duplication; `update_preferences` schema and error text; plugin size limits; all cited doc lines in `docs/bot-secrets.md`, `docs/skills.md`, `docs/integrations.md`, `docs/computer.md`, `docs/computer-runtime.md`, `docs/build-a-plugin.md`, `docs/import-an-agent.md`, `docs/settings-from-chat-tasks.md`; the two docs/code disagreements (core-set size, "BM25").

**Remaining doubts:**

- The quiet-return rule for `shell` (1 s when output looks like a device-code prompt, else 10 s) is confirmed from the constants and their comments (`shell-command-stream.ts:10-20`) and their use as defaults (`:186-187`); the branching logic between the two was not read line by line.
- "Hard max 60 min" is the constant `MAX_SANDBOX_COMMAND_TIMEOUT_MS` (`core/src/sandbox-command.ts:2`); the validation function that applies it was not opened.
- `filterBuiltinToolsForRun` / `filterBuiltinToolsForThread` (in `schedule-tools.ts`) and `selectMemoryTools` (in `memory-tools.ts`) are part of the selection chain and were not read, so section 2.4 is not a complete list of rules.
- Section 1.8's `watch` behaviour ("without a model", "only runs the bot on change") is taken from the tool description text, not from the scheduler code.
- Whether `skill_create`, `shell`, `send_email` and others need user approval remains unknown (approval gate not read), as the original author already said.
- Section 4 is inference; its supporting citations were checked, the conclusions were not testable.

