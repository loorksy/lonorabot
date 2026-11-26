# Handoff to Cursor (written 2026-11-20 by the lead Claude session)

You are taking over the Lonora mandate work from a Claude Code session that may stop at any moment
(quota). Read this whole file before acting. Everything here is true as of the commit that adds it;
anything newer on the branches named below was done after it, so check `git log` first.

## 0. What binds you

- `VISION.md` on `main` is the owner's mandate. It is executed literally, phases 1-8,
  "to the letter, no patching, no workarounds". Key clauses you will touch:
  - 0.4: every owner-facing text and doc is true at every commit;
  - 4: the Full/Ask modes;
  - 4.7: a paused agent may still reduce risk;
  - 6: the safety core, which is never weakened;
  - 10: the fixed cards and GenUI slots;
  - 14: the removal plan. Its order is: add the new path, then move what survives, then delete the old path. The 11 core tests of 14.1.2 must pass after every step;
  - 17: Arabic first.
- Amendment 1: there is no Stop control ("لا داعي ل زر ايقاف ابدا").
- `AGENTS.md` and `CLAUDE.md` apply. Work on focused branches and merge to `main` through a PR.
- **Language:** reply to the owner in short Arabic. Code, commits and docs are in English. When the owner writes «بلعربي», answer fully in Arabic with no English terms.
- **Decisions:** never ask the owner "how" questions. Decide, and say what you chose. Every recorded decision is in section 4.

## 1. Owner's standing rules (verbatim intent, all still in force)

- «معك كل الصلاحيات لكن لاتلمس اي مشروع يعمل»: you have full permissions, but touch no running project.
- **Secrets:** never print or paste them (`.env`, `ACCESS.txt`, keys, tokens). Refer to them by name only.
- **Production:**
  - Production is ONLY `/opt/lonora2` on the VPS. Never route around the normal update path.
  - Never delete or modify `/opt/lonora-mobile-build`.
  - `lonora-analysis.service` stays: do not stop, disable or modify it, and do not touch `/opt/lonora-analysis` or `/etc/lonora-analysis`.
  - Never touch erpsystem, wakeed, codex-tunnel, or any traefik file other than `lonora.yml`. Rakazo was reinstalled by someone else: do not touch it.
  - The four switched-off EURUSDm watches are the owner's.
- **MetaApi / Exness:**
  - The demo MetaApi account `acadead6` (Exness-MT5Trial16) stays UNDEPLOYED until the very last step («اترك قصة الحساب الى اخر شي»).
  - The two real Exness-MT5Real11 MetaApi accounts must never be touched.
  - No credential ever leaves the VPS or enters a message.
- **Scope:** GitHub work is limited to `loorksy/lonorabot`.
- **The owner's latest orders:**
  - «استمر وادمج كل ما ينجح»: continue, and merge everything that passes;
  - close all PRs down to zero;
  - then run a full user cycle and fix every error;
  - the UI/UX and how the cards look must be right.

## 2. Where things are

### Production
- main **3e8bcfb1** (batch 20) is live. Alembic head is `0127_no_supervision_grants`.
- The last backup is `/opt/lonora2/backups/lonora-20261120T074222Z.tar.gpg`.
- Data shape: 3 agents (Lonora, plus Dino and دكستر, both trading specialists), all in Ask, none paused. 0 positions, 0 orders.
- The 2 trading agents sit at the old ladder level "analysis", so they cannot trade even in Ask. W-AUTH slice D (migration 0128) fixes this; see `docs/handoff/prod-counts-2026-11-20.md`.
- **Updating** follows `docs/operations.md`: `sudo lonora update <version>` with `LONORA_HOME=/opt/lonora2`. It backs up, migrates, and rolls back by itself.
- **Before a deploy:** run read-only prechecks: counts of the tables the migrations touch, positions and orders, the version in table `lonora_v2_alembic`.
- **After a deploy:** run the same counts, then check:
  - `/health` and `/ready`;
  - the gateway steps, which must have no failures;
  - the startup ERROR lines; only the usual one-off `workspace_unavailable` is expected;
  - that `lonora-analysis.service` is still active.

