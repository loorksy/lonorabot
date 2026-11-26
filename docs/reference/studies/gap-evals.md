# Gap analysis: testing and evaluating agents (Lonora vs OpenMausBot and rakazo)

Scope: how agent behavior is tested and evaluated. Lonora is read at `/home/user/wt-agent/fxmain` (main `d8193b98`), read only. The reference projects are known only from `reports/openmausbot-evals.md` and `reports/rakazo-evals.md`, plus a spot check that the cited files exist in the clones (nothing was run there). All Lonora paths below are relative to the repository root.

Binding constraints applied throughout:
- VISION §6 (the safety core) is never weakened.
- No Stop control (Amendment 1).
- MetaTrader 5 through MetaApi only (Amendment 2).
- Lonora Cloud is one dedicated installation per customer. The customer is the owner, and the model key is the customer's (Amendment 3, D6, D41).
- §16 rules that "which choice it makes is not asserted", and §17 that "there is no backtesting or simulation gate on strategies".

## Ranked recommendations

| # | Recommendation | Verdict | Pri | Source | Effort | Owner decision | Main Lonora files | VISION clauses |
|---|---|---|---|---|---|---|---|---|
| 1 | One gate script for the local gate, mirrored by `ci.yml`. It covers all 11 core tests of §14.1.2, the full pytest run and `acceptance.py --offline` | adopt | P1 | both | M | no | `.github/workflows/ci.yml`, `tests/run_foundation_checks.py`, new `scripts/gate.sh`, `docs/handoff/CURSOR_HANDOFF.md` | 14.1.2, 6.1–6.9, 14.1.1 |
| 2 | Release only a gated commit: the release manifest carries the gate result of that exact commit, and CI runs again (paid minutes or a self-hosted runner) | adapt | P1 | openmausbot | M | **yes** | `scripts/release_manifest.py`, `.github/workflows/publish-server-image.yml`, `.github/workflows/ci.yml` | 14.1.2, 6, Amendment 3.6 |
| 3 | Re-baseline the live `agent_eval` layer for Full/Ask: seed modes the way `acceptance.py` does, stop seeding through the grant route, and re-run | adapt | P1 | rakazo | M | no | `scripts/agent_eval/bank.py`, `tests/fixtures/agent_eval/BASELINE.json`, `recordings/`, `docs/agent-eval.md` | 4.1, 4.2, 14.1.3, 14.2, 5.3, 16 |
| 4 | Financial invariants as hard checks on every trial: no duplicate send, no resend of an uncertain operation, no new risk in Ask without an exact approval, no send on another agent's ticket | adopt | P1 | rakazo | S | no | `scripts/agent_eval/score.py`, `runner.py`, `broker.py`, `acceptance.py` | 6.1–6.4, 6.6, 6.7, 3.3.4, Amendment 2 |
| 5 | Live runs with `--trials N` reported as k/N, a spend guard on the developer's key, and a `--compare` that refuses mismatched settings and exits non-zero on a regression | adapt | P2 | both | M | no | `scripts/agent_eval/run.py`, `score.py`, `acceptance.py` | 16, 12.1, D6/D41 |
| 6 | `ScriptedModelAdapter` gets per-reply `expect(...)` and `assert_complete()` | adopt | P2 | rakazo | S | no | `packages/adapters/src/lonora_adapters/models/fake.py` and its callers | 14.1.2 |
| 7 | A bank of proactive behavior cases (live, with offline twins): silence on unchanged data, one alert on a real change, an honest message when a feed fails, a promised follow-up, an injected instruction in news | adapt | P2 | rakazo | M | no | `scripts/agent_eval/{bank,score,acceptance}.py`, `tests/fixtures/agent_eval/scenarios.json`, `tests/test_agent_eval.py` | P6, 11.1, 11.4, 11.5, 11.6, 11.8, 6.10 |
| 8 | A bank of agent-to-agent cases: harness-written peer messages (right, wrong, unevidenced, carrying an instruction) through the real peer path; Lonora as lead | adapt | P2 | both | M | no | `scripts/agent_eval/acceptance.py` (4a runner), `bank.py`, `score.py` | 3.1, 3.2, 6.10, 11.8, 16 (4a, 7) |
| 9 | A golden decision table for the execution door (mode × risk direction × pause × ticket owner × uncertain op × approval) → outcome | adopt | P2 | openmausbot | M | no | new `tests/test_door_golden.py`, reads `packages/trading/src/lonora_trading/{agent_permission,execution,admission}.py` | 6.1, 6.3, 6.6, 6.7, 6.9, 4.1, 4.7, 3.3.4 |
| 10 | An optional meaning judge for the wording checks only. It runs after the deterministic checks, uses Lonora's own router, a sha-pinned rubric and Arabic calibration anchors, and aborts on disagreement | adapt | P2 | both | M | no | new `scripts/agent_eval/judge.py`, `score.py`, `tests/fixtures/agent_eval/judge/` | 5.3, 16, P4, 12.1 |
| 11 | Redaction and leak scan for any fixture taken from a real conversation. In Lonora Cloud no fixture comes from a customer's installation except by the customer's own export | adapt | P2 | openmausbot | S | **yes** (customer export) | `scripts/agent_eval/runner.py` (`scrub`), new `redact.py`, `tests/fixtures/agent_eval/` | Amendment 3.3, 3.7, 7.2 |
| 12 | Live eval scripts refuse to run on a hosted (Cloud) installation, so nothing ever spends a customer's key or writes rows on the customer's behalf | adapt | P2 | both | S | no | `scripts/verify_agent_journeys.py`, `scripts/agent_eval/{run,acceptance}.py` | Amendment 3.3, 3.4, D6, D41 |
| 13 | Failure categories on live records: `agent`, `product`, `provider`, `harness`, `incomplete` | adopt | P3 | rakazo | S | no | `scripts/agent_eval/{score,run,acceptance}.py` | 16 |
| 14 | A prompt fingerprint on every Run: policy digest, tool-schema hash and model, written to `model_metadata` and to eval records | adapt | P3 | rakazo | S | no | `packages/agent-runtime/src/lonora_agent/skills/system_policy.py`, `lonora_agent/executor.py`, `scripts/agent_eval/runner.py` | 5.8.6, 17 |
| 15 | A loopback HTTP model emulator for a few end-to-end trading journeys (split tool arguments, disconnect mid-stream after a trade call) | adapt | P3 | rakazo | M | no | new `tests/model_emulator.py`, `packages/providers`, `packages/adapters/src/lonora_adapters/models/` | 6.3, 6.4, 17 |
| 16 | A per-model qualification report for the providers in §12, for information only and never a limit on assignment | adapt | P3 | neither (both lack it) | M | no (yes if shown to customers) | `scripts/agent_eval/run.py`, `docs/agent-eval.md` | 12.1, 12.3, P1, D41 |
| 17 | A simulated owner (a second model, Arabic, private brief) for the live run of §16 | adapt | P3 | rakazo | L | no | `scripts/agent_eval/acceptance.py` | 16, 17, 5.3.3 |
| 18 | Weekly capped exploratory QA of the web and Android clients on a seeded stack with the fake terminal | adapt | P3 | rakazo | M | **yes** | new `scripts/exploratory_qa/`, `playwright.config.mjs` | 17 (RTL), P5, 10, D36 |
| A1 | Owner's own Arabic case bank, with the forbidden vocabulary derived from code | already-better | – | both | – | – | `scripts/agent_eval/score.py`, `tests/fixtures/agent_eval/scenarios.json` | 5.3, 17 |
| A2 | Expected failures held strictly in both directions (`BASELINE.json`, acceptance `defects`) | already-better | – | both | – | – | `tests/test_agent_eval.py`, `tests/test_acceptance_scenario.py` | 14.1.2 |
| A3 | Structural probes: the ideal calls with no model ("would the product deliver?") | already-better | – | both | – | – | `scripts/agent_eval/run.py --probe` | 16 |
| A4 | A fake MetaApi terminal under the real adapter, with an induced lost reply | already-better | – | rakazo | – | – | `scripts/agent_eval/broker.py`, `acceptance.py` (`AcceptanceTerminal.lose_reply`) | 6.2–6.4, 6.8 |
| A5 | The acceptance scenario held to the mandate clause by clause (needs/pending/void; judgment checked, not chosen) | already-better | – | both | – | – | `scripts/agent_eval/acceptance.py`, `tests/fixtures/agent_eval/acceptance.json` | 16, Amendment 1 |
| A6 | A runtime check that no credential reaches any model (not only a fixture scan) | already-better | – | openmausbot | – | – | `acceptance.py` (`Witness`), `tests/check_simple_lonora.py` | 7.2, 6.10 |
| A7 | Flakes fixed at their root cause, never retried | already-better | – | openmausbot | – | – | `docs/handoff/CURSOR_HANDOFF.md` §3 | 14.1.2 |
| A8 | Prompt as code: sha-pinned manual and hard size ceilings | already-better | – | both | – | – | `lonora_agent/skills/system_policy.py`, `tests/test_system_policy.py`, `tests/test_tool_discovery.py` | 5.8.6 |
| S1 | "Time to stop after an owner Stop" metric | skip | – | rakazo | – | – | – | Amendment 1 |
| S2 | "Orders over the owner's risk limit" metric | skip | – | rakazo | – | – | – | P1 |
| S3 | A lint rule against keyword graders | skip | – | rakazo | – | – | – | 17 |
| S4 | A fingerprinted run store that reuses and regrades results | skip | – | rakazo | – | – | – | – |
| S5 | Golden-thread trace replay | skip | – | openmausbot | – | – | – | – |
| S6 | Trading canaries on installations, or any eval that grades trade quality | skip | – | both | – | – | – | Amendment 3.3, 5.1, 16, 17 |
| S7 | A real-model gate on every pull request | skip | – | both | – | – | – | 12.1 |

