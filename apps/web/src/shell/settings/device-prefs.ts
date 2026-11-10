import { useSyncExternalStore } from "react";

/* Device preferences of the settings pages: per browser, like the reference's S.notif, S.a11y and
   S.lock. One small store per key in localStorage (`lonora.<key>`), shared by every component
   that reads it (the heads-up banner, the lock layer, the root page's values). */
const listeners = new Map<string, Set<() => void>>();
const cache = new Map<string, unknown>();

function read<T>(key: string, initial: T): T {
  if (cache.has(key)) return cache.get(key) as T;
  let value = initial;
  try {
    const raw = localStorage.getItem(`lonora.${key}`);
    if (raw) value = { ...initial, ...(JSON.parse(raw) as object) } as T;
  } catch {
    /* private mode or a broken value: the defaults */
  }
  cache.set(key, value);
  return value;
}

export function writeDevicePref<T>(key: string, value: T) {
  cache.set(key, value);
  try {
    localStorage.setItem(`lonora.${key}`, JSON.stringify(value));
  } catch {
    /* the value still applies for this page */
  }
  for (const listener of listeners.get(key) ?? []) listener();
}

export function useDevicePref<T extends object>(key: string, initial: T) {
  const value = useSyncExternalStore(
    (listener) => {
      const set = listeners.get(key) ?? new Set();
      set.add(listener);
      listeners.set(key, set);
      return () => set.delete(listener);
    },
    () => read(key, initial),
  );
  return [value, (patch: Partial<T>) => writeDevicePref(key, { ...value, ...patch })] as const;
}
export const readDevicePref = read;

/** «الإشعارات»: the in-app banner, its text preview and its tone (device preferences). */
export type NotifyPrefs = { inApp: boolean; preview: boolean; sound: boolean };
export const NOTIFY_DEFAULTS: NotifyPrefs = { inApp: true, preview: true, sound: true };

/** «سهولة الاستخدام»: text size 0–4, higher contrast, reduced motion. */
export type A11yPrefs = { size: number; contrast: boolean; motion: boolean };
export const A11Y_DEFAULTS: A11yPrefs = { size: 1, contrast: false, motion: false };
const FS: Record<string, number> = { xs: 12, sm: 14, md: 16, lg: 20, xl: 28 };
const SCALE = [0.9, 1, 1.1, 1.2, 1.32];
export function applyA11y(prefs: A11yPrefs) {
  const factor = SCALE[prefs.size] ?? 1;
  const root = document.documentElement;
  for (const [name, size] of Object.entries(FS))
    if (factor === 1) root.style.removeProperty(`--fs-${name}`);
    else root.style.setProperty(`--fs-${name}`, `${Math.round(size * factor * 10) / 10}px`);
  document.body.classList.toggle("hc", prefs.contrast);
  document.body.classList.toggle("rm", prefs.motion);
}
