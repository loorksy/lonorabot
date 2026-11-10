import { useEffect, useState } from "react";

/* One theme for every component that reads it: a change made in settings reaches the shell
   (theme-color meta) at once. Kept per device in localStorage («lonora.theme»). */
const listeners = new Set<(theme: "dark" | "light") => void>();
function stored(): "dark" | "light" {
  try {
    return JSON.parse(localStorage.getItem("lonora.theme") ?? '"dark"') === "light"
      ? "light"
      : "dark";
  } catch {
    return "dark";
  }
}
export function useTheme() {
  const [theme, setLocal] = useState<"dark" | "light">(stored);
  useEffect(() => {
    listeners.add(setLocal);
    return () => {
      listeners.delete(setLocal);
    };
  }, []);
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  const setTheme = (next: "dark" | "light") => {
    try {
      localStorage.setItem("lonora.theme", JSON.stringify(next));
    } catch {
      /* this page only */
    }
    for (const listener of listeners) listener(next);
  };
  return { theme, setTheme };
}
