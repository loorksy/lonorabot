import { useEffect, useState } from "react";

/* One theme for every component that reads it: a change made in settings reaches the shell
   (theme-color meta) at once. Kept per device in localStorage («lonora.theme»); with no saved
   choice it follows the device, as public/theme-init.js does for the first frame. */
const listeners = new Set<(theme: "dark" | "light") => void>();
function stored(): "dark" | "light" {
  try {
    const saved = localStorage.getItem("lonora.theme");
    if (saved === null)
      return matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
    return JSON.parse(saved) === "light" ? "light" : "dark";
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
