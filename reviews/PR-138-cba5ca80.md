# PR #138 at cba5ca80: FINDINGS (0 high, 1 medium, 0 low)

- PR: #138 (W-TEAM). New since 441252e8:
  - fix commit cba5ca80;
  - merges eb81082e (wtask/1 at 3604c46b), 9d16215a (wteam/1 at f6affc53) and eb5507e7 (main at e97efe90).
- Reviewer: R-AGENT, 2026-11-12T07:56Z
- Verdict: FINDINGS. All four earlier lows are fixed. The head cannot migrate.

## Finding 1 (medium): two alembic heads, so `upgrade head` fails at the PR head

- `0125_flat_team_creation.py:16` is now chained to `0170_broker_health_attention`, but the stacked wtask/1 migration `0060_agent_trading_mode.py:14` still chains to `0068_end_trading_goals`. Its chain ends at `0061_trade_approval_validity`.
- Evidence:
  - `alembic heads` gives `0061_trade_approval_validity (head)` and `0125_flat_team_creation (head)`;
  - `upgrade head` gives "Multiple head revisions";
  - the PR's own `tests/check_flat_creation_migration.py` (BEFORE = 0170) fails at the downgrade step.
- Fix: one chain, 0085 → 0140 → 0170 → 0060 → 0061 → 0125. Set `0060.down_revision = "0170_broker_health_attention"` (wtask/1 needs this on its rebase anyway, or carry it in this merge's resolution), `0125.down_revision = "0061_trade_approval_validity"`, and the check's BEFORE to `"0061_trade_approval_validity"`.
- Verified: with exactly these three edits applied temporarily, there is a single head, `check_flat_creation_migration` passes, and the other tests below pass.

## Earlier findings: all fixed

- F1: the docs, the `agents.py` docstring and tool text, and `lonora.md:465` now say an owner turn creates in Ask even after third-party content, and a wake or routine copies Lonora's mode. The probe still gives `created mode: ask lonora=full`, and the text matches it.
- F2: "the owner's form" is removed from `contracts/agent_creation.py:1,31`.
- F3: the `AvatarSheet` draft branch and comment and the `TopBar` JSDoc are removed.
- F4: `restrictions.py:103` no longer lists agent creation.

## Merge resolutions

- `routine.py`: `SERVER_AUTHORED_TRIGGERS` drops `goal` and `agent_created`; nothing uses them.
- Manifest: regenerated. `--check` and `check_policy_distribution` exit 0.
- `messages.po`: ar and en have equal live entries with no empty msgstr (static check; there is no node_modules).

## What was checked

With the temporary rechain:
- `check_agent_create` and `check_simple_lonora`: rc 0.
- The PR's pytest files: 136 passed, 4 skipped.
- Core 14.1.2: all pass.
