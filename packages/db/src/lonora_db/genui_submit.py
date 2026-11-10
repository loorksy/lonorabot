"""A generated card's send (GENUI_PLAN §8.2): checked, composed and queued by the server.

The client posts only the card message, its part, the button's node path and the card's
values. Everything else is the server's: the intent comes from the stored card's node; the
data is computed from the stored card and the validated values (server-set fields from the
card's compile record); the owner's bubble is the button label (``ask``) or the intent's
registry template filled with the server's own names. The submission is stored with
``origin='ui_submit'`` and always gets its own queued Run carrying ``ui_submit_origin``
(the taint, §8.5): it never steers or answers an active Run. Its Run is claimed only after
every earlier Run of its agent in the thread has ended (rule Q), reads the thread up to
its claim (rule W), stays invisible to every other Run until it ends and for good if it
never started (rules V and N), takes its ticks from its own Run (rule T) and is cancelled
30 minutes after the submission if it has not started (rule L).
"""

from __future__ import annotations

import math
from datetime import timedelta
from typing import Any, cast

from lonora_contracts.domain import MessageCreate, utcnow
from lonora_contracts.genui import UiDocument, node_at, walk
from lonora_contracts.genui_expr import environment, evaluate, render_template
from lonora_contracts.genui_intents import (
    REGISTRY,
    IntentDataError,
    compose_bubble,
    intent_denied,
    validate_data,
    watch_name,
)
from lonora_core.public_reply import public_reply_violation
from lonora_core.user_error import LonoraError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .agent_state import watch_summary
from .conversation_locale import conversation_locale
from .events import emit
from .genui_taint import SUBMIT
from .owner_words import TERMINAL, ui_submit_origin
from .schema import (
    AgentRow,
    BrokerSessionRow,
    EffectReceiptRow,
    MarketWatchRow,
    MessageRow,
    RunRow,
    ThreadRow,
)
from .transactions import owned_agent

SUBMIT_LIFETIME = timedelta(minutes=30)
WAITING = ("waiting_input", "waiting_takeover")
NEVER_RAN_NOTE = "طلب من بطاقة لم يُنفَّذ"
# Intents the S-A01 slice lists (the capability block, §3.6); a submit is checked again.
LISTED_INTENTS = ("ask", "alert.create", "alert.off")


def card_document(row: MessageRow, part: int) -> dict[str, Any] | None:
    """The compiled v2 card at ``part`` of an assistant message, or None."""
    parts = (row.rich_content or {}).get("parts", [])
    if row.role != "assistant" or not 0 <= part < len(parts):
        return None
    item: dict[str, Any] = parts[part] if isinstance(parts[part], dict) else {}
    document: Any = item.get("document")
    if not isinstance(document, dict) or item.get("building"):
        return None
    document = cast(dict[str, Any], document)
    return document if document.get("v") == 2 else None


def option_values(node: dict[str, Any]) -> list[Any]:
    options = cast(list[Any], node.get("options", []))
    return [cast(dict[str, Any], o).get("value") if isinstance(o, dict) else o for o in options]


def unlocked_seq(card: MessageRow, part: int) -> int:
    parts: Any = (card.ui_state or {}).get("parts") or {}
    entry: Any = cast(dict[str, Any], parts).get(str(part)) if isinstance(parts, dict) else None
    if isinstance(entry, dict):
        return int(cast(dict[str, Any], entry).get("unlocked_seq") or 0)
    return 0


def never_ran(submit: dict[str, Any] | None, status: str | None) -> bool:
    """Rule N: its Run is terminal and never started."""
    return bool(submit) and not (submit or {}).get("started_at") and status in TERMINAL


async def submit_status(session: AsyncSession, row: MessageRow) -> str | None:
    run_id = (row.ui_submit or {}).get("run_id")
    if not run_id:
        return None
    return await session.scalar(select(RunRow.status).where(RunRow.id == run_id))


