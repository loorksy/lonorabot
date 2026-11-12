# PR #104 — Phase 4 (W-WS 1): the owner's workspace as a service (7.1.1-7.1.4)

- Head: dee40d0c (ws/1-workspace-service)
- Base: main 4d4348ae; own commits 37c1d70, 9f247fe, 34a4cae, dee40d0 over merge-base 2a244c8c
- Reviewer: R-SEC
- Verdict: **FINDINGS** (1 high / 2 medium / 4 low)
- Conflicts with main: none (merge-tree clean)

## Verified findings

### H1 (high, 7.1.4): MetaApi is blocked only by name and by a snapshot of known addresses, so a workspace process can still reach MetaApi hosts
- Code:
  - `packages/workspace/src/lonora_workspace/egress.py:93-99`: the nft ruleset rejects ports 53/853 to anything off the host, plus `@blocked4/@blocked6`. Everything else, including TCP 443 to any public address, is accepted.
  - `netguard.py:170-178, 215-216`: the only MetaApi addresses in those sets are `learned`. That is what Docker's resolver returns every 300 s for the fixed `METAAPI_KNOWN_HOSTS` (`packages/core/src/lonora_core/broker_endpoints.py:12-24`).
- Bypasses:
  - **DNS over HTTPS** on 443 (`https://dns.google/resolve?name=…`, `https://1.1.1.1/dns-query`), a hard-coded address, or a wildcard-DNS name such as `<ip>.nip.io` all skip the forwarder's name check. Any MetaApi address not in `learned` is then reachable with the right SNI/Host.
  - **Hosts that are never learned:**
    - regions beyond the fixed four (the SDK discovers regions at run time from `/users/current/regions`);
    - instance letters beyond `-a`/`-b` (the SDK builds `chr(97+n)`);
    - every MetaApi API the door does not use (copyfactory, metastats, risk-management). 7.1.4 says "any MetaApi host".
  - **Load-balanced or geo-DNS addresses** that differ from the ones Docker's resolver happened to return in a given window.
- Reproduced: the generated ruleset was loaded in a scratch network namespace. A uid-20000 process is refused only on 53/853, private ranges and listed addresses, while port 443 to other public addresses passes. MetaApi itself is unreachable from this review host, so no live connect was made.
- The acceptance check cannot see the gap: `tests/check_workspace_service.py:355-377` dials the same names the guard learned.
- The docs overstate the guarantee:
  - `docs/operations.md:31`: «ولا تصل … خوادم MetaApi» ("does not reach MetaApi servers");
  - `docs/operations.md:183-185`: "cannot reach … MetaApi".
- Impact: 7.2 lets the owner store any value as a workspace secret, including a MetaApi token. A workspace script could then trade outside the execution door, against 9.5 ("MetaApi accounts are traded only through the execution door").
- Fix:
  - Make the MetaApi guard independent of DNS. In `workspace-net`, redirect workspace TCP 80/443 to a small relay that peeks the TLS ClientHello SNI or the HTTP Host. It refuses any name under `BROKER_DOMAINS`, and refuses a ClientHello without SNI or with ECH.
  - Keep the learned-address set as a second layer.
  - Add a check step that connects to a learned MetaApi address with a non-MetaApi Host, and to a non-learned MetaApi name via a hard-coded address.
  - Until the relay exists, state the limitation in both the Arabic and English docs.

### M1 (medium, 0.4): the docs say agents' commands already run in this workspace; nothing sends them there yet
- `docs/operations.md:161`: "Every agent's commands run in one persistent Linux workspace per owner (mandate 7.1) …".
- `docs/operations.md:31` (Arabic): «لكل مالك مساحة عمل Linux واحدة دائمة يتشاركها كل وكلائه …».
- The limits-table row reads "workspace (the owner's agents' terminal)".
- At this commit no code outside `packages/workspace` references `lonora_workspace`, the supervisor socket or `/v1/run`. The gateway does not mount `workspace-control`. Agents still use the old 45-second jobs (`lonora_agent/workspace*.py`).
- Fix: say that the workspace service is installed and running, and that agents' commands move to it in the change that wires the tools. Keep "every agent's commands run there" for that change.

### M2 (medium, 7.1.2 package installation): `PIP_USER=1` breaks `pip install` in any virtualenv an agent makes
- `packages/workspace/src/lonora_workspace/supervisor.py:273`: `"PIP_USER": "1"` is set in every agent's environment.
- Reproduced: `python3.12 -m venv v && PIP_USER=1 PYTHONUSERBASE=… v/bin/pip install --no-index six` fails with `ERROR: Can not perform a '--user' install. User site-packages are not visible in this virtualenv.`
- `PYTHONUSERBASE` alone already sends a non-root `pip install` to `~/.local` (pip falls back to a user install when site-packages is not writable).
- Fix: drop `PIP_USER`, keep `PYTHONUSERBASE`. Add a venv `pip install` step to `check_workspace_service.py`.

