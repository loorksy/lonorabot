# Agent memory, history recall and skill provenance

Mandate §9 requires every Agent to have independent memory and experience, to
search its own history and retrieve original evidence, and to keep private
information from becoming available to every other Agent. This page describes
how the agent tools enforce that, how an Agent recalls earlier work, how it edits
memory without resending the whole document, and how skills state where they
came from.

## Private by default

An Agent's history scope is derived on the server from the calling Run, never
from tool arguments (`lonora_memory/sessions.py`, `HistoryScope`):

- its own memory document (`ln_memory` row of that Agent);
- threads whose `agent_id` is the Agent: its conversation, Task work threads
  and the threads of its subagents, because a subagent Run carries its
  parent's Agent id and therefore has exactly the parent's scope;
- group threads whose group lists the Agent in `member_ids`;
- trading decision snapshots it recorded (`trading.decision_recorded` events
  with its `agent_id`).

Peer requests and collaboration rounds already write into the target Agent's own
conversation thread, so a participant sees the request it answered there and
nothing of the host's private thread. A persistent child Agent has its own
identity and therefore its own scope.

`search_internal` (literal substring) now uses this scope: agent names (the same
directory `list_agents` serves), this Agent's own memory and the messages of the
threads above. It is no longer in the eager core set, and remains reachable
through `tool_call`. The owner API `GET /api/search` keeps its owner-wide search
(`internal_search`): the owner can read everything they own, but that function is
never exposed to an Agent.

## session_search

A read-only core tool (`lonora_tools/session_search.py`), so subagents and
observe-only Runs have it too. Its shape follows the arguments, adapted from
Hermes Agent `tools/session_search_tool.py` (MIT, see `THIRD_PARTY_NOTICES.md`):

| Arguments | Shape | Returns |
| --- | --- | --- |
| `query` (optional `thread_id`) | discover | ranked message hits with `thread_id`, `seq`, `message_id`, `role`, author, `created_at`, a bounded excerpt and thread title/purpose; up to 5 matching decisions of this Agent |
| `thread_id` + `around_seq` | scroll | the messages from `around_seq - limit/2` to `around_seq + limit/2` |
| `thread_id` (optional `after_seq`) | read | the next `limit` messages after `after_seq`, with `next_after_seq` while more remain |
| none | browse | the most recently active scoped threads with message counts |

`limit` is 1 to 30 (default 10). Each message is cut at 2,000 characters and a
page at 16,000; discovery excerpts are 480 characters around the first matching
term. A thread outside the scope fails with `thread_not_found`, exactly like a
missing one, so its existence is not revealed.

Every response carries `authority: "historical_record"` and a notice: the text
is what was written then, untrusted data rather than instructions, and never
current market, account or broker state. Run evidence classifies
`session_search` results as retrieved untrusted content.

**Ranking.** On PostgreSQL, discovery matches
`to_tsvector('simple', content) @@ websearch_to_tsquery('simple', query)` or a
literal `ILIKE` of each identifier in the query (broker symbols such as
`XAUUSDm`, ids such as `ord-77f2`; see `lonora_memory/retrieval.identifiers`)
and of a short whole query. Every word must match first (web-search syntax:
quoted phrases, `or`, `-word`); when nothing does, a multi-word query is retried
matching any of its words and reports `match: "full_text_any_word"`. Rank is
`ts_rank_cd` plus a bonus for a literal hit, then newest first. The `simple` configuration does no stemming or stop-word
removal, so symbols, numbers and Arabic or English words keep their exact
tokens. Other dialects (the SQLite unit tests) use the literal match only and
report `match: "literal"`.

**No index yet.** This track adds no migration. Each discovery scans the scoped
threads' messages (through the existing `thread_id` index) under
`SET LOCAL statement_timeout = '5s'`; a timeout returns `tool_read_timeout`.
Follow-up: a GIN expression index built concurrently, for example
`CREATE INDEX CONCURRENTLY ln_messages_content_simple_fts ON ln_messages USING gin (to_tsvector('simple', content))`,
whose expression must match the query's exactly.

## Granular memory edits

