# Reference-37 fidelity work: shared brief

Read this whole file before you touch anything. It applies to implementers and reviewers.

## What the owner asked for

The owner compared the live web app (`apps/web`) with the reference prototype and found that
many things do not match it. An audit confirmed 162 gaps; you work on one package of them.

In the owner's words (translated from Arabic):

- "It must be the same animation, the same containers, the same way of navigating, and so on."
- "The design does not have to be identical. You may make it better, but with the same
  cleanliness as the reference file."
- "The reference file may contain mistakes. You must write the code cleanly."

So: the reference decides how things look, move and navigate. Where you can do something
better than the reference without changing its character, do it. Never reproduce a reference
bug, and never copy its code.

## Sources of truth, in this order

1. `docs/ui-reference/OWNER_DECISIONS.md` (102 lines, read it all). Binding. Where a decision
   differs from the reference, the decision wins. In particular, do NOT bring back:
   the «حول» section (Q54: only a version line at the bottom of settings), support or bug-report
   sheets (Q49), terms or privacy pages (Q50), privacy data actions such as export, reset or
   delete account (Q48), browser or phone notification settings (Q10), a spend cap or budget
   (Q22), an emoji button in the composer (Q28), phone/OTP/sign-up/forgot-password (Q46),
   deleting agents, groups or conversations (Q1, Q44: «مسح المحادثة» hides history, nothing is
   deleted), channels other than Lonora (Q53), brokers other than MetaApi plus «تجريبي» (Q52),
   local MCP (Q56), «إيقاف الوكيل» on Lonora (Q38). Lonora keeps its own avatar (Q42). English
   stays available (Q7). A disabled call button opens the voice provider settings (Q58). The
   vocabulary is fixed by Q19.
2. `docs/ui-reference/Lonora-Desktop-37.html`: look, layout, motion, navigation, wording.
3. `docs/ui-reference/DESIGN_TREE_37.md`: the owner's own outline of that file. It has the
   spring table, durations, gesture thresholds, the seven back-order rules, keyboard shortcuts
   and the reduced-motion rules. Use its numbers.
4. `docs/ui-reference/CAPABILITY_MAP.md`: how each reference surface maps to the real backend.

If these disagree in a way the list above does not settle, choose the option that is cleanest
for the owner, and say so in your report. The team decides UI questions itself; do not stop to
ask.

## Reading and running the reference

- The file has 9612 lines: CSS on lines 8-2264, JS on 2270-9611. Some lines are very long.
  Never read it whole. Use `grep -n '<pattern>' docs/ui-reference/Lonora-Desktop-37.html | cut -c1-300`
  and `sed -n 'A,Bp' <file> | cut -c1-600`.
- It runs from `file://`. Its functions are global (`go('settings')`, `openSheet(...)`), routes are
  `location.hash`, and state lives in localStorage under `lonora-complete-v4`.
- `openRef()` in the helpers (below) opens it signed in, at a viewport and theme.

## Rules for the code

- **Never copy code from the reference.** It is a one-file prototype built from string
  templates and global state. Take the outcome from it (sizes, colours, timings, the order
  things happen in, wording), then write it the way this codebase already works.
- **Reference mistakes.** If the reference contradicts itself, has a bug, an inaccessible
  control or inconsistent wording, do the sound thing and list it under `reference_issues`.
- **Reuse first.** Before adding a component, hook, helper or CSS rule, search
  `apps/web/src/shell`, `apps/web/src/conversation`, `packages/core/src`, `packages/chat-ui` and
  `packages/ui-web` for one that already does the job: `shell/lists/Popover.tsx` (`usePopover`),
  `useOverlayHistory`, the sheets in `shell/sheets`, the settings primitives in
  `shell/settings/ui.tsx`, `shell/spring.ts`, `shell/Toast.tsx`, `shell/Skeleton.tsx`,
  `Icon` from `@lonora/ui-web`.
