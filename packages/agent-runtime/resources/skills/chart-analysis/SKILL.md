# Chart Analysis

## Purpose
Lonora chart-analysis workflow.

## When to activate
Use for the matching current task or durable trigger; never infer financial authority from relevance.

## When not to activate
Unrelated tasks, unavailable required tools, failed dependencies or exhausted context budget.

## Preconditions and required evidence
Use current owner-scoped tool results, exact broker identities and observation times. Missing data remains unavailable.

## Workflow and tool usage
Load server-side chart state and broker candles. Validate timeframe and exact series identity. Use server-calculated supported indicators as evidence. Persist annotations/artifacts. A snapshot is a fixed image; a cloud chart streams updates. If asked for an image, try chart_snapshot and return the actual artifact, never a fabricated attachment.

## Decision rules and failure handling
Inspect machine status and stable error code. Do not hide unavailable evidence or retry ambiguous financial mutations. WAIT is a valid result.

## Anti-patterns
No invented success, stale actionable recommendations, authority escalation, unbounded context or browser-only durable state.

## Output contract
Return concise sourced findings, actions actually completed, remaining uncertainty, and persisted resource/artifact identities when available.

## Related skills
None required.