async def card_locks(
    session: AsyncSession, thread_id: str, cards: list[MessageRow]
) -> dict[str, dict[int, dict[str, Any]]]:
    """Per card message and part: the locking submission that replies to it, if any.

    A card is locked when a locking submission with a higher seq than the part's
    ``unlocked_seq`` replies to it and its Run did not end without starting (rule N).
    """
    ids = [row.id for row in cards]
    if not ids:
        return {}
    submits = list(
        await session.scalars(
            select(MessageRow)
            .where(
                MessageRow.thread_id == thread_id,
                MessageRow.origin == "ui_submit",
                MessageRow.reply_to.in_(ids),
            )
            .order_by(MessageRow.seq)
        )
    )
    run_ids = [s.ui_submit.get("run_id") for s in submits if s.ui_submit]
    statuses = (
        dict(
            (
                await session.execute(
                    select(RunRow.id, RunRow.status).where(RunRow.id.in_(run_ids))
                )
            ).all()
        )
        if run_ids
        else {}
    )
    by_id = {row.id: row for row in cards}
    locks: dict[str, dict[int, dict[str, Any]]] = {}
    for submit in submits:
        data = submit.ui_submit or {}
        card = by_id.get(submit.reply_to or "")
        if card is None or not data.get("lock"):
            continue
        part = int(data.get("part", 0))
        if submit.seq <= unlocked_seq(card, part):
            continue
        if never_ran(data, statuses.get(str(data.get("run_id")))):
            continue
        locks.setdefault(card.id, {})[part] = {
            "message_id": submit.id,
            "seq": submit.seq,
            "agent_id": card.agent_id,
        }
    return locks


def _validate_values(document: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    """Values against the card's declared state: keys, types, bounds, option membership."""
    state: dict[str, Any] = document.get("state", {})
    if set(values) - set(state) or len(str(values)) > 8000:
        raise LonoraError("ui_submit_values_invalid", 422)
    options: dict[str, list[Any]] = {}
    numbers: set[str] = set()
    for _path, node in walk(document.get("blocks", [])):
        if node["type"] in {"Segmented", "Select"} and isinstance(node.get("bind"), str):
            options[node["bind"]] = option_values(node)
        if node["type"] in {"Number", "Slider"} and isinstance(node.get("bind"), str):
            numbers.add(node["bind"])
    clean = dict(state)
    for key, value in values.items():
        initial = state[key]
        if key in options:
            if value not in options[key]:
                raise LonoraError("ui_submit_values_invalid", 422)
        elif key in numbers or isinstance(initial, int | float) and not isinstance(initial, bool):
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, int | float)
                or not math.isfinite(value)
                or abs(value) > 1e12
            ):
                raise LonoraError("ui_submit_values_invalid", 422)
        elif isinstance(initial, bool):
            if not isinstance(value, bool):
                raise LonoraError("ui_submit_values_invalid", 422)
        elif isinstance(initial, str) or initial is None:
            if value is not None and not (
                (isinstance(value, str) and len(value) <= 400)
                or isinstance(value, int | float | bool)
            ):
                raise LonoraError("ui_submit_values_invalid", 422)
        elif isinstance(initial, list):
            if not isinstance(value, list) or len(cast(list[Any], value)) > 50:
                raise LonoraError("ui_submit_values_invalid", 422)
        elif not isinstance(value, type(initial)):
            raise LonoraError("ui_submit_values_invalid", 422)
        clean[key] = value
    return clean


async def _identity_names(
    session: AsyncSession,
    owner_id: str,
    document: dict[str, Any],
    intent: str,
    data: dict[str, Any],
) -> dict[str, str]:
    """The server's own names for identity fields (§8.3, Identity values)."""
    names: dict[str, str] = {}
    if intent == "alert.off":
        watch = await session.get(MarketWatchRow, data["watch_id"])
        if (
            watch is None
            or watch.owner_id != owner_id
            or watch.agent_id != document.get("agent_id")
        ):
            raise LonoraError("ui_submit_data_invalid", 422)
        names["watch_id"] = watch_name(watch_summary(watch), "ar")
    if intent == "alert.create":
        accounts = await enabled_accounts(session, owner_id)
        if len(accounts) > 1:
            from .owner_actions import account_facts

            # Read the card's own account directly: the list above is bounded.
            account_id = str(data.get("account_id"))
            row = await session.get(BrokerSessionRow, account_id)
            owned = row if row is not None and row.owner_id == owner_id else None
            label = account_facts(owned, account_id).get("label")
            if not label:
                # The bubble must name the account and cannot (§8.3, account).
                raise LonoraError("ui_submit_account_unnamed", 409)
            names["account_id"] = str(label)
    return names


async def enabled_accounts(session: AsyncSession, owner_id: str) -> list[BrokerSessionRow]:
    """The owner's enabled trading accounts (connections), at most 8 read."""
    rows = await session.scalars(
        select(BrokerSessionRow).where(BrokerSessionRow.owner_id == owner_id).limit(32)
    )
    return [row for row in rows if row.payload.get("enabled", True)][:8]


