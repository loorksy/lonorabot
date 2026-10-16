import assert from "node:assert/strict";
import { test } from "node:test";
import { ApiError } from "../../apps/mobile/lib/api-error";
import { MobileVoiceJoin, type VoiceApi } from "../../apps/mobile/lib/voice-transport";
import type {
  VoiceActivity,
  VoiceChannel,
  VoiceDevice,
  VoiceMedia,
  VoicePeer,
} from "../../apps/mobile/lib/voice-types";

class Channel implements VoiceChannel {
  readyState = "open";
  listeners = new Map<string, (event: { data?: string }) => void>();
  sent: string[] = [];
  closeCount = 0;
  send(value: string) {
    this.sent.push(value);
    if (JSON.parse(value).type === "session.close") this.emit({ type: "session.closed" });
  }
  emit(value: unknown) {
    this.listeners.get("message")?.({ data: JSON.stringify(value) });
  }
  close() {
    this.closeCount++;
    this.readyState = "closed";
  }
  addEventListener(type: string, listener: (event: { data?: string }) => void) {
    this.listeners.set(type, listener);
  }
}
class Peer implements VoicePeer {
  connectionState = "new";
  iceGatheringState = "complete";
  localDescription: { sdp?: string } | null = null;
  channel = new Channel();
  listeners = new Map<string, () => void>();
  tracks = 0;
  closeCount = 0;
  answer: { sdp: string; type: string } | null = null;
  stats: Map<string, Record<string, unknown>> = new Map();
  addTrack() {
    this.tracks++;
  }
  createDataChannel(label: string) {
    assert.equal(label, "oai-events");
    return this.channel;
  }
  async createOffer() {
    return { type: "offer", sdp: "scripted-offer" };
  }
  async setLocalDescription(value: { sdp: string }) {
    this.localDescription = value;
  }
  async setRemoteDescription(value: { sdp: string; type: string }) {
    this.answer = value;
    this.channel.emit({ type: "session.started" });
  }
  addEventListener(type: string, listener: () => void) {
    this.listeners.set(type, listener);
  }
  removeEventListener(type: string) {
    this.listeners.delete(type);
  }
  async getStats() {
    return this.stats;
  }
  close() {
    this.closeCount++;
  }
}
function fixture() {
  const peer = new Peer();
  let stopped = 0,
    startedAudio = 0,
    stoppedAudio = 0,
    closed = 0;
  const track = {
    enabled: true,
    stop() {
      stopped++;
    },
  };
  const microphone: VoiceMedia = { getTracks: () => [track], getAudioTracks: () => [track] };
  const device: VoiceDevice = {
    peer,
    microphone: async () => microphone,
    startAudio() {
      startedAudio++;
    },
    muteAudio() {},
    stopAudio() {
      stoppedAudio++;
    },
  };
  const requests: { path: string; body?: unknown; method: string }[] = [];
  const api: VoiceApi = {
    async post<T>(path: string, body: unknown) {
      requests.push({ path, body, method: "POST" });
      return (
        path === "/voice/sessions" ? { session_id: "origin-session", sdp: "scripted-answer" } : {}
      ) as T;
    },
    async delete<T>(path: string) {
      requests.push({ path, method: "DELETE" });
      return {} as T;
    },
  };
  const activity: VoiceActivity[] = [];
  const errors: unknown[] = [];
  const connected: boolean[] = [];
  const join = new MobileVoiceJoin(
    (value) => connected.push(value),
    (error) => errors.push(error),
    (value) => activity.push(value),
    () => {
      closed++;
    },
    device,
    api,
  );
  return {
    join,
    peer,
    device,
    api,
    track,
    microphone,
    requests,
    errors,
    activity,
    connected,
    counters: () => ({ stopped, startedAudio, stoppedAudio, closed }),
  };
}

test("native/browser transport uses the exact current bot/thread, same resident server runtime and authenticated SDP exchange", async () => {
  const f = fixture();
  await f.join.connect("current-bot", "current-thread");
  assert.equal(f.peer.tracks, 1);
  assert.deepEqual(f.requests[0], {
    path: "/voice/sessions",
    method: "POST",
    body: {
      agent_id: "current-bot",
      thread_id: "current-thread",
      mode: "gpt_live",
      client_nonce: f.join.nonce,
      sdp: "scripted-offer",
    },
  });
  assert.deepEqual(f.peer.answer, { type: "answer", sdp: "scripted-answer" });
  assert.equal(f.connected[0], true);
  assert.equal(f.counters().startedAudio, 1);
  f.join.setMuted(true);
  assert.equal(f.track.enabled, false);
  f.join.setMuted(false);
  assert.equal(f.track.enabled, true);
  await Promise.all([f.join.close(), f.join.close(), f.join.close()]);
  assert.deepEqual(
    f.requests.filter((row) => row.method === "DELETE"),
    [{ path: "/voice/sessions/origin-session", method: "DELETE" }],
  );
  assert.deepEqual(f.counters(), { stopped: 1, startedAudio: 1, stoppedAudio: 1, closed: 1 });
  assert.equal(f.peer.closeCount, 1);
  assert.equal(f.peer.channel.closeCount, 1);
  assert.equal(f.errors.length, 0);
});

