import { useEffect } from "react";
import { useLocalPreferences } from "./useLocalPreferences";
export function useTheme() {
  const [theme, setTheme] = useLocalPreferences<"dark" | "light">("theme", "dark");
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  return { theme, setTheme };
}
