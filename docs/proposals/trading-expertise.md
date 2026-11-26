# Trading expertise for Lonora's agents: skills, not fixed numbers (proposal)

Audience: Lonora developers. The plain Arabic summary for the owner comes first.
Status: TX1 and TX2 shipped (the 18 skills; built behaviour in `docs/trading-skills.md`). TX3 to TX6 are proposed.
Lonora was read at `main` `d8193b98` (`/home/user/wt-agent/fxmain`), and AiChart at `1a1b5e0` (`/home/user/aichart`).
Both were read only. Nothing was built, run or published.
Inputs: `aichart-knowledge.md`, `aichart-learning.md`, `lonora-trading-knowledge.md`, `gap-memory.md`, the skills parts of
`rakazo-memory.md` and `openmausbot-memory.md`, and `ROADMAP.md`, all in this folder. I spot-checked the claims I rely on in
the code (section 7).
Binding texts: VISION 1, P1, P2, P3, 5.1-5.8, 6 (never weakened), 13, 17 ("The model decides. There is no rule engine and no
fixed strategy pipeline."), and Amendment 2 (MetaTrader only, any symbol the broker offers).

---

## الخلاصة بالعربية

1. مشروع AiChart ليس نموذجاً مدرَّباً على التداول. أغلب "خبرته" أرقام ثابتة داخل برنامج. الجزء الذي يعلّم فعلاً هو أطلس النماذج وقواعد الانضباط في القرار، وهو نفسه ألغى ربط الثقة بالاختبار التاريخي.
2. لونورا عندها أدوات ممتازة وأمان قوي، لكن "عقل المتداول" فيها شبه فارغ: لا توجد معرفة مكتوبة عن قراءة السوق أو المخاطرة أو إدارة الصفقة أو مراجعتها.
3. اقتراحنا أن نكتب خبرة المتداول المحترف على شكل مهارات يقرؤها النموذج بنفسه عند الحاجة، كما يرجع الخبير إلى مرجعه. لا يتحول أي رقم ثابت فيها إلى شرط.
4. المكتبة سبع عشرة مهارة:
   - بنية السوق والسيولة، والأطر الزمنية، والجلسات والتوقيت؛
   - أطلس النماذج والشموع، والمؤشرات كسياق، والأخبار والاقتصاد الكلي؛
   - تخطيط الصفقة، والمخاطرة وحجم العقد، وإدارة الصفقة والخروج؛
   - المراجعة والتعلم، وتحويل استراتيجيتك إلى منهج؛
   - وخمس عائلات أدوات: العملات، والمعادن، والمؤشرات، والطاقة، والعملات الرقمية كعقود فروقات إن كان وسيطك يقدمها.
5. خمس منها مأخوذة من AiChart بعد تعميمها على كل الرموز، وجزء من مهارة المراجعة كذلك. الباقي جديد لأن AiChart لا يغطيه.
6. كل مهارة تعلّم طريقة التفكير: ماذا أقرر، وكيف أزن الأدلة، وماذا أفحص، ومتى تضعف الفكرة، وكيف أقول رأيي بحسم. لا يظهر رقم إلا مثالاً، ومكتوب بجانبه أنه مثال.
7. يرى النموذج قائمة قصيرة بأسماء المهارات ويختار بنفسه ما يقرؤه. لا يوجد برنامج يختار عنه، ولا قاعدة تمنعه.
8. نستعمل نظام المهارات الموجود في لونورا كما هو، ونرفع فقط مقدار ما يستطيع الوكيل قراءته في الجلسة الواحدة.
9. عند إغلاق كل صفقة يعطي الخادمُ الوكيلَ حقائقها من الوسيط: الدخول، والخروج، والوقف الأول، والنتيجة بوحدات المخاطرة. ثم يكتب الوكيل مراجعة منظمة: ماذا توقع، وماذا حدث، وما السبب، وما الدرس ومتى ينطبق.
10. قبل قراره التالي يبحث الوكيل عن الدروس المشابهة (نفس الرمز أو العائلة أو نوع الإعداد أو الجلسة)، ويقرؤها كدليل.
11. الإحصاءات تُحسب من صفقات الوكيل الحقيقية فقط: كم صفقة ربحت من الكل، ومتوسط العائد بوحدات المخاطرة، حسب نوع الإعداد والرمز والجلسة، للوكيل وللفريق. تُعرض دليلاً يزنه الوكيل، لا قاعدة يلتزم بها.
12. في التقرير الأسبوعي يقرر الوكيل إن كان درسٌ ما قد صار قوياً بما يكفي ليغيّر منهجه. يكتب التغيير مع دليله، ويظهر لك في التقرير، وتستطيع التراجع عنه بكلمة.
13. المنهج الذي تعطيه للوكيل يبقى نصه كما كتبته، وتُكتب التحسينات بجانبه منفصلة.
14. الاختبار التاريخي سبق أن قررتَ استبعاده من لونورا، ونوصي بإبقائه مستبعداً. نقله من AiChart يكلف أسابيع ويخالف قرارك.
15. لن نبني محرك قواعد، ولا حدوداً، ولا شروطاً رقمية، ولا طريقاً جديداً لتنفيذ الأوامر. كل أمر يمر من باب التنفيذ نفسه كما هو اليوم.
16. التنفيذ على ست دفعات، في نحو خمسة إلى سبعة أسابيع عمل لمطور واحد.
17. نحتاج قرارك في خمس نقاط:
    - الاختبار التاريخي؛
    - العملات الرقمية كعقود فروقات؛
    - هل ينتظر تحسينُ منهجك موافقتك؛
    - رفع ميزانية قراءة المهارات؛
    - مشاركة الدروس بين الوكلاء.

---

## 0. What the three studies show (the basis for this proposal)

- **AiChart is not a model trained to trade.** It has a thin prose layer and a deterministic engine
  (`aichart-knowledge.md` headline).
  - The prose holds about 27 KB of always-on discipline rules and one real teaching skill, the Pattern Atlas (10.3 KB).
  - The engine holds almost all fixed numbers. Examples: ATR multiples in `scalpGeometry.ts`, POI grades in
    `scorePoi.ts`, the 30/15-minute news blackout, and the 0.62/0.38 premium and discount lines.
  - Sessions, indicators, news interpretation, trade management, sizing and psychology are absent.
- **AiChart's backtest-to-confidence path is switched off by AiChart itself.** See
  `src/lib/agent/researchEvidence.ts:624`: "Simulation backtests are deleted. Never raise confidence from them."
  - Its live learning is a forward ledger plus prompt text framed as evidence: «سياق تزنه، لا قاعدة تُلزمك»
    (`src/lib/agent/learningLoop.ts:158`).
  - Its free-text lessons were never wired: `insertTradeLesson` has no caller.
- **Lonora has a strong workbench and a thin mind** (`lonora-trading-knowledge.md` section 0).
  - No built-in skill teaches trading. The seven built-ins teach tool procedure.
  - The trader's judgment in `lonora.md:31-42` is a list of verbs.
  - The close-wake review is one sentence (`close_wake.py:93-95`).
  - Statistics are a count and net P&L per label (`statistics.py`).
- **Lonora's skill system is already the right delivery mechanism.**
  - A catalog sits in the system role. The model loads a body with `skill_view`.
  - Versions are pinned, provenance is labelled, and `authority_granted: False` is set (`context/skills.py`,
    `skills/access.py`).
  - Nothing new is needed to deliver knowledge. What is missing is the content, a measurable journal, and a way back from
    results to the method.

The proposal has three parts:
1. Write the expertise as built-in skills.
2. Measure the journal in R, write a review per trade and retrieve the lessons.
3. Grow lessons into the method in the weekly run.

None of this adds a rule, a limit or an order path.

---

## 1. The skill library

### 1.1 Authoring contract (applies to every trading skill)

1. **Judgment, not conditions.** Each skill states what an expert weighs and why, and never says "only enter if". The
   words "must" and "never" are kept for honesty, for example "never call a wick a break", and are never used for a
   trading choice. VISION 5.2 ("examples of judgment the agent may choose, never rules it must follow").
2. **The instrument's own units.** Distances are stated in the symbol's own ATR, typical candle range, spread and tick size,
   read live from `market_snapshot` and `market_instrument`. Never in fixed points or pips across symbols. This removes
   AiChart's gold point constants (`aichart-knowledge.md` 5.2).
3. **Numbers only as illustrations.** A number appears only on a line that says "Illustration". A test enforces this
   (section 2.4).
4. **A fixed schema per topic**, generalised from the atlas schema:
   - When to use;
   - What you are deciding;
   - How to reason;
   - What to check;
   - Weak when / what fails it;
   - How to say it.
5. **Decisive uncertainty.** Name the condition that changes the view and the evidence you lack, in one line, then decide.
   Never "it may go up or down". This matches `lonora.md:21-24`, and AiChart's voice section is reused.
   - "No trade" is a first-class outcome: "Not trading is a decision" (VISION 5.2).
   - AiChart's "never answer WAIT" is dropped.
6. **No symbol lists.** Families are recognised from the contract specification, meaning `Instrument.path` (the broker
   category, `contracts/market.py:13-14`) and the base and profit currencies. Every family skill starts by telling the agent
   to read contract size, tick value, digits, stops level, trading hours and swap. Amendment 2.
7. **Knowledge never grants authority.** Each skill is `risk_class: read_only` with no required tools, so it is eligible in
   every scope, observe-only and helper runs included. The catalog already says skills never grant tools or financial
   authority (`context/skills.py:203-205`).
8. **English text, owner-language replies** (`lonora.md`: "Author skill names, descriptions, instructions and examples in
   English").
   - Bilingual descriptions are not needed. The model reads the catalog itself.
   - AiChart needed Arabic tags only because its keyword scorer missed Arabic requests.
9. **No backtesting vocabulary.** `tests/test_backtesting_excluded.py:96-110` scans every shipped resource for
   `backtest|walk.?forward|monte.?carlo|out.of.sample|strategy.research`. The review skill speaks of forward results and
   "trades you have not yet seen", never "out of sample".
10. **Size.**
    - Each body should be 5,000 characters or less. The manifest `context_budget` default of 6,000 is the hard cap
      (`contracts/skills.py:67`).
    - Each description should be 200 characters or less, and written as a trigger ("Use when ...").

### 1.2 The skills to ship (17 new built-ins)

"Source" means: **AiChart** = ported and generalised beyond gold; **new** = AiChart has nothing on it.

| # | id | Purpose and outline | Source | Target body |
|---|---|---|---|---|
| 1 | `market-structure` | Regime (trend, range, transition); breaks (a close beyond) vs sweeps (a wick beyond); BOS and CHoCH; dealing range and premium/discount; liquidity pools; supply and demand zone quality as weighed factors; level decay with touches. Full text in 1.3. | AiChart: atlas "Structure and liquidity", `scorePoi.ts` factors without points or grades, `rangePosition.ts` without fixed fractions, `trading-strategies` dimensions | 4,500 |
| 2 | `multi-timeframe` | The leading, context and timing frames; conflict handling (which leads, and say so); match the plan style to the holding horizon; closed vs forming bars on each frame; lower-frame noise never overrides higher-frame invalidation. | AiChart: constitution timeframe conflict; its fixed "minute = scalp" map rewritten as judgment | 3,000 |
| 3 | `sessions-and-time` | What Asia, London and New York tend to do; overlaps; opens that sweep the prior session's extremes; rollover spread widening; Friday close and weekend gap risk; holidays (the `market_sessions` tool says "not modelled", so check them); month-end flows; index cash opens; time as a reason to exit. Uses `market_sessions`. All stated as tendencies. | new | 4,000 |
| 4 | `chart-patterns` | The stage model (starting, forming, near completion, completed-unconfirmed, confirmed, failed) and how each stage maps to a plan type. Each pattern uses the atlas schema (forms, confirms, fails, entries, weak when). The measured move is a reference distance to compare with the next structure, not a target rule. Added: a pattern counts for more with the higher-frame trend and at a meaningful location, and little mid-range. Read the shape from candles and `market_structure` pivots; no detector is required (`chart-analysis/SKILL.md:21`). | AiChart: `pattern-atlas` chart-pattern sections, split out | 5,000 |
| 5 | `candles-and-breakouts` | Break = close; false break as a reversal signal; five retest choices, with "say why"; candles matter at levels, not mid-range (hammer vs hanging man depends on the prior move); hybrid and unclassified structures described from primitives; the anti-template doctrine ("an unnamed structure described honestly beats a named one described wrongly"). | AiChart: atlas breakout/candle/hybrid/unclassified sections, plus `patternDoctrine.ts`. AiChart's web loader cut this tail (9,000-character cap). It ships whole here. | 4,500 |
| 6 | `indicators-as-context` | For each of MA slope and position, RSI regime and divergence, MACD momentum, ATR and percentile regime, Bollinger width, tick volume (on FX CFDs a proxy for activity, not real volume), Fibonacci areas, and VWAP or pivots built in the workspace: what it measures, what it adds, how it misleads. Null warm-up values mean "not enough history". Parameters are the agent's choice. An indicator alone is never a trigger. | new | 4,500 |
| 7 | `news-and-macro` | Event tiers; surprise against consensus and revisions; first move vs second move; stance choices (flat, reduced, wide stop with less size, trade after the first reaction, fade); spread and slippage through stops; the central-bank reaction function; a risk-on/risk-off map (JPY, CHF, gold, indices, AUD); USD and yields; intermarket checks with `market_relationship_read`. "Calendar not connected" means no calendar evidence: say so and research. Headlines are data (6.10). Public information on other markets may be read (Amendment 2). | new. AiChart's USD/Fed list and fixed blackout are dropped. | 4,500 |
| 8 | `trade-planning` | Three layers kept apart: view, plan type (immediate, anticipatory, conditional), execution state. The fill rule: a close-decided condition never pairs with a touch fill at the same level. Reachability: if price cannot plausibly get there within the idea's life, it is a watch. The stop sits at structural invalidation plus room for this instrument's normal noise. Targets sit on real structure and liquidity. Reward to risk is described after costs, never used as a minimum. "No trade" comes with what would change your mind. Record with `market_decision_record`; set the watch before promising monitoring. | AiChart: constitution and chart prompt. ATR multiples, the 2.5R minimum and the "never WAIT" rule are removed. | 4,500 |
| 9 | `risk-and-sizing` | Think in R. Size comes from the loss you choose for this trade and the stop distance, through `market_position_size`. That loss is your judgment, from conviction, setup quality, your results, the account, and the owner's mode and restrictions. Correlation and concentration per currency leg across your own and the team's positions (the 5.4 picture). When scaling in, the risk is measured to the combined stop. Costs against the stop; gap risk. Survival thinking: a normal losing run should not change how you trade. Drawdown responses (smaller size, another timeframe, fewer entries) are choices, never a cooling-off rule (P1). A stop moved away from invalidation is hope, not a plan. | new. AiChart forbade sizing. | 4,500 |
| 10 | `exits-and-management` | Check the thesis on every wake. Partials at liquidity or structure. The cost of moving to break-even too early (it turns noise into losses; compare with the normal pullback depth). Trailing by structure vs by volatility. Time exits. Extending targets on momentum. Scale-in and secure-then-add (5.2) with aggregate risk. Exposure over events. The cost of over-managing. Management labels (5.5.3). Watches to wake yourself. | new | 4,500 |
| 11 | `trade-review` | Gather the close facts (3.1), your decision record, your thesis, and candles for MFE and MAE. Grade analysis, entry, management, execution and discipline separately (`lonora.md:568`). Name a cause (read, entry, management, execution, event, variance). Keep outcome apart from decision quality. Write the review with `trade_review_write`. How to read statistics (wins out of n, mean R, the spread of outcomes, sample-size humility); look for counter-cases. When a lesson is ready to change the method, and how to write that change (3.5). Self-calibration: compare stated conviction with outcomes; notice tilt in your own journal (size jumps after losses, trades outside your method). Reuse the labels you already use. Loaded by the close and weekly wakes. | AiChart in part: the ledger honesty rules (grade from the real fill, partial wins count, query both sides, counts below a sample). Mostly new. | 5,000 |
| 12 | `method-intake` | VISION 5.6. Read the owner's strategy (message, PDF or file) in full. Extract markets, timeframes, setup in words, entry, stop, exit, management, sizing and when not to trade. Write it into OPERATING.md as "Rules as given" (the owner's words) plus "How I apply it". Ask only about genuinely missing decisions (`wait_for_input`). Pick a label for trades under it. Refine from results in a separate "Refinements" part (3.5). Never present it as validated. | new | 3,000 |
| 13 | `family-forex` | Each pair is two currencies' stories. USD legs and a dollar index as context, where the broker offers one. JPY and CHF as risk gauges. Commodity currencies (CAD with oil, AUD with metals and China). Rate differentials and central-bank divergence. Crosses are relative strength. Session liquidity per currency. Swap over multi-day holds. Rollover spread. Per-leg correlation across positions. Pip vs point from `digits`. | new | 3,000 |
| 14 | `family-metals` | Gold: real yields, USD, risk-off flows, central-bank demand, geopolitics; wide ranges and stop runs around US data; London fix times as facts. Silver: higher beta, industrial demand, thinner liquidity. The gold/silver ratio as context. Platinum and palladium where offered: thin. Contract size differs by broker. | new. AiChart was gold-only and point-denominated. | 3,000 |
| 15 | `family-indices` | Cash vs futures-based CFDs (roll dates and price adjustments). Hours and breaks. Opening gaps and the opening drive. Earnings season and mega-cap concentration. Yields and risk sentiment. Dividend adjustments. Index-to-index correlation. A volatility index as context where offered. Weekend gaps. The exchange's time zone. | new | 3,000 |
| 16 | `family-energy` | Crude: weekly US inventory reports, OPEC+ decisions, geopolitics, USD, contract roll on futures-based CFDs, Brent vs WTI. Natural gas: weather, storage reports, extreme volatility, wide spreads. Trading hours. | new | 3,000 |
| 17 | `family-crypto-cfd` | Only for crypto CFDs the MT5 broker offers, traded through the door (Amendment 2: no exchange, no wallet). Broker hours vs the 24/7 underlying (weekend gaps or thin weekends). Volatility and wide spreads. Heavy swap. Broker-specific margin. Correlation with risk assets. Liquidation cascades. ETF flows and regulation as news. Owner decision TX-D2. | new | 3,000 |

Total: about 66,000 characters of reviewed expert text. The existing `trade-management` and `position-management` keep their
names and stay mechanics only. The new names do not collide with them.

### 1.3 Example: `market-structure` (complete, as it would ship)

`packages/agent-runtime/resources/skills/market-structure/SKILL.md`, about 4,300 characters:

```markdown
---
name: market-structure
description: Use when reading trend, range or transition on any MT5 symbol, locating price in its dealing range, judging a supply or demand zone, or deciding whether a level broke or was swept.
---

# Market Structure and Liquidity

Follow the owner's current language in replies. This is judgment knowledge: what an
expert weighs, never a condition you must meet. No line here is a threshold; a number
appears only as a marked illustration.

## What you are deciding

Who controls the timeframe that leads your decision, where price sits in the range that
matters, where resting orders are likely, and which level proves you wrong. Structure
gives location and invalidation. It does not by itself give a side.

## Read the regime first

- Trend: confirmed swings step in one direction and pullbacks are absorbed before they
  undo most of the prior leg. Judge from confirmed pivots (market_structure), never
  from the forming bar.
- Range: swings fail at the same areas from both sides and breaks do not follow through.
- Transition: the swing that defended the trend has failed and no new sequence exists.
  Expect two-way trade and hold your conviction lower.
Ask whether volatility is expanding or contracting (market_snapshot regime). Expansion
out of a range and contraction into a trend leg mean different things.

## Breaks, sweeps and shifts

- A break is a candle close beyond the level on the timeframe you judge. A wick beyond
  it that closes back inside is a sweep: orders were taken, the level was not accepted.
- A break of structure with the trend supports continuation. The first break against
  it (change of character) opens the case for reversal; it does not prove it.
- A sweep alone is not a trade. A sweep followed by a shift on your timing frame often
  is worth a plan. Say which of the two you have.
- Each new test of a level usually weakens it, because the orders defending it get
  used. A level tested again and again is often a break in waiting, not a stronger wall.

## Locate price in the dealing range

Take the range that matters for your horizon: the last swing high and low price trades
between. Buying in its upper part pays up; selling in its lower part chases. Mid-range
is a poor place for an immediate entry and a good place to plan an order at an edge.
Choose the range from structure, not from a fixed lookback.

## Where liquidity rests

Equal highs and lows, prior day and week extremes (market_snapshot), session highs and
lows (sessions-and-time), round numbers, and the far side of obvious stop placements.
They pull price as often as they stop it. Before entering, ask which pool price is
likely to reach first, and whether your own stop sits inside an obvious one.

## Judging a supply or demand zone

Weigh these together; never count them:
- the strength of the move that left the zone;
- freshness: an untested zone is cleaner, and each return spends it;
- whether it took liquidity before leaving and whether it broke structure;
- agreement with the higher timeframe;
- width against this instrument's normal candle range: wider than a typical swing is
  a region, not a level;
- distance: a zone price cannot reach within your idea's life is a watch, not an entry.
A strong zone in the wrong half of the range and against the higher timeframe is still
a weak trade.

## Units for any symbol

Never carry points or pips from one symbol to another. Measure in the instrument's own
units: its recent ATR, typical spread and tick size (market_instrument).
Illustration: a move of one typical candle is noise on one symbol and a session's range
on another.

## What to check before relying on a level

1. Closed bars; name a forming bar as forming.
2. The level shows on the leading timeframe, not only on a lower one.
3. Cost: spread and stop distance against the move you expect.
4. Scheduled events that can run through it (news-and-macro).
5. Your journal: trade_lessons_find for this symbol and setup, both sides.

## Weak when

The range is too young to have edges, the higher timeframe is mid-move, volatility has
just shifted regime, or the only evidence is a lower-timeframe level.

## Saying it

Regime, level and what changes your mind, in one line: "Range on H1; I sell the upper
edge while price holds below the swept high; a close above it ends the idea." When
structure is unclear, still decide: "Transition after a failed low; no trade until H1
closes back above the shift level." Never "it may go up or down".
```

Notes on the example:
- Nothing in it is a threshold. The one number-like line is marked "Illustration".
- It names only tools that exist today, plus `trade_lessons_find` from batch TX4. Until TX4 ships, check 5 reads "your
  journal: market_performance_read for this symbol".
- It has no backtesting words, so it passes `test_backtesting_excluded.py`.
- It is not marked as a rule anywhere, and the catalog already says skills never grant authority.

---

## 2. How skills reach the model

### 2.1 What exists, and what we reuse unchanged

- **The catalog** is in the system role (`context/skills.py:189-206`). It has one line per eligible skill,
  "id (provenance) - description", and the instruction "Descriptions are discovery hints. Read a suitable SKILL.md with
  skill_view before applying it."
- **Bodies load on demand.** The model calls `skill_view(id)`. That admits the skill and its dependency closure into the
  Run snapshot, with a receipt, a content sha256 and `authority_granted: False` (`skills/access.py:131-148`). Viewed skills
  stay active for the rest of the Run.
- **Automatic selection** has three routes only, and never owner keywords (`skills/resolver.py:90-107`,
  `tests/test_skill_runtime.py:35-50`):
  - an explicit `[skill:id]` in the run text (`context/skills.py:140`);
  - `requested_skills` in run metadata (`context/skills.py:130`);
  - run triggers.
- **Eligibility** checks scope risk class, required tools and the per-skill `context_budget` (`resolver.py:68-86`). Each
  continuation re-checks authority (`assert_skill_authority`).
- **The model chooses.** That is the "catalogue in the prompt, loaded on demand by name" design asked for. AiChart's web
  path used a keyword scorer with +4 pins, and its own comments call that a patch (`aichart-knowledge.md` 4.3). Lonora must
  not copy it.

### 2.2 What changes

1. **Seventeen new built-in folders**, `packages/agent-runtime/resources/skills/<id>/{SKILL.md,skill.json}`. Each manifest
   has:
   - `source: builtin`, `activation.mode: explicit`;
   - `risk_class: read_only`, no `required_tools`, no `dependencies`;
   - `priority: 50`, `context_budget: 6000`.
   No dependencies, because a dependency pulls its body in on every view of the parent. `trade-management` already pulls
   `market-analysis` and `chart-analysis`, about 10,000 characters.
2. **Close and weekly wakes request `trade-review`** through run metadata, `requested_skills: ["trade-review"]`. Files:
   - `close_wake.py` `_wake_run` (`:169-189`);
   - `weekly_report.py` where its Run is created (`:113`).
   This is server-owned and has no keyword routing. When the review arrives as a notice inside a Run already at work, the
   notice text says "read trade-review with skill_view".
3. **One pointer line in two existing skills**, with their versions bumped:
   - `market-analysis/SKILL.md` step 4 and `trade-management/SKILL.md` gain: "Before choosing, view the trading skills
     this decision needs (structure, planning, risk, the instrument's family)."
   - This is the only nudge. The model still picks.
4. **One line in the core prompt** under "Trader's judgment" (`lonora.md:31-42`), about 220 characters of the roughly
   2,500 free before the 14,500 cap (`test_system_policy.py:322-325`):
   - "Your trading skills hold a professional's way of reading markets, planning, sizing, managing and reviewing; read the
     ones a decision needs before you make it."
   - Regenerate `resources/system/manifest.json` in the same change (VISION 5.8.6).
5. **A larger reading budget per Run.**
   - `ACTIVE_BUDGET = 16000` (`skills/access.py:29`) leaves about 6,000 characters after the `trade-management` bundle,
     which is one more skill. An expert decision typically needs structure, planning, risk and a family skill (about
     16,000 characters on top of the bundle).
   - Raise the one shared constant to 32,000. It is today repeated as a literal in `resolver.py:27,92`, `runtime.py:11`
     and `catalog.py:55` (the owner view's resolve; `catalog.py:47` is a separate content cut); make it one constant.
     `MAX_SNAPSHOT_CHARS = 128000` (`snapshot.py:13`) already allows this.
   - This is a context size, not a trading limit.
   - Cost: up to about 8,000 more input tokens per model call in a Run that loads that much. It is mostly cached within the
     Run once ROADMAP B14 lands. Owner decision TX-D4, because he pays the model key (D6, D41).
6. **Catalog room.**
   - Today 7 lines take 1,068 characters. 17 new lines at about 220 each bring the total to about 4,800 of the 6,000-character
     cut at `context/skills.py:198`. Owner and agent skills share that room.
   - Ship ROADMAP B22 P3-08 (cut at whole lines, then "N more: use skills_list") in the same batch or before it, so a skill
     never silently falls off the catalog.

### 2.3 Size budget (summary)

| Item | Budget | Today | After |
|---|---|---|---|
| One skill body | 6,000 (manifest cap), target 5,000 or less | largest built-in 4,287 | every new skill under 5,000 |
| Active skill text per Run | 16,000 then 32,000 | trade bundle about 10,000 | bundle plus about 4 expertise skills |
| Catalog | 6,000 characters | 1,068 | about 4,800, plus B22's omitted count |
| Core prompt | 14,500 | 11,991 | about 12,210 |
| Intelligence chapter | 4,666 (`14000 // 3`) | 3,732 | about 4,350 (two tool lines, section 3) |

### 2.4 Files to touch (TX1 and TX2)

- New: the 17 folders above.
- `pyproject.toml:90-96` and `packages/agent-runtime/pyproject.toml:20-26`: data-file entries for each folder (VISION
  14.3 lists them literally).
- `packages/agent-runtime/src/lonora_agent/skills/{access,resolver,runtime,catalog}.py`: the one budget constant.
- `packages/agent-runtime/src/lonora_agent/context/skills.py:198`: the whole-line catalog cut (B22).
- `resources/skills/market-analysis/*`, `resources/skills/trade-management/*`: the pointer line and version bump.
- `resources/system/lonora.md` (core line) and `resources/system/manifest.json` (regenerated).
- `packages/trading/src/lonora_trading/close_wake.py`, `weekly_report.py`: `requested_skills`.
- Tests:
  - `tests/test_skill_runtime.py`: the built-in set. The new skills never load without a request or trigger.
  - `tests/test_backtesting_excluded.py`: unchanged and must pass.
  - A new `tests/test_trading_skills.py`. Each new skill:
    - parses, and its body is 5,000 characters or less;
    - has a description starting "Use when";
    - has the schema headings;
    - has no line with a digit next to a unit (`%`, `R`, `ATR`, `pip`, `point`, `lot`, `x`, `minute`, `hour`, `day`)
      unless the line contains "Illustration";
    - names no broker symbol.
    Every family skill contains the "read the contract specification" step.

---

## 3. Learning so experience accumulates without fixed numbers

The principle is AiChart's best idea (`aichart-learning.md` section 6): **code measures facts honestly, the model
interprets, the model decides.** What AiChart left unwired, Lonora wires: the per-trade written review, the lesson's use at
the next decision, and the step from lesson to method. Every piece reuses an existing Lonora path.

### 3.1 Facts the server supplies when a trade closes

`close_text` (`close_wake.py:68-95`) gives today: symbol, side, volume, label, realized P&L, currency, opened and closed
times, and held minutes. It gains broker-derived numbers only:
- `entry_price` and `exit_price`: volume-weighted from the trade's IN and OUT deals (`ClosedTradeRow.deals`).
- `initial_stop` and `initial_take_profit`: from the opening journaled order's request (`opening_operation_id`). If the
  order had no stop, the first confirmed modify that set one on that ticket before the first exit is used.
- `r_multiple`:
  - Price R is the side-signed (exit - entry) / |entry - initial stop|.
  - Net R uses the trade's own realized money per price unit, from its deals. Commission and swap are therefore included,
    and no tick value needs to be guessed.
  - When R cannot be computed it is `null` with a reason code: `no_initial_stop`, `unpriced` or `no_price_move`.
    It is never estimated.
- `session_at_open`: from `lonora_market.sessions.session_clock(opened_at)` (`market/sessions.py:145`).
- `had_adds` and `partial_exits`: counts from the deals.
- `opening_operation_id` and `thesis_id`, so the agent can read its own decision and thesis with tools.

Design choice: the opening order's free-text `reason` is **not** inlined.
- The `close_text` docstring keeps one invariant: the only agent-chosen value in the wake text is the label slug, and every
  value is JSON-escaped.
- A free-text reason written in a run that read outside content would carry that text into a later wake (6.10).
- The agent reads its own record by id instead.

The computation lives in a new pure module, `packages/trading/src/lonora_trading/trade_r.py`. It is read-only over the
ledger and journal. `execution.py` and the door are not touched (VISION 6).

### 3.2 The review: one structured record per closed trade

- **Trigger.** The same close wake (5.5.2), with `requested_skills: ["trade-review"]`. Its last sentence changes:
  - from: "write a short self-review ... with memory_write";
  - to: "write your review of this trade with trade_review_write, following trade-review".
  The review stays the agent's memory in Lonora's memory store (3.2.4). It just gets structure.
- **Tool `trade_review_write`** (new, `packages/tools/src/lonora_tools/trade_reviews.py`). Its inputs:
  - `closed_trade_id` (the server fills symbol, side, label, R, P&L, session and times from the ledger; the agent cannot
    restate them);
  - `family` (the agent's reading of the instrument family), `timeframe` and `setup` (defaults to the label);
  - `expected`, `happened`;
  - `cause`, one of `read | entry | management | execution | event | variance` (a vocabulary for retrieval, not a rule);
  - `lesson` (one or two sentences), `applies_when`, `not_when`;
  - `decision_id` (optional).
  Rewriting a review replaces it and emits an event with the prior text, the same pattern `knowledge_note_delete` uses
  (`tools/knowledge.py`).
- **Storage: reuse `ln_semantic_memory` (`SemanticMemoryRow`); no new table and no migration.**
  - `payload.kind = "trade_review"`, with the structured fields beside `text` and `embedding`.
  - The document id is `stable_id(agent_id, "trade-review:" + closed_trade_id)`, so there is one review per trade.
  - A new `index_trade_review` sits beside `index_note` (`lonora_memory/semantic.py:70`) and reuses `embed_text` (`:28`).
    An embedding is stored only when the owner set an embedding model (13.1: no hidden switch).
  - `lonora_db/knowledge.py` `knowledge_items` lists reviews as their own type.
  - The automatic recall candidate pool (`lonora_memory/evidence.py`) skips `kind = trade_review`, so reviews do not crowd
    the 6,000-character recall budget. They are fetched on purpose (3.3).
- **Provenance.** Reviews are agent-authored data and rank below the owner's instructions (`context/memory.py:47-50`). If
  ROADMAP O3/D7 (the outside-content label) is adopted, reviews carry the same label.

### 3.3 Retrieval at the next decision: `trade_lessons_find`

- **The tool** (new, same module) is read-only. Its inputs are `symbol`, `family`, `setup`, `session`, `timeframe` and
  free text `situation`, all optional.
- **Ranking** is a reciprocal-rank fusion of two signals:
  - structured closeness: same symbol, then same family (marked `transferred_from` when the symbol differs), then same setup
    label and same session;
  - text similarity on `situation` against lesson, applies-when and not-when, using `retrieval.lexical_score` and the
    embedding when configured (the same fusion as `fuse_evidence`).
  It returns at most 6 reviews and about 3,600 characters. Each review carries its ledger facts (R, P&L, date) and its
  cause.
- **Both sides.** The tool never filters by direction. It returns lessons from both sides, and the skill says to call it
  before choosing a side. This is AiChart's guard against evidence becoming justification (`aichart-learning.md` Flow D.5).
- **Its own facts line.** It also returns the measured statistics for that symbol and setup (3.4), so the lesson text is
  always shown next to what the ledger says.
- **Usage is logged.** `market_decision_record` gains an optional `lesson_ids` (at most 8) in
  `contracts/trading_decision.py` `DecisionRequest` / `TradingDecision`. A review's `decision_id` then links outcome to
  lessons used. This fixes AiChart weakness 11 ("cannot learn whether its lessons help"). An analysis of "did plans that
  used lesson X do better" is left for later. Recording the link is cheap now.
- **No automatic injection.** The model calls the tool when deciding. `market-structure`, `trade-planning` and
  `market-analysis` say when. The wake picture keeps only the statistics (3.4). VISION 5.1: the model decides what to read.

### 3.4 Statistics: measured from the journal, shown as evidence

- **Where.** `statistics_block` (`statistics.py`) and `market_performance_read` (`tools/performance.py`,
  `contracts/execution_quality.py` `PerformanceRead`).
- **Per group:**
  - `trades`, `wins`, `losses` and `flat` (by the sign of net realized P&L, so a TP1-then-stop trade is a win; this fixes
    AiChart weakness 3);
  - net P&L per currency (as today);
  - `r: {n, mean, sum, mean_win, mean_loss}`, where `mean` is the expectancy in R;
  - `no_stop` and `unpriced` counts.
- **Win rate is shown as "wins of n"** (for example `{"wins": 6, "of": 9}`), never as a bare percentage.
  - The model sees the sample size every time.
  - There is no floor constant: no "8 trades before a rate".
  - Sample humility is taught in `trade-review`, not coded as a threshold.
  - AiChart's fixed floors (5, 8, 20) are an example of what we avoid (`aichart-learning.md` section 3).
- **New inputs on `PerformanceRead`:**
  - `group_by: label | symbol | session | side | label_symbol` (default `label`, as today);
  - `since` (optional; the agent chooses the window; no fixed window);
  - `scope: own | team`.
- **Scope:**
  - `own`: the agent's trades, as today.
  - `team`: all agents' broker-confirmed closes combined, per group. For Lonora it is split per agent, plus one row for the
    owner's own tickets (`agent_id` null), because Lonora sees the whole account (3.1.3) and knows the owner (3.1.4).
  - These are ledger facts, not memory, so 3.2.4 is respected. Lesson text stays private (3.5, TX-D5).
- **The wake.** `own_results` in the wake picture (`context/picture.py:340`) keeps its per-label rows and adds the `r`
  fields. Its framing sentence (`:358`) adds: "measured facts from broker deals; you weigh them; they are not rules."
- **The weekly report.** Facts (`weekly_report.py:78`) add per-label R for the week and since the start.
- **The intelligence chapter of `lonora.md`** (about 930 characters free) gets two short lines, one for
  `trade_review_write` and one for `trade_lessons_find`. The `market_performance_read` line notes R. Regenerate
  `manifest.json`, whose `tool_policies` must list the two new tools under `intelligence` (`system_policy.py:73-75`).

### 3.5 From lessons to an updated method, with the owner's say (5.5, 5.6)

- **The weekly run is the moment.** It reuses ROADMAP B30 (P3-16): read before write, the do-not-capture list, versioned
  writes, nothing posted when nothing changed. This proposal adds three things:
  - `requested_skills: ["trade-review"]`;
  - facts: the week's reviews grouped by label and symbol, with the 3.4 statistics for each group;
  - in the wake text, one question: "Is any lesson now supported well enough by independent trades to change your method?
    Change only what the evidence supports, cite the reviews and the numbers, and report each change."
- **There is no promotion threshold in code.** `trade-review` teaches the judgment:
  - several independent trades point the same way;
  - the ledger agrees (n, mean R);
  - the counter-cases are understood;
  - the condition can be stated precisely;
  - one thing changes at a time.
  Code never writes method text and never promotes anything.
- **Method layout** (taught in `trade-review` and `method-intake`), inside OPERATING.md. For each method:
  - `## Method: <name> (owner-given <date> | my own)`;
  - `Rules as given` (the owner's words, verbatim);
  - `How I apply it`;
  - `Refinements from results`, one line each: the change, the evidence (review ids, n, mean R, window) and the date.
  A refinement the results later contradict is struck, not deleted.
- **The owner's say, without an approval queue** (P1, P5; `gap-memory.md` S4 rejects a queue):
  1. Every method write is already a version (5.5.5, `lonora_memory/method.py`). The owner, Lonora or the agent can
     restore any version with `method_restore`. "Undo that change" in chat is enough.
  2. The weekly report lists each change with its evidence. 5.5.6 already requires "what it changed".
  3. "Rules as given" is the owner's text. The agent never rewrites it without his message. Its refinements go in their own
     part, so he always sees what is his and what was learned. Optionally, protect those lines later with the
     owner-word mechanism that `USER.md` uses (`OWNERS_WORD_PROTECTED`). Not proposed now.
  4. Whether refinements to an owner-given method apply at once, or wait for his yes, is TX-D3. The recommendation is to
     apply and report, because 5.6 says the agent "applies it and refines it from results".
- **Lonora as lead** may edit team agents' methods (3.1.2). In its weekly brief it may carry a lesson one agent proved into
  another agent's method, and it says why in one line. Lesson text otherwise stays with its agent (3.2.4, TX-D5).

### 3.6 Files (TX3 to TX5)

| Change | Files |
|---|---|
| R facts at close | new `packages/trading/src/lonora_trading/trade_r.py`; `close_wake.py` (`close_text`, `_wake_run`) |
| Statistics | `packages/trading/src/lonora_trading/statistics.py`, `performance.py`; `packages/contracts/src/lonora_contracts/execution_quality.py`; `packages/tools/src/lonora_tools/performance.py`; `packages/agent-runtime/src/lonora_agent/context/picture.py` |
| Reviews and retrieval | new `packages/tools/src/lonora_tools/trade_reviews.py` (registered in `lonora_tools/loader.py` `MODULES`); `packages/memory/src/lonora_memory/{semantic,retrieval,evidence}.py`; `packages/db/src/lonora_db/knowledge.py` |
| Lesson use | `packages/contracts/src/lonora_contracts/trading_decision.py`; `packages/tools/src/lonora_tools/trading_decision.py` |
| Weekly method step | `packages/trading/src/lonora_trading/weekly_report.py` (wake text `:29`, facts `:78`), together with ROADMAP B30 |
| Policy | `resources/system/lonora.md` (intelligence chapter), `resources/system/manifest.json` |
| Reused unchanged | `lonora_memory/method.py` (`method_history`, `method_restore`), `context/memory.py` (OPERATING.md at weight 82), `closed_trades.py` (ledger) |
| Tests | R computation: a stop on the order, a stop by a later modify, no stop, partial exits, adds, commission and swap, netting reversal. Close text has no free text. One review per trade, and a rewrite emits the prior text. `trade_lessons_find` returns both sides and marks transferred lessons. Recall excludes reviews. `PerformanceRead` groupings and `team` scope (Lonora vs team agent). Decision `lesson_ids`. Weekly facts. |

---

## 4. Optional evidence: porting AiChart's backtester

**What it is.** `research-service/` is Python, about 18,200 lines, of which about 5,300 are the backtest, validation and
strategy packages. It has:
- a frozen strategy DSL;
- a bar-close engine with costs;
- Monte Carlo, bootstrap, walk-forward and sensitivity checks;
- a readiness ladder;
- `src/lib/strategies/calibration.ts` (Wilson and bootstrap intervals).
AiChart **does not use it for confidence** (`researchEvidence.ts:624`, `noBacktestClaims.test.ts`).

**It conflicts with a standing owner decision.**
- Commit `63439adc` "Remove strategy backtesting entirely (owner mandate section 5)" removed Lonora's own SMA-cross research
  engine (`docs/decision-readiness.md:34-55`).
- `lonora.md:570` says "Strategy backtesting is excluded from Lonora by the owner".
- `tests/test_backtesting_excluded.py` bans the vocabulary from every shipped skill.
- VISION 17: "There is no backtesting or simulation gate on strategies."

**Cost if the owner reverses the decision.** L, about 2 to 3 weeks:
- port the engine and metrics;
- feed it MT5 history through MetaApi candle reads, whose depth is bounded by the broker;
- model costs from Lonora's live spread, commission and swap;
- update the policy, the exclusion test and the docs;
- keep maintaining it.
It would be a research tool only: never a gate, every result labelled "simulation, not results", and every metric with
"undefined + reason".

**Recommendation: do not port (TX-D1).**
- The owner asked for an agent that is expert by its skills and its own experience, and that is sections 1 and 3.
- What is worth taking needs no reversal:
  - the honesty rules of grading (real fills, a stop first on an ambiguous candle, partial wins count), used in 3.1 and 3.4;
  - optionally a Wilson interval beside "wins of n" (`calibration.ts`), as presentation only.
- The line stays where `lonora.md:191,512` puts it. A workspace study of *how the market behaved* (for example how often
  the Asia range was taken in London) is market evidence and allowed. A simulation of a strategy's trades and P&L is
  excluded.
- Grading the agent's own untaken decisions against later prices (AiChart learning recommendation 9) is a gray area under
  the same exclusion. It is not in the batches, and comes back only if the owner reverses TX-D1.

---

## 5. What we will NOT do

1. **No rule engine** and no fixed strategy pipeline (VISION 1, 5.1, 17). No checklist gate, no confluence count, no
   required pattern or detector, no scorer that picks a side. AiChart's `tradingPlaybook` weights, `scorePoi` grades and
   G1-G7 gates are not ported.
2. **No fixed thresholds as conditions.**
   - Not in skills: no minimum R:R, no "risk 1%", no ATR multiples, no news blackout minutes, no premium or discount
     fractions.
   - Not in code that interprets results: no sample floors gating a statistic, no "win rate above X", no confidence nudge.
     AiChart's DNA and shadow nudge of -0.15..+0.10 is not ported; the platform never rewrites the model's number.
3. **No limits** (P1): no caps, quotas, money limits, cooling-off periods or activity budgets, written as rules or enforced.
   A drawdown response is the agent's choice, taught as judgment.
4. **No automatic strategy pipeline.**
   - Code never turns a lesson into a method, a method into an order, or a pattern into a trade.
   - No saved-steps replay of orders (`gap-memory.md` S3).
   - No keyword-routed skill selection (AiChart's scorer).
5. **Nothing bypasses the execution door, approvals or the mode.**
   - Skills, lessons and statistics are text and read-only facts. `ExecutionService.execute` stays the only sender (6.1).
   - Trade Approval exact match, the journal, preflight, reconciliation and owner settlement are untouched (6.2-6.8).
   - `close_wake` and the weekly run read the ledger and journal only.
6. **No backtesting**, unless the owner reverses TX-D1. No backtest words in any resource.
7. **No symbol list and no venue beyond MT5** (Amendment 2). Families are recognised from contract specs. Crypto exists only
   as broker CFDs, and only if TX-D2 is yes.
8. **No disclaimers or hedging** in skills (5.3). Uncertainty is stated as a condition and a decision.
9. **No approval queue** for memory, method or skill writes (P1, P5). Versions and undo are the owner's control.
10. **No sharing of agents' private memory** beyond 3.2.4. Team statistics are ledger facts. Lesson text is shared through
    Lonora (TX-D5).
11. **No gold point constants** and no "never answer WAIT".

---

## 6. Delivery batches and owner decisions

Effort scale as in ROADMAP: **S** up to 2 developer-days, **M** 3 to 5 days, **L** 1 to 3 weeks. Total is about 5 to 7
developer-weeks.

| Batch | Content | Effort | Depends on | Owner |
|---|---|---|---|---|
| **TX1. Reading skills** | Skills 1-8 (structure, timeframes, sessions, two atlas parts, indicators, news, planning). Budget constant at 32,000. Pointer lines in `market-analysis` and `trade-management`. Core line and regenerated manifest. pyproject data files. `test_trading_skills.py`. Most of the effort is writing and expert review of about 34,000 characters. | M (upper end) | ROADMAP B22 P3-08 (catalog cut), or ship it inside TX1 | TX-D4 |
| **TX2. Risk, management, review and families** | Skills 9-17 (risk, exits, review, method intake, five families). Until TX4, `trade-review` uses `memory_write` and `market_performance_read` (the tools that exist today). | M (upper end) | TX1 (test and budget) | TX-D2 |
| **TX3. R facts and statistics** | `trade_r.py`; `close_text` facts; `statistics_block` R fields and groupings; `PerformanceRead` `group_by`/`since`/`scope`; wake `own_results`; weekly facts; policy line. Can run in parallel with TX1. | M | none | no |
| **TX4. Reviews and lessons** | `trade_review_write` and `trade_lessons_find` over `ln_semantic_memory`; recall exclusion; `knowledge_items` type; close wake requests `trade-review` and the tool; decision `lesson_ids`; intelligence chapter lines and regenerated manifest; `trade-review` and `market-structure` switched to the new tools. | L (about 1 to 1.5 weeks with the PostgreSQL tests) | TX2, TX3 | TX-D5 |
| **TX5. Lesson to method** | Weekly run: `requested_skills`, review-group facts, one question; method layout taught in `trade-review` and `method-intake`; Lonora's cross-agent carry in its brief. | M | TX4, ROADMAP B30 | TX-D3 |
| **TX6. Evals** | Scenarios in the `scripts/agent_eval` bank. An entry request: at least one expertise skill viewed, a decision recorded with invalidation, no threshold language in the reply. A close wake: a review written with a cause and both-sides retrieval. A weekly run: a method change cites review ids and numbers, or nothing changes. Live trials as in ROADMAP B18. | M | TX1-TX5, ROADMAP B13 and B18 | no |
| *(TX7, not recommended)* | Backtest research tool (section 4). | L | TX-D1 = reverse | TX-D1 |

Owner decisions, one sentence each:

- **TX-D1.** Do you keep your earlier decision that Lonora has no backtesting (recommended), or should we port AiChart's
  backtester as a research-only tool the agent may call for evidence, at about 2 to 3 weeks of work?
- **TX-D2.** Your words «لا داعي للكريبتو نهائياً» excluded crypto exchanges, so should we still ship the crypto-CFD skill
  for brokers that offer crypto as ordinary MT5 symbols (allowed by Amendment 2), or leave it out?
- **TX-D3.** When an agent refines a method you gave it, should the refinement apply at once and appear in the weekly report
  with one-word undo (recommended, as 5.6 says), or wait for your yes?
- **TX-D4.** May an agent read up to about twice as much skill text in one run (up to about 8,000 more input tokens per model
  call on your key when it does), so that structure, planning, risk and the instrument's family can be read together?
- **TX-D5.** Should agents learn from each other's trade reviews only through Lonora (recommended, keeps each agent's memory
  private under 3.2.4), or may every agent search the whole team's reviews?

---

## 7. Verification notes and what I could not confirm

Checked in code:
- Lonora skill delivery:
  - catalog and cut: `context/skills.py:189-206`, `:198`;
  - explicit and metadata requests: `:130`, `:140`;
  - no keyword routing: `resolver.py:90-107`;
  - budgets: `access.py:29`, `contracts/skills.py:67`, `snapshot.py:12-13`;
  - built-in sizes: 1,410 to 4,287 characters; catalog lines total 1,068.
- `trade-management` depends on `market-analysis`, which depends on `chart-analysis` (skill.json files,
  `tests/test_skill_runtime.py:41-45`).
- The backtest exclusion: `lonora.md:191,512,570`, `tests/test_backtesting_excluded.py:96-110`, commit `63439adc`,
  `docs/decision-readiness.md:34-55`, VISION 17.
- The close wake:
  - text `close_wake.py:68-95`;
  - Run metadata `:169-189`;
  - `requested_skills` passes through `create_run` metadata (`lonora_db/runs.py:187-200`).
- The ledger fields (`schema.py:1096-1140`; no stop or R stored). Opening request fields (`contracts/trading.py`,
  `TradeRequest.stop_loss`, `thesis_id`; annotation `reason`, `label`).
- `Instrument.path` is the broker category (`contracts/market.py:13-14`).
- Chapter sizes, computed from `lonora.md`: core 11,991, intelligence 3,732, memory 4,446.
- Domain cap `MAX_DOMAIN_CHARS // MAX_DOMAINS` (`system_policy.py:20-22,77-81`).
- AiChart:
  - `MIN_LESSON_SAMPLE = 5` (`learningLoop.ts:48`);
  - the evidence framing (`:158`);
  - the backtest removal comment (`researchEvidence.ts:624`);
  - `insertTradeLesson` has no non-test caller;
  - the atlas is 10,317 bytes, over AiChart's own 9,000-character web cap.
  - Its heading already reads "Lonora Pattern Atlas" (`agent/workspace/skills/pattern-atlas/SKILL.md`), so porting it
    is a natural fit.

Not confirmed:
- Whether `tests/test_capability_exposure.py` enumerates built-in skills. Only `test_skill_runtime.py` was read for that.
- The exact MT5 deal fields for commission and swap on every broker through MetaApi. The R method in 3.1 uses only
  `realized_pnl` (already profit + commission + swap) and deal prices and volumes.
- How often broker activity wakes carry `trigger = broker_event` besides close wakes. That is why `trade-review` is
  requested by metadata on the close and weekly Runs only, not by trigger.
- Token costs are estimates from character counts (about 4 characters per token), not measurements.


## Owner decisions taken (2026-11-26)

The owner approved the proposal («نعم موافق، ابدأ التنفيذ») and ordered that no earlier decision is cancelled by later
material («اي قرار سبق و اتخذته لايجب ان نلغيه بشان ماكتبته الان»).

| # | Decision |
|---|---|
| TX-D1 | No backtesting: the earlier decision stands. AiChart's backtester is not ported; "similar historical cases" come only from the agent's own reviewed trades (TX4). |
| TX-D2 | No crypto skill: the owner's earlier words «لا داعي للكريبتو نهائياً» stand. `family-crypto-cfd` is dropped. |
| TX-D3 | A refinement of an owner's method applies at once, appears in the weekly report and is undone with one word (5.6). |
| TX-D4 | Yes: an agent may read about twice as much skill text in one run. |
| TX-D5 | Agents learn from each other's reviews only through Lonora; each agent's memory stays private (3.2.4). |

### Additions from the owner's gold-agent specification (2026-11-26)

The owner shared a specification for a gold agent and asked which parts can be Lonora skills. Within the decisions above:

- `market-structure` names fair value gaps (FVG) and liquidity sweeps (turtle soup) explicitly.
- `family-metals` carries the gold detail: the dollar index as context, real yields, the Fed's tone from open news,
  geopolitical safe-haven demand, the London and New York sessions.
- `trade-planning` teaches two conditional scenarios (a breakout buy and a failed-break sell as two pending orders, the
  other cancelled when one triggers).
- New skill `pre-trade-check`: before sending, review the idea from the analysis side and the risk side (size, spread,
  exposure, the news ahead); the agent may consult another model (`consult_model`).
- New skill `trader-psychology`: admitting a loss plainly, patience in dead ranges ("no trade" is a decision), noticing
  tilt in one's own journal, and an end-of-day question to the owner for the trading diary when the owner wants it.
- The specification's fixed limits (a daily drawdown breaker, a cooldown after losses, a maximum of open trades, a minimum
  reward-to-risk) are taught as principles, never enforced (P1). An owner who wants personal rules writes them in the
  method, and the agent applies them as the owner's words (5.6).
- Not built, by earlier decisions: a master kill switch (Amendment 1), fast backtests (TX-D1), broadcasting to followers'
  channels (Lonora is the owner's own agent).

The library is therefore 18 skills: the 17 of section 1.2 without `family-crypto-cfd`, plus `pre-trade-check` and
`trader-psychology`.
