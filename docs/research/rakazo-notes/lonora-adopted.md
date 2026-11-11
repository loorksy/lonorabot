# What Lonora has already taken from rakazo

Scope: the Lonora repository (`/home/user/lonorabot`, HEAD `9f5b1da`, 2026-11-11). All paths are relative to the Lonora root unless prefixed `rakazo:`. "(stated)" = the claim rests on a document or notice; "(implemented)" = confirmed in code.

Method: `grep -ril rakazo` (excluding `.git`, `node_modules`) returned 15 files with 39 matching lines; every hit was read in context. `git log --all -i --grep=rakazo` returned 4 commits (`197ccdb`, `eef53bb`, `d6adfca`, `7eeb487`); all four only adjust the Playwright spec `tests/web/rakazo-parity.spec.mjs` to follow the new reference UI. No commit message records the original import of rakazo code.

## 1. Headline findings

1. Lonora's front end started as a derivative of rakazo's web and Expo apps, taken through an intermediate template repository ("Tampletgrok"). This is declared in the notices (stated) and still visible in code: 36 files contain the attribution line `Modified for Lonora; source attribution in THIRD_PARTY_NOTICES.md. Apache-2.0.` (counted by grep for that text; it is a `//` comment in the TypeScript files, and a few of the 36 are CSS files such as `packages/ui-tokens/src/tokens.css` and `apps/web/src/styles.css`) (26 in `packages/ui-web`, 5 in `packages/chat-ui`, 2 in `packages/ui-tokens`, 3 in `apps/web`; e.g. `packages/chat-ui/src/markdown.ts:1`, `packages/ui-web/src/components/ui/button.tsx:1`) (implemented).
2. Nothing from rakazo's agent runtime (`rakazo:packages/adapters/src/run-*.ts`, `pi-*.ts`) was taken. The notice says the changes include a "Python runtime" and "removal of desktop, billing and coding tools" (`THIRD_PARTY_NOTICES.md:121-122`) (stated). The engine references named in these documents are Hermes Agent (`docs/lonora-specs/MANDATE_EXECUTION_PLAN.md:35`; `THIRD_PARTY_NOTICES.md:11-12`) and nanobot (`THIRD_PARTY_NOTICES.md:3-9`), not rakazo (stated). I did not search Lonora's Python runtime for code resembling rakazo's TypeScript runtime, so "nothing was taken" rests on the notices and on the language difference, not on a code comparison.
3. The web UI is being rebuilt (owner decisions on it were recorded 2026-11-09, `docs/ui-reference/OWNER_DECISIONS.md:3`) against the owner's own HTML prototype, not rakazo: "`docs/ui-reference/Lonora-Desktop-37.html` is the single source of truth for how the new `apps/web` looks and behaves" (`docs/ui-reference/CAPABILITY_MAP.md:18`; `docs/lonora-specs/MANDATE_EXECUTION_PLAN.md:614` says the same in slightly different words: "the single source of truth for the look and behaviour of the new `apps/web`") (stated). The app imports `Shell` from `./shell/Shell` (`apps/web/src/App.tsx:8`) (implemented); several older screens under `apps/web/src/pages` are still imported by that shell (section 3.1). So the direction is away from the rakazo-derived UI, but it is not gone.
4. The test named "rakazo-parity" does not compare anything with rakazo (section 5).
5. In `docs/ui-reference/OWNER_DECISIONS.md` rakazo is mentioned exactly once (Q25, dictation). There is no owner decision that says "copy rakazo" or "match rakazo" (section 6).
6. The owner had the rakazo and nanobot installations on the production VPS deleted: "the owner had rakazo and nanobot deleted. Done and verified; their archive is deleted too." (`docs/handoff/HANDOFF.md:200-201`) (stated; this is about the VPS host, not about the code).

## 2. Provenance chain and licensing notices (stated)

Five different rakazo revisions are cited in Lonora. None could be checked: the rakazo checkout used for this study is a single-commit shallow clone at `cd7e20e`, and `git cat-file` fails for all five.