### GitHub
- CI does NOT run on this repository: jobs end in about 1 s, most likely a billing or minutes problem. The local gate in section 3, `scripts/gate.sh`, is the only gate. `.github/workflows/ci.yml` only sets up the tools and calls that same script, for the day CI runs again.
- **Open PRs:** only `#180` and `#162`, both old W-AUTH work. Close them without merging once R2 lands (see `docs/handoff/wauth-plan.md` §2). Each comment you post on GitHub ends with an attribution footer.

### Branches in flight (pushed; check each one's latest commit)

1. **`ui/v38-port`** (>= 9445331f): the port of the owner's Claude Design pass v38. The design files are in `docs/ui-reference/`: `Lonora-Desktop-38.html`, `UI_CHANGES-38.md`, `UI_BUGS-38.md` and `PORT_MAP-38.md`.
   - Part 1 (global defects, the fixed cards, settings) is ported, with review fixes.
   - Round 2 may be unfinished. It covers:
     - merging main 3e8bcfb1 into the branch;
     - the slot-height decisions LD1-LD3 below;
     - the open findings in `docs/handoff/v38-open-findings.json` (`screenshot_findings_after_round1` and the partial re-review ones);
     - then the full gate and screenshots.
   - A WIP snapshot may exist on `wip/ui-v38-port`. Never merge `wip/*`; read it only to recover work.
2. **`fix/flakes-20`** (>= de8dbcfb): web Playwright tests that failed only under machine load.
   - Round 1 is fixed: the Integrations rows wait for their capabilities; the Composer's ResizeObserver loop; the specs wait for real readiness signals.
   - Round 2 may be unfinished. It covers:
     - making every spec's `finally { context.request.delete(...) }` cleanup unable to replace the body's error (move it to `afterEach`, or catch it);
     - `chat-lists.spec.mjs:313`: the "Add to list" sheet misses the group under load;
     - `genui.spec.mjs:469`: find the real hanging step;
     - `tests/test_memory_privacy.py::test_discovery_arms_stay_bounded_and_index_compatible`: its assertion depends on the planner.
   - Note: DELETE /api/agents/{id} is NOT slow (68 ms median). The "DELETE timeout" in reports is the masking cleanup.
3. **`wauth/r2`** (>= 923cf302): W-AUTH. It already contains:
   - R1 server slices A1-A4: the safety assertions ported to the modes; the survivors moved to `lonora_trading/ownership.py`; one stale-target check at the door (6.6); `trading_mode` on every read; `GET /owner-actions/mandate?agent_id=`;
   - slice D: migration `0128_authority_migration`;
   - main merged in.

   **Still to do on this branch, in this order:**
   - (a) `check_delegated_scope.py` and `check_agent_binding.py` now fail with `tolerance_required`, because D changed `default_level` to supervised. Update them to the true Ask behaviour: pass a tolerance and expect a pending Trade Approval card.
   - (b) A5: enrolling a call device outside the grant flows (web NotifyPages, mobile incoming-call-settings).
   - (c) A6: the client readouts show the mode:
     - the composer chip, the agent page and the sheet;
     - the mobile safety pill shows only the uncertain state;
     - a Trade Approval refused by the tool's pre-check shows «Not sent», not «Failed».
   - (d) S1a: no new grants. The Mandate card is the only way to Full. Server, web, mobile, core and texts change together; delete the ladder API and the grant screens, as the plan lists.
   - (e) S1b: the `grant_authority` card kind goes.
   - (f) v38 part 2 rows, which go with A6/S1a: the composer mode chip and mode menu, the agent page, and removing MandateSheet. Also add back the AuthFlow slide «كل وكيل يستأذنك… حتى توكّله بلمسة» and the Welcome line «لكل وكيل تفويضه: يستأذن أو وكّله», which become true only now.
   - (g) Measure the Mandate slot with the `previous_grants` line (`tests/web/genui.spec.mjs` records `mandate-migration-card-height`), then decide by LD1.

   **Deploy rule:** D, S1a and S1b deploy TOGETHER (release R2). Before deploying, re-run these production queries:
   - the plan's §4 queries;
   - agents with `trading_mode='full'` whose level is 'analysis';
   - live `trigger='activation'` Runs and waiting grant-management Runs;
   - open supervisor holds.

