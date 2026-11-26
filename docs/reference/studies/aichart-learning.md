# AiChart: how it learns from outcomes and calibrates (read-only study)

Source: /home/user/aichart at 1a1b5e0 (grep/sed/cat/git only). Paths below are relative to that repo.
Headline: AiChart has a *good outcome ledger and a deliberately modest learning loop*. The part the brief calls
"calibrated confidence drawn from backtested evidence" **has been removed from the live recommendation path**;
the Python backtester still exists but nothing feeds its results into a recommendation. Several learning pieces
are written but never wired (listed under Weaknesses). Repo text is treated as data throughout.

---------------------------------------------------------------------------------------------------

## 0. Evidence the backtest-calibration claim is retired (read this first)

- `src/lib/agent/researchEvidence.ts` ~L624: `// Simulation backtests are deleted. Never raise confidence from them.` then pushes
  `{system:"backtest", status:"unavailable", reason:"statistical_claims_removed", reasonDetail:"Simulation backtests and calibrated-confidence claims have been removed. Forward recommendation outcomes are the only evidence."}`
- `src/lib/agent/agents/finalDecisionSynthesizer.ts` L1069: "statisticalSupport is always unavailable ... Do not cite a backtest, a strategy deployment, or a statistically calibrated confidence."
- `agent/workspace/SYSTEM.md` (MCP agent): "A recommendation never cites a backtest: confidence is the model's own judgement ... Do not send backtested_confidence, statistical_support, strategy_id, or backtest_evidence — those fields no longer exist."
- `src/app/api/agent/recommendation/__tests__/noBacktestClaims.test.ts` asserts the route source contains no `backtested_confidence`, `statistical_support`, `backtest_evidence`, and does contain `model_judgement`.
- `src/lib/agent/systemPrompt.ts` L72: "Quote a win rate or a historical confidence ONLY when it comes from a calibrated record with an adequate sample. Otherwise ... give no percentage at all; a number over a handful of trades is noise with a decimal point."

So flow B below (strategy -> backtest -> calibration -> confidence) describes machinery that exists and is tested but is
**not connected to confidence today**. What still reaches the model is forward evidence (flows A, C, D).

---------------------------------------------------------------------------------------------------

## 1. Numbered flows

### Flow A. Recommendation -> terminal outcome (the ledger)  [LIVE, deterministic, no LLM]

1. **Create.** MCP `create_recommendation` -> `src/app/api/agent/recommendation/route.ts`. The model's own confidence is stored as
   `model_judgement` (clamped 0-100). A visual-review penalty can only *lower* the displayed number
   (`applyVisualConfidencePenalty`). The route attaches up to 3 prior lessons to the rationale text (`searchSimilarLessons(..., embeddings:false)` -> `formatLessonsForPrompt`).
   Plan carries entry type / fill rule, entry zone, stop, 2-3 targets, invalidation, validity, optional machine-checkable `activationRule`.
