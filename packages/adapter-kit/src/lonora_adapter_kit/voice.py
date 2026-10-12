from typing import Protocol


class SpeechToText(Protocol):
    async def transcribe(self, audio: bytes, model: str) -> str: ...


class TextToSpeech(Protocol):
    async def synthesize(self, text: str, model: str, voice: str) -> bytes: ...


class VoiceTransport(Protocol):
    async def join_token(self, room: str, identity: str) -> str: ...
