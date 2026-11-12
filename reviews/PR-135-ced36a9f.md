# PR #135 at ced36a9f: FINDINGS (0 high, 1 medium, 2 low), with a rebase request

- PR: #135, wowner/5-trust-from-words (W-OWNER). One commit on #134 (b425b6fe..ced36a9f).
- Reviewer: R-AGENT, 2026-11-12T07:37Z
- Verdict: FINDINGS

## Rebase request (not a finding)

The same as #134: rechain 0131 to 0085, resolve the .po and manifest conflicts, and regenerate the manifest. 0132 chains on 0131.

## Finding 1 (medium): an MCP server gets the write tier when the owner said "read only", or used "write" about something else

- File: `packages/tools/src/lonora_tools/source_trust.py:107-114`. `asks_writes` looks only for a negation in the four words before a writing word, and `mcp.py:362-364` then grants `write_nonfinancial`.
- Evidence: probe at this head. Each of these returns `asks_writes= True`:
  - "Use Notes to write me a summary"
  - "Trust Notes for reading only; I will write the notes myself"
  - "Trust Notes read-only, write nothing"
  - "اكتب لي ملخصا من Notes"
- Impact: the owner's explicit "read only" becomes non-financial write authority for the server.
- Fix:
  - Return False on a read-only phrase ("read only", "read-only", "reading only", «للقراءة فقط», «قراءة فقط»).
  - Treat "nothing", "none" or «لا شيء» after the writing word as negation.
  - Count the writing word only when the server is its subject ("let it write", «اسمح له بالكتابة»).
  - Add these strings to `test_owner_words_ask_for_writing_only_in_so_many_words`.

## Finding 2 (low): skill_repository_inspect is marked read_only but now writes trust

`packages/tools/src/lonora_tools/skills.py:175` keeps `read_only=True`, while `access.py:234` now persists a trust row through `repository_trusted`. `read_only` drives permission, parallel batching and crash-replay (`base.py:100,111`). Mark it non-read-only and replay-safe, or do the trust only in `skill_package_import`.

## Finding 3 (low): naming a source in passing counts as asking to trust it

Probe: "Take notes on gold today" names the server "Notes", and "what does reuters.com say about gold?" names `reuters.com`. Both return True. In an untainted owner run, only the model's judgment separates mentioning a source from trusting it. Require a trust or subscribe intent near the name, or record this as a lead decision.

## Rejected candidates

- 6.10 taint: any third-party read in the run refuses trust, including inside an owner-triggered run. Tested for MCP, skills and feeds.
- Routine and wake runs: refused before contact.
- Look-alike domains, sub-domains and repository paths: rejected by strict matching.
- The feed check read: it does not taint and is not shown to the model.
- Removed kind leftovers: none.
- Clients: updated.
- Migration 0132: round trip passes.
- 14.3.8: trust paths still work.

## What was checked

- `check_trust_migration` (3/3) and `check_trusted_sources` PASS.
- Trust, owner-action, taint and readiness tests: 102 passed, 6 skipped (existing timezone skips).
- `check_simple_lonora` exits 0.
- Core 14.1.2 at this head: all pass (five scripts; 101 passed).
