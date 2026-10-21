# Analytical container execution boundary

Four ordinary tools now expose persistent analytical files and optional isolated
execution through the existing Agent: `workspace_inspect`, `workspace_read`,
`workspace_update`, and `workspace_execute`. Files and operation receipts live in
PostgreSQL. A dedicated Unix-socket bridge runs commands in fresh, immutable-image
containers and returns actual exit status, bounded output and validated files.
No new Agent, model loop, scheduler, broker adapter or financial authority exists.

This capability is verified in development, **not installed or activated in
production**. File management needs migration `0028_analytical_workspace`;
execution additionally requires an explicitly configured host socket. Missing
configuration is reported as unavailable, never replaced with a host subprocess.

## Privilege boundary

The adapter runs in a dedicated trusted host process, `lonora_agent.workspace_host`.
Only that process can access the local Docker daemon. The API/Gateway receive a
restricted Unix socket, never the Docker socket. The protocol accepts only a
bounded file snapshot, command and deadline: no image, mount, host path,
environment, Docker flags, account credential or financial request is accepted.
The host has no model or database connection and needs no Lonora secret.

The socket directory is mode 0750, the socket 0660; the configured Unix group is
the trusted application principal. Requests are bounded to 12 MiB, body reads to
ten seconds and execution concurrency to two by default (maximum four), with
immediate busy responses rather than an unbounded queue. Startup takes an
exclusive filesystem lock before removing only this host namespace’s labelled
analytical orphan containers. The namespace is derived from the canonical socket
directory, so another host directory cannot reap its live jobs. A second host cannot clean up another active host's jobs. Transport
uses the fixed local socket with proxy inheritance, redirects and retries disabled.

The administrator builds `infra/analysis/Dockerfile`, reviews its contents and
configures its full local `sha256:` image ID. Execution never pulls an image and
does not accept mutable tags. The base Python image is digest-pinned; the image
contains no Lonora application, broker SDK, credentials or project checkout.
Only Python's standard library and the base shell are available initially.
Third-party dependency installation remains unimplemented and network-disabled.

Each command runs as UID/GID 10001, with zero effective capabilities and
`no-new-privileges`, in private PID, IPC, cgroup and network namespaces. The root
filesystem is read-only. No host directories, service data, credentials or Docker
socket are mounted. Docker's implicit proxy variables are explicitly emptied,
and the command starts with a fixed clean environment. Network mode is `none`,
including for dependency installers and attempts to contact broker endpoints.

A small trusted container control path runs as container root with **CAP_KILL
only**. It runs fixed, isolated Python code to terminate UID10001 descendants
before collecting output. The model cannot select this identity or control
program, gain capabilities, or kill the root controller. Docker's init process
reaps orphan descendants. This is container-local supervision, not host root
access. Command content never becomes control-program source.

## Bounds and snapshot behavior

| Resource | Enforced bound |
| --- | --- |
| Aggregate container memory and swap | 256 MiB, swap disabled beyond memory limit |
| Aggregate CPU | 0.5 CPU |
| Processes | 32 |
| Root filesystem | Read-only |
| `/work` and `/tmp` | 32 MiB and 8 MiB tmpfs; nodev/nosuid/noexec |
| Default job deadline / maximum | 30 / 45 seconds, including preparation and export |
| Command length | 32 KiB |
| stdout and stderr | 128 KiB each |
| Returned files | 128 files, 2 MiB each, 8 MiB total |
| Snapshot transport | 12 MiB |
| Paths | Relative, canonical, at most 256 characters and eight components |

The adapter checks the **actual** cgroup memory, PID and CPU limits before any
untrusted code executes; an unavailable or mismatched limit fails closed. Input
files are validated on the host and bootstrapped by a fixed Python program.
Docker copy cannot populate a read-only container root and does not reliably
export tmpfs contents, so it is deliberately not the snapshot mechanism.

After the shell returns, the trusted controller kills remaining job descendants.
An isolated, fixed exporter then reads only regular files without following
links. Symlinks, hardlinks, FIFOs and other special files fail closed. The host
independently revalidates exported paths, file sizes, counts, total size and
base64 structure, and computes digests. No archive is extracted to the host.
All file contents and analytical output remain untrusted evidence.

The entire container is force-removed after success, failure, timeout, excessive
output or cancellation. Cleanup waits are bounded and an unconfirmed cleanup
logs a constant diagnostic without command contents or secrets. If the host
process disappears, the fixed 120-second root workload lifetime bounds a running
orphan; restart policy is `no`. The exclusive host
startup reaper removes this host namespace’s labelled orphan containers before serving requests.
Unconfirmed cleanup is never treated as proof that a job disappeared.

## Persistent ownership, revisions and recovery

Migration `0028_analytical_workspace` adds two focused tables. One row per Agent
stores its current bounded binary snapshot, revision and active reservation. An
operation row stores typed Agent/Run/fence/request identity, status and bounded
receipt. Only the current file snapshot is retained; receipts contain file
metadata and output, not duplicate filesystem copies. Agent deletion cascades both
tables; Run deletion removes its operation receipts. Ownership is derived from
the existing Agent, avoiding a second owner or permission system.

