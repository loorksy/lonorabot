# AiChart trading knowledge study (read-only)

Source: /home/user/aichart at 1a1b5e0. Nothing was edited, built or run. All paths below are relative to that repo.
There are no methodology docs: `docs/` only holds `vps-install.md`; README and MIGRATION_NOTES do not teach trading.

## Headline finding

AiChart is NOT a model that was taught to trade through a large body of principles. It is two things stacked:

1. A thin prose layer (about 14 KB constitution + 13 KB chart prompt + 4 small skills, of which only one, the Pattern Atlas, is real trading teaching, about 10 KB). It teaches decision DISCIPLINE (BUY or SELL always, plan types, fill rules, stop and target construction, honesty about statistics) and a PATTERN reference.
2. A deterministic TypeScript engine (candidates, POI scoring, scalp geometry, gates G1-G7, revalidation) holding almost all the fixed numbers. That engine decides tradability, and the model never sees most of these numbers as teaching.

There is no skill on: sessions and killzones, indicators (RSI/MACD/MAs/Fibonacci/volume), macro/news interpretation beyond "check USD, Fed, yields, inflation, high-impact US events", trade management after entry (trailing, partials, breakeven), psychology, or position sizing. Those topics are essentially absent. Lonora has to author that knowledge itself.

## 1. Inventory table

Legend. Kind: P = qualitative principle, N = fixed numeric rule or threshold. Scope: G = gold-specific, X = general to any MT5 symbol. Delivery: ALWAYS = in every prompt; SEL = selected by topic scoring; TOOL = loaded on demand by a tool; CODE = engine only, the model never reads it.

| # | Piece (file) | Size | Topics | Kind | Scope | Delivery |
|---|---|---|---|---|---|---|
| 1 | Constitution `agent/workspace/SYSTEM.md` (core block shared with MCP) | 13,980 B | decision authority, plan types, fill rule, entries, exits, risk, honesty about stats | Mostly P. N: "several ATR", "~30 candles of travel", TF to style map (minute = scalp, 15m-30m = intraday, 1h+ = swing) | Framing says gold-only; the rules are X | ALWAYS (web via `canonicalIdentityCore`, MCP via core block) |
| 2 | Chart runtime prompt `src/lib/agent/systemPrompt.ts` (`CHART_ROLE_PROMPT`, the "analysis gates" and trade rules) | about 13 KB | direction, entries (fill, trendline entry, false breakout, gaps), stops, targets, news, drawing, voice | Mixed. N: touch tolerance 10-15 gold points, 15-point "still a wait" rule, "at least TWO targets", 4605.39/4601.89 worked example | G (points, XAUUSD, USD/Fed/yields news list) | ALWAYS |
| 3 | `patternDoctrine.ts` (PATTERN_IDENTIFICATION_DOCTRINE) | 1.9 KB | pattern recognition honesty | P. Catalog list only; "zero or one pattern" | X | ALWAYS (inside chart prompt and synthesizer) |
| 4 | Skill `aichart-trading` v3.0.0 | 2.1 KB (body 1.7K chars) | recommendation workflow, plan binding, prohibitions | P | G (gold only, XAUUSD tags) | SEL. `requiredTools` get_ohlc and detect_levels, TOOL via `load_agent_skill` on MCP |
| 5 | Skill `trading-strategies` v2.0.0 | 2.5 KB (body 2.1K) | evidence dimensions, immediate/anticipatory/conditional, retest as option | P, no numbers | X (tags say "forex scalping", not symbol-bound) | SEL, pinned +4 on analysis intents |
| 6 | Skill `pattern-atlas` v1.0.0 | 10.3 KB (body 9.8K chars) | patterns, stages, breakouts/false breaks, candlesticks, BOS/CHoCH/sweeps/equal highs/supply-demand/accumulation, hybrid and unclassified | Mostly P. Few N: "retraces less than half the impulse" (flag) | X | SEL, pinned +4 when the geometry engine detected a pattern; flag `PATTERN_ATLAS_V1` default on |
| 7 | Skill `cards` v2.1.1 | 3.2 KB | presentation: cards, buttons, reading order | P (UI contract, not trading) | X | SEL (category and tag match) |
| 8 | `trading/tradingPlaybook.ts` | 9 KB | 12-item evidence checklist: data quality, market open, HTF alignment, mid-range, POI exists/strength, liquidity, BOS/CHoCH, no chasing, net R:R, spread, news | Dimensions are P. Reads `SCALP_GEOMETRY.minNetTp1R = 2.5`. Weights 5-10 per item. Fails are downgraded to "warning" (never blocks) | G tuning, items X | CODE: output goes to the synthesizer as evidence |
| 9 | `trading/patternBoundaryZones.ts` | 6.2 KB | anticipatory entries from forming-pattern boundaries (trendline, channel, neckline, range edge) | N: `ZONE_HALF_ATR = 0.35`; needs trendline touches >= 2, a range with >= 2 anchors | X | CODE: emits supply/demand zones to the candidate engine |
| 10 | `trading/scalpGeometry.ts` | 11.5 KB | span and stop construction | N (see section 5) | G-calibrated, X in form | CODE (the "30 candles" prose in the prompt echoes it) |
| 11 | `trading/scorePoi.ts` | 7.3 KB | zone quality score | N: base 20; touches (untouched/1/>=3); impulse >=2 ATR / >=1 ATR; HTF confluence +15; sweep +10; BOS +15; width >3 ATR -15 or <0.1 ATR -10; distance >10 ATR -20 or <=4 ATR +5; premium/discount fit. Grade A >85, B >=75, C >=60 else reject. Tradable only A or B | X | CODE |
| 12 | `marketContext/rangePosition.ts` | n/a | premium/discount | N: >=0.95 near_high, >=0.62 premium, <=0.38 discount, <=0.05 near_low; lookback 120 bars (min 20) | X | CODE |
| 13 | `symbolProfiles.ts` | 1.5 KB | bias engine | N: lookback 50 bars, change threshold 0.6 percent | G | CODE |
| 14 | `gates/buildGates.ts` G1-G7, `newsWindow.ts`, `revalidation.ts` | n/a | news blackout, liquidity, zones, structure/MTF, risk geometry, reachability | N: news block 30 min before and 15 min after (env-tunable); target at most 25 ATR; market entry at most 0.3 ATR, waiting entry at most 4 ATR from price | G/X mix | CODE: can refuse a plan by name; the prompt says never pre-empt it |
| 15 | `quickPrompts.ts` | 0.7 KB | three Arabic buttons (analyze, news risk, manage open trades) | P | X | UI injects as a user message |
| 16 | Skill machinery `src/lib/agent/skills/*`, `mcp/src/skills/*` | about 6 files each | registry, selector, loader, user store | n/a | X | see section 4 |

