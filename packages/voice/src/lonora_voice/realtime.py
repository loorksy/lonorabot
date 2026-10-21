"""Resident GPT-Live sideband: microphone stays on WebRTC; tools stay in Lonora."""

import asyncio
import hashlib
import json
import time
from copy import deepcopy
from typing import Any

from lonora_adapters.voice.realtime import OpenAILiveAdapter
from lonora_contracts.domain import MessageCreate
from lonora_db.client import Database
from lonora_db.events import emit
from lonora_db.messages import send_message
from lonora_db.schema import MessageRow, RunRow, TradeApprovalRow, VoiceSessionRow
from lonora_providers.credentials import ProviderCredentials
from sqlalchemy import select
from websockets.asyncio.client import ClientConnection

APPROVAL_CARD = (
    "The approval card is inside this call and has Approve and Reject buttons. "
    "Tell the owner only to press one button. Do not ask them to say or type yes, "
    "and do not ask which pair or to repeat the symbol. Speech and chat text are not "
    "approval. Do not start another order."
)
TRANSCRIPT_HANDOFF_TIMEOUT_SECONDS = 30
TRANSCRIPT_HANDOFF_FAILURE = (
    "I couldn't pass that voice turn to Lonora, so I haven't started new work. "
    "You can continue in this call or send a message in the chat; any ongoing work is preserved."
)


def text_chunks(content: str) -> list[str]:
    """Every append is under 500 UTF-8 bytes, conservatively below 500 tokens."""
    chunks: list[str] = []
    current = ""
    if len(content) > 2400:
        content = content[:2400] + "\nThe full backend result is available in the chat transcript."
    for character in content:
        if len((current + character).encode()) > 480:
            chunks.append(current)
            current = ""
        current += character
    if current:
        chunks.append(current)
    return chunks


