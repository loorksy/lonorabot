"""Routine and thread-less watch threads become hidden work threads (VISION 11.6).

A routine, or a watch set up outside any chat, used to post into a chat of its own. Its
thread becomes its hidden work thread (its memory), and its results go to its Agent's
own conversation. A thread the owner wrote in, or that other work used, stays a
conversation, as does a thread that holds a record the owner reads there (an approval,
a card, a journal row, an opportunity, an artifact, a peer message, a
collaboration, a Task, a place in a chat list, a pin or a favourite) or a question
waiting for the owner's answer; a routine on such a thread moves to a new work thread of
its own. An Agent's earliest conversation is never converted: it is the Agent's own
conversation. A routine or watch run still in flight in a converted thread reports to the
Agent's conversation, like the runs the new code queues.
"""

from alembic import op

revision = "0090_routine_work_threads"
down_revision = "0068_end_trading_goals"
branch_labels = None
depends_on = None

# One statement: the threads it converts become work threads, and a routine, watch or
# follow-up run still in flight in one of them reports to its Agent's conversation, as
# the runs the new code queues do. Only the threads converted here are stamped: a Task's
# own work thread keeps its runs as they are. The Agent's earliest conversation, read
# from the statement's snapshot, is never one of the converted threads.
CONVERT = """
WITH converted AS (
    UPDATE ln_threads t SET purpose = 'work'
    WHERE t.purpose = 'conversation' AND t.group_id IS NULL AND t.agent_id IS NOT NULL
    AND (
        EXISTS (SELECT 1 FROM ln_routines r WHERE r.thread_id = t.id)
        OR EXISTS (SELECT 1 FROM ln_market_watches w WHERE w.thread_id = t.id)
    )
    AND NOT EXISTS (SELECT 1 FROM ln_messages m WHERE m.thread_id = t.id AND m.role = 'user')
    AND NOT EXISTS (SELECT 1 FROM ln_trade_approvals a WHERE a.thread_id = t.id)
    AND NOT EXISTS (SELECT 1 FROM ln_owner_actions a WHERE a.thread_id = t.id)
    AND NOT EXISTS (SELECT 1 FROM ln_trading_journal a WHERE a.thread_id = t.id)
    AND NOT EXISTS (SELECT 1 FROM ln_trading_opportunities a WHERE a.thread_id = t.id)
    AND NOT EXISTS (SELECT 1 FROM ln_artifacts a WHERE a.thread_id = t.id)
    AND NOT EXISTS (SELECT 1 FROM ln_peer_messages a WHERE a.thread_id = t.id)
    AND NOT EXISTS (SELECT 1 FROM ln_collaboration_sessions a WHERE a.thread_id = t.id)
    AND NOT EXISTS (SELECT 1 FROM ln_chat_list_members a WHERE a.thread_id = t.id)
    AND NOT EXISTS (
        SELECT 1 FROM ln_thread_prefs a
        WHERE a.thread_id = t.id AND (a.pinned_order IS NOT NULL OR a.favourite)
    )
    AND NOT EXISTS (SELECT 1 FROM ln_runs a WHERE a.thread_id = t.id AND a.status = 'waiting_input')
    AND NOT EXISTS (
        SELECT 1 FROM ln_tickets k
        WHERE k.thread_id = t.id OR (k.state::jsonb -> 'task' ->> 'origin_thread_id') = t.id
    )
    AND NOT EXISTS (
        SELECT 1 FROM ln_runs x
        WHERE x.thread_id = t.id AND x.trigger NOT IN ('routine', 'watch', 'follow_up')
    )
    AND t.id <> (
        SELECT c.id FROM ln_threads c
        WHERE c.owner_id = t.owner_id AND c.agent_id = t.agent_id
        AND c.group_id IS NULL AND c.purpose = 'conversation'
        ORDER BY c.created_at, c.id LIMIT 1
    )
    RETURNING t.id, t.owner_id, t.agent_id
)
UPDATE ln_runs r SET model_metadata = (
    r.model_metadata::jsonb || jsonb_build_object('origin_thread_id', (
        SELECT c.id FROM ln_threads c
        WHERE c.owner_id = converted.owner_id AND c.agent_id = converted.agent_id
        AND c.group_id IS NULL AND c.purpose = 'conversation'
        ORDER BY c.created_at, c.id LIMIT 1
    ))
)::json
FROM converted
WHERE r.thread_id = converted.id
AND r.trigger IN ('routine', 'watch', 'follow_up')
AND r.status NOT IN ('completed', 'failed', 'cancelled')
AND (r.model_metadata::jsonb ->> 'origin_thread_id') IS NULL
"""

MOVE = """
WITH moved AS (
    SELECT r.id AS routine_id, gen_random_uuid()::text AS thread_id,
           r.owner_id, r.agent_id, left(r.prompt, 80) AS title
    FROM ln_routines r JOIN ln_threads t ON t.id = r.thread_id
    WHERE t.purpose = 'conversation'
), created AS (
    INSERT INTO ln_threads
        (id, owner_id, agent_id, group_id, title, next_seq, purpose, options,
         context_summary, summary_seq, created_at)
    SELECT thread_id, owner_id, agent_id, NULL, title, 1, 'work', '{}', '', 0, now()
    FROM moved
)
UPDATE ln_routines r SET thread_id = moved.thread_id
FROM moved WHERE r.id = moved.routine_id
"""


def upgrade() -> None:
    op.execute(CONVERT)
    op.execute(MOVE)


def downgrade() -> None:
    # Work threads cannot tell which of them were routine chats before; they stay work.
    pass
