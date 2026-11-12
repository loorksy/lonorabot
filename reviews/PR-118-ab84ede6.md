# PR #118 at ab84ede6 (re-review of the new commit only)

- PR: #118, `mobile/2-message-actions`
- Head: ab84ede6. Previous review: 458373e3 (`PR-118-458373e3.md`).
- Reviewed: 458373e3..ab84ede6 only.
- Verdict: **CLEAN**
- Scope: #118's own commit only; #95's two commits are reviewed in `PR-95-0a49110e.md`.

## Previous findings
- **M1 fixed.** `retryableFailure` (`packages/core/src/run-state.ts`) now takes the newest `user`/`group` run with no `parent_run_id`. My earlier probe on the head gives:
  - failed routine run: `null`;
  - failed subagent run: `null`;
  - failed owner reply followed by a newer succeeded routine run: the owner's reply, `u`.
  - `tests/mobile/run-retry.test.ts`: 3/3. The comment is corrected.
- **L1 fixed.** The banner filter is back to main's `run.status === "failed"`.
- **L3 fixed.** `trading-avatar-motion.js` is reverted; it no longer differs from 458373e3's parent.
- **L2 withdrawn.**
  - Main's web (`Conversation.tsx:534-536`, in `onMenu`) guards «Turn into a task» only with `!hasGenUi && !voicePart`. The `attachment_ids` check at `:522` is the edit item's.
  - However, #76's web adds `!message.attachment_ids.length` to the task item. Mobile matches the web conversation W-UI is landing, which is the parity target.
  - Not counted. If #76 drops that guard, mobile should follow.

## What I checked
- The diff of ab84ede6: `thread.tsx`, `run-state.ts`, the motion file revert, `message-actions.spec.mjs` (a routine-run fixture) and `run-retry.test.ts`.
