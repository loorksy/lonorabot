import { useSyncExternalStore } from "react";

/* The reference's per-device chat preferences (PREF_DEFAULT, Desktop-37 5748). «حالة الوكيل
   التفصيلية» (agentStatus) is off by default (Q35); the alert capsule always shows problems. */
export const CHAT_PREFS_DEFAULT = {
  steps: true,
  stepsOpen: false,
  markdown: true,
  enterSend: true,
  assist: true,
  haptics: true,
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
