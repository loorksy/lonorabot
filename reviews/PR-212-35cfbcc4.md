# PR #212 at 35cfbcc4

- Head: 35cfbcc4. Previous review: eb4d348b (FINDINGS 0/0/4); 728bf77c was a merge only.
- New commits:
  - ffc93b19: the R-UI L1–L4 fixes.
  - 4c371861: the spec checks the hints.
  - 35cfbcc4: a new list-ar screenshot.
- Verdict: CLEAN.

## Checked
- L1 fixed: `/chart` now uses `showsTradingControl({ role, trading_account_id, level: permission?.effective_level, grants: permission?.active_authorities.length })`, the same inputs as web's Composer. `permission` comes from `AgentPermissions` through a new `onState` callback. `AgentPermissions` spreads its props into `PermissionControl`, so the callback reaches it.
- L2 fixed: `clearMessagesQ` and `clearAction` are removed from i18n.ts.
- L3 fixed: the row shows `row.hint`, and a bare typed command shows the hint as `command-hint` ghost text. The spec asserts both.
- L4 fixed: the list row and the bubble chip prefix U+200F in Arabic. Zoomed in, the new list-ar.png shows «/» at the right edge, before «مهمة», «بحث», «ملخص».
- Mobile tsc: clean. Playwright Expo slash-commands.spec at 35cfbcc4: 1 passed.
