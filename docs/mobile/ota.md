# Signed mobile updates, without EAS

Lonora serves Expo Updates protocol v1 at `/api/mobile/updates`. The native app pins the public certificate in `apps/mobile/certificates/ota.pem`; unsigned or modified manifests are rejected by Expo's native verifier. Assets are immutable and verified by SHA256. Runtime fingerprints keep incompatible native builds separate. The service is public and read-only; there is no upload endpoint.

**Current bootstrap: 0.2.7 / Android versionCode 26101901.** This owner-authorized release uses a new Android signing certificate; the first installation requires removing the earlier differently signed app and signing in again. Older APKs do not contain `expo-updates` or the new native voice dependencies and cannot gain those native modules through OTA. After that, compatible JavaScript/assets updates download automatically on launch or return to foreground and activate on the next cold launch. An active call or conversation is never forcibly reloaded. Native dependencies, permissions or signing changes still require a new APK.

## Publish

The existing signing key is local at `~/.config/lonora/ota/private.pem` (mode 600). Back it up securely; losing it means restoring the same key or shipping a new native certificate. Never add it to Git, Docker, CI artifacts, or the VPS. `scripts/ota-release.py init` refuses to replace an incomplete existing identity.

```bash
# Requires installed workspace dependencies and Python .venv, no Expo token.
bash scripts/ota-publish.sh android production
# Optional separate preview builds/releases:
bash scripts/ota-publish.sh android preview
```

This exports the real Metro bundle, derives the native fingerprint, signs the exact manifest bytes and writes `.runtime/releases/ota`. The active pointer is written last. Publish only from the same native configuration as the installed bootstrap APK; native dependency changes alter the fingerprint and intentionally do not update older runtimes.

Transfer `.runtime/releases/ota/assets/` and `releases/` to the same directory on the VPS using authenticated deployment access. Transfer immutable assets and release UUID directories **before** their `active.json` pointers; replace each pointer atomically last. Do not expose an upload HTTP API. The production Compose API mounts this directory read-only at `/app/releases/ota`; `LONORA_OTA_ROOT` selects it. No gateway restart is needed when the pointer changes. Deploy the API/Compose configuration once before publishing the first release.

## Roll back

```bash
.venv/bin/python scripts/ota-release.py rollback \
  --platform android --channel production --runtime NATIVE_FINGERPRINT
```

Deploy its signed directive directory and active pointer last as above. The multipart directive returns the client to its embedded bundle. The RSA signature is verified just like manifests. No financial state or conversation history lives in the OTA payload; those remain server-side.

## Verify

```bash
.venv/bin/python -m pytest tests/test_mobile_updates.py -q
```

After deployment, request the endpoint with `expo-protocol-version: 1`, `expo-platform: android`, `expo-channel-name: production`, and `expo-runtime-version: <installed fingerprint>`. A matching release returns a signed manifest, an unknown runtime returns 204. On a device install the bootstrap APK, publish a compatible small text/style change, reopen the app, let it download, close fully and reopen; confirm the new UI and unchanged login/conversation. Check an in-progress call is not interrupted. Native WebRTC calls require a real device check separately.


### Recorded0.2.7 runtime

The native release and the resolver from its actual build environment both produced `a954b90f9547b7c5a25444f4087d93eb42deeb90`. Compatible production OTA publication uses this exact runtime and the unchanged pinned OTA certificate. Public Android release-certificate SHA256 is `f1739a3196d6a9d1ce446d883d1d87527dab50226f979aa35dc8aef22ddcceee`. Android APK signing and OTA manifest signing remain separate identities. The full resolver inputs are retained locally with build artifacts; never replace this fingerprint with a previous host's runtime.