---

## 1. What Lonora does today

### 1.1 The layers

| Layer | Real parts | Stand-ins | Entry point |
|---|---|---|---|
| Unit and plumbing tests (about 540 files) | one module, or the real loop on PostgreSQL | scripted model, simulation broker | `.venv/bin/python -m pytest -q tests` |
| Provider wire tests | the real provider adapters and router | `httpx.MockTransport` | `tests/test_provider_resilience.py` (stream errors, cut-off tool input, `length` finish, 429/503, auth, overflow), `tests/test_model_context.py`, `tests/test_model_providers.py` |
| Scripted journeys on the real loop | API, DB, router, loop, tools, door | `ScriptedModelAdapter` (`packages/adapters/src/lonora_adapters/models/fake.py`), simulation broker | `tests/check_llm_harness.py` (its docstring says it "does not establish the reasoning quality of a live LLM"), `tests/check_simple_lonora.py` (Arabic journeys, a worker restart mid-Run with no second operation, a credential scan), `tests/check_gold_journey.py`, inline scripts in `ci.yml` |
| Behavior eval, deterministic | real tool handlers, real `MetaApiBroker` code | `FakeTerminal` (`scripts/agent_eval/broker.py`) | `tests/test_agent_eval.py`: scorer rules on the owner's real bad replies, the fake broker, bank integrity, the recorded baseline replayed, structural probes |
| Behavior eval, live | prompt assembly, router, provider adapter, `execute_run` (120 s lease, 24 rounds) | fake terminal; key added by the proxy | `scripts/agent_eval/run.py --live` (default `openai/gpt-5.4-mini`, one sample) |
| Acceptance scenario §16 | real loop, gateway steps (`check_watches`, `dispatch_routines`, `brief_tick`, `reconcile_ambiguous`) | per-agent `ScriptedModel`, `AcceptanceTerminal` | `scripts/agent_eval/acceptance.py --offline`, `--live`, `--broker demo --steps 1` |
| Real-model non-financial journeys | the deployed Gateway/API with the owner's credential | none | `scripts/verify_agent_journeys.py --allow-live-model` |
| Prompt as code | `lonora.md` and the bootstrap files | none | `manifest.json` sha256 checked at load (`lonora_agent/skills/system_policy.py`: `MAX_CORE_CHARS = 16000`, `MAX_DOMAIN_CHARS = 14000`, `voice_surface` ≤ 800 bytes), `tests/test_system_policy.py` (`test_cache_boundary_contains_no_owner_memory_or_market_state`), `tests/test_tool_discovery.py` (`test_eager_schema_budget_holds_for_every_run_shape`), `scripts/export_agent_tool_reference.py --check` |
| Proactivity plumbing | real loop and gateway steps | scripted model | `tests/test_background_silence.py` (31 tests, VISION 11.5), `tests/test_proactive_wakes.py`, `tests/test_morning_brief.py`, `tests/check_close_wake.py` |
| Collaboration plumbing | real child runtimes and peer delivery | scripted model | `tests/check_runtime_collaboration.py`, `tests/check_team.py`, `tests/check_streaming.py` (idempotent peer communication), `tests/test_context_engine.py::test_a_peer_message_reaches_the_model_inside_the_data_frame` |
| Web and mobile end to end | the real web client and the Expo client against the Python API | none | `pnpm test:web`, `pnpm test:mobile` |

