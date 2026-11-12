import assert from "node:assert/strict";
import { test } from "node:test";
import { CHAT_PREFS_DEFAULT, setChatPref } from "../../apps/web/src/conversation/prefs";

/* The chat preferences of this device (reference PREF_DEFAULT, Desktop-37 5748). The module
   reads the browser only when called. */
const values = new Map<string, string>();
Object.assign(globalThis, {
  localStorage: {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
  },
});

test("the defaults are the reference's, and a change is kept on this device", () => {
  assert.deepEqual(CHAT_PREFS_DEFAULT, {
    steps: true,
    stepsOpen: false,
    markdown: true,
    enterSend: true,
    assist: true,
    haptics: true,
    agentStatus: false,
  });
  setChatPref("stepsOpen", true);
  assert.equal(JSON.parse(values.get("lonora.chatPrefs") ?? "{}").stepsOpen, true);
  setChatPref("stepsOpen", false);
});
