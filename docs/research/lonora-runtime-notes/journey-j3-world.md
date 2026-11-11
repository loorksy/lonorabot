# Journeys J3: acting in the world (files, code, browser, web, MCP, skills, notifications)

Repository `/home/user/lonorabot`, HEAD `9f5b1da` (the working tree was clean before and after every run). Read-only audit. Paths are relative to the repo root unless they start with `audit/`, which means `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/`.

## 0. What is real and what is scripted

REAL in every run: the API app over PostgreSQL (database `audit_j3_test`), the Personal Agent row, the owner message route (`POST /threads/{id}/messages`), the context builder and operating-policy chapters, the frozen tool exposure, `tool_environment` / `tool_call`, the tool registry and every tool handler, dispatch, `environment.observe()` (the `recovery` block), the guard rails, the automatic read retry, run status and stream events.

SCRIPTED (and labelled "SCRIPTED" in every raw file): only the model turns, i.e. which tool calls the model makes and its final text. The final texts in the raw files ("SCRIPTED final text (not evidence)") are not evidence of what a real model would say. The evidence is each tool result, the inventory text, the native tool list, the guard text, the stream events and the run status.

FAKE, only where stated: J3-02c uses a local HTTP stub as the "website" and replaces the SSRF check `validate_public_url` by identity so the stub on 127.0.0.1 can be reached (the fetch code itself is real). J3-02 and J3-03 try real hostnames; the sandbox has no DNS, so those calls end in `remote_host_unavailable`. That code is a property of this sandbox, not of the product, and I do not use it as evidence.

The owner requests below are representative asks I chose for each capability. They are not production messages, except J3-07, which reproduces production messages [74] to [76] and the production tool search.

Files:

- Driver: `audit/scripts/j3_world.py`, library `audit/scripts/j3_lib.py`, reset `audit/scripts/j3_reset_db3.sh`.
- Raw outputs: `audit/runs/J3-*.txt` (plus `audit/runs/J3-07-discovery-tokens.txt` and `audit/runs/J3-07-gate-trace.txt`).
- Rerun any journey (the reset empties database 3 first): `cd /home/user/lonorabot && source /tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/env.sh 3 && /tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/j3_reset_db3.sh && .venv/bin/python /tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/j3_world.py <ID>` where `<ID>` is one of `J3-01 J3-01b J3-02 J3-02b J3-02c J3-03 J3-03b J3-04 J3-05 J3-06 J3-06b J3-06c J3-07 J3-08`. The wrapper `audit/scripts/j3_run.sh <ID>` does reset + run and writes `audit/runs/<ID>.txt`. Variants that need a different deployment setting (`J3-01b`, `J3-02b`) set the environment variable inside `j3_world.py` (`ENV`, search that name).
- Existing check also run: `cd /home/user/lonorabot && source .../audit/env.sh 3 && .venv/bin/python -m pytest tests/test_capability_exposure.py -q -p no:cacheprovider` printed `30 passed`. It asserts the same availability mechanism this audit shows (`tests/test_capability_exposure.py:625-629`, `tests/test_capability_exposure.py:851-857`). Its context has no workspace access object at all, so there `workspace_execute` carries `workspace_unconfigured` (`tests/test_capability_exposure.py:626`), whereas the real gateway always injects one and the code is `workspace_execution_unconfigured` (`packages/gateway/src/lonora_gateway/runtime.py:107-109`).

## 1. Correction from the production trace (the trace wins)

`audit/production-trace.md:20-21` lists the tools offered in production: baseline native set of 23 tools including `web_search`, and "U0 = unavailable {mcp_execute: mcp_tool_not_authorized, economic_calendar_read: economic_calendar_not_configured}". The unavailable set therefore did NOT contain `workspace_execute`, `workspace_*`, `web_browse`, `skill_package_validate` or `web_search`. Those backends (analysis host, browser service, a search provider) were configured in the owner's production install, because the same availability checks that list them as missing in my fixture (`audit/runs/J3-01.txt`, line starting `unavailable_now`) did not list them in production.

Consequence for this file: journeys J3-01, J3-02 and J3-03 reproduce what a deployment WITHOUT those backends gives the model. They are not what the owner hit on 2026-11-11. The owner's conversation never asked for files, browsing, MCP or skills (I searched `audit/lonora-chat.md`); the live failures in my area are the tool-discovery ones (J3-07) and the self-description at `audit/lonora-chat.md` message [81]: when asked what it can do, the reply lists only market, watch and decision work and says «أحذف أو أوقف متابعة إذا كانت الأداة متاحة» (`audit/lonora-chat.md:645`), with no mention of web, files, code, skills or MCP.

No earlier findings file needed changing for this; I checked `audit/map-tools-world.md` against these runs and its statements about the unavailable-tool inventory and the empty discovery result (its S9 row) match.

## 2. Summary table

| ID | Owner asks | What the runtime gave the model | Class |
|---|---|---|---|
| J3-01 | «احسب لي القسط الشهري لقرض 50000 بفائدة 7% على 5 سنوات» (no analysis host) | `tool_environment` query returns an empty list; `workspace_execute` -> bare `workspace_execution_unconfigured` + `inspect_authorized_alternative` naming nothing | dead-end (this deployment) + recoverable-not-led |
| J3-01b | «حلل لي ملف المبيعات واحسب المتوسط» (host configured, not answering) | `workspace_execution_uncertain`, though the connection never opened | bug + leak |
| J3-02 | «افتح موقع example.com وقلي شو مكتوب فيه» (no browser service) | `browser_unconfigured`; the named fallback `web_fetch` is not native | owner-needed (operator) + recoverable-not-led |
| J3-02b | same, browser service configured but down | 7.5 s of silent runtime retries, then bare `tool_connection_failure` | leak + silence |
| J3-02c | open a page that redirects / blocks robots | redirect and 403 give the same bare `research_source_unavailable`; no Location | recoverable-not-led + bug |
| J3-03 | «ابحث لي عن آخر أخبار الذهب على الإنترنت» (no search provider) | `web_search` not native; 4 failed attempts; guard text says "correct the arguments" | owner-needed, led only if the model finds the card tool |
| J3-03b | owner switches "web search" on for the chat, provider missing | prompt orders the model to gather sources with a tool that is not offered | owner-needed, silent |
| J3-04 | «ثبّت لي مكتبة yfinance واستخدمها لجلب الأسعار» | no install tool; discovery empty; nothing says what is preinstalled | dead-end (needed for safety) + recoverable-not-led |
| J3-05 | «استخدم خادم MCP حق github وجيب لي آخر issues» (no server) | `mcp_not_found` for a guessed id; the card path exists and works | owner-needed (led, if discovered) |
| J3-06 / 06b / 06c | «اعمل لي مهارة جديدة ... ثم استخدمها» | create works; `skill_view` right after -> bare `skill_disabled`; with a Python utility and no host, activation is a dead end | recoverable-not-led / dead-end |
| J3-07 | «ألغِ المراقبة على الذهب» / «شوف ادواتك» (production messages) | the production tool query returns `[]` for a reproducible reason; a direct call by exact name works | recoverable-not-led (root cause of production [75]) |
| J3-08 | «ابعتلي رسالة على تيليجرام لما يخلص التحليل» | no outbound channel tool; `owner_notify` says "Shown" while its status says not shown | dead-end + bug |

