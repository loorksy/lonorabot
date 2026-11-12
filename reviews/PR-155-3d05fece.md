# PR #155 at 3d05fece (W-MOBILE 5: mobile heads-up)

- PR: #155, `mobile/5-heads-up`
- Head: 3d05fece. Own commits: 37142eda, 3d05fece.
- Base: main e97efe90 (not stacked).
- Verdict: **CLEAN**

## Verified findings
None.

## What I checked
- **Parity with web's `HeadsUp`** (main `apps/web/src/shell/lists/HeadsUp.tsx`):
  - the same `@lonora/core` rules: `headsUpAllowed` for mute and archive, `inQuietHours`, and `attentionAlwaysShows` for urgent items, which show even in quiet hours;
  - the same 120-character cut;
  - agents whose in-app rule is off are excluded (`/agents/notifications` `in_app`);
  - a broker health item with no row of its own goes on Lonora's row (3.1.5, 9.4);
  - nothing is shown for the open chat or for events from before the app opened.
- **Delivery rules:** reach-me and in-app rules are re-read on foreground and at most once a minute on the shell's poll.
- **P5:** a transient overlay in the root layout, not a screen.
- **Stop:** untouched. The `emergency_stop` attention label already existed and is only exported under a new name.
- **Arabic and ids:** the new label `newMessage` has Arabic. The banner shows the agent's name and text, never raw ids or codes; attention items go through `attentionLabels`.
- **Tests:**
  - tsx `heads-up.test.ts` + `arabic-labels.test.ts`: 6/6.
  - `pnpm --filter @lonora/mobile check`: clean.
  - Playwright mobile `tests/mobile/heads-up.spec.mjs`: 1/1.