| Where | Revision cited | What it says was taken |
|---|---|---|
| `THIRD_PARTY_NOTICES.md:1` | none | "Lonora incorporates modified UI primitives and design tokens from Rakazo." |
| `THIRD_PARTY_NOTICES.md:118-122` | `2d666c4e…` | Source and copyright line; changes listed as "Python runtime, single-owner API, Arabic-first catalogs, market/trading/voice domains, renamed workspace packages, and removal of desktop, billing and coding tools." |
| `THIRD_PARTY_NOTICES.md:124-139` | Tampletgrok `20fc9ac…`, which extracts rakazo `c9375d4…` | "Adapted portions: conversation shell/roster/To picker/command palette, resizable context panel and panel preferences, transcript/composer presentation, artifact grid, board columns/ticket dialog, search rows, and Expo inbox/thread navigation." Removed: "simulated adapters, computer execution, public signup, billing and spaces." |
| `apps/mobile/NOTICE:4-14` | `c9375d4…` | Tampletgrok is "a frontend extraction of the Rakazo web and Expo applications"; files under `apps/web`, `apps/mobile`, `packages/ui-web`, `packages/ui-tokens`, `packages/chat-ui`, `packages/contracts`, `packages/core` derive from that commit; package names changed from `@rakazo/*` to `@tampletgrok/*`. |
| `apps/mobile/NOTICE:36-45` | Tampletgrok `20fc9ac…` | Lonora mobile modifications: "simplified classic assistant avatar, Inbox layout metrics and colors, and native Inbox-to-thread navigation adapted to the Lonora API." Excluded: "Native-only notifications, demo adapters, spaces, billing and computer screens". |
| `apps/mobile/NOTICE:47-54` | `afa3177…` | A second, direct adaptation: "Native inbox toolbar, title/composer geometry, grouped settings, member picker and file-card hierarchy". "Computer actions are replaced by actual persistent broker/chart scenes; vendor sandbox, billing, SSO and notifications are not included." |
| `docs/FRONTEND_STRUCTURE.md:5` | `48f26b1…` | Concept review (Arabic). Translation: "We take the agent's continuity, the simplicity of its identity, memory, tasks and groups, and connect them to a real market, orders and trading account through Python." |
| `docs/persistent-trading-teammate.md:10-12` | `548e6d6…` | "Product reference": rakazo's `VISION.md`, `AGENTS.md`, `CLAUDE.md`, the repository-local skills, and product/context/verification docs. |
| `LICENSE:166` | — | "Copyright 2026 Rakazo contributors" under the Apache-2.0 text. |

Note the inconsistency: one notice says "Rakazo contributors" (`THIRD_PARTY_NOTICES.md:120`, `LICENSE:166`), another says "the Rakazo authors" (`THIRD_PARTY_NOTICES.md:130`, `apps/mobile/NOTICE:5`). `THIRD_PARTY_NOTICES.md` has no heading; it starts directly with the sentence quoted from line 1.

## 3. Adopted and shipped (present in the current tree)

### 3.1 Code and assets

