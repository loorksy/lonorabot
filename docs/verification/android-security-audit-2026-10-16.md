# Android download verification, 2026-10-16

The HTTPS production download at `https://lonora.lork.cloud/download/lonora.apk`
was inspected with Android SDK 36 `apksigner`, `aapt`, `zipalign`, and the repository's
`apps/mobile/scripts/android-verify.py`. No APK was uploaded to an external scanner.
Signing validation establishes artifact integrity against its signing identity;
it does not establish that an application is free of malware. The exact warning
text and detection details are needed to distinguish an unknown sideload warning
from a harmful-app classification. Do not advise disabling Play Protect.

## Observed production artifact

- Package: `ai.lonora.mobile`; version `0.2.5`; version code `26101612`.
- Size: 153,050,525 bytes; SHA256 `e76a7094b68790487bf996f6c56328192029e34e6305900ca03e9ef1d0dc938f`.
- Public signer: `CN=Lonora, O=Lonora`, RSA4096; certificate SHA256
  `D5:F6:F9:D8:C9:6F:B5:5C:74:EB:25:F9:76:8B:1B:78:EA:A3:DB:1B:02:2E:38:7A:F3:82:E5:4D:FE:F5:63:3C`.
- APK signature v2 verifies; app is not debuggable. Minimum API24, target API36;
  four Android ABIs; embedded JavaScript and 16KB ZIP/ELF alignment checks pass.
- Manifest includes `SYSTEM_ALERT_WINDOW` and `READ_EXTERNAL_STORAGE` /
  `WRITE_EXTERNAL_STORAGE` (storage capped at API32), in addition to microphone,
  audio, network, vibration, biometric and an app signature permission. No camera,
  SMS, contacts, accessibility binding or package-install permission is declared.
- `https://lonora.lork.cloud/.well-known/assetlinks.json` returned `[]`, with no
  Android certificate association. That affects domain/passkey association and
  does not establish a cause for the security warning.

## Release corrections and checks

The existing local `.runtime/releases/android/lonora.apk` was version `0.2.4`,
code `5`, with a different signer:
`C177337770EE01DD15C5B56702A24FACE2072A8082D0F242BCCE757A7345C4C3`.
The checked-in config then used code `6`. Neither is a compatible production
update: the candidate must retain the observed production signing identity and
use a code greater than `26101612`. Do not rotate signing keys or uninstall users'
apps to work around this mismatch.

The Expo config now blocks camera, overlay and broad legacy storage declarations.
Attachment selection uses `expo-document-picker` with `copyToCacheDirectory: true`.
Its Android implementation uses Storage Access Framework `ACTION_OPEN_DOCUMENT`
and copies the selected content URI into the app cache. Uploads read that cached
URI; artifact downloads use `Paths.cache`, and sharing uses `expo-sharing` URI
grants. These paths do not require broad shared-storage or overlay access.

New builds run the packaged-manifest permission gate automatically. To verify a
candidate explicitly, use the configured Android SDK/JDK and run:

```sh
LONORA_EXPECTED_SIGNER_SHA256=d5f6f9d8c96fb55c74eb25f9768b1b78eaa3db1b022e387af382e54dfef5633c \
  python3 apps/mobile/scripts/android-verify.py /path/to/candidate.apk --require-minimal-permissions
```

The expected fingerprint is public metadata, not a signing secret. This check
must also be run against the final downloaded artifact after publication. Native
permission changes require a new APK; an OTA JavaScript update cannot remove
permissions from an installed APK. Permission reduction is a scoped hardening
change; it does not prove or promise removal of Google's warning.