2. **Fill rule is part of the plan**, not assumed (`recommendations/entrySemantics.ts`): `market`, `limit_touch`, `confirmation_close` (fills at the confirming candle's CLOSE), `retest_zone`. `effectiveEntry` is the honest fill; all R math uses it, never the nominal level.
3. **Sweep.** Cron `src/app/api/cron/recommendation-sweep/route.ts` -> `runRecommendationSweep` -> `trackRecommendations` (`recommendationTracker.ts`). For each non-terminal rec: `fetchOhlc({fromMs: createdCandleTime, skipCache:true})`, keep only `isCandleComplete` candles, convert to `TrackerCandle{time,open,high,low,close}`.
   A rule that names its own timeframe is graded on that timeframe's candles.
4. **Evaluate** (`recommendationStatus.ts::evaluateRecommendation`, pure function). Documented policies:
   - creation candle never triggers or stops the plan; candles must be strictly after it;
   - same-candle SL+TP after entry is ambiguous from OHLC -> **SL first** (risk honesty) unless a TP was already banked earlier;
   - TPs are sequential (TP2 only after TP1) and use a *target zone* equal to the entry-fill band (`targetHitTolerance`, gold floor 10 / cap 15 points); the recorded hit price is the nearest traded extreme that entered the zone, not the labeled line;
   - TP then SL/expiry = partial win at the highest TP reached (`win_tp{n}`);
   - "no wall-clock expiry" doctrine after a 2026-09-10 incident (closed -> expired illegal transition);
   - terminal rows are never re-evaluated.
5. **Measure** (`tradeMetrics.ts`): MFE/MAE in R from the *fill*, realized R of the real exit (a close-mode stop can be worse than -1R and is recorded as such), time-to-activation, time-in-trade, `stopBreachSurvivedCount`, exit reason (`target|stop|stop_after_target|expiry|expiry_after_target|invalidated|cancelled`).
6. **Persist** (`recommendationStore.ts::updateTrackedRecommendation` -> `appendTrackerOutcome` -> `canonical/outcomes.ts::recordRecommendationOutcome`): an **append-only** `recommendation_outcomes` row with `dedupe_key = "tracker:<TYPE>"` (idempotent), `source:"deterministic_tracker"`, `evidence:{method:"complete_ohlc_candles", validated:false}`. Then `appendLearningEvents` writes `recommendation_learning_events` (`PartialTargetHit | FinalTargetHit | RecommendationSucceeded | RecommendationFailed | Expired | Invalidated | ...`) with deterministic ids `rec:<id>:outcome:<oid>:<type>`.
   Note `RecommendationSucceeded` is emitted only for **TP3**; TP1/TP2 are `PartialTargetHit`. A TP1-then-stop partial win is a `ManualClose` row and produces *no* success/failure event (see Weaknesses).
7. **Lifecycle events** (`lifecycleEvents.ts`, `lifecycleNotifier.ts`): changes are announced to the operator; `reevaluationTriggers.ts` + `reevaluationCycle.ts` can re-run the brain on a live plan after the deterministic pass, but only `applyRecommendationRevision` may change a plan - the tracker "grades, never decides".

### Flow B. Outcome -> lesson (what actually gets written)  [PARTIALLY LIVE]

1. After every outcome insert, `ensureDerivedLearning` calls `evaluateTradeLessonCandidate(userId, recId)` (`canonical/tradeLessons.ts`).
2. It pulls all `RecommendationSucceeded|RecommendationFailed` events for the user in the same market, keeps the same direction, requires `n >= 5` (`DEFAULT_LESSON_MIN_SAMPLE_SIZE`).
3. `result = successes >= failures ? "success":"failure"`; `confidence = (dominantShare * meanStatedConfidence/100)`; needs `>= 0.65`.
4. Upsert a row in `trade_lesson_candidates` keyed by fingerprint `strategyId:market:direction:result` (strategyId is effectively `direct_analysis`), status `candidate`, with `evidence_event_ids_json` (last 100), `affected_symbols_json`, `sample_size`, and a canned English `reason` ("... produced a validated majority of successful buy recommendations").
5. `validateTradeLessonCandidate` would promote to `validated`, but **nothing calls it** outside tests. So `listValidatedTradeLessons` (what `get_trade_lessons` returns as `validated_patterns`) is always empty in this tree.
6. Separate "personal notes" path (`recommendations/personalNotes.ts`): per symbol, group resolved TP/SL outcomes by trading session (asia/london/newyork from creation time). A note exists only if a session has >=5 results and the dominant result share >= 0.65. Text is an observation, e.g. "نتائجك في جلسة london على XAUUSD: 6 رابحة و2 خاسرة من 8 بمتوسط عائد متحقق 0.41R." Max 2 notes. Persisted as candidates with fingerprint `personal_note:<sym>:<session>:<result>`.
7. **Free-text post-mortem lessons (`trade_lessons` table + `insertTradeLesson` + job `trade_post_mortem`) have no writer.** `insertTradeLesson` is defined in `tradeMemory.ts` and never called; `trade_post_mortem` is declared in `queue.ts` `JobPayloads` but `registerHandler` is only called for `opportunity_scan` and `memory_lifecycle` (`src/lib/jobs.ts`). `git log -S insertTradeLesson` shows only the merge commit. The table and its embedding search are read-only plumbing.

### Flow C. Lesson/outcome -> next recommendation prompt  [LIVE, evidence-only]

Two independent read paths:

1. **Platform brain** (`agent/orchestrator.ts::buildLessonsBlock`, called at ~L1307 before the decision call, passed as `lessonsBlock` into `finalDecisionSynthesizer`):
   - `listTrackedRecommendations(userId,{limit:60})`, keep `outcome === loss | win_*`, map to `TradeOutcomeRecord{symbol,direction,won,rMultiple,session,closedAt}` (`rMultiple` via `realisedRMultiple`, `session` via `sessionOf(createdAt)`; a comment records that both used to be hardcoded null so the analysis "ran on every request and could never conclude anything").
   - `summarizeTradeLessons` (`agent/learningLoop.ts`): per symbol, last 20; `MIN_LESSON_SAMPLE=5` else counts only; weak session if >=60% of >=3 losses; weak direction if one side's win rate is >=0.30 below the other with >=3 each; average R.
   - `appendPersonalNotes` adds <=2 session notes; `renderLessonsForPrompt` renders Arabic text framed as "سياق تزنه، لا قاعدة تُلزمك ولا بديل عن قراءة السوق الحالية" (context you weigh, not a rule). Under-sample: "N نتيجة فقط — عينة أصغر من أن تُبنى عليها ملاحظة."
   - Any error -> `null` block ("History is an aid, never a gate").
2. **MCP agent** (`get_trade_lessons` tool in `mcp/src/tools/core.ts` -> `GET /api/agent/memory/lessons`): returns schema `structured-trade-lessons-v1` with `lessons[]` from `trade_lessons` (empty, see B7) and `validated_patterns[]` (empty, see B5). `create_recommendation` also appends up to 3 symbol-filtered lessons into the rationale (embedding call forbidden on that surface: "zero platform model spend"). The MCP SYSTEM.md tells the model to weigh lessons "in 1-2 sentences of prose, or skip them" and never present them as statistical support.
3. **Historical-market memory** (`marketMemory/*`, MCP `find_similar_cases`): fingerprint the current moment, fetch both directions at once, return hit rate / average net R only when `sampleSize >= MIN_STATS_SAMPLE (8)`; below that, counts only; `found:false` -> "no comparable history" (see D).
4. **Trading DNA / shadow trader** nudge the displayed confidence (see E).

### Flow D. Historical case memory (the data-measured piece that is still live)

1. Indexer (`caseIndexer.ts`, `goldCaseIndexer.ts`) walks warehouse candles. For each past moment: `fingerprintAt(candles)` using only candles at/before that time -> `CaseFingerprint{regime, trend, rangeZone, pullbackDepth, impulseAtr, volatility, session, structureRun}`.
2. `forwardOutcome.ts::resolveForwardOutcome` walks only candles strictly after: stop = 1 ATR, target = 2 ATR, horizon 40 bars, stop wins same-bar ties, `netR` net of a round-trip cost -> `{resolution: target_first|stop_first|unresolved|false_break, bars, maxFavourableAtr, maxAdverseAtr, netR}`.
3. Query (`caseQuery.ts::findSimilarCases/collectCaseEvidence`): weighted similarity on `fingerprintVector`, optional same-pattern subset, optional forming-pattern stage stats; `statisticallyUsable` flag; `describeSimilarCases` prints "N حالة مشابهة: وصل الهدف قبل الوقف في X% بمتوسط صافي YR" only above the floor.
4. Route `src/app/api/agent/similar-cases/route.ts` accepts `at_ms` to answer "as of then" (cases at/after it excluded) - an anti-lookahead guard.
5. It deliberately queries long and short *together* "before the direction is chosen ... otherwise evidence becomes justification".

### Flow E. Operator-history confidence nudge  [LIVE]

`agent/researchEvidence.ts::collectBoundedResearchEvidence`: Trading DNA snapshot (`tradingDna/*`) and Shadow Trader each yield a delta; `scoreDnaReliability` is weighted by sample (n<5 -> 0; n<20 -> 0.35; n<50 -> 0.7; else 1) and by metric support; deltas clamped (DNA -0.12..+0.08, shadow -0.09..+0.07 scaled by shadow confidence, <0.35 conf -> 0); total `historicalEvidenceTendency` clamped **-0.15..+0.10** and applied to `finalDecision.confidence` in `orchestrator.ts` ~L2133 (the code comment says the number must actually move if the UI claims a nudge). Budget 900 ms; every skipped system gets a machine reason code.

### Flow F. Strategy -> backtest -> calibration -> confidence  [CODE EXISTS, NOT WIRED TO CONFIDENCE]

1. **Strategy definition** (`research-service/app/strategies/`): `StrategySpecification` (pydantic, frozen, `extra="forbid"`, strict) in `schema.py` (741 lines). `spec_version "1.0.0"`, `market: forex`, symbols validated against `SYMBOL_REGISTRY` (28 FX pairs + XAUUSD + XAGUSD with pip/tick/contract size), `timeframes{entry, higher<=3}`, `direction long|short|both`, entry condition trees (`all|any|not`, depth<=8, <=256 leaves, every leaf timeframe must be declared), `entry` (order type, price reference, offset, valid_for_bars, cooldown, reentry), `stop_loss` (fixed_pips | atr_multiple | recent_swing | percentage | structure_level), `targets[]` (size_percent must total exactly 100; fixed_pips | risk_reward | atr_multiple | percentage | structure_level), `position_sizing` (fixed_lot | fixed_notional | risk_percent), `management` (break-even, trailing with tightening-only, max holding bars, close on opposite signal, session close), `risk_controls` (max positions, daily loss %, consecutive-loss pause, daily trade limit, min reward:risk), `costs` (spread none|fixed|bar_column|session_schedule; slippage none|fixed pips/ticks|percentage|seeded distribution; commission; carry).
   Condition leaves: `price_comparison, ema_relation, sma_relation, rsi_threshold, atr_threshold, macd, bollinger, range_breakout, market_session, day_of_week, time_window`.
2. **Compile** (`compiler.py::compile_strategy`): parse+validate, `canonical_strategy_dict`, `strategy_spec_hash` (sha-256 over canonical spec -> `spec_hash`), derive `indicator_requirements` and per-timeframe `warmup_bars`, pin `signal_timing:"bar_close"`, `order_activation_timing:"next_bar"`, `source_generated:False` (no code generation).
3. **Store** (`store.py`): immutable versioned `StrategyVersion{strategy_id, version_id, version_number, parent_version_id, spec_hash, status draft|valid|invalid|deprecated, change_summary}`; conflicts raise. Only an in-memory implementation shown ("restart loses every version"); the web side keeps its own catalog.
4. **Catalog** (TS, `src/lib/strategies/catalog.ts` + `catalogGen.ts`): ~60 strategy ids (3 hand-written legacy + generated families x parameter grids). `CATALOG_SPEC_REVISION = "6"` is bumped whenever geometry/costs change so *stale results are never reused* (rev 4: timeframe-aware risk geometry; rev 5: MACD/Bollinger leaves; rev 6: session-aware spread). `riskPolicy.ts` maps timeframe -> style (scalp/intraday/swing) -> ATR stop multiple, R targets, max hold, break-even.
   Example condition leaf: `{"type":"ema_relation","timeframe":tf,"fast_period":20,"slow_period":50,"operator":"crosses_above"}`.
5. **Backtest** (`backtest/engine.py`, `execution.py`, `orders.py`, `positions.py`, `accounting.py`, `metrics.py`): bar-close signals, next-bar activation, per-session costs, carry, trailing/break-even management, end-of-run close. `metrics.py` returns profit factor (null + reason when no losses), average/median R, Sharpe, Sortino, max drawdown (abs + %), recovery factor, win/loss streaks, `intrabar_ambiguous` count, exposure, holding time, breakdowns by side/weekday etc., with an explicit `reasons{}` dict for every metric that is undefined.
6. **Validation suite** (`validation/`): `monte_carlo.py` (shuffle + execution-cost stress), `bootstrap.py` (expectancy/etc. CI, IID or block), `walk_forward.py` (train/OOS windows, "likely_overfit" flag), `sensitivity.py` (parameter perturbation stability), seeded for determinism.
7. **Readiness classification** (`validation/readiness.py::classify_readiness`): `rejected -> needs_more_data -> experimental -> paper_ready -> demo_ready -> live_candidate`. Fixed `ReadinessPolicy` defaults: trades 20/50/100/200; OOS windows 2/3; max drawdown 0.35/0.25/0.20; profit factor 1.0/1.15/1.25; cost-stress profitable probability >= 0.70; walk-forward profitable fraction >= 0.60; MC loss probability <= 0.20; intrabar ambiguity <= 0.05; bootstrap expectancy lower bound > 0; sensitivity stable. Monotonic-threshold validator. `live_candidate` always carries `live_trading_authorized=False`. Missing evidence is reported as `"<name> is unavailable"` warnings and **fails** the gate (absence is never a pass).
8. **Confidence calibration** (`src/lib/strategies/calibration.ts`): `calibrateBootstrapWinRate` - below 30 trades return a Wilson interval with `statisticallySufficient:false`; at >=30, a seeded xorshift IID bootstrap CI (default 2000 iterations, 90%). `selectionBias.ts` adds an IC pre-filter and Deflated-Sharpe note ("test 100 random strategies at 5% and ~5 pass on luck"); `thresholds.ts`: `MIN_BACKTEST_TRADES = 100`, "lowering the 100-trade minimum" is listed as "must not change"; `liveCostProfile.ts`: per-session spread median/p90 from live samples (`MIN_SAMPLES=20`, 14-day window, stale after 24h), static class spreads only as fallback and `null` when not modellable.
9. **Where it used to go and where it stops now:** `researchEvidence.decideResearchJustification` still *decides* whether a backtest is "worth it" (mid-confidence 0.45-0.78, or the user asked) but then records `statistical_claims_removed`. No code path converts a readiness result or bootstrap interval into a `confidence` number on a recommendation. `src/lib/strategies/decayLifecycle.ts` (see below) and `canonical/goldLearning.ts` are likewise orphaned.

### Flow G. Performance and decay  [MOSTLY ANALYTIC, DECAY NOT WIRED]

- `recommendations/recommendationStats.ts`: win rate over *completed triggered* plans only; `WIN_RATE_SAMPLE_FLOOR = 8` -> below it `winRate = null` (counts only). Also activation rate ("honesty metric for a conditional-plan product"), expired-unactivated rate, total realized R, expectancy, profit factor, cumulative-R **equity curve** (`EquityCurvePoint{id,at,grade,r,cumR}`), streaks, recent outcomes strip.
- `canonical/analytics.ts::computeCanonicalRecommendationAnalytics`: totals, `expectancy = mean(R)`, profit factor, avg MAE/MFE, and groupings by symbol, timeframe, strategy, **confidence bucket (10-point bands)**, session, exit reason, entry type, **decision source (platform_agent vs mcp_client kept apart)**, month, day.
- `recommendations/tradabilityCalibration.ts` + cron `tradability-calibration`: did "tradability" verdicts tell the truth? per verdict: activation rate, died-waiting, predicted vs actual bars-to-activation. Used "so the limits are tuned against evidence instead of taste".
- `strategies/decayLifecycle.ts`: `active -> monitoring -> decayed -> disabled` with asymmetric hysteresis (downgrade immediate, upgrade needs `recoveryStreak` = 2 healthy evaluations), `minSampleForJudgement 20`, win-rate drop 15% -> monitoring, 30% -> decayed, live profit factor <= 1 -> disabled, Sharpe < 0 -> monitoring; "disabled" never auto-revives. **No non-test caller of `evaluateLifecycle` exists** - there are no actual decay alerts in this tree.
- `canonical/goldLearning.ts`: versioned advisor-weight updates (`candidate -> active -> rolled_back`), exponential decay 0.98, weights clamped 0.3..2.0, only advisors with >=20 samples, requires >=20 validated events and 0.70 dominance; no non-test caller of `proposeGoldWeightVersion` / `activateGoldWeightVersion`.

---------------------------------------------------------------------------------------------------

## 2. Data shapes (short excerpts)

Outcome ledger row (`canonical/outcomes.ts`):
```
recommendation_outcomes(recommendation_id, user_id, outcome_type, target_index, price, r_multiple,
  pnl, holding_ms, mae, mfe, spread_cost, slippage, commission, risk_used, occurred_at,
  source, evidence_json, dedupe_key)          -- type: TP1|TP2|TP3|SL|BreakEven|Trailing|Expired|Cancelled|Invalidated|ManualClose
recommendation_learning_events(event_id, recommendation_id, user_id, event_type, occurred_at,
  source_outcome_id, payload_json, evidence_json)
```
Tracked status vs outcome (`recommendations/types.ts`): status `pending_entry|triggered|tp1_hit|tp2_hit|tp3_hit|sl_hit|invalidated|expired|cancelled`; outcome `pending|win_tp1|win_tp2|win_tp3|loss|expired|cancelled|invalidated`; "A record is TERMINAL when outcome !== pending."

Trade metrics (`tradeMetrics.ts`):
```
{ mfeR, maeR, realizedR, exitPrice, exitAt, exitReason, timeToActivationMs, timeInTradeMs,
  stopBreachSurvivedCount, lastStopBreachSurvivedAt }
```
Lesson candidate (`canonical/tradeLessons.ts`):
```
{ fingerprint:"direct_analysis:forex:buy:success", status:"candidate|validated|rejected",
  reason, evidenceEventIds[], strategyId, market, confidence, affectedSymbols[], sampleSize }
```
MCP lessons response (`api/agent/memory/lessons/route.ts`, `schema_version:"structured-trade-lessons-v1"`):
```
lessons:[{ lesson_id, recommendation_id, trade_id,
  result:{outcome,pnl,pnl_pct}, strategy:{id:"direct_analysis"},
  market_context:{symbol,market,timeframe,regime,direction,confidence,entry:{...}},
  evidence:{tags[],similarity,recorded_at}, summary_ar }],
validated_patterns:[ ...TradeLessonCandidate ]
```
Lesson summary fed to the prompt (`agent/learningLoop.ts`):
```
LessonSummary{ symbol, sampleSize, wins, losses, winRate, averageR, weakSessions[], weakDirection,
  notes[]  /* "Short factual lines for the model. Never instructions." */, insufficient }
```
Case memory (`marketMemory`): `CaseFingerprint{regime,trend,rangeZone,pullbackDepth,impulseAtr,volatility,session,structureRun}`; `ForwardOutcome{resolution,bars,maxFavourableAtr,maxAdverseAtr,netR}`; evidence `{fingerprint,long:{sampleSize,hitRate,averageNetR,averageBars,samePattern,formingStages,summary},short:{...},note}`.
Strategy spec (research-service): see Flow F.1; readiness: `ReadinessResult{readiness_status, readiness_reasons[], failed_gates[], warnings[], live_trading_authorized:false}`.

---------------------------------------------------------------------------------------------------

## 3. Fixed numeric rules vs evidence measured from data

Fixed (hand-set constants; correct to call "rules", not "learned"):
- Sample floors: lessons 5, personal notes 5, win-rate display 8, case stats 8, DNA 5, cost profile 20, decay judgement 20, gold weights 20, bootstrap sufficiency 30, backtest trades 100, IC sample 60.
- Lesson heuristics: weak session = 60% of >=3 losses; direction gap 0.30; candidate confidence gate 0.65 (gold 0.70).
- Confidence nudge bounds (-0.15..+0.10), DNA/shadow coefficients (0.06, -0.10, 0.07, -0.09), sample weights 0.35/0.7/1.
- Gold target/entry tolerance 10-15 points; same-candle tie -> stop; case outcome geometry stop 1 ATR / target 2 ATR / horizon 40 bars.
- Readiness policy table (Flow F.7), decay thresholds (0.15 / 0.30 / PF 1 / streak 2), gold weight decay 0.98 and clamp 0.3-2.
- Per-timeframe risk policy (`riskPolicy.ts`), static class spreads (fallback only).

Measured from data:
- Every R multiple, MFE, MAE, hold time, activation time (from real complete candles).
- Per-symbol/session/direction win rates, average R, expectancy, profit factor, equity curve, confidence-bucket outcomes, decision-source split.
- Case-memory hit rates and net R (warehouse candles, forward-only).
- Live per-session spread median/p90 and derived slippage (`liveCostProfile.ts`).
- Tradability verdict activation rates vs predicted.
- Backtest metrics and validation statistics (when run) and bootstrap/Wilson intervals.

Observation: the thresholds that *interpret* data are fixed even though the numbers they test are measured. Nothing re-tunes the thresholds themselves except the manual `tradability-calibration` report.

---------------------------------------------------------------------------------------------------

## 4. Strengths

1. **Evidence, never a veto.** Lessons produce observations, no score/gate; a read failure degrades to no block. Prompt wording and code both enforce that the model keeps authority.
2. **Honest grading.** Fill rule is part of the plan; R is measured from the real fill; SL-first on ambiguous candles; close-mode stops may exceed -1R and are recorded so; complete candles only; creation candle excluded; target zones use traded extremes.
3. **Append-only, idempotent ledger** with dedupe keys, deterministic event ids, explicit source and `validated:false`, plus decision-source separation so MCP-client plans and platform plans never mix.
4. **Sample-size discipline everywhere.** Below the floor: counts, not percentages; "no comparable history" instead of a rate; incentives against fabricated precision.
5. **Look-ahead discipline.** Fingerprint uses past only, outcome uses future only, different functions; `at_ms` replay excludes later cases.
6. **Bug-honesty culture.** Comments record real incidents (hardcoded-null R silently disabling analysis; wall-clock expiry crash; "-1 lie").
7. **Research-service design.** Frozen strict schema, closed condition DSL (no generated code), canonical hash for reproducibility, immutable versions, spec revision bumping to invalidate stale results, explicit "undefined metric + reason", monotonic readiness policy, missing evidence fails gates, `live_trading_authorized` hard false, multiple-testing guard for catalog growth.
8. **Both-directions case query before choosing direction** (avoids evidence-as-justification).
9. **Display honesty:** nudge applied to the number if the UI claims it; every skipped research system carries a reason code.

## 5. Weaknesses

1. **The learning loop is thin and partly dead.** `trade_lessons` has no writer (`insertTradeLesson` and `trade_post_mortem` never connected); `validateTradeLessonCandidate`, `evaluateLifecycle` (decay), `proposeGoldWeightVersion/activate` have no production callers. So `get_trade_lessons` returns empty `lessons` and empty `validated_patterns` in practice, and there are no decay alerts.
2. **Lesson candidates are shallow.** Fingerprint is `direct_analysis:market:direction:result`; it learns "your buys win more than they lose", not *why*. Confidence multiplies win share by the model's own stated confidence, mixing measured with self-reported. No tags for regime, setup, session, news, entry type, invalidation reason.
3. **Partial wins are invisible to lessons.** `RecommendationSucceeded` only on TP3; TP1/TP2 are partials; TP-then-stop is a `ManualClose` row with no success/failure event. A strategy that regularly banks TP1 and TP2 looks neutral or negative to the lesson candidate builder.
4. **Gold-centric constants.** Tolerance bands, prompts and SYSTEM.md are tuned to XAUUSD points; SYMBOL_REGISTRY is a hard-coded list (28 FX pairs + gold/silver); market is `forex` only; `personalNotes` writes `market:"forex"`. Not "any symbol".
5. **No closed loop to confidence.** Calibration code (Wilson/bootstrap, readiness, selection bias) is orphaned; confidence is the model's own number plus a +/-0.15 nudge from DNA/shadow. There is no calibration curve checking that "80" means 80% (only `byConfidence` buckets in analytics, display only).
6. **Fixed thresholds interpreting measured data** (floors, 60%, 0.30, 0.65) - never tuned from outcomes; sample floors of 5 are low for the stated claims (5 trades can flip a session note).
7. **Outcome simplifications.** Case memory uses a universal 1 ATR / 2 ATR geometry, not the plan's own risk geometry; R in analytics falls back to +/-1 when R is missing; graded on platform candles (OANDA/warehouse) not the account's own fills; spread/slippage in the tracker are modelled, not realized from a broker.
8. **Dedupe by type, not occurrence.** `tracker:<TYPE>` means one SL per recommendation, fine here, but reopened/re-entered plans (re-evaluation revisions) share a recommendation id and could collide.
9. **Research store is in-memory** (restart loses strategy versions); catalog lives in TS separately from the Python store, so "what is a strategy" exists in two places.
10. **Language coupling.** Lesson text is Arabic strings built in code; the English `reason` on candidates is canned; machine-readable tags are thin, so retrieval by embedding or symbol is the only index.
11. **No per-lesson provenance of use.** Nothing records "lesson X was shown for recommendation Y and the outcome was Z", so the system cannot learn whether its lessons help (types.ts has a comment about `trade_lessons` IDs referenced per analysis, but that is not measured).

---------------------------------------------------------------------------------------------------

## 6. What Lonora should take (agent trading any symbol on MT5 through Lonora's execution door)

Principle: the user asked for a model with *skills, rules and experience, not fixed numbers*. AiChart's best idea is the separation: **measure outcomes honestly (code), express them as quantified observations (code), let the model judge (LLM)**. Take that; skip the dead branches and the gold-specific constants.

### Take as-is (design)
1. **Outcome ledger + terminal grading against closed candles, with the grading rules written down.** Port the policies: fill rule belongs to the plan, grade from the real fill, SL-first on ambiguous candles, complete candles only, measured R/MFE/MAE/time-to-fill/time-in-trade, exit reason taxonomy, partial-win handling. For Lonora with real MT5 execution, *prefer the broker's actual fills, spread, slippage, commission and swap* (AiChart's `spread_cost/slippage/commission/risk_used` columns exist but are unused by the tracker) and keep candle-grading for *plans that were not executed* (counterfactual/shadow outcomes). Record `source` ("broker_fill" vs "candle_replay") on every row.
2. **Append-only outcome ledger with dedupe key and learning events**, plus **decision-source separation** (which agent/skill/model produced the plan).
3. **Evidence-never-veto contract** for lessons, and "below the sample floor, counts not percentages" as a code-level rule for everything the model sees.
4. **Both directions queried before choosing** and **look-ahead-safe features/outcomes in separate functions** for any similar-case memory.
5. **Group-by analytics** (symbol, timeframe, session, entry type, decision source, confidence bucket, exit reason), expectancy, profit factor, cumulative-R curve, activation rate.
6. **Closed, strict, hashable strategy DSL** only if Lonora wants agent-authored *testable* playbooks later: frozen schema, canonical hash, immutable versions, revision bump on engine/cost change, "undefined metric + reason". Keep it optional; it is the heaviest part and unused by AiChart's own confidence today.
7. **Readiness ladder semantics** (missing evidence fails the gate; "live_candidate" never authorizes live) as a pattern for promoting a *playbook* to wider autonomy, but express the gate values as owner/mandate policy, not code constants.

