# Porting Lonora's words to Android

`port_i18n.mjs` copies the Expo app's own wording into the Android app. It never writes new
wording: it bundles the TypeScript sources with esbuild, runs them, and writes what they hold.

| Output | From |
|---|---|
| `assets/l10n/ar.json`, `assets/l10n/en.json` (flat `key → text`) | `apps/mobile/lib/i18n.ts` (590 own keys) and its spreads `labels-shell.ts` (176 `sh_*`) and `labels-shell-extra.ts` (2); `incoming-call-labels.json` as `incoming.<key>` (16); `attention-labels.ts` as `attention.<code>` (27, the label each code names) and `attention.model.<reason>` (4) |
| `lib/l10n/core/core_tables.g.dart` | the text tables of the `@lonora/core` modules the UI shows (owner actions, owner profile, financial boundary, agent permission errors, ChatGPT plan, agent status, agent model, capabilities, trading readiness, trade actions, order line, turn activity), module-private tables included |
| `test/l10n/fixtures/*.json` | the TS functions' own outputs (plural phrases for 0, 1, 2, 3, 10, 11, 100 and more, `fill()`, and every ported `@lonora/core` function on a set of server-shaped inputs), plus `catalog_manifest.json` (source key counts and hashes) |

Keys keep their source names; only the extra sources get a namespace. Keys keep source order.

## Run

Node 22 and esbuild are needed. esbuild comes with the repository's `pnpm install` (through
`tsx`); without it, install esbuild anywhere and point `LONORA_I18N_TOOLS` at it, or install
it into `tool/i18n/.tools` (ignored by git):

```sh
npm install --prefix apps/android/tool/i18n/.tools esbuild@0.28.2   # once, if needed
export PATH=/opt/flutter/bin:$PATH                                   # dart, for dart format
node apps/android/tool/i18n/port_i18n.mjs                            # from the repo root
cd apps/android && flutter test test/l10n
```

The converter pins `TZ=UTC` and uses fixed dates, so the same sources always give the same
bytes. It runs `dart format` on the generated Dart file (it warns if `dart` is missing).
`test/l10n/catalog_test.dart` fails when a source changed after the last run: run the
converter again and commit what changes.

## When the sources change

- A new or changed label in `apps/mobile/lib/i18n.ts` (or the shell files, the incoming-call
  JSON, the attention map): re-run; nothing else to do.
- A new table in a ported `@lonora/core` module: add it to `CORE` (private tables) and
  `buildCoreTables` in `port_i18n.mjs`; a changed function: update its Dart port in
  `lib/l10n/core/` (each cites its TS lines) and its fixture inputs in `coreFixtures`.
- `network-strip.tsx`'s inline waiting phrase is copied into the converter; a guard fails the
  run if the component's text changes.

## Android-only text

New UI text that Lonora does not have yet is registered by the feature, never added to these
generated files: `L10n.instance.register({'key': ['النص', 'The text']})`. Registering an
existing Lonora key with other words fails an assert: reuse Lonora's label instead.
