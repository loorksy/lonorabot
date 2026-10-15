# Trading Goal

## Purpose
Lonora trading-goal workflow.

## When to activate
Use for the matching current task or durable trigger; never infer financial authority from relevance.

## When not to activate
Unrelated tasks, unavailable required tools, failed dependencies or exhausted context budget.

## Preconditions and required evidence
Use current owner-scoped tool results, exact broker identities and observation times. Missing data remains unavailable.

## Workflow and tool usage
Use the existing durable TradingGoal steps and decision journal. Read current goal, exact scope, current account and evidence before adapting a plan. Wait through durable watches or scheduled wakes; do not poll with repeated LLM turns. Respect pause, cancellation, lease fencing and approval boundaries. Goal persistence is not authorization for autonomous execution.

## Decision rules and failure handling
Inspect machine status and stable error code. Do not hide unavailable evidence or retry ambiguous financial mutations. WAIT is a valid result.

## Anti-patterns
No invented success, stale actionable recommendations, authority escalation, unbounded context or browser-only durable state.

## Output contract
Return concise sourced findings, actions actually completed, remaining uncertainty, and persisted resource/artifact identities when available.

## Related skills
trade-management