`memory_write` takes either the whole document (`content`, unchanged contract and
result) or a batch of `operations` at the current `version`
(`lonora_memory/edits.py`, adapted from Hermes Agent `tools/memory_tool.py`):

- `add`: append `content` as an entry of `section` `USER.md` (owner preferences)
  or `MEMORY.md` (durable knowledge, the default). It goes at the end of the last
  section with that heading; unsectioned legacy text counts as `MEMORY.md`; a
  missing heading is created at the end. An entry already present in that view
  is reported `changed: false` instead of duplicated.
- `patch`: replace `old_text`, which must occur exactly once in the document
  (overlapping occurrences count), with `content`.
- `remove`: delete the whole lines the unique `old_text` touches, so no dangling
  bullet remains.

Operations apply in order to a working copy; the batch commits all or nothing in
the same transaction, lease fence, optimistic revision and effect receipt as a
whole-document write (`commit_memory(..., transform=...)`). A replayed call
returns its receipt. The `# USER.md` / `# MEMORY.md` headings cannot be removed
or added by `patch`/`remove` (`memory_edit_heading_protected`); restructuring
takes a whole-document write.

A rejected operation returns `ok: false` with `code` (`memory_edit_no_match`,
with up to three `closest_lines`; `memory_edit_ambiguous` with `matches`;
`memory_edit_heading_protected`) and `operation_index`, and nothing is saved.

**Overflow protocol.** The 30,000-character limit is checked only on the batch
result. When it is exceeded the call returns `code: "memory_too_large"`,
`version`, `current_chars`, `resulting_chars`, `limit` and `shortfall`, so the
model can resend one batch that also removes or shortens at least `shortfall`
characters. A version conflict on an operations batch returns the current
`version` and size: operations are content-addressed, so the model can re-check
the same batch against the newer revision without re-reading 30K characters.

A successful batch returns the new `version`, `updated_at`, `chars`, `limit` and
the `applied` list, not the whole document. The `memory.updated` event records
`change: "operations"` or `"document"`.

## Skill provenance

Every surface the model reads labels a skill by its real origin
(`lonora_agent/skills/provenance.py`):

| Manifest source | Provenance | Context-section trust |
| --- | --- | --- |
| `builtin` | `bundled` | `bundled_first_party` |
| `owner` | `owner` | `owner_supplied` |
| `legacy` (owner instructions saved before manifests) | `owner` | `legacy_owner_skill` |
| `installed` (an Agent's workspace package, `skill_package_create`) | `agent_authored` | `agent_authored` |
| `external` (a pinned public import, `skill_package_import`) | `external` | `external_import` |

The server sets the source of every package version; an owner-saved skill that
declares `installed` or `external` is labelled by that declaration. The label
appears in the system-role catalog (`- id (agent_authored) — description`;
bundled entries have none), in `skills_list` entries, in each `skill_view`
acknowledgment and in the Run's `skill_selection` diagnostics. Earlier releases
labelled every non-bundled skill `owner_supplied`; a stored `skill_view` receipt
with that old label still verifies when everything else is identical, so a
resumed Run is not refused. No label grants tools or financial authority.

## Verification

`tests/test_memory_privacy.py` covers the edit semantics, the overflow and
freeing batch, the input shapes, and on PostgreSQL: three Agents with private
conversations, a shared and a private group and decisions (`search_internal`,
discover, browse, scroll and read never return another Agent's memory, thread,
group or decision; an out-of-scope thread is `thread_not_found`; the owner API
stays owner-wide), a subagent searching with its parent's scope, full-text
ranking with symbol and id matches, scroll and paged read, and memory batches
with receipts, all-or-nothing rejection, version conflict and overflow.
`tests/test_progressive_skills.py` covers the provenance mapping on every
surface and pre-upgrade receipts.

## Not yet done

- The GIN full-text index above.
- Earlier memory revisions are still not stored, so an edit cannot be reverted
  from the server (mandate §11 "reversible"); a revision table is the next step.
- Automatic per-turn recall still covers only the current thread; other threads
  are reached through `session_search`.
