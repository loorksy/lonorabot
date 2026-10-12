import asyncio
import io
import wave
from array import array
from typing import Any, cast

from livekit import rtc
from lonora_adapters.voice.livekit import LiveKitTransport
from lonora_bus.durable_events import stream_events
from lonora_contracts.domain import new_id
from lonora_contracts.voice import VoiceTranscript
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.schema import VoiceSessionRow
from lonora_providers.credentials import ProviderCredentials

from .barge_in import barge_in
from .synthesis import pcm_24000, synthesize
from .transcript import commit_transcript
from .transcription import transcribe


def wav_segment(pcm: bytes) -> bytes:
    target = io.BytesIO()
    with wave.open(target, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(pcm)
    return target.getvalue()


class RealtimeVoiceSession:
    """LiveKit transports audio; all transcripts execute through the existing agent run path."""

    def __init__(
        self,
        db: Database,
        credentials: ProviderCredentials,
        session_id: str,
        url: str,
        key: str,
        secret: str,
        gateway_id: str = "",
    ):
        self.db, self.credentials, self.session_id, self.url = db, credentials, session_id, url
        self.transport = LiveKitTransport(key, secret)
        self.room = rtc.Room()
        self.source = rtc.AudioSource(24000, 1)
        self.tasks: set[asyncio.Task[None]] = set()
        self.owner_id = ""
        self.thread_id = ""
        self.gateway_id = gateway_id
        self.failure: str | None = None
        self.speaking = False
        self.interrupted = asyncio.Event()

    def task_finished(self, task: asyncio.Task[None]) -> None:
        self.tasks.discard(task)
        if not task.cancelled() and task.exception():
            error = task.exception()
            self.failure = (
                error.code if isinstance(error, LonoraError) else "voice_transport_failed"
            )

    async def assert_connection(self) -> None:
        async with self.db.sessions() as session:
            row = await session.get(VoiceSessionRow, self.session_id)
            if (
                row is None
                or row.payload.get("status") != "connected"
                or (self.gateway_id and row.state.get("gateway") != self.gateway_id)
            ):
                raise LonoraError("voice_session_closed", 409)

    async def input_track(self, track: rtc.Track) -> None:
        stream = rtc.AudioStream(track, sample_rate=24000, num_channels=1)
        segment = bytearray()
        silence = 0.0
        voiced = False
        async for event in stream:
            frame = event.frame
            data = bytes(frame.data)
            samples = array("h", data)
            energy = sum(abs(value) for value in samples) / max(1, len(samples))
            duration = frame.samples_per_channel / frame.sample_rate
            audible = energy > 220
            if audible:
                if self.speaking:
                    self.interrupted.set()
                    self.source.clear_queue()
                    await barge_in(self.db, self.owner_id, self.thread_id)
                voiced = True
                silence = 0
            else:
                silence += duration
            if voiced:
                segment.extend(data)
            if voiced and (silence >= 0.75 or len(segment) >= 24000 * 2 * 15):
                audio = wav_segment(bytes(segment))
                segment.clear()
                voiced = False
                silence = 0
                text = await transcribe(self.db, self.credentials, audio)
                await self.assert_connection()
                if text.strip():
                    await commit_transcript(
                        self.db,
                        self.owner_id,
                        self.thread_id,
                        VoiceTranscript(text=text, client_nonce=self.session_id + ":" + new_id()),
                    )

    async def output_messages(self, cursor: int) -> None:
        async for event in stream_events(self.db, self.owner_id, cursor, self.thread_id):
            payload = event["payload"]
            if event["kind"] != "message.created" or payload.get("role") != "assistant":
                continue
            await self.assert_connection()
            self.interrupted.clear()
            self.speaking = True
            audio = pcm_24000(
                await synthesize(self.db, self.credentials, str(payload.get("content", "")))
            )
            try:
                for offset in range(0, len(audio), 960):
                    if self.interrupted.is_set():
                        break
                    chunk = audio[offset : offset + 960]
                    if len(chunk) < 960:
                        chunk += b"\0" * (960 - len(chunk))
                    await self.source.capture_frame(
                        rtc.AudioFrame(chunk, 24000, 1, len(chunk) // 2)
                    )
                await self.source.wait_for_playout()
            finally:
                self.speaking = False

    async def serve(self) -> None:
        from lonora_db.schema import EventRow
        from sqlalchemy import func, select

        async with self.db.sessions() as session:
            row = await session.get(VoiceSessionRow, self.session_id)
            if row is None or not row.thread_id:
                return
            self.owner_id, self.thread_id = row.owner_id, row.thread_id
            room_name = row.payload["room"]
            cursor = (await session.scalar(select(func.max(EventRow.cursor)))) or 0
        token = await self.transport.join_token(room_name, "agent:" + self.session_id)

        def on_track(
            track: rtc.Track,
            publication: rtc.RemoteTrackPublication,
            participant: rtc.RemoteParticipant,
        ) -> None:
            if track.kind == rtc.TrackKind.KIND_AUDIO and participant.identity.startswith(
                "owner:" + self.owner_id + ":" + self.session_id
            ):
                task = asyncio.create_task(self.input_track(track))
                self.tasks.add(task)
                task.add_done_callback(self.task_finished)

        cast(Any, self.room).on("track_subscribed", on_track)
        try:
            await self.room.connect(self.url, token)
            track = rtc.LocalAudioTrack.create_audio_track("lonora-voice", self.source)
            await self.room.local_participant.publish_track(
                track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
            )
            output = asyncio.create_task(self.output_messages(cursor))
            self.tasks.add(output)
            output.add_done_callback(self.task_finished)
            async with self.db.sessions() as session, session.begin():
                row = await session.get(VoiceSessionRow, self.session_id, with_for_update=True)
                if row:
                    row.payload = {**row.payload, "status": "connected"}
            while True:
                await asyncio.sleep(2)
                async with self.db.sessions() as session:
                    row = await session.get(VoiceSessionRow, self.session_id)
                    if self.failure:
                        raise LonoraError(self.failure, 502)
                    if (
                        row is None
                        or row.payload.get("status") == "closed"
                        or (self.gateway_id and row.state.get("gateway") != self.gateway_id)
                    ):
                        break
        except Exception as error:
            async with self.db.sessions() as session, session.begin():
                row = await session.get(VoiceSessionRow, self.session_id, with_for_update=True)
                if row:
                    row.state = {
                        **row.state,
                        "code": error.code
                        if isinstance(error, LonoraError)
                        else "voice_transport_failed",
                    }
                    row.payload = {**row.payload, "status": "failed"}
        finally:
            for task in self.tasks:
                task.cancel()
            await asyncio.gather(*self.tasks, return_exceptions=True)
            await self.room.disconnect()
