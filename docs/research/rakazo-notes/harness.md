# rakazo harness study: tool registry, validation, errors, discovery, guards

Repository: `/home/user/elie222/rakazo` at commit `cd7e20e`. Read-only study; nothing was run.
Paths are relative to the repo root. `A/` is short for `packages/adapters/src/`, `K/` for
`packages/adapter-kit/src/`, `C/` for `packages/core/src/`.

The agent loop itself is a third-party library ("pi": `@earendil-works/pi-agent-core` and
`@earendil-works/pi-ai`, both pinned at 1.5.0 in `packages/adapters/package.json:36-37`).
`node_modules` is not installed in the checkout, so I read the published 1.5.0 tarballs from npm.
Those citations are written `pi-agent-core/dist/...`, `pi-ai/dist/...`, `pi-schema/dist/...` and
are NOT files in the rakazo repo.

---

## 1. Tool registry

### Definition shape

One plain object type for every tool, built-in or connector:

- `K/types.ts:265-279` `ConnectorTool { name, description, inputSchema (plain JSON Schema object),
  readOnly?, batch?, label?, route?, appResourceUri? }`. There is no `execute` on the definition.
- Built-ins are one static array: `A/builtin-tools.ts:248` `export const builtinAgentTools:
  ConnectorTool[] = [`. It holds 88 entries (counted `name:` lines before line 1918), plus 3
  agent-connection tools in a second array at `A/builtin-tools.ts:1918`.
- Execution is a separate name-to-handler map: `A/run-tools.ts:41-59` `TOOL_HANDLERS`, built by
  spreading per-family maps (`computerTools`, `fileTools`, `memoryTools`, `integrationTools`,
  `taskTools`, `messagingTools`, `secretTools`, `fleetTools`, ...). Handler type:
  `A/run-tool-gate.ts:127` `(ctx: RunContext, call: ToolCall) => Promise<unknown>`.
- A name with no handler falls through to a connector: `A/run-tools.ts:61-65` (prefix
  `cloud_agent_` goes to the cloud-agent handler, everything else to `connectorTool`).
- Conversion to the pi library's tool shape (`name`, `label`, `description`, `parameters`,
  `prepareArguments`, `execute`, optional `executionMode`) happens in
  `A/pi-runtime-tools.ts:362-383` and `:489`. `execute` does not run the tool itself; it calls
  back into the app through `host.request.executeTool(...)` (`A/pi-runtime-tools.ts:631-642`),
  which is wired to `applyTool` at `A/executor.ts:1916-1919`.

### How the per-run set is assembled

Subtractive: start from all 88 built-ins and filter. `A/run-tool-selection.ts:98-217`
`selectBuiltinToolsForRun`, called from `A/executor.ts:1259-1291`. Conditions that remove tools:

| Condition | Effect | Citation |
|---|---|---|
| Model cannot see images / no graphical computer | drop screenshot-returning computer tools | `A/run-tool-selection.ts:151`, `A/executor.ts:1218` |
| No page-capable browser on the computer | drop `browser_navigate/snapshot/act` | `A/run-tool-selection.ts:150-153`, `:225-231`, `A/executor.ts:1219-1220` |
| Bot owner disabled a built-in | dropped | `A/run-tool-selection.ts:136`, `:164` |
| Trigger `created` (intro run) | only `ask_user`, `update_bot`; no connector tools | `A/run-tool-selection.ts:64`, `:165`; `A/executor.ts:1335-1338` |
| Background helper run | only 9 read-only tools | `A/run-tool-selection.ts:71-81`, `:166-167` |
| Fleet tools | need `fleetManagement` and an owner-started run | `A/run-tool-selection.ts:168-169` |
| No payment wallet / no media provider / no paid services / no ticket board | matching tools dropped | `A/run-tool-selection.ts:171-176` |
| Background trigger | no `message_user`, `message_bot`, `handoff_to_bot`, media | `A/run-tool-selection.ts:177-185` |
| Not a voice call | no `end_call` | `A/run-tool-selection.ts:186` |
| No bot email / cannot send | email tools dropped | `A/run-tool-selection.ts:187-189` |
| User's desktop not connected (or no screen driver) | `user_computer_*` dropped | `A/run-tool-selection.ts:190-192`, `A/executor.ts:1245-1258` |
| Run from a shared messaging channel | no schedules, skills, memory, scratchpad, tickets | `A/run-tool-selection.ts:202-215` |
| No cloud-agent provider | 4 `cloud_agent_*` dropped | `A/cloud-agent-tools-select.ts:3-18` |
| Semantic memory off | memory tools filtered | `A/run-tool-selection.ts:147-160` |

Approval mode does NOT change which tools are offered; it is applied per call at the gate
(section 7). Connector tools (MCP, Composio, Pipedream, installed APIs) are appended after the
built-ins, minus any that share a built-in's name: `A/executor.ts:1308-1317`, `:1335-1338`.

### What the model actually sees (two-tier listing)

