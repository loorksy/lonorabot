# Native voice startup verification

The mobile call startup transport preserves the selected Agent and Thread, authenticated
SDP exchange, original initialization nonce, and server-side approval flow. Lifecycle
regressions covered by the automated tests include cancellation while microphone access,
SDP offer creation, or ICE gathering is pending; late native work must not configure a
closed peer or create a server voice session. Native cleanup failures must still release
the peer and provider and finalize the original server session. Audio routing teardown
must run even if receiver silencing or microphone reset fails.

Run the repeatable checks from the repository root:

```sh
pnpm exec tsx --test tests/mobile/voice-transport.test.ts tests/mobile/voice-readiness.test.ts
pnpm --filter @lonora/mobile check
```

These tests execute the transport with scripted peers and the native device adapter with
scripted native modules. They cannot establish that Android WebRTC/audio initialization
works on a physical device or determine the cause of an Android process exit.

For the reported immediate exit when pressing Call, collect a native reproduction using
the exact signed APK and installed update version. Record Android version, device model,
ABI, APK version code and fingerprint, microphone permission state, and call timestamp.
Capture logcat across app launch and the call attempt, including `AndroidRuntime`,
`ReactNativeJS`, WebRTC, InCallManager, and native fatal signal/tombstone entries. Keep logs
private and redact account identifiers and tokens before sharing them. Do not clear user
data or uninstall the existing app to collect evidence.

Verify a successful call and end, denied microphone access, repeated Call taps, immediate
hangup while connecting, background/foreground, logout during connection, and a second
call after failure. Check that the originating Agent/Thread and pending approvals remain
correct and no microphone remains active after ending. Physical acceptance remains open
until the signed native build passes these checks; a TypeScript or Expo web check alone
is insufficient to claim the process-exit bug is fixed.

## Missing wake-lock declaration found in the published APK

The audited0.2.5/code26101612 packaged manifest has no android.permission.WAKE_LOCK. InCallManager4.3.0 declares none in its library manifest; its Handler-thread start calls updatePartialWakeLock and PowerManager.WakeLock.acquire without catching SecurityException. A JavaScript try/catch cannot contain that native Handler failure. Version0.2.6 explicitly requests the normal WAKE_LOCK permission alongside microphone/audio settings. Every new release verifier checks these actual packaged declarations; permission changes require a compatible new binary. Native reproduction evidence is recorded separately; static tracing alone does not certify all Samsung call behavior.

## Evidence from the 2026-10-16 native probe

The audited production APK (version 0.2.5, code 26101612) installed and launched on
the existing Android API 24 / x86_64 AOSP emulator using software CPU emulation.
The installed manifest lacks `android.permission.WAKE_LOCK`. A disposable Java
`app_process` harness loaded the exact installed APK's `InCallManagerModule` class
and called `start("audio", true, "")` as the installed app UID (10062). Android
rejected `PowerManager.WakeLock.acquire` with:

```text
java.lang.SecurityException: Neither user 10062 nor current process has android.permission.WAKE_LOCK.
  InCallWakeLockUtils.acquirePartialWakeLock
  InCallManagerModule.updatePartialWakeLock
  InCallManagerModule.startOnLifecycleThread
```

This confirms the native audio startup permission defect in the shipped APK. It
is an installed-class harness reproduction, not a full UI call reproduction.
The normal Call button reached a disposable local `/voice/status` response but
returned a caught error before microphone/audio startup; that separate failure
was not diagnosed by this probe. No external account, voice provider, or broker
was used. The emulator blocked outbound access except to the local fixture host.
The corrected signed APK must be retested. API 24 emulation cannot establish
acceptance on the reported Samsung S24 Ultra or other modern physical devices.
