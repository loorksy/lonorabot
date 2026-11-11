import { useSyncExternalStore } from "react";

/* The reference's per-device chat preferences (PREF_DEFAULT, Desktop-37 5748). «حالة الوكيل
   التفصيلية» (agentStatus) is off by default (Q35); the alert capsule always shows problems. */
export const CHAT_PREFS_DEFAULT = {
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
};
export type ChatPrefs = typeof CHAT_PREFS_DEFAULT;
const KEY = "lonora.chatPrefs";
const listeners = new Set<() => void>();
let cache: ChatPrefs | null = null;

function read(): ChatPrefs {
  if (cache) return cache;
  try {
    cache = { ...CHAT_PREFS_DEFAULT, ...JSON.parse(localStorage.getItem(KEY) ?? "{}") };
  } catch {
    cache = { ...CHAT_PREFS_DEFAULT };
  }
  return cache as ChatPrefs;
}

/** The preferences outside React (the vibration gate reads them on every call). */
export const chatPrefs = read;

let gated = false;
/**
 * «الاهتزاز» off silences every vibration of the app, as the reference does (Desktop-37
 * 5750): the one place every caller goes through, present and future. Installed once.
 */
export function gateHaptics() {
  const vibrate = navigator.vibrate?.bind(navigator) as
    | ((pattern: VibratePattern) => boolean)
    | undefined;
  if (gated || !vibrate) return;
  gated = true;
  try {
    navigator.vibrate = ((pattern: VibratePattern) =>
      read().haptics ? vibrate(pattern) : false) as Navigator["vibrate"];
  } catch {
    // An engine that forbids replacing it keeps its own vibration.
  }
}

export function setChatPref<K extends keyof ChatPrefs>(key: K, value: ChatPrefs[K]) {
  cache = { ...read(), [key]: value };
  try {
    localStorage.setItem(KEY, JSON.stringify(cache));
  } catch {
    // closed storage: the preference holds for this session
  }
  for (const listener of listeners) listener();
}

export function useChatPrefs(): ChatPrefs {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    read,
    read,
  );
}
