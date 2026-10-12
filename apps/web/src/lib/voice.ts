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
export const stopVoice = (id: string) => api.delete(`/voice/sessions/${id}`);
export const interruptVoice = (id: string) => api.post(`/voice/sessions/${id}/interrupt`, {});
export const voiceSnapshot = (id: string) => api.get<VoiceSnapshot>(`/voice/sessions/${id}`);

/** One click-owned transport; React effect replay never negotiates another paid call. */
export class VoiceJoin {
  session_id: string | null = null;
  readonly audio = document.createElement("audio");
  readonly nonce = crypto.randomUUID();
  readonly peer = new RTCPeerConnection();
  private microphone: MediaStream | null = null;
  private channel: RTCDataChannel | null = null;
  private abort = new AbortController();
  private disposed = false;
  private finalized = false;
  private resolveFinalized: (() => void) | null = null;
  private ended = new Promise<void>((resolve) => {
    this.resolveFinalized = resolve;
  });
  private seen = new Set<string>();
  constructor(
    readonly entity: string,
    private status: (connected: boolean) => void,
    private error: (error: unknown) => void,
    private transcript: (channel: "input" | "output", fragment: VoiceFragment) => void,
    private onClosed: () => void,
  ) {
    this.audio.autoplay = true;
    this.audio.controls = true;
    this.audio.setAttribute("aria-label", "GPT-Live audio");
    this.peer.ontrack = (event) => {
      this.audio.srcObject = new MediaStream([event.track]);
      void this.audio.play().catch(() => {
        /* Visible controls let the user resume blocked autoplay. */
      });
    };
    this.peer.onconnectionstatechange = () => {
      if (this.disposed) return;
      if (["failed", "disconnected"].includes(this.peer.connectionState)) {
        this.error(new ApiError("voice_connection_failed", 502));
        void this.close().catch((failure) => this.error(failure));
      }
    };
  }
  async connect(agentId: string, threadId: string) {
    try {
      if (!navigator.mediaDevices?.getUserMedia)
        throw new ApiError("voice_browser_unsupported", 409);
      this.microphone = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (this.disposed) {
        this.microphone.getTracks().forEach((track) => {
          track.stop();
        });
        return;
      }
      for (const track of this.microphone.getAudioTracks())
        this.peer.addTrack(track, this.microphone);
      this.channel = this.peer.createDataChannel("oai-events");
      this.channel.onmessage = ({ data }) => {
        try {
          const event = JSON.parse(data) as Record<string, unknown>;
          if (event.type === "session.started") this.status(true);
          if (event.type === "session.closed") {
            this.finalized = true;
            this.resolveFinalized?.();
            void this.close().catch((failure) => this.error(failure));
          }
          if (event.type === "error") this.error(new ApiError("voice_connection_failed", 502));
          if (
            ["session.input_transcript.delta", "session.output_transcript.delta"].includes(
              String(event.type),
            ) &&
            typeof event.delta === "string"
          ) {
            const id = String(event.event_id ?? "");
            if (this.seen.has(id)) return;
            this.seen.add(id);
            if (this.seen.size > 512) this.seen.delete(this.seen.values().next().value ?? "");
            this.transcript(event.type === "session.input_transcript.delta" ? "input" : "output", {
              event_id: id,
              start_ms: Number(event.start_ms),
              end_ms: Number(event.end_ms),
              delta: event.delta,
            });
          }
          // The resident server sideband alone executes client delegation; the browser never forwards tools.
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
          const timer = setTimeout(() => {
            this.peer.removeEventListener("icegatheringstatechange", check);
            reject(new ApiError("voice_connection_failed", 504));
          }, 10_000);
          const check = () => {
            if (this.disposed || this.peer.iceGatheringState === "complete") {
              clearTimeout(timer);
              this.peer.removeEventListener("icegatheringstatechange", check);
              resolve();
            }
          };
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
    } catch (error) {
      if (!this.disposed) {
        this.error(
          error instanceof DOMException && error.name === "NotAllowedError"
            ? new ApiError("voice_permission_denied", 403)
            : error,
        );
        await this.close();
      }
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
  async close() {
    if (this.disposed) return;
    this.disposed = true;
    this.abort.abort();
    this.microphone?.getTracks().forEach((track) => {
      track.stop();
    });
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
    this.channel?.close();
    this.peer.close();
    this.audio.pause();
    this.audio.srcObject = null;
    this.audio.remove();
    this.status(false);
    this.onClosed();
    if (this.session_id) await stopVoice(this.session_id);
    else await api.post("/voice/cancel-initialization", { client_nonce: this.nonce });
  }
}
