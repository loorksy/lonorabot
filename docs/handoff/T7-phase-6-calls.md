# Status for the next agent — T7, UI phase 6 (calls), branch `ui/phase-6-calls`

Web only: no backend change and no migration (reserved id 0059 unused). No PR is open yet.

## Finished
- **call.screen** `/app/call`: `apps/web/src/shell/call/CallPages.tsx` (`CallPage`, `CallHeader`,
  `foldCall`, `callReturn`). The route is the open call; `Shell.tsx` keeps the route and
  `voice.minimized` in step (the effect right after `const conversation`). ⌄ or pulling down folds
  to the view it was opened from. Controls كتم · السماعة (output sheet, `setSinkId`) · إنهاء; the
  call's `TradeApprovals` stay under them (a call never approves a trade). No large title
  (`largeTitle` in `Shell.tsx` skips `call`, as the reference does).
- **call.strip**: `CallStrip` inside the TopBar strips in `Shell.tsx`; hidden on the call and its own chat.
- **call.incoming** `/app/incoming/:callId`: `IncomingPage` and the `useIncomingCalls` poller (3 s,
  only while the reach-me channel is `call` with a device; answers with the policy's device).
- **call.voice-not-configured (Q58)**: `useCallStarter` checks `GET /api/voice/status` before
  dialling; not configured → no session, no microphone, a sheet that opens `/app/providers`.
- **call.permissions-mic**: the phase-2 `PermissionSheet` (Shell opens it on `voice_permission_denied`).
- CSS `shell/call/call.css`; routes `call`, `incoming` in `shell/routes.ts`; pages in `shell/pages.tsx`.
  Removed the floating `CallCard`, `VoiceChatCard`, `VoiceStatus`; trimmed `components/call/call.css`.
- Docs: `docs/FRONTEND_STRUCTURE.md`, `docs/ui-reference/CAPABILITY_MAP.md` call rows.

## Open
1. **call.capsule** — needs `apps/web/src/shell/ChatHeader.tsx` (owned by T2's PR #51; build it after
   #51 merges). Reference `callPill()` at `docs/ui-reference/Lonora-Desktop-37.html:3583`: the call
   button grows once in place (clip-path 0.5 s) into [hang up · mute · wave]; tap the wave → the call
   screen. It replaces `apps/web/src/components/call/CallPill.tsx`.
2. **Q58 disabled look** of the header call button, also in `ChatHeader.tsx`: use `aria-disabled`
   so a tap still shows the warning (`useCallStarter().notConfigured`).
3. Decide the reference toast «أنه المكالمة الحالية أولاً.» when calling another agent during a call;
   today the header reads "Open active call" and opens the running call (`useCallStarter.start`).
4. Open the PR into main and run the final gate once: `pytest tests -q` on a fresh `*_test` DB;
   `pnpm lint`, `pnpm check`, `pnpm build`, `pnpm --filter @lonora/web i18n`; the full Playwright web suite.

## Last test runs (fresh `_ci` DB, `LONORA_UI_TEST_BROWSER_PATH=/usr/bin/google-chrome`)
- `npx playwright test tests/web/calls.spec.mjs` → 4/4; `tests/web/voice.spec.mjs` → 1/1.
- `npx playwright test --trace off` (full web) → 149 passed, 10 failed: 7 known baselines
  (agent-permissions:391, group-status:14, skills-management:122, visual-response:64 ×4);
  avatar-studio:6, owner-actions:326, workspace:414 passed 5/5 when rerun alone.
- `npx tsx --test tests/web/shell-routes.test.ts` → 3/3; tsc, biome, i18n clean (0 missing Arabic).
- pytest not run (no Python touched).
