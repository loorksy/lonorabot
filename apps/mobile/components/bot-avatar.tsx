import {
  AvatarMotion,
  type AvatarStateId,
  avatarState,
  CAT_AVATAR_ASSETS,
  CAT_AVATAR_PALETTES,
  CAT_AVATAR_VIEWBOX,
  catAvatarSignals,
} from "@lonora/core";
import { memo, useEffect, useRef, useState } from "react";
import { AppState, View } from "react-native";
import { useReducedMotion } from "react-native-reanimated";
import Svg, { Circle, G, Image, Path } from "react-native-svg";
import { useSession } from "../lib/session";
import { colors } from "./ui";

/** The supplied cat shell and shared live signals, rendered natively without a WebView. */
export const BotAvatar = memo(function BotAvatar({
  size = 54,
  working = false,
  superBot = false,
  state,
}: {
  // Saved identity fields remain compatible; the cat is now the common appearance.
  color: string;
  size?: number;
  working?: boolean;
  variant?: string;
  identity?: string;
  superBot?: boolean;
  state?: AvatarStateId;
}) {
  const { t } = useSession();
  const visualState = state ?? avatarState({ working });
  const [sampler] = useState(() => new AvatarMotion(visualState));
  const motion = useRef(sampler);
  const [bars, setBars] = useState(() => motion.current.frame(0));
  const reduced = useReducedMotion();
  const [pressed, setPressed] = useState(false);
  const [foreground, setForeground] = useState(
    AppState.currentState !== "background" && AppState.currentState !== "inactive",
  );
  useEffect(() => {
    const listener = AppState.addEventListener("change", (next) =>
      setForeground(next === "active"),
    );
    return () => listener.remove();
  }, []);
  useEffect(() => {
    motion.current.setState(visualState);
    setBars(motion.current.frame(0, reduced));
    if (reduced || !foreground) return;
    // Idle and completed history stays still; active work and larger previews animate.
    if (
      size < 64 &&
      ["waiting", "success", "error", "warning", "sleeping", "celebrating"].includes(visualState)
    )
      return;
    let frame = 0;
    let previous = 0;
    const draw = (now: number) => {
      if (!previous || now - previous >= 1000 / 30) {
        setBars(motion.current.frame(previous ? (now - previous) / 1000 : 0));
        previous = now;
      }
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [visualState, reduced, foreground, size]);
  // Native currently uses the application's dark palette, regardless of OS theme.
  const palette = CAT_AVATAR_PALETTES.night;
  return (
    <View
      testID="trading-avatar"
      style={{ width: size, height: size }}
      onTouchStart={reduced ? undefined : () => setPressed(true)}
      onTouchEnd={() => setPressed(false)}
      onTouchCancel={() => setPressed(false)}
    >
      <Svg
        width={size}
        height={size}
        viewBox={CAT_AVATAR_VIEWBOX}
        accessibilityElementsHidden
        importantForAccessibility="no-hide-descendants"
      >
        <G transform={pressed && !reduced ? "translate(8 8) scale(.96)" : undefined}>
          <Image href={CAT_AVATAR_ASSETS.night} x={0} y={0} width={400} height={400} />
          {catAvatarSignals(bars).map((signal, i) => (
            <Path
              // biome-ignore lint/suspicious/noArrayIndexKey: fixed signal slots never reorder.
              key={i}
              d={signal.path}
              fill="none"
              stroke={palette.signal}
              strokeWidth={signal.width}
              opacity={signal.opacity}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ))}
        </G>
      </Svg>
      {superBot && (
        <View
          testID="super-bot-avatar"
          accessible
          accessibilityLabel={t("superBotEnabled")}
          pointerEvents="none"
          style={{ position: "absolute", right: -2, top: -2 }}
        >
          <Svg
            width={Math.max(12, size * 0.34)}
            height={Math.max(12, size * 0.34)}
            viewBox="0 0 20 20"
          >
            <Circle cx={10} cy={10} r={10} fill={colors.background} />
            <Path d="M4 7 7 9 10 4 13 9 16 7 14 14H6Z" fill="#f0c866" />
          </Svg>
        </View>
      )}
    </View>
  );
});
