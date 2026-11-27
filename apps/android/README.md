# Lonora for Android

Native Android client of the Lonora server, written in Flutter (package `ai.lonora.android`,
Android 8.0 / API 26 and later). Design and architecture: [ARCHITECTURE.md](ARCHITECTURE.md);
server contract and inventories: [docs/android/analysis](../../docs/android/analysis/README.md).

The app is a client only. Agents, schedules, provider keys and trading decisions stay on the
Lonora server; the phone never stores a provider or broker secret.

## Toolchain

| Tool | Version |
|---|---|
| Flutter | 3.47.9 (Dart 3.13.7) |
| JDK | 17 or 21 |
| Android SDK | compileSdk 36, build-tools 36 |

```sh
cd apps/android
flutter pub get --enforce-lockfile
```

## Checks

```sh
dart format --output=none --set-exit-if-changed lib test
flutter analyze
flutter test                      # unit, widget and golden tests
flutter test --update-goldens     # only after reviewing an intended visual change
```

Golden tests render with Roboto from the Flutter SDK cache (`test/design/fonts.dart`), the font
the app uses on Android.

### Real-backend tests

Tests named `*backend*_test.dart` and `test/integration/` talk to a real Lonora server. They are
skipped unless `LONORA_TEST_CREDS` names a JSON file
`{server_url, owner_email, owner_password}` for a **disposable** server:

```sh
LONORA_TEST_CREDS=/path/to/creds.json flutter test test/integration
```

Never point them at a production server. How to run a throwaway local server with the scripted
model fixture: [lonora-local-runtime.md](../../docs/android/analysis/lonora-local-runtime.md).
These tests never call order execution, `POST /api/runs`, webhooks or approval decisions.

## Builds

```sh
flutter build apk --debug                      # ai.lonora.android.debug, debug-signed
flutter build apk --release --build-number=N   # signed release APK
flutter build appbundle --release --build-number=N
```

`versionName` comes from `pubspec.yaml` (`version:`); `--build-number` sets `versionCode`
(CI uses `1000 + run number` for releases). Debug builds install next to release builds
(`.debug` suffix, label "Lonora Debug").

### Release signing

No key, password or keystore lives in this repository. `android/app/build.gradle.kts` reads the
signing identity, in order, from:

1. Environment variables: `LONORA_ANDROID_KEYSTORE` (path), `LONORA_ANDROID_KEYSTORE_PASSWORD`,
   `LONORA_ANDROID_KEY_ALIAS`, `LONORA_ANDROID_KEY_PASSWORD`.
2. A properties file named by `LONORA_ANDROID_SIGNING_PROPERTIES`, by default
   `~/.config/lonora/android-native/signing.properties`:

   ```properties
   storeFile=upload.p12          # relative to this file, or absolute
   storePassword=…
   keyAlias=…
   keyPassword=…
   ```

A release build without a complete identity stops with an error; it never falls back to the
debug key. Release builds are minified and resource-shrunk (R8, `proguard-rules.pro`) and signed
with APK Signature Scheme v2 and v3.

Verified locally on 2026-11-27 with a throwaway key outside the repository: the release APK
(universal, arm64-v8a + armeabi-v7a + x86_64, about 117 MB because native libraries are stored
uncompressed for each ABI) and the App Bundle (about 95 MB; Google Play serves one ABI per
device) both build, and `apksigner verify` reports schemes v2 and v3.

`tool/release_manifest.py <apk>` prints the package, version, SDK levels, signing-certificate
SHA-256 and file SHA-256 of a built APK as JSON (public metadata only).

### In-app updates (sideloaded builds)

Installs from Google Play update through Play. An APK installed directly looks for updates
only when it was built with the address of a release manifest:

```sh
flutter build apk --release --build-number=N \
  --dart-define=LONORA_UPDATE_MANIFEST=https://releases.example.com/lonora-android.json
```

Without that flag (or with an `http://` address) the build never looks for updates. To publish a release,
upload the APK, then print its manifest and serve it at that address with
`Content-Type: application/json` (UTF-8). Served as anything else (a GitHub release asset comes
as `application/octet-stream`), the app reads no manifest and every check finds no update:

```sh
python3 tool/release_manifest.py build/app/outputs/flutter-apk/app-release.apk \
  --update-manifest https://releases.example.com/lonora-android-1.2.0.apk \
  --notes-ar "…" --notes-en "…" > lonora-android.json
```

```json
{"package": "ai.lonora.android", "version_name": "1.2.0", "version_code": 1012,
 "url": "https://releases.example.com/lonora-android-1.2.0.apk",
 "notes": {"ar": "…", "en": "…"}}
```

The app reads the manifest at sign-in and on resume (at most every 6 hours) and from About →
«Check for updates», and offers the update when `version_code` (else `version_name`) is newer
than its own;
«Download» opens `url` in the browser and the owner installs it. The app ignores a manifest for
another package, a link that is not `https`, and the Expo companion's `/download/lonora.apk`
(`ai.lonora.mobile`); the script refuses those links too. Checked by
`python3 -m unittest test/tool/release_manifest_test.py` and
`flutter test test/tool/update_manifest_script_test.dart`.

## CI

`.github/workflows/android.yml` runs format, analyze, tests and a debug APK on every push that
touches `apps/android/`. A manual run with `release: true` also builds the signed release APK
and App Bundle from these repository secrets:

| Secret | Content |
|---|---|
| `LONORA_ANDROID_KEYSTORE_BASE64` | base64 of the upload keystore (PKCS12 or JKS) |
| `LONORA_ANDROID_KEYSTORE_PASSWORD` | keystore password |
| `LONORA_ANDROID_KEY_ALIAS` | key alias |
| `LONORA_ANDROID_KEY_PASSWORD` | key password |

The keystore is restored into the runner's temp folder for the build and deleted afterwards.
