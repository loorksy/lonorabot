# Built-in trading skills

Lonora ships twenty-five built-in skills under `packages/agent-runtime/resources/skills/`.
Seven are procedures (how to use the tools): `chart-analysis`, `market-analysis`,
`market-watch`, `memory`, `position-management`, `research` and `trade-management`.
Eighteen are trading knowledge: what a professional trader weighs, written as judgment
the agent may apply, never as a rule it must follow (VISION 5.1, 5.2, P1).

| Group | Skills |
| --- | --- |
| Reading the market | `market-structure`, `multi-timeframe`, `sessions-and-time`, `chart-patterns`, `candles-and-breakouts`, `indicators-as-context`, `news-and-macro` |
| Deciding and managing | `trade-planning`, `risk-and-sizing`, `pre-trade-check`, `exits-and-management`, `trader-psychology` |
| Learning | `trade-review`, `method-intake` |
| Instrument families | `family-forex`, `family-metals`, `family-indices`, `family-energy` |

There is no crypto skill (owner decision TX-D2) and nothing about backtesting
(TX-D1; `tests/test_backtesting_excluded.py`). The plan and the owner's decisions are in
[the proposal](proposals/trading-expertise.md); this document covers its batches TX1 and
TX2. The close and weekly wakes do not request `trade-review` yet (TX4, TX5), so the
model reads it from the catalog like any other skill.

## How the model reaches them

- **The model chooses.** Each skill's description is one line in the skill catalog in
  the system role, and the model reads a body with `skill_view`. Nothing selects a
  trading skill by keyword; the routes are an explicit `[skill:id]`, `requested_skills`
  in run metadata, or a run trigger (`skills/resolver.py`).
- **Pointers.** `market-analysis` (step 4) and `trade-management` (step 2) say to view the
  trading skills a decision needs, and the core prompt's trader's-judgment chapter
  (`resources/system/lonora.md`) has one line saying the same.
- **Room.** One Run may hold 32,000 characters of active skill text (`ACTIVE_BUDGET` in
  `skills/resolver.py`, owner decision TX-D4): the trade procedures plus about four
  trading skills. It is a context size, not a trading limit.
- **Catalog.** Catalog lines are kept whole within 6,000 characters
  (`context/skills.py` `catalog_lines`); any past that room are counted as
  "N more: use skills_list", never cut mid-line.
- **No authority.** Every trading skill is `risk_class: read_only` with no required
  tools, capabilities or dependencies, so it is eligible in every scope, observe-only
  and helper runs included, and it grants nothing (`authority_granted: False`).

## What every trading skill must hold

`tests/test_trading_skills.py` enforces the authoring contract; run one skill with
`pytest tests/test_trading_skills.py -k <id>`.

- A description that starts "Use when", names the topic in English and in Arabic (so an
  Arabic request finds it) and stays within 200 characters.
- An English body of 5,000 characters or less with the headings "What you are
  deciding", "What to check", "Weak when" and "Saying it" (or "How to say it"), plus at
  least one topic heading.
- Only tool names, argument names and values that the tool registry defines; fields and
  concepts in plain words. No broker symbol: the agent finds the broker's own names with
  `market_symbols`, and a family skill starts from the contract specification
  (`market_instrument`).
- Timeframes as the tools take them (`15m`, `1h`, `4h`, `1d`), never `M15` or `H1`.
- No rule language (caps, gates, minimum reward to risk, a stop after N losses, a kill
  switch). A number, whether written in digits or spelled ("two hours", "half size"),
  appears only in a passage marked "Illustration".
