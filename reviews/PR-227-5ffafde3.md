# PR #227 at 5ffafde3

- Head: 5ffafde3. Previous review: de94ae7d (FINDINGS 0/1/2).
- New commits:
  - 2f88ce29: a merge of main; no hand resolutions.
  - 9b18fae4: R-UI M1, L1 and L2.
  - 5ffafde3: a spec timing fix.
- Verdict: CLEAN

## Checked
- M1 fixed: the README now describes the «إعداد Lonora» first run (e-mail, a password of at least 12 characters, `LONORA_BOOTSTRAP_TOKEN`). Its instruction to set up the owner on the web first is gone.
- L1 fixed: a failed sign-in bumps `recheck`, so the status check runs again and a missed first run appears.
- L2: new specs cover "the answer belongs to its address" and "a sign-in that fails asks the server again".
- Mobile tsc: 0 errors. Playwright Expo first-run.spec: 6 of 6.
