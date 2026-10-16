import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { runInNewContext } from "node:vm";
import ts from "typescript";
import { ApiError } from "../../apps/mobile/lib/api-error";

function fixture({
  available = true,
  granted = true,
  receiversFail = false,
  unmuteFails = false,
} = {}) {
  const calls: string[] = [];
  const source = readFileSync(
    new URL("../../apps/mobile/lib/voice-device.native.ts", import.meta.url),
    "utf8",
  );
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.CommonJS,
      esModuleInterop: true,
    },
  });
  class Peer {
    constructor() {
      calls.push("peer");
    }
    getReceivers() {
      if (receiversFail) throw new Error("receiver already disposed");
      return [];
    }
  }
  const exports: {
    createVoiceDevice?: () => Promise<{
      microphone(): Promise<unknown>;
      startAudio(): void;
      stopAudio(): void;
    }>;
  } = {};
  const require = (name: string) => {
    if (name === "react-native")
      return {
        NativeModules: available ? { WebRTCModule: {}, InCallManager: {} } : {},
        Platform: { OS: "android" },
        PermissionsAndroid: {
          PERMISSIONS: { RECORD_AUDIO: "microphone" },
          RESULTS: { GRANTED: "granted" },
          request: async () => {
            calls.push("permission");
            return granted ? "granted" : "denied";
          },
        },
      };
    if (name === "./api-error") return { ApiError };
    if (name === "react-native-webrtc") {
      calls.push("load-webrtc");
      return {
        RTCPeerConnection: Peer,
        mediaDevices: {
          getUserMedia: async () => {
            calls.push("microphone");
            return {};
          },
        },
      };
    }
    if (name === "react-native-incall-manager")
      return {
        start() {
          calls.push("audio-start");
        },
        stop() {
          calls.push("audio-stop");
        },
        setForceSpeakerphoneOn() {},
        setMicrophoneMute() {
          if (unmuteFails) throw new Error("audio route interrupted");
        },
      };
    throw new Error(`Unexpected import ${name}`);
  };
  runInNewContext(outputText, { exports, require });
  return { create: () => exports.createVoiceDevice?.(), calls };
}

test("unsupported installed binary rejects before loading or initializing native voice libraries", async () => {
  const f = fixture({ available: false });
  await assert.rejects(
    f.create,
    (reason: unknown) => reason instanceof ApiError && reason.code === "voice_native_unavailable",
  );
  assert.deepEqual(f.calls, []);
});

for (const failure of [{ receiversFail: true }, { unmuteFails: true }]) {
  test(`native audio route stops even when teardown fails: ${JSON.stringify(failure)}`, async () => {
    const f = fixture(failure);
    const device = await f.create();
    device?.startAudio();
    assert.throws(() => device?.stopAudio());
    assert.equal(f.calls.filter((call) => call === "audio-stop").length, 1);
  });
}
test("denied microphone permission cannot create native peer, audio route or microphone", async () => {
  const f = fixture({ granted: false });
  await assert.rejects(
    f.create,
    (reason: unknown) => reason instanceof ApiError && reason.code === "voice_permission_denied",
  );
  assert.deepEqual(f.calls, ["permission"]);
});
test("supported native device requests permission before native peer; unused audio does not teardown route", async () => {
  const f = fixture();
  const device = await f.create();
  assert.deepEqual(f.calls, ["permission", "load-webrtc", "peer"]);
  device?.stopAudio();
  assert.equal(f.calls.includes("audio-stop"), false);
  await device?.microphone();
  device?.startAudio();
  device?.stopAudio();
  device?.stopAudio();
  assert.deepEqual(f.calls, [
    "permission",
    "load-webrtc",
    "peer",
    "microphone",
    "audio-start",
    "audio-stop",
  ]);
});