### 1.2 What is strong

- **The owner's real cases.** `tests/fixtures/agent_eval/conversation.json` holds 81 messages of the owner's production conversation. `scenarios.json` turns them into 42 scenarios in his own words (Levantine and standard Arabic), each with the state that came before it.
- **A scorer with no judge.** `scripts/agent_eval/score.py` takes its lists of tool names, error codes (every `LonoraError(...)` literal), states and resource names from the code. It checks the VISION 5.3 conditions as regex oracles that were reviewed adversarially: `disclaimer`, `reassurance`, `refused_view`, `unshown_profit`, `unbacked_claim`, `mismatched_claim`, `promise_without_trigger`, `language`. The known gaps are written down in the Limits section of `docs/agent-eval.md`.
- **Expected failures held in both directions.** `BASELINE.json` names each scenario's expected failures, and the suite fails whether a scenario gets better or worse without the file changing. The acceptance step states are richer than either reference's: `pending`, `not written`, `known defect`, `not exercised`, `void` (step 6, by Amendment 1).
- **Strict scripted turns in the acceptance run.** `ScriptedModel.start` raises `no scripted turn left for X` on an unplanned wake, and `run_step` adds the check "every scripted turn was used". `Witness` records every message any model was shown, and the credential check runs against all of it.
- **Exact plumbing, judged choices.** Plumbing assertions are exact: one close in the journal, one send, no resend after the drop. A model choice is checked by `judged()`: the agent acted within its authority, did not ask, and explained in one line. This is §16 as written.

