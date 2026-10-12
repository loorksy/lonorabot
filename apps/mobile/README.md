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
