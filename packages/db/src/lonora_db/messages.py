from typing import Any, cast

from lonora_contracts.domain import MessageCreate
from lonora_core.group_mentions import mentions
from lonora_core.message_replies import require_same_thread
from lonora_core.run_state import TERMINAL, is_conversational
from lonora_core.user_error import LonoraError
from sqlalchemy import delete, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from .cancellation import cancel_run
from .events import emit
from .pauses import OWNER_ADDRESSED, claimable_while_paused, runs_while_paused
from .reactions import reactions_by_message
from .rich_response import server_rich_content
from .runs import OFFER_OBLIGATION, run_data
from .schema import (
    AgentRow,
    ArtifactRow,
    EffectReceiptRow,
    GroupRow,
    MessageRow,
    RunRow,
    SteeringRow,
    ThreadRow,
)
from .transactions import owned_agent, owned_thread

# A voice note waiting for its transcript; the receipt is removed once it settles.
VOICE_NOTE_PENDING = "voice-note:"
VOICE_MEDIA_TYPES = frozenset({"audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg", "audio/wav"})


async def voice_artifact(
    session: AsyncSession, owner_id: str, thread_id: str, artifact_id: str
) -> ArtifactRow:
    """The owner's audio artifact uploaded to this thread (a recorder's codec suffix is
    ignored: ``audio/webm;codecs=opus`` is ``audio/webm``)."""
    artifact = await session.get(ArtifactRow, artifact_id)
    if artifact is None or artifact.owner_id != owner_id:
        raise LonoraError("artifact_not_found", 404)
    media_type = str(artifact.payload.get("media_type", "")).split(";")[0].strip().lower()
    if artifact.thread_id != thread_id or media_type not in VOICE_MEDIA_TYPES:
        raise LonoraError("voice_artifact_invalid", 422)
    return artifact


# A direct chat's @mention invites at most this many guests per message (Q29).
MAX_DIRECT_GUESTS = 2


def message_data(row: MessageRow) -> dict[str, Any]:
    """One message as clients read it. ``reactions`` and ``superseded_by`` are empty here
    (a new message has neither); ``messages_data`` fills them for a page."""
    return {
        "id": row.id,
        "thread_id": row.thread_id,
        "agent_id": row.agent_id,
        "seq": row.seq,
        "role": row.role,
        "content": row.content,
        "rich_content": row.rich_content,
        "reply_to": row.reply_to,
        "mentions": row.mentions,
        "attachment_ids": row.attachment_ids,
        "created_at": row.created_at.isoformat(),
        "client_nonce": row.client_nonce,
        "origin": row.origin or "owner",
        "ui_submit": public_submit(row.ui_submit),
        "ui_state": row.ui_state,
        "suggested_reply": row.suggested_reply,
        "edited_from": row.edited_from,
        "superseded_by": None,
        "reactions": [],
    }


def public_submit(submit: dict[str, Any] | None) -> dict[str, Any] | None:
    """What a client may see of a card submission (GENUI_PLAN §8.2 step 4)."""
    if not submit:
        return None
    keys = ("source_message_id", "part", "intent", "lock", "card_title", "run_id")
    shown = {key: submit[key] for key in keys if key in submit}
    for key in ("started_at", "superseded_at", "mark"):
        if submit.get(key):
            shown[key] = submit[key]
    return shown


async def follow_up_tap(session: AsyncSession, thread_id: str, content: str) -> bool:
    """A plain message equal to a v1 follow-up action text of a card among the thread's
    last 20 assistant messages was a tap, not the owner's typed words (§8.4)."""
    rows = await session.scalars(
        select(MessageRow.rich_content)
        .where(MessageRow.thread_id == thread_id, MessageRow.role == "assistant")
        .order_by(MessageRow.seq.desc())
        .limit(20)
    )

    def found(value: Any) -> bool:
        if isinstance(value, dict):
            item = cast(dict[str, Any], value)
            if item.get("kind") == "follow_up" and item.get("text") == content:
                return True
            return any(found(child) for child in item.values())
        if isinstance(value, list):
            return any(found(child) for child in cast(list[Any], value))
        return False

    return any(found(rich) for rich in rows if rich)


