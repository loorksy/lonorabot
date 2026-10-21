# Analytical container execution boundary

This is the verified execution substrate for the agent-first mandate, **not yet
an enabled Agent tool or a production workspace service**. `lonora_agent.workspace`
runs one analytical command in a fresh, immutable-image Docker container. It
accepts a bounded snapshot and returns exit status, actual command output, regular
file bytes and host-computed SHA-256 digests. It does not create another Agent,
model loop, scheduler, broker adapter or financial authority.

## Privilege boundary

The adapter belongs in a dedicated trusted host process. It requires access to
the local Docker daemon; that access must never be mounted into Lonora's API,
Gateway or an analytical job. No tool registry entry or production Compose
socket mount is introduced by this increment. The future ownership bridge must
accept only owned, fenced Agent operations and fixed execution requests, never
Docker arguments, image selection, host paths, environment variables or mounts.

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
orphan; restart policy is `no`. A host startup reaper for stopped labelled
containers is still needed before production activation. Durable file revisions,
operation receipts, concurrency limits across jobs and restart recovery are not
implemented by this stateless substrate.

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

## Remaining integration

1. A dedicated trusted host bridge with bounded global concurrency and startup
   cleanup; no Docker socket in application services.
2. Existing Agent/owner/lease checks, operation identities, persistent snapshot
   revisions and conflict handling; expose shell/files through ordinary tools.
3. Existing artifact export and visual inspection, retaining provenance and
   separating analytical evidence from execution authority.
4. Reviewed pinned dependencies, faithful Skill adaptation, executable tests,
   installation, update and rollback through the existing owned Skill lifecycle.

Generated code can analyze supplied market data. Live trades continue to require
the existing typed, authorized, risk-checked, journaled and reconciled services.