### 1.3 Honest gaps found in Lonora itself

1. **The gate is manual.**
   - `docs/handoff/CURSOR_HANDOFF.md` §2 says: "CI does NOT run on this repository … The local gate in section 3 is the only gate." It also says the Fernet key in `ci.yml` is not valid.
   - Even if CI ran, `ci.yml` never runs `pytest tests` as a whole. It runs only `tests/test_mobile_updates.py`, `tests/test_model_access_guard.py`, `tests/voice` and the `run_foundation_checks.py` list.
   - So 6 of the 11 core tests that §14.1.2 says MUST pass after every step are absent from CI: `test_broker_effect_verification.py`, `test_execution_records.py`, `test_preflight_identity.py`, `test_metaapi_reconciliation_history.py`, `test_tool_execution_core.py` and `test_financial_admission.py`. So are `test_agent_eval.py` and `test_acceptance_scenario.py`.
   - `scripts/release_manifest.py` records the commit and the migration head, but no gate result.
2. **The live evidence is stale.**
   - The live column is one sample from 2026-11-11 (`main` `9f5b1da`), taken before the move to Full/Ask modes.
   - `docs/agent-eval.md` starts with "Superseded by VISION.md".
   - `scripts/agent_eval/bank.py::seed` still signs a grant: `POST /agents/{id}/account-authorities` and `device.sign_grant`. `prepare` revokes it through `/account-authorities/{id}/revoke`. That is a feature §14.2 removes.
   - `acceptance.py` already seeds the new way: `set_trading_mode(..., "full", by="owner_tap")`.
3. **`ScriptedModelAdapter` is lax.** It checks no request and does not fail when scripted replies are left over. The acceptance `ScriptedModel` does both of these at the turn level; the shared fake does neither.
4. **No statistics on live runs.** There are no trials, spend guard, compare tool, judge or prompt fingerprint per Run.
5. **No live bank for proactivity or agent-to-agent behavior.** The plumbing is tested deeply. Whether a model stays silent, speaks up, or ignores an instruction inside a peer message or news item is not measured. Today's bank is driven only by owner messages.
6. **Fixtures carry real identifiers.**
   - `conversation.json` contains a real production position ticket (`2217873130`).
   - `runner.py::scrub` replaces run ids and refuses `sk-` keys, but it scans for nothing else.
   - This is acceptable for the self-hosting owner who consented. It must never be repeated with a Lonora Cloud customer's data (Amendment 3.3).
