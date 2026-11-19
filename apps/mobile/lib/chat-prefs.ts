// Per-device chat preferences, as Web's (conversation/prefs.ts, «تجربة المحادثة»): applied to
// every conversation. Only the switches a phone's conversation honours are kept («Send with
// Enter» is a computer's). «حالة الوكيل التفصيلية» is off by default (Q35). They belong to the
// device, not the owner: a sign-out keeps them, as on Web.
import { useSyncExternalStore } from "react";
import { loadSetting, saveSetting } from "./storage";

export const CHAT_PREFS_DEFAULT = {
  steps: true,
  stepsOpen: false,
  agentStatus: false,
  assist: true,
};
export type ChatPrefs = typeof CHAT_PREFS_DEFAULT;
const KEY = "lonora.chatPrefs";
const listeners = new Set<() => void>();
let current: ChatPrefs = { ...CHAT_PREFS_DEFAULT };
let loaded = false;

function notify() {
  for (const listener of listeners) listener();
}
/** Reads the saved preferences once; until then the defaults hold. */
export async function loadChatPrefs() {
  if (loaded) return;
  loaded = true;
  try {
    const saved = JSON.parse((await loadSetting(KEY)) ?? "{}");
    const next = { ...CHAT_PREFS_DEFAULT };
    for (const key of Object.keys(next) as (keyof ChatPrefs)[])
      if (typeof saved?.[key] === "boolean") next[key] = saved[key];
    current = next;
    notify();
  } catch {
    /* Unreadable settings: the defaults hold. */
  }
}
export function chatPrefs(): ChatPrefs {
  return current;
}
export function setChatPref<K extends keyof ChatPrefs>(key: K, value: ChatPrefs[K]) {
  current = { ...current, [key]: value };
  notify();
  void saveSetting(KEY, JSON.stringify(current)).catch(() => undefined);
}
export function useChatPrefs(): ChatPrefs {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      void loadChatPrefs();
      return () => {
        listeners.delete(listener);
      };
    },
    chatPrefs,
    chatPrefs,
  );
}