- 34 "core" built-ins are listed with full schemas: `A/builtin-tool-bridge.ts:21-56`.
- Every other offered built-in is "deferred": `A/builtin-tool-bridge.ts:80-82`. When any exist,
  two bridge tools `find_tool` and `use_tool` are added: `A/builtin-tool-bridge.ts:85-92`,
  `:111-138`.
- Connector tools are always listed directly, but each connector collapses to three wrapper
  tools (`*_search_tools`, `*_load_tool`, `*_execute_tool`) once it has more than 20 tools:
  `A/lazy-tool-catalog.ts:10` (`DIRECT_TOOL_LIMIT = 20`), `A/mcp-connector.ts:422-424`,
  `A/installed-connectors.ts:193-194`, `A/pipedream-connector.ts:219-220`.

Count (derived from the constants, not measured on a live run): at most 34 core + 2 bridge
tools from the built-in side, with up to 54 more built-ins behind `find_tool`; plus per connector
either its tools (20 or fewer) or 3 wrappers. A typical owner chat without wallet, fleet, email
or user desktop will be somewhat under 34 listed built-ins. The comment states the design aim:
"so the listed tools stay small and never change mid-run" (`A/builtin-tool-bridge.ts:17-19`).

There is also a "computer mode" inside the pi runtime: screen tools throw unless the top-level
agent has entered it (`A/pi-runtime-computer-mode.ts:13-24`, `A/pi-runtime-tools.ts:497-502`).

---

## 2. Schema validation and casting

### Libraries

- Tool definitions carry plain JSON Schema (`K/types.ts:268`).
- For the model-facing list they are rebuilt as TypeBox nodes (`import { Type } from "typebox"`,
  `A/pi-runtime-tool-parameters.ts:4`; conversion in `jsonSchemaParameters` `:183-265` and
  `jsonField` `:409-476`). Some built-ins get hand-written, stricter TypeBox schemas:
  `A/pi-runtime-tool-parameters.ts:61-181`.
- Validation of model arguments is done by the pi library with its own JSON-Schema compiler
  (`pi-ai/dist/utils/validation.js:1`, `:12` `compile(schema, { formats, coerce: true,
  unresolvedRefs: "reject" })`).
- Zod is used for a second validation of catalog-executed connector calls
  (`A/lazy-tool-catalog.ts:351-369`, `z.fromJSONSchema`) and inside many handlers.

### Are arguments validated before execution? Yes, in up to three layers

1. `prepareArguments` (rakazo, per tool): `A/pi-runtime-tools.ts:383-488`.
2. Schema validation with coercion (pi): `pi-agent-core/dist/agent-loop.js:497-498` calls
   `prepareToolCallArguments` then `validateToolArguments`.
3. Handler-level checks (rakazo), which return `{ error }`.

Deferred tools called through `use_tool` get the same two first steps explicitly:
`A/pi-runtime-tools.ts:115-122`. So do tool calls replayed from a checkpoint:
`A/pi-runtime.ts:1034-1038`.

### Coercion and casting

- pi-level coercion, stated in the library: "models often send `"42"` for a number, a single
  value for an array, or `null` for an omitted optional property"
  (`pi-ai/dist/utils/validation.js:41-43`). The three passes are described at
  `pi-schema/dist/coerce.js:5-13` (drop null optionals; TypeBox-style conversion; Ajv-style
  primitive coercion). "A value that cannot be coerced is left as it is; the check then reports
  it" (`pi-schema/dist/coerce.js:13`).
- Stringified JSON to object: not found in `pi-schema/dist/coerce.js` (no `JSON.parse` in the
  file). One hand-written exception in rakazo: `request_secret` folds "a JSON string credential"
  into `credential` (`A/pi-runtime-tools.ts:333-360`).
- Schema `default` values are not applied by the validator (not found). Defaults are instead
  hard-coded per tool in `prepareArguments`, e.g. `computer_act` gets `observe: true` and
  `settle_ms: 350` (`A/pi-runtime-tools.ts:420-426`), `write_file` path defaults to
  `notes/result.txt` (`:414-418`), `read_file` drops a bad `offset`/`limit` "so one bad argument
  cannot fail the read" (`:428-438`).
- Fleet tools: `prepareFleetArguments` keeps only known keys, `String()`s them, and drops null or
  blank optionals because "`String(null)` would otherwise become the text "null""
  (`A/pi-runtime-tool-parameters.ts:358-389`). It also accepts `notify_on_finish` as an alias of
  `notifyOnFinish` (`:383`), and `archive_bot` accepts `confirmName`/`botId` camel-case aliases
  (`A/pi-runtime-tools.ts:481-486`).
- Deliberate non-coercion: `ask_user` keeps a bad `options` value as-is "so schema minItems can
  reject it" (`A/pi-runtime-tools.ts:406-408`).

### What the model receives when validation fails (pi library text, verbatim shape)

`pi-ai/dist/utils/validation.js:58-60`:

```
Validation failed for tool "<name>":
  - <dotted.path>: <message>

Received arguments:
<pretty-printed JSON of what the model sent>
```