async def account_label(session: AsyncSession, account_id: str) -> str | None:
    from .owner_actions import account_facts

    row = await session.get(BrokerSessionRow, account_id)
    label = account_facts(row, account_id).get("label") if row is not None else None
    return str(label) if label else None


async def queued_submit(session: AsyncSession, thread_id: str, agent_id: str) -> RunRow | None:
    """This agent's submission in this thread whose Run has not started yet."""
    rows = await session.scalars(
        select(RunRow).where(
            RunRow.thread_id == thread_id,
            RunRow.agent_id == agent_id,
            RunRow.status.in_(["queued", "leased"]),
        )
    )
    for row in rows:
        if row.model_metadata.get("ui_submit_origin") and not row.model_metadata.get(
            "ui_submit_started"
        ):
            return row
    return None


async def submit_card(
    session: AsyncSession, owner_id: str, thread: ThreadRow, request: MessageCreate
) -> tuple[MessageRow, RunRow]:
    """Check everything, then store the bubble, the submission and its own queued Run."""
    submit = request.ui_submit
    assert submit is not None
    if request.mention_agent_ids or request.mention_all or request.collaboration_session_id:
        raise LonoraError("ui_submit_invalid", 422)
    source = await session.get(MessageRow, submit.source_message_id)
    if source is None or source.thread_id != thread.id:
        raise LonoraError("ui_submit_source_invalid", 404)
    document = card_document(source, submit.part)
    if document is None:
        raise LonoraError("ui_submit_source_invalid", 422)
    UiDocument.model_validate(document)
    parts = (source.rich_content or {}).get("parts", [])
    if parts[submit.part].get("cut") is not None:
        raise LonoraError("ui_submit_card_cut", 409)
    node = node_at(document.get("blocks", []), submit.path)
    if node is None or node.get("type") != "Button":
        raise LonoraError("ui_submit_invalid", 422)
    action: dict[str, Any] = cast(
        dict[str, Any],
        node.get("action") or {"do": "send", "intent": "ask", "data": {}, "lock": False},
    )
    if action.get("do") != "send":
        raise LonoraError("ui_submit_invalid", 422)
    intent_name = str(action["intent"])
    intent = REGISTRY.get(intent_name)
    if intent is None or intent_denied(intent_name) or intent_name not in LISTED_INTENTS:
        raise LonoraError("ui_submit_intent_refused", 422)
    lock = bool(action.get("lock", intent.lock) and intent.lock)
    agent_id = source.agent_id or document.get("agent_id")
    if not agent_id:
        raise LonoraError("ui_submit_source_invalid", 422)
    agent: AgentRow = await owned_agent(session, owner_id, agent_id)
    if agent.paused:
        raise LonoraError("agent_paused", 409)
    locks = await card_locks(session, thread.id, [source])
    if lock and submit.part in locks.get(source.id, {}):
        raise LonoraError("ui_submit_locked", 409)
    waiting = await session.scalar(
        select(RunRow.id)
        .where(
            RunRow.thread_id == thread.id,
            RunRow.agent_id == agent_id,
            RunRow.status.in_(WAITING),
        )
        .limit(1)
    )
    if waiting is not None:
        # The owner's next step is that question or approval; a card must not answer it.
        raise LonoraError("ui_submit_waiting", 409)
    if await queued_submit(session, thread.id, agent_id) is not None:
        raise LonoraError("ui_submit_busy", 409)

    values = _validate_values(document, submit.values)
    facts = {key: fact.get("value") for key, fact in document.get("facts", {}).items()}
    env = environment(values, document.get("calc", {}), facts)
    for _path, item in walk(document.get("blocks", [])):
        if item.get("required") and evaluate(item.get("when", True), env, False):
            if env.values.get(str(item.get("bind"))) in (None, ""):
                raise LonoraError("ui_submit_required_missing", 422)
    if action.get("disabled") or (
        node.get("disabled") is not None and evaluate(node["disabled"], env, True)
    ):
        raise LonoraError("ui_submit_disabled", 422)
    data: dict[str, Any] = {}
    for key, source_value in cast(dict[str, Any], action.get("data", {})).items():
        data[key] = (
            env.values.get(source_value[1:])
            if isinstance(source_value, str) and source_value.startswith("$")
            else source_value
        )
    for field in intent.fields:
        if field.server_set:
            if field.type == "account":
                data[field.name] = document.get("account_id")
    try:
        data = validate_data(intent, data)
    except IntentDataError as error:
        raise LonoraError(str(error), 422) from error
    if intent_name == "alert.create":
        # The symbol must be one of the card's own checked options (§8.3).
        offered = {
            value
            for _p, n in walk(document.get("blocks", []))
            if n["type"] in {"Segmented", "Select"}
            for value in option_values(n)
        }
        if data["symbol"] not in offered:
            raise LonoraError("ui_submit_data_invalid", 422)
    language = await conversation_locale(session, owner_id, thread.id)
    if intent_name == "ask":
        content = render_template(str(node["label"]), env).strip()
    else:
        names = await _identity_names(session, owner_id, document, intent_name, data)
        content = compose_bubble(intent, data, language, names)
    if not content or public_reply_violation(content):
        raise LonoraError("ui_submit_text_refused", 422)

    message = MessageRow(
        thread_id=thread.id,
        seq=thread.next_seq,
        role="user",
        content=content,
        reply_to=source.id,
        mentions={"agent_ids": [], "all": False, "session_id": None},
        attachment_ids=[],
        client_nonce=request.client_nonce,
        origin="ui_submit",
    )
    thread.next_seq += 1
    session.add(message)
    await session.flush()
    from lonora_contracts.runs import RunRequest

    from .runs import create_run

    # Through ``create_run``: the thread, group-membership and pause checks of every Run.
    run = await create_run(
        session,
        owner_id,
        RunRequest(
            thread_id=thread.id,
            agent_id=agent_id,
            trigger="group" if thread.group_id else "user",
        ),
    )
    # Only this Run is a submission (the queue rules read it); it is also the taint's root.
    run.model_metadata = {
        **run.model_metadata,
        SUBMIT: {"message_id": message.id, "intent": intent_name},
    }
    # The values the owner sent stay with the card, so a reload on any device shows them.
    ui_state = dict(source.ui_state or {})
    saved = dict(ui_state.get("parts", {}))
    saved[str(submit.part)] = {**saved.get(str(submit.part), {}), "values": values}
    source.ui_state = {**ui_state, "parts": saved, "updated_at": utcnow().isoformat()}
    message.ui_submit = {
        "source_message_id": source.id,
        "part": submit.part,
        "path": submit.path,
        "intent": intent_name,
        "data": data,
        "lock": lock,
        "card_title": str(document.get("title", ""))[:40],
        "run_id": run.id,
    }
    return message, run


