# Market Watch

## Purpose
Lonora market-watch workflow.

## When to activate
Use for the matching current task or durable trigger; never infer financial authority from relevance.

## When not to activate
Unrelated tasks, unavailable required tools, failed dependencies or exhausted context budget.

## Preconditions and required evidence
Use current owner-scoped tool results, exact broker identities and observation times. Missing data remains unavailable.

## Workflow and tool usage
Persist watches through watch_create and inspect with watch_list. Use the exact bound symbol and account, condition, expiry and meaningful trigger. Trigger wakes analysis; it does not authorize execution. Read fresh evidence after waking and return WAIT on missing/stale data. Monitoring continues without a browser; do not use model loops or client timers.

## Decision rules and failure handling
Inspect machine status and stable error code. Do not hide unavailable evidence or retry ambiguous financial mutations. WAIT is a valid result.

## Anti-patterns
No invented success, stale actionable recommendations, authority escalation, unbounded context or browser-only durable state.

## Output contract
Return concise sourced findings, actions actually completed, remaining uncertainty, and persisted resource/artifact identities when available.

## Related skills
None required.
