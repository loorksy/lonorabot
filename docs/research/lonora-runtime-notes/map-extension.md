# Map: self-extension, workspace host/sandbox, browser service

Repository `/home/user/lonorabot`, HEAD `9f5b1da`. Read-only audit. Every claim cites `path:line`
(paths relative to the repo root). Where a doc and the code disagree, the code is stated as the truth.

Scope: Part 1.5 (self-extension: skills, MCP, tools, account connection) and the workspace
host/sandbox + browser service parts of Part 1.8.

---

## 0. Summary table

| # | Capability | Verdict | Gate / reason (short) |
|---|---|---|---|
| 1 | Read/write files | Present and working, bounded | Per-agent DB snapshot: 128 files, 2 MiB each, 8 MiB total; text-only writes; exact-revision required |
| 2 | Run code / shell | Present but restricted, and off by default | Needs the optional workspace host (`LONORA_WORKSPACE_SOCKET`); Python 3.12 + `/bin/sh` only; no network; no pip/npm; 45 s / 256 MiB / 0.5 CPU / 32 PIDs |
| 3 | Drive a browser | Present but restricted, and off by default | Real headless Chromium, anonymous, GET/HEAD only, no login, fresh page per call, optional overlay (`LONORA_BROWSER_URL`) |
| 4 | Create a skill and use it | Present and working for instruction-only skills; restricted for skills with scripts | No owner approval step; scripts need the workspace host, `.py` only, exit code 0 smoke test |
| 5 | Add an MCP server | Present but restricted: owner must type the URL/token and trust the tools | Two owner cards (`connect_credential`, then `trust_source`); HTTPS only; stdio blocked; money tools never run |
| 6 | Add a new tool by itself | Absent | Tool registry is a static module list built at start |
| 7 | Connect an account from chat | Broker, MCP server, news feed, Brave Search, economic calendar: present via one card. Telegram/webhook: owner UI only. Email, personal calendar: absent | `CREDENTIAL_TARGETS` |

Cross-cutting mechanisms that produce "I can't / it did not work / code shown" in this area are in section 8.

---

## 1. Files: read/write, where, limits

**Verdict: present and working (bounded).** No host, container or overlay is needed for file tools.

Where files live: one row per agent in PostgreSQL holding the whole snapshot
(`packages/agent-runtime/src/lonora_agent/workspace_access.py:76-80`). There is no host filesystem
access; the policy says "Do not read arbitrary server files or claim access to the owner's device
filesystem." (`packages/agent-runtime/resources/system/lonora.md:609`).

Tools (`packages/tools/src/lonora_tools/workspace.py:80-122`): `workspace_inspect`, `workspace_read`,
`workspace_update`, `workspace_export`, `workspace_execute`. The four file tools use
`availability=workspace_available` (`packages/tools/src/lonora_tools/workspace.py:41-42`), and the
gateway always supplies a `RunWorkspaceAccess` object, with or without an executor
(`packages/gateway/src/lonora_gateway/runtime.py:107-109`), so file tools are available on every
deployment.

Limits:

- 128 files, 2 MiB per file, 8 MiB total (`packages/agent-runtime/src/lonora_agent/workspace.py:22-24`,
  enforced in `encode_snapshot` `packages/agent-runtime/src/lonora_agent/workspace.py:121-131`).
- Paths: relative, at most 256 characters and 8 components, no `.`/`..`, no backslash
  (`packages/agent-runtime/src/lonora_agent/workspace.py:105-118`).
- `workspace_update` writes UTF-8 text only: `files: dict[str, str]`, at most 128 entries
  (`packages/tools/src/lonora_tools/workspace.py:26-28`; encoded at
  `packages/agent-runtime/src/lonora_agent/workspace_access.py:224`). Binary files can only be produced
  by a command run in the sandbox.
- `workspace_read`: at most 16000 characters per call, default 8000
  (`packages/tools/src/lonora_tools/workspace.py:20-23`); a non-UTF-8 file fails with
  `workspace_file_binary` (`packages/agent-runtime/src/lonora_agent/workspace_access.py:208-211`).
- Every read, write, run and export must name the exact current `revision`; a stale number fails with
  `workspace_revision_conflict` (`packages/agent-runtime/src/lonora_agent/workspace_access.py:127-131`,
  `packages/agent-runtime/src/lonora_agent/workspace_access.py:203-204`). This code is classified
  `version_conflict` / `reload_authoritative_state` (`packages/agent-runtime/src/lonora_agent/environment.py:46-47`),
  so the model is told to re-inspect: a recoverable loop, not a stop.
- A paused agent cannot write (`tool_not_allowed`), and a helper (subagent) can only execute, not
  update (`packages/agent-runtime/src/lonora_agent/workspace_access.py:55-58`;
  `packages/tools/src/lonora_tools/base.py:50`).
- Export to the owner as a chat attachment: only `.txt .md .csv .tsv .json` and
  `.png .jpg .jpeg .webp .gif` (`packages/agent-runtime/src/lonora_agent/workspace_artifacts.py:21-34`);
  anything else (PDF, XLSX, HTML, SVG) fails with `workspace_export_format_unsupported`
  (`packages/agent-runtime/src/lonora_agent/workspace_artifacts.py:50`).

Exposure: none of the workspace tools is in an eager profile (no `eager=` in
`packages/tools/src/lonora_tools/workspace.py:80-122`), so they are not in the native tool list of a
Run unless remembered; the model must find them in the capability inventory and call them through
`tool_call` (`packages/tools/src/lonora_tools/registry.py:270-288`,
`packages/tools/src/lonora_tools/registry.py:406-412`).

Failure outcomes (the model gets `{"ok": false, "code": ...}` plus a `recovery` block, see section 8):
`workspace_unconfigured` (`packages/tools/src/lonora_tools/workspace.py:56`),
`workspace_scope_mismatch` (`packages/agent-runtime/src/lonora_agent/workspace_access.py:54`),
`tool_not_allowed` (`packages/agent-runtime/src/lonora_agent/workspace_access.py:58`),
`workspace_busy` (`packages/agent-runtime/src/lonora_agent/workspace_access.py:123`,
`packages/agent-runtime/src/lonora_agent/workspace_access.py:129`),
`workspace_revision_conflict` (`packages/agent-runtime/src/lonora_agent/workspace_access.py:131`),
`workspace_operation_conflict` (`packages/agent-runtime/src/lonora_agent/workspace_access.py:121`),
`workspace_read_invalid` (`packages/agent-runtime/src/lonora_agent/workspace_access.py:199`),
`workspace_file_not_found` (`packages/agent-runtime/src/lonora_agent/workspace_access.py:207`),
`workspace_file_binary` (`packages/agent-runtime/src/lonora_agent/workspace_access.py:211`),
`workspace_update_conflict` (`packages/agent-runtime/src/lonora_agent/workspace_access.py:228`),
`workspace_path_unsafe` (`packages/agent-runtime/src/lonora_agent/workspace.py:117`),
`workspace_snapshot_too_large` / `workspace_file_too_large`
(`packages/agent-runtime/src/lonora_agent/workspace.py:124`,
`packages/agent-runtime/src/lonora_agent/workspace.py:128`),
export: `workspace_export_format_invalid`, `workspace_export_format_unsupported`,
`workspace_export_filename_invalid`, `workspace_export_format_mismatch`, `workspace_export_conflict`,
`artifact_file_missing`, `artifact_integrity_failed`
(`packages/agent-runtime/src/lonora_agent/workspace_artifacts.py:48`,
`packages/agent-runtime/src/lonora_agent/workspace_artifacts.py:50`,
`packages/agent-runtime/src/lonora_agent/workspace_artifacts.py:73`,
`packages/agent-runtime/src/lonora_agent/workspace_artifacts.py:82`,
`packages/agent-runtime/src/lonora_agent/workspace_artifacts.py:102`,
`packages/agent-runtime/src/lonora_agent/workspace_artifacts.py:58`,
`packages/agent-runtime/src/lonora_agent/workspace_artifacts.py:64`).

