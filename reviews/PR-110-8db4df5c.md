# PR #110 at 8db4df5c: CLEAN (merge only)

- Reviewer: R-AGENT, 2026-11-19T12:20Z
- Main: de96cb30 (migration head 0200_old_workspace_data).
- Verdict: CLEAN (merge only)

- New since 968079a4: merges of integration/batch-14 and wauth/2 only.
- `--remerge-diff`:
  - `CARD_ATTENTION` keeps `trading_mode` → `mandate_proposed` and takes batch 14's renamed `secret` kind;
  - `attention_messages.json` takes the renamed `owner_action_secret_connected_mcp` key and keeps `mandate_proposed`;
  - `docs/attention.md` keeps both sides.
- This PR's content is already in main through batch 14: against main its own files differ by 1 line in `check_attention_items.py`.
- Ran: `check_attention_items`: PASS.
- `merge-tree` with main de96cb30: 0 conflicts.