test("ending during microphone permission wait stops late media and cancels only the original initialization nonce", async () => {
  const f = fixture();
  let release: ((value: VoiceMedia) => void) | undefined;
  f.device.microphone = () =>
    new Promise((resolve) => {
      release = resolve;
    });
  const negotiating = f.join.connect("current-bot", "current-thread");
  await f.join.close();
  release?.(f.microphone);
  await negotiating;
  assert.equal(f.peer.tracks, 0);
  assert.equal(f.counters().stopped, 1);
  assert.equal(f.counters().startedAudio, 0);
  assert.deepEqual(f.requests, [
    { path: "/voice/cancel-initialization", method: "POST", body: { client_nonce: f.join.nonce } },
  ]);
});

test("permission denial cannot create a server voice session and releases the peer/audio route", async () => {
  const f = fixture();
  f.device.microphone = async () => {
    throw new ApiError("voice_permission_denied", 403);
  };
  await f.join.connect("current-bot", "current-thread");
  assert.equal((f.errors[0] as ApiError).code, "voice_permission_denied");
  assert.equal(
    f.requests.some((row) => row.path === "/voice/sessions"),
    false,
  );
  assert.equal(f.peer.closeCount, 1);
  assert.equal(f.counters().closed, 1);
});

test("actual audio stats drive avatar level; output events mark speaking without inventing amplitude", async () => {
  const f = fixture();
  f.peer.stats.set("input", { type: "media-source", kind: "audio", audioLevel: 0.42 });
  await f.join.connect("current-bot", "current-thread");
  await new Promise((resolve) => setTimeout(resolve, 200));
  assert.ok(f.activity.some((value) => value.phase === "listening" && value.level === 0.42));
  f.join.setMuted(true);
  await new Promise((resolve) => setTimeout(resolve, 170));
  assert.equal(f.activity.at(-1)?.level, 0);
  f.peer.channel.emit({ type: "session.output_transcript.delta", delta: "fixture output" });
  await new Promise((resolve) => setTimeout(resolve, 170));
  assert.equal(f.activity.at(-1)?.phase, "speaking");
  assert.equal(f.activity.at(-1)?.level, 0);
  await f.join.close();
});

test("connection failure releases media once and retains stable error code", async () => {
  const f = fixture();
  await f.join.connect("current-bot", "current-thread");
  f.peer.connectionState = "failed";
  f.peer.listeners.get("connectionstatechange")?.();
  await f.join.close();
  assert.equal((f.errors[0] as ApiError).code, "voice_connection_failed");
  assert.equal(f.counters().closed, 1);
  assert.equal(f.peer.closeCount, 1);
  assert.equal(f.requests.filter((row) => row.method === "DELETE").length, 1);
});

test("ending during offer creation never configures a closed native peer", async () => {
  const f = fixture();
  let release!: (value: { type: string; sdp: string }) => void;
  let offered!: () => void;
  const offerStarted = new Promise<void>((resolve) => {
    offered = resolve;
  });
  f.peer.createOffer = () => {
    offered();
    return new Promise((resolve) => {
      release = resolve;
    });
  };
  const negotiating = f.join.connect("current-bot", "current-thread");
  await offerStarted;
  await f.join.close();
  release({ type: "offer", sdp: "late-offer" });
  await negotiating;
  assert.equal(f.peer.localDescription, null);
  assert.equal(
    f.requests.some((row) => row.path === "/voice/sessions"),
    false,
  );
  assert.equal(f.peer.closeCount, 1);
});

test("ending while gathering ICE promptly releases startup listener and prevents session creation", async () => {
  const f = fixture();
  f.peer.iceGatheringState = "gathering";
  let gathering!: () => void;
  const gatheringStarted = new Promise<void>((resolve) => {
    gathering = resolve;
  });
  const add = f.peer.addEventListener.bind(f.peer);
  f.peer.addEventListener = (type, listener) => {
    add(type, listener);
    if (type === "icegatheringstatechange") gathering();
  };
  const negotiating = f.join.connect("current-bot", "current-thread");
  await gatheringStarted;
  await f.join.close();
  await negotiating;
  assert.equal(f.peer.listeners.has("icegatheringstatechange"), false);
  assert.equal(
    f.requests.some((row) => row.path === "/voice/sessions"),
    false,
  );
});

test("native teardown failure still finalizes server session, closes peer and releases provider once", async () => {
  const f = fixture();
  await f.join.connect("current-bot", "current-thread");
  const failure = new Error("native audio session already interrupted");
  f.track.stop = () => {
    throw failure;
  };
  f.device.stopAudio = () => {
    throw failure;
  };
  f.peer.channel.close = () => {
    throw failure;
  };
  const closing = f.join.close();
  assert.equal(f.join.close(), closing);
  await assert.rejects(closing, failure);
  assert.equal(f.peer.closeCount, 1);
  assert.equal(f.counters().closed, 1);
  assert.equal(f.requests.filter((row) => row.method === "DELETE").length, 1);
});

test("closed data channel send failure still deletes original server session and closes peer", async () => {
  const f = fixture();
  await f.join.connect("current-bot", "current-thread");
  const failure = new Error("data channel closed before send");
  f.peer.channel.send = () => {
    throw failure;
  };
  await assert.rejects(f.join.close(), failure);
  assert.equal(f.peer.closeCount, 1);
  assert.equal(f.counters().closed, 1);
  assert.equal(f.requests.filter((row) => row.method === "DELETE").length, 1);
});
