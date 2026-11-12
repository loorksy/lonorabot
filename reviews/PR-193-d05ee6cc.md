# PR #193 at d05ee6cc: FINDINGS (0 high, 0 medium, 2 low), with a rebase request

- PR: #193, team/5a-no-supervision-grants (W-TEAM). Stacked on #185 (57059914). Own range 57059914..d05ee6cc: 76faf048, merge 9c8178ca (empty remerge diff), 802d3d2e and d05ee6cc.
- Reviewer: R-AGENT, 2026-11-12T11:14Z
- Verdict: FINDINGS (lows only). The safety-relevant paths are correct.

## Rebase request (not a finding)

`0127_no_supervision_grants` (in range) sits on the stack's `0126_team_heads_merge`. Main c5b5f1c2's head is `0110_closed_trades`, and `git merge-tree` conflicts as for #185. Rechain 0125-0127 onto 0110 when #138, #146 and #185 land.

## Finding 1 (low): dead code and comments false at this commit in control_work (0.4, 3.3.3)

- File: `packages/db/src/lonora_db/supervision.py`. `reaches` (`:253`) now passes only for the lead, which leaves three pieces unreachable:
  - the non-lead money-standing refusal (`:300-310`), whose comment says "a team supervisor still pauses only an agent's routines, watches or Tasks on its own";
  - the supervisor pause-card branch (`:326-333`, "Other supervisors keep theirs…");
  - half of the hold-lift condition at `:344-349`.
- `raise_supervision_pause_card` has no production caller outside that dead branch, only tests.
- The docstring at `:220-224` describes future work.
- Fix: delete the money-standing block and the `is_lead` card branch, simplify `:344-349` to `elif hold.holder_agent_id != actor_id: raise supervision_resume_not_yours`, drop the future-tense sentence, and move legacy-card seeding into a test helper if still needed.

## Finding 2 (low): a doc line names a future removal (0.4)

`docs/supervision.md:134`: "Restrictions are removed with W-REMOVE." State only what is true now.

## What was checked

- 14.1.1: every former grant reader goes through `lead.reaches` or `reached_ids` (memory sessions, tool exposure, directory, subagents, inspect, routine toggle, `control_work`, `lead_control`), and no grant symbol remains outside tests and the migration.
- 14.3.6: the owner-pause functions live in `lonora_db/pauses.py`, untouched, and `SupervisionHoldRow` stays.
- 14.3.15: `grant_default` and `seed_personal_grants` are removed in this change (closing my #138 lead note).
- 14.3.9: 0127 deletes the supervision card rows before the literals change; the round trip passes.
- 14.3.18.4 and .6: declared as later steps. Roles and templates are untouched here. W-AUTH's migration must end `source='agent'` holds whose holder is not Lonora.
- 14.1.4: the web, mobile and contract supervision files are deleted with no dangling import.
- Arabic: no new text and no empty msgstr.
- 14.1.3: no 6.1-6.9 assertion is removed. 6.9 is untouched.
- Manifest `--check` passes.
- 3.2.2 / 3.2.4: `test_private_memory` passes, and a team agent gets `supervision_required`, `agent_control_lead_only` and `thread_not_found` for another agent.
- Tests:
  - area pytest: 238 passed, 13 skipped (the task-db skips give 17/17 when a task database is set);
  - more pytest: 85 passed;
  - `check_supervision`, `check_lossless_downgrades` and `check_simple_lonora`: exit 0;
  - core 14.1.2: all pass;
  - re-run by me: `test_private_memory` and `test_supervision`, 10 passed.
