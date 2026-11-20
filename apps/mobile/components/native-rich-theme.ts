import { appearance, type Theme } from "@lonora/ui-tokens";
import { useEffect, useState } from "react";
import { Platform } from "react-native";
import { useTheme } from "../lib/theme";

export type NativeVisualPalette = (typeof appearance)[Theme];

/** Native responses use the same semantic palette as the website, never model colors. */
export function useNativeVisualTheme(): NativeVisualPalette {
  const { mode } = useTheme();
  const [browserTheme, setBrowserTheme] = useState<Theme | null>(null);
  useEffect(() => {
    if (Platform.OS !== "web" || typeof document === "undefined") return;
    const read = () => {
      const value = document.documentElement.getAttribute("data-theme");
      setBrowserTheme(value === "light" || value === "dark" ? value : null);
    };
    read();
    const observer = new MutationObserver(read);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => observer.disconnect();
  }, []);
  // Rich answers follow the app's own theme (light or dark), as its conversation surface
  // does; a browser page that sets data-theme keeps its own.
  return appearance[Platform.OS === "web" ? (browserTheme ?? mode) : mode];
}

export function visualTone(palette: NativeVisualPalette, tone?: string): string {
  if (tone === "success") return palette.success;
  if (tone === "warning") return palette.warning;
  if (tone === "danger") return palette.destructive;
  if (tone === "info") return palette.link;
  return palette.foreground;
}
