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
- **History.** A routine's run history (`GET /routines/{id}/history`) lists its runs by
  routine, so it survives a move to a new work thread. On mobile, a history entry opens
  the agent's conversation.

Migration `0090_routine_work_threads` converts the routine chats of earlier releases:
a chat used only by a routine or a thread-less watch becomes that routine's work thread.
A thread stays a conversation when the owner wrote in it, when other work ran in it,
when it holds a record the owner reads there (an approval, a card, a journal row, a Goal,
an opportunity, an artifact, a peer message, a collaboration, a Task, or a place in a chat
list), or when it is the agent's earliest conversation; a routine on such a thread moves
to a new work thread of its own.

Not yet built: a question a background run asks the owner (`wait_for_input`) is posted in
its work thread, so it cannot be answered from the conversation yet.