Paths are converted from JSON Pointers to dotted paths for the model
(`pi-ai/dist/utils/validation.js:16-25`). The error is caught and returned as a normal tool
result with `isError: true`: `pi-agent-core/dist/agent-loop.js:539-545`. It is free text; no
code, no hint, no schema echo.

Catalog-executed connector tools fail with a different shape:
`A/lazy-tool-catalog.ts:366` `Tool arguments are invalid: ${z.prettifyError(parsed.error)}`,
returned as `{ error }` after redaction at `A/run-tool-request.ts:158-160`.

Handler-level Zod errors are flattened by `A/tool-args.ts:4-8` to
`"<path or input>: <message> ..."` on one line.

### Repair of malformed tool-call JSON

- In pi: `pi-ai/dist/utils/json-parse.js:24-70` `repairJson` only escapes raw control characters
  and invalid backslash escapes inside strings; `:71-82` retries `JSON.parse` once on the repaired
  text. If it still fails the arguments become `{}` and an `argumentsError` is attached that
  includes the raw text (`:91-107`), which then reaches the model as
  `Invalid arguments for tool "<name>": <parse error>\n\nReceived arguments:\n<raw text>`
  (`pi-ai/dist/utils/validation.js:50-52`).
- In rakazo: `A/model-json.ts:9-21` uses the `jsonrepair` package, but only for JSON a model
  writes as reply text (structured side-calls), not for tool-call arguments.

### Per-provider schema sanitising

- Root `oneOf`/`anyOf`/`allOf` is flattened into one object and `type: "object"` plus
  `properties` are forced, because "Anthropic rejects the whole request when a tool's root schema
  carries oneOf, anyOf, or allOf" and local OpenAI-compatible servers reject envelopes without
  them: `A/openai-tool-parameters.ts:1-15`, `:43-156`; applied in
  `A/pi-runtime-tool-parameters.ts:12-24`. The comment admits exclusivity is lost on the wire "so
  the executor must keep validating arguments against the original schema"
  (`A/openai-tool-parameters.ts:39-41`).
- String enums are emitted as plain `enum` because "some gateways discard the allowed values from
  anyOf/const unions": `A/pi-runtime-tool-parameters.ts:391-394`. String `const` gets a matching
  one-value `enum`: `:421-431`, `:269-279`.
- Free-form objects are kept open because Fireworks "reads the empty map as 'no keys allowed' and
  emits `{}`": `A/pi-runtime-tool-parameters.ts:225-236`, and `:257-263`.
- A remote MCP schema TypeBox cannot express degrades to a permissive `{}` object instead of
  failing the turn: `A/pi-runtime-tool-parameters.ts:50-59`.
- Tool names are normalised to `^[a-zA-Z0-9_-]+$`, max 64 chars, with stable hash suffixes on
  collision: `A/pi-runtime-tools.ts:58-62`, `:179-187`, `:288-312`. Tools and schema keys are
  sorted so the provider-visible list is stable: `A/pi-runtime-tools.ts:137-173`.
- Gemini only: missing thought signatures on replayed function calls are filled with Google's
  skip marker (`A/google-tool-history.ts:15-40`). This is history repair, not schema work.

---

## 3. Error messages as contract

### Envelope: mostly `{ error: "<sentence>" }`, no uniform structure

- The common shape is a plain object with one free-text `error` string, serialised with
  `JSON.stringify` into the tool result text: `A/pi-runtime-tools.ts:739-748`, `:649-662`.
  Success/failure is detected only by the presence of an `error` key: `A/run-tools.ts:195-199`,
  `A/tool-result-error.ts:1-5`.
- Refusals have a fixed machine code, but it is deliberately NOT given to the model. It is held in
  a `WeakMap` and only logged: `A/tool-refusal.ts:1-11` ("only the code is ever logged"),
  consumed at `A/run-tools.ts:105-124`.
- Thrown errors (handler throws, sandbox failure) become bare text with `isError: true` in pi:
  `pi-agent-core/dist/agent-loop.js:590-598`, `:646-651`.
- No `code`, `class`, `retryable`, `hint`, `candidates` or `next_actions` fields as a general
  convention: not found. Ad-hoc extra fields do exist per tool:
  - `uncertain: true` for an interrupted side effect: `A/approval-effect.ts:463`, `:473-486`.
  - browser tools: `{ ok: false, uncertain, error, fallback: "computer_act", note }`:
    `A/browser-tools.ts:97-99`, `:359-367`, `:503-525`.
  - memory: `{ error, entries: [...] }` (the candidate list): `A/memory-tools.ts:56-62`.
  - skills: `{ error, files: [...] }`: `A/skill-tools.ts:156`.
  - files: `{ error, path, totalLines }`: `A/workspace-file-tools.ts:62-67`.
  - find_tool: `{ tools, unknown?, hint? }`: `A/builtin-tool-bridge.ts:154-158`.
  - catalog search: `{ tools, groups, hint }`: `A/lazy-tool-catalog.ts:218-222`.