Totals that matter for Lonora: the always-on text is about 27 KB (about 7k tokens) and almost entirely discipline rules. The only substantial topical teaching is item 6 (about 2.5k tokens).

## 2. Per-piece summaries

### 2.1 Constitution (`SYSTEM.md`) and chart prompt (`systemPrompt.ts`)

What it teaches. A decision contract:
- The model alone owns the analytical view (BUY or SELL, never WAIT). The platform's mandatory checks may refuse to issue the plan, and that refusal is never the model's.
- Three layers kept separate: analytical view, plan type (immediate / anticipatory / conditional), execution state (valid now / awaiting activation / expired / invalidated / blocked).
- The fill rule is part of the plan. A condition decided by a candle CLOSE must not pair with an entry that fills on a TOUCH of the same level, because after the close the touch can never happen. This is a genuinely good, general logic rule.
- A far entry is a "market view under watch", not dressed up as an entry. The plan must be reachable within its validity.
- Timeframe conflict: say which TF leads, which gives context, which times the entry. Conflict never removes the direction.
- Stop = structural invalidation PLUS a volatility buffer, never exactly on the level. At least two targets; the first sits on a REAL swing, not "the first minor shelf".
- Reward:risk is descriptive, not a minimum. Risk per trade is R-expression, never sizing.
- Statistics honesty: quote a win rate only from a calibrated record with an adequate sample, else say the plan rests on direct analysis and quote no percentage. ("a win rate over a handful of trades is noise with a decimal point.")
- Chart prompt adds: review the live chart before and after proposing levels; false-breakout, retest-after-real-break, rejection candles, supply/demand confluence, gaps and news named when they apply; a trendline tag can itself be the entry (say whether from the break or from the retest); draw the zone at the candle that printed the condition; no candle chasing; news only before or after an event; "do not assume price will return to retest the same zone" (default one touch, maybe one more attempt).
- Voice: answer first, own an opinion ("I lean buy while price stays above X" is hedged, "may go up or down" is evasion), no filler, use conversation history, quote real numbers.

