Superseded by VISION.md

# Reusable procedures from the owner's workspace

The ordinary Agent may write a bounded analytical procedure in the owner's persistent
workspace (VISION.md 7.1; `docs/operations.md`, "The workspace"), then register it with
`skill_package_create`. This creates an owned, versioned procedure in the same Skill
catalog. It does not modify the application, create another Agent, or grant trading
authority. Generated instructions remain lower-trust material.

Creation lists one directory of the workspace (relative to the agent's home) as the
agent's own Unix user and reads each file through the workspace client, whose secret
scan refuses a file holding a secret. The directory must contain a valid `SKILL.md`.
Canonical relative paths, UTF-8 text, file/count/byte limits and nested-package
boundaries are validated, then the files are copied as `skills/<id>/<version>/` into the
agent's **private package store** (the table of the former analytical workspace, kept for
this: packages are the agent's own, while workspace files are shared by every agent).
The store has no revision the model sees; files are written in the same transaction that
publishes the version. The existing utility scanner, disabled installation, graph
validation, immutable versions, leases, receipts, rollback, disable/remove and
revocations are reused. New procedures start disabled.

Provenance distinguishes `github` from `workspace`. The model sees a workspace package
labelled `agent_authored` and a public import labelled `external`, never as
owner-supplied (`docs/agent-memory-and-recall.md`). Local provenance stores the actual
Agent, Run, source directory and the digest of the selected source; a package made from
the former analytical workspace also keeps that workspace's revision. A bounded prepared
receipt preserves the exact selected input across a crash before catalog publication;
a retry does not read changed source.

Every declared Python utility must pass a smoke test before activation:
`skill_package_validate` copies the package from the store into `.skill-validation/` in
the agent's home and runs the utility there for at most 30 seconds. The receipt binds the
exact source hash and the actual exit status. The workspace is persistent and agents
install into it themselves, so no image is pinned: a receipt holds as long as the stored
source is unchanged. A utility that rewrites itself changes only its copy. A passing
smoke test establishes neither strategy quality nor semantic equivalence with an external
strategy, and guarantees no profit or safe trading recommendation.

Generic owner updates may edit ordinary owner instructions. A managed package cannot be
enabled or rewritten through that route; its validated lifecycle remains authoritative.
Owners may still disable or delete a package, including one with damaged metadata. The
authenticated owner catalog checks the same stored source and validation. Current
eligibility, exact retained versions and revocations remain authoritative when an old
checkpoint resumes.

Missing dependencies and unsupported binaries remain explicit failures. All broker
mutations still require the existing financial authority, fresh preflight, controls,
journal and independent reconciliation.