## 3. Cross-cutting mechanisms (each seen in the journeys below)

M1. A failing tool gives the model only a code. `dispatch_call` builds `{"ok": False, "code": error.code}` (`packages/agent-runtime/src/lonora_agent/tool_dispatch.py:113`); `observe()` adds a `recovery` block chosen from the spelling of the code: `*_unconfigured` and three named codes become `not_configured` / `inspect_authorized_alternative` (`packages/agent-runtime/src/lonora_agent/environment.py:74-79`), `*_not_found` becomes `inspect_existing_state` (`packages/agent-runtime/src/lonora_agent/environment.py:80-81`), everything else `terminal_domain_failure` / `alternate_route` (`packages/agent-runtime/src/lonora_agent/environment.py:36-37`). The block is attached at `packages/agent-runtime/src/lonora_agent/environment.py:210`. It never names which alternative tool, card or owner step.

M2. Tools whose backend is missing are taken out of the native tool list and are named only as `name=code` in one inventory line. `registry.exposure` drops every unavailable name from the eager set (`packages/tools/src/lonora_tools/registry.py:288`); the inventory prints `unavailable_now (backend or permission missing when this Run started; calls fail with the code unless that changed): ...` (`packages/tools/src/lonora_tools/registry.py:442`). Doc and code differ in wording: the availability docstring says "A failing check never hides a capability: the handler stays authoritative" (`packages/tools/src/lonora_tools/registry.py:229`); the code does hide it from the native list (line 288) and keeps it callable through `tool_call`. The code wins.

M3. The personal agent's native set contains no world tool except `web_search`. Its profiles are `core`, `market` (the personal role counts as trading) and `coordination` (`packages/agent-runtime/src/lonora_agent/tool_exposure.py:43-46`). `web_fetch` is `eager_for("research")` only (`packages/tools/src/lonora_tools/search.py:331`) and `web_search` is `eager_for("research", "coordination")` (`packages/tools/src/lonora_tools/search.py:342`). So workspace, browser, MCP, skill-package, feed, notify and artifact tools are one `tool_environment` + `tool_call` step away. Production confirms the same 23-tool set (`audit/production-trace.md:20`).

M4. Tool discovery is a strict gate, not a ranking. In `search_definitions` the "gate" token is the rarest query token, ties broken alphabetically (`packages/tools/src/lonora_tools/tool_discovery.py:62`); a tool must contain it (`packages/tools/src/lonora_tools/tool_discovery.py:70`), and a query of four or more known words needs at least half of them in the same tool (`packages/tools/src/lonora_tools/tool_discovery.py:64`). A word that occurs in no tool name, description or parameter name has frequency 0, so it becomes the gate and every tool fails. Tokens are whole words with no stemming (`packages/tools/src/lonora_tools/tool_discovery.py:41`). The schema tells the model to use English catalog terms (`packages/tools/src/lonora_tools/environment.py:16`); an Arabic query is therefore always empty. The empty answer carries no hint (`packages/tools/src/lonora_tools/registry.py:383`).

M5. Operating-policy chapters arrive only after the model has called a tool of that domain. `apply_operating_policy` scans the last 16 messages for assistant tool calls and maps each call name to a chapter (`packages/agent-runtime/src/lonora_agent/skills/system_policy.py:134-138`; the mapping is `packages/agent-runtime/resources/system/manifest.json`, e.g. `web_search` -> `research` at line 38, `owner_notify` -> `voice` at line 133). The `research` chapter holds the rule "A missing account, key or server is one connect_credential card" (`packages/agent-runtime/resources/system/lonora.md:561`) and "If a service is unavailable, state the practical access limitation and the single supported next step" (`packages/agent-runtime/resources/system/lonora.md:568`). Observed: in J3-03 the first two scripted turns carry no domain chapter and turn 3 (after the first failed `web_search`) carries it (`audit/runs/J3-03.txt`, block "domain policy chapters present").

M6. The repeated-failure guard text is generic. After the third failure of the same tool in a run the model gets: "{tool} has failed {count} times in this run. Diagnose the latest error before another attempt: correct the arguments, use a narrower request or a genuinely different source, or report the blocker." (`packages/agent-runtime/src/lonora_agent/tool_guardrails.py:83-86`, warn at 3 failures, halt at 8: `packages/agent-runtime/src/lonora_agent/tool_guardrails.py:57-58`). A not-configured backend counts like any failure.

M7. The model is also told, by policy, to report the limit: "Shell and Python analysis require execution_configured from workspace_inspect; an unconfigured backend cannot run commands." (`packages/agent-runtime/resources/system/lonora.md:157`), "Report the practical failure and one concrete next step" (`packages/agent-runtime/resources/system/lonora.md:163`). This is honest and needed for honesty, but with M1 it is the shortest path to «ما أقدر».

## 4. Journeys

### J3-01: «احسب لي القسط الشهري لقرض 50000 بفائدة 7% على 5 سنوات» with no analysis host

Owner request: «احسب لي القسط الشهري لقرض 50000 بفائدة 7% على 5 سنوات» (a plain calculation; the same path serves "analyse this file").

Rerun: `cd /home/user/lonorabot && source /tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/env.sh 3 && /tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/j3_reset_db3.sh && .venv/bin/python /tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/j3_world.py J3-01` (output saved in `audit/runs/J3-01.txt`)

Setup: default fixture settings, i.e. no `LONORA_WORKSPACE_SOCKET` (deployment without the analysis host).