7. **The live scripts run on the deployed server.** `scripts/verify_agent_journeys.py` runs "inside the deployed Gateway/API environment" with "one existing owner's configured provider credential". On a Cloud installation that would spend the customer's key and write rows into the customer's database.

## 2. What OpenMausBot and rakazo do better or differently

| Topic | OpenMausBot | rakazo | Lonora |
|---|---|---|---|
| Central rule | "evaluate the harness, never the models" | "a scripted response proves a tool call executes; only a real model shows it chooses a useful action" | both, as two layers: structural (no model) and live |
| Model stand-in | fake CLIs that speak the real wire protocol; a scripted room agent calls the real MCP tools; an `unplanned` turn fails | `startModelEmulator`: loopback HTTP/SSE, `expect(request)` per step, `assertComplete()`, failure shapes (disconnect, hold, split args) | in-process `ScriptedModelAdapter` (lax) and acceptance `ScriptedModel` (strict per turn); wire shapes tested only at adapter level |
| Grading | pure scorers over a frozen snapshot; trace baselines | deterministic criteria first, then a calibrated LLM judge; a ratchet bans keyword grading | deterministic effects plus regex wording oracles; no judge |
| Real-model statistics | one sample, a 0.25 drift allowance | trials (1–5), `SpendBudget` ($5 default), a compare that refuses mismatched settings (but exits 0) | one sample, no cap, no compare |
| Proactivity | none graded (`routine-deferral` only) | `silence` and `initiative` suites with offline twins | plumbing only |
| Agent-to-agent | `dispatch-supersede` (turn order, handoff tree) | `deliberation` and `group-routing` with harness-written peer text | plumbing plus acceptance 4a (news agent tells the others) |
| Policy as tables | `admission-golden.test.ts` freezes every admission decision | – | case-by-case door tests, partly parametrized (`tests/test_trading_mode.py`) |
| Fixture privacy | redactor plus a leak scan that reports category and path only | synthetic fixtures; the recorder keeps a closed vocabulary | real owner text and a ticket; a key-shape check only |
| Prompt changes | 2% drift budget per section, byte-pinned tool catalog, identical-prefix test | automatic `promptVersion` fingerprint stored on every Run, plus an outcome query by version | sha manifest regenerated by hand, hard ceilings, cache-boundary test; nothing stored per Run |
| CI | one required gate; release only a commit whose own CI is green | `checks` is both the required check and the deploy gate | workflow not running; a manual local gate |
| Flakes | an owner-listed retry list, CI only | – | root cause only; never retried |

## 3. Recommendations in detail

Each item gives the verdict, why, the files it touches, the VISION clauses involved, the effort, and whether the owner must decide.

**1. One gate script, mirrored by CI** (adopt, P1, M, no owner decision)
- Write `scripts/gate.sh` to do exactly what `CURSOR_HANDOFF.md` §3 lists: migrate a fresh database, run the full pytest, run `run_foundation_checks.py --isolated-databases`, run `acceptance.py --offline`, run `build.sh`, check i18n and the manifest, then the full web and mobile Playwright suites.
- Have `ci.yml` call that one script instead of a hand-picked list. Fix its Fernet fixture.
- Why: §14.1.2 says the 11 core tests "MUST pass after every step". Today half of them, and both eval tests, exist only in a document people are trusted to follow. Both references have a single required gate.
- Nothing in §6 changes. This item only makes §6's tests run every time.

**2. Release only a gated commit** (adapt, P1, M, owner decision)
- The gate script writes `{commit, steps, result}`. `release_manifest.py` puts it into `/app/release.json`, and the image build refuses a commit without a passing result. `lonora update` can then show it.
- OpenMausBot's `release-ci.mjs` does this against CI. Lonora needs the owner to choose whether CI runs again (paid Actions minutes or a self-hosted runner), or whether a signed local result is enough.
- Lonora Cloud raises the stakes: one image reaches every customer's installation (Amendment 3.6 keeps hosting hooks additive, so this is a release step, not product behavior).

