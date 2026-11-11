import assert from "node:assert/strict";
import { test } from "node:test";
import {
  CHAT_PREFS_DEFAULT,
  chatPrefs,
  gateHaptics,
  setChatPref,
} from "../../apps/web/src/conversation/prefs";

/* The chat preferences of this device (reference PREF_DEFAULT, Desktop-37 5748) and the one
   gate every vibration goes through. The module reads the browser only when called. */
const calls: unknown[] = [];
const values = new Map<string, string>();
Object.defineProperty(globalThis, "navigator", {
  configurable: true,
  value: {
    vibrate(pattern: unknown) {
      calls.push(pattern);
      return true;
    },
  },
});
Object.assign(globalThis, {
  localStorage: {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
  },
});

test("the defaults are the reference's, and a change is kept on this device", () => {
  assert.deepEqual(CHAT_PREFS_DEFAULT, {
    stream: true,
    steps: true,
    stepsOpen: false,
    markdown: true,
    enterSend: true,
    assist: true,
    haptics: true,
    genui: true,
    genuiWhy: true,
    agentStatus: false,
  });
  setChatPref("stream", false);
  assert.equal(chatPrefs().stream, false);
  assert.equal(JSON.parse(values.get("lonora.chatPrefs") ?? "{}").stream, false);
  setChatPref("stream", true);
});

test("with «الاهتزاز» off nothing vibrates, whoever asks", () => {
  gateHaptics();
  // Installed once: a second call does not wrap the wrapper.
  gateHaptics();
  assert.equal(navigator.vibrate(6), true);
  assert.deepEqual(calls, [6]);
  setChatPref("haptics", false);
  assert.equal(navigator.vibrate([10, 20]), false);
  assert.deepEqual(calls, [6]);
  setChatPref("haptics", true);
  assert.equal(navigator.vibrate(8), true);
  assert.deepEqual(calls, [6, 8]);
});
