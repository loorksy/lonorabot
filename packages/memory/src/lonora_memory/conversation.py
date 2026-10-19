"""Bounded recall of compacted canonical messages in one authorized direct thread."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from lonora_db.schema import MessageRow, ThreadRow
from lonora_db.transactions import owned_thread
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .retrieval import query_terms

if TYPE_CHECKING:
    from .evidence import Evidence

CONVERSATION_CANDIDATES = 128
CONVERSATION_TEXT_CHARS = 6000
ARABIC_MARKS = "".join(chr(number) for number in range(0x64B, 0x660)) + "\u0670"


@dataclass(frozen=True)
class ConversationRecallScope:
    """Server-owned cutoffs, never a model supplied cross-thread search grant.

    before_seq is inclusive (the last summarized sequence). Current history
    includes messages after that sequence, so they must not be retrieved twice.
    """

    thread_id: str
    input_seq: int
    before_seq: int
    include_neighbor: bool = False

    def __post_init__(self) -> None:
        if (
            not self.thread_id
            or type(self.input_seq) is not int
            or type(self.before_seq) is not int
            or self.input_seq < 0
            or self.before_seq < 0
        ):
            raise ValueError("invalid_conversation_recall_scope")


async def conversation_candidates(
    session: AsyncSession,
    owner_id: str,
    agent_id: str,
    scope: ConversationRecallScope,
    query: str,
    *,
    neighbor_seq: int | None = None,
    neighbor_role: str | None = None,
) -> tuple[list["Evidence"], str, bool]:
    from .evidence import Evidence

    thread = await owned_thread(session, owner_id, scope.thread_id)
    if thread.agent_id != agent_id or thread.group_id or thread.purpose != "conversation":
        return [], "scope_unavailable", False
    cutoff = min(scope.before_seq, thread.summary_seq, scope.input_seq - 1, thread.next_seq - 1)
    if cutoff < 1:
        return [], "no_compacted_history", False
    statement = (
        select(
            MessageRow.id,
            MessageRow.thread_id,
            MessageRow.agent_id,
            MessageRow.seq,
            MessageRow.role,
            MessageRow.created_at,
            func.substr(MessageRow.content, 1, CONVERSATION_TEXT_CHARS + 1).label("text"),
        )
        .join(ThreadRow, ThreadRow.id == MessageRow.thread_id)
        .where(
            ThreadRow.id == scope.thread_id,
            ThreadRow.owner_id == owner_id,
            ThreadRow.agent_id == agent_id,
            ThreadRow.group_id.is_(None),
            ThreadRow.purpose == "conversation",
            MessageRow.seq <= cutoff,
            MessageRow.seq < scope.input_seq,
            MessageRow.seq > 0,
            or_(
                and_(MessageRow.role == "user", MessageRow.agent_id.is_(None)),
                and_(MessageRow.role == "assistant", MessageRow.agent_id == agent_id),
            ),
            # Peer outcome/request transport is not an owner/Agent conversation turn.
            or_(MessageRow.client_nonce.is_(None), ~MessageRow.client_nonce.startswith("peer:")),
        )
    )
    if neighbor_seq is None:
        wanted = sorted(query_terms(query))
        if not wanted:
            return [], "no_match", False
        normalized = func.translate(MessageRow.content, ARABIC_MARKS, "")
        statement = statement.where(
            or_(*(normalized.icontains(term, autoescape=True) for term in wanted))
        )
        statement = statement.order_by(MessageRow.seq.desc()).limit(CONVERSATION_CANDIDATES + 1)
    else:
        if neighbor_role not in {"user", "assistant"}:
            return [], "no_match", False
        # Expand the matching exchange, not a previous unrelated assistant turn.
        target_seq = neighbor_seq + 1 if neighbor_role == "user" else neighbor_seq - 1
        target_role = "assistant" if neighbor_role == "user" else "user"
        statement = statement.where(MessageRow.seq == target_seq, MessageRow.role == target_role)
        statement = statement.limit(1)
    rows = (await session.execute(statement)).mappings().all()
    capped = len(rows) > CONVERSATION_CANDIDATES
    items: list[Evidence] = []
    for row in rows[:CONVERSATION_CANDIDATES]:
        text = str(row["text"])
        if not text.strip():
            continue
        items.append(
            Evidence(
                id="message:" + str(row["id"]),
                source="conversation_message",
                text=text[:CONVERSATION_TEXT_CHARS],
                version=0,  # Messages have no version column; never invent a revision.
                recorded_at=row["created_at"].isoformat(),
                provenance={
                    "message_id": row["id"],
                    "thread_id": row["thread_id"],
                    "seq": row["seq"],
                    "role": row["role"],
                    "author_id": row["agent_id"] if row["role"] == "assistant" else owner_id,
                    "author_kind": "agent" if row["role"] == "assistant" else "owner",
                    "source": "canonical_message",
                    "neighbor_of_seq": neighbor_seq,
                },
                truncated=len(text) > CONVERSATION_TEXT_CHARS,
                authority="untrusted_historical_conversation",
            )
        )
    return items, "matched" if items else "no_match", capped