async def submission_seq(session: AsyncSession, run: RunRow) -> int | None:
    """The seq of the card submission this Run answers, or None."""
    origin = ui_submit_origin(run)
    if origin is None:
        return None
    message = await session.get(MessageRow, str(origin.get("message_id")))
    return message.seq if message is not None and message.thread_id == run.thread_id else None


async def decorate(
    session: AsyncSession, thread_id: str, rows: list[MessageRow], items: list[dict[str, Any]]
) -> None:
    """Embed the derived card locks and the never-run marks in a history page (§9.3)."""
    cards = [row for row in rows if row.role == "assistant" and row.rich_content]
    locks = await card_locks(session, thread_id, cards)
    by_id = {row.id: row for row in rows}
    for item in items:
        if item["id"] in locks:
            item["ui_lock"] = {str(part): lock for part, lock in locks[item["id"]].items()}
        row = by_id.get(item["id"])
        if row is not None and row.origin == "ui_submit":
            item["ui_mark"] = await submit_mark(session, row)


async def submit_mark(session: AsyncSession, row: MessageRow) -> str | None:
    """«مُعدّلة» (superseded by «تعديل») or «لم يُنفَّذ» (never ran), rule N; else None."""
    submit = row.ui_submit or {}
    if submit.get("mark") in {"superseded", "not_run"}:
        return str(submit["mark"])
    if not never_ran(submit, await submit_status(session, row)):
        return None
    return "superseded" if submit.get("superseded_at") else "not_run"


async def mark_submit_started(session: AsyncSession, run: RunRow) -> None:
    """The first ``running`` transition of a submission's Run (rules N and T): recorded,
    never inferred, because a cancelled Run's status no longer says whether it ran. Clients
    learn it at once, so a send that ran is never shown as never run (review U1)."""
    origin = ui_submit_origin(run)
    if origin is None or run.model_metadata.get("ui_submit_started"):
        return
    now = utcnow().isoformat()
    run.model_metadata = {**run.model_metadata, "ui_submit_started": now}
    message = await session.get(MessageRow, str(origin.get("message_id")), with_for_update=True)
    if message is not None and message.ui_submit and not message.ui_submit.get("started_at"):
        message.ui_submit = {**message.ui_submit, "started_at": now}
        await _updated(session, message)