**3. Re-baseline the live `agent_eval` layer for Full/Ask** (adapt, P1, M)
- Seed the mode directly with `set_trading_mode(..., by="owner_tap")`, as `acceptance.py` does. Rakazo's rule applies: "setup never depends on the behavior under test".
- Replace `mandate: none` with `mode: ask`. Delete `sign_grant` and the `/account-authorities` calls from `bank.py` in the same change that removes grants (§14.1.3, §14.1.4).
- Re-run the live bank, then rewrite the tables in `docs/agent-eval.md` so its "Superseded" line can go.
- Why: the only real-model evidence about P1 (the agent acts as the owner's delegate without refusing) and §5.3 comes from code that the mandate has since replaced.

**4. Financial invariants on every trial** (adopt, P1, S)
- `score.py` already sees `tool_calls`, `state_after` and the calls that reached the fake terminal. Add fixed conditions that apply to every scenario and every trial:
  - each terminal send matches exactly one journal reservation (§6.2);
  - no second send for an operation whose outcome was unknown (§6.3);
  - no new risk sent in Ask without the exact approved request (§6.7);
  - no send on a ticket owned by another agent or the owner (§3.3.4);
  - nothing reported as filled without a broker deal (§6.4).
- These are hard: one breach fails the case, whatever the average says. OpenMausBot's own "avoid" list asks for hard invariants plus an aggregate for style.
- Rakazo's money metrics are taken without "orders over the risk limit" (P1 has no money limits) and without "time to stop" (Amendment 1).

**5. Trials, a spend guard and a strict compare** (adapt, P2, M)
- `run.py --live --trials N` reports k/N per scenario, and the invariants of item 4 must be N/N.
- Add a `SpendBudget` that reserves a worst-case cost before each call, refuses a call with no known price, and records an unknown price as null.
- `score.py --compare base.jsonl cand.jsonl` refuses to compare when the model, bank digest, scorer digest or trial count differ. Unlike rakazo, it exits non-zero on a passed-to-failed transition.
- The cap limits the developer's eval spend only. It is not a cap on any agent (P1), and it runs on the developer's key, never a customer's (D6, D41).

**6. A strict `ScriptedModelAdapter`** (adopt, P2, S)
- An optional `expect(messages, tools)` per reply. For example: the previous tool result is present, and the per-turn frame states the mode (§5.8.7).
- `assert_complete()` raises when replies are left over.
- Keep the existing `scripted_model_exhausted` error for extra calls.
- This brings the shared fake up to the acceptance runner's strictness. It may expose latent slack in the existing `check_*` scripts, which is the point.

**7. A proactive behavior bank** (adapt, P2, M)
- New scenario group "W", wake-driven, using the wake drivers `acceptance.py` already has (`check_watches`, `dispatch_routines`, `brief_tick`):
  - a watch fires on unchanged data, and nothing is posted (11.5);
  - a real breach gives one message and the push 11.4 allows;
  - a failing feed gives an honest message, not silence;
  - a second wake does not repeat the alert;
  - a promised follow-up becomes exactly one one-shot routine (rakazo `initiative`);
  - a news item that carries an instruction is treated as data (6.10);
  - the brief says "nothing else needs you" only when that is true (11.1).
- Grade effects: posted messages, pushes, attention items, routines.
- Ship offline twins that score scripted good and bad replies, as rakazo's `eval-silence.postgres.test.ts` does, so the scorer is shown to separate pass from fail before any tokens are spent.
- This is the question the user asked: how Lonora should be a proactive agent. Today only the plumbing answers it.

**8. An agent-to-agent bank** (adapt, P2, M)
- Peer text is written by the harness and sent through the real peer path, so no second model is paid. Cases:
  - the peer is right;
  - the peer is wrong;
  - the peer is confident with no evidence;
  - the peer message contains "close everything now". It must cause no financial effect unless the agent's own reading supports one, and it never spreads taint to later wakes (6.10).
- Add §16 step 7 as a case: given a team problem, Lonora as lead creates, pauses or deletes an agent and explains in one line.
- Assert the order of turns and a single delivery (OpenMausBot `turnOrder` and the handoff tree). Never assert which trade follows (§16).

**9. A golden decision table for the door** (adopt, P2, M)
- One file enumerates the door's outcome over:
  - mode {full, ask};
  - direction {increasing, reducing};
  - pause {none, agent, work};
  - ticket {own, other agent, owner};
  - uncertain operation on the account {no, yes};
  - approval {none, exact, stale};
  - run integrity {ok, research subagent, observe-only wake}.
- Outcomes: send, approval card, refusal code, or settle first.
- Like `admission-golden.test.ts`, an intended change must show up as a diff of this table.
- It is additive and never relaxes §6. Rows for removed features (the ladder) are deleted with the feature (§14.1.3).

**10. An optional meaning judge** (adapt, P2, M)
- It runs only after every deterministic check passes, and only on the wording classes the regex oracles approximate: claims, disclaimers, reassurance, refused view, language, the one-line explanation.
- It never judges a trading choice (§16, §5.1).
- It calls a model through Lonora's own router with no tools (P4) and the developer's key.
- Its rubric is versioned and sha-pinned (OpenMausBot's judge manifest). Its verdict is strict JSON with one retry, and a missing verdict counts as incomplete, never as a pass.
- Before any trial it is calibrated on anchors: the owner's real bad replies in `conversation.json` and the good replies in `test_agent_eval.py`, in Levantine and standard Arabic and in English. The run aborts if the judge disagrees with an anchor (rakazo).
- The regex oracles stay as the free offline floor.

**11. Redaction and leak scan for real-conversation fixtures** (adapt, P2, S, owner decision for Cloud)
- A scan reports a category and a path only, never the matched text. Categories: MT5 logins, tickets, MetaApi account ids, emails, URLs, absolute paths, key shapes. Run it over `tests/fixtures/agent_eval/**` in the gate, with an allowlist for the values the owner already consented to.
- Any new case drawn from a real conversation goes through a redactor that replaces values with positional placeholders and keeps the Arabic wording (§17).
- In Lonora Cloud the operator may not read or copy conversations (Amendment 3.3). So a customer case can only come from the customer's own export. Whether to build that export (it must not be a portal function, Amendment 3.7) is the owner's decision.

**12. No live eval on a hosted installation** (adapt, P2, S)
- `verify_agent_journeys.py`, `run.py --live` and `acceptance.py --live` refuse to start on a hosted installation. They are for the developer's own installation, or a self-hosted owner who runs them personally.
- The marker to check is `LONORA_HOSTED_PORTAL_URL` (Amendment 3.5). It is not in the code yet: cloud task P1-T6 in `docs/cloud/PHASES.md` adds it. Until then the scripts need whatever hosted marker provisioning sets.
- This enforces Amendment 3.3 and 3.4: the operator does not use the customer's model key or write into the customer's data. Both references keep real-model runs on the developer's own account.

**13. Failure categories** (adopt, P3, S)
- Each live record gets one category:
  - `agent`: the structural probe passed but the live run failed;
  - `product`: the structural probe failed;
  - `provider`: model timeout or outage;
  - `harness`: the fake lacked something, or the run was still queued after three pickups;
  - `incomplete`.
- Read the category before blaming a prompt change (rakazo).

**14. A prompt fingerprint per Run** (adapt, P3, S)
- `PolicyBundle.digest` already exists. Add a hash of the native tool schemas sent and the model id, and write all three to `RunRow.model_metadata` and to every eval record.
- Item 5's compare then refuses records whose fingerprints differ.
- Store operational fields only, never content. On Lonora Cloud only the customer reads them.

**15. A loopback model emulator for trading journeys** (adapt, P3, M)
- A few journeys run through the real router, the real adapter, the real loop and the door: a trade tool call whose arguments arrive in fragments; a disconnect after the trade call was emitted; a held stream.
- Assert that the operation is never sent twice and that an unknown outcome is settled from broker evidence (§6.3, §6.4).
- Lonora's unit-level wire tests already cover each failure shape alone. This item adds the combination with the money path.

**16. A per-model qualification report** (adapt, P3, M)
- Run the live bank for each model family of §12 and publish k/N plus the invariants in `docs/`.
- It is information for the developer and never a restriction: the owner assigns any model (12.3). Showing it to Cloud customers, for example in the help guides of D41, is an owner decision. Neither reference evaluates a model change at all.

**17. A simulated owner for §16 live** (adapt, P3, L)
- A second model plays the owner in Arabic from a private brief and moves by JSON (`say`, `tap`, `done`).
- Grade from the fake terminal and the product state, never from the agent's own claims (rakazo: "the bot's claims are not evidence"; §5.3.3).

**18. Weekly capped exploratory QA** (adapt, P3, M, owner decision)
- A model drives the web client and the Android client (D36: the app is the product) on a seeded stack with the fake terminal, in Arabic RTL, with budget, step and issue caps.
- A second job with no model access files the issues.
- It needs a runner and a spend decision.

## 4. Where Lonora is already better

- **A1. A real-owner bank with vocabulary from code.** Neither reference derives its "must not show" lists from the codebase (error-code literals, contract states, registry names). Rakazo uses synthetic fixtures. OpenMausBot's tool-choice cases are real requests, but they are graded by tool name only.
- **A2. Expected failures held strictly in both directions.** `BASELINE.json` and the acceptance `defects` entries fail the suite when a scenario gets better without the file being updated. Rakazo's compare exits 0, and OpenMausBot allows 0.25 of drift.
- **A3. Structural probes.** The ideal calls are sent with no model through the loop's own dispatch. This cleanly separates "the product cannot deliver" from "the model chose wrong". Rakazo's offline twins test the graders, not the product.
- **A4. The money-path fake.** `FakeMetaApiBroker` is the product adapter with only its SDK connection replaced, so a missing terminal can never fall through to MetaApi. `AcceptanceTerminal.lose_reply` is exactly an ambiguous submit, the case rakazo's `uncertainWrite` models generically.
- **A5. Clause-by-clause acceptance.** Every step quotes §16, names its feature and owner, and stays `pending` until its code exists. Step 6 is void by Amendment 1, and a test enforces that. Judgment is checked, not chosen.
- **A6. A runtime credential check.** No credential may appear in anything any model was shown (`Witness` inputs), nor in messages, events, cards or Runs (`check_simple_lonora.py`, property 4). OpenMausBot scans only fixtures.
- **A7. Flake policy.** "A flaky test is fixed at its root cause. Never skip it, retry it or raise its timeout." This is stricter than OpenMausBot's retry list.
- **A8. Prompt as code.** The sha manifest is checked at load, the policy chapters have hard ceilings, the cache boundary is tested to hold no owner memory or market state, and the eager schemas have a budget. This matches OpenMausBot's 2% budgets or does better.

## 5. Skipped, and why

- **S1. "Time to stop after an owner Stop".** Amendment 1: Lonora has no Stop control.
- **S2. "Orders over the owner's risk limit".** P1: there are no money limits to measure.
- **S3. Rakazo's ratchet against keyword graders.** It would forbid Lonora's deliberate, reviewed Arabic regex oracles, which are free and run offline. Item 10 adds the judge on top instead.
- **S4. A fingerprinted run store with reuse and regrade.** `score.py` already re-scores any stored recording offline (`--baseline`). At 42 scenarios the reuse machinery is not worth its complexity (CLAUDE.md §2), and rakazo itself documents the store's blind spot for code changes.
- **S5. Golden-thread trace replay.** In scripted runs the script fixes the tool order. In live runs the trace varies from sample to sample. Lonora's structural probes and strict baseline already cover the useful part.
- **S6. Trading canaries on installations, or evals that grade trade quality.** In Cloud the operator must not place orders or read trading data (Amendment 3.3), so post-update checks stay health-only (`/ready`, gateway steps). Grading trade choices or backtesting contradicts §5.1, §16 and §17. The only real-broker check stays acceptance step 1 with `--broker demo` on a demo account, which places no order.
- **S7. A real-model gate on every pull request.** It costs tokens on every change and is noisy at one sample. Both references keep live runs opt-in. With items 4 and 5, a scheduled run becomes possible once item 2's runner decision is made.

## 6. Rules that apply to every item above

- Live runs use the developer's key on the developer's installation (D6, D41, item 12), and never a Cloud customer's.
- Every fake broker is MetaApi/MT5-shaped. No fake or real venue other than MT5 is added (Amendment 2).
- No eval adds or tests a Stop control (Amendment 1). Assertions about §6.1–6.9 are only ever added, never weakened (§14.1.3).
- A model's trading choice is never asserted. Only authority, not asking, one-line explanation, honesty (§5.3.3) and the plumbing are asserted (§16).
- Evals change no product behavior. Item 14 writes metadata only, and item 12 adds only a refusal to the eval scripts.
