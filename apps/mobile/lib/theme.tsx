// The reference's two themes (packages/ui-tokens `reference`): dark is `:root`, light is `body.light`.
import { reference } from "@lonora/ui-tokens";
import {
  createContext,
  Fragment,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { applyLegacyTheme } from "../components/ui";
import { loadSetting, saveSetting } from "./storage";

export type ThemeMode = "dark" | "light";
const dark = reference.dark;
const light = { ...reference.dark, ...reference.light };
/** The reference's colour tokens for one theme (CSS var names without `--`). */
export type Palette = Record<keyof typeof reference.dark, string>;
export const palettes: Record<ThemeMode, Palette> = {
  dark: dark as unknown as Palette,
  light: light as unknown as Palette,
};
export const type = reference.type;
export const radius = reference.radius;

type Theme = { mode: ThemeMode; c: Palette; setMode: (mode: ThemeMode) => void };
const Context = createContext<Theme>({ mode: "dark", c: palettes.dark, setMode: () => undefined });

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>("dark");
  useEffect(() => {
    let live = true;
    void loadSetting("lonora.theme")
      .then((stored) => {
        if (live && (stored === "dark" || stored === "light")) setModeState(stored);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);
  const setMode = useCallback((next: ThemeMode) => {
    setModeState(next);
    void saveSetting("lonora.theme", next).catch(() => undefined);
  }, []);
  const value = useMemo(() => ({ mode, c: palettes[mode], setMode }), [mode, setMode]);
  // The legacy palette is a module-level object: update it before the tree below renders, and
  // remount that tree so every screen reads the new colours.
  applyLegacyTheme(mode);
  return (
    <Context.Provider value={value}>
      <Fragment key={mode}>{children}</Fragment>
    </Context.Provider>
  );
}

export const useTheme = () => useContext(Context);