What the model was given before it acted (REAL): 22 native tools, none of them a workspace, browser or MCP tool: `peer_send, memory_read, memory_write, session_search, skills_list, skill_view, market_instrument, market_quote, market_candles, market_snapshot, market_sessions, watch_create, market_decision_record, market_decision_history, chart_snapshot, list_accounts, account_read, trade_execute, wait_for_input, agent_inspect, tool_environment, tool_call`. The inventory line in its system prompt (verbatim): `unavailable_now (backend or permission missing when this Run started; calls fail with the code unless that changed): economic_calendar_read=economic_calendar_not_configured, mcp_execute=mcp_tool_not_authorized, skill_package_validate=workspace_execution_unconfigured, web_browse=browser_unconfigured, web_search=research_provider_not_configured, workspace_execute=workspace_execution_unconfigured`.

Scripted turns (every model turn is SCRIPTED; calls to non-native tools are sent through `tool_call`, which the runtime unwraps, so the raw transcript shows the real tool name):

1. SCRIPTED: `tool_environment {"query": "run python calculation"}`
   RUNTIME result: `{"ok": true, "tools": [], "total": 0, "next_offset": null, ... "execution_authorized": false}`
2. SCRIPTED: `workspace_inspect {}`
   RUNTIME result: `{"ok": true, "revision": 0, "files": [], "execution_configured": false, "active_operation_id": null, "recovery_required": false}`
3. SCRIPTED: `workspace_update {"revision": 0, "files": {"calc.py": ...}}`
   RUNTIME result: `{"ok": true, ..., "revision": 1, "files": [{"path": "calc.py", "size": 57, ...}]}`
4. SCRIPTED: `workspace_execute {"revision": 1, "command": "python calc.py"}`
   RUNTIME result (verbatim): `{"ok": false, "code": "workspace_execution_unconfigured", "recovery": {"category": "not_configured", "next_action": "inspect_authorized_alternative", "safe_to_retry": false, "schema_tool": "tool_environment", "attempt": 1, "retry_exhausted": false}}`

What the owner sees: whatever the model writes next; the runtime gave it one bare code and a `recovery` block that names no alternative. The model had already written a file the tool could not run (turn 3 succeeded before turn 4 failed): the files tools are available while execution is not, which the availability map shows (`workspace_update` is not in the unavailable list).

Root cause:

- Execution availability is the `execution_configured` flag: `packages/tools/src/lonora_tools/workspace.py:45-51`; the flag is `executor is not None` (`packages/agent-runtime/src/lonora_agent/workspace_access.py:139-141`); the executor exists only when a socket is configured (`packages/gateway/src/lonora_gateway/runtime.py:107-109`).
- The code is turned into the generic recovery by M1 (`packages/agent-runtime/src/lonora_agent/environment.py:74`); no tool, card or message follows from it. The system capability report does say "not_set_up: this server lacks it; say so plainly" (`packages/tools/src/lonora_tools/capabilities.py:303`) and marks `workspace_execution` `not_set_up` (`packages/tools/src/lonora_tools/capabilities.py:90`), but `capabilities_list` is not native (M3) and nothing tells the model to call it.
- The discovery query is empty because "calculation" is in no tool text (frequency 0) (M4; `audit/runs/J3-07-discovery-tokens.txt`: `{"query": "run python calculation", ... "tokens_found_in_no_tool": ["calculation"], "result": []}`), while the one-word query `python` finds `workspace_execute` (same file).
- No other tool can compute: `chart_indicator` is the only tool with the word "calculate" (`audit/runs/J3-07-discovery-tokens.txt`, `calculate -> tools containing the token: 1`).
- "Analyse this file": no tool takes an artifact or attachment id and writes it into the workspace. `workspace_update` takes the file content as a string in the call (`packages/tools/src/lonora_tools/workspace.py:26-28`); `artifact_read` returns a 24,000-character text page (`packages/tools/src/lonora_tools/artifacts.py:23-27`) and `workspace_export` goes the other way (`packages/tools/src/lonora_tools/workspace.py:83-89`). I found no tool in `packages/tools/src/lonora_tools/` that copies an owner attachment into the workspace (grep of `attachment_id|artifact_id` found only `artifacts.py`). A large owner file therefore has to pass through the model's own context and be re-typed. UNSURE: whether the owner's uploaded file reaches the model by another path (for example inline text in the message); I did not test an upload.

Class: dead-end for a deployment with no analysis host (operator-needed), plus recoverable-not-led (empty discovery, recovery that names nothing). The isolation of the container itself (no network, no host files) is needed for safety (`packages/agent-runtime/src/lonora_agent/workspace.py:207`); the missing host and the missing alternative are not.

### J3-01b: analysis host configured but not answering

Owner request: «حلل لي ملف المبيعات واحسب المتوسط».

Rerun: same command as J3-01 with `J3-01b` (the driver sets `LONORA_WORKSPACE_SOCKET=/tmp/claude-0/does-not-exist/workspace.sock`; raw output `audit/runs/J3-01b.txt`).

Setup: the socket is configured, so the availability check passes and the inventory line no longer lists `workspace_execute` or `skill_package_validate` (`audit/runs/J3-01b.txt`: `unavailable_now ...: economic_calendar_read=..., mcp_execute=..., web_browse=..., web_search=...`).

Scripted turns: SCRIPTED `workspace_update` (ok, revision 1); SCRIPTED `workspace_execute {"revision": 1, "command": "python -c 'print(2)'"}`; SCRIPTED `workspace_inspect`; SCRIPTED the same `workspace_execute` again.

RUNTIME results (verbatim):

- First execute: `{"ok": false, "code": "workspace_execution_uncertain", "recovery": {"category": "terminal_domain_failure", "next_action": "alternate_route", "safe_to_retry": false, "schema_tool": "tool_environment", "attempt": 1, "retry_exhausted": false}}`
- `workspace_inspect` right after: `{"ok": true, "revision": 1, ..., "execution_configured": true, "active_operation_id": null, "recovery_required": false}` (so the host is reported as configured while it does not exist).
- Same execute again: the same code with `"attempt": 2` and `"runtime_notice": [{"kind": "tool_guardrail", "source": "lonora_runtime", "message": "workspace_execute has failed 2 times with identical arguments. Inspect the error and change strategy instead of retrying it unchanged."}]`.

