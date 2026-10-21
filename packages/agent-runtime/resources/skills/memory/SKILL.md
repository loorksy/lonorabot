---
name: memory
description: Recall past conversations, preserve owner preferences and update verified long-term trading knowledge without confusing memory with live broker state.
---

# Memory

## Recall

Read the current conversation and checkpoint first. Search past messages with
search_internal using a precise topic, date or identifier. Inspect the matching
context. Remembered facts are not current prices, positions or permissions.
Do not ask the owner to repeat a known direction, horizon or loss limit.
Resolve a short answer against the question it actually answered.

## Remember

Read memory_read and its revision before changing anything. Keep owner attributes,
language, length and tone under `# USER.md`; verified durable trading context
under `# MEMORY.md`. These headings share the existing document and revision.
Unsectioned old content is valid; do not erase it to adopt the layout.
Use memory_write with the full merged document and current version. Re-read on
conflict; say remembered only after a successful write.

Keep atomic current facts, not "discussed risk". Merge duplicates, replace
corrected facts and remove superseded details. Apply SNIP: Signal, Novel,
Important, Persistent. Active work belongs in the existing task/goal and
scratchpad, not permanent identity. Reusable procedures belong in skills,
not repeated in preferences. Never store secrets or infer financial permission
from a remembered amount. A reminder in memory does not schedule anything.

## Output

Briefly confirm the actual fact saved or the recall limitation. Example:
"سأتذكر أنك تفضّل تحليلًا مختصرًا بالعربية." Only say this after persistence.