So the "contract" lives in the wording of each sentence, which is consistently written to say
what to do next.

### Representative error strings returned to the model

"Next step?" = does the sentence itself tell the model what to do.

| # | Area | String (verbatim) | Citation | Next step? |
|---|---|---|---|---|
| 1 | files | `file is not UTF-8 text; use open_path to inspect it` | `A/workspace-file-tools.ts:215` | yes, names another tool |
| 2 | files | `offset ${offset} is past the end of the file, which has ${totalLines} lines` (+ `totalLines` field) | `A/workspace-file-tools.ts:64-66` | implicit, gives the valid range |
| 3 | files | `file not found or unreadable` (attach_file) | `A/run-tools-files.ts:201` | no |
| 4 | browser | `browser_act accepts at most 24 actions but got N; none ran. Send the first 24 or fewer now, then the rest in a separate call.` | `A/browser-tools.ts:377` | yes |
| 5 | browser | `browser_act action ${index} needs kind: click, fill, ...` (lists all valid kinds) | `A/browser-tools.ts:387-389` | yes, valid options |
| 6 | browser | note: `Page browser could not complete this step. Inspect the current state before continuing with computer_act if available, otherwise request_takeover. Do not replay completed or uncertain actions.` | `A/browser-tools.ts:524` | yes |
| 7 | computer | `unsupported computer action ${kind}` / `computer_act requires at least one action` | `A/computer-tools.ts:95`, `:30` | no (no list of valid kinds) |
| 8 | web | `query is required` / `url is required`; otherwise the provider's raw message | `A/web-tools.ts:10`, `:32`, `:22`, `:45` | no |
| 9 | integrations | `The ${stale} connection is no longer active. Ask the user to reconnect ${stale}.` | `A/composio-connector.ts:613` | yes |
| 10 | integrations | `MCP server "<name>" is unavailable: <reason>` | `A/mcp-connector.ts:678` | partly (reason) |
| 11 | integrations | `No such app is available in the connector catalog.` (connect_app) | `A/connect-app.ts:45` | no, no candidates |
| 12 | routines | `A watch takes no schedule: it checks every watch.everyMinutes minutes (.. to 1440). Call again without ${named}.` | `A/schedule-tools.ts:643` | yes |
| 13 | routines | `Schedule not found.` / `Provide routineId or the exact schedule name to cancel.` | `A/schedule-tools.ts:866`, `:1013` | first no, second yes |
| 14 | memory | `No entry contains old_text. Copy it exactly from one of these entries.` + `entries` | `A/memory-tools.ts:59-61` | yes, with candidates |
| 15 | memory | `Memory is full (N bytes). Make room by merging, shortening or removing entries with old_text, then save again.` | `A/memory-tools.ts:76` | yes |
| 16 | secrets | `Credential is unavailable. Use request_secret to save it first.` | `A/bot-secrets.ts:999` | yes |
| 17 | secrets | `This login has no field named "x". Its fields: A, B.` | `A/bot-secrets.ts:1346` | yes, valid options |
| 18 | fleet | `No bot named "${name}". Call list_fleet and pass bot_id.` | `A/fleet-tools.ts:1137` | yes |
| 19 | interrupted effect | `The earlier ${toolName} execution was interrupted, so its outcome is unknown. It was not replayed to avoid a duplicate side effect. ...Call list_fleet to check whether it happened before retrying.` | `A/approval-effect.ts:477-486` | yes |
| 20 | gate | `${name} is not available to a background helper. Don't retry; say in your result what the bot should do.` | `A/run-tools.ts:154` | yes |

Pattern worth copying: errors state (a) what happened, (b) whether anything ran ("none ran"),
(c) the next call, and often (d) an explicit "Don't retry" when retrying cannot help. Weak spots
are numbers 3, 7, 8, 11 and "Schedule not found.".

Connector errors are passed through with redaction and a 2,000-character cap
(`A/connector-safety.ts:22-30`); Composio batch failures are expanded so that "the model cannot
tell 'message not found' apart from a broken integration" is avoided
(`A/composio-connector.ts:950-977`).

### The error classes in adapter-kit