Good parts:
- The three-layer separation, the fill-rule logic, the "evidence never selects the side" framing and the statistics honesty rule.
- The voice section is excellent and fully reusable.
- It is explicitly designed so rules do not become a hidden policy engine ("do not count confluences, apply fixed score thresholds").

Weak parts:
- "Never answer WAIT" is a product decision that forces a direction in chop. It is the opposite of an expert who knows when not to trade. Lonora's mandate (agent with authority, real money) likely needs "no trade" as a first-class outcome.
- Fixed gold numbers leak into prose: touch tolerance 10-15 points, the 3.5-point worked example, "not 0.5 ATR or 5 points". These are point-denominated and wrong for any other symbol.
- The prompt references a "mandatory chain" the model must not pre-empt, which is deliberate but means the model gets no calibrated feel for what will be refused.
- Prompt is a rule list with no worked reasoning examples beyond one production counterexample.
- No teaching of sessions, volatility regimes, news interpretation, trade management, or psychology.

### 2.2 `patternDoctrine.ts`

Teaches identification honesty. Names a closed catalog (classic 21 shapes, 18 candle patterns, 6 harmonic: Gartley, butterfly, bat, crab, shark, AB=CD), "zero or one pattern", "no clear pattern is valid", detector hits are hints, and never default to inverse H&S "because it is a common gold template" (a real production failure). Good: the anti-confirmation-bias rule; use it. Weak: the catalog is a closed list with harmonics that the atlas does not actually explain; "do not invent a family outside it" is needlessly restrictive.

### 2.3 Skill `pattern-atlas` (the real knowledge)

Structure: framing (aid not gate, 3 rules), stage table, chart patterns, breakouts/retests/false breaks, candlesticks, structure and liquidity, hybrid structures, unclassified structures.
- Framing rules: a pattern is not required for a recommendation; never force a template; a structure still forming is not "nothing yet" (its boundary is often the best entry, at higher risk, said out loud).
- Stage model (deterministic detector feeds it): starting, forming, near_completion, completed_unconfirmed, confirmed, failed, each mapped to a typical plan type. "Failed" is itself a signal, often the other side.
- Each pattern entry has the same schema: how it forms, what confirms, what fails it, entries (anticipatory / on break / conditional on retest), target projection (height from break, flagpole height), "weak when".
- Distinctions worth keeping: break = CLOSE beyond a level, a wick is a sweep; false break (close that reclaims) is one of the strongest reversal signals, stop beyond the extreme; retest is one option among five, say why; mid-range is a poor immediate entry but a plan waiting at an edge; each additional touch usually weakens a level (triple top, zone retests); equal highs/lows are targets as often as barriers; hammer vs hanging man differ only by the prior move; candles matter at levels, not mid-range; sweep alone is not a trade, sweep plus structure shift usually is; BOS vs CHoCH/MSS; supply-demand first return is the cleanest test; hybrids and unnamed structures are described from primitives (highs/lows, defended side, resting liquidity, impulse origin) and the entry and stop come from the LEVEL not the label.
Good: schema consistency, the formation-stage idea, honest handling of unclassified structure, anti-template stance.
Weak: it is only about chart shapes plus a small SMC glossary. Classical patterns are statistically weak on their own and the atlas does not say so. Targets are textbook measured moves (fixed-style rule, "height projected from break"). No instruction about how a pattern's reliability depends on context (trend, session, HTF). Detector-dependent ("Detection is deterministic and arrives with each analysis") so the text assumes a geometry engine Lonora may not have. The web loader truncates it (see 4.3).

### 2.4 Skill `trading-strategies`

