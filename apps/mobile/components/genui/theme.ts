/** The card palette of `apps/web/src/components/genui/genui.css` (Desktop-37 `.ux`), built from
 * the reference tokens in dark and light. React Native has no `color-mix`, so the mixes the
 * web card uses are computed here from the same token values. Agents never set a colour. */
import { appearance, reference } from "@lonora/ui-tokens";
import { useNativeVisualTheme } from "../native-rich-theme";

type Tokens = Record<keyof typeof reference.dark, string>;

function rgb(hex: string): [number, number, number] {
  const value = hex.replace("#", "");
  const full =
    value.length === 3
      ? value
          .split("")
          .map((c) => c + c)
          .join("")
      : value;
  return [0, 2, 4].map((at) => Number.parseInt(full.slice(at, at + 2), 16)) as [
    number,
    number,
    number,
  ];
}

/** `color-mix(in srgb, a p%, b)`. */
function mix(a: string, p: number, b: string): string {
  const [x, y] = [rgb(a), rgb(b)];
  const channel = (i: number) => Math.round((x[i] ?? 0) * p + (y[i] ?? 0) * (1 - p));
  return `rgb(${channel(0)}, ${channel(1)}, ${channel(2)})`;
}

/** `color-mix(in srgb, a p%, transparent)`. */
function alpha(a: string, p: number): string {
  const [r, g, b] = rgb(a);
  return `rgba(${r}, ${g}, ${b}, ${p})`;
}

export type CardPalette = ReturnType<typeof palette>;

function palette(mode: "dark" | "light") {
  const t = (
    mode === "dark" ? reference.dark : { ...reference.dark, ...reference.light }
  ) as Tokens;
  const light = mode === "light";
  return {
    mode,
    text: t.text,
    muted: t.muted,
    faint: t.faint,
    line: t.line,
    lineStrong: t["line-strong"],
    accent: t.accent,
    accentInk: t["accent-ink"],
    onAccent: t["on-accent"],
    primary: t.primary,
    onPrimary: t["on-primary"],
    red: t.red,
    amber: t.amber,
    input: light ? "#ffffff" : t.bg,
    card: light ? mix(t.text, 0.02, "#ffffff") : mix(t.text, 0.035, t["bubble-in"]),
    raise: alpha(t.text, light ? 0.035 : 0.05),
    track: light ? "#e6e2d8" : alpha(t.text, 0.09),
    thumb: light ? "#ffffff" : "#3a3d46",
    iconTile: alpha(t.accent, 0.14),
    toneBg: {
      warn: alpha(t.amber, 0.13),
      good: alpha(t.accent, 0.12),
      bad: alpha(t.red, 0.12),
    } as Record<string, string>,
    badgeGood: alpha(t.accent, 0.16),
    focus: alpha(t.accent, 0.22),
  };
}

const PALETTES = { dark: palette("dark"), light: palette("light") };

/** The same theme choice as the other native rich responses (web follows the page). */
export function useCardPalette(): CardPalette {
  const shell = useNativeVisualTheme();
  return shell === appearance.light ? PALETTES.light : PALETTES.dark;
}
