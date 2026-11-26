# OpenMausBot: how agent behavior is tested and evaluated

Scope: the third-party clone of `milind-soni/OpenMausBot`, read only. Everything below was read in the repo; where I did not open a file I say so. Paths are repo-relative.

## 0. The short version

OpenMausBot has no "model quality" gate in CI. Its central idea is stated in `evals/README.md`: "evaluate the harness, never the models." The model is replaced by a scripted fake, and the real server around it (admission, handoffs, routines, prompts, tool gating) is the thing under test.

Layers, cheapest first:

1. Unit and contract tests, colocated (`server/**/*.test.ts`), using an in-memory fake driver and scripted fake CLIs that speak the real wire protocols of Claude, Codex and ACP agents.
2. Real-server e2e tests: boot the actual server against a throwaway home with a fake engine (`scripts/control-omb.ts: launchVerificationServer`) and drive it over HTTP and the `omb` CLI.
3. Tier 1 behavior evals (`evals/`): JSON scenarios, scripted turns, pure-function assertions. Offline, hermetic, a CI gate.
4. Tier 2 golden-thread replay: a real thread is redacted into a synthetic scenario and a committed trace baseline is diffed. Offline, a CI gate.
5. Tier 3 and side evals with a real model (`evals/live`, `evals/tool-choice`, `evals/dream/run-dream.ts`): opt-in, never in CI, with an LLM judge for open-ended replies.
6. Release gates: CI must have passed on the exact release commit (`scripts/release-ci.mjs`), plus packaged-app smokes in `.github/workflows/release.yml`.

## 1. Fakes for model providers and CLIs

Rule from `CONTRIBUTING.md`: "extend those fakes rather than mocking `child_process`". Fakes are real executables that speak the real protocol, so the driver code under test is the production code.

### 1.1 In-memory driver
`server/testing/fake-driver.ts: makeFakeDriver(opts)` returns a `ProviderDriver` plus a handle (`created`, `decodedConfigs`, `disposed`, `probes`). Options inject failure shapes: `failCreate`, `failSnapshot`, `hangSnapshot`, `holdSnapshot`. The test emits canonical `RuntimeEvent`s itself. Used for registry and bus tests.

