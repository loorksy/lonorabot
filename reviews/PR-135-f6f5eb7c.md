# PR #135 at f6f5eb7c: FINDINGS (0 high, 1 medium, 2 low), with a rebase request

- PR: #135 (W-OWNER). New since 3b38c97f: f6f5eb7c, "The server checks only that the owner named the source; the agent judges intent".
- Reviewer: R-AGENT, 2026-11-12T09:29Z
- Verdict: FINDINGS

## Rebase request (not a finding)

Main merged #134 as different commits, so main's 0131 sits on 0090 with 0120 → 0145 above it. `git merge-tree 82ca3b03 f6f5eb7c` conflicts in 10 files (add/add on 0131, `manifest.json`, `lonora.md`, `owner_actions.py` in api, contracts and db, `agent_state.py`). Rebase only the #135 commits onto main, set 0132's `down_revision = "0145_metaapi_token"`, and regenerate the manifest.

## Design assessment

- 10.3.2 and 14.3.5 are met: the owner's typed message, checked by `owner_message_id` with no card, plus a strict name match.
- Probe on a real database: a tainted owner turn, a source the owner did not name, and a routine wake are each refused, including `mcp_trust` with `tier=write_nonfinancial`.
- Earlier F1 and F2 (word-matching misfires) are superseded, since the server no longer reads intent. F3 (natural requests refused) is fixed.
- For the lead, a design call and not a finding: the MCP write tier is now the agent's choice alone. The probe gives `write_nonfinancial` for "Trust Notes, read only. It must never write." and for "What did I save in Notes yesterday?" whenever the model passes `tier=write_nonfinancial`. Money tools stay blocked. The mandate does not require more, but the owner's explicit "read only" is guarded only by model judgment.

## Finding 1 (medium): inspecting a repository the owner only mentions, or refuses, trusts it

- `packages/agent-runtime/src/lonora_agent/skills/access.py:229-231` always calls `repository_trusted` (`lifecycle.py:216-244`). With intent checks gone, any naming trusts, and the tool has no way to inspect without trusting, so the agent cannot exercise the judgment the commit gives it. The description (`packages/tools/src/lonora_tools/skills.py:172`, "Trust applies only when the owner's own message names the repository and asks for it") is false for this tool.
- Probe at this head (run by me), with github.com revoked:
  - "What is in pubXXXX/tools? Don't add it, just tell me." gives `source_trusted: True`, row via `owner_message`;
  - «لا تثق في pubXXXX/tools، فقط أخبرني ماذا فيه» gives `source_trusted: True`, row via `owner_message`.
- Fix: add `trust: bool = False` to `SkillRepositoryInput` ("true only when the owner asks to trust this repository"), and call `repository_trusted` only when it is true. Add tests: omitted leaves no row; true on a named, clean turn adds one; true on a tainted or routine run is refused.

## Finding 2 (low): tool descriptions tie the refusal code to "asks for it"

`feeds.py:183-185`, `mcp.py:473-476` and `skills.py:131` say trust applies "only when the owner's own message names it and asks for it (trust_requires_owner_message otherwise)". The server refuses only on a missing name or a tainted run. Reword to say that asking is the agent's judgment, and that the server refuses when the message does not name the source or the run read third-party content.

## Finding 3 (low): lonora.md does not mention the new tier argument (0.4)

`packages/agent-runtime/resources/system/lonora.md:525` says "needs_write_trust … call mcp_trust first". With `tier` defaulting to `read`, that leaves the tool waiting. Say "…when he asks it to write: call mcp_trust with tier=write_nonfinancial", and regenerate the manifest.

## What was checked

- `test_trusted_sources`: 17 passed.
- `check_trusted_sources`, `check_trust_migration` and `check_mcp_directory`: exit 0.
- Core 14.1.2: all pass (129 in the pytest set).
- Policy, capability and teammate tests: 94 passed.
- No `asks_trust`, `asks_writes` or `owner_did_not_ask_for_writes` is left anywhere.