Teaches the evidence dimensions (regime and structure, entry context, confirmation context, level construction, stage of move) and the three plan types with concrete examples of anticipatory entries (rising lows inside a triangle, second rejection before neckline, range edge, post-sweep). "A retest is one option among several, never a rule to wait for" with the five alternatives. Ends with the anti-rule statement: no confluence counting, no minimum R:R, no automatic side blocking. Good and fully general. Weak: very short, descriptive not instructive, nothing about HOW to judge regime or when momentum makes a deep retest unlikely.

### 2.5 Skill `aichart-trading`

A restatement of the constitution as a 5-step workflow plus prohibitions (no order tools, no balance or lots, no other markets). Mostly redundant with items 1 and 2; its content is product policy, not trading knowledge.

### 2.6 Skill `cards`

Pure presentation contract (recommendation-card, live-chart, reading order, chat-only buttons, "a gate refusal is a named checklist, not a weaker ticket"). Not trading knowledge. Only the reading order (decision, levels, activation, invalidation, alternative scenario, checklist) is a transferable communication structure.

### 2.7 Engine pieces (`tradingPlaybook`, `scalpGeometry`, `scorePoi`, gates)

These encode the real numeric trading logic (section 5). Notable: `tradingPlaybook` turns its own failures into warnings and returns `blockingReasons: []` always ("Evidence summary only"), so it is a vocabulary of what to look at, not a gate. The checklist dimensions are the useful part: data sufficiency, market open and freshness, HTF alignment or reversal evidence, not mid-range, valid POI and its strength, liquidity context, BOS/CHoCH confirmation, not chasing, net R:R after costs, spread relative to stop and ATR, news risk. `scorePoi` is a decent zone-quality heuristic (impulse origin, freshness, displacement, HTF confluence, sweep, structure break, width sanity, distance, premium/discount fit).

## 3. Numeric rules and thresholds (quoted)

Prompt-level (the model sees these):
- Touch tolerance 10-15 gold points; a sell more than 15 points above entry is a genuine wait.
- First target "several ATR from entry (on the order of 30 candles of travel)"; at least 2 targets, a third when structure offers one.
- TF to style: minute = scalp, 15m-30m = intraday, 1h and above = swing.
- Flag retrace under half the impulse (atlas).
- Worked example 5m XAUUSD SELL entry 4605.39 / live 4601.89.

Engine-level (model never reads):
- `SCALP_GEOMETRY`: minNetTp1R 2.5; preferred TP2 4-5R; slippage = 0.5 x spread; immediate if within 0.4 ATR; conditional up to 4 ATR; reject beyond 8 ATR.
- `TRADE_SPAN` (ATR multiples): scalp TP1 3.5 / TP2 6 / stop buffer 0.5 / min stop 2; intraday 4.5 / 7.5 / 0.6 / 1.5; swing 6 / 10 / 0.75 / 1.2.
- Gates: news block 30 min before and 15 min after; max target distance 25 ATR (calibrated on "targets run 3.8-5.0 ATR"); market entry max 0.3 ATR, waiting entry max 4 ATR.
- POI score and grade A >85, B >=75, C >=60; zone half-height 0.35 ATR; premium >=0.62, discount <=0.38 of a 120-bar range; bias 0.6 percent over 50 bars; checklist weights 5-10.
All are marked in comments as "documented starting point, not a measured constant" or incident-driven (e.g. the 113-ATR target incident). None is derived from backtests; the backtest apparatus was deleted.

## 4. How knowledge reaches the model and skill selection

### 4.1 Always in the prompt
Constitution core block, chart role prompt, pattern doctrine, voice section. On MCP the same core text plus an MCP-core paragraph (session start order: get_agent_capabilities, get_agent_settings, resolve_agent_skills, load_agent_skill once per selected skill, then await the operator).

