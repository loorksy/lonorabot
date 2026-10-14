import { ApiError } from "./api-error";
import type { VoiceActivity, VoiceChannel, VoiceDevice, VoiceMedia } from "./voice-types";

export type VoiceApi = {
  post<T>(path: string, body: unknown): Promise<T>;
  delete<T>(path: string): Promise<T>;
};

export class MobileVoiceJoin {
  sessionId: string | null = null;
  readonly nonce =
    `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
  private device: VoiceDevice;
  private microphone: VoiceMedia | null = null;
  private channel: VoiceChannel | null = null;
  private disposed = false;
  private closing: Promise<void> | null = null;
  private timer: ReturnType<typeof setInterval> | undefined;
  private outputAt = 0;
  private muted = false;
  private finalized = false;
  private resolveEnded: (() => void) | null = null;
  private ended = new Promise<void>((resolve) => {
    this.resolveEnded = resolve;
  });

  constructor(
    private status: (connected: boolean) => void,
    private error: (reason: unknown) => void,
    private activity: (value: VoiceActivity) => void,
    private onClosed: () => void,
    device: VoiceDevice,
    private api: VoiceApi,
  ) {
    this.device = device;
    this.device.peer.addEventListener("connectionstatechange", () => {
      if (this.disposed) return;
      const state = this.device.peer.connectionState;
      if (state === "connected") this.status(true);
      if (["disconnected", "failed", "closed"].includes(state)) {
        this.error(new ApiError("voice_connection_failed", 502));
        void this.close().catch(this.error);
      }
    });
  }

  async connect(agentId: string, threadId: string) {
    try {
      this.microphone = await this.device.microphone();
      if (this.disposed) {
        this.microphone.getTracks().forEach((track) => {
          track.stop();
        });
        return;
      }
      this.device.startAudio();
      this.setMuted(this.muted);
      for (const track of this.microphone.getAudioTracks())
        this.device.peer.addTrack(track, this.microphone);
      this.channel = this.device.peer.createDataChannel("oai-events");
      this.channel.addEventListener("message", ({ data }) => {
        try {
          const event = JSON.parse(data ?? "{}") as Record<string, unknown>;
          if (event.type === "session.closed") {
            this.finalized = true;
            this.resolveEnded?.();
            void this.close().catch(this.error);
          }
          if (this.disposed) return;
          if (event.type === "session.started") this.status(true);
          if (event.type === "error") this.error(new ApiError("voice_connection_failed", 502));
          if (
            event.type === "session.output_audio.delta" ||
            event.type === "session.output_transcript.delta"
          )
            this.outputAt = Date.now();
        } catch {
          this.error(new ApiError("voice_response_invalid", 502));
        }
      });
      this.channel.addEventListener("close", () => {
        if (!this.disposed) void this.close().catch(this.error);
      });
      await this.device.peer.setLocalDescription(await this.device.peer.createOffer());
      if (this.device.peer.iceGatheringState !== "complete") await this.waitIce();
      if (this.disposed) return;
      const sdp = this.device.peer.localDescription?.sdp;
      if (!sdp) throw new ApiError("voice_response_invalid", 502);
      const result = await this.api.post<{ session_id: string; sdp: string }>("/voice/sessions", {
        agent_id: agentId,
        thread_id: threadId,
        mode: "gpt_live",
        client_nonce: this.nonce,
        sdp,
      });
      this.sessionId = result.session_id;
      if (this.disposed) {
        await this.api.delete(`/voice/sessions/${encodeURIComponent(result.session_id)}`);
        return;
      }
      await this.device.peer.setRemoteDescription({ type: "answer", sdp: result.sdp });
      let sampling = false;
      this.timer = setInterval(() => {
        if (sampling || this.disposed) return;
        sampling = true;
        void this.sample().finally(() => {
          sampling = false;
        });
      }, 150);
    } catch (reason) {
      if (!this.disposed) {
        this.error(
          reason instanceof Error && reason.name === "NotAllowedError"
            ? new ApiError("voice_permission_denied", 403)
            : reason,
        );
        await this.close();
      }
    }
  }

  private waitIce(): Promise<void> {
    return new Promise((resolve, reject) => {
      const check = () => {
        if (this.disposed || this.device.peer.iceGatheringState === "complete") {
          clearTimeout(timer);
          this.device.peer.removeEventListener("icegatheringstatechange", check);
          resolve();
        }
      };
      const timer = setTimeout(() => {
        this.device.peer.removeEventListener("icegatheringstatechange", check);
        reject(new ApiError("voice_connection_failed", 504));
      }, 10_000);
      this.device.peer.addEventListener("icegatheringstatechange", check);
      check();
    });
  }

  private async sample() {
    let input = 0,
      output = 0;
    try {
      const stats = await this.device.peer.getStats();
      stats.forEach((value) => {
        if (value.kind !== "audio" && value.mediaType !== "audio") return;
        const level =
          typeof value.audioLevel === "number" ? Math.max(0, Math.min(1, value.audioLevel)) : 0;
        if (["media-source", "outbound-rtp"].includes(String(value.type)))
          input = Math.max(input, level);
        if (value.type === "inbound-rtp") output = Math.max(output, level);
      });
    } catch {
      /* Meters are optional; call transport remains authoritative. */
    }
    if (this.disposed) return;
    if (output > 0.03) this.outputAt = Date.now();
    const speaking = Date.now() - this.outputAt < 650;
    this.activity({
      phase: speaking ? "speaking" : "listening",
      level: speaking ? output : this.muted ? 0 : input,
    });
  }

  setMuted(value: boolean) {
    this.muted = value;
    this.microphone?.getAudioTracks().forEach((track) => {
      track.enabled = !value;
    });
    if (this.microphone && !this.disposed) this.device.muteAudio(value);
  }

  close(): Promise<void> {
    if (this.closing) return this.closing;
    this.disposed = true;
    clearInterval(this.timer);
    this.microphone?.getTracks().forEach((track) => {
      track.stop();
    });
    this.device.stopAudio();
    this.status(false);
    this.closing = Promise.resolve().then(async () => {
      try {
        if (!this.finalized && this.channel?.readyState === "open") {
          this.channel.send(JSON.stringify({ type: "session.close" }));
          let timer: ReturnType<typeof setTimeout> | undefined;
          await Promise.race([
            this.ended,
            new Promise<void>((resolve) => {
              timer = setTimeout(resolve, 2500);
            }),
          ]);
          clearTimeout(timer);
        }
        if (this.sessionId)
          await this.api.delete(`/voice/sessions/${encodeURIComponent(this.sessionId)}`);
        else await this.api.post("/voice/cancel-initialization", { client_nonce: this.nonce });
      } finally {
        this.channel?.close();
        this.device.peer.close();
        this.onClosed();
      }
    });
    return this.closing;
  }
}