---

## 2. Code / shell execution

**Verdict: present but restricted; absent on a default installation.**

### 2.1 What runs, and in what sandbox

- Tool: `workspace_execute`, description (verbatim): "Run a shell terminal command or Python analysis
  from an exact workspace revision in a resource-bounded, networkless container without host files or
  credentials. Returns actual exit status, bounded output and new file revision. No broker mutation is
  possible through this path. Interrupted operations are not automatically rerun."
  (`packages/tools/src/lonora_tools/workspace.py:115-116`).
- The command is passed to `/bin/sh -c` inside a fresh Docker container, as UID 10001, with a fixed
  clean environment (`packages/agent-runtime/src/lonora_agent/workspace.py:389-409`).
- Languages: whatever the administrator-pinned image contains. The two shipped images are both
  `python:3.12-slim-bookworm` (`infra/analysis/Dockerfile:3`, `infra/analysis/analytics.Dockerfile:3`).
  The minimal one adds nothing; the analytics one adds NumPy, pandas, SciPy, matplotlib and Pillow from
  a hash-locked wheel set (`infra/analysis/analytics.Dockerfile:7`,
  `infra/analysis/analytics.requirements.lock:7-15`). No Node.js, npm or other runtime is installed by
  either Dockerfile. UNSURE: which of the two images a given production host pins; that is the
  administrator's `LONORA_ANALYSIS_IMAGE` value (`infra/analysis/lonora-analysis.service:14`).
- Network: `--network=none` (`packages/agent-runtime/src/lonora_agent/workspace.py:207`), proxy
  variables emptied (`packages/agent-runtime/src/lonora_agent/workspace.py:234`), and the sandbox is
  verified to have only the `lo` interface before the command runs
  (`packages/agent-runtime/src/lonora_agent/workspace.py:332-342`).
- Package installation: impossible at run time. No network, read-only root filesystem
  (`packages/agent-runtime/src/lonora_agent/workspace.py:211`), image never pulled
  (`packages/agent-runtime/src/lonora_agent/workspace.py:200`). The policy tells the model so: "Never
  run source setup hooks or dependency downloads in analytical jobs. Only administrator-reviewed
  immutable image dependencies are available; missing imports are real failures."
  (`packages/agent-runtime/resources/system/lonora.md:477`). A new library needs an administrator image
  rebuild (`infra/analysis/build-analytics.sh:2`, `infra/analysis/build-analytics.sh:15-16`).
- Scratch space: `/work` 32 MiB and `/tmp` 8 MiB tmpfs, both `noexec`
  (`packages/agent-runtime/src/lonora_agent/workspace.py:230-233`). `noexec` means a file written
  there cannot be executed directly; it must be passed to an interpreter (`python3 x.py`, `sh x.sh`).
- Limits: 256 MiB memory, no extra swap, 32 processes, 0.5 CPU, 128 open files
  (`packages/agent-runtime/src/lonora_agent/workspace.py:27-29`,
  `packages/agent-runtime/src/lonora_agent/workspace.py:216-225`); all capabilities dropped except KILL
  for the root control step, `no-new-privileges` (`packages/agent-runtime/src/lonora_agent/workspace.py:212-214`).
- Time: `deadline_seconds` default 30, maximum 45 (`packages/tools/src/lonora_tools/workspace.py:33`).
  The deadline covers container creation, start, isolation check, file bootstrap, the command, process
  cleanup and file export together (`packages/agent-runtime/src/lonora_agent/workspace.py:364-433`), so
  the command itself has less than the stated number of seconds.
- Output: stdout and stderr 128 KiB each (`packages/agent-runtime/src/lonora_agent/workspace.py:26`).
  Exceeding it is not truncated; the whole run fails with `workspace_output_too_large`
  (`packages/agent-runtime/src/lonora_agent/workspace.py:262-265`,
  `packages/agent-runtime/src/lonora_agent/workspace.py:284-287`) and no files are published
  (`packages/agent-runtime/src/lonora_agent/workspace_access.py:412-422`).
- Command text at most 32768 bytes (`packages/tools/src/lonora_tools/workspace.py:32`).
- Concurrency: the host runs 2 jobs at once by default (`packages/agent-runtime/src/lonora_agent/workspace_host.py:26`,
  `packages/agent-runtime/src/lonora_agent/workspace_host.py:154`); a third request is refused at once
  with `workspace_busy`, there is no queue (`packages/agent-runtime/src/lonora_agent/workspace_host.py:38-39`,
  `packages/agent-runtime/src/lonora_agent/workspace_client.py:94-95`). One agent can have only one
  active operation (`packages/agent-runtime/src/lonora_agent/workspace_access.py:127-129`).
- No persistent processes: the container is force-removed after every command
  (`packages/agent-runtime/src/lonora_agent/workspace.py:436-444`); only files under `/work` survive,
  re-validated to the limits in section 1 (`packages/agent-runtime/src/lonora_agent/workspace.py:85-99`).
- A non-zero exit code is returned as a normal result with `exit_code`, `stdout`, `stderr` and the new
  file list (`packages/agent-runtime/src/lonora_agent/workspace_access.py:398-405`); it is not a tool
  failure.

All of these isolation rules are **needed for safety** (no broker credentials, no network, no host
files: `packages/agent-runtime/resources/system/lonora.md:581`). They do not have to be relaxed to fix
the owner's complaint; what matters is whether the capability is installed at all and what the model
is told when it is not.

### 2.2 How the host runs

- A separate root systemd service on the server, not a container of the application
  (`infra/analysis/lonora-analysis.service:8`, `infra/analysis/lonora-analysis.service:14`), limited to
  Unix sockets and 512 MiB (`infra/analysis/lonora-analysis.service:31`,
  `infra/analysis/lonora-analysis.service:33`). It talks to Docker on the fixed local socket
  (`packages/agent-runtime/src/lonora_agent/workspace.py:250-253`).
- The application reaches it only through a Unix socket whose path is `LONORA_WORKSPACE_SOCKET`, set
  by an **optional** Compose overlay (`infra/analysis/compose.workspace.yml:12`,
  `infra/analysis/compose.workspace.yml:24`).
- The installer's overlay list is empty by default (`infra/compose/install.sh:28`); the workspace
  overlay is added only with `--overlay` (`infra/compose/install.sh:16-17`). The base production
  Compose file sets no workspace socket (`infra/compose/docker-compose.prod.yml:30-41`). The developer
  `docker-compose.yml` runs only PostgreSQL (`docker-compose.yml:1-17`).
- The installer does not install the systemd service; it only warns when the socket is missing
  (`infra/compose/install.sh:133-134`).

So on a default installation the agent cannot run any code.

### 2.3 What happens when the host is not configured or not running

Three different states, three different codes:

1. **Socket path not configured** (default install). `execution_available` returns
   `workspace_execution_unconfigured` (`packages/tools/src/lonora_tools/workspace.py:45-51`). The tool
   is removed from the native list (`packages/tools/src/lonora_tools/registry.py:288`) and listed in the
   prompt as `unavailable_now (...): workspace_execute=workspace_execution_unconfigured`
   (`packages/tools/src/lonora_tools/registry.py:442-444`). A call still fails with the same code
   (`packages/agent-runtime/src/lonora_agent/workspace_access.py:350-351`). The code ends in
   `_unconfigured`, so the recovery hint is `not_configured` / `inspect_authorized_alternative`
   (`packages/agent-runtime/src/lonora_agent/environment.py:74-79`). `capabilities_list` reports
   `workspace_execution: not_set_up` with the guidance "not_set_up: this server lacks it; say so
   plainly." (`packages/tools/src/lonora_tools/capabilities.py:90`,
   `packages/tools/src/lonora_tools/capabilities.py:303`). There is no card and no owner action that
   fixes it; the owner is a non-technical person and the fix is a server administration task.