async def messages_data(session: AsyncSession, rows: list[MessageRow]) -> list[dict[str, Any]]:
    """A page of messages with their reactions and ``superseded_by`` (the newer message
    whose ``edited_from`` is this one), each batch-loaded in one query."""
    ids = [row.id for row in rows]
    reactions = await reactions_by_message(session, ids)
    superseded: dict[str, str] = {}
    if ids:
        superseded = {
            original: newer
            for newer, original in await session.execute(
                select(MessageRow.id, MessageRow.edited_from).where(MessageRow.edited_from.in_(ids))
            )
            if original
        }
    items = [message_data(row) for row in rows]
    for item in items:
        item["reactions"] = reactions.get(item["id"], [])
        item["superseded_by"] = superseded.get(item["id"])
    return items


async def history(
    session: AsyncSession,
    owner_id: str,
    thread_id: str,
    limit: int = 100,
    before: int | None = None,
    *,
    floor: int = 0,
) -> list[MessageRow]:
    """The latest messages before ``before``; ``floor`` is the owner's «مسح» cursor
    (``lonora_db.thread_prefs.hidden_floor``): nothing at or before it is returned."""
    await owned_thread(session, owner_id, thread_id)
    query = select(MessageRow).where(MessageRow.thread_id == thread_id, MessageRow.seq > floor)
    if before:
        query = query.where(MessageRow.seq < before)
    rows = list(
        (await session.scalars(query.order_by(MessageRow.seq.desc()).limit(min(limit, 200)))).all()
    )
    return list(reversed(rows))


