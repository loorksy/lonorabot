class ScriptedSpeech:
    def __init__(self, transcript: str, audio: bytes):
        self.transcript, self.audio = transcript, audio

    async def transcribe(self, audio: bytes, model: str) -> str:
        return self.transcript

    async def synthesize(self, text: str, model: str, voice: str) -> bytes:
        return self.audio
