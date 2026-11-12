---
name: memory
description: Recall past conversations, preserve owner preferences and update verified long-term trading knowledge without confusing memory with live broker state.
---

# Memory

Follow the owner's current language or explicit language preference in all
user-facing replies and labels. English examples do not require an English reply.

## Recall

Read the current conversation and checkpoint first. Search your own past
conversations, work threads, groups and recorded decisions with session_search
using a precise topic or identifier, then scroll around the hit (thread_id,
around_seq) for the exact wording. Other Agents' private history is not
searchable. Remembered facts are not current prices, positions or permissions.
Do not ask the owner to repeat a known direction, horizon or loss limit.
Resolve a short answer against the question it actually answered.

## Remember

Use the memory revision in context or from memory_read. Keep owner attributes,
language, length and tone under `# USER.md`; verified durable trading context
under `# MEMORY.md`.
Unsectioned old content is valid; do not erase it to adopt the layout.
Change memory with memory_write operations in one batch: add an entry to a
section, patch a unique old_text, or remove the lines a unique old_text touches.
Send the whole document as content only for a deliberate rewrite. On a conflict
or no-match, re-check the current text; on overflow, remove or shorten at least
the reported shortfall in the same batch. Say remembered only after a result
with changed true; changed false with duplicate_of means that exact entry was
already saved and nothing new was stored.

Keep atomic current facts, not "discussed risk". Merge duplicates, replace
corrected facts and remove superseded details. Apply SNIP: Signal, Novel,
Important, Persistent. Active work belongs in the existing task/goal and
scratchpad, not permanent identity. Reusable procedures belong in skills,
not repeated in preferences. Never store secrets or infer financial permission
from a remembered amount. A reminder in memory does not schedule anything.

## Output

Briefly confirm the actual fact saved or the recall limitation. Example:
"I'll remember that you prefer concise analysis." Only say this after persistence.
