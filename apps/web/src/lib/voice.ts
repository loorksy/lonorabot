import { ApiError, api, request } from "./api";
export type VoiceFragment = { event_id: string; start_ms: number; end_ms: number; delta: string };
export type VoiceSnapshot = {
  session_id: string;
  status: string;
  error?: string;
  input: VoiceFragment[];
  output: VoiceFragment[];
  finalized: boolean;
  usage?: { seconds: number };
};
export type VoiceActivity = { phase: "listening" | "speaking"; level: number };
export const stopVoice = (id: string) => api.delete(`/voice/sessions/${id}`);
export const interruptVoice = (id: string) => api.post(`/voice/sessions/${id}/interrupt`, {});
export const voiceSnapshot = (id: string) => api.get<VoiceSnapshot>(`/voice/sessions/${id}`);

/** A click-owned transport. Hiding a view never owns negotiation or media teardown. */
export class VoiceJoin {
  session_id: string | null = null;
  readonly audio: HTMLAudioElement;
  readonly nonce = crypto.randomUUID();
  readonly peer: RTCPeerConnection;
  muted = false;
  private microphone: MediaStream | null = null;
  private channel: RTCDataChannel | null = null;
  private abort = new AbortController();
  private disposed = false;
  private finalized = false;
  private closing: Promise<void> | null = null;
  private resolveFinalized: (() => void) | null = null;
  private ended = new Promise<void>((resolve) => {
    this.resolveFinalized = resolve;
  });
  private seen = new Set<string>();
  private meterContext: AudioContext | null = null;
  private inputMeter: AnalyserNode | null = null;
  private outputMeter: AnalyserNode | null = null;
  private meterFrame = 0;
  private lastMeter = 0;
  private outputAt = 0;
  private lastPhase: VoiceActivity["phase"] = "listening";

