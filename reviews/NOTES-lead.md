# R-AGENT notes for the lead (outside my PR area)

- 2026-11-12T10:19Z: main c5b5f1c2 tracks a symlink `.venv` → `/home/user/lonorabot/.venv` (mode 120000, blob fb42151c). It came in with b0996536 "Merge W-ENV's w-env/secret-redaction (scanned_values) into ws/2-access-layer" (W-WS, R-SEC area). A dangling `.venv` symlink on a fresh checkout can break `python -m venv .venv` and setup in CI or deploy. Suggest `git rm --cached .venv`, a `.venv` entry without a slash in `.gitignore`, and a CI check rejecting mode-120000 entries that point outside the repo. The same mistake appeared on wpro/1b (fixed) and on #133 with node_modules (fixed). I could not message the lead session directly (trusted-device refusal).
- 2026-11-12T11:06Z: resolved by #191 (wpro/untrack-venv, 6ebe7be4), reviewed CLEAN.
