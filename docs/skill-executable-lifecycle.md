Superseded by VISION.md

# Pinned executable Skill packages

The existing Agent catalog, Run snapshots, revocation controls and analytical
workspace now share one package lifecycle. There is no second Skill runtime or
financial permission system.

## Import and adaptation

An import first checks the owner's trusted sources (`docs/trusted-sources.md`): inside
them (github.com by default) it goes on silently; outside them it raises one owner card
and fetches nothing. Instructions-only packages need no analysis host.

`skill_repository_inspect` discovers documents, utility hashes, Python imports,
dependency filenames and licensing without executing source. `skill_package_import`
then accepts one compatible `SKILL.md` at a full immutable Git commit, an adapted
instruction document, and an explicit review of original behavior, adapted
behavior, assumptions and limitations. The review is evidence of what was
declared; it does not independently establish semantic equivalence.

Import preserves the selected subtree's original UTF-8 files and applicable
license files under `skills/<identity>/<semantic-version>/`. Nested Skills are
separate packages. Archives are never extracted on the application host, setup
hooks never run during import, and publisher permission declarations are ignored.
The import starts disabled. Limits are 64 selected files, 256 KiB per file,
1 MiB total, and the existing workspace path/depth bounds.

The package records its repository commit, archive/document/file digests,
external import names, dependencies outside the selected subtree, adaptation
review and executable paths. Up to eight immutable versions are retained in the
existing Skill resource state. Updates require the current optimistic resource
version and a new semantic version. Existing Run instruction snapshots remain
pinned to their original content.

## Controlled validation and lifecycle

`skill_package_validate` runs one exact stored Python utility, with bounded quoted
arguments, in the owner's persistent workspace, from a fresh copy of the stored version at
`skills/<id>/<version>/` in the agent's home (`docs/workspace-created-skills.md`). The
owner, Agent, Thread and Run lease are checked before and after execution, and the
stored source hashes must match before and after. A script that changes its own
source changes only its copy.

Validation records actual exit status, source digest and arguments. A missing dependency produces the real failed exit and bounded stderr.
Identical retries return the original receipt, including failures; changed
arguments cannot reuse that identity. A call interrupted before its receipt is not run
again on its own (the workspace has internet access): the agent runs it again. Passing a smoke test is not proof of
security, predictive accuracy, instrument equivalence or full strategy semantics.

`skill_package_control` supports activation, disabling, rollback and removal.
Every executable utility must have a successful matching validation before
activation. Unsupported non-Python utilities prevent activation. Rollback restores
retained instructions disabled and requires an explicit later activation.
Activation writes the same fresh copy. Removal deletes the catalog resource and retains
the stored files. Existing dependency-graph and semantic-version revocations remain
authoritative. A removed identity with a revoked version cannot be reimported
under a new label to erase that denial.

## Deliberate limits

This is a bounded public-package import path, not automatic conversion of every
external Agent framework. Binary packages, arbitrary root/shared module layouts,
unavailable dependencies and other executable languages are reported or rejected.
Import names are not trusted package-install instructions: validation installs
nothing; a dependency is available only if it is already in the workspace.

Imported instructions and Python receive no broker credentials, host filesystem or
additional trading permission. Ordinary financial actions
still pass through the existing typed executor, approvals or signed authority,
risk limits, journal and reconciliation.

## Verification

`tests/test_skill_packages.py` covers archive/path/size/identity restrictions,
non-execution of hooks, immutable revisions and tool-effect contracts.
`tests/check_skill_packages.py` exercises the actual Agent loop, PostgreSQL, the
package store and catalog lifecycle, with a stand-in workspace supervisor. It covers import/validation/activation/view, immutable
updates, replay, rollback, ownership, helper (subagent) denial, revocation/relabel
denial, removal, stale leases, missing dependencies and a self-modifying utility.
Financial journal and approval counts remain unchanged.

## Actual public-source acceptance

On 2026-10-23 the pinned public repository
`Jakeschincariol/day-trader-skill@3d0f4ef6986f4984b7c6bd46f7ff4f87744c3abd`
was fetched over verified HTTPS. Its eleven documents were enumerated, and
`trader-budget` was imported with explicit diagnostic-only adapted instructions,
source/license hashes and original utility. The stock allocation utility ran in
an actual networkless container using a declared AAPL price scenario and budget,
and activated only after its matching utility receipt. Financial journal and
approval counts stayed zero. Whole-stock-share sizing was explicitly identified
as incompatible with gold broker lots without verified monetary contract metadata;
this is not a claim of gold-strategy adaptation.

That acceptance ran in the former networkless container.
`tests/check_public_skill_package.py <workspace-supervisor-socket>` now reproduces it
in the persistent workspace: an optional network acceptance against an explicitly migrated disposable PostgreSQL DB.
It is separate from the default offline checks. Source behavior can require actual
inputs: the first probe correctly rejected a missing scenario price rather than
inventing one; a declared fixture price supplied that missing input.