### 4.2 Selected by topic (web path)
`src/lib/agent/skills/skillContext.ts` + `skillSelector.ts`, called twice in `orchestrator.ts` (before candles exist, then again with `detectedPatterns` once geometry ran).
- Candidate pool: `agent/workspace/skills/*/SKILL.md` frontmatter only (16 KB header read) plus the operator's own DB skills as virtual descriptors (catalogue names win a collision).
- Hard filters: enabled, `supportedLocales`, `allowedMarkets` (market hard-coded "forex"), `requiredTools` all available (orchestrator passes render_cards, detect_levels, get_ohlc), `forbiddenTools`, execution-risk skills rejected, atlas gated by feature flag.
- Scoring is keyword overlap, not model choice: request tokens (>=3 chars, stopwords removed, digits dropped, plus intent strings and detected pattern names) against skill tokens (category + riskLevel + description + tags + name). Exact match = 1; 4-letter prefix match = 1 (stem-lite). Intent contains category (or reverse) = +3. Market soft boost = +1 only if score already >0. Atlas gets +4 when patterns were detected. `trading-strategies` gets +4 when any intent matches `analysis|analyz|trade|chart|market|recommend`.
- Selection: sort by score then name; keep those within 50 percent of the top score (min 1); cap 3 system slots (4 when the user has skills). Hard cap max 4.
- Loading: per-skill body capped at 9,000 chars, total 16,000 chars, injected as "# Loaded skills (advisory guidance only)" with "(user-provided)" and "(truncated)" labels. Failures are reported, never faked. Feature flag `agentSkillsV1`.

### 4.3 Problems seen in the selector and loader
- Truncation bug: `pattern-atlas` body is 9,805 chars and the web cap is 9,000, so on the web path the tail (end of structure/liquidity and the entire hybrid and unclassified sections) is cut. The MCP loader cap is 20,000 so MCP is unaffected. The two doctrines that most carry the "do not force a name" principle are exactly the cut part.
- Arabic requests: skill metadata is mostly English tokens (only a few Arabic tags), so selection of Arabic requests leans on intents; the MCP resolver explicitly defaults effective intents because "an Arabic request with no declared intents scored zero".
- Pure lexical scoring means selection can miss (a question about "stop loss placement" matches almost nothing) and pins (+4) exist only to patch alphabetical tie-break evictions. The code comments say so.
- Web and MCP selectors are two copies of the same logic (kept "in parity" by hand).

### 4.4 Loaded on demand by a tool (MCP path)
`mcp/src/skills/catalog.ts`, `select.ts`; tools `list_agent_skills` (metadata only), `resolve_agent_skills` (request, intents, locale, market, max_skills 1-4, default 3; returns selected, rejected with reasons, candidate scores), `load_agent_skill` (full body, cap 20,000 chars, explicit error if missing or empty, never pretends a listed resource was read). Visible skill resources are stubs saying "this URI is not a loaded skill". The model is told to resolve at session start and load each selected skill once, re-resolving only when the topic changes. So on MCP the model chooses what to load from a scored shortlist.

### 4.5 User-skill store
`userSkillStore.ts`: per-user rows in `user_agent_skills`; one SKILL.md per skill, name kebab-case, max 100 KB each, max 12 per user. Hard rails: trust always "user", riskLevel capped at analysis (execution rejected on save and again in the selector), `requiredTools` ignored. Enabled user skills join the web selector; body is injected with "(user-provided)" and a note that it never grants permissions. REST at `src/app/api/skills`. Note the 100 KB store cap vs the 9 KB injection cap: a large user skill is silently truncated to 9 KB on the web path.

## 5. What Lonora should take

### 5.1 Take as principles (general to any MT5 symbol)
1. Decision discipline in structured form: view, plan type, execution state as separate layers; plan type definitions (immediate, anticipatory, conditional) with the "retest is one option among several" teaching.
2. The fill-rule consistency rule (close-condition never paired with a touch fill of the same level).
3. Reachability: an executable plan is one the market can reach within its validity; otherwise it is a watch, not an entry.
4. Level construction: stop at the structural invalidation plus a volatility buffer; targets at real structure that spans a real swing of the timeframe; at least two targets; state both structural and protected stop.
5. Evidence dimensions as a vocabulary: regime/structure, location (premium/discount, range edge), liquidity (equal highs/lows, sweeps), confirmation (BOS/CHoCH, rejection), multi-timeframe (leading vs context vs timing), cost (spread and slippage vs stop), news, data freshness.
6. Pattern atlas: formation stages, break = close, false break as reversal signal, retest and level decay with touches, hybrid and unnamed structures from primitives, anti-template stance, "pattern not required".
7. Statistics honesty and no invented data. Voice rules (answer first, own an opinion, use history, real numbers).
8. Zone-quality factors from `scorePoi` as qualitative factors: origin impulse strength, freshness (touches), HTF confluence, liquidity taken before, structure break after, width sanity, distance, premium/discount fit.
9. Quality of the `trading-strategies` evidence-catalogue idea: dimensions as "what to look at", never a count.
10. Anti-confirmation-bias doctrine from `patternDoctrine` (do not stamp a favourite template).