2. **Socket path configured but the service is down** (after a reboot, or the service stopped; the
   overlay comment itself describes this case, `infra/analysis/compose.workspace.yml:1-6`). The
   availability check only tests that an executor object exists
   (`packages/agent-runtime/src/lonora_agent/workspace_access.py:138-141`), so the tool is presented as
   available. The call then fails on the socket connection with `workspace_execution_uncertain`
   (`packages/agent-runtime/src/lonora_agent/workspace_client.py:111-114`). **Present but unreliable:**
   the code says "uncertain" for a command that never started, and it is not in any recovery class, so
   the hint is the default `terminal_domain_failure` / `alternate_route`
   (`packages/agent-runtime/src/lonora_agent/environment.py:36-37`). The overlay comment says the tools
   "report the host unavailable" (`infra/analysis/compose.workspace.yml:4`); the code actually reports
   `workspace_execution_uncertain`. Code wins.
3. **Docker/daemon error inside the host**: `workspace_backend_unavailable`
   (`packages/agent-runtime/src/lonora_agent/workspace.py:311`,
   `packages/agent-runtime/src/lonora_agent/workspace_host.py:95-99`) or
   `workspace_isolation_unavailable` (`packages/agent-runtime/src/lonora_agent/workspace.py:331`,
   `packages/agent-runtime/src/lonora_agent/workspace.py:342`).

The host's status code is discarded by the client: every controlled host failure is re-raised with
status 409 and the bare code (`packages/agent-runtime/src/lonora_agent/workspace_client.py:108-110`).

Other execute failures: `workspace_command_invalid`
(`packages/agent-runtime/src/lonora_agent/workspace_access.py:335`), `workspace_timeout`
(`packages/agent-runtime/src/lonora_agent/workspace.py:434-435`), `workspace_output_too_large`
(above), `workspace_busy` (above), `workspace_profile_changed` / `workspace_profile_invalid`
(`packages/agent-runtime/src/lonora_agent/workspace.py:352-353`,
`packages/agent-runtime/src/lonora_agent/workspace_access.py:354-358`),
`workspace_operation_superseded` (`packages/agent-runtime/src/lonora_agent/workspace_access.py:386-387`),
`workspace_execution_interrupted` (`packages/agent-runtime/src/lonora_agent/workspace_access.py:102`,
`packages/agent-runtime/src/lonora_agent/workspace_access.py:413-415`),
`workspace_file_unsafe` / `workspace_snapshot_too_large` from the exporter when the command left a
symlink, an oversized file or more than 128 files (`packages/agent-runtime/src/lonora_agent/workspace.py:89-99`;
these surface as `workspace_backend_unavailable` because the exporter runs with `check=True`,
`packages/agent-runtime/src/lonora_agent/workspace.py:308-311`,
`packages/agent-runtime/src/lonora_agent/workspace.py:416-425`),
`workspace_request_too_large`, `workspace_request_invalid`, `workspace_request_timeout`
(`packages/agent-runtime/src/lonora_agent/workspace_host.py:47`,
`packages/agent-runtime/src/lonora_agent/workspace_host.py:76`,
`packages/agent-runtime/src/lonora_agent/workspace_host.py:94`),
`workspace_response_too_large`, `workspace_response_invalid`
(`packages/agent-runtime/src/lonora_agent/workspace_client.py:93`,
`packages/agent-runtime/src/lonora_agent/workspace_client.py:138`).

None of `workspace_busy`, `workspace_timeout`, `workspace_backend_unavailable`,
`workspace_execution_uncertain` is in the transient set
(`packages/core/src/lonora_core/runtime_failure.py:10-21`), so none is auto-retried and all get the
default hint `alternate_route`. `workspace_busy` in particular is a momentary condition (two other
jobs running) that a short wait would clear.

### 2.4 Prompt text that discourages using the shell

- Research chapter: "Do not start OAuth, browse a signed-in desktop or invoke shell commands; servers
  and credentials come only through those cards." (`packages/agent-runtime/resources/system/lonora.md:566`).
- Core chapter: "Analytical files are scoped to this Agent. Shell and Python analysis require
  execution_configured from workspace_inspect; an unconfigured backend cannot run commands. There is no
  host filesystem, desktop mouse or unrestricted browser capability."
  (`packages/agent-runtime/resources/system/lonora.md:157`).
- Tool description: "Run a shell terminal command or Python analysis ..."
  (`packages/tools/src/lonora_tools/workspace.py:116`).

Line 566 is meant for external connections but read literally it forbids the same thing the tool
description offers. A model that reads both can refuse a computation it is able to do.

### 2.5 Doc vs code

- `docs/analytical-workspace.md:189-190` says the overlay "binds only the socket directory read-only and
  refuses to create a missing host path". The overlay sets `create_host_path: true`
  (`infra/analysis/compose.workspace.yml:19`, `infra/analysis/compose.workspace.yml:31`). Code wins: the
  path is created.
- `docs/analytical-workspace.md:19` says the host bridge is "now installed and verified on the production
  VPS", while `docs/analytical-workspace.md:163` says it "has **not** been installed or verified there".
  The document contradicts itself; neither statement is checkable from the repository. UNSURE: whether
  the owner's server runs the host today.

---

## 3. Browser

**Verdict: present but restricted (real browser, anonymous, read-only); absent on a default installation.**

- Real browser, not fetch-only: headless Chromium driven by Playwright with JavaScript enabled
  (`packages/tools/src/lonora_tools/browser_service.py:76-92`,
  `packages/tools/src/lonora_tools/browser_service.py:118-124`). Chromium is installed in the
  application image (`Dockerfile:18`).
- Chromium itself has no network: it is launched with an unreachable proxy
  (`packages/tools/src/lonora_tools/browser_service.py:82`) and every request is fetched by the server's
  public-address-checked reader and handed back to the page
  (`packages/tools/src/lonora_tools/browser_service.py:150-186`).
- Only `GET`/`HEAD`, and only document/script/stylesheet/xhr/fetch resources
  (`packages/tools/src/lonora_tools/browser_service.py:43`,
  `packages/tools/src/lonora_tools/browser_service.py:141-149`). Images, fonts and media are blocked;
  WebSockets are closed (`packages/tools/src/lonora_tools/browser_service.py:112-113`,
  `packages/tools/src/lonora_tools/browser_service.py:216`). A page whose data arrives by `POST` (many
  search forms, most single-page apps) or by WebSocket (live price pages) cannot be read.
- Logins: not possible. Filling a `password`, `file` or `hidden` input raises `browser_action_failed`
  (`packages/tools/src/lonora_tools/browser_service.py:266-267`), `POST` is blocked, and each call uses a
  new context with no saved profile or cookies (`packages/tools/src/lonora_tools/browser_service.py:118-124`,
  closed at `packages/tools/src/lonora_tools/browser_service.py:307`). Tool description (verbatim):
  "Each call starts a fresh page, so supply the URL and complete action sequence. Only GET/HEAD requests
  are allowed; no login, credentials, form submissions using POST, downloads or private networks."
  (`packages/tools/src/lonora_tools/browser.py:106-108`). Policy: "It does not use the owner's signed-in
  browser, saved cookies, credentials or local desktop." (`packages/agent-runtime/resources/system/lonora.md:547`)
  and "external writes, purchases, trading and login are unsupported"
  (`packages/agent-runtime/resources/system/lonora.md:548`). **Needed for safety** (no trading or
  purchases through a browser; no secrets in a browser).