### Do differently (to meet "knowledge, not fixed numbers")
1. **Make learning actually close the loop, and make it model-written.** AiChart's code writes shallow stat candidates; its intended free-text post-mortem was never connected. Lonora should, on every terminal outcome (and on meaningful interim events such as "reached +1.5R then stopped"), hand the model the full record (plan, market context at entry, what the market did after, MFE/MAE, costs, the reasoning it wrote) and have the *agent* write a short structured **lesson**: `{situation, what_I_expected, what_happened, cause (skill|execution|market|news|luck), rule_or_skill_candidate, applies_when, does_not_apply_when, evidence:{recommendation_ids,n}, confidence:'tentative|supported|well_supported'}`. Code supplies facts and sample counts; the model supplies interpretation. Store in the agent's own memory/skills (Lonora's E5 memory and skill machinery) rather than a separate table nobody reads.
2. **Promote skills from lessons with evidence gates stated as counts and recency, not percentages.** A lesson becomes a *skill/rule candidate* when the agent can cite >=N independent outcomes (N chosen by the agent per instrument/timeframe and shown to the owner), tracked by the ledger, with a counter-case list. Demotion/decay: re-evaluate a skill whenever new outcomes arrive; show "supported by 9, contradicted by 4, last contradicted 3 days ago". AiChart's decay state machine (active/monitoring/decayed/disabled with asymmetric hysteresis) is a good template - but *wire it* and apply it to skills/playbooks, not only strategies.
3. **Generalize beyond gold/forex.** Pull symbol metadata (digits, tick/pip size, contract size, currency, trading hours, min lot, step) from MT5 `symbol_info` at runtime instead of a hard-coded registry; compute tolerance bands from ATR/spread/tick size rather than "gold 10-15 points". Group lessons by *instrument class* and by symbol, so a lesson learned on XAUUSD can be offered (as lower-weight evidence) on XAGUSD or indices, and labelled as transferred.
4. **Measure calibration of the model's own confidence** rather than hard-wiring a nudge: keep the model's stated confidence on each plan, bucket outcomes by it, and show the agent its own reliability curve per instrument/horizon ("your 70-79 plans: 11 resolved, 6 TP1+ ... small sample"). The agent then adjusts itself; the platform never rewrites the number. This replaces AiChart's -0.15..+0.10 DNA/shadow nudge and its removed backtest calibration.
5. **Backtests as skill-testing tools for the agent, not as a confidence source.** If Lonora ports anything from research-service, port: the engine's honesty rules (bar-close signals, next-bar activation, session spreads from live samples, SL-first), `calculate_metrics` with explicit reasons for undefined values, bootstrap/Wilson intervals, walk-forward OOS and the multiple-testing warning. Use them when the agent proposes "I think pattern X works" so it can test it on MT5 history and read back `{n, expectancy_R, CI, oos_windows, cost_stress}`; the model decides what to do. Do not convert them to a single confidence number.
6. **Log lesson usage.** Record which lesson/skill ids were in the prompt for each recommendation (AiChart does not), so the outcome ledger can later say whether plans that used a lesson did better - the only way to know the lessons help.
7. **Keep thresholds out of code where possible.** Put sample floors, tolerance multipliers and "weak-session" cutoffs in the agent's visible settings or mandate (owner-editable, versioned), and record the version used on each evaluation, like AiChart's catalog spec revision.
8. **Count partial wins correctly.** Emit success/failure learning events for every terminal exit using realized R (win if R >= some banked-R, loss if < 0, scratch otherwise) so TP1-then-stop trades are not invisible.
9. **Replay window = counterfactual learning.** Because Lonora's door executes real orders, also grade *unexecuted* plans (blocked by risk limits, declined by the owner, awaiting approval) against candles, labelled counterfactual, so the agent learns from decisions it could not or did not take and the owner can see the cost of a refusal. Never mix counterfactual and executed in the same statistic.

### Concrete data shapes to adopt (suggested, not copied)
```
outcome:  { plan_id, agent_id, symbol, instrument_class, source:"broker_fill|candle_replay",
            entry_fill, exit_fill, realized_R, mfe_R, mae_R, time_to_fill_ms, time_in_trade_ms,
            exit_reason, costs:{spread,slippage,commission,swap}, session, regime_at_entry,
            lessons_in_context:[lesson_id], model_confidence, skill_ids_used }
lesson:   { id, written_by:"agent", situation, expectation, result, cause, rule_candidate,
            applies_when[], not_when[], evidence:{plan_ids[], n, contradicted_by[]}, status:"tentative|supported|retired",
            transferred_from?: symbol|class, last_validated_at }
facts_block (what the code hands the model): counted observations only, each with n, window, and "insufficient" flag
```

### What not to copy
- The orphaned modules (gold weights, decay, validate-candidate, `trade_lessons` embedding search without a writer).
- Gold/forex-only registries and point tolerances.
- Candidate confidence formed from the model's stated confidence times win share.
- Any recommendation field carrying "backtested/statistical confidence"; AiChart itself removed it.
- Free-text Arabic strings generated in code as the only lesson representation.