### 5.2 Rewrite as principles instead of fixed numbers
| AiChart fixed rule | Rewrite as |
|---|---|
| Touch tolerance 10-15 gold points; "through by more than 0 is printed" | "Judge fill against the instrument's own noise: spread, typical candle range, and the cost of being a few ticks off." Express in ATR or spread terms the agent computes live, never points. |
| Entry to market within 0.3 ATR; waiting entry within 4 ATR; reject beyond 8 ATR | "An entry is actionable only if price can plausibly reach it before the idea expires; far levels stay as a watch." The agent measures reach from current volatility and the plan's validity. |
| TP1 at least 3.5/4.5/6 ATR, stop buffer 0.5/0.6/0.75 ATR, min stop 1.2-2 ATR | "Targets sit on real structure a real swing away; the stop sits beyond invalidation with room for ordinary noise; neither is stretched or squeezed to improve the ratio." Let the agent derive buffers from recent ATR/wick behaviour and note the reasoning. |
| minNetTp1R 2.5, TP2 4-5R | "Compare reward to risk after costs, and ask whether the move is worth taking; no universal minimum." Make the agent state the net ratio and judge it against how likely and how far the target is. |
| News block 30 before / 15 after | "High-impact events reprice instantly and widen spreads; decide per event whether to stand aside, trade after, or reduce exposure, and say why." Event impact varies by instrument and event type. |
| POI score thresholds (A > 85, B >= 75) | Keep the factors, drop the points and grades. |
| Premium >= 0.62 / discount <= 0.38 of 120-bar range; bias 0.6 percent over 50 bars | "Locate price within the relevant dealing range; trend and bias are judged from structure, not a percentage over a fixed window." |
| TF to style map (minute = scalp ...) | "Match plan style and management to the timeframe of the decision; the higher timeframe leads, the lower one times." |
| Gold point denominations and worked example | Use R, ATR, spread-relative and percentage units plus a worked example per asset class generated at runtime. |
| "Never answer WAIT" | Replace with "the agent may decide not to trade, and states the condition that would change its mind." This matches Lonora's authority model and is the most important rewrite. |

### 5.3 What AiChart lacks that Lonora must author (the "expert trader" gap)
No coverage of: session behaviour (Asia/London/NY, rollover, spread widening, killzone-style liquidity runs), volatility regimes and when to stand down, indicators (as context, not signals), correlation and macro drivers per asset (USD, yields, risk sentiment; oil for energy; etc.), news interpretation and positioning, trade management (partials, breakeven, trailing, scaling, time stops, what to do when thesis changes), position and portfolio risk (exposure, correlation, daily loss behaviour), psychology and discipline (revenge trading, overtrading, FOMO, stop-moving), journaling and review loops, execution realities (slippage, requotes, weekend gaps, swap). Recommend authoring these as small topic skills with the same schema the atlas uses (what it is, how to recognise, what confirms, what invalidates, how to enter and manage, weak when) and no embedded constants.

### 5.4 Mechanism lessons
- Keep skills as lazily loaded markdown with frontmatter (name, description, tags, riskLevel, locales, allowed markets) and hard rails: user skills are never allowed to grant permissions or raise trust.
- Do not copy the pure keyword scorer with +4 pins. Prefer model-chosen loading from a short catalogue (name plus one-line description) via a load tool, as the MCP path does, with a small always-on core. Make descriptions bilingual so Arabic requests match.
- Avoid the size-cap mismatch: define one cap for store, selector and loader, and test that every shipped skill fits it.
- Keep the honesty design: a failed load is reported, a listed skill is not treated as loaded.
- Keep gate-style factual refusals separate from knowledge: knowledge should inform judgement while any enforced limits live in code with their own explanations.
- Add worked, scenario-style examples and reviewed corrections (as `patternDoctrine`'s inverse-H&S fix and the 113-ATR target incident show) as a feedback loop for the knowledge base.
