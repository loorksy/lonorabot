# sweep/13-no-guest-cap at b9a12c3a (re-review of the new commits only)

- Branch: `sweep/13-no-guest-cap` (no PR number yet)
- Head: b9a12c3a. Previous review: f822c0b2 (`PR-sweep-13-no-guest-cap-f822c0b2.md`).
- Reviewed: 8b3ce05c (catalogs, line references only) and b9a12c3a.
- Verdict: **CLEAN**

## Previous finding
**M1 fixed.**
- `tests/web/group-members.spec.mjs` looks members up with `exact: true`.
- It also picks a member (`agents[0]`) as the group's coordinator. The default coordinator, Lonora, is not a member, so the page rightly refused to submit. This was a second test fault, not a product one.

## What I checked
- Playwright web `tests/web/group-members.spec.mjs`: 1/1 at b9a12c3a.