- **Reference tokens only.** Colours, radii, type sizes, easings and springs come from
  `packages/ui-tokens` (the reference token layer) and `shell/spring.ts`. In anything you add or
  rewrite: no hex colours, no one-off font sizes, no Tailwind utility classes, no
  `.legacy-surface`, no shadcn or Base UI primitives, no `lucide-react`. The accent `#22E3A8`
  is for markers only.
- **Minimum code.** Nothing speculative, no option nobody asked for, no abstraction for a
  single use, no comment that narrates the change. Match the style around you. Delete what
  your change makes dead (imports, CSS rules, catalog strings, files), and nothing else.
- **Every changed line traces to a gap in your package.** If you notice an unrelated problem,
  put it in `notes_for_lead`; do not fix it.
- **Both languages.** Owner-visible text goes through Lingui (`t`, `Trans`, `msg`) with an
  English source string. Run `pnpm --filter @lonora/web i18n` in your worktree and fill every
  new Arabic entry in `apps/web/src/i18n/locales/ar/messages.po` with the reference's wording.
  Arabic must have 0 missing. Two different Arabic texts need two different msgids (use a
  Lingui `context` when the English is the same). Layout uses logical properties and works in
  RTL and LTR.
- **Accessibility.** Keyboard reachable, visible focus, labels on icon buttons, and
  `prefers-reduced-motion` handled as the design tree says.
- **Both sizes, both themes.** Phone 390x844 and desktop 1280x800, dark and light.
- No new dependencies. No changes to `apps/mobile` unless your package says so. If you change
  shared code in `packages/core` or `packages/chat-ui`, keep `pnpm check` green for mobile too.
- Server changes (FastAPI, `packages/*/src` Python): only when a gap needs data the API does
  not give. Follow the existing route and contract style, add pytest coverage, and never add a
  migration unless there is no other way (if you must, say so loudly in your report: migration
  heads have to be re-chained by the lead).

## Money-safety invariants

Do not weaken any of these. If a gap seems to need it, leave that gap and report why.

- Money moves only through the signed grant or an approval card, at the single executor.
- Exits (closing or reducing a position) are always admissible. The global brake
  («إيقاف الصفقات الجديدة» / «استئناف») must stay reachable by the owner at all times.
- The journal and authority records are append-only. No shadow trading. No Alpaca. MetaApi is
  the default broker. A broker account that is disabled stays disabled.
- Never print, log or commit secrets. The values in the env files here are test-only.

## Your environment

Your package has its own git worktree, branch, databases and server. Paths for package `<pkg>`:

