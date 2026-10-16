# Market Analysis

## Purpose
Lonora market-analysis workflow.

## When to activate
Use for the matching current task or durable trigger; never infer financial authority from relevance.

## When not to activate
Unrelated tasks, unavailable required tools, failed dependencies or exhausted context budget.

## Preconditions and required evidence
Use current owner-scoped tool results, exact broker identities and observation times. Missing data remains unavailable.

## Workflow and tool usage
Before reading an account, discover saved connections with list_accounts. Pass its exact connection_id as account_id to broker tools; login is the broker's actual account number; broker/server/name identify the user's broker. The adapter provisioning identifier is configuration, never the broker account number. broker_sessions_not_found means the supplied internal connection ID was not found for this owner; it does not prove no accounts are saved or that MetaApi rejected credentials. Refresh the directory rather than declaring the account disconnected. A saved connection is not proof of live connectivity: use account_read to verify actual data. Never expose tokens or secret identifiers.

When no immutable trading market is bound, for a single-symbol recommendation first discover the exact symbol with market_symbols, then request market_instrument, market_quote and market_candles for that same connection and symbol. When a market is bound, use that symbol directly. Gold may have broker suffixes or a different broker name; never guess or strip them. Letter case alone is not a different symbol: if market_symbols has one match ignoring case, use that exact spelling and do not ask the owner to retype it. A failure loading specifications for all instruments does not establish that a particular symbol's quote or candles are unavailable. Tool failures are independent: inspect their actual error codes. Candles use timeframes such as 15m or 1h, not M15 or H1. If the owner requests a chart image, call chart_snapshot using that verified symbol/timeframe and return the resulting artifact; do not declare chart images unsupported without trying the tool. Clearly distinguish a historical snapshot from a live quote. Without current quotes and sufficient candles, do not turn remembered price levels into a current actionable recommendation or invent entries/stops/targets; report the actual missing data and error instead.

## Decision rules and failure handling
For cross-market claims use market_relationship_record with two exact broker symbols and an explicit timeframe/window. It measures identical closed-bar intervals against a separate recent baseline; missing bars, flat prices and stale history may make the result unavailable or unreliable. Use market_relationship_read for saved evidence, and pass relevant relationship_ids into market_decision_record so stale/unreliable relationship evidence forces WAIT. Relationship sign/strength is measured association, never causation or a standalone BUY/SELL rule. A specialist may compare its bound symbol to a related market on its same account; this read-only evidence does not change its symbol binding or financial authority.

Inspect machine status and stable error code. Do not hide unavailable evidence or retry ambiguous financial mutations. WAIT is a valid result.

## Anti-patterns
No invented success, stale actionable recommendations, authority escalation, unbounded context or browser-only durable state.

## Output contract
Return concise sourced findings, actions actually completed, remaining uncertainty, and persisted resource/artifact identities when available.

## Related skills
chart-analysis
