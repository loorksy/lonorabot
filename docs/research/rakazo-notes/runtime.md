# Rakazo: runtime and harness (infrastructure)

Source: `/home/user/elie222/rakazo` at commit `cd7e20e5da754d8d8deaf2780671ed34a38e2241`. Paths are relative to that repo root.
"(implemented)" = confirmed in code or compose files. "(stated)" = only in docs/comments.

## 0. Short version

- The agent loop does **not** run inside the bot's computer. It runs in the API or worker Node process; the computer is a remote tool target reached through a `SandboxProvider` interface (stated, `docs/computer-runtime.md:13`; consistent with the code: the Docker provider is only an HTTP client of the supervisor, `packages/adapters/src/docker-sandbox.ts:147-196`).
- With `SANDBOX_PROVIDER=docker`, a small privileged service (the "supervisor") owns the Docker socket and creates one container per **computer** (not strictly per bot: a Team computer is shared by a Space's bots; see section 4).
- A computer is a Debian container with Xvfb + fluxbox + Chromium + noVNC, running as uid 1000 with all capabilities dropped. The home directory is the only persistent part.
- Computers start lazily on first tool use and are stopped after 10 minutes idle by default.

## 1. Deployment topology (compose)

There are four compose variants. Service set of the source-checkout stack `infra/compose/docker-compose.yml` (implemented):

| Service | What it does | Evidence |
| --- | --- | --- |
| `postgres` | Postgres 18; refuses any other major version at start | `infra/compose/docker-compose.yml:292-324` |
| `supervisor` | Sandbox supervisor on port 7091, mounts `/var/run/docker.sock` and the data dir | `infra/compose/docker-compose.yml:326-361` |
| `computer` | One-shot stub (`command: ["true"]`) whose only purpose is to build the image `rakazo/computer:local` that the supervisor launches | `infra/compose/docker-compose.yml:363-368` |
| `data-init` | One-shot busybox that chowns `/data` entries to 1000:1000 | `infra/compose/docker-compose.yml:370-394` |
| `migrate` | One-shot; applies DB migrations as the DB owner. Only this container gets the owner login; API and worker connect as `rakazo_app`, which row-level security binds | `infra/compose/docker-compose.yml:396-411` |
| `api` | HTTP API (also starts runs in-process, see section 6); bound to `127.0.0.1:3100` | `infra/compose/docker-compose.yml:413-491` |
| `worker` | Background jobs and run recovery; `stop_grace_period: 50m` | `infra/compose/docker-compose.yml:493-523` |
| `web` | Vite preview server on 5173; also the screen proxy (it gets `SCREEN_PROXY_SECRET`) | `infra/compose/docker-compose.yml:525-547` |

Other variants:
- `docker-compose.images.yml`: the same eight service names from published images, but its Postgres default is `postgres:16` pinned by digest, not 18 (`infra/compose/docker-compose.images.yml:305`); two networks, `app` and an `internal: true` `data` network (`infra/compose/docker-compose.images.yml:303-362`, `:620-623`).
- `docker-compose.prod.yml`: adds `caddy` (TLS, ports 80/443), optional `updater` (profile, port 7092, mounts the Docker socket) and optional `pitr` (WAL backup sidecar). Five networks: `edge`, `app`, `control`, `data` (internal), `backup` (`infra/compose/docker-compose.prod.yml:358-380`, `:650-701`, `:712-745`, `:755-761`). On its own it has **no** supervisor; it assumes a remote provider (`infra/compose/docker-compose.prod.docker.yml:9-10`).
- `docker-compose.prod.docker.yml`: overlay that adds `supervisor`, `computer`, `data-init` and flips `SANDBOX_PROVIDER` default to `docker` (`infra/compose/docker-compose.prod.docker.yml:1-13`, `:60-127`).
- `docker-compose.topology.yml`: a test topology (hard-coded password `topology-only-password`, `infra/compose/docker-compose.topology.yml:1-14`). Not read further.

Hardening numbers in the prod stack (implemented): postgres, pitr, migrate, api, worker, web, updater and caddy each set `no-new-privileges` (`infra/compose/docker-compose.prod.yml:333`, `:374`, `:430`, `:465`, `:570`, `:606`, `:665`, `:718`); api/worker/web/caddy drop all capabilities (postgres, updater and the overlay's supervisor do not); limits are postgres `pids_limit 200` / `mem_limit 2560m` (`infra/compose/docker-compose.prod.yml:332-335`), api `512` pids / `2g` (`:464-470`), worker `512` pids / `2g` (`:569-574`), web `128` pids / `512m` (`:605-610`), caddy `128` pids / `256m`, read-only root, all caps dropped then `NET_BIND_SERVICE` added back (`:716-724`), supervisor `256` pids / `512m` (`infra/compose/docker-compose.prod.docker.yml:71-74`).

The supervisor runs as `user: root` and holds the Docker socket; the compose comments say plainly that access to it "is equivalent to control of the Docker host" and it has no published port and only the `app` network (`infra/compose/docker-compose.images.yml:360-369`; `infra/compose/docker-compose.prod.docker.yml:70`, `:109-112`).

## 2. The supervisor

Code: `infra/sandboxes/supervisor/src/`. A Hono HTTP app (`routes.ts:114`), default bind `127.0.0.1:7091` when run outside compose (`index.ts:36-37`); compose sets `0.0.0.0` (`infra/compose/docker-compose.yml:333-334`).

### 2.1 API (implemented, `infra/sandboxes/supervisor/src/routes.ts`)

| Route | Purpose | Line |
| --- | --- | --- |
| `GET /health` | unauthenticated liveness; returns image name | `:130` |
| `POST /computers` | create or resume the container for `{botId, homePath, spaceId, timezone?, language?}` | `:147-376` |
| `GET /computers/:id` | `{running, image}` | `:378-392` |
| `POST /computers/:id/exec` | run `argv` with `cwd`, `env`, `timeoutMs`; streams NDJSON `stdout`/`stderr`/`exit` events | `:396-505` |
| `POST /computers/:id/browser` | page-browser commands `navigate`, `snapshot`, `act`, `purchase_check` | `:510-704` |
| `POST /computers/:id/observe` | screenshot + cursor/window info | `:706` |
| `POST /computers/:id/actions` | batched GUI actions (key, pointer, clipboard, scroll, wait, open, launch, focus) | `:741`; schema `supervisor-logic.ts:71-92` |
| `GET/POST /computers/:id/files` | list / read (base64) / write a file under the home | `:795-871` |
| `GET /computers/:id/screen`, `POST .../screen-mode` | view-only or interactive (human) screen URL | `:873-951` |
| `POST /computers/:id/terminal` | human PTY terminal bound to a control token | `:953-997` |
| `POST /computers/:id/input` | one human key/pointer/clipboard input via `xdotool` | `:1001-1041` |
| `DELETE /computers/:id/screen` | release a bot's screen (optionally keep it warm) | `:1043-1129` |
| `POST /computers/:id/stop` | quiesce browser profiles, then `docker stop`; if stop throws, `kill` and poll up to 30 x 1 s. With header `x-rakazo-discard-unsaved: 1` the quiesce step is skipped | route `:1148-1194`; `stopOrKill` `:1131-1146` |
| `DELETE /computers/:id` | force-remove container and its network | `:1196-1222` |

Limits and timeouts:
- Request bodies are capped at 1 MiB, except file writes, which allow `max(16 MiB, 4/3 x MAX_UPLOAD_SIZE)` + 64 KiB (`request-limits.ts:6-24`).
- Exec timeout: default 5 min, hard maximum 60 min (`packages/core/src/sandbox-command.ts:1-2`, `:20-26`); enforced inside the container with `timeout --kill-after=1s` (`supervisor-logic.ts:608-619`). A blank NDJSON line is sent every 15 s as keep-alive (`routes.ts:394`, `:443-451`).
- Page-browser helper timeout: 25 s; output cap 512 KiB (`routes.ts:660`, `:675-680`); at most 24 actions per `act` (`routes.ts:609-610`).
- Screen readiness: polls `embed.html` every 300 ms with a 1.5 s request timeout for up to 45 s (`readiness.ts:7-31`).

Error shaping worth noting for Lonora: once a browser request has passed validation, a helper failure (timeout, nonzero exit, oversized or malformed output, or any exception in the handler) is not returned raw. The route answers HTTP 200 with `{ok:false, fallback:"computer_act", uncertain, error}` (`routes.ts:692-703`), where the error text tells the caller what to do next, e.g. (implemented, `routes.ts:683-687`). Two cases are not shaped this way: an invalid request gets HTTP 400 `invalid_browser_request` (`routes.ts:617-622`), and a helper refusal (exit code 2) is passed through as the helper wrote it (`routes.ts:675-678`). Whether this text reaches the model unchanged was not traced on the app side (unverified):

> "Page browser timed out; the page may be busy or blocked by a dialog. … Inspect the screen before continuing." / "Retry once before using other tools."

Exec on a stopped container answers `409 computer is not running` "so the caller can boot it" (`routes.ts:412-413`). On any non-OK exec response the app-side provider asks the supervisor whether the container is running and, if it is not, throws a "sandbox gone" error; it does the same when stderr matches `no such container` (`packages/adapters/src/docker-sandbox.ts:273-278`, `:298-300`). The code comments say this is so "the computer is booted again" (`docker-sandbox.ts:275`) and that callers "replace the computer" on such an error (`packages/adapters/src/sandbox-errors.ts:21`); I did not trace the caller that performs the re-boot, nor whether the model ever sees the error (unverified).

### 2.2 Identity and auth between app and supervisor (implemented)

- One shared bearer token, `SANDBOX_SUPERVISOR_TOKEN`, compared in constant time (`routes.ts:132-143`; `supervisor-logic.ts:115-121`). It is required by compose (`infra/compose/docker-compose.yml:342`) and must differ from `BETTER_AUTH_SECRET` and `SCREEN_PROXY_SECRET`; outside dev/test a missing value, a known placeholder, or a value shorter than 32 characters is refused (`packages/core/src/secrets-guard.ts:22-27`, `:80-107`, `:109-118`).
- Requests also carry `x-rakazo-space-id` and, when the caller has them, `x-rakazo-bot-id`, `x-rakazo-screen-id`, `x-rakazo-screen-lease-id` (read at `routes.ts:121-128`; sent conditionally by `packages/adapters/src/docker-sandbox.ts:147-157`). Routes that go through `managedContainer` reject a request with no bot or space id and only act on a container whose Docker labels `rakazo.botId` / `rakazo.spaceId` match those headers (`identity.ts:64-71`; `supervisor-logic.ts:106-113`, `:821-830`). Labels are set at create (`computer-spec.ts:620-625`).
- The home path must be exactly `DATA_DIR/homes/<botId>` (`identity.ts:81-86`).
- My inference (not a Rakazo statement): this is a confused-deputy check, not a second trust boundary, because the headers are plain values set by the token holder (`packages/adapters/src/docker-sandbox.ts:147-157`).

### 2.3 Container spec (implemented, `computer-spec.ts:602-661`)

- Image: `rakazo/computer:local` unless `RAKAZO_COMPUTER_IMAGE` (+ tag) is set (`computer-spec.ts:18-30`). The supervisor only pulls registry-qualified names, never a bare name that Docker Hub would resolve (`computer-spec.ts:56-67`).
- User: `1000:1000` (`computer-spec.ts:69-71`, `:608`). `docker exec` sets no user, so the bot's shell and the human terminal both run as that user (`supervisor-logic.ts:774-786`).
- Security: `CapDrop: ["ALL"]`, `no-new-privileges:true`, `/usr/share/novnc` read-only (`computer-spec.ts:651-654`). Root filesystem is **not** read-only.
- Resources: memory `2g` with `MemorySwap` equal to memory (no swap), `2` CPUs, `2048` pids, `/dev/shm` 256 MiB (`computer-spec.ts:107-109`, `:186-193`, `:650`). `0`/`none`/`unlimited` disables a ceiling (`computer-spec.ts:120-123`). Limits are parsed at supervisor start so a bad value fails early (`index.ts:16-20`).
- Mounts: the home is either a bind `homePath:/home/rakazo` or a named-volume **subpath** (needs Docker Engine 26+/API 1.45) (`computer-spec.ts:550-555`, `:628-648`). Optional operator mounts from `SANDBOX_COMPUTER_MOUNTS` may only target `/mnt`, `/media`, `/srv`, are read-only by default, and may not overlap `/var/run`, `/run`, `/proc`, `/sys`, `/dev`, `/etc`, `/boot`, `/root`, `/var/lib/docker`, the data dir or the Docker socket (`computer-spec.ts:263-279`, `:296-361`).
- Env passed to the container: cache dirs under `/tmp/rakazo-cache`, `DISPLAY=:1`, `HOME`, `PATH` with `~/.local/bin` first, `NPM_CONFIG_PREFIX=~/.local`, `PIP_USER=1`, a random per-container `RAKAZO_COMPUTER_CONTROL_TOKEN`, and optional `TZ`/`LANGUAGE` taken from the `timezone`/`language` fields of the create request (`computer-spec.ts:610-619`; `routes.ts:319`; `computer-locale.ts:45-50`; `packages/core/src/node/desktop-runtime.ts:38-44`). That list contains no model key and no app secret.
- Ports: only the noVNC port 6080 is published, to `127.0.0.1` on a random host port; the control port 7070 is published (also loopback) only with `SANDBOX_CONTROL_VIA_LOOPBACK=true` for Docker Desktop (`computer-spec.ts:513-526`; `context.ts:46-48`).
- Names: container `rakazo-bot-<sanitized id, max 40 chars>`, network `rakazo-computer-<id>-<sha256/32>` (`computer-spec.ts:663-678`).

### 2.4 Create/resume logic (implemented, `routes.ts:163-371`)

An existing container is **resumed** (started if stopped) only if all of these still match: image id, network attachment, restricted-bridge name, user, DNS, operator mounts, locale env, control-port publication, home volume. Otherwise it is removed and recreated (`routes.ts:244-275`, `:333-352`). The home survives because it lives outside the container. On a failed create the new container and network are removed, without force (`routes.ts:353-358`).

### 2.5 Locks (implemented, `locks.ts:1-30`)

Three in-memory promise-chain mutexes (`supervisor-logic.ts:487-506`): per bot id (create/delete), per container id (screen claim/release), per space id (count + create under `SANDBOX_MAX_COMPUTERS_PER_SPACE`). Lock order is bot then space (`routes.ts:277-280`). They are plain in-process `Map`s (`locks.ts:3-5`), so (my inference) the design assumes a single supervisor instance.

### 2.6 Networks and egress (implemented)

- Each computer gets its own Docker bridge network so computers cannot dial each other (`networks.ts:36-51`). In compose (`SANDBOX_SCREEN_NETWORK=isolated`, `infra/compose/docker-compose.yml:343`), the supervisor container and the `web` screen-proxy container join each bot network to reach the screen and control ports (`networks.ts:53-96`).
- A stopped computer gives its network back because Docker's address pools "run out after a few dozen networks" (`networks.ts:197-208`); idle networks are also reclaimed at supervisor start (`index.ts:33-35`; `networks.ts:153-167`).
- Egress modes `open` / `restricted` / `auto` (`computer-spec.ts:202-225`). `restricted` only gives the bridge a deterministic name `rakazo-c<7 hex>` (`computer-spec.ts:424-427`, `:482-484`); the actual blocking is a host script, `infra/compose/restrict-computer-egress.sh`, which adds iptables rules matching `-i rakazo-c+`: drop INPUT to the host except established replies, and drop forwarding to `0.0.0.0/8, 10/8, 100.64/10, 127/8, 169.254/16, 172.16/12, 192.0.0.0/24, 192.168/16, 198.18/15, 224/4, 240/4` plus IPv6 `::1, fc00::/7, fe80::/10, ff00::/8` (`infra/compose/restrict-computer-egress.sh:56-79`, `:93-97`). Public internet stays fully open: there is no domain allowlist.
- On supervisor start and again on each `POST /computers` (result cached after the first success), the supervisor checks enforcement (`index.ts:21-32`; `routes.ts:165`; `egress.ts:20-47`). The check runs a probe container (64 MiB, 32 pids, read-only root) on a network `rakazo-egress-probe` whose bridge is named `rakazo-cprobe`; it tries the gateway on ports 22 and 1 (2 s each) and `169.254.169.254:80`; if anything answers, restricted mode is "not enforced" (`egress-probe.ts:20-33`, `:52-69`, `:91-154`). In `auto` (the compose default, `infra/compose/docker-compose.yml:344`) that result downgrades to open with only a log warning (`egress.ts:20-38`); in explicit `restricted` the error is thrown instead (`egress.ts:40-47`). With the variable unset (a supervisor run outside compose) the mode is `open` (`computer-spec.ts:222`).
- Restricted mode is IPv4-only; open mode creates dual-stack networks with a fallback to IPv4 (`computer-spec.ts:459-486`; `networks.ts:210-233`).
- Docs note: `docs/self-host-restricted-network.md` is about installing from mirrors/offline (`docs/self-host-restricted-network.md:1-11`), not about computer egress. Egress is documented in `docs/self-host-docker-computers.md:35-109`.

### 2.7 Screens (implemented, `screens.ts`, `packages/core/src/node/desktop-runtime.ts`)

- The supervisor keeps an in-memory registry: container id -> (screen key -> slot with index, view token, lease id, control token) (`screens.ts:26-28`). Screen key is the `x-rakazo-screen-id` header, i.e. the acting bot's id (`screens.ts:150`; `packages/adapters/src/docker-sandbox.ts:153`).
- Each slot is its own X display `:1+index` with its own Chromium debug port `9221 + display` and its own profile directory `~/.browser-profiles/chromium-bot-<sha256(screenId)/32>` (`desktop-runtime.ts:56-68`, `:114-116`). All screens use the same view/control port 6080 (`desktop-runtime.ts:64-65`); each view is an x11vnc on its own Unix socket, and a token file maps the view token to that socket for the gateway (`desktop-runtime.ts:806-824`; stated as "one token-protected screen gateway" in `docs/computer-runtime.md:46`).
- The registry is tied to the container's `StartedAt`; if the container restarted, or the supervisor lost its memory, all desktop processes in the container are reset on the next screen request (`screens.ts:138-149`; comment at `routes.ts:1110-1112`).
- A screen set up less than 30 s ago is reused without re-running setup for page-browser calls (`supervisor-logic.ts:406-418`).
- `SANDBOX_TEAM_SCREEN_LIMIT` caps concurrent desktops per computer; unset or `0` falls back to the technical maximum `65535 - 9221` displays (`computer-spec.ts:78-87`; `packages/core/src/node/desktop-runtime.ts:7`). When no index is free, the oldest idle screen that is not user-controlled and not being released is torn down, if there is one (`screens.ts:151-172`; `supervisor-logic.ts:328-341`).

## 3. The computer image

Code: `infra/sandboxes/computer/`.

### 3.1 Contents (implemented, `infra/sandboxes/computer/Dockerfile`)

- Base: `debian:bookworm-slim` pinned by digest (`Dockerfile:45`).
- Desktop: `xvfb`, `x11vnc`, `fluxbox`, `xterm`, `xdotool`, `wmctrl`, `imagemagick`, `novnc`, `websockify`, `dbus-x11`, `xdg-desktop-portal(-gtk)`, `xclip`, `xsel` (`Dockerfile:53-86`). Screen is 1280x800x24 (`start.sh:40`).
- Browser: Debian `chromium` by default; build arg `BROWSER=chrome|brave` swaps it (`Dockerfile:1-3`, `:110-145`). Managed policy turns off the password manager and autofill and allows pop-ups (`browser-policy.json:1-6`).
- Languages/tools: `python3` (+ `python` symlink, `python3-openpyxl`), `bash`, `curl`, `git`, `jq`, `openssh-client`, `unzip`, `poppler-utils`, `pandoc`, `ripgrep`, `fd`, `file`, `sqlite3` (`Dockerfile:65-93`, `:226-227`); `uv`/`uvx` 0.12.19 and GitHub `gh` 2.100.0, both sha256-checked (`Dockerfile:148-175`); `agent-browser` 0.41.0, sha256-checked (`install-agent-browser.sh:9-12`).
- No Node.js, no compiler, no `sudo` in the final image: the apt list at `Dockerfile:53-93` has none of them, and the comment says "Compilers stay in the builder stage" (`Dockerfile:48-50`). `NPM_CONFIG_PREFIX` is nevertheless set (`computer-spec.ts:615`).
- Fonts: Liberation, DejaVu, Noto CJK, Noto colour emoji (`Dockerfile:71-74`). No Arabic-specific font package is listed; unsure how Arabic text renders (DejaVu covers basic Arabic).
- Final `USER 1000:1000` (`Dockerfile:235`).

### 3.2 Boot (implemented, `start.sh`)

PID 1 is a bash script that: starts the control service in a restart loop if a token is set (`start.sh:31-36`), starts Xvfb `:1` and waits up to 100 x 0.1 s (`:40-55`), a dbus session and the file-chooser portals (`:57-72`), fluxbox (`:74-85`), registers `rakazo-browser` as default browser (`:87-102`), a **view-only** x11vnc on loopback (`:104`) and websockify on `0.0.0.0:6080` with a token file (`:125`). It exits when Xvfb exits (`:127-129`). `start.sh` does not launch a browser. The docs say "Desktop stacks start lazily when a bot uses graphical tools" (stated, `docs/computer-runtime.md:46`), but that is only partly what the code does: the primary display `:1` (Xvfb, fluxbox, view-only x11vnc, websockify) is started at container boot by `start.sh` as listed above, and what is lazy is the per-screen setup command the supervisor runs on a screen request (`screens.ts:178-182`). I did not read `ensureScreenCommand` far enough to say exactly where the browser is launched (unverified).

Because the container may run under a host uid that has no passwd entry, `nss_wrapper` is preloaded to fake one (`user-env.sh:1-21`; `Dockerfile:230-234`).

### 3.3 How the bot uses it

1. **Shell**: `docker exec` of `argv` as uid 1000 in `/home/rakazo`, env from the request layered on a fixed base (`routes.ts:458-467`; `exec.ts:38-49`).
2. **Files**: small Python snippets executed in the container to list, read (base64, optional `maxBytes`, exit 42 -> HTTP 413) and write (stdin, mode `0600`/`0700`); paths are normalised and `.`/`..` segments rejected, always under `/home/rakazo` (`routes.ts:795-871`; `exec.ts:153-187`; `supervisor-logic.ts:595-606`). Symlinks are skipped when listing (`routes.ts:833`).
3. **Page browser (DOM level)**: `/usr/local/bin/rakazo-page-browser`, a Python wrapper around `agent-browser` attached to the visible Chromium over CDP on loopback (`rakazo-page-browser:1-8`, `:36`; flags at `rakazo-browser:455`). Arguments go over stdin, not argv, when they carry a saved login, because "argv is readable by any process in the computer, including the bot's own shell" (`routes.ts:639-647`).
4. **GUI (pixel level)**: preferred path is an HTTP service inside the container, `control.py` on `0.0.0.0:7070`, bearer-token protected, which accepts only supervisor-shaped argv (`env DISPLAY=:N xdotool …`, `xdg-open`, `rakazo-browser`, `xterm`, `rakazo-focus-or-launch`) and returns a PNG screenshot from a native capture library (`control.py:15-35`, `:205-235`, `:358-399`, `:407`). Body cap 256 KiB, 10 s per step (`control.py:24`, `:35`). If it is unreachable the supervisor falls back to `docker exec` with `xdotool` and ImageMagick `import` (`supervisor-logic.ts:123-125`; `exec.ts:112-151`).
5. **Human view/takeover**: view-only x11vnc per display; "take control" starts a second, non-view-only x11vnc on its own Unix socket guarded by a control token (`desktop-runtime.ts:813`, `:909`; `routes.ts:892-951`).

### 3.4 Persistence, root, installing software

- Persistent: only `/home/rakazo` (the mounted home), including browser profiles under `.browser-profiles` (`computer-spec.ts:628-648`; `desktop-runtime.ts:29-36`). Tool caches are deliberately redirected to `/tmp/rakazo-cache` so they are not saved (`desktop-runtime.ts:37-44`).
- Rebuilt: everything else. The container is replaced whenever the image id or any of ~8 settings change (`routes.ts:244-275`).
- No root: uid 1000, all caps dropped, `no-new-privileges`, no `sudo` package (`computer-spec.ts:608`, `:651-652`).
- Installing software: system packages cannot be installed at runtime (`Dockerfile:48-50`, stated in a comment and consistent with the spec above). User-level installs into the home work: `uv tool install`, `pip` with `PIP_USER=1`, npm prefix in `~/.local` if a Node binary is brought in (`Dockerfile:187-189`; `computer-spec.ts:614-616`; stated `docs/computer-runtime.md:129`).
- **Docs/code disagreement**: `infra/compose/restrict-computer-egress.sh:4` and `docs/self-host-docker-computers.md:37-38` list "apt" among things a restricted computer can still do, but `Dockerfile:48-50` says nothing can be installed at runtime and the container has no root. The network path to apt mirrors is open; apt itself cannot run usefully.
- Minor inconsistency: `Dockerfile:229` exposes 7070 and 6080-6095, but all screens use port 6080 by default (`desktop-runtime.ts:64-65`).
- **Docs/code disagreement (uv cache)**: `docs/computer-runtime.md:129` says the uv "cache stay[s] under the persistent home", but the container env sets `UV_CACHE_DIR=/tmp/rakazo-cache/uv` (`desktop-runtime.ts:37-44`, applied at `computer-spec.ts:611`).

## 4. Team vs Private computer, takeover, lazy start, idle release

### 4.1 Team vs Private (implemented)

- DB `Computer.scope` is `team` (default) or `dedicated` (`packages/db/prisma/schema.prisma:1807`; `packages/db/src/computers.ts:61-64`).
- A Team computer is keyed `team:<spaceId>:<userId>`; a Private one `bot:<botId>` (`packages/db/src/computers.ts:77-81`). The key handed to the provider as "botId" is the computer's `homeKey`: `team-<sha256(space:user)/32>` or the bot id (`packages/db/src/computers.ts:89-99`; `packages/adapters/src/computer-lifecycle.ts:446-448`). So with Docker there is **one container per computer**, and a Team container hosts several bots.
- On a Team computer each bot's shell starts in `bots/<bot-id>/` and shared work goes in `shared/`; this is a convention, not a boundary (`packages/adapters/src/computer-support.ts:111-119`, `:134-144`; stated `docs/computer-runtime.md:40`, `:57`).
- User-facing wording: Team bots "share one Team Computer, with the same files and installed tools"; Private is for "files or sign-ins [that] must not be shared" (stated, `docs/computer.md:29-35`).
- Caps: `SANDBOX_MAX_COMPUTERS_PER_USER` (DB-side, default 0 = none) and `SANDBOX_MAX_COMPUTERS_PER_SPACE` (supervisor-side, returns HTTP 429) (`packages/db/src/computers.ts:136-147`; `computer-spec.ts:89-100`; `routes.ts:283-291`).

### 4.2 User takeover (implemented unless marked)

- The user's control lease lasts 15 min by default (`COMPUTER_TAKEOVER_TTL_MS`, minimum 1 s) (`packages/adapters/src/computer-control.ts:17-22`).
- Taking control while the bot holds a live execution lease is refused with CONFLICT "Stop the bot first", unless the run is `waiting_takeover` or the computer's `controlRunId` equals the lease's run (the bot asked); and then only the run's own user may take it, others get "The bot is waiting for someone else" (`apps/api/src/routes/computer.ts:398-414`; blocking rule in `apps/api/src/computer-status.ts:14-29`).
- When a run waits for takeover on a provider that does not bill per minute, the computer is kept awake 30 min (`packages/adapters/src/computer-idle.ts:47-52`).
- The screen URL the browser gets goes through the `web` service's proxy and a capability signed with `SCREEN_PROXY_SECRET` (stated `docs/self-host-docker-computers.md:8-10`; secret wiring at `infra/compose/docker-compose.yml:450`, `:537`). I did not read the proxy code.

### 4.3 Lazy start and idle release (implemented)

- `lazyRunComputer` wraps the start call: the first tool that needs the computer triggers it, a second caller reuses the same promise, and a failed start is remembered and rethrown for every later use in that run (`packages/adapters/src/run-computer.ts:9-38`). Reason given: "Remote computers bill while they run" (`:6-7`).
- Idle stop: default 10 min, minimum 30 s, `SANDBOX_IDLE_MS=0` disables (`packages/adapters/src/computer-idle.ts:39`, `:329-332`, `:351-353`). A sweep runs every 10 min (`:59`).
- Uptime cap default: 2 h (`COMPUTER_MAX_ACTIVE_MS`, 0 disables, minimum 60 s). For "providers that do not bill while running" a separate cap applies only if `COMPUTER_MAX_ACTIVE_UNBILLED_MS` is set to at least 60 s (`computer-idle.ts:46`, `:334-349`). Which providers count as unbilled was not traced beyond the `billsWhileRunning?` hook (`packages/adapter-kit/src/interfaces.ts:104-105`); `docker-sandbox.ts` does not define it.
- A suspend claim older than 60 min is treated as abandoned (`computer-idle.ts:53-58`).
- On a normal supervisor stop, browser profiles are quiesced before the container is stopped (implemented, `routes.ts:1161-1178`). Workspace checkpointing is app-side and only stated here: workspaces are checkpointed at run completion or failure, before explicit stop and before idle suspension, and for Docker, which mounts the home directly, this "only advances its revision marker" (stated, `docs/computer-runtime.md:119`). For transferred (remote) workspaces, homes over 5 GiB or one million files stay running unsaved (stated, `docs/computer-runtime.md:125`).
- `sandbox-allowance.ts` is billing only: a per-organization spend limit in micro-dollars for providers that bill while running; Docker and host computers cost 0 (`packages/adapters/src/sandbox-allowance.ts:9-15`, `:46-59`).

## 5. Sandbox provider abstraction

- Interface `SandboxProvider` (`packages/adapter-kit/src/interfaces.ts:101-260`). Required methods: `describe`, `provision`, `prepare`, `execute` (async stream of process events), `connectScreen`, `sendInput`, `observe`, `act`, `listFiles`, `readFile`, `writeFile`, `exportWorkspace`, `importWorkspace`, `snapshot`, `stop`, `destroy`. Optional: `pageBrowser`, `connectTerminal`, `isRunning`, `isStopped`, `keepAlive`, `releaseScreen`, `cancelRunWork`, `inspectBackgroundWork`, `billsWhileRunning`, `keepsHome`, `environment`, and others.
- Factory: `createSandboxProvider(kind, opts)` accepts `none | docker | e2b | novita | daytona | createos | boat | boxd | instabox | railway | kubernetes | incus | wuying | desktop | fake` (`packages/adapters/src/sandbox-factory.ts:91-237`).
- **`none`**: `describe()` reports all capabilities false and the other methods call one `fail()` that throws a fixed message, "Computers unavailable. Set SANDBOX_PROVIDER=docker …" (`packages/adapters/src/none-sandbox.ts:14-39`; I counted 15 `this.fail()` calls in the 138-line file but did not read each method). It is also what you get for an empty kind or a remote provider with a missing API key, with a message naming the missing variable (`sandbox-factory.ts:72-89`, `:95`, `:107`). So, per the class comment, the API boots without a computer host and "Provision and runtime calls fail closed" (`none-sandbox.ts:17`).
- **`docker`**: HTTP client of the supervisor; declares graphical, pty, snapshots, takeover, persistentHome, multiScreen (`packages/adapters/src/docker-sandbox.ts:127-141`). It tracks computers that left a command unanswered and health-checks them (`argv: ["true"]`, 10 s) before the next use (`docker-sandbox.ts:49`, `:111-118`, `:232-240`).
- **`desktop`**: runs commands directly on the API/worker host with a whitelisted minimal environment; refused unless `NODE_ENV` is `development`/`test` or the process is Electron (`packages/adapters/src/desktop-sandbox.ts:66-74`; env whitelist `packages/adapters/src/sandbox-command-environment.ts:28-96`).
- **Host computer ("This Mac")**: when the env kind is `docker` and the bot's `computerHost` is `this-mac`, the kind becomes `desktop` and commands go through an authenticated bridge to the Electron app (`packages/adapters/src/host-aware-sandbox.ts:34-37`; stated `docs/self-host-sandbox-providers.md:36`, `docs/computer.md:53-63`). I did not read `host-computer-*.ts` in full.
- **`kubernetes`**: one pod per computer, default namespace `rakazo-sandboxes`, ready timeout 120 s, no service-account token, caps dropped, no privilege escalation; CPU/memory limits are optional with no default (`packages/adapters/src/kubernetes-sandbox.ts:36-40`, `:377-378`, `:394`, `:409-412`).
- **`incus`**: defaults `2` CPUs, `2GiB`, `2048` processes; unprivileged, no nesting, isolated idmap (`packages/adapters/src/incus-sandbox.ts:43-46`, `:428-435`).
- **Remote (e2b, daytona, boat, …)**: the stored workspace is the durable copy; new or replacement machines import the latest stored workspace, and the provider reference is "an acceleration path, not durable data" (stated, `docs/computer-runtime.md:117-119`). The interface has `exportWorkspace`/`importWorkspace` for this (`packages/adapter-kit/src/interfaces.ts:101-260`). Provider adapters not read in code.
- `ConfiguredSandbox` wraps the env-selected provider and can route a computer to a provider chosen in Settings, with credentials loaded from the secret store and cached (max 1000 entries) (`packages/adapters/src/configured-sandbox.ts:172-265`, `:279-300`). Docker, Kubernetes, Incus, desktop, fake, none are env-only (stated, `docs/self-host-sandbox-providers.md:28`).

## 6. Sessions, queues, concurrency

- **Where runs execute**: a run starts in whichever process made it due, normally the API process, as an independent task; there is no queue between a due run and its start (stated, `docs/run-execution.md:3-10`; a compose comment agrees: "Chat runs execute in the API that receives them", `infra/compose/docker-compose.prod.yml:468`). A recovery scan runs at start and then every 5 s by default (`packages/adapters/src/run-wakeup.ts:218-220`); that it runs in each worker and what it recovers is stated (`docs/run-execution.md:21-23`).
- **Lease claim (one claimer at a time)**: `claimRun` is a single conditional `UPDATE` that sets `status=leased`, `leaseOwner`, a new `leaseFence`, and a 5-minute `leaseExpiresAt`; it only matches rows that are queued/waiting or whose lease expired, and it claims nothing while the Space is being deleted (`packages/adapters/src/run-lifecycle.ts:378-420`). An expired lease can be claimed again, so this is not exactly-once execution. A heartbeat every 60 s renews the run lease (5 min) and the computer lease; if either renewal fails the run is aborted (`packages/adapters/src/executor.ts:461-479`; `run-lifecycle.ts:149-164`).
- **No fixed concurrency number for runs**: admission is by memory headroom, not a count. A new run waits (1 s polls) only while other runs are active and available physical memory or V8 heap is below `4 x ATTACHMENT_MAX_BYTES` (`packages/adapters/src/run-execution.ts:7-35`, `:78-109`).
- **Per bot**: on a Team computer, one run at a time per bot per computer. `ComputerExecutionLease` has a unique `(computerId, botId)` constraint; acquiring while another run holds an unexpired lease throws `ComputerBusyError` and the run is re-queued (`packages/db/prisma/schema.prisma:1904-1920`; `packages/adapters/src/computer-lifecycle.ts:877-940`; `packages/adapters/src/executor.ts:363-400`). For a non-Team (`dedicated`) computer this function returns `null` (`computer-lifecycle.ts:888`) and the executor uses `acquireDedicatedScreenLeaseFence` instead (`executor.ts:373-380`), which I did not read. The docs state the general rule "A bot uses its computer for one run at a time" (stated, `docs/run-execution.md:25`). Lease length 5 min (`computer-lifecycle.ts:66`). Different bots on the same Team computer can run concurrently (same unique key; stated `docs/computer-runtime.md:42`).
- **Messages during a run**: they steer the running run instead of queuing a second one (stated, `docs/run-execution.md:25-29`). Steering claims lock the thread row with `SELECT … FROM threads … FOR UPDATE` (`packages/db/src/thread-steering.ts:46-47`). That row lock is the only per-thread lock I found; I did not trace run creation.
- **Worker role** (`apps/worker/src/index.ts`): hosts Graphile background jobs with concurrency `GRAPHILE_WORKER_CONCURRENCY`, default 4 (`:242-249`), the run recovery host, and a reconciler with Postgres-based leadership (`:251-263`). On stop it drains running jobs for up to 45 min (`packages/adapters/src/wakeup.ts:205`), which is why compose gives it `stop_grace_period: 50m` (`infra/compose/docker-compose.yml:500-502`).
- **Supervisor side**: in-memory per-bot, per-container and per-space locks (section 2.5); the `/exec` handler takes none of them (`routes.ts:396-505`).

## 7. Isolation

Between computers (implemented): separate container, separate Docker bridge network per computer (`networks.ts:36-51`), separate home directory, label-checked identity on every supervisor call (`identity.ts:64-71`), resource ceilings (`computer-spec.ts:186-193`), optional host firewall (section 2.6).

Inside one Team computer (stated and consistent with code): none. Same OS user, same home, same X server access; "screen leases coordinate tool calls, not mutually untrusted processes" (`docs/computer-runtime.md:57`). Per-bot Chromium profiles keep cookies apart only by convention (`desktop-runtime.ts:114-116`).

Between Spaces: a Team computer's key includes the space id and user id, a Private one is keyed by bot id only (`packages/db/src/computers.ts:77-81`); the supervisor also checks the container's space label on calls that go through `managedContainer` (`identity.ts:64-71`); the database uses Postgres row-level security with per-request `app.space_id` / `app.user_id` settings and a non-owner app login (`packages/db/src/row-security.ts:216`, `:281`; `infra/compose/docker-compose.yml:396-411`; stated `docs/self-host-configuration.md:115-139`). Operator mounts are the stated exception: "every bot in every Space sees every mount" (`docs/self-host-docker-computers.md:170-171`).

Between computer and host: the default spec mounts only the bot home (a subdirectory of the data dir) (`computer-spec.ts:628-648`), and operator mounts are refused if their source overlaps `/var/run`, `/run`, `/var/lib/docker` and the other denied paths, or any of the supervisor's own mount sources such as the data dir and the Docker socket (`computer-spec.ts:269-279`, `:296-305`; `routes.ts:167-171`); in open-egress mode it can reach the host's bridge address, the LAN and cloud metadata (`computer-spec.ts:202-205`).

## 8. Secrets and credentials at the infra level

- **Deployment secrets** live in `.env`: `POSTGRES_PASSWORD`, `POSTGRES_APP_PASSWORD`, `BETTER_AUTH_SECRET`, `ENCRYPTION_KEY`, `SCREEN_PROXY_SECRET`, `SANDBOX_SUPERVISOR_TOKEN`; the installer fills them with `openssl rand -hex 16/32` (stated, `docs/self-host-secrets.md:13-20`). Each compose service receives only the keys it reads (`infra/compose/docker-compose.prod.yml:11-14`).
- **Wrapped env values** (`packages/adapters/src/wrapped-env.ts`): any `.env` value may be stored as `wrapped:v1:<masterKeyId>.<wrappedKey>.<sealed>`; at process start it is unwrapped with a key provider (AES-256-GCM, 12-byte IV, variable name as associated data, so a value copied to another variable fails) (`wrapped-env.ts:4-35`, `:63-77`; called at `apps/worker/src/index.ts:10` and `apps/api/src/index.ts:7`). This protects the server's own secrets at rest; it has nothing to do with the computer.
- **Stored credentials** (model keys, bot secrets, provider keys): `EncryptedSecretStore`, format `v2:` = base64(salt16 | iv12 | tag16 | ciphertext), AES-256-GCM, key = scrypt(`ENCRYPTION_KEY`, salt; N=16384, r=8, p=1), record id as associated data (`packages/adapters/src/secrets.ts:21-30`, `:38-40`, `:101-109`). Model credentials are typed as a union (`api_key`, `oauth`, `openai_compatible`) (`packages/adapters/src/model-secret.ts:26-49`); that they are written through this store was not traced (unverified). Rotating `ENCRYPTION_KEY` makes them unreadable (stated, `docs/self-host-secrets.md:64-66`).
- **Infisical** is optional (`SECRET_STORE=infisical`, default `encrypted`) (`packages/adapters/src/secret-store-factory.ts:16-21`); the DB then holds opaque refs in the existing `ciphertext` columns, values are cached for at most 30 s / 256 entries, and `ENCRYPTION_KEY` is still needed (all stated, `docs/infisical-secrets.md:3-6`, `:32-33`, `:37`).
- **Content encryption** is separate: per-space 256-bit data keys wrapped by a master key; ciphertext `rkz1:…` bound to table/column/row/space (stated, `docs/content-encryption.md:8-16`, `:42-54`). Default on outside development (`packages/core/src/secrets-guard.ts:35-41`).
- **What reaches the computer container**:
  - Container env: only what section 2.3 lists. No model key, no `ENCRYPTION_KEY`, no supervisor token (`computer-spec.ts:610-619`).
  - Per-command env: the shell tool loads "command variables" fresh before every command and passes them in the exec request's `env`; values are registered for output redaction first (`packages/adapters/src/run-tools-computer.ts:386-393`, `:464-467`; supervisor merges them at `routes.ts:463-466`). The docs are explicit that this is not a boundary: "**The bot's shell reads this value.**" (`docs/bot-secrets.md:64`).
  - `unsetEnv` is applied by prefixing `env -u NAME … --` (`packages/adapters/src/sandbox-command-environment.ts:22-25`).
  - For providers whose exec API has no env field, values are written to a file that is opened, deleted, then sourced, so they do not appear in the process list (`packages/adapters/src/sandbox-shell-environment.ts:5-27`).
  - API-key style secrets normally never enter the computer: the backend makes the HTTP request itself (`secret_request`) (stated, `docs/bot-secrets.md:19-39`).
- **`page_secrets.py`**: per its module docstring, types saved logins, card details and pay tokens into the page over CDP, only after checking, in an isolated JS world of the field's own frame, that the frame's document is on the right site (`infra/sandboxes/computer/page_secrets.py:1-7`; the check code itself was not read). A hard-coded set of 9 payment-provider origins lists the third-party frames whose card fields a card may be typed into on a merchant's page (`page_secrets.py:31-44`). Frame depth max 4, max 32 frame sessions, CDP messages over 2 MiB skipped (`page_secrets.py:24-25`, `:58-59`).
- The in-container control service strips its own token from the environment of every child it starts and uses a fixed `PATH` that excludes `~/.local/bin` (`infra/sandboxes/computer/control.py:15-23`).

## 9. Observations relevant to Lonora (my inference, not Rakazo claims)

- Several infrastructure faults have a repair path below the tool result: a stopped container is reported as "gone" so that, per the code comment, it is booted again (`docker-sandbox.ts:273-278`; the re-boot caller was not traced); when a recently reused screen's browser is not ready, the page-browser route runs setup and retries once, except for `purchase_check` (`routes.ts:666-671`); a failed control-service call falls back to `docker exec` (`supervisor-logic.ts:123-125`). I did not verify that these are the only paths or that the model never sees the intermediate error.
- In the two places I read, the error text returned to the caller is a next step rather than a diagnosis (`routes.ts:683-701`; `page_secrets.py:48-51`: "Open the merchant's checkout with browser_navigate, then fill again."). For Lonora's "symbol not found -> gave up" case, the equivalent would be a tool error that names the recovery action (e.g. "search the broker's symbol list for names starting with XAUUSD").
- Some API errors shown to the user are short fixed strings (e.g. "Stop the bot first", `apps/api/src/routes/computer.ts:414`). I did not verify that this is systematic; several supervisor routes return the raw exception message in their JSON error (e.g. `routes.ts:372-375`, `:735-738`), and whether those reach a user was not traced (unverified).

## Weaknesses and risks seen in this area

1. **Docker socket in a root container.** The supervisor runs as root with `/var/run/docker.sock`; one bearer token is the whole boundary, and the API and worker both hold it (`infra/compose/docker-compose.prod.docker.yml:70`, `:109`; `routes.ts:132-143`; token in the env block shared by api and worker, `infra/compose/docker-compose.yml:189-190`, `:424`, `:512`). My inference from the compose comment that supervisor access "is equivalent to control of the Docker host" (`infra/compose/docker-compose.images.yml:360-361`): a compromise of the API or worker process gives the same. The prod updater has the same socket (`infra/compose/docker-compose.prod.yml:663`, `:698`).
2. **Egress restriction depends on a manual host step and degrades silently.** Blocking lives in a host iptables script; in `auto` mode (the compose default; unset means `open`, `computer-spec.ts:222`) a missing ruleset becomes open egress with only a log warning (`egress.ts:22-38`). Open egress reaches the host bridge, LAN and cloud metadata (`computer-spec.ts:202-205`). Not supported on Docker Desktop, rootless Docker or the nftables backend (`infra/compose/restrict-computer-egress.sh:27-29`). Restricted mode checks IPv4 only (`computer-spec.ts:464-465`).
3. **No outbound allowlist at all.** Even "restricted" allows the whole public internet (`infra/compose/restrict-computer-egress.sh:4`), so a prompt-injected bot can exfiltrate anything in its home or its command variables.
4. **Chromium runs with `--no-sandbox`** and processes untrusted pages (`infra/sandboxes/computer/rakazo-browser:455`; `packages/core/src/node/desktop-runtime.ts:455`). The container is the only barrier, and on a Team computer that container also holds every other bot's files and browser profiles (`docs/computer-runtime.md:57`).
5. **Team computer has no internal isolation** (same OS user, workspace, browser profiles and shell/X11 access, stated `docs/computer-runtime.md:40`, `:57`), so (my inference) a bot's shell can read another bot's browser profile on disk. Fine for one owner, but `team` is the schema default (`packages/db/prisma/schema.prisma:1807`).
6. **Command variables are plain env in the bot's shell** and readable by anything the bot runs (`docs/bot-secrets.md:64`); redaction covers only plain, base64 and URL-encoded echoes (`docs/bot-secrets.md:62`).
7. **Supervisor state is in memory.** Locks and the screen registry live in one process (`locks.ts:3-5`; `screens.ts:26-28`). A supervisor restart loses the registry, and the next screen request resets every desktop process in the container (`routes.ts:1110-1112`; `screens.ts:138-149`). Two supervisors would not be safe.
8. **Heavy per-computer footprint.** Each computer reserves up to 2 GiB RAM, 2 CPUs, 2048 pids for Xvfb + window manager + Chromium (`computer-spec.ts:107-109`), plus its own Docker network, whose address pool "run[s] out after a few dozen networks" (`networks.ts:197-198`). That is a lot of machinery if the agent mainly calls APIs.
9. **Large and intricate surface.** `routes.ts` is 1222 lines, `supervisor-logic.ts` 830, `rakazo-page-browser` 2686, `page_secrets.py` 904, `desktop-runtime.ts` builds long bash scripts as strings (e.g. `desktop-runtime.ts:798-816`, `:909`). The create/resume path alone compares about nine properties and has special cases for IPv6 fallback and restricted-bridge rekeying (`routes.ts:195-275`). Hard to copy partially.
10. **Shell-string process management.** Screens, x11vnc and websockify are found and killed with `pgrep`/`pkill -f` regexes (`desktop-runtime.ts:588`, `:618`, `:638`); fragile against process-name changes.
11. **Supervisor exec errors are disguised as command output.** An identity or lookup failure on `/exec` returns HTTP 200 with `code: 1` and the error as stderr (`routes.ts:418-421`), and the provider then pattern-matches stderr for "no such container" (`docker-sandbox.ts:298-300`). String matching on Docker error text recurs (`networks.ts:92`, `:106`, `:193`, `:216`; `computer-spec.ts:455-457`).
12. **No stated rotation path for the credential key.** With the default store, stored credentials are sealed with a key derived from `ENCRYPTION_KEY` (`packages/adapters/src/secrets.ts:101-109`); changing it makes old ciphertext unreadable (stated, `docs/self-host-secrets.md:64-66`). Short or example keys are still accepted with only a warning (`packages/core/src/secrets-guard.ts:69-78`).
13. **Docs drift.** "apt" is listed as available to computers although nothing can be installed as root (`infra/compose/restrict-computer-egress.sh:4` vs `infra/sandboxes/computer/Dockerfile:48-50`); `Dockerfile:229` exposes 16 screen ports (6080-6095) plus 7070 where the default layout uses 6080 only (`packages/core/src/node/desktop-runtime.ts:64-65`); the uv cache location differs between `docs/computer-runtime.md:129` and `desktop-runtime.ts:37-44`; `NPM_CONFIG_PREFIX` is set though the image has no Node (`computer-spec.ts:615`, `Dockerfile:53-93`).
14. **Long worker shutdown.** A worker stop can wait up to 45 minutes for running jobs, with a 50-minute compose grace period (`packages/adapters/src/wakeup.ts:205`; `infra/compose/docker-compose.yml:502`).
15. **Operator mounts are deployment-wide** and with `rw` let any Space's bot change another's files (`docs/self-host-docker-computers.md:170-171`); the denylist compares the configured path while Docker follows host symlinks, so a symlinked source can get past it (stated, `docs/self-host-docker-computers.md:174-175`).

## Not read / unsure

- Not read: `infra/sandboxes/supervisor/src/home-ownership.ts`, `computer-image.ts`, `computer-locale.ts` (only function names); `routes.ts:720-794` (observe/actions bodies); most of `control.py` (capture, xdotool allowlist), `rakazo-page-browser` beyond its header, `rakazo-focus-or-launch`, `xcapture.c`, `embed.html`, the clipboard and mobile-keyboard scripts; `infra/sandboxes/desktop/`.
- Not read: remote provider adapters (`e2b`, `daytona`, `boat`, `novita`, `createos`, `railway`, `boxd`, `instabox`, `wuying`), `host-computer-*.ts`, most of `desktop-sandbox.ts`, `kubernetes-sandbox.ts` and `incus-sandbox.ts` beyond the cited lines. Statements about them marked "(stated)" rest on docs.
- Not read: the web screen proxy and how `SCREEN_PROXY_SECRET` capabilities are built and verified; `infra/updater`, `infra/railway`, `infra/systemd`, `infra/preview`; `harden-host.sh`, `install-images.sh`, backup and PITR scripts; `docker-compose.topology.yml` beyond the first lines.
- Unsure: whether a run can start in the API process in every deployment, or only when the worker is absent. `docs/run-execution.md:3-10` says the API starts runs; I confirmed the worker's 5 s scan and the lease claim in code but did not read `RunStarter`.
- Unsure: whether there is a per-thread limit of one active run beyond steering. I found the thread row lock in steering only.
- Unsure: the exact workspace checkpoint flow for Docker (docs say Docker mounts the home directly and "only advances its revision marker", `docs/computer-runtime.md:119`); not traced in `computer-workspace.ts`.
- Unsure: Arabic font coverage in the image (no Arabic font package in `Dockerfile:71-74`).
- Unsure: whether `docker-compose.yml` (source checkout) applies any container hardening to api/worker/web; I saw none in `infra/compose/docker-compose.yml:413-547`, unlike the prod file.
- The row-level-security description comes from docs plus two `set_config` lines; the policies themselves were not read.
- No test suites were run; `*.test.ts` files were not used as evidence.

## Verification log

Independent check of this file against the repository at the commit named at the top. Each cited range was opened and compared with the sentence that cites it.

**Citations checked:** 374 `path:line` tokens in the original text (379 matched by a pattern scan, minus 5 that are host:port strings such as `127.0.0.1:3100`), plus 59 that I added while correcting, each opened at the cited lines. No citation pointed at a wrong file or beyond end of file. One range was loose (`routes.ts:1131-1194` for the stop route, which starts at 1148). All verbatim quotations matched the source, allowing for line wraps. The file sizes given in weakness 9 (1222, 830, 2686, 904 lines) are correct.

**Corrections made (before -> after):**

1. Section 1, images variant: "same services from published images" -> same service names, but Postgres defaults to `postgres:16` there, not 18.
2. Section 1, prod hardening: "every app container has `no-new-privileges`" -> the eight services listed with line numbers; added that caddy re-adds `NET_BIND_SERVICE` and that postgres/updater/supervisor do not drop capabilities.
3. Section 2.1, stop route: line range `:1131-1194` -> route `:1148-1194`, helper `:1131-1146`; added the `x-rakazo-discard-unsaved` path, which skips the quiesce step.
4. Section 2.1, browser errors: "the browser route never returns a raw failure" -> true only after validation; HTTP 400 `invalid_browser_request` and exit-code-2 refusals are passed through. Added that delivery of the text to the model was not traced.
5. Section 2.1, stopped container: "triggers a re-boot instead of surfacing to the model" -> the provider throws a "sandbox gone" error; the re-boot is what two code comments say, the caller was not traced (unverified).
6. Section 2.2, supervisor token: added the 32-character minimum and the citation for the function body (`secrets-guard.ts:80-107`).
7. Section 2.2, identity headers: "Every request also carries" four headers -> space id always, the other three only when the caller has them.
8. Section 2.2 and 2.5: two uncited conclusions (confused deputy; single supervisor instance) are now labelled as inference and given the lines they rest on.
9. Section 2.3, locale env: "from the owner's account" -> from the create request's `timezone`/`language` fields; "No model keys, no app secrets" -> scoped to the cited env list.
10. Section 2.6, egress probe: "Before the first restricted computer starts" -> at supervisor start and on each create, cached; "silently downgrades ... with a log warning" -> "downgrades with only a log warning"; added that explicit `restricted` throws and that an unset variable means `open`. Probe network name corrected (`rakazo-egress-probe`, bridge `rakazo-cprobe`).
11. Section 2.7, gateway: citation `desktop-runtime.ts:813` showed only the x11vnc line -> `:806-824` (socket plus token file), and the "one gateway" wording is marked as stated in docs.
12. Section 2.7, screen limit: added that unset/`0` means the technical maximum, not unlimited, and the exact eviction filter.
13. Section 3.2, lazy desktops: "desktops and browsers start on first graphical use" -> docs and code disagree in part: `start.sh` starts the primary display stack at boot; only per-screen setup is lazy. Where the browser is launched is marked unverified.
14. Section 3.4: `EXPOSE` list corrected to include 7070; added one verified docs/code disagreement about the uv cache location.
15. Section 4.2, takeover: added the second condition (`controlRunId`) and the citation for the blocking rule (`apps/api/src/computer-status.ts:14-29`).
16. Section 4.3, uptime cap: "for Docker/Kubernetes/Incus" -> "providers that do not bill while running"; the list of providers was not in the cited lines.
17. Section 4.3, stop: "the workspace is checkpointed and browser profiles are quiesced" (cited to the supervisor route) -> the route only quiesces browser profiles; checkpointing is app-side and stated in docs, and for Docker the docs say it only advances a revision marker. The 5 GiB / one million files limit is scoped to transferred workspaces as the doc paragraph is.
18. Section 5, `none`: "every method throws" -> what was actually read (15 `fail()` calls counted, not each method read).
19. Section 5, remote providers: "the provider disk is a cache" -> the doc's own wording about the provider reference.
20. Section 6: "Exactly-once claim" -> "Lease claim (one claimer at a time)"; an expired lease can be reclaimed. Added the Space-deletion guard.
21. Section 6, per-bot lease: the lease-table mechanism applies to Team computers only; `dedicated` computers take a different path that was not read.
22. Section 6, recovery scan: location in the worker is now marked as stated; interval cited to `run-wakeup.ts:218-220`.
23. Section 6, supervisor: "exec calls themselves are not serialized" given its citation.
24. Section 7: "computers are keyed by space" -> only the Team key contains the space id; "the container never gets the Docker socket or the data dir" -> the home is a subdirectory of the data dir; the denylist applies to operator mounts.
25. Section 8: model credentials "stored through that store" -> not traced (unverified); Infisical "opaque refs" given its doc line and marked stated; `page_secrets.py` behaviour marked as docstring-level, and "card fields are accepted only in ..." -> the set lists third-party frames, not every place a card may be typed.
26. Section 9: "The model sees a tool error only after those paths are exhausted" and "Technical detail stays out of user-visible text by construction" -> both softened; the second is contradicted in part by supervisor routes that return raw exception messages.
27. Weaknesses 1, 2, 5, 12, 13, 14, 15: added missing citations, marked two conclusions as inference, removed "on a containerized supervisor" (not in the cited doc lines), and corrected "45-50 minutes" to a 45-minute drain inside a 50-minute grace period.

**Remaining doubts:**

- Whether the "sandbox gone" error leads to an automatic re-boot within the same tool call, and what the model sees meanwhile. Only comments say so.
- Whether supervisor error strings reach the model or the user unchanged. The app-side tool wrappers (`run-tools-computer.ts` beyond lines 386-393 and 464-467) were not read.
- Where the browser process is first launched (`ensureScreenCommand` body not read in full).
- The takeover rule depends on `ACTIVE_RUN_STATUSES`, whose contents were not opened.
- `acquireDedicatedScreenLeaseFence` (Private computers) was not read, so "one run at a time per bot" is confirmed in code only for Team computers.
- `page_secrets.py` origin checks, `control.py` xdotool allowlist, and `rakazo-page-browser` beyond its header remain unread; statements about them rest on docstrings and constants.
- Row-level security policies were not read; only the two `set_config` lines and the docs.
- The statement that the worker hosts the 5-second recovery scan rests on docs; `RunWorkerHost` wiring was seen (`apps/worker/src/index.ts:245`) but not followed into `run-wakeup.ts`.
- No tests were run and no container was started; everything here is from reading source.
