Superseded by VISION.md

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
- the owner profile, which every Agent reads (below), not a peer's memory;
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

A supervisor also reads the threads, decisions, memory and Runs of the agents it
supervises now, through the owner's visible, revocable supervision grant
(`docs/supervision.md`; Lonora holds one over every agent by default). Each such
result names the agent and is labelled untrusted; without a grant everything below
is unchanged.

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

## One owner profile, shared by every Agent

What the owner says about himself (language, reply length, tone, how to reach
him, quiet hours, standing rules) is stored once, in the owner profile, and every
Agent reads it (`ln_owner_profile`, `lonora_db/owner_profile.py`). Each Agent's
own document keeps only its private views:

| View | Where | Who writes it | How a Run sees it |
| --- | --- | --- | --- |
| `USER.md` | `ln_owner_profile.content`, one per owner | the owner (Settings ← الملف الشخصي, `/app/owner`) or any Agent from the owner's message | `owner_preferences` context section, every Run of every Agent |
| `MEMORY.md` (and older unsectioned text) | the Agent's `ln_memory` row | the Agent or the owner | `memory` context section, that Agent only |
| `OPERATING.md` | the Agent's `ln_memory` row | the Agent (its own working method) or the owner | `operating_notes` context section, that Agent only |

The structured part of the profile is the reply language
(`ln_owner_profile.reply_language`: Arabic, English, or none = the language of
the owner's latest message) and the reach-me preference. The reach-me preference
is the existing incoming-call policy record with a `channel` (activity only,
notify, message or call; see `docs/incoming-attention.md`), so the call gate and
the profile can never disagree.

**Reading.** `memory_read` returns the Agent's own view (`MEMORY.md` and
`OPERATING.md`) with its `version`, and `owner_profile` with its
`profile_version` and structured preferences. The context builder
(`lonora_agent/context/memory.py`) puts three labelled sections in the user-role
context message, never the system role: `owner_preferences` (trust
`owner_attributed`, priority 90), `operating_notes` (trust `agent_authored`,
priority 82), `memory` (priority 80) and, when the owner kept any for this Agent,
`owner_knowledge` (trust `owner_attributed_untrusted`, priority 78). The owner
preferences rank below the system policy and the owner's own messages and above
retrieved content; none of these sections grants tools, permissions or financial
authority. `owner_knowledge` holds this Agent's light goals (`ln_agent_goals`:
title, description, done) and knowledge links (`ln_knowledge_links`: title, URL,
note) from «الأهداف» and «المعرفة»: at most 20 of each, newest first, every field
cut at 400 characters except the URL, which stays whole (at most 2,000 by contract).
Its fixed note is English; the owner's text is carried as data in its own language.
Under a small window sections shed lowest priority first, so `owner_knowledge`
goes before `memory`, `operating_notes` and `owner_preferences`. Every body is JSON
escaped like `profile_context`. The profile is capped at 8,000 characters
(`OWNER_PROFILE_CHAR_LIMIT`); if a merged profile is longer, its newest lines are
injected with a note asking the Agent to summarize it. Conversation locale for
server-rendered cards (`conversation_locale`) uses the profile's reply language
first. Voice context carries the same profile and reach-me preference.

**Writing.** `memory_write` operations with `section: "USER.md"` change the owner
profile; `MEMORY.md` and `OPERATING.md` operations change the Agent's own
document. One batch may touch both; it commits in one transaction under one
receipt and lease fence, all or nothing. `version` is the Agent's own revision and
`profile_version` (optional, 0 = current) the profile's; operations are
content-addressed, so they are checked against whatever is stored when the write
holds the document's lock. Every write reads the row again under that lock
(`populate_existing`), never an earlier read, so two Agents answering one group
message, or an Agent and the owner saving in Knowledge, both keep their lines and
get distinct versions; a stale explicit version is `version_conflict`. A profile
write needs a Run that answers the owner's message (`owner_message_id`): a wake,
peer or task Run gets
`owner_profile_requires_owner_message` and nothing is saved, so text an Agent
read elsewhere can never become an owner preference. `owner_preferences_update`
(long-tail, reached through `tool_call`) sets the reach-me channel, reply
language, quiet hours and timezone under the same rule. A whole-document write
replaces only the Agent's own document and may not contain a `# USER.md` heading
(`memory_user_section_moved`); the owner API refuses one too.

**Authority statements.** `OPERATING.md` and the owner profile are followed as
guidance, so a write that adds an authority statement to them is refused whole
(`memory_authority_claim_refused`, `lonora_memory/guard.py`): phrases that skip
or bypass approval, claim authorization to trade, say the owner approved, ignore
or override limits, policies, pauses or instructions, or claim full or unlimited
authority, in English and Arabic. The same guard refuses standing instructions to hand
private data elsewhere: send or forward memory, `MEMORY.md`, `OPERATING.md`, the owner
profile, notes or secrets anywhere, fetch an address built from data
(`https://…?d=<summary>`), or name `peer_send`. A profile write or preference change
from a Run that has read third-party content is no longer the owner's word
(`owner_profile_requires_owner_message`, see `agents-from-chat.md`). A statement that is already present (an owner
edit) does not block unrelated edits. `MEMORY.md` keeps its earlier contract: it
is untrusted data. This is defence in depth only; the executor never reads memory
and authority comes from the signed grant alone.

