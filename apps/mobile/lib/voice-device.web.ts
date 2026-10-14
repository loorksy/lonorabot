import { ApiError } from "./api-error";
import type { VoiceDevice, VoiceMedia, VoicePeer } from "./voice-types";

export function createVoiceDevice(): VoiceDevice {
  if (typeof RTCPeerConnection === "undefined" || !navigator.mediaDevices?.getUserMedia)
    throw new ApiError("voice_browser_unsupported", 409);
  const peer = new RTCPeerConnection();
  const audio = document.createElement("audio");
  audio.autoplay = true;
  peer.ontrack = (event) => {
    audio.srcObject = event.streams[0] ?? new MediaStream([event.track]);
    void audio.play().catch(() => undefined);
  };
  return {
    peer: peer as unknown as VoicePeer,
    microphone: () =>
      navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      }) as unknown as Promise<VoiceMedia>,
    startAudio() {},
    muteAudio() {},
    stopAudio() {
      audio.pause();
      audio.srcObject = null;
      audio.remove();
    },
  };
}
