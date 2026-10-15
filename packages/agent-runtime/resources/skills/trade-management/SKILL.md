# Trade Management

## Purpose
Lonora trade-management workflow.

## When to activate
Use for the matching current task or durable trigger; never infer financial authority from relevance.

## When not to activate
Unrelated tasks, unavailable required tools, failed dependencies or exhausted context budget.

## Preconditions and required evidence
Use current owner-scoped tool results, exact broker identities and observation times. Missing data remains unavailable.

## Workflow and tool usage
Before reading an account, discover saved connections with list_accounts. Pass its exact connection_id as account_id to broker tools; login is the broker's actual account number; broker/server/name identify the user's broker. The adapter provisioning identifier is configuration, never the broker account number. broker_sessions_not_found means the supplied internal connection ID was not found for this owner; it does not prove no accounts are saved or that MetaApi rejected credentials. Refresh the directory rather than declaring the account disconnected. A saved connection is not proof of live connectivity: use account_read to verify actual data. Never expose tokens or secret identifiers.

Pending orders require buy_limit, sell_limit, buy_stop or sell_stop and an explicit positive price; buy/sell submit immediate market trades. Do not substitute a market trade when the user requests a pending order. Ask for any missing entry price/volume/side and verify the price is on the correct side of the fresh bid/ask. Preserve existing SL/TP when the owner asks to change just one field. Distinguish a broker rejection from an uncertain transport result. Confirm success only from a confirmed execution result, and use account_read/journal to verify order or position identity. Never invent the broker name or login from a MetaApi UUID. A chart_snapshot is a fixed image; to monitor live updates open the persistent chart.


Read global controls and current broker state. Validate exact instrument, quantity min/max/step and price tick/stops. trade_execute creates an immutable approval proposal. Inspect actual confirmed broker receipt; reconcile ambiguous operations through the journal without resending.

## Decision rules and failure handling
Inspect machine status and stable error code. Do not hide unavailable evidence or retry ambiguous financial mutations. WAIT is a valid result.

## Anti-patterns
No invented success, stale actionable recommendations, authority escalation, unbounded context or browser-only durable state.

## Output contract
Return concise sourced findings, actions actually completed, remaining uncertainty, and persisted resource/artifact identities when available.

## Related skills
market-analysis
