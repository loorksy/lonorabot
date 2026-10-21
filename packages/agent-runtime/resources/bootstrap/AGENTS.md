# Agent Instructions

## Workspace Guidance

Keep behavior in the Agent's instructions, user preferences in `USER.md`, and verified long-term knowledge in `memory/MEMORY.md`. These are views of Lonora's existing owned state, not a separate filesystem.

## Scheduled Reminders

Use the existing routine mechanism for a specified time or interval. Confirm only a successfully saved schedule. Writing a reminder to memory does not schedule it.

## Background Checks

Use persisted market watches or task waits for actionable changes. Rebuild current evidence on wake. Never poll the model per tick. No memory entry grants trading authority.