- Actions: `click`, `fill`, `scroll`, `wait`, at most 8 per call
  (`packages/tools/src/lonora_tools/browser.py:17`, `packages/tools/src/lonora_tools/browser.py:34`).
- Limits per call: 80 requests, 16 MiB transferred, 6 redirects
  (`packages/tools/src/lonora_tools/browser_service.py:40-42`); 40 s for the whole render
  (`packages/tools/src/lonora_tools/browser_service.py:318`); navigation timeout 15 s, action timeout
  4 s (`packages/tools/src/lonora_tools/browser_service.py:218-219`); each upstream fetch 8 s
  (`packages/security/src/lonora_security/public_http.py:64`). Returned text is capped at 24000
  characters and 48000 bytes, 60 links, 40 controls
  (`packages/tools/src/lonora_tools/browser_service.py:289-291`,
  `packages/tools/src/lonora_tools/browser_service.py:52`). No screenshot is returned; the result is text,
  links and control selectors only (`packages/tools/src/lonora_tools/browser_service.py:295-300`).
- Capacity: 2 pages at a time for the whole server; a third call waits 2 s then fails `browser_busy`
  (`packages/tools/src/lonora_tools/browser_service.py:94`,
  `packages/tools/src/lonora_tools/browser_service.py:313-316`).
- Deployment: an **optional** overlay (`infra/research/compose.research.yml:1-2`) starts the `browser`
  service from the application image with a read-only filesystem, all capabilities dropped, 768 MiB,
  0.5 CPU, 256 PIDs, on its own bridge network with no database or secrets
  (`infra/research/compose.research.yml:42-65`). `LONORA_BROWSER_URL` is set on the `gateway` service
  only (`infra/research/compose.research.yml:6-9`). The installer's overlay list is empty by default
  (`infra/compose/install.sh:28`).
- UNSURE: the owner-facing `/capabilities` route reads `browser_url` from the API process settings
  (`apps/api/src/lonora_api/routes/capabilities.py:25`), and the overlay does not set it on the `api`
  service. Unless `.env` also sets it, the owner's Capabilities page can show the browser as not set up
  while agent Runs in the gateway have it. Not confirmed against a running deployment.

When not configured: `browser_available` returns `browser_unconfigured`
(`packages/tools/src/lonora_tools/browser.py:37-38`); the tool leaves the native list and appears under
`unavailable_now` (`packages/tools/src/lonora_tools/registry.py:288`,
`packages/tools/src/lonora_tools/registry.py:442`); a call fails with `browser_unconfigured`
(`packages/tools/src/lonora_tools/browser.py:42-43`); `capabilities_list` says
`web_browse: not_set_up` (`packages/tools/src/lonora_tools/capabilities.py:86`).

Fetch-only alternative that needs no overlay: `web_fetch`, "Read or fetch a public HTTPS URL ..."
(`packages/tools/src/lonora_tools/search.py:326-327`), eager for the `research` profile only
(`packages/tools/src/lonora_tools/search.py:331`).

Failure outcomes of `web_browse` as the model sees them
(`packages/tools/src/lonora_tools/browser.py:59-85`):

| Model sees | Cause |
|---|---|
| `browser_unconfigured` | no `LONORA_BROWSER_URL` (`packages/tools/src/lonora_tools/browser.py:43`) |
| `tool_read_timeout` | HTTP timeout to the service, or the service said `browser_busy` / `browser_timeout` (`packages/tools/src/lonora_tools/browser.py:59-60`, `packages/tools/src/lonora_tools/browser.py:83-84`) |
| `tool_connection_failure` | the service is unreachable, or the page's own fetch failed (`packages/tools/src/lonora_tools/browser.py:61-62`, `packages/tools/src/lonora_tools/browser_service.py:193-197`) |
| `browser_source_unavailable` | main page status >= 400, non-text document, download, too many redirects (`packages/tools/src/lonora_tools/browser_service.py:166-167`, `packages/tools/src/lonora_tools/browser_service.py:178-185`) |
| `browser_action_failed` | a click/fill did not work, or a password field was targeted (`packages/tools/src/lonora_tools/browser_service.py:267`, `packages/tools/src/lonora_tools/browser_service.py:324-325`) |
| `unsafe_remote_url`, `private_remote_address_forbidden`, `remote_host_unavailable` | URL safety (`packages/tools/src/lonora_tools/browser.py:78-80`) |
| `browser_unavailable` | any other service error, including `research_source_too_large`, which is not in the permitted set (`packages/tools/src/lonora_tools/browser.py:73-85`, `packages/tools/src/lonora_tools/browser_service.py:158`) |
| `browser_response_invalid` | malformed or oversized (>128 KiB) reply (`packages/tools/src/lonora_tools/browser.py:55-56`) |

`tool_read_timeout` and `tool_connection_failure` are transient codes
(`packages/core/src/lonora_core/runtime_failure.py:17-18`), so for this read-only tool they are marked
`safe_to_retry` (`packages/agent-runtime/src/lonora_agent/environment.py:92`) and the runtime schedules a
retry of the same call (`packages/agent-runtime/src/lonora_agent/tool_block.py:309-328`). Mapping "busy" to "timeout" hides the real reason (two other pages rendering).

Policy on failure: "If a search/browser backend is unavailable, do not repeat it under a new query
pretending it worked." (`packages/agent-runtime/resources/system/lonora.md:553`) and "If a service is
unavailable, state the practical access limitation and the single supported next step."
(`packages/agent-runtime/resources/system/lonora.md:568`). The second line instructs the model to stop
and report after one failure in this area, rather than try `web_fetch` or `web_search` first.

---

## 4. Creating a skill and using it

**Verdict: present and working without any owner approval for instruction-only skills; present but
restricted for skills that contain scripts (needs the workspace host, Python only).**

### 4.1 Lifecycle of an agent-authored skill

1. Write `<dir>/SKILL.md` (and optional scripts) with `workspace_update`. `SKILL.md` must start with
   YAML frontmatter whose `name` equals the skill id and a 1-1000 character `description`, plus a
   non-empty body (`packages/agent-runtime/src/lonora_agent/skills/document.py:12-37`).
2. `skill_package_create` (description: "Register a reusable analytical Skill from this Agent's exact
   current workspace revision. ... create disabled, then validate exact utilities before activation."
   `packages/tools/src/lonora_tools/skills.py:123-124`). It copies the directory to
   `skills/<id>/<version>/` and creates the catalog row with `enabled=False`, activation mode
   `explicit`, source `installed` (`packages/agent-runtime/src/lonora_agent/skills/packages.py:208-212`,
   `packages/agent-runtime/src/lonora_agent/skills/packages.py:128-143`). Result status:
   `disabled_pending_validation` (`packages/agent-runtime/src/lonora_agent/skills/lifecycle.py:326`).
   The model must also supply a `review` object with four prose fields
   (`packages/tools/src/lonora_tools/skills.py:27-35`, `packages/tools/src/lonora_tools/skills.py:49-55`).
3. For every script: `skill_package_validate` runs `python3 <utility> <args>` in the sandbox for 30 s
   (`packages/agent-runtime/src/lonora_agent/skills/lifecycle.py:404-410`). Only `.py` is accepted
   (`packages/agent-runtime/src/lonora_agent/skills/lifecycle.py:399-400`).
4. `skill_package_control` with `action="activate"`
   (`packages/agent-runtime/src/lonora_agent/skills/lifecycle.py:495-500`). For a skill with scripts,
   every script must have an exit-0 receipt from the image the host runs now
   (`packages/agent-runtime/src/lonora_agent/skills/packages.py:71-91`,
   `packages/agent-runtime/src/lonora_agent/skills/lifecycle.py:498-499`).
