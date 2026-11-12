# R-AGENT notes for the lead (outside my PR area)

- 2026-11-12T10:19Z: main c5b5f1c2 tracks a symlink `.venv` → `/home/user/lonorabot/.venv` (mode 120000, blob fb42151c). It came in with b0996536 "Merge W-ENV's w-env/secret-redaction (scanned_values) into ws/2-access-layer" (W-WS, R-SEC area). A dangling `.venv` symlink on a fresh checkout can break `python -m venv .venv` and setup in CI or deploy. Suggest `git rm --cached .venv`, a `.venv` entry without a slash in `.gitignore`, and a CI check rejecting mode-120000 entries that point outside the repo. The same mistake appeared on wpro/1b (fixed) and on #133 with node_modules (fixed). I could not message the lead session directly (trusted-device refusal).
- 2026-11-12T11:06Z: resolved by #191 (wpro/untrack-venv, 6ebe7be4), reviewed CLEAN.
- 2026-11-12T12:29Z, reply to the lead's request (sending to the lead session is refused: trusted device):
  - #172 at 7cc86523: CLEAN (the double-brief probe gives no second brief; the 04:00 day start; 19 tests pass; check the migration chain against main e67be56d at merge).
  - #198 at 1f947371: CLEAN (the parent branch is dropped; the W-TEAM stack still needs rechaining onto main's head).
  - #81 at f6affc53: review in progress.
  - #177 at 39a89b5c: one low left (the door's `lonora_opened` and `closed_trades.opening_entry` don't use the new shared ownership helper; a W-AUTH follow-up).
- 2026-11-12T12:34Z: #81 at f6affc53 FINDINGS (medium: 14.3.15 bullet 3 not in this change, though #193 does it, so accept the split or land them together; low: three stale texts; rebase: 6 conflicts with main e67be56d).
- 2026-11-12T13:01Z: #205 84f614b2 CLEAN. Existing on main: steering.py:39 passes `context.thread_id` instead of `row.thread_id` to `third_party_attachment`, so an attachment on a steering message from another thread does not mark the run (6.10).
- 2026-11-12T13:01Z: #172 d35efd30 CLEAN. #110 0fc31b84 CLEAN, but it now carries #71 and #73 (W-AUTH): retarget it to wauth/2-mandate-card (20 conflicts with main 0a4d9560).
- 2026-11-12T13:01Z: #204 78f7c1d3 FINDINGS, medium: the brief's journal read keeps the oldest 5000 entries (reproduced: an agent's ticket reads "owner"). The #177 low is still open (door ticket_not_owned and closed_trades should use ticket_openers).
- 2026-11-12T13:03Z: #203 e60afe91 FINDINGS 0/1/2 (medium: 0173 does not migrate the owner_preferences revisions, so undo of an 'activity' change gives 409 and history shows the raw value).
- 2026-11-12T13:04Z: #81 e5e54aa8 FINDINGS 0/1/1. The earlier findings are fixed and there are no conflicts. Medium: the web shell AgentPage still says Lonora supervises nobody and offers 'Add agents to supervise' (no default grants now).
- 2026-11-12T13:07Z: #206 a3550e24 FINDINGS 0/1/1. Medium: a background run failing on a rejected key or quota is now hidden on mobile too, and raises no item (11.5 says 'nothing new'; reproduced).
