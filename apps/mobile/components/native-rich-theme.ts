import { appearance, type Theme } from "@lonora/ui-tokens";
import { useEffect, useState } from "react";
import { Platform, useColorScheme } from "react-native";

export type NativeVisualPalette = (typeof appearance)[Theme];

/** Native responses use the same semantic palette as the website, never model colors. */
export function useNativeVisualTheme(): NativeVisualPalette {
  const system = useColorScheme();
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
  return appearance[browserTheme ?? (system === "light" ? "light" : "dark")];
}

export function visualTone(palette: NativeVisualPalette, tone?: string): string {
  if (tone === "success") return palette.success;
  if (tone === "warning") return palette.warning;
  if (tone === "danger") return palette.destructive;
  if (tone === "info") return palette.link;
  return palette.foreground;
}