- `K/sandbox-errors.ts:8-129`: typed sandbox errors with a `code` and human message
  (`SandboxRateLimitError` with `retryAfterMs` `:8-17`, `SandboxUnavailableError` "The computer
  did not start. Try again." `:65-71`, `SandboxDamagedError` `:103-109`, ...).
  `isSandboxProviderOutage` (`:77-84`) is used for log level and job handling, e.g.
  `A/workspace-file-tools.ts:330`. These are run/infra-level, not a tool-result envelope.
- `K/connector-errors.ts:4-10`, `K/secret-errors.ts:1-17`: same pattern, a class with `code`.
- `K/model-errors.ts:4-26`, `:175`: classify failures of the model provider call
  (`TransientModelError`, `isTransientModelError`), used for model retry and backup-model
  fallback. Not about tools.

### `retryable` for tools and automatic retry

- A `retryable` field on tool results: not found.
- `C/retry-policy.ts:17-21` `isRetryableError` exists (no response, 5xx, 429, 408) but its users
  are background loops such as the computer running-check (`A/computer-lifecycle.ts:682-697`),
  not tool dispatch.
- Automatic retry of a failed tool call before the model sees it: not found in
  `A/run-tools.ts:95-193` (single `await toolHandler(...)`, `:184`) nor in pi
  (`pi-agent-core/dist/agent-loop.js:580-598`).
- Computer start is lazy and happens inside the first tool that needs it
  (`A/run-computer.ts:9-29`, `A/run-tools-files.ts:30`). A failed start is kept and aborts the
  whole run rather than being shown to the model as a tool error: `A/run-computer.ts:7`,
  `A/executor.ts:1029`, `A/run-turn.ts:770`, `:1026-1030`.
- Retry is instead steered through wording ("Try again.", "Don't retry; tell the user.") and
  through idempotency: every side-effecting call is recorded as an effect, and a duplicate
  returns the stored result or the "outcome is unknown" error instead of re-running
  (`A/approval-effect.ts:435-461`, `A/run-tool-gate.ts:611-672`).

---

## 4. Not-found / resolution behaviour

Mixed. Exact match plus a "go list them" pointer is the default; real fuzzy matching with
candidates exists in three places (models, catalog tool ids, deferred tool search).

1. **Bot names (fleet): exact only, with a pointer.** `A/fleet-tools.ts:1113` "Exact ids or exact
   names"; lookup `:1148-1168`; not found gives `No bot named "x". Call list_fleet and pass
   bot_id.` (`:1163-1167`); duplicates give `More than one bot is named "x". Pass bot_id
   instead.` (`:1159-1161`). No near-name candidates, not even case-insensitive. Groups are the
   same (`:1171-1200`).
2. **Model names: fuzzy, with candidates.** `A/model-choice.ts:68-111` matches "a model name as
   people say it": every said word must appear in the model's name, hyphenated versions are
   normalised (`:39-54`), ties go to the bot's current provider, then the plainest family, then
   newest version. Ambiguous gives `"x" matches several models. Ask the user which one, or pass
   its id as model: p/id (Label), ...` (`:134-141`). Nothing connected gives `No connected model
   matches "x". The user needs to connect <Provider> in Settings first.` (`:154-159`).
3. **Catalog tool ids (connector lazy catalog): tolerant.** `A/lazy-tool-catalog.ts:265-299`
   accepts the exact id, the bare tool name, or a group-qualified name with any of `: / __ .`
   separators (`:301-323`), because "Models often name a tool by the source label they saw in
   search". Ambiguous gives `Tool name is ambiguous; use one of these ids: ...` (`:288-294`).
   Unknown gives `Tool is unknown or not authorized for this bot. Use the exact id returned by
   search.` (`:296-298`). Source (group) names are matched case-insensitively (`:257-263`).
4. **Skills: case-insensitive exact name, no candidates.** `C/agent-skill.ts:230-237`;
   `A/skill-tools.ts:114-125`; miss gives `Skill not found.` (`A/skill-tools.ts:143`). A wrong
   file inside a skill does list the valid files: `A/skill-tools.ts:156`.
5. **Routines: exact id or exact name, no candidates.** `A/schedule-tools.ts:1021-1023`; miss
   gives `Schedule not found.` (`:1031`). One helpful special case: if it exists but belongs to a
   different chat, the error says so (`A/schedule-tools.ts:783-793`).
6. **File paths: no fuzzy resolution.** `A/computer-support.ts:121-132` only expands `~` and
   maps into the bot's folder. A missing file in `read_file` rethrows the sandbox provider's
   error as raw text (`A/workspace-file-tools.ts:194-201`); `attach_file` returns the fixed
   `file not found or unreadable` (`A/run-tools-files.ts:200-202`). No sibling-name suggestions.
7. **App names (connect_app): slug or name, case-insensitive, plus featured aliases; no
   candidates.** `C/app-connect.ts:15-22`, `A/connect-app.ts:25-45`.
8. **Deferred built-in names (find_tool `names`): exact, with `unknown` echoed back and a hint.**
   `A/builtin-tool-bridge.ts:146-158`.

---

## 5. Tool discovery

Two parallel mechanisms that share one ranking function.

### Algorithm: keyword scoring, no embeddings, no model

- `A/lazy-tool-catalog.ts:226-255` `rankCatalogEntries`, scoring in `:576-607`.
- Query is lower-cased and split on anything that is not a Unicode letter or digit
  (`:560-565`).
- Each query word scores on its best field: tool name 3, source/group 2, description 1
  (`:583-587`). A word matches when a field word starts with it (`:594-597`), so "project"
  finds `list_projects`.
- An exact tool name outranks everything (`:582`).
- If no tool matches every word at a word start, the whole query is rescored allowing matches
  anywhere inside a word ("mail" in "gmail"): `:238-243`.
- **Hits are the tools with the highest number of matched words, as long as that is at least
  one** (`:244-245`). A query word that is absent from the catalogue therefore does not zero the
  result; the tools matching the remaining words are still returned.
- For deferred built-ins, parameter names are appended to the description so they rank too
  (`A/builtin-tool-bridge.ts:98-101`).

### Zero hits and partial hits

- Connector catalog: if hits are partial or empty, the result still carries the list of sources
  with counts and this hint (`A/lazy-tool-catalog.ts:217-222`):
  `No tool matches every word. Try other words or pass group. Built-in tools are not in this
  catalog.`
- An empty query lists names by source, or source counts if the list is too big
  (`A/lazy-tool-catalog.ts:176-204`). A query that is exactly a source name is treated as "list
  that source" (`:166-173`). Unknown group: `{ group, names: [], error: "Unknown or empty group"
  }` (`:178-183`).
- `find_tool`: zero hits gives `{ tools: [], hint: "Pass names from this tool's list or other
  words." }` (`A/builtin-tool-bridge.ts:157`). Partial matches are returned without saying they
  are partial (the `complete` flag is ignored at `:149`).
- The model is never dependent on search alone: the full name index of every deferred built-in,
  grouped by area, is embedded in the `find_tool` description
  (`A/builtin-tool-bridge.ts:115`, areas `:60-78`), and the connector search tool's description
  embeds the name index when it fits 200 names / 2,048 bytes
  (`A/lazy-tool-catalog.ts:57-61`, `:13-14`, `:502-506`), else source names with counts
  (`:547-558`).
- A failed MCP server is still represented by a stand-in tool whose description says "Tell the
  user it failed to start rather than saying it is not assigned" (`A/mcp-connector.ts:264-281`).
- Related prompt line: "a missing connection alone is never a reason to decline"
  (`A/executor.ts:1385`), and `connect_app` guidance at `A/run-instructions.ts:312-313`.

### Language

Built-in names and descriptions are English literals (`A/builtin-tools.ts:248-262`). The
tokenizer is Unicode-aware (`\p{L}\p{N}`, `A/lazy-tool-catalog.ts:563`) but there is no
translation, stemming, synonym table or embedding (not found). A query in another language
matches only if its words literally appear in a name, source or description. The mitigation is
the embedded name index, which lets the model pick by name regardless of the user's language.

### How a discovered tool becomes callable

- Built-ins: `find_tool` returns `{ name, description, inputSchema }`
  (`A/builtin-tool-bridge.ts:155`); the model then calls `use_tool { name, arguments }`. The
  wrapper unwraps to the real tool, runs its `prepareArguments` and schema validation, then its
  normal `execute`, so "its gate, approvals, checkpoint, audit and activity all name that tool
  exactly as a direct call would" (`A/pi-runtime-tools.ts:89-125`). The tool list itself never
  changes mid-run (`A/builtin-tool-bridge.ts:17-19`). The description says to call `find_tool`
  first, but this is not enforced in code: `use_tool` only checks the name is runnable
  (`A/pi-runtime-tools.ts:104-105`).
- Connectors: `*_search_tools` then `*_load_tool` (returns the input schema,
  `A/lazy-tool-catalog.ts:465-477`) then `*_execute_tool { id, arguments }`, which is resolved to
  the real tool and Zod-validated before the gate (`A/lazy-tool-catalog.ts:330-349`,
  `A/run-tool-request.ts:126-160`).

### Limits

`FIND_TOOL_LIMIT = 3` (`A/builtin-tool-bridge.ts:14`); `find_tool.names` max 5, query max 200
chars (`:119-120`); connector search limit 10 (`A/lazy-tool-catalog.ts:11`, `:206-209`);
descriptions cut to 500 chars in hits (`:19`, `:214`); a loaded schema over 100,000 bytes is
refused with `Tool schema is too large` (`:12`, `:325-328`).

`A/run-tool-selection.ts` and `A/cloud-agent-tools-select.ts` are availability filters, not
search. `A/mcp-server-tool.ts` is the `add_mcp_server` handler (registering a new server,
`:127-162`), not discovery.

---

## 6. Tool-call guard

### `pi-tool-call-guard.ts` is narrow

It handles one case only: tool calls with an empty name. "Some OpenAI-compatible gateways stream
tool-call deltas whose `function.name` never arrives" (`A/pi-tool-call-guard.ts:3-8`). Such calls
and their results are stripped from the transcript just before it is sent
(`A/pi-tool-call-guard.ts:26-60`, `:62-65`), and only for the OpenAI-compatible provider
(`A/pi-openai-compatible-provider.ts:408`, `:445`). It tells the model nothing. It does not
detect repeats, loops or unknown names.

### Repeat / loop detection lives in `tool-loop.ts`

- `A/tool-loop.ts:118-153`, driven from `A/run-turn.ts:550-583`.
- Same tool + same arguments failing 6 times in a row stops the run (`A/tool-loop.ts:37-38`,
  `:147-150`). Calls that differ only by digits, or identical calls that keep succeeding, get 25
  (`:39-42`). A repeat whose last answer was new restarts the count, to allow polling
  (`:111-117`, `:134-137`). Results are fingerprinted with failures marked (`:91-109`).
- 4 consecutive `computer_act`/`browser_act` batches over the 24-action limit also stop the run
  (`:45-49`, `:59-68`).
- When it trips, the model is NOT warned or nudged; the model stream is aborted and the run ends
  with a message to the user (`A/run-turn.ts:616-650`). Text (`A/tool-loop.ts:7-10`, `:24-27`):
  `I got stuck calling <tool> with the same input N times in a row without making progress, so I
  stopped early. Try rephrasing this, or ask me to try a different approach.`
- Optional hard cap on tool calls per turn, off by default (`A/pi-runtime-tools.ts:64-71`); past
  it the model gets `Skipped: tool-call limit reached.` (`:519-524`).
- A softer variant for one class of refusal: the first time explains, a repeat ends the turn
  (`A/run-context.ts:371-385`). Denied approvals are remembered and a repeat gets `The user
  denied this action. Do not retry or rephrase it; tell the user and ask what they want instead.`
  (`A/approval-effect.ts:417-418`, `A/run-tool-gate.ts:500-506`).

### Model calls a tool that does not exist

- Not in the listed tools: pi answers `Tool <name> not found` with `isError: true`
  (`pi-agent-core/dist/agent-loop.js:487-494`). No candidates, no hint.
- Unknown name through `use_tool`: `<name> is not available. Use a name find_tool lists.`
  (`A/pi-runtime-tools.ts:113`).
- If a name still reaches app dispatch: disabled gives `This tool is disabled for this bot.`
  (`A/run-tools.ts:141-143`); otherwise it falls to the connector handler, which ends in
  `unknown tool <name>` (`A/run-tools-integrations.ts:39`, `:80`). The code notes "a runtime can
  still emit any name" (`A/run-tools.ts:144-145`).
- Fuzzy correction of a misspelled tool name: not found.

---

## 7. Permissions and sandbox at the harness level

### Where a call is gated

Single choke point `A/run-tools.ts:95-193`, in order: daily-check-in allowlist (`:125-132`),
handed-off stage (`:133-140`), disabled tool (`:141-143`), background-helper allowlist
(`:146-157`), page browser / image capability (`:158-165`), resolve catalog call
(`:166-175`), tool-specific preconditions (`:176-177`), then `gateToolCall` (`:179-180`), then
the handler with an audit record (`:182-192`).

`A/run-tool-gate.ts:151-687` decides run / ask / auto-review / refuse. Inputs include the tool's
declared `readOnly` (`:165-183`), approval rules and the space's approval mode
(`:326-332`, modes include `auto` and `never`, `:333`, `:372`), whether the destination site is
new, whether a purchase is involved (`:367-380`), and the trigger (webhook runs cannot ask,
`:184-194`). Each gated call is recorded as an effect with an idempotency key (`:611-672`).

### What the model sees

- Denied by rule: `<name> is blocked in this space. Don't try it another way; tell the user it's
  blocked.` (`A/run-tool-gate.ts:399`).
- Never-ask space, untrusted origin: `<name> needs the owner's approval because it could have
  been asked for by someone else, and this space never asks. Don't retry; tell the user.`
  (`A/run-tool-gate.ts:400`).
- Unattended: `This would complete a purchase, which needs the user's approval, and a webhook run
  cannot ask. Don't retry; tell the user.` (`A/run-tool-gate.ts:387`).
- Helper: `<name> needs the owner's approval, and a background helper cannot ask. Don't retry;
  say in your result what the bot should ask for.` (`A/run-tool-gate.ts:580`).
- User denied (now or earlier in the run): `The user denied this action. Do not retry or rephrase
  it; tell the user and ask what they want instead.` (`A/approval-effect.ts:417-418`, `:442-445`).
- Awaiting approval: the tool result is `Waiting for approval.` with `terminate: true`
  (`A/approval-effect.ts:374-381`). The turn is checkpointed, an approval card is posted and the
  run pauses (`A/run-tool-gate.ts:799-826`); the turn is aborted so no further model request
  happens (`A/pi-runtime-tools.ts:681-684`). On approval the exact stored request is replayed,
  not a re-generated one (`A/run-tool-request.ts:186-189`). `ask_user` and `request_takeover`
  pause the same way with `Waiting for the user's choice.` / `Takeover requested.`
  (`A/pi-runtime-tools.ts:545-548`, `:576-580`).

### Where tools execute

- Inside the bot's computer (through the `sandbox`/`browser` provider): `shell`
  (`A/run-tools-computer.ts:373-394`), `read_file`/`list_files`
  (`A/workspace-file-tools.ts:163-167`, `:191-193`), `write_file`
  (`A/run-tools-files.ts:107-112`), `attach_file` reads from it (`A/run-tools-files.ts:194-199`),
  the page browser (`A/browser-tools.ts:329-333`), plus `computer_observe/act`, `open_path`,
  `launch_app`, `render_plot` (same file family, `A/run-tools-computer.ts:529-592`). The computer
  is started lazily by the first of these (`A/run-computer.ts:3-8`).
- In the app process: web search/fetch (`A/run-tools-integrations.ts:153-168`), connectors and
  MCP (`:35-81`), `connect_app` (`:192-207`), memory, schedules, skills, fleet, secrets, tickets
  (handlers call Prisma directly, e.g. `A/skill-tools.ts:142-149`,
  `A/schedule-tools.ts:855-857`), and the non-background `run_subagent`
  (`A/pi-runtime-tools.ts:624-630`). `find_tool` is answered inside the runtime
  (`A/pi-runtime-tools.ts:611-622`).
- On the user's own desktop through a device gateway: `user_computer_*`
  (`A/run-tools.ts:51-53`; gated separately at `A/run-tool-gate.ts:365-366`).

---

## Weaknesses seen

1. **No structured error envelope.** The only machine-readable signal the model gets is the
   presence of an `error` key; the refusal `code` exists but is hidden from the model
   (`A/tool-refusal.ts:1-11`). Quality depends on each author writing a good sentence; several do
   not (`Schedule not found.`, `Skill not found.`, `No such app is available in the connector
   catalog.`, `unsupported computer action`).
2. **Three different validation-failure shapes** (pi text, `Tool arguments are invalid: ...`,
   `argsError` one-liners) and none of them echo the expected schema or valid values.
3. **Unknown tool name gives `Tool X not found`** with no suggestion
   (`pi-agent-core/dist/agent-loop.js:489-494`). Deeper in the app the fallback is the even
   barer `unknown tool X` (`A/run-tools-integrations.ts:80`).
4. **Not-found handling is inconsistent.** Models and catalog ids resolve fuzzily with
   candidates; bots, groups, routines, skills, apps and file paths do not, and bot names are
   case-sensitive (`A/fleet-tools.ts:1135`).
5. **Discovery is literal keyword matching on English text.** No synonyms, stemming or
   embeddings; non-English queries depend on the embedded name index. `find_tool` returns at most
   3 results and does not say when they are only partial matches
   (`A/builtin-tool-bridge.ts:14`, `:149`).
6. **Two discovery systems with different verbs** (`find_tool`/`use_tool` vs
   `*_search_tools`/`*_load_tool`/`*_execute_tool`), and the connector hint has to tell the model
   "Built-in tools are not in this catalog" (`A/lazy-tool-catalog.ts:221`).
7. **`use_tool` does not enforce the "find_tool first" rule** stated in its description
   (`A/pi-runtime-tools.ts:104-122`).
8. **No automatic retry and no `retryable` flag** for transient tool failures; web and connector
   errors pass provider text straight through (`A/web-tools.ts:22`, `:45`).
9. **Loop guard never warns the model.** It goes straight from silent counting to ending the run
   (`A/run-turn.ts:576-583`); only the over-limit action case tells the model in the error text.
10. **`prepareArguments` silently invents values** (`write_file` path `notes/result.txt`,
    `ask_user` question `What should I use?`, `A/pi-runtime-tools.ts:402`, `:416`), which can
    hide a model mistake instead of reporting it.
11. **A failed computer start aborts the run** rather than letting the model continue with
    non-computer tools (`A/run-computer.ts:7`, `A/executor.ts:1029`).

## Not read / unsure

- Nothing was executed, so the "typical run" tool count is derived from constants, not measured.
- The pi library is not vendored in the repo; I read the npm 1.5.0 tarballs matching the pinned
  version. I did not read all of `pi-schema/dist/coerce.js` (584 lines); the coercion summary
  relies on its header comment (`:1-19`) and a search showing no `JSON.parse` in the file.
- Whether `z.fromJSONSchema(...).safeParse` coerces types for catalog calls: the code requests no
  coercion (`A/lazy-tool-catalog.ts:363-364`), but a comment elsewhere mentions "Zod
  stripping/coercion" (`A/run-tool-request.ts:258-259`). Not verified against Zod 4.6.7.
- Whether text of errors thrown by handlers is secret-redacted before it reaches the model on the
  normal (non-replay) path: the replay path sanitises (`A/pi-runtime.ts:1054`); I did not trace
  the normal path beyond pi's catch.
- Not read in full: `A/builtin-tools.ts` (only the head, structure and names), most of
  `A/run-tool-gate.ts:215-590` (read selectively), `A/run-tools-messaging.ts`,
  `A/run-tools-email.ts`, `A/run-tools-pages.ts`, `A/run-tools-tasks.ts`,
  `A/run-tools-user-computer.ts`, `A/pi-runtime-subagent.ts`, `A/schedule-tools.ts` filters
  (`filterBuiltinToolsForRun/Thread`), `A/memory-tools.ts` `selectMemoryTools`,
  `A/run-instructions.ts` (only the `connect_app` line), the Pipedream and installed-API
  connectors beyond their catalog threshold lines, and all tests.
- `planActionGate` and `userComputerGate` internals (the actual ask/allow/review matrix) were not
  read; section 7 describes inputs and outputs only.