Root cause: `WorkspaceClient.execute` maps every `httpx.HTTPError` to `workspace_execution_uncertain` with the comment "No automatic transport retry: the host might already be running the command" (`packages/agent-runtime/src/lonora_agent/workspace_client.py:111-114`). That is right when a request was sent and the answer was lost; it is wrong for a socket that does not exist, where the command certainly did not run. The model is told an effect may have happened; the guard then says "change strategy" (`packages/agent-runtime/src/lonora_agent/tool_guardrails.py:79-80`) with no strategy available. The policy tells the model to keep "unavailable and uncertain" distinct (`packages/agent-runtime/resources/system/lonora.md:163`), but the runtime itself reports "uncertain" for an unavailable host.

Class: bug (wrong code) + leak (internal code `workspace_execution_uncertain` is all the model has).

### J3-02: «افتح موقع example.com وقلي شو مكتوب فيه» with no browser service

Rerun: same command with `J3-02` (`audit/runs/J3-02.txt`). Setup: default fixture settings (no `LONORA_BROWSER_URL`).

Scripted turns: SCRIPTED `tool_environment {"query": "open website browse page"}`; SCRIPTED `web_browse {"url": "https://example.com"}`; SCRIPTED `web_fetch {"url": "https://example.com"}`.

RUNTIME results:

- Discovery finds `web_browse` and `web_fetch` (`audit/runs/J3-02.txt`, first result; the raw file trims the long result before the availability fields). Each entry carries `"invoke"`, `"available"` and, when missing, `"unavailable_reason"` (`packages/tools/src/lonora_tools/registry.py:329-333`); the same fields are visible for `web_search` in `audit/runs/J3-03.txt` (`"available": false, "unavailable_reason": "research_provider_not_configured"`).
- `web_browse`: `{"ok": false, "code": "browser_unconfigured", "recovery": {"category": "not_configured", "next_action": "inspect_authorized_alternative", "safe_to_retry": false, "schema_tool": "tool_environment", "attempt": 1, "retry_exhausted": false}}`.
- `web_fetch` ended in `remote_host_unavailable`. That is the sandbox having no DNS (see section 0), so I draw no conclusion from it; the working path of `web_fetch` is shown in J3-02c.

Root cause: `browser_available` returns `browser_unconfigured` when `context.browser_url` is empty (`packages/tools/src/lonora_tools/browser.py:37-38`) and `browse` raises the same code (`packages/tools/src/lonora_tools/browser.py:42-43`). The tool description itself names the fallback: "Use web_fetch for simple text sources and web_search to discover URLs." (`packages/tools/src/lonora_tools/browser.py:109`), but the runtime's recovery block does not (M1), `web_fetch` is not in the personal agent's native set (M3), and the `research` chapter that says "If a search/browser backend is unavailable, do not repeat it under a new query pretending it worked" (`packages/agent-runtime/resources/system/lonora.md:553`) only arrives after a research tool was called (M5).

Class: owner-needed in the sense of operator-needed (the server lacks the browser), plus recoverable-not-led (a text fetch of a plain page is possible and is not pointed to). Needed for safety: the browser is anonymous, GET/HEAD only and public-only (`packages/tools/src/lonora_tools/browser.py:104-110`); that limit is not the failure.

### J3-02b: browser service configured but not answering

Owner request: «افتح هذا الموقع وقلي شو مكتوب فيه: https://93.184.216.34/» (an IP-literal URL so the sandbox DNS does not mask the failure).

Rerun: same command with `J3-02b` (`audit/runs/J3-02b.txt`; the driver sets `LONORA_BROWSER_URL=http://127.0.0.1:9`, a port with no listener).

Scripted turn: SCRIPTED `web_browse {"url": "https://93.184.216.34/"}`, then one scripted final text. Everything between is the runtime.

RUNTIME behaviour (verbatim fragments):

