# Lonora Android — architecture

Native Android client of the Lonora server, written in Flutter. Its visual and interaction
language lives in `lib/design` (tokens, theme, components); every capability and every byte of
data comes from the real Lonora backend. The app never runs agents, never stores provider keys,
and never decides anything on the owner's behalf: agents keep working on the server when the
phone is closed.

## Stack

| Concern | Choice |
|---|---|
| UI kit | `forui` 0.15.1 (themed to Lonora's tokens), platform font (Roboto on Android), Lucide (`FIcons`) |
| State | `async_redux` single store (`lib/state`) |
| DI | `get_it` (`lib/app/services.dart`) |
| Routing | `go_router` with a `StatefulShellRoute` for the floating tab bar (`lib/app/router.dart`) |
| HTTP | `dio` (`lib/core/api/api_client.dart`): bearer token, session generation fencing |
| Realtime | `dart:io` WebSocket on `/api/ws/events` (`lib/core/realtime/event_stream.dart`) |
| Secure storage | `flutter_secure_storage` (Android Keystore) for the session token |
| Local cache | JSON documents per server+owner (`lib/core/storage/local_store.dart`); held order identities in one of them (`held_operations.dart`), kept across «مسح ذاكرة التخزين المؤقت» |
| Notifications | `flutter_local_notifications` + `workmanager` (attention polling fallback) |

## Layout

```
lib/
  main.dart                bootstrap (edge-to-edge, services, store, realtime)
  app/                     LonoraApp, router, routes, home shell, deep links, splash
  core/                    api client + errors, models, realtime, storage, json helpers
  state/                   AppState, reply-stream reducer, realtime controller, actions/
  design/                  tokens, theme (LnTheme/forui/material), components/
  avatar/                  Lonora agent avatar (sphere + visor glyph) painter
  l10n/                    catalogs (ported from apps/mobile i18n) + core text ports
  features/<feature>/      screens and widgets, one folder per feature
```

## Contracts for feature code

- **Screens**: each route's screen class already exists in `lib/features/**` (see
  `lib/app/router.dart`). Replace the stub's body; keep the class name and constructor.
- **Reading state**: `context.select((AppState s) => ...)` (rebuilds only when the selected
  value changes) or `context.state` / `context.read()` from `lib/state/actions/base.dart`.
- **Changing state / calling the server**: dispatch actions (`context.dispatch(Action())`,
  `await context.dispatchAndWait(...)`). Actions extend `AppAction` and use `apiClient`.
  Screen-local data that nothing else needs may be fetched directly with `api.get(...)`
  inside a `StatefulWidget` (always handle `ApiError` and `SessionRequestCancelled`).
- **Errors**: show `context.l10n.errorText(error.code)`; never show raw codes or stack traces.
  `SessionRequestCancelled` is silent. `ApiError.isNetwork` means offline.
- **Strings**: never hard-code user-visible text. Use `context.t('key')` with Lonora's own
  keys (ported from `apps/mobile/lib/i18n.ts` etc.). New Android-only keys go in the
  feature's own `*_strings.dart` registered through `L10n.register({...})` with both Arabic
  and English.
- **RTL**: Arabic is the default locale. Use `EdgeInsetsDirectional`, `AlignmentDirectional`,
  `start/end`; mirror directional icons; isolate numbers/tickers/URLs with the l10n helpers.
- **Design**: only `lib/design` tokens and components (`context.ln`). No raw colours, no
  default Material look (AppBar/ListTile/FAB). Light and dark must both be correct.
- **Safety** (docs/android/analysis/lonora-api-contract.md §19): `POST /api/trading/execute` is
  called from one place only, `lib/features/trading/trades_data.dart`, and only from the owner's
  confirmed review sheet of their own order (open an order, edit stop and target, close a trade,
  cancel a pending order, or check a held one's result); never from agents, agent-written
  content (cards, generated UI, chat commands, voice), notifications, calls, deep links,
  background work, automatic retries or tests (tests use the fake API). Each ticket action keeps
  one `operation_id` with its exact body until its outcome settles, and a retry resends that id
  with the same body. Never call `POST /api/runs`, `/api/webhook`, broker connection
  create/delete or global model routing writes from routine UI; never display or log secret
  values; cards, notifications and calls never approve, settle or switch a trading mode — only
  an explicit owner tap on the corresponding card does.

## Realtime and offline model

1. Bootstrap restores the stored session and the cached snapshot (instant UI), then verifies
   `GET /auth/session`.
2. The event feed connects (`live: true` first time). After every `ready` the app refetches the
   shell snapshot and every loaded conversation, then flushes the outbox.
3. Events patch state: messages merge by id (outbox entries are acknowledged by
   `client_nonce`), runs update, live replies accumulate through the ported fenced stream
   reducer (`lib/state/reply_stream.dart`, from `packages/core/src/reply-stream.ts`), other
   kinds trigger debounced refetches.
4. In the background the socket is closed; on foreground it resumes from the last cursor.
5. Plain owner text that the API never answered is queued (persisted) and sent automatically
   when the network returns, with the same nonce (server-side dedupe). Answers, edits, card
   submits and voice notes are never queued.