class RealtimeVoiceSession:
    def __init__(
        self, db: Database, credentials: ProviderCredentials, session_id: str, gateway: str
    ):
        self.db, self.credentials, self.session_id, self.gateway = (
            db,
            credentials,
            session_id,
            gateway,
        )
        self.last_audio_write = 0.0
        self.lost_lease = False
        self.adapter: OpenAILiveAdapter | None = None
        self.connection: ClientConnection | None = None

    async def update(self, event: dict[str, Any]) -> None:
        async with self.db.sessions() as session, session.begin():
            row = await session.get(VoiceSessionRow, self.session_id, with_for_update=True)
            if row is None or row.state.get("gateway") != self.gateway:
                return
            state = deepcopy(row.state)
            kind = event.get("type")
            if kind in {"session.input_transcript.delta", "session.output_transcript.delta"}:
                channel = "input" if kind == "session.input_transcript.delta" else "output"
                fragments = list(state.get(channel, []))
                fragment = {
                    key: event.get(key) for key in ("event_id", "start_ms", "end_ms", "delta")
                }
                if isinstance(fragment["delta"], str) and not any(
                    item.get("event_id") == fragment["event_id"] for item in fragments
                ):
                    fragments.append(fragment)
                    removed = fragments[:-2048]
                    state[channel] = fragments[-2048:]
                    if channel == "input" and removed:
                        state["input_trimmed_until"] = max(
                            float(state.get("input_trimmed_until", -1)),
                            max(float(item.get("end_ms") or 0) for item in removed),
                        )
                    emit(
                        session,
                        row.owner_id,
                        "voice.transcript",
                        thread_id=row.thread_id,
                        agent_id=row.agent_id,
                        payload={"session_id": row.id, "channel": channel, **fragment},
                    )
            elif kind == "session.delegation.created":
                delegation = event.get("delegation", {})
                if delegation.get("target") == "client" and isinstance(delegation.get("id"), str):
                    entries = dict(state.get("delegations", {}))
                    entries.setdefault(
                        delegation["id"],
                        {
                            "offset": event.get("offset_ms", 0),
                            "received_at": time.time(),
                            "status": "pending",
                        },
                    )
                    state["delegations"] = entries
            elif kind == "session.commentary.appended":
                entries = dict(state.get("delegations", {}))
                for task in entries.values():
                    if task.get("event_id") == event.get("client_event_id"):
                        task["next_chunk"] = int(task.get("next_chunk", 0)) + 1
                        task.pop("event_id", None)
                        task.pop("sent_at", None)
                state["delegations"] = entries
            elif kind in {"session.usage", "session.closed"}:
                state["usage"] = event.get("usage", {})
                if kind == "session.closed":
                    state["finalized"] = True
                    row.payload = {**row.payload, "status": "closed"}
            elif kind == "error":
                # Provider error messages may contain request details; persist only its code.
                state["provider_error"] = str(
                    event.get("error", {}).get("code") or "voice_connection_failed"
                )
                row.payload = {
                    **row.payload,
                    "status": "failed",
                    "error": "voice_connection_failed",
                }
            if kind not in {"session.usage", "session.input_audio.append"}:
                state["last_activity"] = time.time()
            elif kind == "session.input_audio.append":
                state["last_activity"] = time.time()
            row.state = state

    async def delegate(self) -> None:
        async with self.db.sessions() as session, session.begin():
            row = await session.get(VoiceSessionRow, self.session_id, with_for_update=True)
            if (
                row is None
                or row.state.get("gateway") != self.gateway
                or row.payload.get("status") != "connected"
            ):
                return
            state = deepcopy(row.state)
            entries = dict(state.get("delegations", {}))
            fragments = list(state.get("input", []))
            for identity, task in entries.items():
                if task.get("status") != "pending":
                    continue
                offset = float(task.get("offset", 0))
                previous = float(state.get("input_offset", -1))
                selected = [
                    fragment
                    for fragment in fragments
                    if float(fragment.get("start_ms") or 0) <= offset
                    and float(fragment.get("end_ms") or 0) > previous
                ]
                selected.sort(
                    key=lambda fragment: (
                        float(fragment.get("start_ms") or 0),
                        float(fragment.get("end_ms") or 0),
                        str(fragment.get("event_id") or ""),
                    )
                )
                spoken = "".join(str(fragment.get("delta") or "") for fragment in selected).strip()
                caught_up = (
                    selected
                    and max(float(fragment.get("end_ms") or 0) for fragment in selected) >= offset
                )
                if (
                    not spoken
                    or not caught_up
                    or float(state.get("input_trimmed_until", -1)) > previous
                    or len(spoken) > 30000
                ):
                    if (
                        time.time() - float(task["received_at"])
                        > TRANSCRIPT_HANDOFF_TIMEOUT_SECONDS
                    ):
                        task.update(
                            {
                                "status": "result",
                                "chunks": [TRANSCRIPT_HANDOFF_FAILURE],
                                "next_chunk": 0,
                            }
                        )
                        state["input_offset"] = offset
                    continue
                pending_approval = await session.scalar(
                    select(TradeApprovalRow.id).where(
                        TradeApprovalRow.thread_id == row.thread_id,
                        TradeApprovalRow.status == "pending",
                    )
                )
                if pending_approval:
                    # Another spoken fragment must not become a user message: that steering
                    # cancels the approval before the owner can press the button.
                    task.update(
                        {
                            "status": "result",
                            "chunks": text_chunks(APPROVAL_CARD),
                            "next_chunk": 0,
                        }
                    )
                    continue
                nonce = "voice:" + hashlib.sha256((row.id + identity).encode()).hexdigest()[:64]
                receipt = await send_message(
                    session,
                    row.owner_id,
                    row.thread_id or "",
                    MessageCreate(content=spoken, client_nonce=nonce),
                )
                task.update({"status": "running", "run_ids": receipt["run_ids"]})
                state["input_offset"] = offset
            state["delegations"] = entries
            row.state = state

    async def tick(self) -> bool:
        commands: list[dict[str, Any]] = []
        async with self.db.sessions() as session, session.begin():
            row = await session.get(VoiceSessionRow, self.session_id, with_for_update=True)
            if row is None or row.state.get("gateway") != self.gateway:
                self.lost_lease = True
                return False
            state = deepcopy(row.state)
            state["lease_until"] = time.time() + 60
            if row.payload.get("status") in {"closing", "closed", "failed"}:
                row.state = state
                return False
            interruption = int(state.get("speech_interrupt_requested", 0))
            if interruption > int(state.get("speech_interrupt_consumed", 0)):
                commands.append(
                    {
                        "type": "session.instructions.append",
                        "event_id": f"speech-interrupt:{row.id}:{interruption}",
                        "delegation_id": None,
                        "content": "Stop speaking and listen. Preserve ongoing background tasks and financial operations; speech interruption does not cancel or pause work.",
                    }
                )
                state["speech_interrupt_consumed"] = interruption
            entries = dict(state.get("delegations", {}))
            for identity, task in entries.items():
                if task.get("status") == "running":
                    runs = [await session.get(RunRow, run_id) for run_id in task.get("run_ids", [])]
                    waiting_ids = [run.id for run in runs if run and run.status == "waiting_input"]
                    pending_approval = (
                        await session.scalar(
                            select(TradeApprovalRow.id)
                            .where(
                                TradeApprovalRow.owner_id == row.owner_id,
                                TradeApprovalRow.thread_id == row.thread_id,
                                TradeApprovalRow.run_id.in_(waiting_ids),
                                TradeApprovalRow.status.in_(["pending", "approved"]),
                            )
                            .limit(1)
                        )
                        if waiting_ids
                        else None
                    )
                    if pending_approval:
                        # Approval is a pause of the same durable delegation, not its
                        # final outcome. Continue observing the resumed original run.
                        if not task.get("approval_notice_sent"):
                            task["approval_notice_sent"] = True
                            commands.append(
                                {
                                    "type": "session.commentary.append",
                                    "event_id": "approval-"
                                    + hashlib.sha256(identity.encode()).hexdigest()[:32],
                                    "delegation_id": identity,
                                    "content": APPROVAL_CARD,
                                }
                            )
                        continue
                    if not runs:
                        task.update(
                            {
                                "status": "result",
                                "chunks": [
                                    "The agent is paused or unavailable. No work was started."
                                ],
                                "next_chunk": 0,
                            }
                        )
                    elif all(
                        run
                        and run.status
                        in {"completed", "failed", "cancelled", "waiting_input", "waiting_takeover"}
                        for run in runs
                    ):
                        result: list[str] = []
                        for run in runs:
                            if run is None:
                                continue
                            if run.status == "completed":
                                result.append(
                                    run.result
                                    or "The backend finished; no additional result was returned."
                                )
                            elif run.status == "waiting_input":
                                message = await session.scalar(
                                    select(MessageRow)
                                    .where(
                                        MessageRow.thread_id == run.thread_id,
                                        MessageRow.agent_id == run.agent_id,
                                        MessageRow.role == "assistant",
                                        MessageRow.created_at >= run.created_at,
                                    )
                                    .order_by(MessageRow.seq.desc())
                                    .limit(1)
                                )
                                result.append(
                                    message.content
                                    if message
                                    else "Ask the user for the information the backend still needs."
                                )
                            else:
                                result.append(
                                    "Backend status: " + run.status + ". " + (run.error_code or "")
                                )
                        task.update(
                            {
                                "status": "result",
                                "chunks": text_chunks("\n".join(result)),
                                "next_chunk": 0,
                            }
                        )
                if task.get("status") == "result":
                    index = int(task.get("next_chunk", 0))
                    parts = task.get("chunks", [])
                    if index >= len(parts):
                        task["status"] = "delivered"
                    elif (
                        not task.get("event_id") or time.time() - float(task.get("sent_at", 0)) > 8
                    ):
                        event_id = (
                            "result-"
                            + hashlib.sha256((identity + ":" + str(index)).encode()).hexdigest()[
                                :32
                            ]
                        )
                        task.update({"event_id": event_id, "sent_at": time.time()})
                        commands.append(
                            {
                                "type": "session.commentary.append",
                                "event_id": event_id,
                                "delegation_id": identity,
                                "content": parts[index],
                            }
                        )
            state["delegations"] = entries
            if time.time() - float(state.get("last_activity", time.time())) > 120:
                row.payload = {**row.payload, "status": "closing", "reason": "inactive_transport"}
                row.state = state
                return False
            row.state = state
        if self.connection:
            for command in commands:
                await self.connection.send(json.dumps(command))
        return True

    async def serve(self) -> None:
        remote_id = ""
        finalized = False
        try:
            self.adapter = OpenAILiveAdapter(await self.credentials.resolve("openai"))
            async with self.db.sessions() as session:
                row = await session.get(VoiceSessionRow, self.session_id)
                if row is None:
                    return
                remote_id = str(row.payload["remote_id"])
            async with self.adapter.attach(remote_id) as connection:
                self.connection = connection
                async with self.db.sessions() as session, session.begin():
                    row = await session.get(VoiceSessionRow, self.session_id, with_for_update=True)
                    if row is None or row.state.get("gateway") != self.gateway:
                        return
                    if row.payload.get("status") not in {"closing", "closed", "failed"}:
                        row.payload = {**row.payload, "status": "connected"}
                receiver = asyncio.create_task(self.receive(connection))
                try:
                    while not receiver.done() and await self.tick():
                        await self.delegate()
                        await asyncio.sleep(0.35)
                    if self.lost_lease:
                        return
                    await connection.send(json.dumps({"type": "session.close"}))
                    try:
                        await asyncio.wait_for(asyncio.shield(receiver), 5)
                    except TimeoutError:
                        pass
                    async with self.db.sessions() as session:
                        row = await session.get(VoiceSessionRow, self.session_id)
                        finalized = bool(row and row.state.get("finalized"))
                finally:
                    receiver.cancel()
                    await asyncio.gather(receiver, return_exceptions=True)
        except asyncio.CancelledError:
            # Gateway shutdown must not resubmit or cancel the separate durable backend run.
            if self.adapter and remote_id:
                finalized = await self.adapter.close_session(remote_id)
            raise
        except Exception:
            if self.adapter and remote_id and not self.lost_lease:
                finalized = await self.adapter.close_session(remote_id)
            async with self.db.sessions() as session, session.begin():
                row = await session.get(VoiceSessionRow, self.session_id, with_for_update=True)
                if row and row.state.get("gateway") == self.gateway:
                    row.payload = {
                        **row.payload,
                        "status": "failed",
                        "error": "voice_connection_failed",
                    }
        finally:
            async with self.db.sessions() as session, session.begin():
                row = await session.get(VoiceSessionRow, self.session_id, with_for_update=True)
                if row and row.state.get("gateway") == self.gateway:
                    row.payload = {
                        **row.payload,
                        "status": "closed" if row.payload.get("status") != "failed" else "failed",
                    }
                    row.state = {
                        **row.state,
                        "finalized": bool(row.state.get("finalized") or finalized),
                    }

    async def receive(self, connection: ClientConnection) -> None:
        async for raw in connection:
            event: dict[str, Any] = json.loads(raw)
            if event.get("type") in {"session.input_audio.append", "session.output_audio.delta"}:
                # Do not retain raw audio; record transport activity at a bounded cadence.
                if time.monotonic() - self.last_audio_write < 5:
                    continue
                self.last_audio_write = time.monotonic()
            await self.update(event)
            if event.get("type") == "session.closed":
                return