### 1.2 Scripted CLI fakes (subprocess)
- `server/testing/fake-claude-cli.ts` (1444 lines): fakes the `claude` stream-json surface. The header documents roughly 80 env knobs. Modes include `happy | exit-early | hang | malformed | dead-session | stale-session | error-result | usage-limit | not-logged-in | api-error | stream | slow-write`. Individual knobs script tool calls (`FAKE_CLAUDE_TOOL_CALLS`), replies in order (`FAKE_CLAUDE_REPLIES`), compaction (`FAKE_CLAUDE_COMPACT`, `FAKE_CLAUDE_AUTOCOMPACT_AT`), cost totals, hooks, resume behavior and context growth. `FAKE_CLAUDE_DUMP` writes `{argv, env, cwd, prompt, systemPrompt, mcpConfig}` so a test can assert exactly what the model was sent.
- `server/testing/fake-codex-app-server.ts`: fakes `codex app-server` JSON-RPC over NDJSON. `FAKE_CODEX_MODE` covers approvals, questions, crashes, 401/403 recovery and usage limits.
- `server/testing/fake-acp-cli.ts` (2011 lines): fakes an Agent Client Protocol CLI (used for Gemini, Cursor, OpenCode, Kimi and others). `FAKE_ACP_MODE` covers `hang`, `permission`, `question`, `interleave`, `stall-after-tool`, and `delegate-peer`/`chief-delegate`, which call `coordinate_bots` through the real injected MCP server.
- `server/testing/fake-pi-cli.ts`, `fake-antigravity-cli.ts`, `fake-agy-cli.ts` and many service fakes (`fake-openai-live.ts` for OpenAI's live-session HTTP+WebSocket, `fake-github.ts`, `fake-smtp.ts`, `broker-fake.ts`, `fake-oauth-server.ts`). I read only the headers of these.
- `server/testing/stream-script.ts`: `FAKE_STREAM_SCRIPT` maps a marker string found in the prompt to steps `{say} | {think} | {tool} | {fail}`, streamed in chunks (`FAKE_STREAM_CADENCE="chars:ms"`). `server/testing/live-reply-cases.ts` holds 16 cases (short, long, markdown, code, math, thinking, stop, steer, reconnect, switch, error). Each message carries a unique token such as `T8M2`, so a check can prove no message is duplicated, glued or lost.

### 1.3 The fakes are themselves guarded
`server/testing/fakes-self-contained.test.ts` fails if a subprocess fake imports anything outside `server/testing/` (some are copied to a temp `bin` as `codex`). `server/testing/fake-claude-dump.test.ts` proves the dump file is never read half-written.

### 1.4 The scripted "room agent": a fake model that uses the real tools
`server/testing/room-handoff-agent.ts: runRoomHandoffAgent` is the most reusable idea for Lonora. When `FAKE_CLAUDE_ROOM_PLAN` is set, the fake CLI does not just print text. It spawns the real injected agents MCP proxy and issues real `tools/call` requests:

Control flow of one scripted turn:
1. Read the plan file `room-plan.json`, keyed by bot id. Pick the plan by `byPrompt`, by `turns[turnIndex]`, or by a `script` entry whose `match` strings all appear in the turn's own text (`ownTurnText` strips replayed history and recalled memory so an old quote cannot match).
2. `initialize`, `tools/list`, and `list_room_targets` against the real MCP proxy.
3. For each `steps[]` entry: optional `delayMs`, then `tools/call` (default tool `coordinate_bots`). If the response error state differs from `expectError`, throw `Unexpected tool outcome`. A `capture` regex can save a value from one result into `{{name}}` in later steps.
4. Optional extras: `approve` (asks Claude's permission-prompt tool), `screenCalls`, `writeFiles`, `progress`, then hold on `gateFile` until a test creates it (deterministic busy windows, no sleeps).
5. Return `reply`, or throw for `fail`/`failWith`.
6. Always append one evidence row to `<plan>.evidence.jsonl`: `{botId, turnIndex, threadId, model, permissionMode, system, prompt, evidence:[{step,response}], planKey, approval, screen}`.

Strictness: with a `script`, a turn that matches no entry writes an `unplanned: true` row and throws `Unplanned fixture turn`. `server/runtime-coordination.e2e.test.ts` ends every scenario with `expect(turns().filter(r => r.unplanned)...).toEqual([])`. So a harness change that causes an unexpected extra model turn fails the test.

## 2. Unit and integration patterns for the agent loop

- No sleeps (`CONTRIBUTING.md`): wait on the proving event. `server/testing/events.ts: recordEvents(adapter).until(pred, timeout)` resolves on the first matching `RuntimeEvent`, including already-seen ones. On timeout it rejects with the list of event types seen. `evals/runners/api.ts: waitUntil(what, read, accept, timeoutMs)` polls state with a per-read deadline and a last-value error message.
- Never touch real data: `server/testing/setup.ts` gives every test file a temp `HOME`, deletes `OMB_DATA_DIR`, `CODEX_HOME`, `HERMES_HOME`, disables model-manifest fetch and announcements, pins `navigator.language`, and shrinks provider retry backoff (`FAKE_OPENAI_COMPAT_RETRY_SCALE=0.001`).
- Driver contract tests: `server/drivers/claude.test.ts` spawns the fake CLI and asserts the canonical event stream, argv and env hygiene, interrupts and the permission broker. Fake failure modes are toggled by env var.
- Policy as golden tables: `server/admission-golden.test.ts` freezes every admission decision (`admit("direct-busy", {...}) -> {action: "steer"|"queue"|...}`). Its header: "pair an intentional change with an update here so the diff says so."
- Restart and recovery e2e: `server/runtime-coordination.e2e.test.ts: scenario()` boots a scripted server, creates a Chief ("Clive") and a teammate, writes the plan, sends messages, and reads `runtime.db` (`assignments`, `assignment_events`) directly. It can `restart(signal)` the server mid-run and prove the Chief is resumed once. On failure it prints what the fakes were told and what the chats hold.
- Flaky-test control: `vite.config.ts` plugs in `scripts/testing/ci-retry-runner.ts`. Only tests listed in `scripts/testing/ci-retry-list.json` (file, full name, owner, evidence, date) get two retries, in CI only. `ci-retry-summary.mjs` lists each retried test in the job summary with an annotation. Fail-open if the list is unreadable. `vite.config.ts` also uses a `DurationSequencer` to shard by recorded seconds, and `hostTimeout` doubles timeouts on slow hosts.

## 3. Tier 1: scripted behavior evals (`evals/`)

Idea: a scenario is pure data (no code), so a fixture cannot reach around the harness.

### 3.1 Scenario schema (`evals/types.ts`)
`scenarioSchema` = `{id, title, behavior, issue?, world: "coordination"|"localVm", gates[], librarySkills[], bots[], steps[], assertions[], golden?}`.
- A bot has `turns: [{steps:[{tool, arguments, expectError}], reply, gate, delayMs, fail}]`; `"@key"` in arguments is resolved to the live bot id (`evals/providers/mock/scripted-plan.ts: resolveRefs`).
- Step kinds: `send`, `waitForTurns`, `waitForNodeStatus`, `waitForBusy`, `waitForActivity`, `createRoutine`, `runRoutine`, `snapshotRoutineRun`, `waitForRoutineRun`, `writeGate`, `installSkill`, `setConfig`, `setSkillAssignment`, `setVmState`, `consumeDump`, `captureComputer`, `pollComputerGate`.
- Assertion kinds: `sendNotQueued`, `toolCalls` (ordered with arguments), `toolNames` (ordered, argument-agnostic), `turnOrder`, `instructionsInclude`, `systemPromptIncludes`, `systemPromptOmits`, `promptIncludes`, `handoffTree`, `transcriptIncludes`, `gateAnswer`, `routineRunSnapshot`, `activitySeen`, `noActivityPrefix`, `activityCount`.

### 3.2 Run control flow
`pnpm eval` runs `evals/runners/run-evals.ts: main`.
1. `loadScenarios()` reads `evals/scenarios/*.json` and validates each with `scenarioSchema.parse`.
2. For each selected scenario, `run-scenario.ts: runScenario` picks `CoordinationWorld` or `LocalVmWorld` and calls `world.boot(scenario)`.
3. `CoordinationWorld.boot` launches `launchVerificationServer(..., {scripted: true})`, creates every bot with the `omb new-bot` command (teams materialize when a member is created with `--section`), then PATCHes `chiefOfStaff`, `managedSections`, `acknowledgePeerScope`, writes `room-plan.json` via `buildScriptedPlan`, and installs library skills as approved.
4. Each step runs through `world.runStep`. A failed step is recorded and rethrown, but the world is still closed in `finally`.
5. `world.snapshot(ctx)` freezes evidence: per-turn `system`, `prompt`, `toolCalls` from `<plan>.evidence.jsonl`; handoff tree from `runtime.db`; thread messages; activities; observations.
6. `scorers/assertions.ts: evaluateAssertions` scores each assertion as a pure function of that snapshot. A scorer that throws becomes a failing result, never an exception ("scorers never touch a server").
7. `reports/write-report.ts: writeReport` emits `evals/reports/runs/<stamp>.json` and `.md` (gitignored; uploaded as a CI artifact on failure).
8. Exit 0 only if every scenario passed.

Same scenarios as a test gate: `evals/evals.test.ts` runs `it.each(scenarios)("$id pins its behavior", ...)` with `evals/vitest.config.ts` (serial files, root pinned to repo).

### 3.3 What the six scenarios pin
`evals/scenarios/`: `dispatch-supersede`, `routine-deferral`, `lazy-computer-claim`, `lazy-claim-screenless`, `lazy-claim-rejection`, `skill-assignment-visibility`. I fully read `dispatch-supersede.json` and `lazy-computer-claim.json`; the others I know only from the descriptions in `evals/README.md`.

`dispatch-supersede` is a good example of a multi-agent protocol test:
1. Chief turn 0 calls `coordinate_bots` with `bot_ids: ["@lead"]`. Lead's turn is held by gate `leadWork`.
2. Wait until the lead's handoff node is `running`, and the Chief is not busy.
3. Send the Chief a second message. Assert it is `sendNotQueued`, runs as its own turn, and its instructions include `Assignments you already sent are still outstanding`.
4. Open the gate; wait for lead `completed`, then Chief turn 3.
5. Assert `turnOrder: chief, chief, lead, chief`, a `handoffTree` of `completed`/`completed(hasParent)`/`completed`, and the final text in the Chief's thread.

`lazy-computer-claim` (issue #1361) uses the `localVm` world: it plays the bridge's computer-control poll and asserts a `gateAnswer` with `held: true` and `blockedReasonIncludes: "Another thread is using this computer"` while another bot holds the VM, then `held: false` after release, plus `activitySeen` for the wait chip ("Waiting for its turn on this computer", then "Computer free").

Fixtures cite the bug (`issue`) and a `behavior` sentence. Scenarios are written after bugs and pin "current semantics" ("a new message is not a cancellation").

### 3.4 Worlds
- `coordination`: the real server plus the scripted engine.
- `localVm` (`evals/runners/local-vm-world.ts`): the real server with the container boundary replaced by `server/testing/group-local-vm-hooks.mjs`. I read only the head of this file.
- `live` (tier 3): same base class, real engine, evidence derived from thread messages (section 5).

## 4. Tier 2: golden-thread replay

Goal: turn a real conversation into a reviewable, committable fixture, then catch behavior drift.

1. Export: a raw thread in the shape of `/api/threads/<id>/messages` plus handoff participants (`goldenExportSchema` in `evals/golden/redact/redact-thread.ts`). Sample: `evals/golden/samples/coordination-handoff.sample.json`.
2. Redact: `redactThread` maps participants to `@bot1...`, user and bot text to positional placeholders (`<user message 1>`), tool argument values to type-preserving placeholders (values naming a participant become bot refs so dispatch still replays), and drops timestamps, ids and attachments. Version pinned: `REDACTOR_VERSION = 1`, recorded in the scenario's `golden.redactor`.
3. Leak scan (`redact/leak-scan.ts`): regex categories `email`, `url`, `absolute-path`, `ipv4`, `secret-or-id`, `hex-blob`, over strings and the serialized JSON. Findings report category and path, never the matched text. Additionally every source string of 8+ chars must be proven absent. A leak aborts redaction.
4. Replay: `evals/golden/run-golden.ts: runGolden` runs each golden scenario through tier 1's `runScenario`, reduces the result with `trace/behavior-trace.ts: behaviorTrace` (tool sequence, sorted argument keys, `errored`, handoff tree, send admission, outcome; argument values deliberately omitted), and `trace/diff-trace.ts: diffTrace` against `evals/golden/baselines/<id>.trace.json`. Each difference becomes a line such as `turn 0 (bot1) call 1: tool X -> Y` or `argKeys [a, b] -> [a, c]`.
5. `--update-baseline` rewrites baselines on purpose. A missing baseline fails.
6. `evals/golden/golden.test.ts` also asserts committed fixtures are byte-identical to what the redactor produces from the sample, so the pipeline itself cannot drift silently.

Only one golden fixture exists today (`golden-handoff`).

## 5. Tier 3 and the real-model evals

All gated by `OMB_EVAL_LIVE=1`. With the gate closed, `pnpm eval --live` prints `live tier skipped...` and exits 0. CI asserts that line (`grep -q "live tier skipped"` in `.github/workflows/ci.yml` and `scripts/ci-linux-lanes.mjs: EVALS_LANE`), so "skipped" is the pass condition.

### 5.1 Live smoke (`evals/live/`)
1. `run-live.ts: runLiveMain` loads the engine instance from `OMB_EVAL_LIVE_INSTANCE` or `OMB_EVAL_LIVE_CONFIG` (`liveInstanceSchema`: `instanceId`, `driver`, `model`, `config`, `environmentFrom`). Credentials are copied from the launching shell by name (`environmentFrom`, `OMB_EVAL_LIVE_PASS_ENV`), never inlined.
2. `live-server.ts: spawnLiveServer` starts the real `server/index.ts` in a temp data dir with only that instance configured and an allowlisted environment.
3. `live-suite.ts: toScenario` turns a live scenario into a tier 1 scenario with empty scripted turns and widened wait timeouts.
4. Checks are argument-agnostic invariants: tier 1 assertion kinds plus `botReplied`. `scenarioScore` = share of checks that pass; `suiteScore` = mean.
5. `live-world.ts: evidence` rebuilds scripted-engine-shaped rows from real thread messages (activity messages become tool calls), so the same scorers apply.
6. Open-ended quality: `judged: {prompt}` sends the last reply plus the task to a separate "judge" bot on the same engine. `judge/judge.ts: loadJudgePrompt` refuses a prompt file whose sha256 differs from `judge/prompts/manifest.json` ("prompt files are versioned artifacts and must be bumped, not edited"). `parseJudgeVerdict` takes the first JSON object and validates `{score 0..1, pass, reasons<=5}` with zod; `maxJudgeRetries` retries unparseable verdicts.
7. Thresholds in committed `evals/live/config.json`: `minScore 0.75`, `maxDrift 0.25`, `turnTimeoutMs 240000`, `judgeTimeoutMs 120000`, `maxJudgeRetries 1`. `applyThresholds` fails if `score < minScore` or the drop from the gitignored `evals/live/baselines/live-suite.json` exceeds `maxDrift`. `--update-baseline` records a new baseline.

The `reply-habits-v1` rubric (`judge/prompts/reply-habits-v1.md`) scores 1.0 / 0.5 / 0.0 on: opens with the answer, names no machinery (tool or file names), no closing offer, at most one question, plain time zones, remember/forget confirmed in one line, failures stated with a way forward. Seven live scenarios exist (`live-reply-*`, `live-delegation-lane`, `live-open-ended-judge`).

Prompt-change procedure (from `evals/README.md`): run the `live-reply-*` scenarios on a worktree of the base commit with the scenario and judge files copied in and `--update-baseline`; then on the change without it; the drift line is the before/after. This is manual, on the developer's account.

### 5.2 Tool choice (`evals/tool-choice/`)
`cases.json` holds real requests that went wrong in real use, in the users' own words and languages, each with acceptable `tools`, optional `never` tools and `publishSays`. `run-tool-choice.ts` starts a live server, one bot, one thread per case, polls until the bot is not busy and has replied, reads the thread's activity rows for tool names and the day's `/api/usage` delta for cost. `score.ts: scoreCase` passes if the first non-lookup tool is acceptable (a lookup is `find_tool`/`ToolSearch`), no `never` tool was hit, and a published page's reply matches `publishSays`. Only the scorer has an offline test. `--context` runs no model and prints the bytes of tool schemas sent up front.

This eval is what justified a product decision: `docs/agents-tool-bridge.md` reports a 6-case run (right tool 6/6 both ways, cost $0.56 full vs $0.58 bridged) and keeps the bridge off by default ("Run the eval again before changing this").

### 5.3 Dream (nightly memory) (`evals/dream/`)
`cases.json` gives chats, the current notebook, expected learned lines (`anyOf` words) and forbidden words. `score.ts: scoreDream` grades an answer exactly as production would keep it: `parseDream`, then `checkDreamFacts`, then the person's forgotten passages. It matches through width, invisible characters and look-alike digits (`unmasked`: `0->o`, `1->i`, `$->s`...) so a disguised pasted instruction still counts as forbidden. Unexpected saved lines are reported, and fail only cases marked `nothingElse`. Offline, only scoring has tests; `run-dream.ts` calls a real model through the driver with the real `dreamPrompt` and reports time and cost per case.

### 5.4 Turn routing (`evals/turn-routing/`)
Not a model eval: `classifyTurn` is a deterministic classifier. `score.ts: routeCase` labels each miss `cautious` (full model for a simple turn, costs money) or `eager` (quick model for a hard turn, costs the answer). `score.test.ts` pins today's counts (`cases: 38, right: 16, cautious: 7, eager: 15`) and the exact miss lists, so a router change must update the test and show what it moved. The README calls these "a baseline for a router to beat, not an accuracy rate."

### 5.5 Skill bench (alpha) (`evals/runners/run-skill-bench.ts`, `evals/scorers/skill-bench.ts`)
Each prompt runs twice through the tier 1 machinery: with the fixture skill installed as a user skill and without. Same assertions on both arms. The report gives per-arm pass rate, duration and estimated tokens (chars/4, because the scripted provider makes no API calls) with sample standard deviation, a per-assertion delta, and two flags: `nonDiscriminating` (identical pass rate in both arms, so a control not an effect) and `highVariance` (replicates of one arm disagree). Honest limit: because the "model" is scripted, this measures the harness's skill plumbing (trigger terms, the skill block in the system prompt), not whether a skill makes a model better. `evals/skill-bench/triggers/bench-triage-handoff.json` holds should-trigger, should-not-trigger (train and held-out) and near-miss sets; `triggers.test.ts` checks their structure only. The README says no router runs them yet.

## 6. Prompt checks without a model

Prompt text is treated as code with byte-level tests:
- `server/turn-prompt-budget.test.ts`: each fixed prompt section (reply habits, credentials, triggers, computer prompts, the Chief prompt, Codex developer instructions) "may move at most 2% either way"; a bigger change moves its baseline by hand.
- `server/drivers/agents-catalog-wire.test.ts` + `server/drivers/agents-catalog-goldens/*.json`: the `tools/list` wire for every profile combination is pinned byte for byte, from source and from the esbuild bundle, and size-budgeted; update only with `UPDATE_AGENTS_CATALOG_GOLDENS=1` and a reviewed diff.
- `server/prompt-cache-prefix.e2e.test.ts`: two threads of one bot launch with an identical system prompt (so provider prompt caching works); per-thread data rides the first user message.
- `server/system-prompt.test.ts`: section builders and the stable/volatile split.
- `evals` assertions `instructionsInclude` / `systemPromptIncludes` / `systemPromptOmits` pin the text the model actually saw in a given turn of a scenario, read from the fake CLI's evidence rows.

Model changes: `scripts/check-model-manifest.mjs` (run in the `static` CI job with `--against <base>`) validates `server/model-manifest/model-manifest.json` against a strict schema (`parseModelManifest`), requires an entry per engine and non-empty prices, a 128 KB cap, and demands `updatedAt` moves forward when the file changes. This is a schema and freshness check; nothing runs the new model. I found no automated check that a new model id behaves well.

## 7. End-to-end and UI checks

- Real-server e2e files (`server/*.e2e.test.ts`, `scripts/testing/*.e2e.test.ts`) drive the app through `launchVerificationServer`, the `omb` CLI and a pinned test browser.
- `scripts/verify-live-reply.ts` streams the 16 scripted reply cases through the real renderer, once per engine (claude, codex, acp, cline, copilot, opencode), checking each frame: no duplicated words, none glued together, none vanishing, no thinking shown as reply text, no console errors. It is a recipe, not a CI job (needs a pinned browser).
- Companion/relay: `companion/test/e2e/*` with `fake-relay.ts` and `fake-harness.ts`, plus `scripts/capture-companion-fixtures.mjs`, which records fixtures through a real harness against the fake engine.
- Release smokes (`.github/workflows/release.yml`): signature verify before notarization, packaged server starts and resolves every helper path, bundled browser works with an empty home, Linux package upgrade smokes.
- Updater: `.github/workflows/server-update-e2e.yml` tests update, rollback, a version that never answers and corrupts data, and a kill mid-update.

## 8. Recorded fixtures: what exists and what does not

Exists:
- Redacted golden threads and trace baselines (`evals/golden/`).
- Captured third-party JSON/text fixtures in `server/testing/fixtures/` (Composio Gmail and calendar responses, an OpenCode `models` output).
- Companion app fixtures captured by script.
- Scripted reply cases with unique tokens.

Does not exist (I looked): no recording and replay of real model HTTP responses (no cassettes); no stored real model transcripts used as expected outputs; no multi-sample statistics for real-model evals (no pass@k, no repeated trials per case in tier 3); no automatic regression run of live evals on a prompt change. The live tier, tool-choice and dream runners have no CI job and cost real money per case.

## 9. CI gates

Entry: `.github/workflows/ci.yml`, one required gate job `CI` with `needs: [static, build, vitest, behavior-evals, packaged-server, windows-cua, electron-smokes]`. A job selected by `scripts/ci-scope.mjs` must have passed; a job not selected must have been skipped; a missing or malformed selection fails the gate.

1. `static`: runs `scripts/ci-scope.mjs`, then CI-selection tests, locale check, model manifest check, contrast check, lint, announcements check, and "Source guards" (tests that only read the source: size ratchets, route ratchets, `comment-history`, `lazy-server-modules`). Rationale in a comment: one source guard sat red on main for 11 hours and PRs learned about it only after about 70 minutes of shards.
2. `build`: typecheck, Electron syntax check, UI build.
3. `vitest`: sharded by recorded duration, 8 Linux and 8 Windows shards on main, macOS in the nightly and release lanes. Reproduce one with the same `--shard` and `OMB_VITEST_E2E`.
4. `behavior-evals`: `pnpm exec tsc -p evals/tsconfig.json`; `vitest run --config evals/vitest.config.ts`; `pnpm eval`; `pnpm eval --golden`; and the live tier must print the skip line. Report artifacts upload on failure. Selected when the change touches `server/`, `shared/`, `evals/`, `skills/`, `companion/`, `deploy/` and similar (`SERVER_CHECKS` in `scripts/ci-scope.mjs`).
5. Smokes: packaged server, Windows CUA, macOS Electron.
6. Lanes: when a repository variable turns on Boat CI, `scripts/ci-linux-lanes.mjs` runs the Linux shards, the evals lane and the packaged smoke as parallel process groups on one VM, each with its own timeout and a group-per-lane log. `scripts/ci-workflow.test.ts` holds each command equal to the YAML step it stands for.
7. Events: PRs run only the areas touched; push to main and merge groups run the main lane; nightly (21:17 UTC) and manual dispatch run the full lane (`docs/ci.md`).
8. Local: `scripts/pre-push-check.mjs` runs lint and source guards on only the pushed files inside a 30 s budget; anything it cannot settle is left to CI.

Release (`.github/workflows/release.yml`, `scripts/release-ci.mjs`): ship only a commit whose own code passed `CI` with every platform's every vitest shard. If a main run does not cover that, the script starts CI on a `release-ci/v<version>` branch and waits (`POLL_MS = 60_000`, `MAX_WAIT_MS = 170 * 60_000`). There is an emergency `ship_without_ci` input. A version-only bump may use its parent's run. Each packaging gate in `release.yml` carries a comment saying which past incident it exists for.

## 10. What I could not find or what the code does not do

- No model-quality gate before release: prompt or model changes are not scored by a real model in CI. The only real-model checks are manual, opt-in, per developer account.
- The harness evals do not test "is the agent smart". They test that the harness did what it should around a scripted decision. `evals/README.md` says this deliberately.
- Tier 2 has one golden fixture. I did not check whether other golden samples exist elsewhere.
- No eval grades proactivity quality (when to wake, whether a trigger is appropriate). The only proactive-adjacent scenario I know of is `routine-deferral` (README only; I did not open its JSON). Other proactive tests may exist under `server/*.e2e.test.ts` (for example `routine-cron.e2e.test.ts`, named in my grep); I did not read them.
- Trust and cost: live tier cost is only visible per run (`tool-choice` reads `/api/usage`); there is no budget cap file.
- I did not read the bodies of `lazy-claim-*`, `routine-deferral`, `skill-assignment-visibility`, most of `local-vm-world.ts`, or the many other fake CLIs beyond their headers.
- `docs/ci.md` and `CONTRIBUTING.md` are the maintainers' own claims; I verified them against code where I cite file and function names.

## 11. What Lonora should copy / avoid

Context: Lonora is a Python FastAPI server and worker, React web and Expo mobile clients, a lead agent "Lonora" plus agents the owner creates, trading on MetaTrader 5.

### Copy

1. "Evaluate the harness, not the model." Put a deterministic scripted model behind the same provider interface Lonora's router uses (in Python, a fake `ProviderAdapter` that replays a per-agent turn list). Test admission, steering vs queue, handoffs between Lonora and owner-created agents, routine/watch deferral, and tool gating without any API call.
2. Scenario-as-data with a strict schema (zod in the repo; pydantic in Lonora). Steps drive the real server over HTTP; assertions are pure functions of a frozen snapshot. No scorer reads live state, so a flaky read cannot flatter or fail a run.
3. A scripted fake that calls the real tool surface. `runRoomHandoffAgent` runs real `tools/call` against the real MCP proxy, matches turns by their own text, fails loudly on an `unplanned` turn, and records `{system, prompt, tool calls, responses}` per turn. For Lonora, that makes "agent X may not place an order above its grant", "reduce-only still passes" and "approval card shown" testable end to end through real policy code.
4. Gates, not sleeps. Gate files held open by the test give deterministic busy windows (`gate`, `writeGate`); `waitUntil` and `recordEvents(...).until` wait on state. This matters for trading: tests about concurrent orders, a pause during a watch, or a restart mid-order are only reliable this way.
5. Restart and recovery e2e: boot the real server, script turns, kill it with a signal, restart it on the same data dir, and assert from the database (as `runtime-coordination.e2e.test.ts` does with `runtime.db`). Lonora's worker, leases and reconciliation need exactly this.
6. Golden decision tables for policy (`admission-golden.test.ts`). Do the same for trading admission and risk policy: a table of `(state) -> action`, so any policy change appears as a test diff.
7. Golden trace baselines with argument values dropped: pin tool order, argument keys, error flags, handoff tree and send admission; diff into readable lines; `--update-baseline` is explicit. Pair with a redactor plus leak scan that reports categories, never matched text. Real trading conversations contain account numbers and money, so this redaction discipline is mandatory before any fixture is committed.
8. Live tier closed by default and visibly skipped in CI (the skip line is the pass condition). Versioned, sha256-pinned judge prompts with strict JSON verdict parsing; committed thresholds (`minScore`, `maxDrift`); baseline kept out of git; drift line for before/after of a prompt change.
9. Real-failure case banks (`tool-choice/cases.json`, `dream/cases.json`): every case names the real failure it came from. Lonora has Arabic users; keep those cases in Arabic, as this repo keeps German, Spanish and Japanese ones.
10. Deterministic graders for risky text: `dream/score.ts` folds width, invisible characters and look-alike digits before testing forbidden words. Reuse the idea for "no secrets or account numbers in saved memory or logs".
11. Prompt bytes as code: a 2% budget per fixed prompt section, byte-pinned tool catalog goldens per profile, an identical-prefix test for prompt caching, and `instructionsInclude`-style assertions on what the model was actually sent. A cheap way to catch accidental prompt growth.
12. CI structure: one required gate that checks "selected jobs passed, unselected skipped"; scoped selection by changed paths; source-only guards run first in a fast job; known-flaky tests listed with owner and evidence and retried in CI only; release requires green CI on the exact release commit.
13. Keep the fakes honest: a test that fakes import nothing outside their folder, and fakes that emulate the real wire protocol rather than mocking internals.

### Avoid or improve

1. Do not stop at harness evals. This repo has no automated real-model gate; for a trading assistant, add a small nightly (not per PR) real-model suite on cheap models for safety invariants (never exceeds mandate, asks approval when out of grant, does not place orders when `observe_only`), with several samples per case and a pass-rate threshold rather than one run.
2. Do not rely on a single baseline score with a 0.25 drift allowance. That is loose for safety behavior. Use per-case hard invariants (must pass every time) plus an aggregate for style.
3. Do not let one golden fixture stand for the pipeline. Commit several, including a failure path and a restart path.
4. Avoid hand-run live comparisons for prompt changes. Automate the base-vs-change run (worktree, same cases, drift line) as a labelled workflow that posts the table on the PR.
5. Avoid env-knob sprawl in the fakes (about 80 knobs in `fake-claude-cli.ts`, 2000 lines in `fake-acp-cli.ts`). Prefer plan files like the room plan for new behavior.
6. Do not claim a skill or prompt "improves" a model from a scripted-model bench; that bench only validates plumbing. Label such results as harness checks.
7. Add what is missing here and Lonora needs: proactivity evals (given a broker event or market condition, does the right agent wake, and does a quiet-hours rule hold), cross-agent message evals (lead agent to owner-created agent), and cost caps for any live run.