async def history_around(
    session: AsyncSession,
    owner_id: str,
    thread_id: str,
    seq: int,
    limit: int = 100,
    *,
    floor: int = 0,
) -> list[MessageRow]:
    """A page centred on one message (a search hit): the message, up to half the page
    before it and the rest after it, in order. A hidden or missing message is
    ``message_not_found``."""
    await owned_thread(session, owner_id, thread_id)
    limit = min(limit, 200)
    target = await session.scalar(
        select(MessageRow).where(
            MessageRow.thread_id == thread_id, MessageRow.seq == seq, MessageRow.seq > floor
        )
    )
    if target is None:
        raise LonoraError("message_not_found", 404)
    before = list(
        await session.scalars(
            select(MessageRow)
            .where(MessageRow.thread_id == thread_id, MessageRow.seq < seq, MessageRow.seq > floor)
            .order_by(MessageRow.seq.desc())
            .limit(limit // 2)
        )
    )
    after = list(
        await session.scalars(
            select(MessageRow)
            .where(MessageRow.thread_id == thread_id, MessageRow.seq > seq)
            .order_by(MessageRow.seq)
            .limit(max(limit - len(before) - 1, 0))
        )
    )
    return [*reversed(before), target, *after]


async def acknowledged_runs(session: AsyncSession, run_ids: list[str]) -> list[dict[str, Any]]:
    """Return current canonical activity with the already committed message ack.

    A recovered nonce reuses its original identities. This projection does not
    start another Run or wait for the Gateway/model to handle the message.
    """
    if not run_ids:
        return []
    rows = {
        row.id: row for row in await session.scalars(select(RunRow).where(RunRow.id.in_(run_ids)))
    }
    return [run_data(rows[identity]) for identity in run_ids if identity in rows]


async def send_message(
    session: AsyncSession, owner_id: str, thread_id: str, request: MessageCreate
) -> dict[str, Any]:
    thread = await owned_thread(session, owner_id, thread_id, lock=True)
    existing = await session.scalar(
        select(MessageRow).where(
            MessageRow.thread_id == thread_id, MessageRow.client_nonce == request.client_nonce
        )
    )
    if existing:
        receipt = await session.get(EffectReceiptRow, "message:" + existing.id)
        supplied_submit = request.ui_submit.model_dump(mode="json") if request.ui_submit else None
        original_submit = receipt.result.get("ui_submit") if receipt else None
        if (supplied_submit is not None or original_submit is not None) and (
            supplied_submit != original_submit
        ):
            raise LonoraError("ui_submit_conflict", 409)
        supplied_answer = request.input_answer.model_dump() if request.input_answer else None
        original_answer = receipt.result.get("input_answer") if receipt else None
        if (supplied_answer is not None or original_answer is not None) and (
            supplied_answer != original_answer
            or request.content != existing.content
            or (request.reply_to and request.reply_to != existing.reply_to)
            or bool(
                request.attachment_ids
                or request.mention_agent_ids
                or request.mention_all
                or request.collaboration_session_id
            )
        ):
            raise LonoraError("input_answer_conflict", 409)
        if receipt is None:
            # Backfill older messages using their steering link or creation interval.
            # A later turn must never be returned as this message's original run.
            run_ids = list(
                await session.scalars(
                    select(SteeringRow.run_id).where(SteeringRow.message_id == existing.id)
                )
            )
            next_message = await session.scalar(
                select(MessageRow)
                .where(
                    MessageRow.thread_id == thread_id,
                    MessageRow.seq > existing.seq,
                    MessageRow.role == "user",
                )
                .order_by(MessageRow.seq)
                .limit(1)
            )
            created = select(RunRow.id).where(
                RunRow.thread_id == thread_id,
                RunRow.created_at >= existing.created_at,
                RunRow.trigger.in_(["user", "group"]),
            )
            if next_message:
                created = created.where(RunRow.created_at < next_message.created_at)
            run_ids = list(dict.fromkeys(run_ids + list(await session.scalars(created))))
            receipt = EffectReceiptRow(key="message:" + existing.id, result={"run_ids": run_ids})
            session.add(receipt)
        return {
            "message": (await messages_data(session, [existing]))[0],
            "run_ids": receipt.result.get("run_ids", []),
            "runs": await acknowledged_runs(session, receipt.result.get("run_ids", [])),
            "deduplicated": True,
        }
    if request.ui_submit is not None:
        # A card's send: its own queued Run, never folded into an active one (§8.2).
        from .genui_submit import submit_card, submit_receipt

        # ``create_run`` emitted ``run.queued``.
        message, run = await submit_card(session, owner_id, thread, request)
        session.add(submit_receipt(message, run, request))
        emit(
            session, owner_id, "message.created", thread_id=thread_id, payload=message_data(message)
        )
        return {
            "message": message_data(message),
            "run_ids": [run.id],
            "runs": await acknowledged_runs(session, [run.id]),
            "deduplicated": False,
        }
    answer_run: RunRow | None = None
    answer_question: dict[str, Any] | None = None
    if request.input_answer:
        supplied = request.input_answer
        answer_run = await session.get(RunRow, supplied.run_id, with_for_update=True)
        if (
            answer_run is None
            or answer_run.thread_id != thread_id
            or answer_run.status != "waiting_input"
            or (thread.agent_id and answer_run.agent_id != thread.agent_id)
        ):
            raise LonoraError("input_answer_expired", 409)
        # A paused agent still answers the owner (3.2.5) in a run it may run now; a held
        # run's question waits for its resume.
        agent = await owned_agent(session, owner_id, answer_run.agent_id)
        if agent.paused and not runs_while_paused(answer_run.trigger, answer_run.model_metadata):
            raise LonoraError("agent_paused", 409)
        answer_question = next(
            (
                item
                for item in reversed(answer_run.execution_state.get("input_requests", []))
                if item.get("id") == supplied.question_id and item.get("status") == "pending"
            ),
            None,
        )
        if (
            answer_question is None
            or answer_run.execution_state.get("pending_input_request", {}).get("id")
            != supplied.question_id
        ):
            raise LonoraError("input_answer_expired", 409)
        choice = next(
            (
                item
                for item in answer_question.get("choices", [])
                if item["id"] == supplied.choice_id
            ),
            None,
        )
        if (
            choice is None
            or request.content != choice["label"]
            or request.mention_agent_ids
            or request.mention_all
            or request.collaboration_session_id
            or request.attachment_ids
            or (request.reply_to and request.reply_to != answer_question["message_id"])
            or request.edited_from
        ):
            raise LonoraError("input_answer_invalid", 422)
    for mentioned_id in request.mention_agent_ids:
        await owned_agent(session, owner_id, mentioned_id)
    # A direct chat's @mention invites other agents as guests (Q29): they join the chat's
    # current collaboration session, or start one, and answer under their own name.
    guest_ids = (
        [
            identifier
            for identifier in dict.fromkeys(request.mention_agent_ids)
            if identifier != thread.agent_id
        ]
        if thread.agent_id
        else []
    )
    if len(guest_ids) > MAX_DIRECT_GUESTS:
        raise LonoraError("collaboration_guest_limit", 422)
    collaboration = None
    if request.mention_all or request.collaboration_session_id:
        from .collaboration import CollaborationRepository, current_session

        collaboration = (
            await CollaborationRepository().get(session, owner_id, request.collaboration_session_id)
            if request.collaboration_session_id
            else await current_session(session, owner_id, thread_id)
        )
        if collaboration and (
            collaboration.thread_id != thread_id or collaboration.agent_id != thread.agent_id
        ):
            raise LonoraError("collaboration_thread_mismatch", 409)
        if collaboration is None:
            raise LonoraError("collaboration_session_required", 409)
    elif guest_ids:
        from .collaboration import current_session

        # Guests join the chat's open session while it has room for another round;
        # otherwise the invitation starts a new one.
        current = await current_session(session, owner_id, thread_id)
        if current is not None and len(current.state.get("rounds", [])) < 8:
            collaboration = current
    reply = None
    if request.reply_to:
        reply = await session.get(MessageRow, request.reply_to)
        if reply is None:
            raise LonoraError("reply_not_found", 404)
        require_same_thread(thread_id, reply.thread_id)
    for artifact_id in request.attachment_ids:
        artifact = await session.get(ArtifactRow, artifact_id)
        if artifact is None or artifact.owner_id != owner_id:
            raise LonoraError("artifact_not_found", 404)
    rich_content = None
    if request.voice:
        await voice_artifact(session, owner_id, thread_id, request.voice.artifact_id)
        rich_content = server_rich_content(
            {
                **request.voice.model_dump(mode="json"),
                "type": "voice",
                "transcript_status": "pending",
            }
        )
    if request.edited_from:
        await supersede(session, owner_id, thread_id, request.edited_from)
    message = MessageRow(
        thread_id=thread_id,
        seq=thread.next_seq,
        role="user",
        **request.model_dump(
            exclude={
                "client_nonce",
                "mention_agent_ids",
                "mention_all",
                "collaboration_session_id",
                "input_answer",
                "ui_submit",
                "voice",
            }
        ),
        rich_content=rich_content,
        mentions={
            "agent_ids": list(dict.fromkeys(request.mention_agent_ids)),
            "all": request.mention_all,
            "session_id": collaboration.id if collaboration else None,
        },
        client_nonce=request.client_nonce,
    )
    if answer_question:
        message.reply_to = answer_question["message_id"]
    elif await follow_up_tap(session, thread_id, request.content):
        message.origin = "ui_follow_up"
    # reply_to/attachment_ids are part of the message; no model or provider is selected here.
    thread.next_seq += 1
    if not thread.title:
        thread.title = request.content[:80]
    session.add(message)
    await session.flush()
    if request.voice:
        # The Agent never answers an empty message: Runs are admitted once the
        # transcript lands (lonora_db.voice_notes.settle_voice_note).
        run_ids: list[str] = []
        session.add(
            EffectReceiptRow(
                key=VOICE_NOTE_PENDING + message.id,
                result={"owner_id": owner_id, "thread_id": thread_id, "message_id": message.id},
            )
        )
    else:
        run_ids = await admit_runs(
            session, owner_id, thread, message, request, reply, answer_run, collaboration
        )
    receipt_result: dict[str, Any] = {"run_ids": run_ids}
    if request.input_answer:
        receipt_result["input_answer"] = request.input_answer.model_dump()
    session.add(EffectReceiptRow(key="message:" + message.id, result=receipt_result))
    emit(session, owner_id, "message.created", thread_id=thread_id, payload=message_data(message))
    if request.edited_from:
        # Every client marks the original as replaced («مُعدّلة») without a refetch.
        original = await session.get(MessageRow, request.edited_from)
        if original is not None:
            (updated,) = await messages_data(session, [original])
            emit(session, owner_id, "message.updated", thread_id=thread_id, payload=updated)
    return {
        "message": message_data(message),
        "run_ids": run_ids,
        "runs": await acknowledged_runs(session, run_ids),
        "deduplicated": False,
    }


async def admit_runs(
    session: AsyncSession,
    owner_id: str,
    thread: ThreadRow,
    message: MessageRow,
    request: MessageCreate,
    reply: MessageRow | None,
    answer_run: RunRow | None,
    collaboration: Any,
) -> list[str]:
    """Start or steer the Runs an owner message asks for; returns their ids."""
    thread_id = thread.id
    targets: list[str] = []
    # Whether the owner named the group runs' agents, or they are its fallback answerer.
    addressed = True
    if thread.agent_id:
        targets = [thread.agent_id]
    elif thread.group_id:
        group = await session.get(GroupRow, thread.group_id)
        if group:
            member_ids = list(group.payload.get("member_ids", []))
            agents = list(
                (
                    await session.scalars(
                        select(AgentRow).where(
                            AgentRow.id.in_(member_ids), AgentRow.owner_id == owner_id
                        )
                    )
                ).all()
            )
            explicit = set(request.mention_agent_ids)
            if explicit and not explicit.issubset({a.id for a in agents}):
                raise LonoraError("agent_not_group_member", 409)
            targets = (
                [a.id for a in agents if a.id in explicit]
                if explicit
                else mentions(request.content, {a.id: a.name for a in agents})
            )
            if not targets and request.reply_to and reply and reply.agent_id:
                targets = [a.id for a in agents if a.id == reply.agent_id]
            addressed = bool(targets)
            if not targets:
                # Nobody mentioned: the group's lead answers, else the first available member.
                available = {a.id for a in agents if not a.paused}
                lead = group.payload.get("lead_agent_id")
                for member_id in [lead, *member_ids]:
                    if member_id in available:
                        targets = [member_id]
                        break
    if answer_run:
        targets = [answer_run.agent_id]
    run_ids: list[str] = []
    for agent_id in targets:
        # The owner's message starts a run even of a paused agent (3.2.5, 4.7.1), and that
        # run may only reduce risk. A group's fallback answerer is never paused. A paused
        # agent's held runs never take the owner's words: they go to a run it may run.
        agent = await owned_agent(session, owner_id, agent_id)
        active = await session.scalar(
            select(RunRow)
            .where(
                RunRow.thread_id == thread_id,
                RunRow.agent_id == agent_id,
                RunRow.status.in_(["queued", "leased", "running", "waiting_input"]),
                claimable_while_paused() if agent.paused else true(),
            )
            .order_by(RunRow.created_at)
            .limit(1)
        )
        if answer_run and (active is None or active.id != answer_run.id):
            raise LonoraError("input_answer_expired", 409)
        question_history = list(active.execution_state.get("input_requests", [])) if active else []
        pending_question = next(
            (item for item in reversed(question_history) if item.get("status") == "pending"),
            None,
        )
        if active and (
            is_conversational(active.trigger)
            or (active.status == "waiting_input" and pending_question)
        ):
            if pending_question and active.status == "waiting_input":
                updated = [
                    {
                        **item,
                        "status": "answered",
                        "selected_choice_id": request.input_answer.choice_id
                        if request.input_answer
                        else None,
                        "answer_message_id": message.id,
                    }
                    if item.get("id") == pending_question["id"]
                    else item
                    for item in question_history
                ]
                state: dict[str, Any] = {**active.execution_state, "input_requests": updated}
                state.pop("pending_input_request", None)
                # A picked choice that was bound to calls is what the resumed Run answers
                # for. Any other answer closes the offer: it was open for this message only.
                state.pop(OFFER_OBLIGATION, None)
                picked = request.input_answer.choice_id if request.input_answer else None
                bound = next(
                    (
                        choice.get("actions")
                        for choice in pending_question.get("choices", [])
                        if picked is not None and choice.get("id") == picked
                    ),
                    None,
                )
                if bound:
                    state[OFFER_OBLIGATION] = {
                        "question_id": pending_question["id"],
                        "choice_id": picked,
                        "answer_message_id": message.id,
                        "actions": bound,
                        "status": "open",
                    }
                active.execution_state = state
            if active.model_metadata.get("ui_submit_origin") and message.origin == "owner":
                # A card's send that has not run yet holds the owner's words for it; if
                # «تعديل» or the lifetime cancels it, they are re-queued (genui_submit).
                held = list(active.model_metadata.get("folded_message_ids", []))[-20:]
                active.model_metadata = {
                    **active.model_metadata,
                    "folded_message_ids": [*held, message.id],
                }
            if active.status == "queued":
                active.input_seq = message.seq
                if active.execution_state:
                    # A queued continuation restores its checkpoint instead of rebuilding history.
                    session.add(SteeringRow(run_id=active.id, message_id=message.id))
                    environment = dict(active.execution_state.get("environment", {}))
                    environment.pop("retry", None)
                    active.execution_state = {**active.execution_state, "environment": environment}
            else:
                session.add(SteeringRow(run_id=active.id, message_id=message.id))
                if active.status == "waiting_input":
                    active.status = "queued"
            run_ids.append(active.id)
        else:
            run = RunRow(
                thread_id=thread_id,
                agent_id=agent_id,
                input_seq=message.seq,
                trigger="group" if thread.group_id else "user",
                model_metadata={OWNER_ADDRESSED: True} if thread.group_id and addressed else {},
            )
            session.add(run)
            await session.flush()
            run_ids.append(run.id)
            emit(
                session,
                owner_id,
                "run.queued",
                thread_id=thread_id,
                agent_id=agent_id,
                run_id=run.id,
                payload={"run": run_data(run)},
            )
    if thread.agent_id and (request.mention_agent_ids or request.mention_all):
        from .collaboration import invite

        participant_ids = [i for i in request.mention_agent_ids if i != thread.agent_id]
        if collaboration and (request.mention_all or request.collaboration_session_id):
            participant_ids.extend(
                p["agent_id"] for p in collaboration.state.get("participants", [])
            )
        # A paused guest is not invited; the chat's own agent still answers.
        participant_ids = [
            identifier
            for identifier in dict.fromkeys(participant_ids)
            if identifier != thread.agent_id
            and not (await owned_agent(session, owner_id, identifier)).paused
        ]
        if participant_ids and run_ids:
            host_run = await session.get(RunRow, run_ids[0])
            assert host_run is not None
            await invite(
                session,
                owner_id,
                thread,
                host_run,
                participant_ids,
                request.content,
                message_id=message.id,
                session_id=collaboration.id if collaboration else None,
            )
    return run_ids


async def supersede(
    session: AsyncSession, owner_id: str, thread_id: str, original_id: str
) -> MessageRow:
    """Edit and resend (Q21), inside the admission transaction that holds the thread lock.

    The original must be the owner's own plain text message in this thread (no
    attachments, voice transcript or input answer) that was not edited before. Its still
    active conversational runs are cancelled through the ordinary cancellation path; the
    new message is then admitted normally and carries ``edited_from``. Nothing is deleted.
    """
    from .thread_prefs import hidden_floor

    original = await session.get(MessageRow, original_id)
    if (
        original is None
        or original.thread_id != thread_id
        or original.seq <= await hidden_floor(session, owner_id, thread_id)
    ):
        raise LonoraError("message_not_found", 404)
    receipt = await session.get(EffectReceiptRow, "message:" + original.id)
    if (
        original.role != "user"
        or original.attachment_ids
        or (original.client_nonce or "").startswith("voice:")
        # A voice note's words are the recording's; there is no text to edit.
        or any(
            cast(dict[str, Any], part).get("type") == "voice"
            for part in cast(list[Any], (original.rich_content or {}).get("parts", []))
            if isinstance(part, dict)
        )
        or (receipt is not None and receipt.result.get("input_answer"))
    ):
        raise LonoraError("message_not_editable", 409)
    if await session.scalar(select(MessageRow.id).where(MessageRow.edited_from == original.id)):
        raise LonoraError("message_already_edited", 409)
    active = list(
        await session.scalars(
            select(RunRow.id).where(
                RunRow.thread_id == thread_id,
                RunRow.trigger.in_(["user", "group"]),
                RunRow.input_seq == original.seq,
                RunRow.status.not_in(TERMINAL),
            )
        )
    )
    for run_id in active:
        await cancel_run(session, owner_id, run_id)
    # Sent while another reply was running, the original may wait in that run's steering
    # queue: it is withdrawn, so the running reply never reads the replaced instruction.
    await session.execute(
        delete(SteeringRow).where(
            SteeringRow.message_id == original.id, SteeringRow.consumed.is_(False)
        )
    )
    return original
