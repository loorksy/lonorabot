# Lonora mobile

An Expo Router interface to the Lonora Python server. Native toolbar, title capsules, composer, member picker, settings groups and message/file cards follow the actual template source. Shared avatar geometry is used across Web and mobile; see `NOTICE` for source revisions and licensing. It uses the real Lonora API and never starts a separate agent runtime.

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
- Live server roster and activity, groups, toolbar search, creation/actions sheets and pull to refresh.
- Agent creation/profile editing with name, title, description, shared avatar shapes/color, instructions and pause state; group creation with real members.
- Continuous existing thread history, older-message pagination, sending, stable retry nonce, server run status, cancellation and takeover resume.
- Native/Web file selection and real server upload, attachments shown in messages.
- Editable agent identity/instructions/pause and versioned persistent memory; editable group membership.
- Routine creation/editing/pause/delete, interval or Cron/timezone schedules, actual execution history.
- Authenticated artifact library, inline generated images/chart PNGs, selectable Markdown, tool result cards, image/text preview, isolated HTML and PDF Web previews, native sharing with cache cleanup.
- Group mention suggestions, persisted replies, retry nonces, live server reply snapshots and shared 15-minute/date separators.
- Persistent chart scenes with real candles, price annotations, MA overlays and RSI; chart creation uses enabled broker connections and exact server symbols, and refresh requests the resident worker.
- Global settings routes for account, model routing, integrations and server voice status; safe server change revokes the old session; durable logout.

## Current scope and validation

Mobile is a companion surface. Provider/integration configuration, financial execution controls, boards, skills/scratchpad/semantic knowledge editing and realtime voice remain in the full Web interface. Native charts read persistent server scenes and never synthesize market data. Native model/integration/voice settings read real state and open the matching Web settings dialog. Native PDF/HTML files can be shared to a trusted external viewer; HTML previews show safe source. The agent runtime, memory, tools and trading still execute on the shared Python server when used through a thread.

Earlier validation used Expo version `0.2.3`, Android versionCode `4`. `pnpm --filter @lonora/mobile build` exports the Web, iOS and Android JavaScript bundles. TypeScript, Expo dependency compatibility and these exports are checked in the cloud workspace. The Android release APK is compiled and verified with real Android signing/alignment tools. Both the published version0.2.0 APK and the new version0.2.1 candidate install and reach the actual native sign-in screen on clean Android7/API24 x86_64 emulator state, without Metro. Updating the production APK with the candidate produces `INSTALL_FAILED_UPDATE_INCOMPATIBLE` because their signing identities differ; restore the original release key before publishing an update. Physical-device permissions, native file picker/upload and iOS binaries are not claimed as validated here. No model/provider or broker account is bundled or simulated by the app.

The `0.2.2` universal APK retains the saved `0.2.1` signer. Its package metadata, v2 signature, 16 KB ZIP/ELF alignment and four ABIs were verified. On the existing Android7/API24 emulator, package manager reported versionCode3 after replacement and the release reached its native Arabic sign-in screen without Metro. Full native authenticated conversation/chart flows and physical devices remain unverified; their API flows are covered by the Expo browser regression.

The retained `pnpm test:mobile` browser regression serves a fresh Expo Web export against the real Python API on port 8831, using the same explicit disposable-database guard as Web tests. It checks profile/memory edits, routine creation/history, authenticated artifact preview/download, lost-response message retry deduplication, continuous Inbox reopening, persisted replies, group mentions, generated PNG pixels, stored candlestick/RSI scenes, chart creation/refresh, bilingual global settings and logout. The chart fixture invokes the real executor with scripted model responses and explicitly imported test candles/instruments in a disposable PostgreSQL database. This is browser validation of Expo, not a native binary or device certification.

The `0.2.3` universal APK includes authenticated live chart scene events and native broker identity labels. Its versionCode4, unchanged release signer, v2 signature, four ABIs and 16 KB ZIP/ELF alignment were verified during the release build. The retained Expo browser checks cover live candles, persistence after reload and the existing companion flows; a physical-device installation of this exact release is not claimed.

### 0.2.6 repair release

Native configuration now requires versionCode26101613 or higher, above the deployed0.2.5/code26101612. Preserve the published signing identity when building an update; this workspace may contain an older, different local key. Overlay and legacy shared-storage permissions are blocked and new release verification checks the packaged manifest. The native permission change updates the runtime fingerprint and requires a new compatible APK before later matching OTA updates. Voice lifecycle and setup/teardown fixes are covered by transport tests; see `docs/mobile/voice-native-verification.md` and `docs/verification/android-security-audit-2026-10-16.md` for actual native acceptance limits.


## Authorized Android signing rotation (2026-10-19)

The owner authorized a new release identity for0.2.7/versionCode26101901 because the private key for the currently distributed certificate was unavailable. Public release-certificate SHA256: `f1739a3196d6a9d1ce446d883d1d87527dab50226f979aa35dc8aef22ddcceee`. This first install cannot update the previous differently signed APK in place: uninstall that app and sign in after installation. Server-side conversations remain in Lonora; Android-local drafts/settings are not preserved by uninstall.

The private identity is held outside the repository. Set `LONORA_SIGNING_DIR` to the authorized new private signing directory (`~/.config/lonora/android-production-20261019` on this build host) and `LONORA_EXPECTED_SIGNER_SHA256` to the public certificate above for future releases. Do not use the older default local key or generate another identity. Never commit or distribute the private key/credential manifest. Native runtime fingerprinting and the separately pinned OTA signing certificate remain enabled; do not force a runtime from an unrelated APK. The release's embedded fingerprint must match its recorded resolver provenance before publishing compatible OTA.
