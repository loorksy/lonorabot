# PR #82 — W-ENV 2: workspace output never carries a secret's value (fix check at 95fef7cc)

- Head: 95fef7cc. New since e61bf443: the merge of #78 (5a46a31, d82712d) and 95fef7c ("The scan covers every stored value outside the broker scope")
- Reviewer: R-SEC (checking the lead's first review)
- Verdict: **CLEAN**
- Conflicts with main: none

## The lead's items
- **Scan all non-broker scopes:** done. `EncryptedSecretStore.scanned_values` decrypts the owner's workspace, integration and provider values; a name shared by two scopes is shown as `scope:NAME`, so no value is dropped.
  - `workspace_access.scan` and `artifacts.py` use it.
  - `workspace_values` stays workspace-only for use by name (7.2.4/7.2.5).
  - Leaving the broker scope out is consistent with 7.2.3: those values never enter the workspace.
- **Re-chain:** see #78.
- **Doc line:** `docs/analytical-workspace.md` names the scanned scopes and the 3-character minimum, which now applies to every scanned scope.

## What I checked
- tests/test_secret_redaction.py, test_secret_scopes.py, test_visual_acceptance.py and test_mcp_boundary.py: 61 passed on a fresh PostgreSQL DB.
- Migration: upgrade, downgrade -1 and upgrade, one head.

## Cross-PR note (filed on #122)
- #122's new `terminal.py` builds its scan from `workspace_values()` (lines 65 and 99), not `scanned_values()`. Once both merge, integration and provider values printed through the new workspace tools would not be redacted. #122 must switch to `scanned_values()` after rebasing on this head.