  constructor(
    readonly entity: string,
    private status: (connected: boolean) => void,
    private error: (error: unknown) => void,
    private transcript: (channel: "input" | "output", fragment: VoiceFragment) => void,
    private onClosed: () => void,
    private activity: (activity: VoiceActivity) => void = () => undefined,
    private playback: (blocked: boolean) => void = () => undefined,
  ) {
    if (typeof RTCPeerConnection === "undefined")
      throw new ApiError("voice_browser_unsupported", 409);
    this.peer = new RTCPeerConnection();
    this.audio = document.createElement("audio");
    this.audio.autoplay = true;
    this.audio.controls = false;
    this.peer.ontrack = (event) => {
      if (this.disposed) return;
      const stream = event.streams?.[0] ?? new MediaStream([event.track]);
      this.audio.srcObject = stream;
      this.outputMeter = this.makeMeter(stream);
      void this.resumePlayback().catch(() => undefined);
    };
    this.peer.onconnectionstatechange = () => {
      if (!this.disposed && ["failed", "disconnected"].includes(this.peer.connectionState)) {
        this.error(new ApiError("voice_connection_failed", 502));
        void this.close().catch((failure) => this.error(failure));
      }
    };
  }
  private makeMeter(stream: MediaStream): AnalyserNode | null {
    if (typeof AudioContext === "undefined") return null;
    try {
      this.meterContext ??= new AudioContext();
      void this.meterContext.resume().catch(() => undefined);
      const meter = this.meterContext.createAnalyser();
      meter.fftSize = 256;
      const source = this.meterContext.createMediaStreamSource(stream);
      const silence = this.meterContext.createGain();
      silence.gain.value = 0;
      source.connect(meter);
      meter.connect(silence);
      silence.connect(this.meterContext.destination);
      return meter;
    } catch {
      return null;
    }
  }
  private monitor() {
    const input = new Uint8Array(256),
      output = new Uint8Array(256);
    const level = (meter: AnalyserNode | null, samples: Uint8Array<ArrayBuffer>) => {
      if (!meter) return 0;
      meter.getByteTimeDomainData(samples);
      const power =
        samples.reduce((sum, sample) => sum + ((sample - 128) / 128) ** 2, 0) / samples.length;
      return Math.min(1, Math.sqrt(power) * 7);
    };
    const tick = (now: number) => {
      if (this.disposed) return;
      if (now - this.lastMeter >= 80) {
        this.lastMeter = now;
        const inputLevel = this.muted ? 0 : level(this.inputMeter, input);
        const outputLevel = level(this.outputMeter, output);
        if (outputLevel > 0.03) this.outputAt = now;
        this.lastPhase = now - this.outputAt < 650 && this.outputAt > 0 ? "speaking" : "listening";
        this.activity({
          phase: this.lastPhase,
          level: this.lastPhase === "speaking" ? outputLevel : inputLevel,
        });
      }
      this.meterFrame = requestAnimationFrame(tick);
    };
    this.meterFrame = requestAnimationFrame(tick);
  }
  async connect(agentId: string, threadId: string) {
    try {
      if (!navigator.mediaDevices?.getUserMedia)
        throw new ApiError("voice_browser_unsupported", 409);
      this.microphone = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      if (this.disposed) {
        this.microphone.getTracks().forEach((track) => {
          track.stop();
        });
        return;
      }
      this.setMuted(this.muted);
      this.inputMeter = this.makeMeter(this.microphone);
      this.monitor();
      for (const track of this.microphone.getAudioTracks())
        this.peer.addTrack(track, this.microphone);
      this.channel = this.peer.createDataChannel("oai-events");
      this.channel.onmessage = ({ data }) => {
        try {
          const event = JSON.parse(data) as Record<string, unknown>;
          if (event.type === "session.closed") {
            this.finalized = true;
            this.resolveFinalized?.();
            void this.close().catch((failure) => this.error(failure));
            return;
          }
          if (this.disposed) return;
          if (event.type === "session.started") this.status(true);
          if (event.type === "error") this.error(new ApiError("voice_connection_failed", 502));
          if (event.type === "session.output_audio.delta") this.outputAt = performance.now();
          if (
            ["session.input_transcript.delta", "session.output_transcript.delta"].includes(
              String(event.type),
            ) &&
            typeof event.delta === "string"
          ) {
            const id = String(event.event_id ?? "");
            if (!id || this.seen.has(id)) return;
            this.seen.add(id);
            if (this.seen.size > 2048) this.seen.delete(this.seen.values().next().value ?? "");
            const channel = event.type === "session.input_transcript.delta" ? "input" : "output";
            if (channel === "output") this.outputAt = performance.now();
            this.transcript(channel, {
              event_id: id,
              start_ms: Number(event.start_ms),
              end_ms: Number(event.end_ms),
              delta: event.delta,
            });
          }
          // Delegated tools and all financial permissions remain on the resident server sideband.
        } catch {
          this.error(new ApiError("voice_response_invalid", 502));
        }
      };
      this.channel.onclose = () => {
        if (!this.disposed) void this.close().catch((failure) => this.error(failure));
      };
      await this.peer.setLocalDescription(await this.peer.createOffer());
      if (this.peer.iceGatheringState !== "complete")
        await new Promise<void>((resolve, reject) => {
          const check = () => {
            if (this.disposed || this.peer.iceGatheringState === "complete") {
              clearTimeout(timer);
              this.peer.removeEventListener("icegatheringstatechange", check);
              resolve();
            }
          };
          const timer = setTimeout(() => {
            this.peer.removeEventListener("icegatheringstatechange", check);
            reject(new ApiError("voice_connection_failed", 504));
          }, 10_000);
          this.peer.addEventListener("icegatheringstatechange", check);
          check();
        });
      if (this.disposed) return;
      const sdp = this.peer.localDescription?.sdp;
      if (!sdp) throw new ApiError("voice_response_invalid", 502);
      const session = await request<{ session_id: string; sdp: string }>("/voice/sessions", {
        method: "POST",
        body: JSON.stringify({
          agent_id: agentId,
          thread_id: threadId,
          mode: "gpt_live",
          client_nonce: this.nonce,
          sdp,
        }),
        signal: this.abort.signal,
      });
      this.session_id = session.session_id;
      if (this.disposed) {
        await stopVoice(session.session_id);
        return;
      }
      await this.peer.setRemoteDescription({ type: "answer", sdp: session.sdp });
    } catch (failure) {
      if (!this.disposed) {
        this.error(
          failure instanceof DOMException && failure.name === "NotAllowedError"
            ? new ApiError("voice_permission_denied", 403)
            : failure,
        );
        await this.close();
      }
    }
  }
  setMuted(muted: boolean) {
    this.muted = muted;
    this.microphone?.getAudioTracks().forEach((track) => {
      track.enabled = !muted;
    });
  }
  async resumePlayback() {
    try {
      await this.audio.play();
      this.playback(false);
    } catch (error) {
      this.playback(true);
      throw error;
    }
  }
  async interrupt() {
    if (this.channel?.readyState === "open")
      this.channel.send(
        JSON.stringify({
          type: "session.instructions.append",
          event_id: crypto.randomUUID(),
          delegation_id: null,
          content: "Stop speaking and listen. The owner explicitly interrupted the current work.",
        }),
      );
    if (this.session_id) await interruptVoice(this.session_id);
  }
  /** Concurrent End/logout/unmount share one finalization and one authenticated server close. */
  close(): Promise<void> {
    if (this.closing) return this.closing;
    this.disposed = true;
    this.abort.abort();
    cancelAnimationFrame(this.meterFrame);
    this.microphone?.getTracks().forEach((track) => {
      track.stop();
    });
    this.audio.pause();
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
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 10_000);
        try {
          if (this.session_id)
            await request(`/voice/sessions/${this.session_id}`, {
              method: "DELETE",
              signal: controller.signal,
            });
          else
            await request("/voice/cancel-initialization", {
              method: "POST",
              body: JSON.stringify({ client_nonce: this.nonce }),
              signal: controller.signal,
            });
        } finally {
          clearTimeout(timeout);
        }
      } finally {
        this.channel?.close();
        this.peer.close();
        this.audio.srcObject = null;
        this.audio.remove();
        void this.meterContext?.close().catch(() => undefined);
        this.onClosed();
      }
    });
    return this.closing;
  }
}