5. Use: `skill_view` reads the body. The catalog is read live inside the same Run
   (`packages/agent-runtime/src/lonora_agent/skills/access.py:72-76`,
   `packages/agent-runtime/src/lonora_agent/skills/access.py:287-288`), so the skill is usable in the
   same Run that created it. In later Runs it is listed in the `<skill_runtime>` prompt section with the
   label `(agent_authored)` (`packages/agent-runtime/src/lonora_agent/context/skills.py:237-248`,
   `packages/agent-runtime/src/lonora_agent/skills/provenance.py:18`). Because its activation mode is
   `explicit`, it is never injected automatically; the model must choose to call `skill_view`
   (`packages/agent-runtime/src/lonora_agent/skills/resolver.py:103-104`).

**Approval steps for an agent-authored skill: none.** No card, no owner tap. The only owner controls
are after the fact: disable, delete or revoke a version in the owner UI/API
(`apps/api/src/lonora_api/routes/agent_skills.py:254-260`), and the owner cannot enable or rewrite a
managed package through the generic route (`skill_package_lifecycle_required`,
`apps/api/src/lonora_api/routes/agent_skills.py:105-111`).

### 4.2 Importing a skill from GitHub

`skill_repository_inspect` then `skill_package_import`
(`packages/tools/src/lonora_tools/skills.py:130-131`, `packages/tools/src/lonora_tools/skills.py:171-172`).
Only `https://github.com/<owner>/<repo>` URLs (`packages/agent-runtime/src/lonora_agent/skills/repository.py:27-39`)
and a full 40-character commit (`packages/tools/src/lonora_tools/skills.py:40`). Approval: every owner
starts with all of `github.com` trusted (`packages/db/src/lonora_db/trusted_sources.py:32`,
`packages/db/src/lonora_db/trusted_sources.py:284-293`), so the import is silent. Only if the owner
removed that default does the import return `status: owner_trust_required` and raise one `trust_source`
card (`packages/agent-runtime/src/lonora_agent/skills/lifecycle.py:216-241`); after the owner taps
Trust, a continuation Run is started with a fixed prompt
(`packages/db/src/lonora_db/owner_actions.py:2039-2073`).

### 4.3 Gates and where it breaks

- **Scripts need the workspace host.** `skill_package_validate` has `availability=execution_available`
  (`packages/tools/src/lonora_tools/skills.py:142`). On a default install (section 2.2) a skill with any
  script can be created but never validated, so never activated:
  `skill_package_validation_required` (`packages/agent-runtime/src/lonora_agent/skills/packages.py:79`).
- **Non-Python scripts block activation for ever.** Files ending `.sh .bash .js .ts` are counted as
  utilities (`packages/agent-runtime/src/lonora_agent/skills/repository.py:24`,
  `packages/agent-runtime/src/lonora_agent/skills/repository.py:95`), cannot be validated
  (`packages/agent-runtime/src/lonora_agent/skills/lifecycle.py:399-400`), and activation requires a
  receipt for every utility (`packages/agent-runtime/src/lonora_agent/skills/packages.py:76-79`). The
  doc agrees: "Unsupported non-Python utilities prevent activation."
  (`docs/skill-executable-lifecycle.md:50`). The model only learns this from the
  `unsupported_utilities` field of the result (`packages/agent-runtime/src/lonora_agent/skills/lifecycle.py:191`).
- **An active skill with scripts disappears when the host is down or its image changed.** Each Run
  re-checks the host profile; a failure marks the skill rejected with the host's code
  (`packages/agent-runtime/src/lonora_agent/context/skills.py:104-117`). The same happens while any
  workspace command is running (`packages/agent-runtime/src/lonora_agent/context/skills.py:100-101`) or
  if any packaged file was changed in the workspace
  (`packages/agent-runtime/src/lonora_agent/context/skills.py:103`,
  `packages/agent-runtime/src/lonora_agent/skills/packages.py:99-104`). `skills_list` then shows
  `available: false` with the code (`packages/agent-runtime/src/lonora_agent/skills/access.py:266-268`).
  **Present but unreliable** for script skills; instruction-only skills are not affected
  (`packages/agent-runtime/src/lonora_agent/skills/packages.py:73-74`).
- Skill files share the agent's 128-file / 8 MiB workspace (section 1); a package is at most 64 files,
  256 KiB per file, 1 MiB total (`packages/agent-runtime/src/lonora_agent/skills/packages.py:184-187`);
  at most 8 versions per skill (`packages/agent-runtime/src/lonora_agent/skills/lifecycle.py:120-121`);
  active instruction budget 16000 characters (`packages/agent-runtime/src/lonora_agent/skills/access.py:29`).
- A skill is text. It cannot add a tool or permission: "Instructions are bounded and cannot grant tools,
  permissions, or financial authority." (`packages/tools/src/lonora_tools/skills.py:162`). **Needed for
  safety.**
- A helper (subagent) cannot create, import, validate or control skills: these are not read-only and
  not in `HELPER_EFFECTS` (`packages/tools/src/lonora_tools/base.py:50`,
  `packages/tools/src/lonora_tools/base.py:97`).
- Exposure: only `skills_list` and `skill_view` are eager
  (`packages/tools/src/lonora_tools/skills.py:158`, `packages/tools/src/lonora_tools/skills.py:168`);
  the four `skill_package_*` tools and `skill_repository_inspect` are reachable only through
  `tool_call`.
- Prompt: "Do not edit built-in policies or promise autonomous self-improvement of the deployed system."
  (`packages/agent-runtime/resources/system/lonora.md:480`). Nothing in the prompt tells the model
  *when* to create a skill (for example after the owner corrects it, as with «ضع حرف m يعني XAUUSDM»);
  line 474 only says *how*
  (`packages/agent-runtime/resources/system/lonora.md:474`).

### 4.4 Failure codes (model sees the bare code)

