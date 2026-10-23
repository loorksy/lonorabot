# Public Skill repository inspection

`skill_repository_inspect` extends the existing Agent tool registry and injected
`RunSkillAccess`. It inspects a public GitHub repository without installing its
instructions, executing its scripts, granting tools, or changing trading authority.

The Agent supplies `repository_url` and an optional `ref`. A named ref is resolved
with a one-entry commit listing, then only the immutable commit archive is read.
A supplied full commit SHA goes directly to the corresponding archive. Results
include the commit, archive digest, `SKILL.md` identities/descriptions/digests,
utility paths/digests, statically detected Python imports, dependency filenames,
license-file digests, format errors, and explicit validation limitations.

This operation is the inspection foundation, not an installation action. The
separate [pinned package lifecycle](skill-executable-lifecycle.md) now imports,
validates and activates the supported bounded package subset. Python
AST parsing checks syntax and imports; it does not prove code safe. Dynamic
dependencies are unresolved. Import names are not pinned package requirements.
Other script languages are reported as not syntax-validated. Every package still
requires adaptation review and isolated execution before scripts can be activated.

## Boundaries

- Only canonical HTTPS `github.com/owner/repository` URLs are accepted. Credentials,
  alternate hosts, URL query parameters and fragments are rejected.
- Requests target GitHub's API and immutable codeload archives. Redirects are
  disabled even if a supplied HTTP client enables them.
- Downloads and expanded archive content are bounded to 8 MiB and 512 files.
  Commit-list responses and individual inspected Python sources have smaller
  bounds. Unsafe paths, symlinks, duplicate normalized paths and mixed roots fail.
- No archive member is extracted to the host. Package code, setup hooks,
  dependency installers and repository tests are never executed by inspection.
- Existing Run ownership and lease checks occur before network access and again
  before delivery. The normal ToolLoop stores its result and provenance.
- `format_compatible` describes instruction format only. It is not permission,
  security approval, instrument equivalence, or proof that the procedure can run.
- Source descriptions remain untrusted tool-result data. Broker credentials and
  financial services are never supplied to inspected packages.

## Reference acceptance evidence

The public repository `Jakeschincariol/day-trader-skill` was inspected through the
implemented HTTPS path, both by full SHA and by resolving `HEAD`:

- Commit: `3d0f4ef6986f4984b7c6bd46f7ff4f87744c3abd`.
- Archive SHA-256: `1a18cb28faa414c077f7cd3dd39397e5f9eecd2d324f9ffde507bc7b448f51cc`.
- 85 files, 11 instruction documents and 11 utility scripts.
- 10 instruction documents fit the current format limits; `trader-risk` reports
  `skill_frontmatter_invalid` under the existing bounded metadata validator.
- No package code executed; no Skill installed; no authority granted.

Source review found US-equity session and unofficial Yahoo-data assumptions, plus
an external broker procedure with file-based risk/approval state and other broker
connectors. Those cannot be transplanted as Lonora's financial authority. Adapting
the analytical portions requires explicit dataset, session, volume and exact
broker-symbol validation. Replacing a ticker string with a broker-suffixed symbol
does not establish equivalence.

The Nanobot and Hermes references were pinned locally for source review at
`df63526ddfb3674619231f0daf4d25ba3c8b7e54` and
`4d04303818b61bf3aa09278af48356315515965b`, respectively. Reviewed paths include
Nanobot's Skill discovery and shell/sandbox separation, and Hermes' terminal
environment, Docker isolation and quarantined Skill installation. These are
reference patterns; their runtimes and permission models were not imported.

## Verification

`tests/test_skill_repository.py` covers non-execution, immutable revision
resolution, archive/source limits, traversal, symlinks, invalid metadata/source,
URL restrictions, redirects, explicit network errors and read-only registration.
`tests/check_skill_repository.py` exercises the real AgentRuntime/ToolLoop and
PostgreSQL result path with scripted public HTTP responses. It verifies that no
Skill activation or financial journal entry occurs. The latter is included in
the existing isolated foundation runner.
