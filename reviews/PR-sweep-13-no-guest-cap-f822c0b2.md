# sweep/13-no-guest-cap at f822c0b2 (re-review of the new commits only)

- Branch: `sweep/13-no-guest-cap` (no PR number yet)
- Head: f822c0b2. Previous review: 08e011a7 (`PR-sweep-13-no-guest-cap-08e011a7.md`).
- Rebased onto main 6cb4421d. `git range-diff` shows:
  - 83bd446c is identical to 08e011a7;
  - 29a7e729 differs from a0ef4421 only by the regenerated manifest hash and a neighbouring line in `environment.py` from main.
- Reviewed: fe872d7c (catalogs, line references only) and f822c0b2.
- Verdict: **FINDINGS** (0 high, 1 medium, 0 low)

## Previous findings
- **M1 fixed in code.** `NewGroupPage` no longer disables the 13th pick (`GroupPage.tsx`).
- **L1 fixed.** `tests/test_conversation_conveniences.py:704` asserts an agent's 9th round is refused with `collaboration_round_limit`.
- **L2 fixed.** The `collaboration_start` description is built from `MAXIMUM_ROUNDS`.

## Verified findings

### M1 (medium): the new web test fails on every run
- **Where:** `tests/web/group-members.spec.mjs:52-53`, `main.getByRole("switch", { name: agent.name })`. Playwright matches a role name as a substring.
- **Why:** the fixture names agents `${prefix} 0` … `${prefix} 12` (`:24-28`), so the lookup for `… 1` resolves to four switches (`… 1`, `… 10`, `… 11`, `… 12`).
- **Run at f822c0b2:**
  `Error: strict mode violation: locator('main').getByRole('switch', { name: 'Team dec02a 1' }) resolved to 4 elements` → 1 failed.
- **Fix:** `getByRole("switch", { name: agent.name, exact: true })` (and the same for any other name lookup in the spec), then rerun.

## What I checked
- pytest `test_conversation_conveniences` + `test_system_policy`: 28 passed. (`pypdf`, a new main dependency, had to be installed in this environment.)
- `export_agent_tool_reference.py --check`: passes.
- Playwright web `group-members.spec.mjs`: 0/1 (above).
