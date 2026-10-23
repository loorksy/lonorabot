# Reusable procedures from the owned analytical workspace

The ordinary Agent may write a bounded analytical procedure with the existing
workspace operations, then register it using `skill_package_create`. This creates
an owned, versioned procedure in the same Skill catalog. It does not modify the
application, install host dependencies, create another Agent, or grant trading
authority. Generated instructions remain lower-trust material.

Creation reads one exact current Agent workspace revision and source directory.
The directory must contain a valid `SKILL.md`. Canonical relative paths, UTF-8
text, file/count/byte limits and nested-package boundaries are validated before
copying into `skills/<id>/<version>/`. The existing utility scanner, disabled
installation, graph validation, immutable versions, leases, receipts, rollback,
disable/remove and revocations are reused. New procedures start disabled.

Provenance distinguishes `github` from `workspace`. Existing Git sources keep
their genuine repository, full commit and archive digest. Local provenance stores
the actual Agent, Run, original revision, source directory and canonical selected
snapshot digest. Local code never receives a fabricated Git commit. A bounded
prepared receipt preserves the exact selected input across a crash between file
materialization and catalog persistence; retries do not silently import different
source from a newer revision.

Every declared Python utility must pass the existing isolated smoke validation.
Receipts bind exact source hashes and the actual immutable execution image.
Activation compares these receipts to the current trusted host profile. Changing
that image requires revalidation for both imported and workspace-created packages.
A passing smoke test establishes neither strategy quality nor semantic equivalence
with an external strategy, and guarantees no profit or safe trading recommendation.

The existing Unix host exposes only its configured immutable image through a
bounded `/profile` response. It does not expose Docker control or credentials.
The selected package pins that image to its current Run. Subsequent execution
checks the pin before container work and checks the actual returned receipt;
silently switching to a different image is rejected. Completed historical
operations still replay their saved result without rerunning on a new image.
Ordinary file inspection remains available while execution is unavailable.

Generic owner updates may edit ordinary owner instructions. A managed package
cannot be enabled or rewritten through that route; its validated lifecycle remains
authoritative. Owners may still disable or delete a package, including one with
damaged metadata. The authenticated owner catalog checks the same current source and image, so
unconfigured or changed execution is unavailable there too. Current eligibility,
exact retained versions and revocations
remain authoritative when an old checkpoint resumes. Owner-supplied Run metadata
cannot forge an execution-image pin.

This capability supports bounded text/Python procedures on the reviewed dependency
image. It does not convert arbitrary frameworks, install arbitrary packages, or
prove an imported stock-allocation strategy equivalent to a broker-lot strategy.
Missing dependencies and unsupported binaries remain explicit failures. All broker
mutations still require the existing financial authority, fresh preflight, controls,
journal and independent reconciliation.
