Superseded by VISION.md

# Handoff: finishing the reference UI and the production cut-over

Written 2026-11-10 by the lead Claude session, for the next agent (Cursor or any coding agent). The owner's instructions
in Arabic are quoted where they matter. Owner-facing replies are in Arabic. Code, prompts, skills and
commit messages are in English.

## 1. Goal and binding rules

- **Goal:** replace `apps/web` with the reference UI `docs/ui-reference/Lonora-Desktop-37.html` in
  six phases. The reference is the source of truth, the backend changes to serve it, and Lonora's
  avatar stays. Then run the new Lonora in production on the owner's VPS.
- **Binding decisions:** `docs/ui-reference/OWNER_DECISIONS.md` (Q1–Q59 and the standing rules).
  The most important rules:
  - Money moves only via the signed grant or an approval card, at the single executor. Exits
    (stop, close, cancel, reject, revoke) are always admissible. Journal and authority records are
    append-only. Shadow trading is removed.
  - MetaApi is the default broker; there is no Alpaca. Other platforms come later: MCP read-only,
    then plugins behind the single executor.
  - Fresh start: no data migration and no backward compatibility with old data. The only exception
    is the owner's three stored keys (section 5).
  - Model-facing text (prompts, skills, tool text, server text the model reads) is English only.
    Owner-facing cards and labels are in the owner's language (Lingui ar/en).
  - Never print or paste secrets.
- **Code style:** see `CLAUDE.md` and `AGENTS.md`: surgical changes, minimum code, tests that fail
  without the fix.

## 2. Repository state

