---
name: market-watch
description: Persist event-driven market monitoring and resume analysis on meaningful changes without model calls per tick.
---

# Market Watch

Follow the owner's current language or explicit language preference in all
user-facing replies and labels. English examples do not require an English reply.

## Steps

1. Recover the same objective and exact market; inspect watch_list before
   creating duplicate monitoring.
2. Derive a meaningful condition from current evidence or the owner's explicit
   threshold. Persist it with watch_create, actual account/symbol, expiry and
   continuation objective. Never invent a threshold just to fill a schema.
3. A trigger wakes analysis, never execution directly. Read fresh market, account,
   positions and goal before deciding the next step.
4. Use continuous work for ongoing monitoring. Before yielding, use task_wait
   on the actual watch, recovery or justified timer; a reply does not finish
   that responsibility. Include a brief useful result with the wait when
   warranted. Use an existing routine for a requested time/interval. Memory
   entries are not schedules.
5. Respect cancellation and health suspension. Do not poll the model or promise
   uninterrupted monitoring. Keep repeated no-change checks quiet.

## Output

Confirm the actual saved condition briefly. Example:
"I'll return when the specified condition is met." Only say this after persistence succeeds.
Monitoring grants no financial authority.