- Worktree: `/home/user/wt/<pkg>` on branch `fx/<pkg>`. Work only there. Never edit
  `/home/user/lonorabot` (the lead's tree) or another package's worktree.
- Scripts (all take the package name first), in `FX=/tmp/claude-0/-home-user-lonorabot/5d377f24-3ac2-5c89-bb02-ed3686a435ad/scratchpad/fx`:
  - `$FX/serve.sh <pkg>`: build the web app, restart your API server on your port and refresh
    the signed-in seed. Run it after changes you want to see in the browser (about 30 s).
  - `$FX/pytest.sh <pkg> tests/test_x.py`: pytest against your test database.
  - `$FX/check.sh <pkg> check_attention`: run `tests/check_attention.py` (or a `*_browser.py`)
    on a fresh migrated database.
  - `$FX/pw.sh <pkg> tests/web/shell.spec.mjs`: run repo Playwright specs. The suite's port is
    shared by the whole machine, so runs queue one at a time: run only the specs that cover
    what you changed, and expect to wait.
  - `$FX/slot.sh <command>`: run a heavy command in one of three machine-wide slots. Use it for
    type checks: `cd /home/user/wt/<pkg> && $FX/slot.sh pnpm --filter @lonora/web check`.
- Other commands, from your worktree (first `. $FX/<pkg>/env.sh`):
  - Lint: `pnpm lint` (Biome; `pnpm format` fixes formatting).
  - Type check of everything, mobile included: `$FX/slot.sh pnpm check`.
  - Node unit tests: `pnpm exec tsx --test tests/web/<name>.test.ts`.
  - Catalogs: `pnpm --filter @lonora/web i18n`.
- Looking at the app and the reference: `$FX/helpers.mjs` exports
  `openApp(viewport, theme, path, opts)`, `openRef(viewport, theme, hash, opts)`, `shot(page, file)`,
  `close()`, `PHONE`, `DESKTOP`, `SEED`, `BASE`. Write small `.mjs` scripts in `$FX/<pkg>/` and run
  them with `. $FX/<pkg>/env.sh && node $FX/<pkg>/<script>.mjs`. Save screenshots in
  `$FX/<pkg>/shots/`, named `<gap-id>-<app|ref>-<phone|desktop>-<dark|light>-<before|after>.png`.
  Read the PNGs with the Read tool to look at them.
- The seed (`tests/ui-reference/seed_reference.py`, `seed_domain.py`) gives the owner
  `ahmed@example.com`, four agents (Lonora, gold, research, friend), one group and their
  conversations, one task, one skill. There is no model provider, so agents do not answer on
  this server: to see streaming, cards or errors, do what the existing specs do
  (`tests/web/streaming.spec.mjs`, `genui.spec.mjs`, `owner-actions.spec.mjs` and others mock
  the API with `page.route`), or write rows the way the seed scripts do.
- Chrome is at `/usr/bin/google-chrome`. Do not install browsers or packages.
- The machine is shared by about ten packages: do not start watch-mode processes or dev
  servers, and do not leave background processes running other than your one API server.

## Tests

- Behaviour you change gets a test that fails without your change: node unit tests in
  `tests/web/*.test.ts` for logic, Playwright specs in `tests/web/*.spec.mjs` for behaviour in
  the browser, pytest for the server.
- A spec that asserts the old behaviour is updated to assert the new one. Never skip, delete
  or weaken a test to get green.
- These Playwright tests already fail on the base branch and are not yours to fix:
  `agent-permissions.spec.mjs:391`, `group-status.spec.mjs:14`, `skills-management.spec.mjs:122`,
  `visual-response.spec.mjs:64` (four variants).
- Before you finish: `pnpm lint`, `$FX/slot.sh pnpm check`, the unit tests you touched or that
  import what you touched, the Playwright specs that cover what you changed, and a look at the
  result in the browser at both sizes and both themes next to the reference.

## Commits

- Commit on your branch in your worktree, one logical change per commit. Do not push, do not
  merge, do not rebase, do not touch other branches.
- Message: a short imperative subject in plain English, then a body that says what the owner
  now sees. End every message with these two lines exactly:

  ```
  Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_0111sgouu67WYk3Zo9wPCpEY
  ```

- Do not write model names, agent names or tool names anywhere else in the repository.
- Commit the regenerated catalogs with the change that needs them.

## Shared contracts between packages

Several packages run at the same time. These targets are fixed so that links agree:

| What | Path |
| --- | --- |
| Agent page («معلومات الوكيل») | `/app/agent/<agentId>` |
| Group page («معلومات المجموعة») | `/app/group/<groupId>` |
| Agent's skills | `/app/skills?agent=<agentId>` |
| New scheduled task, agent preselected | `/app/new-schedule?agent=<agentId>` |
| One task | `/app/tasks/<taskId>` |
| Integrations | `/app/integrations` |
| Model providers list, one provider form | `/app/providers`, `/app/provider/<providerId>` |
| Global model routing and allowed models (new page, package `settings`) | `/app/models` |
| Voice provider settings (Q58 target) | `/app/provider/openai` |
| Link a trading account | `/app/broker` |
| Old `?tab=models`, `?tab=voice`, `?tab=trading` on `/app/settings` | redirects kept by package `settings` |
| Owner's display name and initial | one helper in `apps/web/src/shell/data.tsx` or next to it, owned by package `profile`: `ownerDisplayName(profile, session)` returns the form of address, else the name, else the e-mail local part |

Files owned by another package: you may change a line or two in them when your gap needs it
(for example a link target), but keep the hunk as small as possible, because the lead merges
all the branches together afterwards. Your package file lists what you own.
