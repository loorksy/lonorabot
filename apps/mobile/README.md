# Lonora mobile

An Expo Router companion to the Lonora Python server. The Inbox layout, native navigation and classic assistant avatar are adapted from the actual Tampletgrok Expo interface at `20fc9ac862bb833d1578968a7aba5ea18ff88a29`; see `NOTICE` for upstream licensing. It uses the real Lonora API and never starts a separate agent runtime.

## Run

From the repository root:

```sh
pnpm install
pnpm --filter @lonora/mobile start
```

Open with an Expo client compatible with SDK 57, or run `pnpm --filter @lonora/mobile android` / `ios` on a workstation with the corresponding Android SDK / Xcode. Native project directories are generated locally and are not committed. Initialize the single owner using the Web interface first. On the sign-in screen enter the reachable Lonora server URL and owner credentials. A physical phone cannot access the server through the phone's `localhost`; use your server's HTTPS address or a reachable LAN address for development.

Native login calls `/api/auth/mobile/login`. The server returns an opaque, expiring session token, stored only in Expo SecureStore. Every request sends that token as `Authorization: Bearer`; server logout revokes it. Provider keys and passwords are never stored by the app. Closing the app does not stop resident server workers. No push notifications or native voice APIs are imported, so Expo Web does not call unavailable notification modules.

## Signed Android APK

Install Java 17 or later, official Android SDK command-line tools, API 36, build-tools 36.0.0, NDK 27.1.12297006 and CMake 3.22.1. Set `ANDROID_HOME` to that SDK. Use the system proxy and its trusted CA when your build host requires them; Java/Gradle also needs the matching proxy and trust-store configuration. Keep TLS verification enabled.

```sh
sdkmanager "platform-tools" "platforms;android-36" "build-tools;36.0.0" "ndk;27.1.12297006" "cmake;3.22.1"
pnpm --filter @lonora/mobile android:release
```

The release builder creates or reuses a private RSA release key at `$XDG_CONFIG_HOME/lonora/android` (normally `~/.config/lonora/android`), outside the Git checkout. `LONORA_SIGNING_DIR` can point at your existing private build-key directory. Securely back up both `lonora-release.p12` and `signing.json` from that directory and restore them on future build hosts. These files contain the release identity and passwords and must never be committed, published or copied into the APK. The builder refuses to replace an existing key with missing credentials. Expo prebuild retains signing through the config plugin, and a release build without the private identity fails instead of using the Android debug key.

The deliverable is `.runtime/releases/android/lonora.apk` with public verification metadata in `lonora.json`; JavaScript exports do not overwrite it. It is a universal, non-debuggable APK with embedded Hermes JavaScript and the four Android ABIs, requiring Android 7/API 24 or later. The verifier checks its Android package, signature, native library alignment and archive alignment, and rejects HTML or an unsigned/debug-signed artifact.

```sh
pnpm --filter @lonora/mobile android:verify ../../.runtime/releases/android/lonora.apk
# Diagnose a device's existing installation before attempting an update:
pnpm --filter @lonora/mobile android:verify ../../.runtime/releases/android/lonora.apk --device DEVICE_SERIAL
# Run native smoke checks on an explicitly selected test device/emulator:
python3 tests/mobile/android-smoke.py .runtime/releases/android/lonora.apk --serial DEVICE_SERIAL
```

An APK download URL must serve the actual binary with `Content-Type: application/vnd.android.package-archive`, not the Web application's HTML fallback. A previous installation can update only when the signing certificate matches and the new version code is not lower. Use the verifier/`adb install -r` result to distinguish signature conflict, version downgrade, unsupported Android version/ABI or an invalid download. Do not uninstall an existing app as a generic repair: uninstalling discards app-local state. If an earlier release used another key, restore that original key before building an update.

## Web preview

```sh
pnpm --filter @lonora/mobile start --web
pnpm --filter @lonora/mobile build:web
```

The export lives in `apps/mobile/dist`. Serve it with an `/api` proxy to Lonora on the same origin, with SPA fallback to `index.html`. Alternatively set the Python server's `LONORA_ALLOWED_ORIGIN` to the exact preview origin, use the server URL in the sign-in screen, and serve both from the same site for the strict session cookie. Expo Web deliberately uses the browser login endpoint, HttpOnly cookies and CSRF, without persisting bearer tokens in browser storage. Production HTTPS is required when `LONORA_COOKIE_SECURE=true`.

## Included

- Arabic first and English, with RTL layout and logical Inbox → thread navigation.
- Live server roster, groups, search by name, running status and pull to refresh.
- Agent creation with name, avatar and color only; group creation with real members.
- Continuous existing thread history, older-message pagination, sending, stable retry nonce, server run status, cancellation and takeover resume.
- Native/Web file selection and real server upload, attachments shown in messages.
- Editable agent identity/instructions/pause and versioned persistent memory; editable group membership.
- Routine creation/editing/pause/delete, interval or Cron/timezone schedules, actual execution history.
- Authenticated artifact library, search/filter, image/text preview, isolated HTML and PDF Web previews, native share/download with cache cleanup.
- Global settings routes for account, model routing, integrations and server voice status; safe server change revokes the old session; durable logout.

## Current scope and validation

Mobile is a companion surface. Provider/integration configuration, broker controls, markets/charts, boards, skills/scratchpad/semantic knowledge editing and realtime voice remain in the full Web interface. Native model/integration/voice settings read real state and open the matching Web settings dialog. Native PDF/HTML files can be shared to a trusted external viewer; HTML previews show safe source. Message bodies currently render selectable text rather than the Web Markdown/artifact renderer. The agent runtime, memory, tools and trading still execute on the shared Python server when used through a thread.

`pnpm --filter @lonora/mobile build` exports the Web, iOS and Android JavaScript bundles. TypeScript, Expo dependency compatibility and these exports are checked in the cloud workspace. Native binary builds, permissions, SecureStore persistence on a physical device and native file picker/upload require a simulator or physical device and are not claimed as validated here. No model/provider or broker account is bundled or simulated by the app.

The retained `pnpm test:mobile` browser regression serves a fresh Expo Web export against the real Python API on port 8831, using the same explicit disposable-database guard as Web tests. It checks profile/memory edits, routine creation/history, authenticated artifact preview/download, group editing, bilingual global settings and logout. This is browser validation of Expo, not a native binary or device certification.
