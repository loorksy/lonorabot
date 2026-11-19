# PR #159 — W-PUSH 2c: push a Mandate card an agent proposed (re-cut, at 973dbfdc)

- Head: 973dbfdc, re-cut on `integration/batch-14` (3f371259) with W-ATTN's `attn/2-mandate-items` (0a76d147) merged in (2bcef5b6). This PR's own commit is 973dbfdc (3 files, +61/-3). No conflict with main.
- Reviewer: R-SEC
- Verdict: **CLEAN** (PR-159-d65d33d7 stands).

## What I checked
- **973dbfdc:** `mandate_proposed` joins `PUSH_CODES`.
  - Like the Secret card, only a card an agent's run proposed pushes (`source == "agent"` and a `run_id`). Lonora's onboarding Mandate card is the system's and does not push (tested).
  - Through Telegram it reaches only the paired chat.
  - The push text is fixed: no price, size or account.
  - The docs (Arabic and English sections) and the module docstring list the new event, true at this commit (11.4 names "a Mandate card proposed").
- **The base merge 2bcef5b6 (`git show --remerge-diff`):**
  - `connect_credential` (removed by #157) leaves `CARD_ATTENTION`, the attention docs and the messages.
  - `secret_requested` and `mandate_proposed` are both kept, with Arabic and English text.
  - `0172_mandate_attention` (W-ATTN's) chains to batch 14's head `0100_execution_receipts`, with one head.
- **Tests:** test_push_sender, test_attention and test_telegram_channel give 68 passed on a fresh migrated `_test` database. ruff is clean on the changed files.
- **Note:** the batch-14 base has the gateway lint errors recorded in PR-228-9449adaa; they are not this PR's.