async def _updated(session: AsyncSession, message: MessageRow) -> None:
    from .messages import message_data

    thread = await session.get(ThreadRow, message.thread_id)
    if thread is not None:
        emit(
            session,
            thread.owner_id,
            "message.updated",
            thread_id=message.thread_id,
            payload=message_data(message),
        )


async def settle_unstarted(session: AsyncSession, run: RunRow) -> None:
    """Rule N recorded by the server when a submission's Run ends without starting:
    «مُعدّلة» after «تعديل», «لم يُنفَّذ» otherwise. Clients read this fact, never infer it
    from a Run's status (review U1)."""
    origin = ui_submit_origin(run)
    if origin is None or run.model_metadata.get("ui_submit_started") or run.status not in TERMINAL:
        return
    message = await session.get(MessageRow, str(origin.get("message_id")), with_for_update=True)
    if message is None or not message.ui_submit or message.ui_submit.get("mark"):
        return
    mark = "superseded" if message.ui_submit.get("superseded_at") else "not_run"
    message.ui_submit = {**message.ui_submit, "mark": mark}
    await _updated(session, message)


async def expire_submits(session: AsyncSession, thread_id: str | None = None) -> list[RunRow]:
    """Rule L: a submission not started 30 minutes after it was sent is cancelled
    (``ui_submit_expired``), settled lazily at claim and on read, with no countdown."""
    query = select(RunRow).where(
        RunRow.status == "queued",
        RunRow.created_at <= utcnow() - SUBMIT_LIFETIME,
        # Only submissions (the marker, never the taint) that have not started.
        RunRow.model_metadata[SUBMIT].as_string().is_not(None),
        RunRow.model_metadata["ui_submit_started"].as_string().is_(None),
    )
    if thread_id is not None:
        query = query.where(RunRow.thread_id == thread_id)
    expired: list[RunRow] = []
    query = query.order_by(RunRow.created_at).limit(50).with_for_update(skip_locked=True)
    for run in await session.scalars(query):
        run.status = "cancelled"
        run.error_code = "ui_submit_expired"
        run.updated_at = utcnow()
        run.lease_fence += 1
        thread = await session.get(ThreadRow, run.thread_id)
        if thread is not None:
            emit(
                session,
                thread.owner_id,
                "run.cancelled",
                thread_id=run.thread_id,
                agent_id=run.agent_id,
                run_id=run.id,
                payload={"code": "ui_submit_expired"},
            )
        await settle_unstarted(session, run)
        expired.append(run)
    return expired


async def unlock_card(
    session: AsyncSession, owner_id: str, thread: ThreadRow, message_id: str, part: int
) -> dict[str, Any]:
    """«تعديل»: record ``unlocked_seq`` and, in the same transaction, cancel the locking
    submission's Run if it has not started (Q21) and mark it superseded (rule N)."""
    source = await session.get(MessageRow, message_id, with_for_update=True)
    if source is None or source.thread_id != thread.id or card_document(source, part) is None:
        raise LonoraError("message_not_found", 404)
    locks = await card_locks(session, thread.id, [source])
    lock = locks.get(source.id, {}).get(part)
    if lock is None:
        return {"unlocked": True}
    submit = await session.get(MessageRow, lock["message_id"], with_for_update=True)
    assert submit is not None and submit.ui_submit is not None
    run = await session.get(RunRow, submit.ui_submit.get("run_id"), with_for_update=True)
    if (
        run is not None
        and run.status not in TERMINAL
        and not run.model_metadata.get("ui_submit_started")
    ):
        from .cancellation import cancel_run

        # Superseded first, so the cancellation records «مُعدّلة» (Q21, review U2).
        submit.ui_submit = {**submit.ui_submit, "superseded_at": utcnow().isoformat()}
        await cancel_run(session, owner_id, run.id)
    state = dict(source.ui_state or {})
    parts = dict(state.get("parts", {}))
    parts[str(part)] = {**parts.get(str(part), {}), "unlocked_seq": submit.seq}
    source.ui_state = {**state, "parts": parts, "updated_at": utcnow().isoformat()}
    from .messages import message_data

    emit(session, owner_id, "message.updated", thread_id=thread.id, payload=message_data(source))
    return {"unlocked": True, "cancelled_run_id": run.id if run else None}


def submit_receipt(message: MessageRow, run: RunRow, request: MessageCreate) -> EffectReceiptRow:
    assert request.ui_submit is not None
    return EffectReceiptRow(
        key="message:" + message.id,
        result={"run_ids": [run.id], "ui_submit": request.ui_submit.model_dump(mode="json")},
    )
