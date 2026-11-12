# Proactivity

How agents reach the owner without being asked (VISION.md section 11). This page
describes the behaviour as built; each phase 7 change extends it.

## Routine and watch output (11.6)

A routine is the agent's own scheduled work, and its output belongs in the agent's own
conversation, never in a chat of its own.

- **Work thread.** Each routine has one hidden work thread (`ln_threads.purpose = 'work'`),
  created with the routine (`create_routine` in `lonora_db/routines.py`). It is the
  routine's memory: every run of the routine works there and reads its earlier runs.
  Work threads never appear in the owner's chat list (`list_threads` lists conversations
  only).
- **Origin.** When the routine fires, its run carries `origin_thread_id`, the agent's own
  conversation (`background_origin` in `lonora_db/threads.py`, which resolves
  `conversation_thread`). Everything owner-facing the run raises follows the origin, as a
  broker-event wake's already does: its non-empty result is copied into the conversation
  (`return_outcome` in `lonora_agent/collaboration/outcome_return.py`), and its approval
  cards, owner cards, journal entries and new watches are placed there (`report_thread`).
- **Its further work.** A Task the run starts reports to the conversation
  (`task_start` uses `report_thread`), and when the run hands work to a peer and finishes
  first, the follow-up run keeps the origin and its non-empty result is copied too.
- **Watches.** A watch set in a chat keeps that chat and runs there. A watch set up
  outside any chat (for example through `POST /watches` without a thread) gets a hidden
  work thread and reports to the agent's conversation exactly like a routine.
- **Questions.** A question the run asks the owner (`wait_for_input`) is posted in its
  work thread, which stays its memory, and copied into the conversation it reports to
  (`report_thread`); the stored request names the copy and its thread, so the question
  card shows under the copy (`threadQuestions` in `packages/core`). The owner answers it
  there: by tapping a choice, by replying to the question, or with the next message when
  nothing in that conversation is taking messages and the question is still the last
  message there (`asking_run` in `lonora_db/messages.py`); a live voice transcript answers
  only by reply. The answer
  resumes the same run from its checkpoint in its work thread; the run reads it as the
  owner's message and gains no authority from it, and its result is copied back as
  above. A later turn in the conversation sees the question with its choices and a note
  that the answer went to the background work; an answer that went there cannot be
  edited and resent. Card sends, @mentions and collaboration messages never answer a
  background question, and the answer never stands for the owner's words of another run
  in that conversation. The work thread keeps the owner's answer next to the question, so
  the routine's later runs read it. A question from a run that reports nowhere else stays
  in its own thread, and a question whose conversation is deleted goes back to it.
- **History.** A routine's run history (`GET /routines/{id}/history`) lists its runs by
  routine, so it survives a move to a new work thread. On mobile, a history entry, like a
  row of the Tasks tab, opens where the owner reads that run: while it waits for the
  owner's answer, the thread that holds its question; otherwise the agent's conversation
  for a run with an origin, or the run's own thread for a run from before this change (its
  output is there).

Migration `0090_routine_work_threads` converts the routine chats of earlier releases:
a chat used only by a routine or a thread-less watch becomes that routine's work thread.
A thread stays a conversation when the owner wrote in it, when other work ran in it,
when it holds a record the owner reads there (an approval, a card, a journal row,
an opportunity, an artifact, a peer message, a collaboration, a Task, a place in a chat
list, a pin or a favourite), when a question in it waits for the owner's answer, or when it
is the agent's earliest conversation; a routine on such a thread moves to a new work
thread of its own. A routine or watch run still in flight in a converted thread reports
to the agent's conversation, like the runs the new code queues.

## Silence when there is nothing (11.5)

A scheduled or background run with nothing new posts nothing. The agent decides what is
new; the server makes sure that an empty or failed background run leaves nothing in a
conversation, the attention list or a channel.

- **Background runs** (`is_background` in `lonora_core/run_state.py`): the triggers
  `routine`, `watch` (opportunity wakes included), `broker_event` (Lonora's system-alert
  wakes included), `activation`, `tickets` (Tasks with their timer, watch and broker
  resumes, and legacy tickets), `webhook` and `workspace_wake`; and a `follow_up` (a
  helper's returned outcome or a collaboration synthesis) whose parent is background and
  was not written to by the owner: `create_run` marks it `background`, and a caller never
  can. Not background: the owner's messages and taps (`user`, `group`, `owner_card`,
  `agent_created`), peer requests and subagent tasks (they owe the agent that asked an
  answer), the morning brief (11.1) and the weekly report (5.5.6).
- **What the agent is told.** Every background `<wake>` frame carries one fixed sentence
  (`BACKGROUND` in `lonora_agent/context/routine.py`): if nothing is new for the owner, end
  with an empty reply, which posts nothing and notifies no one. The core policy, the
  work-limit notice, the market-watch skill and `routine_create` say the same.
- **An empty reply posts nothing.** While a run may end silent, the router accepts a reply
  the provider ended normally with no text and no call (`allow_empty`; for every other
  caller such a reply is still a broken response that is retried and falls back). The run
  is not nudged with the "no answer" notice, leaves no empty turn in its transcript, and
  `group_silence` accepts it. At its work limit only an empty answer is its choice: a
  failed final call, a turn of calls or a card without text still gives the fixed limit
  report, and a Task that is not finished still asks its owner. `complete_run` posts no
  message and `return_outcome` copies nothing, and no attention item stands in for its
  reply (below).
- **The owner's words are answered.** A background run never absorbs an owner message it
  is not waiting for: the message starts a run of its own. Once the owner writes to a
  background run (an answer to its question), the rest of that run answers like an owner
  turn (`owner_spoke`): it streams, may not end empty, and its follow-up answers too.
- **A failed run posts nothing in the conversation.** It has no result, so nothing is
  copied. A background run streams no preview (`run.delta`) while it may end silent, so no
  partial text remains where it ran, even in a chat. The mobile run strip leaves failed
  background runs out (`run.background`). Once background work has ended in a
  conversation, a helper's outcome is posted there only when the work completed and the
  helper has something to show; a background run still running is still told, and a work
  thread still gets every outcome, as that work's memory. A subagent of background work
  works in a hidden work thread of its own and reports where its parent reports.
- **Attention items.** A wake's source raises no item beside the woken run: a watch
  confirmation that woke its agent, broker activity that woke an agent (`wakes_agent`), a
  server-detected opportunity change whose wake reports in the agent's own conversation,
  and a collaboration synthesis or a Task that completed with an empty result. Such a
  source withdraws no other item. If the woken run fails, its `run.failed` is decided as
  that source, so the owner still learns of the change. A confirmation that woke nobody
  (its wake already spent), broker activity while Lonora is paused, an opportunity whose
  wake cannot report in the agent's conversation, watch invalidation and expiry, and the
  11.4 items stay items.
- **Channels.** A Telegram or webhook integration without a thread never forwards a work
  thread's messages; the conversation copy is sent once.
- **Kept on purpose.** A run that sent an order whose result is not verified always says
  so (5.3.3), also when it ends through `group_silence`. Explicit acts are the agent's own
  choice: `owner_notify`, cards, peer requests, `collaboration_finish`.
