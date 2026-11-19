# PR #157 — re-review at ebad69a5

- New commit only: 38433104..ebad69a5 ("0071: the downgrade leaves connections the earlier contracts can read"; 3 files, +175/-2). No conflict with main.
- Reviewer: R-SEC
- Verdict: **CLEAN** (the two lows of PR-157-b12a06a7 stand).

## What I checked
- **The downgrade:** the existing refusal comes first. While a feed, a calendar or an MCP server keeps its address in the encrypted store, the downgrade refuses and changes nothing.
- **Only then:** it removes `url_secret_id` and `endpoint_sha256` from MCP connections and `domain` from integrations. Those are the fields 0071 added and the earlier `extra="forbid"` contracts reject, and no stored address can be lost because such rows were refused above.
- **New check, `tests/check_secret_card_migration.py`,** passes on a fresh migrated `_test` database:
  - the downgrade refuses while an address is stored, unchanged;
  - it leaves an MCP server and a news feed with exactly the earlier fields and values;
  - the upgrade runs again and the new contracts read the rows.
- **Docs (0.4):** the docstring and `docs/owner-actions.md` say so and are true. ruff is clean.
