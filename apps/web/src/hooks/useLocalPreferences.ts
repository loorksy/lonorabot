import { useState } from "react";
export function useLocalPreferences<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(`lonora.${key}`);
      return raw ? (JSON.parse(raw) as T) : initial;
    } catch {
      return initial;
    }
  });
  return [
    value,
    (next: T) => {
      localStorage.setItem(`lonora.${key}`, JSON.stringify(next));
      setValue(next);
    },
  ] as const;
}
