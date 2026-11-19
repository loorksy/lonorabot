# PR #221 — W-MODELS: DeepSeek's current catalog chooses a default model (12.1)

- Head: ea4fcd59. Own diff against main dcf86b43 is ff32bae9 (2 files, +27/-1). `git merge-tree` against main shows no conflict.
- Reviewer: R-SEC
- Verdict: **CLEAN**

## What I checked
- **The change:** `PREFERRED_FAMILIES["deepseek"]` becomes `("deepseek-v4-pro", "deepseek-flash", "deepseek-chat")`.
  - `preferred_model` only orders ids the provider's own catalog lists (its exact id, or a dated snapshot), so an unlisted id is never chosen.
  - `deepseek-chat` is kept for accounts that still list it.
  - API keys only, no other vendor's client or endpoint (12).
- **Context windows:** the test asserts they stay unknown (`family_window` / `family_output` are None), so the policy's limits apply rather than a guessed number.
- **Comment (0.4):** true at this commit.
- **Tests:** test_model_default (with the new DeepSeek test), test_model_context and test_model_access_guard give 84 passed. ruff is clean.