**Legacy `# USER.md` sections.** Migration `0039_owner_profile_memory_revisions`
merges every Agent's `# USER.md` section into the profile, oldest change first,
keeping each distinct line once (exact, trimmed) under a
`<!-- Merged from <agent name> -->` comment. Agent rows are not modified. The
merge writes only when the resulting content hash differs, so running it again
changes nothing. The merge never pushes the profile past its 8,000-character
limit: whole Agent blocks join it oldest first while they fit, and each block that
does not fit is routed (never dropped) into that Agent's own `# OPERATING.md` notes
under "Owner preferences kept here (the shared profile was full)", once. The owner
can still save an over-limit profile (an older merge) shorter; nothing is saved
longer than the limit (`owner_profile_too_large`, 413). The downgrade first writes
every profile line the Agent rows do not already hold (the owner's edits and Agents'
writes since the upgrade) as a `# USER.md` section of the Personal Agent's document
(else the owner's oldest Agent), where the earlier runtime reads it and a re-upgrade
merges it back; then it drops the two tables (the revision history goes with
them). At runtime the retired section is no longer read from an Agent row: it is
hidden from `memory_read`, the context, recall, `search_internal` and the owner's
memory editor. It stays in the row: every write (operations, a whole document, the
owner's edit, an undo) changes only the Agent's view and keeps the section's lines
after it (`lonora_db.memory.split_legacy` / `with_legacy`), the size limit applies
to the view, and revisions record the view on both sides, so the history shows only
what the change did. A downgrade therefore still finds every earlier preference line.

## Revisions and undo

Every commit to the owner profile, the structured preferences or an Agent's
memory stores one `ln_memory_revisions` row: the text before and after, the
author (`owner`, `agent` with its Agent id, or `system` for the merge), the owner
message an Agent answered, the Run and the kind of change. The newest 100 are kept
per document. The owner API lists them with a bounded line diff (or, for
preferences, plain field changes without device identifiers):

- `GET /api/owner/profile`, `PUT /api/owner/profile` (`content`, `version`),
  `PUT /api/owner/preferences` (`reply_language`, `reach_me`),
  `GET /api/owner/profile/revisions`;
- `GET /api/agents/{id}/memory/revisions`;
- `POST /api/memory/revisions/{id}/revert` (optional `version`): undoes that one
  change as a new owner commit, so nothing is rewritten in place and every later
  change stays. For text (`undo_change`) the lines that change added are removed and
  the lines it removed come back where they were; undoing the newest change gives
  back the exact earlier text. If a later change rewrote the very lines the change
  wrote, nothing is saved and the answer is `memory_revert_conflict` (409): undo the
  later change first or edit the text. For preferences only the settings that
  change touched go back (undoing an Agent's "reply in Arabic" leaves a later "message
  me instead of calling" as it is). The document is locked before anything is read.

On the web the profile lives in Settings: «الملف الشخصي» (`/app/owner`) edits the name, the
form of address, the time zone and the profile text, lists what agents wrote and shows the
change log with «استعادة»; «الإشعارات والتواصل» (`/app/notify-settings`) holds the reach-me
choice, quiet hours to the minute and each agent's delivery rules. The Knowledge panel
links to both. The memory tab of each Agent shows its own history the same way. Labels and error texts come from one table in
`@lonora/core` (`owner-profile.ts`) in Arabic and English, read by both Web
(`userError`) and Mobile (`errorText`).

## session_search

A read-only core tool (`lonora_tools/session_search.py`), so helpers and
observe-only wakes have it too. Its shape follows the arguments, adapted from
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

`tests/test_owner_profile.py` covers the views (the retired section is hidden and
operating notes stay apart), profile operations, the authority guard on English
and Arabic statements and benign methods, the reach-me channel contract, plain
preference changes, the capped profile under admission and the migration merge.
On PostgreSQL it proves that a preference the Personal Agent records from the
owner's message reaches another Agent's context with its attribution, that every
commit keeps a revision and undoing the newest change restores the exact text, that
undoing an older text or preference change keeps every later one (and a rewritten
line is `memory_revert_conflict`), that a Run without an owner message cannot write
the profile, and that reach-me set from chat decides whether a call can ring. Three
races hold a lock in one transaction while another writer waits: two overlapping
`USER.md` adds both survive with distinct versions, an undo racing an Agent commit
is `version_conflict` and loses nothing, and `owner_preferences_update` during an
owner save keeps both. Agent, whole-document and owner writes keep a legacy section
in the row while the history shows only the change. `tests/check_owner_profile.py`
runs on a fresh database: the migration is lossless (every legacy line kept, Agent
rows byte-identical) and idempotent across a re-run and a downgrade/upgrade, an
Agent's write after the upgrade still leaves every legacy line for a downgrade, a
preference reaches the gold Agent through a real Run, and "send me a message instead
of calling" makes the next qualifying event ring nothing and write exactly one
message. `tests/check_lossless_downgrades.py` keeps a line the owner wrote after the
upgrade across a downgrade below 0039 and the re-upgrade, and routes a merge past the
limit into the Agents' own notes once.

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
- Automatic per-turn recall still covers only the current thread; other threads
  are reached through `session_search`.
- Mobile edits the reach-me preference and reply language (Voice settings); the
  profile text and its change history are edited on the web profile page (`/app/owner`).
- Reach-me delivery is in-app only until off-app delivery (Wave 3). Until the
  `owner_notify` tool (W15-7) lets an Agent raise an inbox alert, `notify` behaves
  like `message` plus the alerts Lonora already raises, and its label says exactly
  that.
- The shared Arabic and English label table covers the profile, reach-me, language
  and history words only. Status-line, ladder (No trading / Ask me / On its own) and
  brake ("Stop new trading") words belong to W15-1, W15-3 and W15-9, which rename
  them on Web and Mobile; they are not duplicated here.
