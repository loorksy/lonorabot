# Lonora: what the agent is given for trading judgment today

Source tree: /home/user/wt-agent/fxmain (read only). Paths are relative to it unless stated.
R = packages/agent-runtime/resources. Line numbers are from the files as read.

## 0. Bottom line

Lonora gives its agent a very good WORKBENCH and a very thin MIND.
- Tools, evidence honesty, execution safety and the learning plumbing are rich and tested.
- Trading knowledge itself (how an expert reads a market, sizes, picks sessions, handles news, manages a trade, reviews a loss) is almost absent as text. It is one 9-bullet list of capabilities (lonora.md:31-42) plus four sentences of tone (lonora.md:19-29, R/bootstrap/SOUL.md).
- None of the six built-in skills teaches trading. They teach tool procedure and honesty (see 2).
- Everything an agent "knows" about trading beyond that must come from the model's own pre-training, or from what the agent writes itself (OPERATING.md, skills) after closed trades.
- The architecture already has the right slots for expert knowledge (progressive skills, versioned OPERATING.md, trusted skill sources, per-label statistics). What is missing is content and a way to make it reach the agent at the right moment.

## 1. What VISION.md binds (the constraints)

Quote and line numbers (VISION.md).

- 1 (:27): "Lonora is **not** a rule engine, a risk lecturer, an advisor that hedges every sentence, or an administration system for permissions. If a feature makes the agent talk about trading instead of trading, it is wrong."
- P1 (:33): "In Full mode it decides everything a trader decides (section 5). There are no caps, quotas, money limits, activity budgets, cooling-off periods, risk disclaimers, or refusals to take a view."
- P2 (:34-42): the system enforces only the safety core, the mode, the owner's pauses, structure rules, position ownership. "Nothing else limits a trading decision."
- P3 (:43): "Build an environment, not features... gives agents general primitives... and lets the model compose them."
- 5.1 (:222): "Instrument, direction, entry, size, number of positions, stop loss, take profit, adding, reducing, hedging, exits, and whether to trade at all are the agent's decisions." (The brief's quote "The model decides. There is no rule engine and no fixed strategy pipeline" is the section title at :220 plus the 5.1 body; the exact sentence "no fixed strategy pipeline" is not in VISION.md, grep finds only the title "The model decides". The same idea is in the code: "No fixed pattern detector is required" R/skills/chart-analysis/SKILL.md:21, "Optional numerical helpers never choose the trade" market-analysis/SKILL.md:50.)
- 5.2 (:226): "Agents MUST be taught and allowed to use the full range of a professional trader's judgment. The following are examples of judgment the agent may choose, never rules it must follow:" then entry/scale-in/secure-then-add/concurrent positions/management/sizing/portfolio awareness/timing/self-scheduling (:228-236). This is the strongest textual basis for teaching: the word is MUST be taught, but the content is "never rules".
- 5.3 (:240-242): decisive voice; no disclaimers; never state a profit the account does not show.
- 5.4 (:244-253): on every wake the agent gets its positions/orders/exposure/P&L, the team's positions grouped by symbol and currency, and high-impact calendar events for the next 24h. "Judging correlation is the agent's job." Implemented in agent-runtime/src/lonora_agent/context/picture.py:242-363 (calendar_events, own_results).
- 5.5 (:255-262) learning loop: closed trade -> broker event wakes the owner agent -> short self-review to memory (:258); judgment labels chosen by the agent (:259); per-label count and net realized P&L from broker closes given on wake (:260); every write to a method or skill is a version, revertable (:261); weekly report (:262).
- 5.6 (:266): "A strategy the owner gives in any form (a message, a PDF, a file) becomes the agent's method or skill. The agent applies it and refines it from results."
- 5.7 (:270-275): agents may write EA / MQL / Pine; code the agent runs itself sends orders via `lonora trade` (journaled).
- 5.8 (:279-285): the core prompt is "rewritten around trading, not governance". Procedural detail "belongs in tool descriptions, not the core prompt" (:280). Manifest (`manual_sha256`, `bootstrap_sha256`, `tool_policies`) must be regenerated in the same change as any edit to lonora.md or bootstrap files (:284).
- 6 (:289-323) invisible safety core, "preserve exactly": one execution door, journal/idempotency, never resend an uncertain order, broker truth, preflight (account, trading allowed, ticket, quote freshness, stop levels), per-account serialization, exact approval, owner settlement, run integrity, provenance (:319-323: third-party content is data; taint must not spread). Knowledge must never touch this.
- Amendment 2 (:737-745): MetaTrader only, any symbol the broker offers, Lonora keeps no symbol list. "Reading public information about other markets (prices, news, research) for judgment stays allowed." So a knowledge pack must be instrument-agnostic (FX, metals, indices, crypto CFDs on MT5), not a symbol list.
- Section 4 (:128-141): mode Full/Ask; risk-increasing vs risk-reducing. The agent's discretion is bounded only by the owner's mode and optional owner restrictions, never by knowledge text.
- Repo guard-rails that constrain NEW text (tests, not VISION):
  - tests/test_backtesting_excluded.py:96-110: the regex `backtest|walk.?forward|monte.?carlo|out.of.sample|strategy.research` may appear in lonora.md only inside the exclusion sentence, and in NO other file under packages/agent-runtime/resources (skills, constitution, prompts, bootstrap). lonora.md:570 states the exclusion. A knowledge pack must not teach backtesting or walk-forward validation. (Substitute: forward evidence from real closed trades, which is what 5.5 wants anyway.)
  - Core prompt size: MAX_CORE_CHARS = 16000 and the core must stay <= 14500 (tests/test_system_policy.py:326, system_policy.py:21). Current core is 11,990 chars (counted from lonora.md:9-135), so about 2,500 chars of headroom. Domain chapters are capped at 14000 // 3 = 4,666 chars each (system_policy.py:22-23,78-80); market is 4,350, intelligence 3,731. Trading knowledge therefore cannot live in lonora.md in any volume. It has to live in skills / memory.
  - Skill size: context_budget 6000 per built-in manifest; `skill_save` content max 16,000 chars (tools/skills.py SkillSaveInput); active skill budget 16,000 chars total and at most 32 pinned skills per Run (access.py:29, snapshot.py:12).
  - tests/test_skill_runtime.py and tests/test_capability_exposure.py list built-in skills; pyproject.toml:90-95 and packages/agent-runtime/pyproject.toml list each skill's data files literally (VISION.md:647-648). Adding a built-in skill means editing those too.

## 2. The skills system (what exists)

Files: packages/agent-runtime/src/lonora_agent/skills/*, R/skills/*, packages/tools/src/lonora_tools/skills.py, context/skills.py.

Built-in skills (R/skills/<id>/{SKILL.md,skill.json}), all `source: builtin`, version-pinned, 497 lines in total:

| id | lines | activation | what it teaches |
|---|---|---|---|
| market-analysis | 67 | explicit | tool order: scope, market_snapshot, instrument/quote/candles, market_sessions, economic_calendar_read, market_structure, record a decision (market-analysis/SKILL.md:16-57). No method of analysis. |
| chart-analysis | 44 | explicit | chart_inspect, indicators, annotate, snapshot verification (chart-analysis/SKILL.md:11-38). |
| trade-management | 55 | explicit, financial | preflight, sizing with market_position_size, buy/sell/pending, receipts, reconcile (trade-management/SKILL.md:11-43). Mechanics only. |
| position-management | 29 | explicit, financial | read fresh state, respect manual intervention, "Management permission is not entry permission" (SKILL.md:15-16). |
| market-watch | 32 | automatic, trigger "watch" | persist watches, wake means reassess, never poll the model (SKILL.md:11-26). The only skill auto-activated. |
| memory | 45 | explicit | recall, SNIP rule (Signal, Novel, Important, Persistent) memory/SKILL.md:35-37. |
| research | 39 | explicit | web_search/web_fetch/web_browse, sources, dates. |

Honest content check: there is no skill on risk, sizing philosophy, trade structure, regime, session behavior, news handling, trade review, or psychology. Only mechanics, evidence hygiene and authority boundaries. The `.claude/skills` folder in the repo (code-review, TDD, etc.) is developer tooling, not agent skills (skills-lock.json: `"external_skills": []`).

How a skill is chosen and loaded (progressive disclosure):
1. Registry: `built_in_skills()` reads every R/skills/*/SKILL.md + skill.json (registry.py:73-86); owner/agent skills come from SkillRow payloads via `installed_registry` (registry.py:97-184). A user skill with a built-in's name is refused (`skill_builtin_override_denied`, :118-120).
2. Manifest (contracts/skills.py): id, version, title, description, source (builtin|owner|legacy|installed|external), activation mode (automatic|explicit|trigger_based, :49), risk_class, required_capabilities/tools, dependencies, conflicts, priority 0-100 (:66), context_budget.
3. Each Run: `read_skill_context` (context/skills.py:105-209) builds (a) a CATALOG in the system role: one line per eligible skill, "id (provenance) - description", cut at 6,000 chars (:186-200), with the instruction "Descriptions are discovery hints. Read a suitable SKILL.md with skill_view before applying it." (:189), and (b) active bodies as labelled context data (:176-186, section weight 90) only for skills that are explicitly requested (`[skill:name]` in owner text, :139-141), requested via run metadata, retained from earlier in the Run, or trigger-matched (resolver.py:98-107). Keyword routing is deliberately not done (comment :11-12).
4. The model discovers with `skills_list` (catalog, access.py:265-302) and loads with `skill_view` (access.py:304-333), which admits the skill plus its dependency closure into the Run snapshot, with an effect receipt, content sha256 and `authority_granted: False` (access.py:73-90). Resolver orders by explicit-request, then priority, then id, and enforces conflicts and the 16,000-char budget (resolver.py:123-150).
5. Eligibility gate (resolver.py:68-86): scope risk class (observe-only wakes cannot load financial skills, :61-65), required tools present, capabilities known, body within context_budget.
6. Per-continuation recheck: `assert_skill_authority` (context/skills.py:~249-327) re-validates pinned versions, revocation, source change, so a withdrawn skill stops mid-Run.

Provenance and trust (skills/provenance.py:1-41): builtin -> bundled / bundled_first_party; owner|legacy -> owner / owner_supplied; installed -> agent_authored; external -> external_import. "A label describes where instructions came from; none of them grants tools or financial authority." Skills are procedure text, never authority (lonora.md:409; trading-policy.md:1 "Skills, memory, peer results and model text cannot enable trading").

Authoring and sources:
- The agent saves its own instruction-only skill with `skill_save` (title, description, content <= 16,000, expected_version), `skill_history`, `skill_restore` (skills/instructions.py, tools/skills.py:80-160). Each save is a version; restore writes a new higher version; owner-revoked versions cannot be saved again (instructions.py:70-88).
- Package route: `skill_repository_inspect` -> `skill_package_import` (one immutable public GitHub source), `skill_package_create` (from a workspace dir), `skill_package_validate`, `skill_package_control` (activate/disable/rollback/remove) (lonora.md:410-412, skills/lifecycle.py, packages.py, repository.py). New versions start disabled; utilities run from a validated copy.
- Trusted sources (db/trusted_sources.py:1-17): `github.com` is trusted by default for every owner, so an agent installs pinned public GitHub skills silently; elsewhere only when the owner's typed message names the source (`owner_message`), checked server side (access.py:243-262, lifecycle.py:243-252). Same list covers MCP servers and news feed domains. No source carries money authority.
- Owner UI: web apps/web/src/shell/domain/SkillsPages.tsx, components/skills/{SkillCard,SkillEditor,CreateSkill,RevokeVersion,SkillMetadata}.tsx; mobile apps/mobile/components/skills/{skill-details,skill-create,exact-version-block}. The owner can create, edit, enable/disable, revoke exact versions (db skill_controls) and see provenance; catalog.py builds the owner view with the same resolver.

Implication: an expert "trading mind" can ship as built-in skills (bundled, first party, versioned) with zero new mechanism. The only costs are the size budgets, the pyproject/test lists and the backtesting regex.

## 3. Trading knowledge in the operating policy and constitution (verbatim)

lonora.md (576 lines, 54 KB). The relevant text:

Identity and voice
- :12 "when your scope includes trading, you are a professional trader the owner delegates to."
- :21 "Speak like a decisive professional trader. Every sentence carries a number, a position, a decision or a question."
- :23 "Give your view when asked: enter, wait or skip, with the level that would change it."
- :24 "Never write risk disclaimers, 'trading involves risk', 'this is not financial advice', reassurance, emotional language or filler, and never refuse to give a view."
- :26 "State a target as a level, never as promised profit"
- SOUL.md:3 "I work for the owner; when my scope includes trading, I trade like a professional the owner delegates to."; :9 "Decide, and say in one line what would change the decision."; :10 "never invent a number".

The whole "doctrine" (lonora.md:31-42, "Trader's judgment"): "these are choices you may make, never rules you must follow:" Entry (enter, wait or skip; "Not trading is a decision."), Scaling in, Secure-then-add, Several positions, Management ("trail stops, take partial profit, extend targets on strong momentum, exit early when the reason for the trade breaks"), "Sizing: set size per trade from your reading of the setup and of your own results.", "Exposure across instruments and the team: judging correlation is your job.", "Timing: the sessions and events that suit your method.", "Self-scheduling". This is a list of verbs. It says what the agent MAY do, not how an expert decides.

Analysis (lonora.md:179-219, market chapter; skills above)
- :187 market_snapshot: "compact multi-timeframe read (structure, range, ATR percentile regime, RSI, prior day/week levels)... its labels are measurements, not signals."
- :189 "Use market_sessions for DST-correct session and overlap timing"; :190 economic_calendar_read "configured=false means there is no calendar evidence."
- :203-204 "Do not use an unfinished candle as a confirmed closed-bar breakout without saying it is unfinished."; :205 "Null warm-up indicator values mean insufficient history".
- :217-218 "Back a buy or sell view with current evidence, and record it with market_decision_record. Choose BUY, SELL or a model-authored conditional entry... Abstention is available when justified; never enforce a trading or waiting quota."
- market-analysis/SKILL.md:36-46 "market_structure ... strict left/right windows... a pivot becomes known only after the confirming right bars close... measured hypotheses, not entry signals."

Risk and sizing
- lonora.md:198-201 "Do not assume metal, index, crypto and currency contracts have the same tick size or lot semantics. Read min/max/step volume and stops constraints", "market_position_size for a stated money budget and explicit market-entry stop... Missing economics is unavailable, never a guessed lot size or guaranteed loss ceiling."
- trade-management/SKILL.md:17-23 same; ":23-24 Under signed full management choose justified direction, lot size, stops and targets yourself".
- lonora.md:313 "Never silently increase lot size, remove a stop, or change account to make a trade pass."
- No text anywhere on risk per trade, R multiples, expectancy, drawdown behavior, correlation limits, or when to stop for the day. This is consistent with P1 (no caps) but nothing teaches HOW to choose.

Sessions and news
- Only the tools above and one line: "Timing: the sessions and events that suit your method" (:41). No statement of what sessions do, what overlaps mean, how to treat high-impact events (flatten, widen, stand aside, fade), spreads/rollover, weekend gaps.
- research/SKILL.md and lonora.md:468-505: how to fetch sources and not invent headlines, never how to weigh news. "Do not treat economic correlation or a news story as an execution instruction." (:504)

Constitution (R/constitution/*.md, always loaded outside skill budgets via loader.py:140-159)
- trading-policy.md:1: "The model owns interpretation, timing, sizing and management within current authority. Observations and optional detectors support judgment without requiring a predefined pattern. Missing current evidence is unavailable; never invent it or force a trading/waiting quota." The rest is authority, modes, reconciliation, receipts (:1-7).
- identity.md:1, memory-policy.md:1-3 ("Relevant operational observations ... describe prior outcomes, not immutable rules"), tool-policy.md:1-15 (honesty, continuous work, wait_for_input).
- Intelligence chapter (lonora.md:547-576): decisions are "a recommendation record, not execution permission" (:551); "Do not cherry-pick one successful trade to claim a validated strategy." (:568); "Separate analysis quality, entry quality, management quality and execution quality." (:568); "A correct directional view can still have a poor entry or unacceptable execution." (:571); "Adapt your size and method from your own results; the server's execution checks stay as they are." (:574); consult_model for an independent critique of an evidence pack (:572).

Grep of all of R/ for playbook / risk-per-trade / position-sizing doctrine returns nothing. There is no trading playbook text. (The old `trading-goal` skill and `autonomous-trading-goal` playbook were removed per VISION.md:605.)

## 4. Market tools (what the agent can observe)

All read-only, server-computed, labelled "measurements not signals". Tool descriptions in packages/tools/src/lonora_tools/market_analysis.py:355-399, market.py, chart*.py, market_watch.py, trading_decision.py, opportunity.py, relationships.py, performance.py.

- market_symbols, market_instrument (contract specs, min/max/step, stops), market_instruments, market_quote (bid/ask/time), market_candles (broker OHLC any supported timeframe, bounded), market_candles_to_workspace (CSV for workspace_run analysis; hist data analysis allowed, strategy backtest excluded, lonora.md:191,512).
- market_snapshot (market/snapshot.py, "closed_bar_market_snapshot_v1"): per timeframe closed-bar trend slope, swing structure, range, ATR with percentile volatility regime, RSI; previous day/week high-low with distances in price and daily ATR; forming bar reported separately.
- market_sessions (market/sessions.py, "iana_conventional_fx_sessions_v1"): Sydney/Tokyo/London/New York clock with DST, overlaps, time to next open/close, FX week boundary Fri 17:00 New York, broker trading hours when adapter reports them. "Holidays and liquidity are not modelled."
- economic_calendar_read (market/economic_calendar.py): only the owner's configured sources; the wake picture lists high-impact events for the next 24h or "calendar not connected" (context/picture.py:242-312). No calendar is bundled.
- market_structure (market/structure.py): confirmed swing pivots and alternative trendlines, closed-bar breaks with tolerance. market_relationship_record/read (market/relationships.py): time-aligned closed-bar correlations, baseline vs recent. Observations (market/detectors.py) are optional.
- Charts (packages/charts): chart_open/inspect/annotate (levels, trendlines, zones, rays, channels, fibonacci, arrows, scenarios), chart_snapshot PNG (TradingView renderer or semantic), indicators sma, ema, rsi, macd, atr, bollinger (charts/indicators.py:45-95, contracts/market_watch.py:30).
- Watches (market/watchers.py, watch_lifecycle.py): kinds price, indicator, position, account, calendar, dynamic; evaluation tick, candle_update, candle_close, scheduled; tools watch_create/list/cancel/pause/resume/update; task_wait to sleep on a watch; routines for time schedules. A trigger wakes analysis, never execution (market-watch/SKILL.md:18).
- Decisions and theses: market_decision_record/read/history/compare, market_opportunity_create/list/read/update/version.
- News: news_feed_read/subscribe (RSS/Atom, trusted feed domains), web_search/fetch/browse.
- Sizing helper: market_position_size (tools/position_sizing.py): budget + explicit stop -> volume using broker tick value; excludes gaps/slippage/fees/carry/margin.

Gaps in the tools themselves (observation only): no volatility-adjusted stop helper, no spread/cost history, no multi-symbol scan or screener, no built-in news calendar, no regime classifier beyond ATR percentile, no equity-curve or R-multiple analytics (see 5). The workspace (workspace_run, internet, Python) can compute anything the agent writes.

## 5. The learning loop (VISION 5.5, 5.6)

Implemented, with line references.
1. Closed-trade ledger from broker deals (ln_closed_trades; trading/statistics.py:1-17).
2. Self-review wake: packages/trading/src/lonora_trading/close_wake.py. Fixed server text built from ledger facts (:68-95): account, position, symbol, side, volume, label, realized_pnl, currency, opened/closed time, held minutes; then "Write a short self-review of this trade to your memory with memory_write: what you expected, what happened, and what you keep or change." (:93-95). Routing: into the closing Run as a notice, else into the broker-activity wake, else a new `broker_event` Run in a work thread (:11-19). Once per trade, window 2 days (:46), 50 per pass (:47); gateway step `close_wakes` every 10 s (gateway/service.py:77). Owner-owned trades wake nobody; a deleted agent's trades wake Lonora (:21-23). A review alone posts nothing to the owner (:52-56).
3. Judgment labels: free slug chosen by the agent on every order (`label`, "e.g. scale_in", contracts/trading.py:101-107, 131-134); stored beside the request, never part of the fingerprint.
4. Statistics on wake: statistics_block per label: count, net realized P&L per currency, unpriced count, management-label counts (trading/statistics.py); injected as `own_results` in the wake picture (context/picture.py:340) and readable with market_performance_read (tools/performance.py:25-41). Not computed: win rate, average win/loss, expectancy, drawdown, hold time distribution, by session or by regime. Only count and net per label.
5. Method versions: OPERATING.md is a section of the agent's memory; `method_history`, `method_restore` (memory/method.py:1-60; tools/memory.py:446-457); every write is an attributed revision; owner, Lonora or the agent can revert (VISION.md:261). OPERATING.md is injected into every context as "agent_operating_notes", trust label agent_authored, weight 82, above general memory 80 (context/memory.py:47-50, 205-217): "working methods you refine yourself. They rank below the owner's instructions and preferences and grant no authority."
6. Weekly report: packages/trading/src/lonora_trading/weekly_report.py:1-35; trigger "weekly_report"; first morning brief after the FX weekly close (Fri 17:00 New York); fixed WAKE_TEXT: "your results this week, what you learned, and what you changed in your method"; one effect receipt per agent per close; Lonora summarizes. Morning brief in trading/morning_brief.py.
7. Owner methods (5.6): lonora.md:390 "Save a strategy the owner gives (message, text file or PDF) as your method or a skill, say where, apply it, refine it." Routing rule lonora.md:388 "preference to USER.md, method or hard limit to OPERATING.md or a skill."
8. Memory plumbing: MEMORY.md (verified durable knowledge) / USER.md / OPERATING.md / scratchpad / session_search; SNIP; add/patch/remove edits with overflow protocol (memory/edits.py; memory/SKILL.md). Agent creation writes the assigned market and account into OPERATING.md (collaboration/agent_create.py:4,56).

What this loop does well: it is truthful (broker-confirmed outcomes only), per-trade, versioned and revertible, and it never lets learned text change authority (memory-policy.md:3).

What it does not do:
- The review prompt is one sentence; no review structure (setup quality vs entry vs management vs execution, MAE/MFE, was the plan followed, what market regime, what was the news context). lonora.md:568 mentions the four qualities but nothing asks the agent to grade them.
- Reviews land in free-form memory (MEMORY.md, bounded size) with no structured journal, no tags, no way to query "all losing trades in London open", and no promotion path from repeated lessons to an OPERATING.md rule or skill version.
- Statistics are per label only (count, net). A label is whatever slug the agent invents, so across time and across agents they drift ("scale_in" vs "scalein_add").
- Nothing prompts periodic method review beyond the weekly report; no scheduled "learning" routine, no cross-agent sharing of lessons (Lonora can read team agents' memory, VISION.md:92-93 but no mechanism distills).
- Backtesting is excluded (lonora.md:570), so the only evidence base is live/demo closes; small samples are not warned about except "Do not cherry-pick one successful trade" (:568).

## 6. Does the agent have what an expert has? Gap analysis

Legend: HAVE = text or tool exists; PARTIAL; MISSING.

| Expert capability | Status | Evidence |
|---|---|---|
| Honest evidence handling (fresh, closed bars, no invention) | HAVE, very strong | lonora.md:67-81, 203-215; market-analysis skill |
| Execution safety, reconciliation, receipts | HAVE, very strong | trading-policy.md; lonora.md:83-93, 300-342; VISION 6 |
| Observation tools (snapshot, structure, sessions, calendar, charts, watches) | HAVE | section 4 |
| Self-scheduling / wake on level / task_wait | HAVE | market-watch skill; lonora.md:344-380 |
| Decision record with invalidation | HAVE | market_decision_record; market-analysis/SKILL.md:51-55 |
| Per-trade self-review and per-label stats | PARTIAL | section 5 |
| Versioned, revertable method and skills | HAVE | section 2, 5 |
| Market-reading method (trend/range/regime, structure, levels, confluence, multi-timeframe top-down, what a trigger is) | MISSING as text | Only tool order; no how-to-think |
| Setup taxonomy and when each tends to work/fail (breakout, pullback, range fade, reversal, news, carry, mean reversion), phrased as heuristics, not rules | MISSING | |
| Risk and sizing reasoning (loss budget vs conviction, stop placement from structure/ATR, correlation, concentration, pyramiding rules of thumb, survival, when to cut size after losses) as judgment aids without fixed numbers | MISSING | 5.2 names sizing and exposure but teaches nothing |
| Trade management craft (when to trail, partial, move to BE, time stop, thesis-break exit; cost of over-managing) | MISSING beyond the verb list | lonora.md:38 |
| Session and time behaviour (Asia range, London open, NY overlap, rollover/spread widening, Friday close, Sunday gap, holidays) and per-asset personality (gold, JPY pairs, indices, BTC CFD) | MISSING | tool gives clock only, "Holidays and liquidity are not modelled" |
| News and event handling (tiers of events, pre/post event stance, reading surprise vs expectation, central-bank reaction function, risk-on/off, DXY/yields linkage) | MISSING | only research hygiene |
| Intermarket analysis | PARTIAL | market_relationship tools; no interpretive text |
| Execution-cost awareness (spread, slippage, swap, commission vs stop size) | PARTIAL | instrument/quote tools show spread; policy says only "includes spread" for sizing estimate |
| Trade review framework and error taxonomy (analysis, entry, management, execution, discipline); expectancy thinking; sample size humility | MISSING | one-sentence prompt |
| Self-calibration (confidence vs outcome, detecting tilt after drawdown, revenge trading), phrased without imposing cooling-off periods (P1 forbids them) | MISSING | |
| Learning from the owner's strategy documents | HAVE (route) | 5.6; no guidance on distilling a PDF into a testable method |
| Calendar and news sources actually connected | PARTIAL | tools exist; calendar is "owner's configured sources" only; feeds are owner-subscribed |
| Evaluation of whether the agent trades well | MISSING | scripts/agent_eval is a conversation/behaviour harness (docs/agent-eval.md), not a trading-quality benchmark |

## 7. Binding constraints for any addition (summary)

1. No fixed numbers as rules. P1 forbids caps, quotas, money limits, activity budgets, cooling-off periods, risk disclaimers (VISION.md:33). 5.2 calls every judgment "never rules it must follow" (:226). Knowledge must be framed as considerations, heuristics and questions to ask, with ranges derived from live evidence (ATR, spread, account), never "risk 1%".
2. Knowledge is guidance, never authority. Skills "never grant tools or financial authority" (context/skills.py:207; lonora.md:409; trading-policy.md:1). Nothing written may touch mode, approval, fencing, journal, reconciliation, ticket ownership (VISION 6).
3. No rule engine or fixed strategy pipeline (VISION 1, 5.1, P3): no required detector, no mandatory checklist gate that blocks a trade, no required pattern (chart-analysis SKILL.md:21; trading-policy.md:1).
4. No backtesting or walk-forward text in any resource except the single exclusion sentence (tests/test_backtesting_excluded.py).
5. No disclaimers, hedging or lectures in the voice (lonora.md:24; test_system_policy.py:329-345). Knowledge text must be written for the agent, not turned into replies.
6. Core prompt headroom is about 2,500 chars and domain chapters are near caps (see 1). Edits to lonora.md or bootstrap files need the manifest regenerated in the same change (VISION 5.8.6) and must keep SAFETY_CORE sentences (test_system_policy.py:317-320).
7. MetaTrader only, broker's symbols, no symbol list (Amendment 2): knowledge must be instrument-class based and tell the agent to read the contract specs.
8. Honesty rules stay: never state profit the account doesn't show, never invent data or news (lonora.md:25, 69-81, 485).
9. Agent-authored text is labelled and ranks below owner instructions (context/memory.py:47-50); external skill/PDF text is data (VISION 6.10). A knowledge pack shipped by the product is `builtin`/`bundled_first_party` and is the only text that can carry first-party trust; owner and agent copies are labelled owner_supplied / agent_authored.
10. Progressive loading is the intended design (lonora.md:6-7 "domain chapters are loaded progressively", catalog + skill_view). Only market-watch is automatic; every other builtin is explicit, so new knowledge skills will not be read unless the agent chooses to `skill_view` them from a one-line description. Descriptions are therefore the load path and must be written as triggers ("Use when judging an entry, sizing or an exit").

## 8. Where an expert knowledge layer can attach with no new mechanism

(Findings only; design belongs to the next step.)
- Built-in skills under R/skills/<id>/ (6,000-char budget each, 16,000 active total, 32 max): e.g. one per concern (market reading, risk and sizing judgment, trade management craft, sessions and news, review and learning, instrument personalities). Cost: pyproject lists, skill-runtime tests, regex ban list.
- Skill dependencies (`dependencies` in skill.json) can pull a small "principles" skill automatically whenever market-analysis or trade-management is viewed (resolver.py closure, :110-118). This is the one place to make expert knowledge arrive with the existing skills without raising the core prompt size. Changing the dependencies of market-analysis or trade-management bumps their versions.
- `description` lines (catalog, 6,000-char cut) decide discovery; the `activation.mode` "automatic" with a trigger (as market-watch uses "watch") can load a knowledge skill on wake triggers such as broker_event or weekly_report. Run triggers observed in code: broker_event (close_wake.py:174-186), weekly_report (weekly_report.py:TRIGGER), watch, routine, user.
- close_wake.py:93-95 and weekly_report.py:WAKE_TEXT are server-owned fixed texts, so the review structure can be improved there (VISION 5.5.2 allows it) while staying fixed server text built from ledger facts.
- OPERATING.md seeding: agent_create.py already writes assigned market/account into OPERATING.md; a starter method could be written the same way, versioned and revertable.
- statistics_block can be extended with measured facts (win/loss counts, average, hold time) without changing the safety core; they are broker-confirmed facts, not rules (statistics.py).
- Skill packages from trusted GitHub sources give owner-extensible knowledge (e.g. the owner's own repository) with provenance `external`.

## 9. What I could not confirm

- The brief's quotation "The model decides. There is no rule engine and no fixed strategy pipeline" is not a verbatim VISION.md sentence (title at :220, body at :222; section 1 at :27 says "not a rule engine").
- I did not read the floorplan description JSONs in depth, only used the floorplan to locate nodes (backend-libs.agent.runtime, .memory, .trading.market, .trading.charts, .tools).
- I did not run any code or tests; the size figures for lonora.md come from counting characters in the policy blocks (core 11,990).
- I did not inspect /home/user/aichart (out of scope of this step); comparison with its knowledge content is for a later step.