### L1 (low): the 10-minute foreground limit can be escaped with `setsid`
- `supervisor.py:340-345` kills only the job's process group.
- Reproduced: `setsid sleep 77 & …; sleep 60` with a 2 s limit returned `timed_out: True`, but `sleep 77` was still alive in its own session afterwards, untracked as a job.
- Fix: on timeout, kill every process of the job's uid that descends from the job's pid (walk `/proc` ppids), or run each job in its own cgroup and kill the cgroup.

### L2 (low): the supervisor's 422 answers echo request values
- `/v1/run` uses FastAPI's default `RequestValidationError` handler, which returns `"input": <value>`. Once 7.2.5 injects secrets through `env`, an invalid request (an oversized `env` value or an extra field) would return the secret unredacted.
- Fix: install a handler that returns only `loc` and `type`, as the API does.

### L3 (low): the first update on a host with less than disk + 5 GB free stops the whole update
- `infra/compose/lonora:166-167`: `workspace_disk` runs in `cmd_update`/`cmd_start`/`cmd_restore` and `die`s when `free < LONORA_WORKSPACE_DISK + 5 GiB`, so Lonora itself cannot be updated or restored. The message does say how to fix it.
- Fix: say in the release notes, or in the update message, that `LONORA_WORKSPACE_DISK` can be set lower before updating. Or skip only the workspace services in that case.

### L4 (low): capacity wording is stronger than the protection
- The workspace has `cpu_shares: 128` and `oom_score_adj: 1000`, and the gateway and db have `mem_reservation`, so the Gateway is protected as the docs say.
- But the api has no `mem_reservation` and the workspace has no `blkio_config` weight, so loop-disk I/O competes with Postgres fsync.
- On an updated install that never edits `.env`, the defaults (4g, `cpus: 2` on a 2-vCPU host) apply with no RAM or CPU preflight in `lonora update`/`start`.
- Fix: add a reservation for the api and `blkio_config: {weight: 10}` for the workspace, and have `update`/`start` warn when the defaults exceed the host. Otherwise soften «فلا تجوع البوابة أبدًا» ("never starves the Gateway") to what is guaranteed.

## Rejected (one line each)
- 7.1.2 "told which of its processes ended" is not built: this PR does not claim it. Noted for the wiring PR: the jobs table is in memory only, so it needs persisting.
- A background child of a foreground command gets SIGPIPE: documented in code as by design.
- A file moved into `/workspace/shared` keeps the agent's group: standard `mv` semantics.
- The test file is not run in CI: same as the existing core pytest files. Worth adding, not a finding.
- Host-address detection can come back empty silently: documented manual override exists.

## What I checked
- **Network:** the workspace is only on the `workspace` network, so no route to api/db/gateway/caddy.
- **Blocked ranges:**
  - IPv4: RFC1918, CGNAT, 169.254/16, 127/8, multicast and reserved;
  - IPv6: fc00::/7, fe80::/10, ::ffff:0:0/96 and 64:ff9b::/96;
  - all protocols.
- **Docker resolver:** 127.0.0.11 is refused to agent uids (reproduced in a scratch netns).
- **Agent privileges:**
  - no NET_ADMIN/NET_RAW;
  - `no-new-privileges`;
  - root-owned resolv.conf and hosts;
  - supervisor socket 0660 in a 0750 directory;
  - homes 0700; `.lonora` 0700;
  - shared is 2775 group `agents`, and a write by agent B to agent A's file was reproduced.
- **Users and commands:**
  - usernames come from uids, never agent ids;
  - no shell building (positional wrapper arguments);
  - identity env vars cannot be overridden;
  - uids are never reused, and the map is written atomically.
- **Limits:**
  - 2 CPU / 4g / memswap equal to memory / 20 GiB ext4 loop disk `nodev,nosuid` / pids 256;
  - the 600 s foreground limit was reproduced (capped at 5 s in a probe);
  - `init: true` reaps zombies.
- **Secrets:** no Docker socket, `.env` or Lonora secret in either workspace service. Logs carry only `boot_id`, counts and error types. `NEVER_RESTORED` excludes `LONORA_WORKSPACE_*`.
- **Safety core:** `broker_endpoints.py` holds constants only. `metaapi.py`'s `endswith("." + METAAPI_SDK_DOMAIN)` equals the old check. The door is untouched, and the old workspace is neither broken nor extended (0.4).
- **Tests:** test_workspace_service (15) plus the six core pytest regressions give 116 passed. ruff, ruff format and pyright are clean. `check_workspace_service.py` was not run (no Docker daemon here).