### Next batches
- **Batch 21:** `ui/v38-port` + `fix/flakes-20`, after both are green.
- **Batch 22:** W-AUTH R2 (D + S1a + S1b + A5 + A6 + v38 part 2). Then close #180 and #162.
- **Then:**
  - R3 (S3, then S2a-S2d) per the plan;
  - the full user cycle (VISION 16 acceptance scenario);
  - the UI card verification at 390 and 1280 px, in Arabic and English, light and dark, on web and mobile. Fix every defect;
  - a final audit of every mandate clause, and a final report in Arabic;
  - LAST, the Exness account: the owner checks the MT5 login or opens a new demo, then reconnects from chat.

## 3. The gate (run it in full before every merge to main)

Run `LONORA_DATABASE_URL=<a PostgreSQL 16 server> bash scripts/gate.sh`. Only the URL's server and role are used: the role must be allowed to create databases, and the gate makes a fresh database for each step that needs one and drops them all at the end. The gate sets its own CI-only dummy values (Fernet key, bootstrap token) and puts every `packages/*/src` and `apps/*/src` of the checkout on `PYTHONPATH`. Its header lists the one-time setup. It stops at the first failure and runs, in this order:
- `bash scripts/build.sh`: ruff, ruff format, pyright strict, the tool reference and manifest check (`export_agent_tool_reference.py --check`), the GenUI catalog check and the policy distribution, then pnpm lint, check and build.
- `pnpm --filter @lonora/web i18n`, which refreshes the catalogs in place, with Arabic at 0 missing.
- `bash scripts/migrate.sh` on a fresh database. There must be exactly one alembic head.
- Full pytest: `.venv/bin/python -m pytest -q tests`. It includes `tests/test_acceptance_scenario.py`, which runs `scripts/agent_eval/acceptance.py --offline`.
- `python tests/run_foundation_checks.py --isolated-databases` (109 check scripts and 16 pytest files; each gets a fresh database). Five of the core tests of VISION 14.1.2 are check scripts there; the other six run in the full pytest. `tests/test_gate.py` fails if the gate stops running one of them, or if `ci.yml` gets a test list of its own.
- Every TypeScript unit test: `pnpm exec tsx --test tests/web/*.test.ts tests/mobile/*.test.ts`.
- The FULL Playwright web suite (`pnpm test:web`) and the FULL mobile suite (`pnpm test:mobile`), with `--trace off`. Each runs on a fresh database, one at a time, because the ports are fixed at 8830/8831.

Rules around it:
- Manifest, whenever `lonora.md`, a frame or a tool description changes: regenerate it with `PYTHONPATH=$(ls -d packages/*/src | tr '\n' ':') .venv/bin/python scripts/export_agent_tool_reference.py` before the gate checks it. Mind the `lonora.md` chapter budgets.
- A flaky test is fixed at its root cause. Never skip it, retry it or raise its timeout.

## 4. Decisions already taken (do not reopen)

- **W-AUTH Q1-Q10** (`docs/handoff/wauth-plan.md` §1): every recommendation was adopted. Among them:
  - no forced write of Ask;
  - keep device enrolment for calls;
  - `agents_on_their_own` = Full and not paused;
  - move the 14.3.2 survivors;
  - supervisor holds are released as stale;
  - the agent's Mandate card is read per agent;
  - one error code, `broker_state_changed`;
  - roles are flattened in the data step.
- **Slice D:** an agent in Full whose ladder level was 'No trading' is switched to Ask, and gets its Mandate card once. It never silently gains the right to trade on its own.
- **v38 Q1-Q13:**
  - keep the app's method and tasks pages;
  - «ما يعمل الآن» already exists;
  - agents that cannot trade (no connected broker account) show no mode;
  - keep the usage budget;
  - the agent pause stays;
  - Q6/Q7 are prototype only;
  - Q8: no change;
  - Q9-Q13 are not added.
