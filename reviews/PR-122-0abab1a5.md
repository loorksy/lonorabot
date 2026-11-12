# PR #122 — W-WS 2a re-review at 0abab1a5

- Head: 0abab1a5. New: ebbc88a2 (merge of #104 at d06d2ce1, reviewed CLEAN) and 0abab1a5 ("access round 3").
- Reviewer: R-SEC
- Verdict: **FINDINGS** (0 high / 0 medium / 2 low)
- Rebase item (not a finding): `0135_workspace_given.down_revision = "0070_secret_scopes"`. On main 0070 is no longer the head (main runs 0170 → 0070 → 0165 → 0175 → 0176), so the lead must re-chain it to main's head.

## Status of the findings from 374b06ca
- **M1** (rotated or deleted values lost on a supervisor restart): **fixed.**
  - Every value injected into a command is recorded encrypted on the Gateway (`ln_workspace_given`, `GivenValues.record`, before the command can print), with the secret store's cipher.
  - Every scan includes all values given in the last 30 days (`terminal.scan` → `with_guard`).
  - This survives restarts and puts nothing on the workspace disk.
- **M2** (`guard` with every value in every supervisor response): **fixed.** The supervisor no longer keeps or returns any value; no `guard` or `given` remains in `supervisor.py`.
- **L1** (partial minimum of a third of the form): **fixed.** The partial rule now applies at token boundaries with 8 letters or digits.
- Broker values never enter `ln_workspace_given`: it records only `request.secrets`, taken from `workspace_values()`.

## Verified findings

### L1 (low): an unkeyed SHA-256 of each value is stored beside it
- `packages/db/src/lonora_db/workspace_given.py`: `digest = sha256(owner_id \0 name \0 value)`, stored in `ln_workspace_given.digest`.
- A database dump without the encryption key still lets anyone confirm a guess of a low-entropy secret (a short password) offline. The secret store itself stores no such digest.
- Fix: an HMAC keyed by the encryption key (`hmac.new(key, owner|name|value, sha256)`), or a digest of the ciphertext's associated key-derived value.

### L2 (low, 0.4 and the owner's expectations): a deleted secret's value is kept for 30 days, and no doc says so
- After `DELETE /secrets/{id}` (14.3.11, "the only route that deletes a stored secret"), the value stays encrypted in `ln_workspace_given` for up to 30 days, so the scan can still hide it.
- That is a sound trade-off, but nothing owner-facing says so (no doc mentions `workspace_given` or the 30 days).
- Fix: one line in `docs/operations.md` (Arabic and English) and the `secret_delete` text: "a deleted value stays encrypted on the server for up to 30 days only so it can still be hidden in workspace output".

## What I checked
- The table: owner FK `ON DELETE CASCADE`, unique `(owner_id, digest)`; migration upgrade and downgrade.
- Pruning of entries older than 30 days runs on each read.
- tests/test_workspace_access.py and tests/test_workspace_service.py: 43 passed on a fresh PostgreSQL DB.
