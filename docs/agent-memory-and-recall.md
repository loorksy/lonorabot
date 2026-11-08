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

`subagent_inspect` follows the same rule for Runs
(`lonora_agent/collaboration/subagents.py`, `delegated_by`): it returns a Run
only when the Run belongs to the calling Agent (its own Runs and its subagents,
which carry its Agent id) or when the Run's `parent_run_id` chain reaches one
of the calling Agent's Runs (a peer or collaboration request it sent, and
anything that Run delegated). Any other Run of the owner, such as another
Agent's private Run whose id surfaced in a group thread, is `run_not_found`,
exactly like a missing one.

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

**Ranking.** On PostgreSQL discovery runs separate bounded statements and
merges them in Python (`lonora_memory/sessions.py`):

1. *Whole history.* `to_tsvector('simple', content) @@ (websearch_to_tsquery('simple', query) || identifier tokens)`
   over every scoped message, ordered by `ts_rank_cd` against the query's words.
   Every word must match (web-search syntax: quoted phrases, `or`, `-word`), or
   one identifier in the query as its own full-text token (broker symbols such
   as `XAUUSDm`, ids such as `ord-77f2`; see `lonora_memory/retrieval.identifiers`),
   so a symbol inside a prose question still finds old messages. The predicate
   has no `ILIKE` arm, so the GIN index below serves it.
2. *Recent window.* When statement 1 finds nothing for a multi-word query, or
   exceeds its 4 s budget, the 5,000 newest scoped messages (each thread
   contributes at most its 5,000 newest through the `(thread_id, seq)` index) are
   searched once: every word or identifier token first, otherwise any word
   (`match: "full_text_any_word"`). When the results come from this window, or
   statement 1 timed out, the response says `searched: "recent_messages"` with
   a `coverage_note`; otherwise `searched: "all_history"`.
3. *Literal identifiers.* Each identifier (never the prose query) is matched
   with `ILIKE` in the same recent window, for substrings the tokenizer does not
   separate (`XAUUSD` inside `XAUUSDm`). A row found only this way reports
   `match: "literal"`.

Results order: every-word rows, then identifier-token rows, then the rest; in
each tier a literal identifier hit first, then rank, then newest. Every
response carries `recent_window`. The `simple` configuration does no stemming
or stop-word removal, so symbols, numbers and Arabic or English words keep their
exact tokens. Decisions use one statement over the Agent's 5,000 newest
decision events with the same tiers. A statement savepoint keeps the
transaction usable after a timeout; the windowed statements have a 5 s timeout
and return `tool_read_timeout` if they ever exceed it. Other dialects (the
SQLite unit tests) use a literal match of the query terms and report
`match: "literal"`.

**Measured size limits (no index).** On the development container (PostgreSQL
16.15, parallel workers on, messages of about 420 characters in one Agent
conversation) the whole-history statement took about 0.85 s at 50,000, 1.5 s
at 100,000 and 3.0 s at 200,000 scoped messages, and passed its 4 s budget at
about 270,000; at 300,000 every query answered from the recent window in about
4.3 s, so discovery degrades instead of failing. Slower hardware or concurrent
load lowers these sizes (an earlier review measured 3.9 s at 50,000 with the
previous combined `OR ILIKE` predicate).

**Follow-up: index.** This track adds no migration. The index that statement 1
uses, verified with `EXPLAIN` in `tests/test_memory_privacy.py`, is

```sql
CREATE INDEX CONCURRENTLY ln_messages_content_simple_fts
  ON ln_messages USING gin (to_tsvector('simple'::regconfig, content));
```

Its expression must match the query's exactly. At 300,000 messages it brought
selective queries (a symbol, an id, a two-word phrase) to 10–70 ms. A word that
appears in most messages still costs seconds (2.8 s for a word in 176,000 of
300,000 messages) because `ts_rank_cd` re-parses every matching message; a
stored generated column
`content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED`
with a GIN index ranked the same word in 0.11 s, at the price of a table
rewrite. Literal substrings beyond the recent window need `pg_trgm`
(`CREATE INDEX ... USING gin (content gin_trgm_ops)`) before the identifier
`ILIKE` can cover the whole history.

## Granular memory edits

`memory_write` takes either the whole document (`content`, unchanged contract and
result) or a batch of `operations` at the current `version`
(`lonora_memory/edits.py`, adapted from Hermes Agent `tools/memory_tool.py`):

- `add`: append `content` as an entry of `section` `USER.md` (owner preferences)
  or `MEMORY.md` (durable knowledge, the default). It goes at the end of the last
  section with that heading; unsectioned legacy text counts as `MEMORY.md`; a
  missing heading is created at the end. Only an exact duplicate is skipped: a
  one-line entry equal to a whole line of that view, or a multi-line entry
  equal to a whole block (bounded by blank lines, list items or headings), with
  surrounding whitespace ignored. It is reported `changed: false` with
  `duplicate_of`. A shorter fact that is a prefix or substring of a stored one
  (`- Max daily loss 50` beside `- Max daily loss 500 USD`) is a new entry. An
  entry may not contain a `# USER.md` / `# MEMORY.md` view heading
  (`memory_edit_heading_protected`), so text bound for one view cannot open the
  other.
- `patch`: replace `old_text`, which must occur exactly once in the document
  (overlapping occurrences count), with `content`.
- `remove`: delete the whole lines that hold the unique `old_text`'s
  non-newline characters, so no dangling bullet remains. A newline at either end
  of `old_text` only bounds the match: `"\n- stale fact"` removes that line,
  never the line before it.

Operations apply in order to a working copy; the batch commits all or nothing in
the same transaction, lease fence, optimistic revision and effect receipt as a
whole-document write (`commit_memory(..., transform=...)`). A replayed call
returns its receipt. The `# USER.md` / `# MEMORY.md` headings cannot be removed
or added by any operation (`memory_edit_heading_protected`; `add` may only
create the missing heading of its own section); restructuring takes a
whole-document write.

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

A successful batch returns `changed: true`, the new `version`, `updated_at`,
`chars`, `limit` and the `applied` list, not the whole document. The
`memory.updated` event records `change: "operations"` or `"document"`. A batch
that changes nothing (only duplicate adds, a patch to identical text, or edits
that cancel out) returns `changed: false` with the current revision: the
version is not bumped, no `memory.updated` event is emitted, and the receipt
still makes a replay return the same result. A whole-document write keeps its
original contract and always commits a new revision.

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
ranking with symbol and id matches, the windowed any-word and literal arms,
the timeout fallback through a savepoint, an `EXPLAIN` proving the
whole-history statement can use the GIN expression index, scroll and paged
read, and memory batches with receipts, a no-op batch that keeps its revision,
all-or-nothing rejection, version conflict and overflow. The pure cases also
cover exact-entry duplicates (a shorter prefix fact is still saved), line spans
of `remove` with leading, trailing and multi-line `old_text`, and heading
protection for `add` and `patch`.
`subagent_inspect` is tested for its own subagent, a delegated peer Run and a
Run that one delegated in turn, and refuses another Agent's private Run and,
from the delegated side, the requester's Runs.
`tests/test_progressive_skills.py` covers the provenance mapping on every
surface and pre-upgrade receipts.

## Not yet done

- The GIN full-text index (and, for common words, a stored `tsvector` column)
  above; until then the whole-history statement degrades to the recent window
  beyond a few hundred thousand scoped messages.
- Earlier memory revisions are still not stored, so an edit cannot be reverted
  from the server (mandate §11 "reversible"); a revision table is the next step.
- Automatic per-turn recall still covers only the current thread; other threads
  are reached through `session_search`.
