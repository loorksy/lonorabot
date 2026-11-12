# PR #81 at f6affc53: FINDINGS (0 high, 1 medium, 1 low), with a rebase request

- PR: #81, wteam/1-lead-role (W-TEAM), "Lonora's lead powers are a built-in role, not a grant (14.3.15)".
- Own commits: b1612e20, 624b0084, 5f75c31a (merge of old main 4d4348ae) and f6affc53. Own diff: `git diff 4d4348ae f6affc53`, 16 files.
- Reviewer: R-AGENT, 2026-11-12T12:34Z
- Verdict: FINDINGS

## Rebase request (not a finding)

`git merge-tree` with main e67be56d conflicts in 6 files: `docs/supervision.md`, `lonora.md`, `manifest.json`, `collaboration/subagents.py`, `tool_exposure.py` and `tools/supervision.py`. The lead's earlier "rebase" ask was met only against 4d4348ae. Rebase on main and regenerate the manifest.

## Finding 1 (medium, 14.3.15): the PR claims 14.3.15, but bullet 3 is not met at this commit

- VISION 14.3.15: "`grant_default` and `seed_personal_grants` are removed from agent creation in the same change."
- At f6affc53 both still run at creation: `packages/db/src/lonora_db/agents.py:88-91` (`grant_default`) and `personal_agent.py:37-40` (`seed_personal_grants`).
- The PR body limits its claim to bullets 1-2 and defers bullet 3 to step 5 (#193 removes them), but the title says "(14.3.15)". Merged alone, it breaks "in the same change".
- Fix: remove both calls here, with the tests that expect default grants. Or have the lead explicitly accept the split, and retitle to "14.3.15 bullets 1-2".

## Finding 2 (low, 0.4): text made false by this change

- `packages/tools/src/lonora_tools/session_search.py:30`: "the agents it supervises come from the owner's grants, re-read on every call". For Lonora they now come from `lead.reached_ids`.
- `packages/tools/src/lonora_tools/supervision.py:425`: "a revoked grant ends the reads at once" is false for Lonora, since `require_supervision` uses `reaches`.
- `docs/supervision.md:141-142` justifies the 0041 downgrade refusal by "(Lonora reading an agent the owner took away from it)".
- Fix: reword to "the agents it reaches: every team agent for Lonora (lead role), else those under a grant".

## What was checked

- 14.3.15 bullets 1-2: `personal_agent_id` is defined only in `lonora_db/lead.py`. Memory sessions, tool exposure, directory, subagents and inspect use `reaches` and `reached_ids`.
- 6.10: every new lead read path (`session_search`, `search_internal`, `subagent_inspect`, `agent_inspect`) is in `EXTERNAL_TOOLS`, so the run is marked and results carry `untrusted`.
- 3.2.2 / 3.2.4: non-lead agents keep only the old grant path, and there is one lead per owner.
- The manifest `--check` passes. No migration.
- Tests:
  - area pytest: 232 passed;
  - `check_supervision`, `check_team`, `check_personal_agent`, `check_agent_create` and `check_collaboration_sessions`: PASS;
  - core 14.1.2: all pass.
- Note: #193 (stacked later) removes `grant_default` and `seed_personal_grants`, which resolves finding 1 if the stack lands together.