- **v38 D1-D12:**
  - only the five fixed cards keep their frame when decided; every other kind keeps its one-line fold until it is deleted;
  - mobile chat order lines go, for parity;
  - AuthFlow and Welcome texts that are only true after W-AUTH wait for S1a;
  - MCP tool titles are derived or backfilled, never shown as raw names;
  - the Execution Receipt uses the `.oa-dl` rows;
  - the Secret card shows field labels, never env-style names;
  - the English tab says "Attention";
  - a broker's own sentence is labelled as the broker's;
  - the Settle hint keeps its sentence that new risk stays held.
- **Slot heights (LD1-LD3):**
  - LD1: a slot counts at its record's state when the card is compiled, against RESTING_LIMIT 560. The record's tallest later state counts against HARD_LIMIT 720 for the whole card, or the card falls back. Neither limit changes.
  - LD2: modify_order is counted that way.
  - LD3: the Secret card is counted with its actual labels, and the "replaces" line counts against HARD_LIMIT.
  - "Approved, awaiting the broker" uses the wait tone, never ok.
- **Gate Fernet key:** the gate uses the 44-character fixture named in `docs/acceptance-scenario.md`; `scripts/gate.sh` sets it, and `ci.yml` carries no key of its own.

## 5. Useful facts

- The shared Python venv's editable install must point at the main checkout. If a tool re-runs `pip install -e`, check `.venv/lib/python3.12/site-packages/__editable___lonora_0_2_0_finder.py`.
- The migration chain is one line. A new migration's `down_revision` is the head at merge time (0127 on main, 0128 on `wauth/r2`). Re-chain on merge.
- `tests/check_*_migration.py` seed an older revision, then upgrade. Pin the ones that seed rows a later migration removes.
- Playwright database names come from your label, so do not put a hyphen in the label.

## 6. Final status when the Claude session stopped (2026-11-20, about 13:10 UTC)

The owner stopped the Claude session so that you can take over. Every running job was stopped, and every finished commit is pushed.

### `ui/v38-port` is at **91a16e83**

Round 2 has done these:
- main 3e8bcfb1 is merged in (a16da753);
- a signed number in a list preview shows whole or not at all (2856eda5);
- main's Welcome footer is back, and the MCP server line reads in order with Arabic plurals (0de3f4ff);
- MCP titles are no longer re-read when a server titles none of its tools (30905429);
- the mobile hourglass and receipt kicker (9c307edc);
- jump-to-latest no longer covers a card (88b18c96);
- the mic tip shows over no message or card (91a16e83).

NOT finished:
- **LD1-LD3** (slot heights counted by the record's state at compile time) are half done. They are uncommitted in 11 files, saved on **`wip/ui-v38-port` (aee49401)**: `genui_compile.py`, `genui_slots.py`, `visual_response.py`, `docs/genui.md`, `plain-line.ts`, and the GenUI tests and specs. Read that diff, finish it and test it.
- From the re-review partial list (`docs/handoff/v38-open-findings.json`), several items may still be open:
  - the mobile heads-up prefix;
  - the Latin bubble's `.meta` float;
  - the emoji back icon in English;
  - «عرض الأحدث» after a Settle renewal;
  - a rendered test of the failed Secret card;
  - `keep_tool_titles`;
  - the English list separator;
  - the settings.spec strict-mode pin;
  - one Arabic word for «unverified broker account».

  Check each one against the code.
- Then run the FULL gate and new screenshots.

### `fix/flakes-20` is at **2eb31916**

Round 2 has done these:
- every spec's cleanup now runs in a fixture teardown, so it can no longer replace the body's error (8992f4dd);
- the list's chats page reads agents and groups live (6d329605);
- the memory privacy planner test is deterministic (02df8303);
- the genui spec's stale tap (2eb31916).

NOT done: the verification. Run two full web runs, one of them under load, and one full mobile run. Fix what still fails, by root cause.

### `wauth/r2` is at 923cf302

Unchanged since section 2. Start from item (a) there.

### Next
Batch 21 = `ui/v38-port` + `fix/flakes-20`. Merge `fix/flakes-20` into the batch branch, re-run the full gate, open a PR, merge it, and deploy.
