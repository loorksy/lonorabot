---
name: market-analysis
description: Analyze a broker market with fresh quotes, candles and instrument specifications; separate facts, interpretation and conditional scenarios.
---

# Market Analysis

## When to use

For analysis, an entry plan, market review or continuation after a meaningful
change. Read existing intent and limits; do the requested reversible review.

## Steps

1. Use the specialist's bound account and exact symbol. For a Personal Agent
   discover connections with list_accounts and instruments with market_symbols.
   Use connection_id internally; actual broker/login/server describe the account
   publicly. A MetaApi UUID is not the account number.
2. Read market_instrument, market_quote and sufficient market_candles for that
   account/symbol. Preserve suffixes and exact broker case. Use actual timeframes
   such as 15m or 1h. Never invent a pair or choose a default market.
3. Check timestamps and closed versus developing candles. Quote, history and
   chart failures are distinct; inspect the failed boundary before declaring
   the entire account unavailable. Never manufacture missing observations.
4. Read chart-analysis when charts or server indicators help. Derive levels,
   entry, invalidation and proposed size from real evidence and owner limits.
   Use market_structure when confirmed swing anchors or alternative trendlines
   help the analysis. Its strict left/right windows reject equal extrema, and a
   pivot becomes known only after the confirming right bars close. Keep pivot
   time distinct from confirmation time; a live candle cannot confirm a swing.
   Compare the returned alternatives and closed-close breaks using the declared
   absolute-price tolerance. They are measured hypotheses, not entry signals.
   Their anchors can feed existing chart annotations; inspect the resulting
   scene before claiming a drawing is present. Never imply the analyzer checked
   broker sessions, every formation, or strategy profitability.
5. Build the requested plan, remembering the chosen side and any explicit loss ceiling.
   If evidence contradicts the side, explain and WAIT instead of asking again.
6. Persist actionable evidence through market_decision_record when relevant.
   Cross-market claims use market_relationship_record/read over aligned closed
   bars and a baseline; association is not causation or a standalone entry rule.

## Output

Give the finding, evidence time, decisive uncertainty and one useful next action.
Use wait_for_input only for a genuinely missing owner decision, with suitable
choices and free text. Do not expose resource IDs or narrate internal operations.
Example: "البيع لم يتأكد بعد؛ أحتاج إغلاقًا دون المستوى المرصود قبل الدخول."
Missing/stale evidence means WAIT, never an invented price or guaranteed return.
