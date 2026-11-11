# Status for the next agent — T7, UI phase 6 (calls), branch `ui/phase-6-calls`

Web only: no backend change and no migration (reserved id 0059 unused).

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

## Finished after the conversation header landed
- **call.capsule**: `CallCapsule` in `ChatHeader.tsx` replaces the call button on that agent's chat
  (wave · mute · hang up). The wave keeps `data-testid="active-call-pill"` and opens the call
  screen. `CallPill.tsx` is gone. Other screens keep `CallStrip`.
- **Q58 disabled look**: the header call button uses `aria-disabled` when `/voice/status` says the
  provider is missing, and a tap still opens `useCallStarter().notConfigured`.
- Calling a different agent while a call is up opens the running call (`useCallStarter.start`).
  No extra toast.

## Open
None on this branch. The local gate has run; GitHub Actions jobs still end with zero steps.

## Last test runs (fresh `_ci` DB, `LONORA_UI_TEST_BROWSER_PATH=/usr/bin/google-chrome`)
- Local gate `docs/handoff/gate/gate.sh`: install, lint, check, build, web unit, migrate,
  pytest and the eight named checks all rc=0. Playwright 194 passed, 10 failed (20.2m).
- The 10: account-authority en:131 and the bounded WebAuthn case (cleanup DELETE timeout;
  both passed when rerun alone), calls Q58 before the aria-disabled click (fixed; `calls.spec`
  then 4/4), and the same four baselines as main (agent-permissions account-wide unsigned,
  group-status:14, skills-management:122, visual-response:64 ×4).
- i18n extract: Arabic 0 missing.