`skill_runtime_unavailable` (`packages/tools/src/lonora_tools/skills.py:78`);
create/import: `workspace_revision_conflict` (`packages/agent-runtime/src/lonora_agent/skills/lifecycle.py:352`),
`skill_package_document_missing`, `skill_package_too_large`, `skill_package_file_too_large`,
`skill_package_nested_unsupported` (`packages/agent-runtime/src/lonora_agent/skills/packages.py:183-189`),
`skill_package_binary_unsupported` (`packages/agent-runtime/src/lonora_agent/skills/packages.py:151-153`),
`skill_frontmatter_invalid`, `skill_document_too_large`
(`packages/agent-runtime/src/lonora_agent/skills/packages.py:192-196`),
`version_conflict`, `skill_package_version_limit`, `skill_package_version_immutable`,
`skill_version_revoked` (`packages/agent-runtime/src/lonora_agent/skills/lifecycle.py:114-137`),
`skill_package_identity_conflict` (`packages/agent-runtime/src/lonora_agent/skills/lifecycle.py:46`),
`skill_package_content_changed` (`packages/agent-runtime/src/lonora_agent/skills/lifecycle.py:86`),
`skill_package_source_changed` (`packages/agent-runtime/src/lonora_agent/skills/packages.py:104`),
`workspace_runtime_unavailable` (`packages/agent-runtime/src/lonora_agent/skills/lifecycle.py:210`);
repository: `skill_repository_url_invalid` (`packages/agent-runtime/src/lonora_agent/skills/repository.py:39`),
`skill_repository_ref_invalid`, `skill_repository_revision_invalid`, `skill_repository_unavailable`
(`packages/agent-runtime/src/lonora_agent/skills/repository.py:206`,
`packages/agent-runtime/src/lonora_agent/skills/repository.py:224`,
`packages/agent-runtime/src/lonora_agent/skills/repository.py:233`),
`skill_repository_not_found`, `skill_repository_rate_limited`, `skill_repository_access_denied`,
`skill_repository_archive_too_large`
(`packages/agent-runtime/src/lonora_agent/skills/repository.py:242-254`),
`skill_package_document_incompatible` (`packages/agent-runtime/src/lonora_agent/skills/packages.py:284`);
validate/control: `skill_not_found`, `skill_package_utility_unsupported`,
`skill_package_validation_interrupted`, `skill_package_validation_required`,
`skill_package_version_not_found`, `skill_package_action_invalid`
(`packages/agent-runtime/src/lonora_agent/skills/lifecycle.py:395`,
`packages/agent-runtime/src/lonora_agent/skills/lifecycle.py:400`,
`packages/agent-runtime/src/lonora_agent/skills/lifecycle.py:412`,
`packages/agent-runtime/src/lonora_agent/skills/lifecycle.py:499`,
`packages/agent-runtime/src/lonora_agent/skills/lifecycle.py:491`,
`packages/agent-runtime/src/lonora_agent/skills/lifecycle.py:522`);
a validation whose script exits non-zero is a normal result with `status: smoke_test_failed`
(`packages/agent-runtime/src/lonora_agent/skills/lifecycle.py:446`);
view: the per-skill rejection code, or `skill_unavailable`, `skill_snapshot_invalid`,
`skill_snapshot_budget_exceeded`, `skill_view_identity_conflict`
(`packages/agent-runtime/src/lonora_agent/skills/access.py:96`,
`packages/agent-runtime/src/lonora_agent/skills/access.py:112`,
`packages/agent-runtime/src/lonora_agent/skills/access.py:117`,
`packages/agent-runtime/src/lonora_agent/skills/access.py:128`,
`packages/agent-runtime/src/lonora_agent/skills/access.py:286`).

Every code ending in `_not_found` is given the hint `not_found` / `inspect_existing_state`
(`packages/agent-runtime/src/lonora_agent/environment.py:80-81`); everything else in this list gets the
default `terminal_domain_failure` / `alternate_route`
(`packages/agent-runtime/src/lonora_agent/environment.py:36-37`).

---

## 5. Adding an MCP server

**Verdict: present but restricted. The agent cannot add a server by itself. It can ask with a card; the
owner must type the server's address (and token) and then approve its tools on a second card.**

Steps and gates:

1. **Saving the server: owner only.** The connection row is created through the owner API `/mcp`
   (`apps/api/src/lonora_api/routes/mcp.py:37`). The agent's only route is `owner_action_propose` with
   `kind="connect_credential"`, `target="mcp_server"`: "a secure form whose value goes straight to the
   server, never to you" (`packages/tools/src/lonora_tools/owner_actions.py:314-316`). The form posts to
   the owner API; the card only learns which resource was connected
   (`packages/db/src/lonora_db/capability_cards.py:11-15`). The agent cannot pre-fill the URL: the card
   payload carries only `target` and `service` (`packages/db/src/lonora_db/capability_cards.py:94-100`).
   UNSURE: exactly which fields the card form shows to the owner (client code not read); the server-side
   contract requires a name and an HTTPS URL (`packages/contracts/src/lonora_contracts/mcp.py:9-22`).
2. **Transport: HTTPS only.** `mcp_https_required` (`packages/contracts/src/lonora_contracts/mcp.py:20-21`).
   stdio (a local command, the most common way MCP servers are distributed) is refused when saving
   (`apps/api/src/lonora_api/routes/mcp.py:22-23`), when used
   (`packages/tools/src/lonora_tools/mcp.py:97-98`) and in the transport itself
   (`packages/adapters/src/lonora_adapters/mcp/transport.py:111-118`): `mcp_stdio_isolation_required`.
   **Needed for safety** as built (a command would run as the gateway user), but it removes most
   community MCP servers.
3. **Authentication: static bearer token only.** The transport sends `Authorization: Bearer <token>`
   (`packages/adapters/src/lonora_adapters/mcp/transport.py:51-52`). An OAuth helper module exists
   (`packages/adapters/src/lonora_adapters/mcp/oauth.py:11-54`) but a search of `apps/` and `packages/`
   found no caller, so OAuth-protected MCP servers cannot be connected. The policy also says "Do not
   start OAuth" (`packages/agent-runtime/resources/system/lonora.md:566`).
4. **Trust: owner taps a second card.** Saving a server authorizes nothing
   (`packages/tools/src/lonora_tools/mcp.py:145-153`). After the owner fills the form, the server reads
   the tool list and raises a `trust_source` card
   (`apps/api/src/lonora_api/routes/owner_actions.py:255-284`); on that card the owner must choose a
   tier (`owner_action_tier_required`, `apps/api/src/lonora_api/routes/owner_actions.py:683-684`). The
   agent can also raise it with `owner_action_propose trust_source`
   (`packages/tools/src/lonora_tools/mcp.py:333-353`). What is pinned: the endpoint hash and each tool's
   input-schema hash (`packages/tools/src/lonora_tools/mcp.py:3-4`).
5. **Tier.** At `read`, only tools the server marks read-only run; others fail
   `mcp_tool_needs_write_trust` (`packages/tools/src/lonora_tools/mcp.py:361-363`,
   `packages/tools/src/lonora_tools/mcp.py:378-380`) and need another card.