- `main` = `2dec6d2` (Merge PR #48). Alembic head: `0058_skill_versions`.
- Merged so far:
  - phase 1 (capability map, tokens);
  - phase 2 (shell, lists): #33-era PRs, #44 mobile part 1;
  - phase 5 settings/auth (#39, plus follow-up #52);
  - phase 4b domain pages (#48);
  - fresh-start notes (#47, #49).
- Every merge goes through a PR with a merge commit, after verification plus the local gate
  (section 4). Merge with an expected head SHA so a late push is not merged unseen.

## 3. Open work, in suggested merge order

Each PR branch has (or will have) a "Status for the next agent" section at the top of its PR
description, written by its last worker. Read it first. The heads below were current at handoff;
`git fetch` for newer ones.

### PR #53 `ui/phase-5-settings` (follow-up to phase 5): small, merge first

Done: one shared "password" rate-limit bucket for login, mobile login and onboarding; chat-header
gating (`openPage` returns early until the agent or group is loaded).

Left (tests only, behaviour is correct):

1. `tests/test_auth_rate_limit.py:41/:43`. The `# pyright: ignore[...]` comment swallows the
   `== 10` / `== 500` comparisons, so the asserts check nothing. Put the comparison before the
   comment. Also assert the 429 body `rate_limited` and the `Retry-After` header in the
   split-route test.
2. Specs still leak agents into the 20-agent creation cap: agent-alert, agent-model (web and
   mobile) and attention. Delete them in `finally`/fixture cleanup. Make simple-lonora (web and
   mobile) robust to the cap.
3. Add a test for the group half of the gate (`ChatMenu.tsx:90`, `group && !agentsLoading`).

### PR #46 `ui/phase-4-agent` (phase 4a agent pages): small, merge second

All round-4 items are done. Left:

1. MEDIUM. `apps/web/src/shell/agent/chart-geometry.ts:324`. Commit fd54cf1 removed the note
   y-clamp for ALL notes. In-range notes near the top of the plot now lose their text to the clip
   (worst at 330×170 with an oscillator pane). Hide only off-range notes; keep in-range note text
   inside the plot. Add a unit test.
2. `ChartSheet.tsx:340`: a failed first chart list is never retried. Add backoff, or re-list on
   the next scene_updated while `listed` is null.
3. `ChartSheet.tsx:319`: an unknown-scene event causes two GET /api/charts instead of one.

### PR #42 `fix/agent-behaviour-baseline` (agent reply guards): scope was cut down

Lead decision: the natural-language heuristics kept failing both ways after three rounds, so they
were removed (claim recogniser and repair turn, stop/resume guard, D5 code-block rewriting). Only
one structured rule remains:

- After an owner-started request (not wake runs), if any effect call is still uncertain and was not
  reconciled, append ONE line in the conversation language: not confirmed yet, being checked, will
  not be resent.
  - Effect calls: `trade_execute`, and `goal_step_execute` (read its NESTED `result.status`,
    including the deduplicated replay).
  - Uncertain means ambiguous, operation_ambiguous, tool_execution_uncertain, submitted or
    reserved.
- It also applies on the finish_turn, round-limit and guardrail paths, respects the 24-part cap,
  and never replaces text or cards.

Head `67d5107` implements the cut. Its verification was interrupted, so verify it:

- the rule above;
- removal complete, with no dead code;
- tests with the real result shapes;
- the 109-case eval rerun (gpt-5.4-mini, concurrency 1), with per-case changes reported vs G0 and
  vs 1514678.

No migrations.

### PR #43 `ops/install-update-backup` (installer, update with rollback, backup, restore): needed for production

- Head `84942f3`, round 4, "final gate".
- The lifecycle test passed 21/21 at `0667e50`. Round 4 changed the CLI, so rerun it with
  `docs/handoff/gate/ops-lifecycle.sh`.
- Verify that round 4 did these:
  1. `NEVER_RESTORED` includes `LONORA_PROJECT` and `LONORA_PROXY_LISTEN`.
  2. No Gateway ever runs while `maintenance/on` exists, on every path: gate_pinned,
     `lonora maintenance on` (takes the lock and stops the Gateway), update, rollback, restore,
     the backup-failure path, and a failed compose stop.
  3. Goal and task owner exits are in the rollback-hold fingerprint.
  4. With the workspace overlay, the API starts when `/run/lonora-analysis` is missing (e.g. after
     a reboot).
  5. An unfinished restore has a way out, and prune protects its files.
  6. gpg temp homes are scoped per project.
  7. `--env-from` validates the file before writing anything.
  8. `--behind-proxy` validates the port and address.
  9. CLI messages use the real command name (`lonora-<project>` when needed).
  10. build-from-source pins by digest.
- Merge #43 before the VPS cut-over (section 5).

### PR #51 `ui/phase-3-chat` (phase 3: the conversation): round 3 in progress

Head at handoff `e2d5581` (WIP may follow). Round-3 list:

- **MUST (money and truth)**
  - `Cards.tsx:320`: a pre-send-blocked order (failed + not_sent) shows Sent and Accepted in the
    order sheet timeline. Render the shared `line.steps`.
  - `Cards.tsx:412`: a broker rejection must never say "try again".
  - `AgentSheet.tsx:527`: the freeze wording must be per row.
  - Retry never re-sends money: tickets get `started_by_run_id` in `automation/background.py:46`.
    Test with a real ticket and a real Task.
  - «حسم» jumps to a resolve card in another conversation (needs thread_id from
    trading_readiness).
- **MUST (round-2 leftovers)**
  - M8: Arabic server text in current_work and pending_card_id reaches the model
    (`agent_state.py:87-98/153-155`).
  - M11: pass `risk_currency_required` through `errors.py`.
  - `ToolsSheet.tsx:72` defaults to «دون تنفيذ» while loading.
  - MandateSheet Full subtitle for fixed-pair agents (Q17); "Mandate details" opens the signed
    grant card.
  - Lingui msgctxt for «مكالمة صوتية» and «تعليق».
  - Mobile mention cap must not apply to groups (`apps/mobile/app/thread.tsx:1039`).
  - `shell.css:304` margin is desktop-wrong.
  - Older-history paging retries in a tight loop after a failure (`Conversation.tsx:714`).
- **SHOULD**
  - `sessions.py:225`: call logging idempotency and direction.
  - Load-bearing tests for M2(a), M2(d) and M4.
- **Migrations:** 0046–0048 must be rechained onto the head at merge time (`0058_skill_versions`,
  or #50's 0050 if that merges first). One alembic head only.

### PR #50 `ui/phase-3-conversation` (generative UI cards, slice S-A01): round 4 in progress

Head at handoff `d18daec`. Round-4 list:

- **MUST**
  - HIGH: one shared output budget for nested lists in BOTH evaluators
    (`packages/contracts/src/lonora_contracts/genui_expr.py`, `packages/core/src/genui/expr.ts`).
    Catch MemoryError/RecursionError around compile and render.
  - Taint for opportunities (`market_opportunity_create/update`, opportunity_id in SOURCES).
  - Taint for owner-card continuations (inherit from the card's proposing run).
  - Privacy guard: check exactly the text the client shows (label ?? value, plain-string options).
    Restore the raw head title/sub scan.
- **SHOULD**
  - Quote sparkle inline.
  - Leased-run folded message requeue.
  - §9.4 typed-constant mode or an explicit deferral.
  - PRICE_KEYS stop_loss/take_profit/levels.
  - TS/Py evaluator divergences into expr-vectors.json.
  - Add `tests/web/genui-engine.test.ts` to the CI tsx list.
- **LOW:** UI and test items (in the PR thread).
- **Migration:** 0050 must be rechained onto the head at merge time.

### Not yet a PR

- `ui/phase-6-calls` (phase 6: call screen, strip, incoming, Q58 sheet):
  - head `95d60a2`, reserved migration 0059;
  - the call capsule waits for #51;
  - open a PR after #51 merges, then review.
- Mobile part 2 (reference shell for the conversation on mobile): not started; it waits for #51.

## 4. How the lead verified and merged

1. **Review.** Each finding from a review goes to an independent checker at the new head. Each
   claimed defect gets skeptics who try to refute it, and only confirmed ones are sent back. Rounds
   repeat until the items are done and no confirmed regression is left.
2. **Local gate:** `docs/handoff/gate/gate.sh <worktree> <label> [check scripts]`.
   - It runs install, lint, check, build, web unit tests, a fresh-DB migrate, pytest, the named
     `tests/check_*.py` scripts and the full Playwright suite on a fresh `_ci` DB.
   - Run only one Playwright suite at a time.
   - Compare failures with a run on `main`. Some specs are order-dependent; rerun them alone before
     calling them regressions.
3. **i18n:** after merges, `pnpm --filter @lonora/web i18n` must report 0 missing for ar.
4. **Migrations:** keep one alembic head. Rechain the merging PR's first migration onto the
   current head.

## 5. Production: the owner's VPS

### State now

- **Host:** Ubuntu 24.04, 2 vCPU, 7.8 GB RAM (about 5.4 GB free), 60 GB free disk, Docker 29.
- **Already done:** the owner had rakazo and nanobot deleted. Done and verified; their archive is
  deleted too.
- **traefik:** runs on the host network and owns 80/443, with the file provider at
  `/docker/traefik/dynamic/` (codex-tunnel.yml, erp.yml, lonora.yml, wakeed.yml; watch=true).
  - `lonora.yml` routes `Host(lonora.lork.cloud)` to `http://127.0.0.1:18010`, and the
    `/download` router (priority 1000) to `http://127.0.0.1:18020`.
  - Certificates come from the letsencrypt certResolver.
- **Old Lonora:** compose project `lonora` in `/opt/lonora` (not the CLI from #43).
  - Containers: lonora-api, lonora-gateway, lonora-browser-1, lonora-searxng-1, lonora-downloads
    (nginx), lonora-db.
  - Volumes: lonora-database, lonora-artifacts.
  - Networks: lonora-net, lonora-research.
  - Image: `lonora-local:latest`.
- **Keep:**
  - `lonora-analysis.service` (the systemd workspace host, socket
    `/run/lonora-analysis/host.sock`); the new install uses it through the workspace overlay;
  - `/opt/lonora-mobile-build`: it holds the Android signing keystore. Never delete it.
- **Other projects that must never be touched:** erpsystem, wakeed, codex-tunnel, traefik and its
  other files.
- **Source:** the repository is public, so the VPS can `git clone`/`fetch` anonymously.
- **Old app files:** `/opt/lonora/downloads/lonora.apk` (+ lonora.json) and the OTA tree
  `/opt/lonora/releases/ota/`. Installed apps on runtime e4a51ffd depend on it.

### Owner decisions for the cut-over

- «تحويل فوري، العنوان التجريبي لا اريده»: switch lonora.lork.cloud to the new install as soon as
  it is ready. No test host.
- «يمكنك حذف lonora و اعدة بناء المشروع من جديد كا مشروع جديد لكن استخدم نفس المفاتيح السرية
  الموجودة الان»: rebuild as a new project and reuse the current secrets.
  - From the old `.env`, `--env-from` copies the encryption key, bootstrap token, webhook secret,
    passkey fingerprints, domain and tuning keys.
  - The old DB's `ln_secrets` holds 3 keys, carried by phase 3: provider/openai, provider/zai and
    broker/<MetaApi account id>.
- Destructive steps on the VPS were confirmed by the owner directly in the VPS session. Keep it
  that way: show the owner the dry run or plan, and get their go-ahead before each phase.

### Steps (scripts in `docs/handoff/vps/`)

Run as root on the VPS, from a copy of that directory. Every script prints names only, never a
secret value.

1. **`phase1-install.sh <full main sha after #43 merges>`.** No effect on the old stack.
   - Clones to `/srv/lonorabot`.
   - Runs `infra/compose/build-from-source.sh` (loopback registry 127.0.0.1:5055, capped at 1 CPU
     and 2 GB).
   - Runs `install.sh --home /opt/lonora2 --project lonora2 --behind-proxy 127.0.0.1:18030
     --domain lonora.lork.cloud --env-from /opt/lonora/.env` with the workspace and research
     overlays.
   - Copies the APK, lonora.json and the OTA tree into `/opt/lonora2/.runtime/releases/`.
   - Checks `/ready` and `/download/lonora.apk`.
   - Before running it, check the final #43 options: if round 4 renamed or added flags, adjust the
     script. Use the digest that build-from-source prints if #43 now requires it.
2. **`phase2-switch.sh`.**
   - Swaps only the urls in `lonora.yml` (18010/18020 → 18030), validating the YAML and moving it
     atomically.
   - Probes every host in the traefik directory over https (status plus certificate verify) and
     http, before and after.
   - Puts the file back automatically if any other site changed or lonora.lork.cloud does not
     answer.
3. **Owner signs in.** The owner opens https://lonora.lork.cloud and creates the owner account
   with the bootstrap token (the same token as the old install, because `--env-from` copies it).
   - If the owner does not have it, show it to them privately in the VPS session, never in a shared
     chat.
4. **`phase3-import-secrets.sh`.** Exports the 3 rows (still encrypted) from the old lonora-db and
   imports them in the new api container (`import_secrets.py`).
   - Provider keys go through the app's secret store.
   - The MetaApi account goes through `connect_account` (verified with MetaApi) and is created
     **disabled**; the owner enables it.
   - It is idempotent.
   - Tested locally against a fresh DB at main's schema: providers resolve, the broker token is
     stored, no value is printed.
5. **`phase4-remove-old.sh`.**
   - Run `DRY_RUN=1` first, then the real run after the owner confirms.
   - Refuses unless lonora.yml already points at 18030 and the new install is ready.
   - Runs `compose down --volumes` for project `lonora`, removes its images and `/opt/lonora`, and
     diffs other containers before and after.
   - Keeps `lonora-analysis.service` and `/opt/lonora-mobile-build`.

After the cut-over, merge the remaining UI PRs and update production with `sudo lonora update
<image ref>` (build-from-source again for each new main).

## 6. Things that went wrong before (avoid repeating)

- **Docker Hub rate limit (429) on base images:** pull from `mirror.gcr.io/library/...` and tag
  locally (see `ops-lifecycle.sh`).
- **pyright ignore comments:** a `# pyright: ignore` placed before the comparison silently turned
  asserts into no-ops.
- **Bash:**
  - `x="" y="" name value` is a command, not a declaration;
  - files that hold secrets must be created mode 600 (`umask 077`) from the first byte.
- **Removing a traefik file:** it can hold shared TLS or catch-all routers. Check its content and
  probe every other host (https with certificate verify, plus http) before and after.
- **The VPS session refuses** destructive steps and production DB reads unless the owner confirms
  in that session. That is intended; don't route around it.
