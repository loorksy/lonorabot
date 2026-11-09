# Thread preferences, chat lists and the owner's search

The conversation list of the reference UI (phase 2) is server state per owner, shared by
Web and Mobile (owner decision Q3). Nothing about it lives in a device's storage.

## Per-conversation state (`ln_thread_prefs`, migration `0044_thread_prefs`)

One row per owner and conversation: `last_read_seq`, `marked_unread`, `muted`, `archived`,
`favourite`, `pinned_order` (1..3), `hidden_before_seq`, `updated_at`. Every existing
conversation starts read up to its latest message, so the migration makes nothing unread.

- `POST /api/threads/{id}/read {seq}` moves the read cursor forward only (max-wins across
  devices), clamped to the latest message, and clears marked-unread. `POST
  /api/threads/read-all` does it for every conversation. Event `thread.read`.
- `PATCH /api/threads/{id}/prefs {pinned?, muted?, archived?, favourite?, marked_unread?}`
  and the bulk `POST /api/threads/prefs {thread_ids, ...}` (all or nothing). A new pin goes
  on top (`pinned_order` 1, the others shift); a fourth pin is `409 thread_pin_limit`;
  archiving unpins and pinning unarchives. Event `thread.prefs_updated` with the row.
- `POST /api/threads/{id}/clear` is «مسح» / «حذف» for a conversation (Q1): it sets
  `hidden_before_seq` to the latest message. Messages at or before it leave the owner's
  history (`GET messages`), the inbox `last_message` and the search; the thread, its
  grants, the journal and the agent stay, and the agent's own history is untouched.
  Groups are still removed with `DELETE /api/groups/{id}`.
- `GET/PUT /api/threads/settings {keep_archived}` is «إبقاء المحادثات مؤرشفة». When it is
  off, the gateway step `thread_prefs` applies every published `message.created` event:
  an archived conversation returns to the list (`archived=false`, `thread.prefs_updated`).
  The rule runs on durable events, so every path that writes a message is covered.

`GET /api/threads/inbox` returns, per canonical conversation, `unread_count` (the agent's
messages after the read cursor), the preference fields, `hidden_before_seq` and
`last_message {id, role, agent_id, seq, created_at, content, kind, preview, attachments
{count, kinds}, consumed}`. `kind` is `card` for a rich answer with a ui part, `image`,
`voice` or `file` from the first attachment, else `text`; `preview` is one line of at
most 160 characters. Mute never hides critical or action_required attention (Q4): the
projection only reports `muted`; the attention ledger is separate.

`consumed` (Q2: two accent ticks) is derived, never stored: an owner message is consumed
once a run of its conversation has started (running or later) with `input_seq` at or past
it, or once the message was steered into a running run and merged. `GET
/api/threads/{id}/messages` adds the same `consumed` field to every owner message.

## Groups and templates

A group payload carries `purpose` (≤160) and `lead_agent_id` (a member); the lead answers
when no agent is mentioned and no reply names one (Q8). `ln_agents.template` persists the
creation template (Q9): `POST /api/agents/create` takes the `agent_create` tool's input
(`AgentCreateInput`) and runs the same creation service; the owner's older form derives
`trading` from a focus pair and `general` otherwise; the personal agent and delegated
helpers keep `null`, their role being their type. The migration backfills the column from
the creation records.

## Chat lists (`ln_chat_lists`, `ln_chat_list_members`, migration `0045_chat_lists`)

`GET/POST /api/chat-lists`, `PUT/DELETE /api/chat-lists/{id}`, `PUT
/api/chat-lists/{id}/members {thread_ids}` (replaces the members, every id an owned
thread). A name (≤30) is unique per owner, case-insensitively: `409 chat_list_name_taken`.
Event `chat_list.updated {id}` on every change, with `deleted: true` on a delete.

## Unified search (`GET /api/search`)

`q` (empty allowed), `category` (`chats | messages | tasks | files | knowledge | skills`),
`limit` (default 32) and `offset`. Without a category every category is returned with its
count; the client asks for `limit=3` on «الكل». Query and text are folded the same way
(`lonora_core.search_fold`: lower-case, alef variants → ا, ى → ي, ة → ه, tashkeel and
tatweel removed); messages are served by a pg_trgm index on that expression (created by
`0045_chat_lists`, which installs the trusted `pg_trgm` extension). Score: exact 6, prefix
5, contains 4, a detail field 3, then recency. Files are artifacts, knowledge is every
agent's memory and semantic notes labelled by agent, skills the installed skills (Q5).
Message hits carry `thread_id`, `seq`, `created_at`, `role`, `agent_id` (the speaker),
`thread_agent_id` and `group_id` (the thread's own agent or group, which routes the hit: a
peer's outcome sits in the asking agent's thread) and a 160-character snippet;
`GET /api/threads/{id}/messages?around=seq` centres a page on a
hit. An empty `q` is the browse feed: the same categories by recency, tasks active first.
The search is owner-wide and served to the owner API only; agents keep their scoped
`search_internal` and `session_search` tools. The response is `q`, `category`, `limit`,
`offset`, `counts` and `results` (by category), with or without a category.

## Contracts and clients

Python: `lonora_contracts.thread_prefs`, `lonora_contracts.chat_lists`,
`lonora_contracts.search`, `GroupCreate.purpose/lead_agent_id`, `AgentCreate.template`.
TypeScript (`@lonora/contracts`): `InboxEntry`, `InboxLastMessage`, `ThreadPrefs`,
`ThreadSettings`, `ChatList`, `SearchResult`, `SearchResponse`, `Agent.template`,
`GroupPayload.purpose/lead_agent_id`, `Message.consumed`. `@lonora/core` gives Web and
Mobile the same arithmetic: `inboxUnread`, `unreadBadgeTotal` (archived and muted rows
excluded, a marked-unread row counts one), `archivedSummary` and `orderInbox` (pinned
first in pin order, then latest activity).

Checks: `tests/test_thread_preferences.py`, `tests/check_thread_preferences.py` (migration
round trip and the projection on a fresh database), `tests/web/inbox-order.test.ts`.