- Pass 1: stream events `tool.completed {"name": "web_browse", ..., "ok": false, "code": "tool_connection_failure", "attempt": 1, "recovery_pending": true ...}` then `run.retry_scheduled {"reason_code": "tool_read_recovery", "retry_at": ...}`; the run status goes back to `queued` and the owner has no assistant message (last chat messages: only the owner's own).
- After two more silent retries the model finally receives (verbatim): `{"ok": false, "code": "tool_connection_failure", "recovery": {"category": "temporary_unavailable", "next_action": "alternate_route_or_wait", "safe_to_retry": false, "schema_tool": "tool_environment", "attempt": 3, "retry_exhausted": true}}`.
- Measured: 7.5 seconds from the first model turn to the end of the run.

Root cause: a read-only tool with a transient code is retried by the runtime with back-off `2**attempt` seconds (`packages/agent-runtime/src/lonora_agent/environment.py:222`, scheduled at `packages/agent-runtime/src/lonora_agent/tool_block.py:309-328`); the browser tool maps every non-timeout `httpx.HTTPError` to `tool_connection_failure` (`packages/tools/src/lonora_tools/browser.py:61-62`). The retry itself is good (the runtime recovers alone and the model is not asked). What is missing: nothing tells the owner anything during the wait, and the final result is a bare code with `alternate_route_or_wait` and no named route.

Class: leak + silence (recoverable-not-led at the end).

### J3-02c: a page that redirects or blocks robots (`web_fetch`)

Owner request: «افتح هذا الرابط وقلي شو فيه».

Rerun: same command with `J3-02c` (`audit/runs/J3-02c.txt`). FAKE parts: a local stub site and `validate_public_url` replaced by identity (section 0).

Scripted turns: SCRIPTED three `web_fetch` calls: a URL answering 301 with a `Location` header, a URL answering 403, and the redirect target itself.

RUNTIME results (verbatim):

- `/redirect` (301): `{"ok": false, "code": "research_source_unavailable", "recovery": {"category": "terminal_domain_failure", "next_action": "alternate_route", ...}}`
- `/blocked` (403): the identical result.
- `/real` (200): `{"ok": true, "source": "http://127.0.0.1:38193/real", "observed_at": "...", "untrusted_content": "Price list\nGold 2650"}`

Root cause: `fetch` uses `follow_redirects=False` (`packages/tools/src/lonora_tools/search.py:137`) and answers any error status or redirect with the same code: `if response.is_error or response.is_redirect: raise LonoraError("research_source_unavailable", 502)` (`packages/tools/src/lonora_tools/search.py:141-142`). The model cannot tell "moved to another URL" from "blocked" from "not found", and the target URL of the redirect is not returned. Many public sites redirect from the bare domain or `http` to `https://www.`; the first such request always fails with this bare code. Needed for safety: not following redirects blindly (each hop must be re-checked by the SSRF guard, `packages/tools/src/lonora_tools/search.py:136`); reporting "redirect" versus "blocked" separately is not a safety matter. UNSURE: I did not test a real site, so how often production sites redirect on the first request is not measured here.

Class: recoverable-not-led + bug (two different situations collapsed into one code).

### J3-03: «ابحث لي عن آخر أخبار الذهب على الإنترنت» with no search provider

Rerun: same command with `J3-03` (`audit/runs/J3-03.txt`). Setup: no SearXNG URL, no Brave integration.

Facts about what the model has: `web_search` is NOT native in this deployment because the exposure drops unavailable tools (M2; `audit/runs/J3-03.txt` first block, list has no `web_search`); the inventory names `web_search=research_provider_not_configured`.

Scripted turns and RUNTIME results:

1. SCRIPTED `tool_environment {"tool_name": "web_search"}` -> entry with `"invoke": "tool_call", "available": false, "unavailable_reason": "research_provider_not_configured"`. Its `common_error_codes` list is `tool_arguments_invalid, tool_result_too_large, tool_not_allowed, broker_candles_unavailable, broker_connection_timeout, broker_connection_unavailable, market_candles_unavailable, market_quote_unavailable, provider_temporarily_unavailable, tool_connection_failure, tool_read_timeout`: the same generic read-tool list for every read-only tool (`packages/tools/src/lonora_tools/environment.py:43-48`), with broker codes and without `research_provider_not_configured`.
2. SCRIPTED `web_search {"query": "آخر أخبار الذهب"}` -> `{"ok": false, "code": "research_provider_not_configured", "recovery": {"category": "not_configured", "next_action": "inspect_authorized_alternative", ... "attempt": 1}}`.
3. SCRIPTED two more `web_search` calls with other queries (the tool's own description says "do not retry under new queries pretending access worked", `packages/tools/src/lonora_tools/search.py:337-338`). On the third failure the result gained: `"runtime_notice": [{"kind": "tool_guardrail", "source": "lonora_runtime", "message": "web_search has failed 3 times in this run. Diagnose the latest error before another attempt: correct the arguments, use a narrower request or a genuinely different source, or report the blocker."}]`. The failure is not about the arguments; the notice recommends correcting them (M6).
4. SCRIPTED `capabilities_list {}` -> `built_in` contains `{"capability": "web_search", "state": "not_connected", "via": null}` and `"guidance": "Use any ready capability without asking. not_connected: offer one connect_credential card. not_set_up: this server lacks it; say so plainly. ..."`.
5. SCRIPTED `tool_environment {"query": "connect search credential card"}` -> found `owner_action_propose` (the only tool that can raise the card).
6. SCRIPTED `owner_action_propose {"kind": "connect_credential", "target": "brave_search"}` -> `{"ok": true, "owner_action": {"id": "...", "kind": "connect_credential", "status": "pending", ...}, "already_shown": false, "shown_in_conversation": true, "owner_must_tap": true, "passkey_required": false, "execution_authorized": false}`.
7. SCRIPTED `news_feed_read` of a public RSS URL -> `{"feeds": [{"domain": "reuters.com", "status": "unavailable", "reason": "remote_host_unavailable"}]}` (sandbox DNS; no conclusion).

So a way forward exists (a one-tap card for the owner's Brave key, `packages/contracts/src/lonora_contracts/owner_actions.py:47`). It is reachable only if the model (a) calls `capabilities_list` or reads the `research` chapter, and (b) finds `owner_action_propose`, which is not native (its inventory family is `trading`, `audit/runs/J3-01.txt`, and it is absent from the personal agent's native list printed there). The chapter that explains the card arrives only after a research tool was already called (M5): in `audit/runs/J3-03.txt` the first two scripted turns carry no domain chapter, turn 3 carries "External research and configured connections" with the connect_credential rule. A wasted web_search failure is therefore the normal price of learning the rule. The `research` chapter also names the backend ("the configured self-hosted SearXNG service", `packages/agent-runtime/resources/system/lonora.md:539`); that is model-facing policy text, and nothing in it is written for the owner.

Root cause: `search_available` / `web_search` raise `research_provider_not_configured` when neither a SearXNG URL nor an enabled Brave integration with a secret exists (`packages/tools/src/lonora_tools/search.py:180-183`, `packages/tools/src/lonora_tools/search.py:190-191`).

Class: owner-needed (a key or a server setting), led only if the model finds the card tool; the guard text is misleading.

### J3-03b: the owner switches web search on for the chat, but no provider exists

Owner request: «ما هو سعر الذهب اليوم؟ ابحث في الإنترنت» after switching the chat option on through the real route `PUT /threads/{id}/options`.

Rerun: same command with `J3-03b` (`audit/runs/J3-03b.txt`).

RUNTIME facts: the option is stored (`web_search: true`); the model's native list does not contain `web_search`; the inventory says `web_search=research_provider_not_configured`; and the run context contains (verbatim) `<lonora_chat_option>The owner switched on web search for this chat. Before answering, gather current sources with the web_search tool and ground the answer in them; say briefly where the facts come from. If web search is unavailable, say so plainly instead of answering as if you had searched.</lonora_chat_option>`.

Root cause: the option adds `web_search` to the native list only if the tool is available (`packages/agent-runtime/src/lonora_agent/tool_exposure.py:111-117`, the clause `"web_search" not in unavailable` is at line 116), but the prompt block is added without that check (`packages/agent-runtime/src/lonora_agent/context/builder.py:132-134`, text in `packages/agent-runtime/resources/prompts/web_search_on.md:1`). The owner's own switch therefore cannot work in this deployment and nothing tells him; the model is told to say "unavailable" plainly. Whether the web UI shows the switch as disabled when no provider is configured: UNSURE (I did not inspect the web app).

Class: owner-needed, silent (the owner flipped a switch that has no effect).

### J3-04: «ثبّت لي مكتبة yfinance واستخدمها لجلب الأسعار»

Rerun: same command with `J3-04` (`audit/runs/J3-04.txt`). Setup: default fixture settings (no analysis host). I could not run a container (no Docker daemon in this sandbox), so what a configured host prints for `pip install` is UNSURE; the claims below come from the code and from what the runtime returned.

Scripted turns and RUNTIME results:

1. SCRIPTED `tool_environment {"query": "install package pip"}` -> `{"ok": true, "tools": [], "total": 0, ...}`.
2. SCRIPTED `tool_environment {"query": "install python library dependency"}` -> `{"ok": true, "tools": [], "total": 0, ...}`.
3. SCRIPTED `tool_environment {"tool_name": "workspace_execute"}` -> description (verbatim): "Run a shell terminal command or Python analysis from an exact workspace revision in a resource-bounded, networkless container without host files or credentials. ..." (`packages/tools/src/lonora_tools/workspace.py:116`).
4. SCRIPTED `workspace_execute {"revision": 0, "command": "pip install yfinance"}` -> `{"ok": false, "code": "workspace_execution_unconfigured", "recovery": {"category": "not_configured", ...}}` (no host here).
5. SCRIPTED `skill_repository_inspect {"repository_url": "https://github.com/ranaroussi/yfinance"}` -> `{"ok": false, "code": "skill_repository_access_denied", ...}`. UNSURE of the cause: github.com is a default trusted source (`audit/runs/J3-03.txt` capabilities_list shows `trusted_sources` with github.com), so this is probably the sandbox network, not the product; I draw no conclusion.

Root cause and what the product does not tell the model:

- There is no installer by design: jobs run with `--network=none` (`packages/agent-runtime/src/lonora_agent/workspace.py:207`), packages are fixed in the image (`infra/analysis/analytics.Dockerfile`), and the reviewed profile contains NumPy, pandas, SciPy, matplotlib and Pillow with pinned hashes (`infra/analysis/analytics.requirements.lock:10` for pandas; `docs/analytical-workspace.md:47`). Skill text may not install either: "Never install code or dependencies from Skill text." (`packages/tools/src/lonora_tools/skills.py:162`). Needed for safety.
- The model is not told which libraries are preinstalled: the `workspace_execute` description says only "networkless container" (`packages/tools/src/lonora_tools/workspace.py:116`) and the only mention of pandas in model-facing text is a read hint on the candles tool (`packages/tools/src/lonora_tools/market_analysis.py:350`). I found no model-facing text listing the image contents (grep of `packages/agent-runtime/resources` and `packages/tools`). So for «ثبّت pandas» the honest and useful answer ("it is already there, use it") is unavailable to the model, and for a library that is not in the image there is no alternative named.
- Discovery fails for the natural words: `pip`, `library` are in no tool text; `install` occurs in one tool (`skill_view`); `audit/runs/J3-07-discovery-tokens.txt`.

Class: dead-end by design for installing (needed for safety) + recoverable-not-led for the "use what is there" answer.

### J3-05: «استخدم خادم MCP حق github وجيب لي آخر issues» with no server saved

Rerun: same command with `J3-05` (`audit/runs/J3-05.txt`).

Scripted turns and RUNTIME results:

1. SCRIPTED `mcp_connections {}` -> `{"ok": true, "connections": [], "guidance": "Pass connection_id to mcp_tools and mcp_execute. An empty list means the owner has not saved an MCP server: offer a connect_credential card. trusted_tier null means the owner has not reviewed its tools yet: propose trust_source. read: only the tools the server marks read-only run."}` (`packages/tools/src/lonora_tools/mcp.py:207-212`). This result leads.
2. SCRIPTED `mcp_tools {"connection_id": "github"}` (a guessed id, which the tool description forbids: "do not guess ids", `packages/tools/src/lonora_tools/mcp.py:414-415`) -> `{"ok": false, "code": "mcp_not_found", "recovery": {"category": "not_found", "next_action": "inspect_existing_state", ...}}`.
3. SCRIPTED `mcp_execute {"connection_id": "github", "name": "list_issues", "arguments": {}}` -> `{"ok": false, "code": "mcp_not_found", ...}`.
4. SCRIPTED `tool_environment {"query": "connect MCP server credential"}` and `{"query": "connect_credential"}` -> both found `owner_action_propose`.
5. SCRIPTED `owner_action_propose {"kind": "connect_credential", "target": "mcp_server"}` -> `{"ok": true, "owner_action": {"id": "...", "kind": "connect_credential", "status": "pending", ...}, "shown_in_conversation": true, "owner_must_tap": true, "passkey_required": false, "execution_authorized": false}`.

Adding a server from chat is therefore possible only as a card: "a secure form whose value goes straight to the server, never to you" (`packages/tools/src/lonora_tools/owner_actions.py:314-316`); the agent cannot write the server row itself, which is needed for safety (a URL and token typed in chat would leak). The card text the owner sees: UNSURE (I did not render it; the card carries only server facts per the tool description).

Gaps found:

- `mcp_execute` is flagged `mcp_tool_not_authorized` in the inventory when the owner has no declaration and no trusted server (`packages/tools/src/lonora_tools/mcp.py:275-293`), yet in this run it answered `mcp_not_found` for the guessed id, because the availability code is presentation only (`packages/tools/src/lonora_tools/registry.py:229`) and the handler checks the connection first (`packages/tools/src/lonora_tools/mcp.py:358`). The model sees two different codes for the same missing setup.
- The `research` chapter with the connect_credential rule arrives after the first `mcp_*` call (`audit/runs/J3-05.txt`: turn 1 no chapter, turn 2 onward present, M5).
- The route to the card works only because the query words "connect", "credential" and "MCP" happen to be in the card tool's text (M4).

Class: owner-needed, led (after one wasted call and one discovery step).

### J3-06, J3-06b, J3-06c: «اعمل لي مهارة جديدة اسمها ملخص-الصباح تلخّص أخبار الذهب كل صباح بخمس نقاط قصيرة، ثم استخدمها»

Rerun: same command with `J3-06`, `J3-06b` and `J3-06c` (`audit/runs/J3-06.txt`, `J3-06b.txt`, `J3-06c.txt`). Setup: default fixture settings, no analysis host. The SKILL.md content and the review fields are mine (SCRIPTED).

J3-06 (create, then use at once). SCRIPTED turns and results:

1. `workspace_update` with `drafts/morning/SKILL.md` -> ok, revision 1.
2. `skill_package_create {"source_directory": "drafts/morning", "workspace_revision": 1, "version": "1.0.0", "expected_version": 0, ...}` -> `{"ok": true, "skill_id": "morning-gold-brief", ..., "enabled": false, "source_kind": "workspace", ..., "utilities": [], ...}`. Created disabled: "Preserve actual workspace origin, create disabled, then validate exact utilities before activation." (`packages/tools/src/lonora_tools/skills.py:124`). An instructions-only skill needs no analysis host.
3. `skill_view {"skill_id": "morning-gold-brief"}` (the model "uses it right away") -> `{"ok": false, "code": "skill_disabled", "recovery": {"category": "terminal_domain_failure", "next_action": "alternate_route", ...}}`. The result does not say that `skill_package_control` with `action: "activate"` is the next step.

J3-06b (activate). SCRIPTED: `skill_package_control {"skill_id": ..., "expected_version": 1, "action": "activate", "workspace_revision": 2}` -> `{"ok": true, ..., "resource_version": 2, ..., "enabled": true, ...}` with no owner tap; then `skill_view` -> `{"ok": true, "skill_id": "morning-gold-brief", "skills": [{"id": "morning-gold-brief", "version": "1.0.0", "source": "installed", "provenance": "agent_authored", ... "content": "Read the latest gold news with web_search or news_feed_read, ..."}], "authority_granted": false, ...}`. `skills_list` in the same run also contains `morning-gold-brief`. So creating and using a skill from chat works end to end for instructions-only skills. Activation without an owner tap is allowed because "Instructions ... cannot grant tools, permissions, or financial authority" (`packages/tools/src/lonora_tools/skills.py:162`); nothing in `packages/agent-runtime/src/lonora_agent/skills/lifecycle.py:495-500` asks the owner for instructions-only activation.

J3-06c (a skill with a Python utility, no analysis host). SCRIPTED: `workspace_update` with `SKILL.md` + `mean.py`; `skill_package_create` -> ok, `"utilities": ["skills/mean-calc/1.0.0/mean.py"]`, disabled; `skill_package_validate` -> `{"ok": false, "code": "workspace_execution_unconfigured", ...}`; `skill_package_control` activate -> `{"ok": false, "code": "skill_package_validation_required", "recovery": {"category": "terminal_domain_failure", "next_action": "alternate_route", ...}}`.

Root cause:

- Activation of a package with utilities requires a successful validation receipt per utility (`packages/agent-runtime/src/lonora_agent/skills/packages.py:71-90`, `packages/agent-runtime/src/lonora_agent/skills/lifecycle.py:495-499`); validation needs the analysis host (`packages/tools/src/lonora_tools/skills.py:142`). Without a host the skill can never be activated and the code returned says only "validation required". Needed for safety: no unvalidated code is activated; the missing hint is not.
- A disabled skill is reported as `skill_disabled` (`packages/agent-runtime/src/lonora_agent/skills/registry.py:143`) with the generic recovery (M1). From the code, `skills_list` also lists disabled entries with that code (`packages/agent-runtime/src/lonora_agent/skills/access.py:243-256`); I did not read the J3-06 list output in full (trimmed in the raw file), so that part is from code only.
- Skill tools are not native except `skills_list` and `skill_view` (`packages/tools/src/lonora_tools/skills.py:158,168`); `skill_package_create/control/validate` and `workspace_update` must be discovered, and the query `create skill` does find all seven skill tools, `skill_package_create` first (`audit/runs/J3-07-discovery-tokens.txt`); a longer or non-English phrasing hits M4.

Class: J3-06 recoverable-not-led (`skill_disabled`); J3-06b works (no failure); J3-06c dead-end without an analysis host (activation blocked by a rule needed for safety).

### J3-07: «ألغِ المراقبة على الذهب» and «شوف ادواتك» (production messages [74] to [76]); a tool that exists but is not visible

Rerun: same command with `J3-07` (`audit/runs/J3-07.txt`, token analysis `audit/runs/J3-07-discovery-tokens.txt`, gate trace `audit/runs/J3-07-gate-trace.txt`).

Production reference: owner «شوف ادواتك» (`audit/lonora-chat.md:592`); reply «ما في أداة حذف ظاهرة تحت هذا الاستعلام المبسّط. إذا تريد، أبحث مباشرة عن أداة **watch_cancel** وأجرّبها على المتابعات الحالية.» (`audit/lonora-chat.md:598`); the production run called `tool_environment {"query": "watch cancel task routines goals"}` and got `{"ok": true, "tools": [], "total": 0, ...}` (`audit/production-trace.md:235`).

Part A: reproduction of the production query. SCRIPTED `tool_environment {"query": "watch cancel task routines goals"}` -> `{"ok": true, "tools": [], "total": 0, ...}`: the same empty answer as production. Cause, from `audit/runs/J3-07-gate-trace.txt`: the query has five known words with these frequencies `{'cancel': 4, 'goals': 2, 'routines': 4, 'task': 11, 'watch': 10}`; the gate token is `goals`; five answerable words require coverage 3; the only tools containing `goals` are `trade_execute` and `agent_inspect`, covering 2 each, so nothing passes (`packages/tools/src/lonora_tools/tool_discovery.py:62-73`). The two-word query `cancel watch` returns `['watch_cancel', 'task_control', 'goal_control', 'trade_execute']` (`audit/runs/J3-07-discovery-tokens.txt`, first line). The same fixture gave `watch_cancel` for `cancel watch` and `[]` for the production phrasing.

Part B: a matrix of owner-style queries. The model turn is SCRIPTED; the ranking is the repo's own `search_definitions` over the live registry of 126 tools, run read-only by `audit/scripts/j3_discovery_tokens.py` (output `audit/runs/J3-07-discovery-tokens.txt`); the same queries were also sent through `tool_environment` in the run `audit/runs/J3-07.txt` (the raw run trims long results, so the lists here are the full ones):

| query | result |
|---|---|
| `cancel watch` | `watch_cancel, task_control, goal_control, trade_execute` |
| `ألغِ المراقبة` | `[]` |
| `stop monitoring gold` | `[]` ("gold" is in no tool text) |
| `run python calculation` | `[]` |
| `python` | `workspace_execute, skill_repository_inspect, skill_package_validate` |
| `calculate` | `chart_indicator` only |
| `run code` | `skill_view, workspace_update, market_opportunity_update, skill_repository_inspect` |
| `browser` | `routine_create, web_browse, chart_snapshot` (`web_browse` is only second) |
| `open website` | `web_fetch, web_browse` |
| `create skill` | `skill_package_create, skill_view, skills_list, skill_repository_inspect, skill_package_control, skill_package_validate, skill_package_import` |
| `send telegram message` | `[]` |
| `notify owner` | `owner_notify, owner_preferences_update` |
| `excel spreadsheet pdf` | `[]` |
| `install package` | `skill_view` |
| `weather`, `reminder`, `remind me tomorrow`, `تقرير` | `[]` |
| `schedule daily` | `routine_create` |
| `gold price`, `XAUUSD`, `symbol suffix` | `[]` |
| `connect MCP server credential`, `connect search credential card` | `owner_action_propose` |

Part C: calling a tool that is not in the native list, without discovery. SCRIPTED model turn: `watch_list {}` as a direct call (no `tool_call`, no `tool_environment`). RUNTIME result: `{"ok": true, "watches": []}`: it ran. The registry accepts any registered name for the run's scope and never compares it with the native list (`packages/tools/src/lonora_tools/registry.py:478-484`). Unknown or misspelt names fail: direct `run_python` -> `{"ok": false, "code": "tool_not_allowed", "recovery": {"category": "permission_denied", "next_action": "respect_scope", ...}}`; `tool_call {"name": "watch_lst"}` -> `{"ok": false, "code": "tool_call_target_unknown", ...}` (`packages/tools/src/lonora_tools/registry.py:222`); `tool_environment {"tool_name": "watch_lst"}` -> `tool_not_allowed` with `respect_scope` (`packages/tools/src/lonora_tools/registry.py:353`): a misspelling is reported as a permission problem.

What this means for the production «ما عندي أداة حذف»: the exact name `watch_cancel` was in the model's own system prompt (the inventory lists `market: ... watch_cancel, watch_create, watch_list ...`, `audit/runs/J3-01.txt`, injected as a system message by `packages/agent-runtime/src/lonora_agent/model_runtime.py:66-73`), the exact-name call would have run (Part C), and the discovery query that the model chose returned nothing (Part A). The inventory itself tells the model to inspect with `tool_environment` "before claiming an ability is absent" (`packages/tools/src/lonora_tools/registry.py:428-429`); the inspection it then ran was the one that returns `[]`. The model said it would "search for watch_cancel and try it" ([75]); after the owner said «جرب» it called `watch_create` with "cancel-test" instead (`audit/production-trace.md:236`). UNSURE: whether a real provider lets a model emit a call to a name outside its `tools` array; the runtime accepts it (Part C), the provider behaviour I did not test.

Class: recoverable-not-led (the capability exists, is named in the prompt and is reachable, but the discovery answer is empty and the recovery for a wrong name says "permission").

### J3-08: «ابعتلي رسالة على تيليجرام لما يخلص التحليل»

Rerun: same command with `J3-08` (`audit/runs/J3-08.txt`). Setup: default settings (no reach-me change, no Telegram integration).

Scripted turns and RUNTIME results:

1. SCRIPTED `tool_environment {"query": "send telegram message to owner"}` -> `{"ok": true, "tools": [], "total": 0, ...}`.
2. SCRIPTED `tool_environment {"query": "notify owner"}` -> `owner_notify`, whose description says "Delivery is in-app only for now." (`packages/tools/src/lonora_tools/incoming_call.py:132-133`).
3. SCRIPTED `owner_notify {"importance": "informational", "summary": "التحليل خلص", "dedupe_key": "analysis-done-1"}` -> `{"ok": true, "status": "not_shown_owner_preference", "attention_id": null, "delivery": "in_app", "note": "Shown in the app's notifications and this Agent's conversation. Off-app delivery (push, messaging channels) is not available yet.", "execution_authorized": false}`. The status says the alert was NOT shown, the note says "Shown".
4. The same with another `dedupe_key`: same result.
5. SCRIPTED `owner_notify {"importance": "important_change", ...}` -> `{"ok": true, "status": "pending", "attention_id": "c3c2ea23-...", "delivery": "in_app", "attention": {...}, "note": "Shown in the app's notifications and this Agent's conversation. ..."}`.
6. SCRIPTED `owner_attention_list {}` -> `{"ok": true, "attention": []}` (the list reads only `ready` items, `packages/tools/src/lonora_tools/incoming_call.py:110-113`; the new one was `pending`; I do not claim a defect here).

Root cause:

- There is no tool that sends to Telegram or any off-app channel. A Telegram integration type exists (`packages/contracts/src/lonora_contracts/integrations.py:15`) and a `TelegramAdapter.send` exists (`packages/adapters/src/lonora_adapters/channels/telegram.py:11`), but no tool in `packages/tools/src/lonora_tools/` uses either (grep for "telegram" in that directory finds only `capabilities.py`, where it is a "configured" flag at line 270). The policy says "It is in-app only for now" (`packages/agent-runtime/resources/system/lonora.md:206`). Dead end for «على تيليجرام»; the honest answer is "in the app only".
- The note is chosen by status: only `activity_only` and two agent-rule statuses get their own note; every other status, including `not_shown_owner_preference`, falls through to `NOTIFY_NOTE` (`packages/tools/src/lonora_tools/incoming_call.py:60-66`, text at `packages/tools/src/lonora_tools/incoming_call.py:29-31`). An `informational` alert is suppressed because the owner's attention policy defaults `informational` to `False` (`packages/contracts/src/lonora_contracts/attention.py:42`; the suppression at `packages/db/src/lonora_db/attention.py:147-148`) and the status is then `not_shown_owner_preference` (`packages/db/src/lonora_db/attention.py:461-466`). The model is thus told "Shown" for an alert the owner never sees, and `attention_id` is null so `owner_call_request` cannot follow.

Class: dead-end (no off-app channel) + bug (contradictory note; a model that trusts the note will tell the owner he was notified).

## 5. What I could not reproduce or confirm

- The text of the connect_credential and trust cards as the owner sees them (J3-03, J3-05): I raised them (`owner_must_tap: true`) but did not render them.
- A real container run (no Docker daemon): the output of `pip install` inside the networkless job, and the real analytics profile, are UNSURE.
- Real websites and real search results (sandbox has no DNS).
- Whether the web UI or the mobile app renders `tool.completed` codes to the owner; I read only the stream payloads (`audit/runs/J3-02b.txt`). The owner-visible text in every journey is the model's reply, which is scripted here.
- A real provider's behaviour when a model calls a tool name outside its `tools` array.

## 6. Money-safety check

Nothing in this area moves money. `mcp_execute` refuses financial tools (`packages/tools/src/lonora_tools/mcp.py:376-377`); the workspace has no broker access ("No broker mutation is possible through this path", `packages/tools/src/lonora_tools/workspace.py:116`); skills cannot grant authority (`packages/tools/src/lonora_tools/skills.py:124`, `:162`). The refusals I label "needed for safety": the networkless container, validation before activating code, trust cards for MCP servers and the secure credential form, no redirect-following without re-check, owner-only cards. The refusals that are not needed for safety are the ones that give the model nothing to do next: bare codes (M1), the empty discovery answer (M4), the wrong "uncertain" code (J3-01b), the misleading guard text (M6), the contradictory `owner_notify` note (J3-08).
