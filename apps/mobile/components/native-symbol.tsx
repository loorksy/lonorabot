// Portable fallback for the template's SF Symbols/native toolbar; see NOTICE.
import Svg, { Circle, Path, Rect } from "react-native-svg";
import { colors } from "./ui";

export type SymbolName =
  | "search"
  | "activity"
  | "layers"
  | "plus"
  | "back"
  | "chevron"
  | "more"
  | "chart"
  | "send"
  | "close"
  | "file"
  | "clock"
  | "settings"
  | "group"
  | "agent"
  | "download"
  | "check"
  | "stop"
  | "refresh"
  | "globe";

const paths: Partial<Record<SymbolName, string>> = {
  search: "m21 21-5.2-5.2",
  activity: "M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4",
  layers: "m12 3 9 5-9 5-9-5 9-5ZM3 12l9 5 9-5M3 16l9 5 9-5",
  plus: "M12 5v14M5 12h14",
  back: "m15 5-7 7 7 7",
  chevron: "m9 5 7 7-7 7",
  chart: "M3 3v18h18M7 15l4-5 4 3 5-8",
  send: "M12 19V5m-6 6 6-6 6 6",
  close: "m6 6 12 12M6 18 18 6",
  file: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6Zm0 0v6h6M8 13h8M8 17h6",
  clock: "M12 6v6l4 2",
  settings:
    "m9 3 1-1h4l1 3 3 2 3-1 2 4-2 2v3l2 2-2 4-3-1-3 2-1 3h-4l-1-3-3-2-3 1-2-4 2-2v-3l-2-2 2-4 3 1 3-2 1-2Z",
  group: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M22 21v-2a4 4 0 0 0-3-3.9M16 3a4 4 0 0 1 0 8",
  agent: "M20 21v-2a7 7 0 0 0-14 0v2",
  download: "M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5",
  check: "m5 12 4 4L19 6",
  refresh: "M20 7V3l-4 4M4 17v4l4-4M3 10a9 9 0 0 1 16-5M21 14a9 9 0 0 1-16 5",
  globe: "M3 12h18M12 3a18 18 0 0 1 0 18 18 18 0 0 1 0-18Z",
};

export function NativeSymbol({
  name,
  size = 20,
  color = colors.foreground,
}: {
  name: SymbolName;
  size?: number;
  color?: string;
}) {
  return (
    <Svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
    >
      {paths[name] ? <Path d={paths[name]} /> : null}
      {name === "search" ? <Circle cx={10.5} cy={10.5} r={6.5} /> : null}
      {name === "clock" || name === "globe" ? <Circle cx={12} cy={12} r={9} /> : null}
      {name === "agent" || name === "group" ? (
        <Circle cx={name === "group" ? 9 : 13} cy={7} r={4} />
      ) : null}
      {name === "settings" ? <Circle cx={12} cy={12} r={3} /> : null}
      {name === "more"
        ? [5, 12, 19].map((x) => <Circle key={x} cx={x} cy={12} r={1} fill={color} />)
        : null}
      {name === "stop" ? (
        <Rect x={7} y={7} width={10} height={10} rx={2} fill={color} stroke="none" />
      ) : null}
    </Svg>
  );
}
