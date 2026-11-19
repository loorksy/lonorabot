# PR #227 at de94ae7d

- PR: #227 "mobile: first-run owner setup on sign-in, as Web" (W-MOBILE, mobile/11-first-run)
- Head: de94ae7d. Base: main dcf86b43 (2 commits, 7 files).
- Verdict: FINDINGS 0/1/2

## Findings

### M1 (medium, 0.4): the mobile README still says to set up the owner on the web first
- Where: `apps/mobile/README.md:16`: "Initialize the single owner using the Web interface first. On the sign-in screen enter the reachable Lonora server URL and owner credentials."
- Evidence: this PR adds first-run setup to the mobile sign-in screen, and it removes the same instruction from the app's own `serverHint` («أنشئ حساب المالك أولًا من واجهة الويب»). The README now says the opposite of the app.
- Fix: "On a server with no owner yet, the sign-in screen shows «إعداد Lonora»: enter the e-mail, a password of at least 12 characters and the server's setup token (`LONORA_BOOTSTRAP_TOKEN`), and the app creates the owner and signs in. Otherwise enter the server URL and the owner's credentials."

### L1 (low): a failed status check keeps that address on sign-in
- Where: `apps/mobile/app/sign-in.tsx:31-32`. Any failure of `onboardingStatus` sets `{ address, initialized: true }`.
- Evidence: a server with no owner that is briefly unreachable, or slower than the 10.4 s abort, leaves the screen on sign-in until the address text changes or the app restarts. Web's first-run screen offers "Try again", which asks again.
- Fix: keep the status unknown and check again when a sign-in fails with a network error, or offer a retry.

### L2 (low, 14.1.4): "the status check never touches the session" has no test
- Evidence: the code supports the claim. `onboardingStatus` (`lib/api.ts:111-120`) is a raw `fetch` with its own signal and no `configureApi`, bearer or CSRF. But `tests/mobile/first-run.spec.mjs` covers neither that requests in flight survive a status check nor that an address change re-checks.
- Fix: add a case where an address change triggers a new check, and the signed-in session's requests are unaffected.

## Rejected candidates
- The 409 path can take over or reset an owner: no. `initialize_owner` compares the bootstrap token before checking whether an owner exists (403 first), so 409 needs the right token and writes nothing. The fallback is an ordinary password login, and the code comment explains it.
- A short token gives a generic 422 error: web does the same.
- The token is stored or logged: no. It stays in component state (`secureTextEntry`, autocomplete off), is cleared on success, and is sent only in `POST {server}/api/onboarding`.
- P5: setup is part of the existing sign-in screen, as on web's `AuthFlow`.

## Checked
- Parity with web: the same texts, the password minimum of 12, and the same `invalid_bootstrap_token` text.
- All 6 new labels have Arabic; arabic-labels passes.
- Mobile tsc: clean. CI mobile tsx: 68 of 69 (the one failure is pre-existing).
- Playwright Expo first-run and chat-lists: 16 passed. The app's `POST /onboarding` is mocked in the specs.