Every access checks the current owned Agent, Thread, Run and lease. Mutations also
respect paused Agents and the existing subagent/observe-only restriction. Reads
name an exact revision. Writes atomically compare that revision, apply bounded
UTF-8 replacements/deletions and store a receipt under the canonical call identity.
Duplicate identical calls return that receipt; reusing an identity with changed
arguments fails. Concurrent stale writes never overwrite newer files.

Execution reserves a revision under a short database transaction, then releases
all database locks before IPC. Publication checks the current lease/fence and
reservation again in one transaction. A failed, timed-out, cancelled or superseded
operation cannot advance the filesystem. Ordinary nonzero process exits still
return their actual status and bounded files, allowing the Agent to inspect and
repair failed analysis. A replacement worker abandons an interrupted reservation;
resuming that call returns its interrupted result instead of running it again.
Late old-worker results cannot overwrite the replacement's files. Inspection
projects whether a reservation is genuinely running or needs recovery.

## Reproduce the actual container acceptance

From the repository root, using the local Docker daemon:

```sh
docker --host=unix:///var/run/docker.sock build --network=none \
  -t lonora-analysis:development infra/analysis
analysis_image_id="$(docker --host=unix:///var/run/docker.sock image inspect \
  lonora-analysis:development --format '{{.Id}}')"
.venv/bin/python tests/check_analytical_workspace.py "$analysis_image_id"
.venv/bin/pytest -q tests/test_analytical_workspace.py
```

The standalone acceptance intentionally fails if Docker/cgroups are unavailable;
it does not skip or silently fall back to a host subprocess. It checks actual
file roundtrip and reuse, UID/capabilities/seccomp, missing secrets and broker
packages, read-only root, absent host checkout/socket, disabled network,
concurrent independent snapshots, actual command failure, unsafe files, excessive
output, deadlines, detached descendants, process limits, memory and scratch limits,
cancellation and final absence of leaked containers. It uses no broker or DB.

On 2026-10-21, 31 offline cases and 14 real container acceptance checks passed
in the development environment (Docker 28.4.0, cgroup v2). The VPS was inspected
read-only: Docker 29.8.1 and cgroup v2 are available, but this execution boundary
has **not** been installed or verified there. No production financial operation
was performed.

## Host bridge setup and activation

Development launch, using the reviewed local image ID and the existing repository
virtual environment (the `workspace-host` optional extra declares its HTTP server
dependencies):

```sh
.venv/bin/python -m lonora_agent.workspace_host \
  --image "$analysis_image_id" --directory /run/lonora-analysis \
  --group 10001 --concurrency 2
```

The service requires a dedicated trusted host account with Docker control, a
reviewed installed Agent build and no application `.env`. The supplied
`infra/analysis/lonora-analysis.service` is a production installation template:
its dedicated virtual environment and reviewed image ID must exist first. Its
only environment file contains `LONORA_ANALYSIS_IMAGE`, not DB/model/broker
credentials. The template restricts host network address families to Unix sockets
and defines separate control-process resource limits. Its systemd restrictions
have not been runtime-verified on the VPS in this increment.

Set `LONORA_WORKSPACE_SOCKET` to the absolute socket path for Gateway execution.
`infra/analysis/compose.workspace.yml` is an optional overlay for the existing
production Compose file; it binds only the socket directory read-only and refuses
to create a missing host path. Base production Compose remains unchanged. Its
merged configuration was validated with non-secret placeholder interpolation;
no production service, credential, grant or broker state was changed.

`tests/check_workspace_runtime.py` exercises actual PostgreSQL ownership,
revision conflicts, duplicate calls, failed-call replay, cancellation, late fenced
results, fresh service-object recovery, deletion and the canonical Agent loop.
It is registered in the isolated foundation runner, alongside the empty disposable
DB migration upgrade/downgrade/upgrade check.

`tests/check_workspace_container_runtime.py <image-id>` additionally exercises
actual PostgreSQL, a task-owned Unix host process and real Docker through the
same Agent loop. A scripted model saves analysis code/data, runs Python, reads the
computed output, restarts the host and reruns analysis from the retained files.
It verifies actual orphan cleanup, socket permissions, concurrency rejection and
exclusive startup locking and preservation of a different host namespace, with
unchanged financial journal/approval counts.
Use an explicitly migrated disposable PostgreSQL database accepted by the existing
fixture; this check is separate from the default Docker-independent foundation
runner. It never runs against production money or a production database.

## Remaining integration

- Export generated workspace reports/images through the existing owned artifact
  and visual-inspection path; binary files currently have metadata but no direct
  `workspace_read` text view.
- Reviewed dependency images/installation, faithful Skill adaptation, isolated
  utility validation and executable Skill installation/update/rollback.
- Production systemd activation and recovery verification, after review of the
  integration branch. No default production activation is included here.

Generated code analyzes supplied data. Live trades continue through the existing
typed, authorized, risk-checked, journaled and reconciled services.