- **shadcn-style UI primitives, `packages/ui-web/src/components/ui/` (23 files)** (implemented). Compared file by file with `rakazo:packages/ui-web/src/components/ui/` at `cd7e20e`: all 23 file names exist in rakazo, and by exact-line comparison 20 of the 23 have 2-9 lines not found in rakazo's file, out of 14-256 lines (e.g. `dropdown-menu.tsx` 256 lines, 8 lines not in rakazo's; `tabs.tsx` 74 lines, 5). The larger divergences are `dialog.tsx` (21 of 145), `field.tsx` (17 of 225) and `input-group.tsx` (12 of 146); `input.tsx` differs in 9 of its 20 lines. Caveat: the comparison is against a later rakazo revision than the one imported, so the numbers overstate the differences.
- **Markdown rendering core, `packages/chat-ui/src/markdown.ts`** (implemented): 423 lines, only 9 lines not found in `rakazo:packages/chat-ui/src/markdown.ts` (577 lines); header at `packages/chat-ui/src/markdown.ts:1`. Also `icons.tsx` (1 differing line), `table-utils.ts`, `markdown-table.tsx`, `markdown.web.tsx` (the last two are heavily cut down: 29 and 46 lines vs 605 and 887 in rakazo). Still used by the app (`apps/web/src/components/visual/RichResponse.tsx:4` imports `ChatMarkdown` from `@lonora/chat-ui/web`).
- **Legacy design tokens** (stated + implemented): `packages/ui-tokens/TOKENS.md:8` calls `src/appearance.ts` / `src/tokens.css` the "Legacy (shadcn names)" set, used by "the current Web screens ... and `apps/mobile`"; the canonical set is now `src/reference.ts` from the owner's prototype (`packages/ui-tokens/TOKENS.md:7`). `tokens.css` and `generate-css.ts` contain the attribution line (2 files).
- **Package and file layout**: `packages/{ui-web,ui-tokens,chat-ui,contracts,core}` and `apps/{web,mobile}` mirror rakazo's layout, as `apps/mobile/NOTICE:10-12` states for Tampletgrok. Screen file names carried over from rakazo's `apps/web/src/pages/`: `ActivityList.tsx`, `Artifacts.tsx`, `Board.tsx`, `GroupPanel.tsx`, `KnowledgeSection.tsx`, `ScratchpadSection.tsx`, `SettingsOverlay.tsx`, `ModelSettingsOverlay.tsx`, `VoiceSettingsOverlay.tsx`, `shell/bot-panel.tsx`, `shell/bot-picker.tsx`. Their contents are largely rewritten (e.g. `Artifacts.tsx` 346 lines, of which 268 are not found verbatim in rakazo's 1058-line file by my recount; the first analyst counted 299, presumably with a different method). Only `Artifacts.tsx` was measured; "largely rewritten" is unverified for the other files.
- **Which of those old screens the app still uses** (implemented, by import): `Artifacts` (`apps/web/src/shell/pages.tsx:11`), `AgentCreatePanel` from `pages/shell/bot-panel` (`apps/web/src/shell/pages.tsx:14`), `AgentSettings` from `pages/shell/bot-settings` (`apps/web/src/shell/ChatMenu.tsx:14`), `GroupSettings` from `pages/GroupPanel` (`apps/web/src/shell/ChatMenu.tsx:12`), `SettingsOverlay` by lazy import (`apps/web/src/shell/pages.tsx:62`), which itself imports `ModelSettingsOverlay` and `VoiceSettingsOverlay` (`apps/web/src/pages/SettingsOverlay.tsx:2,5`); `Knowledge` (`apps/web/src/shell/pages.tsx:12`, `apps/web/src/shell/ChatMenu.tsx:13`), which imports `KnowledgeSection`, `ScratchpadSection` and `AgentPicker` from `shell/bot-picker` (`apps/web/src/pages/Knowledge.tsx:7,8,10`); `AgentPicker` is also used by `apps/web/src/components/market/MarketWatch.tsx:9`. So nine of the eleven carried-over file names are still reachable. **Not imported by anything**: `apps/web/src/pages/Board.tsx` (584 lines) and `apps/web/src/pages/ActivityList.tsx` (276 lines) — no `from ".../Board"` or `.../ActivityList"` import exists under `apps/web/src`. They appear to be dead code left from the rakazo-shaped UI (checked by grep for the names under `apps/web/src`, static and dynamic imports; not checked with a bundler).
- **Expo app, `apps/mobile`** (stated in `apps/mobile/NOTICE:39-54`; file names confirm): route files `artifact.tsx`, `artifacts.tsx`, `bot-settings.tsx`, `group-settings.tsx`, `group-thread.tsx`, `image.tsx`, `new-group.tsx`, `routine.tsx`, `server.tsx` exist in both `apps/mobile/app/` and `rakazo:apps/mobile/app/`. I did not diff their contents.
- **App icon**: `apps/mobile/NOTICE:31-33` warns the "orange assistant mark in packages/ui-tokens/assets/AppIcon.icon is the upstream icon source". Lonora's `packages/ui-tokens` has no `assets` directory today (listing shows only `TOKENS.md`, `package.json`, `src`, `tsconfig.json`), so that sentence is stale Tampletgrok text. Unsure whether the mark survives elsewhere under `apps/mobile/assets`.

### 3.2 Concepts (stated; attribution to rakazo rests on docs only)

- Persistent agents with a simple identity, memory, tasks and groups (`docs/FRONTEND_STRUCTURE.md:5`). In code these exist as Lonora features (`apps/web/src/pages/KnowledgeSection.tsx`, `ScratchpadSection.tsx`, `GroupPanel.tsx`, `apps/web/src/lib/peer_messages.ts`), but I cannot show which behaviour, if any, was modelled on rakazo rather than on nanobot or Hermes.
- "Persistent trading teammate": despite the title, the implemented content of `docs/persistent-trading-teammate.md` is nanobot's bootstrap files (`SOUL.md`, `AGENTS.md`, `USER.md`, `MEMORY.md`; lines 5-9, 20-25) and Lonora's own disclosure filter and broker verification (lines 50-83). rakazo appears only as "Product reference" (lines 10-12); no rakazo mechanism is named.
- Inbox semantics: spec 02 tells the implementer to "Inspect Rakazo-style semantics already present in Lonora before changing ordering rules." (`docs/lonora-specs/02_MOBILE_CHAT_UX_AND_STATE_RELIABILITY.md:512`). This states that rakazo-style inbox semantics exist in Lonora; it does not say what they are, and I did not confirm them in code (unverified).
- Activity: the old `ActivityList.tsx` is dead (above). The current activity surface is Lonora's own decision Q45: "Activity is a server projection over durable events and receipts (`GET /api/activity`); the client never invents entries." (`docs/ui-reference/OWNER_DECISIONS.md:79`); a page route named `activity` is placed in the shell's `updates` section (`apps/web/src/shell/routes.ts:142`).

## 4. Planned in specs, not shipped

- **A real rakazo comparison.** The build plan lists rakazo as one of four references for "Agent-centered chat, durable message/run flow, steering, collaboration presentation, progressive panels and overlays", with the evidence column reading "Existing project reference; pin the selected revision and record relevant source paths in Wave 0 before relying on its current behavior" (`docs/lonora-specs/NANOBOT_PARITY_AND_RELIABILITY_PLAN.md:25`). Wave 0 repeats: "Pin Rakazo's selected revision and inspect relevant source paths. Build a cross-reference capability map under R01/R07" (`…PLAN.md:382`). Not done: `rakazo` does not occur in `PROGRESS.md`, `IMPLEMENTATION_MATRIX.md`, `BUILD_CAPABILITY_CARDS.md` or `AGENT_HARNESS_SOURCE_REVIEW.md` (grep), and `PROGRESS.md:940` says "Full Wave 0 comparison ... remain open." So I found no record of a pinned-revision study of rakazo's run flow or steering in `docs/lonora-specs` (only four files there mention rakazo: spec 02, the two plans and `README.md`).
- **Server-side dictation "inspired by Hermes/Rakazo-grade open-source approaches"** as an upgrade after the browser speech API (`docs/ui-reference/OWNER_DECISIONS.md:53`). Not checked in code; the decision itself marks it as a later upgrade.
- **Retiring the inherited board/tickets**: "Legacy tickets and boards are retired." is a Wave 2 item (`docs/lonora-specs/MANDATE_EXECUTION_PLAN.md:741`), and waves 2-4 "are not started" (`…MANDATE_EXECUTION_PLAN.md:3`). `Board.tsx` is still in the tree, unused.
- **An agent computer** (terminal, controlled internet, long jobs; "no interactive browser, no hosting and no inbound ports") is planned as a separate branch after PR #30 (`docs/lonora-specs/MANDATE_EXECUTION_PLAN.md:609`; owner decisions D5-D7 in `docs/lonora-specs/MANDATE_CORRECTIONS.md:15-17`). It is not described as taken from rakazo, but it is the same product idea that the notices say was removed from the rakazo import (next section). Status not verified in code.

## 5. Tests "asserting parity"

- `tests/web/rakazo-parity.spec.mjs` (193 lines, 2 tests). Despite the name, it loads no rakazo page and compares no pixels with rakazo. Test 1 (`:13-144`) checks, against Lonora's own API: a generated SVG attachment renders and its script does not run (`:42`), the "Updates" rail page opens (`:44-51`), agent instructions persist through `PATCH /api/agents/{id}` (`:60-71`), the chart sheet draws candles as SVG "Q37" (`:76-79`), a user message keeps `**` literal while links are clickable (`:96-103`), and a trading agent is created from the template "Owner decision Q9" (`:111-131`). Test 2 (`:146-193`) checks a chart PNG arrives as an assistant image card and survives reload. The only "rakazo" in it is the fixture script name (`tests/check_rakazo_ui.py`, `:7`) and the screenshot folder `.runtime/rakazo-parity/` (`:81`, `:85`, `:184`).
- `tests/check_rakazo_ui.py` (76 lines) is that spec's fixture: docstring "Real PostgreSQL/UI fixture: generated SVG attachment and a persisted cloud chart." (`:1`). No rakazo content.
- `tests/web/tradingview-sheet.spec.mjs:6` reuses the same fixture; `tests/web/voice.spec.mjs:313` and `tests/mobile/workspace.spec.mjs:259,284` only write screenshots into `.runtime/rakazo-parity/`.
- `check_rakazo_ui` is listed as one of five "Playwright stdin helpers" counted among the failing "harness or environment cases, not standalone checks" (`docs/lonora-specs/MANDATE_EXECUTION_PLAN.md:153`; "when run alone" is the wording at `:412`), i.e. it is not a standalone check.
- The current parity gate is against the owner's prototype: "Each phase passes when the reference and the app match side by side (Playwright, 390x844 and 1280x800, dark and light)" (`docs/lonora-specs/MANDATE_EXECUTION_PLAN.md:623`).

## 6. Owner decisions regarding rakazo (`docs/ui-reference/OWNER_DECISIONS.md`)

The file (102 lines, recorded 2026-11-09/10) answers 59 questions about the owner's own reference UI. The only line naming rakazo:

> "Q25 (OQ24) | Dictation: browser speech API first; a professional server-side transcription path (provider-based, inspired by Hermes/Rakazo-grade open-source approaches) as the upgrade." (`docs/ui-reference/OWNER_DECISIONS.md:53`)

Decisions in the same file that bear on this study's question (agent gives up; technical detail shown to the owner), none of which cite rakazo:

- "**The agent has access to every tool** and may use them; the UI shows the results in the reference's visual language (Q37)." (`:10`)
- "**The agent decides the shape of each answer** ... No keyword router, no forced interface, no separate classifier call." (`:12`)
- "**Skills and prompts are written in English only**" while "The model still answers in the owner's language." (`:13`)
- "**Lonora is the only channel to the owner**: no Telegram or other external delivery channels to the owner (Q53)." (`:9`)
- "«حالة الوكيل التفصيلية» is a per-device preference, off by default; the alert capsule always shows problems." (Q35, `:64`) — detailed agent status is hidden by default.
- "No spend cap (D4): ... error cards reflect the provider's actual error family." (Q22, `:50`)
- "Fenced code blocks are allowed as explanation ...; refusing code as a deliverable stays agent policy (D5)." (Q36, `:65`)
- "MCP: remote servers only ...; no local/stdio option shown." (Q56, `:95`)
- "**No further built-in brokers**": other brokers come through MCP, and "An MCP tool that can place a trade or move money is refused" (`:16`).

## 7. Explicitly rejected / removed from the rakazo import (stated)

- Desktop, billing and coding tools (`THIRD_PARTY_NOTICES.md:122`).
- Simulated adapters, computer execution, public signup, billing and spaces (`THIRD_PARTY_NOTICES.md:136-137`).
- Native notifications, demo adapters, spaces, billing and computer screens on mobile (`apps/mobile/NOTICE:43-44`); vendor sandbox, billing, SSO and notifications (`apps/mobile/NOTICE:53-54`).
- rakazo's TypeScript agent runtime: replaced by a Python runtime (`THIRD_PARTY_NOTICES.md:121`).
- Multi-user: "do not build multi-user now (Q46)" (`docs/ui-reference/OWNER_DECISIONS.md:18`), consistent with the notice's "single-owner API".
- A general terminal for the product agent: "The product Agent does not generate application code, expose a general-purpose terminal, execute model-authored scripts" (`docs/lonora-specs/NANOBOT_PARITY_AND_RELIABILITY_PLAN.md:13`, dated 2026-10-18). **This was later reversed in part** by D5/D7 (2026-11-08): "An agent may write and run code inside its own sandbox as a means to analyse, monitor or build skills" (`docs/lonora-specs/MANDATE_CORRECTIONS.md:15`). The two documents disagree; the later one is described as binding (`docs/lonora-specs/MANDATE_EXECUTION_PLAN.md:292`).
- The rakazo look itself, for web: superseded by `Lonora-Desktop-37.html` (section 1, item 3).

## 8. Summary of `docs/lonora-specs/NANOBOT_PARITY_AND_RELIABILITY_PLAN.md` (648 lines)

1. Title is now "Lonora Professional Trading Agent Environment Build Plan"; the filename is kept for links, and the plan "draws selectively from Hermes Agent, gbrain, Rakazo, and Nanobot" (`:1`, `:5`).
2. Status line: "implementation in progress on `feat/trading-agent-environment` from `80b0ff9`. The first context-admission capability has local verification; this does not establish completion of Wave 0/1" (`:3`). `README.md:42` in the same folder calls it "a proposal, not an implementation completion claim."
3. Mandate: a trading agent that does not write application code or run a general terminal (`:13`) — partly overridden later, see section 7.
4. Reference table (`:21-26`): Hermes and gbrain pinned and read; nanobot pinned; rakazo unpinned, to be pinned in Wave 0 (`:25`).
5. Seven architecture requirements R01-R07 (one owner per capability, simple authorization, reviewed analytics, parallel collaboration, knowledge, truthful interaction, code quality; headings at `:59`, `:79`, `:92`, `:102`, `:110`, `:122`, `:137`) and eleven chart requirements C01-C11 (headings from `:153` to `:244`). Only the headings were read, not the bodies.
6. Release gates include "Market truth: exact instrument identity and contract specifications" (`:48`).
7. Waves: 0 baseline and comparison (`:374`), 1 model-aware context management, token estimation instead of character counts (`:387`, `:391`), 2 persisted large results with `result_ref` paging (`:400`, `:406`), 3 skills runtime (`:416`), 4 model/tool protocol hardening (`:432`), 5 continuity and memory consolidation (`:445`), 6 operations and acceptance (`:460`).
8. Wave 4 is the part closest to the owner's complaint: "Use a bounded, shared repair budget for empty, truncated, or malformed responses" (`:437`); "If a tool-free fallback is used, it explains established facts or asks a necessary clarification; it does not simulate execution." (`:441`). It covers malformed model output, not a tool returning a domain error such as an unknown symbol.
9. Boundaries: "No new Agent framework, second Gateway, scheduler, journal, or memory store." (`:629`); "Do not claim 'Lonora outperforms Nanobot'" without published comparison (`:624`).
10. Status by evidence: four capability cards are marked VERIFIED in `IMPLEMENTATION_MATRIX.md:671-674` (ENV-CTX-01 wave 1, ENV-RESULT-01 wave 2, ENV-KNOWLEDGE-01 and ENV-SKILLS-PIN-01 wave 3; each of the four rows contains the word VERIFIED, but I did not read the full evidence cells). Wave 0's comparison, Chart Use and later waves are recorded as open (`PROGRESS.md:940`, `:957`). A later plan, the mandate plan below (started 2026-11-07, `docs/lonora-specs/MANDATE_EXECUTION_PLAN.md:3`), has its own engine track titled "engine parity with Hermes Agent" (`…MANDATE_EXECUTION_PLAN.md:35`); neither document says in the lines I read that it replaces this plan, so "overtaken" is my reading. An editorial note dated 2026-11-07 excluding backtesting was appended (`:635-648`). Unsure how much of waves 4-6 was delivered under this plan's name.

## 9. Summary of `docs/lonora-specs/MANDATE_EXECUTION_PLAN.md` (821 lines)

1. Status: "in progress. Started 2026-11-07. Wave 1 is implemented and integrated on the working branch ...; Wave 1.5 is implemented and its acceptance journeys pass locally ...; waves 2–4 are not started." (`:3`). Verification is local only; "GitHub CI has not run since about 2026-10-12, because the account is billing-locked" (`:7`).
2. Based on a gap analysis at `36bea7c` plus a source study of Hermes Agent at `a9ff979` (`:5`). rakazo is not a source for this plan; it appears only in the test names `check_rakazo_ui` and `rakazo-parity` (`:153`, `:204`, `:412`, `:429`, `:469`, `:539`, `:601`, `:674`, `:725`).
3. Foundations to keep (`:13-19`): one agent loop, fenced durable runs, checkpoint before effect (an interrupted mutating call returns `tool_execution_uncertain` and is never replayed), one financial executor, device-signed grants, nonce-deduplicated message admission, a networkless sandbox.
4. Nine critical defects (`:23-33`), among them cross-agent memory leakage in `search_internal`, a "model-independent 120k-char ceiling" that silently dropped evidence, one failing scheduler step halting all maintenance, and "No off-app delivery to the owner".
5. Wave 1 engine track (`:39-43`), relevant to "gives up": E1 "A guardrail controller replaces the hard `repeated_tool_call` failure. Limits end with a final reply instead of failing the run." (`:39`); E4 provider error taxonomy with backoff and fallback (`:42`). Trading track T1-T4 (`:47-50`): remove backtesting, execution integrity, owner restrictions and money limits, analysis tools.
6. Wave 1 was integrated on branch `ccr-9c66a289-3283wb`, and at the time of writing "has not been merged into `main`"; "Nothing has run against a real broker account, a real model provider or a real device." (`:54`).
7. Wave 1.5 "simplicity and access" (`:290-`): supervised maintenance steps and an LLM-independent watchdog (W15-0), one "Stop new trading / Resume" brake (W15-1), owner action cards in chat (W15-2), the ladder "No trading / Ask me / On its own" (W15-3), create and steer agents from chat (W15-4, `:317-321`), and further slices I did not read line by line (`:322-354`).
8. Reference UI (`:612-623`): six phases against `Lonora-Desktop-37.html`; phase 2 and phase 4a status sections exist (`:625`, `:677`), and a mobile shell port (`:728`). Round-4 rerun of phase 4a: 2104 pytest passed, 18 skipped, and the same 6 `test_web_browser.py` errors (`:725`).
9. Not started: Wave 2 (a `Responsibility` record, one wake primitive, one continuation primitive, event admission, outbox relay, task table with step log, self-improvement loop, per-agent model; `:737-750`), Wave 3 (push delivery, `contact_owner`, server-authored activity states, mobile trading parity, and "Peer outcomes and other wrapper markup are stored as structured metadata, so internal wrappers never reach the owner"; `:785-791`), Wave 4 (release pipeline, installer, backups, real-provider contract tests; `:807-817`).
10. Acceptance for waves 2-3 is one end-to-end scenario with the simulation broker, "with no live trades and no backtesting" (`:821`).

## 10. Side observation relevant to the owner's complaint (Lonora code, not rakazo)

Lonora already contains broker-suffix symbol matching, but not on the tool paths (implemented). `symbol_candidates` returns the exact name, else case-only matches, else "every name that only adds a broker suffix to it" (`packages/tools/src/lonora_tools/agents.py:72-91`; separators `.-_#!+` or a lowercase alphabetic suffix of at most 4 letters, `agents.py:55-56`). It is called only from `resolve_market` (`agents.py:120`), which is used when an agent is created (`agents.py:257`; `apps/api/src/lonora_api/routes/agents.py:98`). A second copy of the same suffix rule lives in `packages/contracts/src/lonora_contracts/instrument_names.py:32-51` for display names; its docstring gives `XAUUSDm` as an example (`instrument_names.py:4-5`).

The market, analysis, indicator and trade tools instead call `canonical_broker_symbol` (`packages/tools/src/lonora_tools/symbols.py:18-35`), which delegates to `catalog_symbol`: "exact, or the single case-only match", otherwise `symbol_not_found` or `symbol_ambiguous` with status 404 (`symbols.py:6-15`). No suffix matching. What happens next depends on a flag the first draft missed:

- With `require_exists=True` the error is raised: `market.py:78` (structure), `market_analysis.py:140,215,305`, `owner_actions.py:85`. On these, `XAUUSD` against a catalog holding only `XAUUSDm` fails with `symbol_not_found`.
- Without the flag (the default, `symbols.py:18`) the error is swallowed and the requested symbol is returned unchanged (`symbols.py:31-35`): `market.py:47,58,65` (instrument, quote, candles), `chart_indicator.py:20`, `trade.py:634`. On these, `XAUUSD` is passed as typed to the broker or market provider; what error that then produces was not traced (unverified).

In neither case does the code shown return a candidate list. A `symbols` tool function that returns the broker's full symbol list exists (`packages/tools/src/lonora_tools/market.py:40-42`); I did not trace whether it is exposed to the model, nor what text the model receives for `symbol_not_found`.

## Weaknesses and risks seen in this area

- **Attribution is inconsistent and unverifiable.** Five different rakazo revisions are cited across four files (`THIRD_PARTY_NOTICES.md:119,129`; `apps/mobile/NOTICE:8,49`; `docs/FRONTEND_STRUCTURE.md:5`; `docs/persistent-trading-teammate.md:11`), with two different copyright holder names (`THIRD_PARTY_NOTICES.md:120` vs `:130`). `apps/mobile/NOTICE:1-33` reads as the Tampletgrok notice carried over (it opens "Tampletgrok / Copyright 2026 Tampletgrok contributors"; the Tampletgrok repository was not available to compare), including statements about paths such as `packages/mock-adapters`, `examples/api-integration` and `packages/ui-tokens/assets/AppIcon.icon` (`apps/mobile/NOTICE:18,21,31`); only the absence of `packages/ui-tokens/assets` was checked.
- **A test name that promises something it does not test.** `tests/web/rakazo-parity.spec.mjs` asserts no parity with rakazo (section 5). A reader of the plan ("rakazo-parity ... 50 of 50", `docs/lonora-specs/MANDATE_EXECUTION_PLAN.md:725`) could conclude rakazo behaviour is covered.
- **A planned comparison that was never run.** rakazo is listed as a reference for run flow and steering with the instruction to pin and inspect it first (`docs/lonora-specs/NANOBOT_PARITY_AND_RELIABILITY_PLAN.md:25,382`), and no record of that work exists. Claims that Lonora "has" rakazo's chat/run behaviour should not be made from these documents.
- **Dead inherited code.** `apps/web/src/pages/Board.tsx` (584 lines) and `ActivityList.tsx` (276 lines) are unimported; `docs/FRONTEND_STRUCTURE.md:31-32,185` still documents them, and lists `pages/Shell.tsx`, `Auth.tsx`, `Onboarding.tsx` (`:27-29`) which no longer exist under `apps/web/src/pages`. The document was last touched 2026-11-10 but describes the pre-reference tree.
- **Two token sets and two UI generations live side by side** (`packages/ui-tokens/TOKENS.md:7-8`): the legacy rakazo/shadcn set for old screens and mobile, the reference set for the new shell. Old screens are still imported by the new shell (`apps/web/src/shell/pages.tsx:11,12,14,62`; `apps/web/src/shell/ChatMenu.tsx:12-14`).
- **Plans contradict each other on agent code execution** (`docs/lonora-specs/NANOBOT_PARITY_AND_RELIABILITY_PLAN.md:13` vs `docs/lonora-specs/MANDATE_CORRECTIONS.md:15-17`), and the notices still say computer execution was removed (`THIRD_PARTY_NOTICES.md:137`).
- **Large plan documents with status prose instead of checkable state.** The mandate plan is 821 lines and the build plan 648; status depends on branch names (`ccr-9c66a289-3283wb`, `w15-a1`) and local-only runs, with CI dark since about 2026-10-12 (`docs/lonora-specs/MANDATE_EXECUTION_PLAN.md:7,54`).
- **Symbol resolution is split across matchers with different rules, and one of them behaves differently per call site** (section 10): the suffix rule exists twice (`packages/tools/src/lonora_tools/agents.py:72-91`, `packages/contracts/src/lonora_contracts/instrument_names.py:32-51`) but the tool path uses exact/case-only matching, raising on some tools and silently passing the unmatched symbol through on others (`packages/tools/src/lonora_tools/symbols.py:18-35`). This is a candidate cause for the "symbol not found, agent gives up" complaint; the link to the owner's actual incident is not demonstrated.

## Not read / unsure

- The five cited rakazo revisions could not be opened (shallow clone); all file comparisons were made against rakazo `cd7e20e`, a later revision, so line-difference counts are indicative only.
- Lonora's git history does not show the original import commit(s) of rakazo/Tampletgrok code; file-add dates returned by `git log --diff-filter=A` point at recent merge-era commits, so I give no import date.
- `apps/mobile` contents were not diffed against rakazo; only route file names were compared.
- Whether any icon, font or image asset from rakazo is still shipped (`apps/mobile/assets`, `apps/web/public`) was not checked.
- Which inbox "Rakazo-style semantics" spec 02 refers to (`:512`) is not defined there; not traced in code.
- `MANDATE_EXECUTION_PLAN.md` lines 56-221, 322-605 and 625-736 (per-slice delivery, verification tables, reviews) were skimmed by heading, not read in full. `NANOBOT_PARITY_AND_RELIABILITY_PLAN.md` lines 59-345 and 472-607 (R/C/B requirement bodies) likewise.
- `IMPLEMENTATION_MATRIX.md:671-674`: confirmed only that each row contains "VERIFIED"; the evidence cells were not read.
- Whether Wave 1 / 1.5 branches are now merged into `main` (the plan text says not yet at 2026-11-08; later PR merges #55/#56 exist in the log) was not verified.
- Status in code of server-side dictation (Q25) and of the agent computer (D5-D7) was not checked.
- What the model is told when a tool raises `symbol_not_found`, and whether the agent has a tool to list broker symbols, belongs to another section and was not traced.
- The Tampletgrok repository itself was not available; its relationship to rakazo is taken from the notices.

## Verification log

Independent check against Lonora HEAD `9f5b1da` and rakazo `cd7e20e` (shallow, confirmed). About 150 `path:line` citations were opened (every one in the file); file counts, line counts, grep counts and the git-log claim in "Method" were re-run. Roughly 130 were correct as written, including all verbatim quotations checked.

Corrections made (before -> after):

1. Section 10, main claim. Before: market, analysis, indicator and trade tools all fail with `symbol_not_found` on `XAUUSD` vs `XAUUSDm`. After: only call sites with `require_exists=True` raise (`market.py:78`, `market_analysis.py:140,215,305`, `owner_actions.py:85`); `market.py:47,58,65`, `chart_indicator.py:20` and `trade.py:634` swallow the error and pass the symbol through unchanged (`symbols.py:31-35`). Also: `symbols.py:6-15` is `catalog_symbol`, not `canonical_broker_symbol` (`:18-35`); added `owner_actions.py:85`, the second copy of the suffix rule (`instrument_names.py:32-51`), the callers of `resolve_market`, and the existing `symbols` function (`market.py:40-42`). Matching weakness bullet rewritten.
2. Headline 2. `THIRD_PARTY_NOTICES.md:3-9` covers nanobot only -> Hermes cited at `:11-12`; added that "nothing taken from the runtime" was not checked by code comparison.
3. Headline 3. "Since 2026-11-09" had no citation -> tied to `OWNER_DECISIONS.md:3`; "same at `MANDATE_EXECUTION_PLAN.md:614`" -> wording there differs, quoted; "rakazo-derived screens are being displaced" softened.
4. Headline 1. "carry the header `// ...`" -> "contain the attribution line" (some of the 36 are CSS files). Counts 26/5/2/3 confirmed.
5. Section 2. `apps/mobile/NOTICE:39-45` -> `36-45`; `NOTICE:10-11` -> `10-12`; garbled sentence about the first line of `THIRD_PARTY_NOTICES.md` rewritten.
6. Section 3.1 primitives. "differ by 2-12 lines out of 20-250" -> 20 of 23 differ by 2-9 lines out of 14-256; larger ones listed with numbers (`dialog` 21, `field` 17, `input-group` 12, `input` 9 of 20).
7. Section 3.1 `Artifacts.tsx`. "299 not in rakazo's" -> 268 by my exact-line recount; "largely rewritten" marked unverified for the other files.
8. Section 3.1 screens still used. The list of four was incomplete -> added `SettingsOverlay` (lazy, `pages.tsx:62`), `ModelSettingsOverlay`, `VoiceSettingsOverlay`, `Knowledge` -> `KnowledgeSection`, `ScratchpadSection`, `bot-picker`. "Dead code" for `Board.tsx`/`ActivityList.tsx` kept (grep confirms no importer) but qualified.
9. Section 3.1 `RichResponse.tsx`: line number added (`:4`), import path corrected to `@lonora/chat-ui/web`.
10. Section 3.2. `routes.ts:142` -> describes `sectionOf` placing page `activity` in section `updates`, not a route rename. Spec 02 sentence: "confirms ... inherited" -> stated, unverified in code.
11. Section 4. "The present study is the first" (unverifiable) -> "no record found in `docs/lonora-specs`".
12. Section 5. Added `:7` for the fixture name; `:153` does not say "when run alone" (that wording is at `:412`).
13. Section 8. R01-R07 `:59-137` and C01-C11 `:153-244` were heading positions, not ranges -> stated as headings only. Wave 1/2 descriptions given supporting lines (`:391`, `:406`). "Overtaken by the mandate plan" -> marked as interpretation; note range `:639-648` -> `:635-648`.
14. Section 9. rakazo occurrences in the mandate plan: 4 lines -> 9 lines listed. W15-4 `:318-321` -> `:317-321`.
15. Weaknesses. NOTICE "copied whole" and "paths Lonora does not have" softened to what was checked; shell import citations widened.

Remaining doubts:

- Line-difference counts against rakazo use `grep -Fxv` (exact line match) on a later rakazo revision; they are indicative only.
- "Dead code" for `Board.tsx` and `ActivityList.tsx` rests on grep, not on a build.
- Whether Lonora's Python runtime borrowed any design from rakazo's runtime was not examined by anyone; only the notices speak to it.
- Section 9 items 3-9 summarise long plan lines; I confirmed the cited lines exist and contain the named items, but did not verify the plan's own claims (branches, test counts) against git or code.
- `IMPLEMENTATION_MATRIX.md:671-674`: each row contains "VERIFIED"; evidence cells still unread.
- What the broker/provider returns when an unmatched symbol is passed through, what the model sees for `symbol_not_found`, and whether the `symbols` tool is exposed to the model are untraced.
- The count "59 questions" was confirmed only as 59 table rows starting `| Q` in `OWNER_DECISIONS.md`.