6. **Money tools never run.** `mcp_tool_financial_forbidden`
   (`packages/tools/src/lonora_tools/mcp.py:376-377`); state `blocked_moves_money`
   (`packages/tools/src/lonora_tools/mcp.py:226-231`). **Needed for safety** (money moves only through
   Lonora's executor).
7. **Schema drift.** If a trusted tool's schema changes, the call fails `mcp_schema_changed` and a
   re-review card is raised (`packages/tools/src/lonora_tools/mcp.py:381-386`).
8. **Operator overrides.** `LONORA_MCP_OWNER_TRUST=false` disables owner trust entirely
   (`apps/api/src/lonora_api/env.py:45-47`; `mcp_owner_trust_disabled`,
   `packages/tools/src/lonora_tools/mcp.py:338-339`); `LONORA_MCP_DECLARATIONS` can pre-authorize
   read-only tools (`apps/api/src/lonora_api/env.py:44`).
9. **Card limits.** Cards live 7 days (`packages/db/src/lonora_db/owner_actions.py:82-83`); one agent may
   have 5 pending cards, then `owner_action_limit`
   (`packages/db/src/lonora_db/owner_actions.py:92`, `packages/db/src/lonora_db/owner_actions.py:1314`).
10. **After the owner taps**, the agent continues by itself: a continuation Run with a fixed prompt
    ("Continue the work that needed it now ...", `packages/db/src/lonora_db/owner_actions.py:2063-2073`),
    unless the agent is paused or delegated (`packages/db/src/lonora_db/owner_actions.py:2089`).

Using a trusted server: `mcp_connections` -> `mcp_tools` -> `mcp_execute`
(`packages/tools/src/lonora_tools/mcp.py:408-444`). MCP tools are not added to the registry; they are
always called through the one generic `mcp_execute` tool. `mcp_execute` shows as unavailable
(`mcp_tool_not_authorized`) until at least one server is trusted or declared
(`packages/tools/src/lonora_tools/mcp.py:275-293`). Limits: 30 s per request, 2 MiB per response, 200
tools (`packages/adapters/src/lonora_adapters/mcp/transport.py:9-10`,
`packages/adapters/src/lonora_adapters/mcp/connector.py:9`), protocol version exactly `2025-06-18`
(`packages/adapters/src/lonora_adapters/mcp/connector.py:49-50`).

Failure codes: `mcp_not_found`, `mcp_disabled`, `mcp_stdio_isolation_required`,
`mcp_credential_scope_forbidden` (`packages/tools/src/lonora_tools/mcp.py:93-106`);
`mcp_tool_not_authorized` (`packages/tools/src/lonora_tools/mcp.py:152`,
`packages/tools/src/lonora_tools/mcp.py:393`); `mcp_tool_needs_write_trust`; `mcp_tool_not_found`
(`packages/tools/src/lonora_tools/mcp.py:375`); `mcp_tool_financial_forbidden`; `mcp_schema_changed`;
`mcp_connection_changed` (`packages/tools/src/lonora_tools/mcp.py:346`,
`packages/tools/src/lonora_tools/mcp.py:391`); `mcp_nothing_to_trust`
(`packages/tools/src/lonora_tools/mcp.py:344`); `mcp_owner_trust_disabled`; transport:
`mcp_connection_timeout`, `mcp_connection_failed`, `mcp_request_failed`,
`mcp_response_encoding_unsupported`, `mcp_response_invalid`, `mcp_response_too_large`,
`mcp_response_missing` (`packages/adapters/src/lonora_adapters/mcp/transport.py:38-91`); protocol:
`mcp_protocol_error`, `mcp_protocol_unsupported`, `mcp_tools_invalid`, `mcp_tools_limit_exceeded`,
`mcp_tool_failed` (`packages/adapters/src/lonora_adapters/mcp/connector.py:32`,
`packages/adapters/src/lonora_adapters/mcp/connector.py:50`,
`packages/adapters/src/lonora_adapters/mcp/connector.py:74`,
`packages/adapters/src/lonora_adapters/mcp/connector.py:110`,
`packages/adapters/src/lonora_adapters/mcp/connector.py:119`).

Two of these throw away the reason on purpose: a remote JSON-RPC error becomes `mcp_protocol_error` and
a tool-level error becomes `mcp_tool_failed`, with the remote message dropped ("Remote messages/data can
contain credentials or instructions", `packages/adapters/src/lonora_adapters/mcp/connector.py:30-32`).
The model therefore cannot tell "wrong argument value" from "server broken" and cannot repair the call;
it can only report that it did not work. None of the `mcp_*` connection codes is in the transient set
(`packages/core/src/lonora_core/runtime_failure.py:10-21`), so `mcp_connection_timeout` on the read-only
`mcp_tools` is not retried.

Owner-facing Arabic strings after the form is filled (verbatim,
`packages/bus/src/lonora_bus/attention_messages.json:46-48`): «تم الربط. يبقى السرّ على الخادم، ولا يرى
وكلاؤك إلا أنه مُعدّ.», «تم الربط. يبقى السرّ على الخادم. راجع أدواته في البطاقة التالية قبل أن يستخدمها
الوكلاء.», «تم الربط. يبقى السرّ على الخادم، لكن تعذّرت قراءة أدواته حتى الآن؛ سيتحقق وكيلك مجددًا ويخبرك.»

Doc vs code: `docs/mcp-boundary.md:18` says "Only an operator-reviewed `McpToolDeclaration` can authorize
an HTTP read operation." The code also authorizes tools the owner trusted
(`packages/tools/src/lonora_tools/mcp.py:145-153`), and the first paragraph of the same doc says so
(`docs/mcp-boundary.md:3-5`). Code wins; line 18 is stale.

---

## 6. Adding a new tool by itself

**Verdict: absent.**

The registry is built once from a fixed dictionary of Python modules
(`packages/tools/src/lonora_tools/loader.py:10-60`). There is no tool that registers a tool, no dynamic
loading from the workspace, and a call to an unknown name fails with `tool_call_target_unknown`
(`packages/tools/src/lonora_tools/registry.py:222`). The prompt states "Do not edit built-in policies or
promise autonomous self-improvement of the deployed system."
(`packages/agent-runtime/resources/system/lonora.md:480`).

Closest substitutes that exist:

- A trusted MCP server's tools, through the single `mcp_execute` bridge (section 5); they do not appear
  as tools of their own.
- A workspace script wrapped in a skill (section 4); it runs only inside the networkless sandbox, so it
  can compute but cannot call the broker, the web or any Lonora tool
  (`packages/agent-runtime/resources/system/lonora.md:581`).

Consequence for the owner's example: a recurring fix such as "on this account gold is `XAUUSDm`" cannot
be turned into a tool; the agent can only store it as memory or as an instruction-only skill.

---

## 7. Connecting accounts from chat

One mechanism: `owner_action_propose` with `kind="connect_credential"`. The agent never receives the
secret ("Never ask for a secret in chat; credentials stay on the server.",
`packages/agent-runtime/resources/system/lonora.md:561`; "Do not request passwords, signing keys, access
tokens, recovery codes or one-time authentication codes in chat.",
`packages/agent-runtime/resources/system/lonora.md:152`). **Needed for safety** (never print secrets).

| Account type | From chat? | Evidence |
|---|---|---|
| Broker | Present: one card, form posts to `/trading/connections` | `packages/db/src/lonora_db/capability_cards.py:38`, `packages/db/src/lonora_db/capability_cards.py:45`, `apps/api/src/lonora_api/routes/trading.py:65` |
| MCP server | Present: card, then a trust card (section 5) | `packages/db/src/lonora_db/capability_cards.py:41` |
| News feed | Present: card | `packages/db/src/lonora_db/capability_cards.py:42` |
| Brave Search key | Present: card; refused with `owner_action_not_needed_credential_already_configured` if a key exists | `packages/db/src/lonora_db/capability_cards.py:168-184`, `packages/db/src/lonora_db/owner_actions.py:1289` |
| Economic calendar (macro events feed) | Present: card | `packages/db/src/lonora_db/capability_cards.py:44` |
| Telegram, webhook (messaging channels) | Exist as integration types, but not a card target: owner UI/API only | `packages/contracts/src/lonora_contracts/integrations.py:15`, `packages/db/src/lonora_db/capability_cards.py:38` |
| Email | Absent. A case-insensitive search for `gmail|imap|smtp|outlook` in the Python under `packages/` and `apps/` (tests excluded) found nothing. Prompt: "Do not claim built-in tools can ... send email/Slack messages unless an actually available authorized connection provides that operation." | `packages/agent-runtime/resources/system/lonora.md:531` |
| Personal calendar | Absent. The same search for `google_calendar|caldav` found nothing; `economic_calendar` is a market-events feed, not the owner's calendar | `packages/db/src/lonora_db/capability_cards.py:38` |

The only way to reach email or a personal calendar is an HTTPS MCP server with a static token
(section 5).

After the owner fills a card form the agent resumes by itself
(`packages/db/src/lonora_db/owner_actions.py:2058-2062`). Broker symbol resolution, account binding and
`symbol_not_found` / `broker_account_not_found` belong to the trading/market part of the audit and are
not covered here.

---

## 8. Cross-cutting mechanisms behind "can't / didn't work / shows a code"

These apply to every tool in sections 1-7.

**M1. A failure reaches the model as a bare internal code.** Any `LonoraError` becomes
`{"ok": false, "code": "<code>"}` (`packages/agent-runtime/src/lonora_agent/tool_dispatch.py:110-113`).
No human-readable reason, no parameters (which limit, what value), no suggested next call. The runtime
then adds a `recovery` object with a category and a `next_action` word
(`packages/agent-runtime/src/lonora_agent/environment.py:203-210`). A search of the web and
mobile clients' error-text tables for the `workspace_*`, `browser_*`, `skill_package_*`,
`skill_repository_*` codes and `mcp_tool_not_authorized` found an owner-language entry for just one of
them (`skill_package_lifecycle_required`, `apps/web/src/lib/user_error.ts:46`,
`apps/mobile/lib/i18n.ts:122`), and that one belongs to an owner route, not to a tool. So the only wording
the model has for the owner is the code itself, which is how strings such as `symbol_not_found` end up
in an Arabic reply. The same code is also sent to the client in the `tool.completed` progress event
(`packages/agent-runtime/src/lonora_agent/tool_block.py:320`). UNSURE: whether the chat UI prints that
code to the owner (client rendering not traced).

**M2. Most codes get the same generic hint.** `classify` starts from `terminal_domain_failure` /
`alternate_route` (`packages/agent-runtime/src/lonora_agent/environment.py:36-37`) and only recognises
a short list. Pattern rules: `*_unconfigured` -> `not_configured` / `inspect_authorized_alternative`;
`*_not_found` -> `not_found` / `inspect_existing_state`
(`packages/agent-runtime/src/lonora_agent/environment.py:74-81`). The word "terminal" is attached to
momentary conditions such as `workspace_busy` and `workspace_timeout`. Only the eight codes in
`TRANSIENT_READ_CODES` are retried automatically
(`packages/core/src/lonora_core/runtime_failure.py:10-21`,
`packages/agent-runtime/src/lonora_agent/environment.py:92`).

**M3. Three identical failures close the route for the rest of the Run.** After 3 failures of the same
tool with the same arguments the call is no longer executed and returns `tool_route_exhausted`
(`packages/agent-runtime/src/lonora_agent/environment.py:127-131`,
`packages/agent-runtime/src/lonora_agent/tool_dispatch.py:70-80`). Read-only routes are forgotten only at
the next owner message or wake (`packages/agent-runtime/src/lonora_agent/environment.py:104-124`); a
non-read-only route such as `workspace_execute` with the same command and revision stays closed.

**M4. "Available" means "configured", not "working".** Availability checks look only at configuration
(`packages/tools/src/lonora_tools/workspace.py:45-51`, `packages/tools/src/lonora_tools/browser.py:37-38`),
are computed once when the Run starts and frozen ("when this Run started",
`packages/tools/src/lonora_tools/registry.py:442`). A host that is configured but down is presented as
ready and fails at call time (section 2.3, case 2). `capabilities_list` has the same blind spot
(`packages/tools/src/lonora_tools/capabilities.py:281`).

**M5. Optional infrastructure is off by default and only an administrator can turn it on.** Browser,
search service and code execution are overlays (`infra/research/compose.research.yml:1-2`,
`infra/analysis/compose.workspace.yml:1`, `infra/compose/install.sh:28`). For these the prompt and tool
guidance tell the model to say so and stop: "not_set_up: this server lacks it; say so plainly."
(`packages/tools/src/lonora_tools/capabilities.py:303`). For a single non-technical owner this is an
"I can't" with no way forward.

**M6. Prompt lines that steer toward stopping and reporting.**
"If a service is unavailable, state the practical access limitation and the single supported next step."
(`packages/agent-runtime/resources/system/lonora.md:568`);
"Report the practical failure and one concrete next step, preserving the distinction between unavailable
and uncertain." (`packages/agent-runtime/resources/system/lonora.md:163`);
"Use only capabilities exposed for this execution; this manual is not proof that every operation is
enabled." (`packages/agent-runtime/resources/system/lonora.md:156`);
"Registered tools are not proof that their backend is configured or reachable; use actual results."
(`packages/agent-runtime/resources/system/lonora.md:541`).
The owner's quoted reply ends with exactly this shape: a failure report followed by one offered next
step («الخطوة التالية المفيدة: أبحث لك عن اسم الذهب الصحيح على هذا الحساب إذا أردت.»). The one line that
pushes the other way is weaker and limited to reads: "For an ordinary safe read failure, make a bounded
meaningful correction or use a genuinely supported alternative source."
(`packages/agent-runtime/resources/system/lonora.md:160`). Nothing says "take the safe read-only next
step yourself before replying".

**M7. The specification asks for the opposite.** "Do not immediately expose every internal tool failure
to the user." (`docs/lonora-specs/19_AGENT_OPERATING_ENVIRONMENT_AND_SELF_DIRECTED_RUNTIME.md:523`);
"determining the bound broker symbol" is listed among bad reasons to involve the owner
(`docs/lonora-specs/19_AGENT_OPERATING_ENVIRONMENT_AND_SELF_DIRECTED_RUNTIME.md:795`); "Do not make the
owner act as the system's symbol resolver."
(`docs/lonora-specs/19_AGENT_OPERATING_ENVIRONMENT_AND_SELF_DIRECTED_RUNTIME.md:1578`). The code paths in
M1-M6 do not enforce any of these three sentences; they are left to the model. Where spec and code
differ, the code is what runs.

**M8. Extension tools are long-tail.** `workspace_*`, `web_browse`, `mcp_*`, `skill_package_*`,
`owner_action_propose` and `capabilities_list` carry no `eager` profile
(`packages/tools/src/lonora_tools/workspace.py:80-122`, `packages/tools/src/lonora_tools/browser.py:101-120`,
`packages/tools/src/lonora_tools/mcp.py:408-444`, `packages/tools/src/lonora_tools/skills.py:120-150`,
`packages/tools/src/lonora_tools/owner_actions.py:288-325`,
`packages/tools/src/lonora_tools/capabilities.py:308-321`). A Run sees them only as names in the
inventory text and must call `tool_environment` for the schema, then `tool_call`
(`packages/tools/src/lonora_tools/registry.py:155-178`). This is two extra steps before any
self-extension action, which makes "I can't" the cheaper answer for the model.

**M9. Every workspace call needs the exact revision number.** A model that does not call
`workspace_inspect` first, or that reuses an old number after its own write, gets
`workspace_revision_conflict` (section 1). It is classified as recoverable, but it costs a round trip on
every multi-step file job and counts toward M3 if repeated with identical arguments.

---

## 9. Safety refusals in this area that must stay

Each of these is a refusal that exists for the money-safety and secret-safety rules. A fix for the
owner's complaint must not remove them.

- Sandbox has no network, no broker credentials, no host files
  (`packages/agent-runtime/src/lonora_agent/workspace.py:207`,
  `packages/agent-runtime/resources/system/lonora.md:581`): needed for safety (no shadow trading from
  generated code).
- Browser cannot log in, POST or fill password fields
  (`packages/tools/src/lonora_tools/browser_service.py:144`,
  `packages/tools/src/lonora_tools/browser_service.py:266-267`): needed for safety.
- MCP tools that trade or move money never run
  (`packages/tools/src/lonora_tools/mcp.py:376-377`): needed for safety (single executor).
- MCP stdio commands are blocked (`packages/adapters/src/lonora_adapters/mcp/transport.py:111-118`):
  needed for safety until an isolated runner exists.
- Secrets are typed only into a card form and never reach the agent
  (`packages/db/src/lonora_db/capability_cards.py:11-15`): needed for safety.
- Skills cannot grant tools or financial authority (`packages/tools/src/lonora_tools/skills.py:162`):
  needed for safety.
- No tool confirms a card; only the owner's tap does
  (`packages/tools/src/lonora_tools/owner_actions.py:5-7`): needed for safety.

What is *not* a safety rule, and is where this area produces the complained-about behaviour: bare codes
with no explanation (M1), generic "terminal" hints for momentary conditions (M2), a configured-but-down
host shown as ready and reported as "uncertain" (M4, section 2.3), busy/timeout conflation in the
browser (section 3), dropped MCP error reasons (section 5), the contradictory "invoke shell commands"
line (section 2.4), and prompt lines that tell the model to report and offer instead of taking the safe
read-only step (M6).
