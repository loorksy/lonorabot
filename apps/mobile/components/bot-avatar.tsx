import {
  AvatarMotion,
  type AvatarStateId,
  avatarBarPath,
  avatarState,
  faceTransform,
  GEOMETRY,
  GLYPH_SCALE,
  resolveAvatarColor,
} from "@lonora/core";
import { memo, useEffect, useId, useRef, useState } from "react";
import { AppState, View } from "react-native";
import { useReducedMotion } from "react-native-reanimated";
import Svg, {
  Circle,
  ClipPath,
  Defs,
  Ellipse,
  FeColorMatrix,
  FeGaussianBlur,
  FeMerge,
  FeMergeNode,
  Filter,
  G,
  Path,
  RadialGradient,
  Rect,
  Stop,
} from "react-native-svg";
import { useSession } from "../lib/session";
import { colors } from "./ui";

/** Native SVG renderer of the supplied liquid-candle engine; no per-avatar WebView. */
export const BotAvatar = memo(function BotAvatar({
  color,
  size = 54,
  working = false,
  identity = "",
  superBot = false,
  state,
}: {
  color: string;
  size?: number;
  working?: boolean;
  variant?: string;
  identity?: string;
  superBot?: boolean;
  state?: AvatarStateId;
}) {
  const { t } = useSession();
  const id = `mta${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  const visualState = state ?? avatarState({ working });
  const [sampler] = useState(() => new AvatarMotion(visualState));
  const motion = useRef(sampler);
  const [bars, setBars] = useState(() => motion.current.frame(0));
  const reduced = useReducedMotion();
  const [poke, setPoke] = useState(0);
  const [foreground, setForeground] = useState(AppState.currentState === "active");
  const [gaze, setGaze] = useState(0);
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
    let frame = 0;
    let previous = 0;
    // Small idle list/message avatars are posters. Active work and call states animate.
    if (size < 64 && visualState === "waiting" && !poke) return;
    const draw = (now: number) => {
      if (!previous || now - previous >= 1000 / 30) {
        setBars(motion.current.frame(previous ? (now - previous) / 1000 : 0));
        setGaze(Math.sin(now / 2400) * 0.4);
        previous = now;
      }
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [visualState, reduced, foreground, size, poke]);
  useEffect(() => {
    if (!poke) return;
    const timeout = setTimeout(() => setPoke(0), 220);
    return () => clearTimeout(timeout);
  }, [poke]);
  const face = GEOMETRY.face;
  const look = faceTransform(reduced ? 0 : gaze, 0, reduced ? 0 : poke);
  const transform = `translate(${200 + look.tx} ${200.5 + look.ty}) rotate(${look.rot}) skewY(${look.skew}) scale(${look.sx} ${look.sy}) translate(-200 -200.5)`;
  return (
    <View
      testID="trading-avatar"
      style={{ width: size, height: size }}
      onTouchStart={reduced ? undefined : () => setPoke(0.8)}
    >
      <Svg
        width={size}
        height={size}
        viewBox={GEOMETRY.viewBox}
        accessibilityElementsHidden
        importantForAccessibility="no-hide-descendants"
      >
        <Defs>
          <ClipPath id={`${id}clip`}>
            <Rect {...face} />
          </ClipPath>
          <RadialGradient id={`${id}shade`} cx="34%" cy="27%" r="95%">
            <Stop offset="0" stopColor="#fff" stopOpacity={0.4} />
            <Stop offset="0.38" stopColor="#fff" stopOpacity={0} />
            <Stop offset="0.6" stopColor="#000" stopOpacity={0} />
            <Stop offset="1" stopColor="#000" stopOpacity={0.42} />
          </RadialGradient>
          <RadialGradient id={`${id}gloss`}>
            <Stop offset="0" stopColor="#fff" stopOpacity={0.5} />
            <Stop offset="1" stopColor="#fff" stopOpacity={0} />
          </RadialGradient>
          <Filter
            id={`${id}goo`}
            filterUnits="userSpaceOnUse"
            x={face.x}
            y={face.y}
            width={face.width}
            height={face.height}
          >
            <FeGaussianBlur in="SourceGraphic" stdDeviation={1.65} result="b" />
            <FeColorMatrix
              in="b"
              type="matrix"
              values="1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 0 0 0 20 -9.5"
              result="g"
            />
            <FeMerge>
              <FeMergeNode in="g" />
            </FeMerge>
          </Filter>
        </Defs>
        <Circle cx={200} cy={200} r={177} fill={resolveAvatarColor(identity, color).hex} />
        <Circle cx={200} cy={200} r={177} fill={`url(#${id}shade)`} />
        <G transform={transform}>
          <Rect {...face} fill="#0d0d11" />
          <G clipPath={`url(#${id}clip)`}>
            <G filter={size >= 64 ? `url(#${id}goo)` : undefined}>
              {bars.map((bar, i) => (
                <Path
                  // biome-ignore lint/suspicious/noArrayIndexKey: fixed particle slots never reorder.
                  key={i}
                  d={avatarBarPath(bar)}
                  fill="none"
                  stroke={`rgb(${Math.round(bar.r)},${Math.round(bar.g)},${Math.round(bar.b)})`}
                  strokeWidth={Math.max(bar.w * GLYPH_SCALE, 0.01)}
                  opacity={bar.o}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              ))}
            </G>
          </G>
        </G>
        <Ellipse
          cx={150}
          cy={82}
          rx={86}
          ry={38}
          transform="rotate(-24 150 82)"
          fill={`url(#${id}gloss)`}
          opacity={0.55}
        />
      </Svg>
      {superBot && (
        <View
          testID="super-bot-avatar"
          accessible
          accessibilityLabel={t("superBotEnabled")}
          pointerEvents="none"
          style={{
            position: "absolute",
            inset: -3,
            borderRadius: size,
            borderWidth: 2,
            borderColor: "#f0c866",
          }}
        >
          <Svg
            width={Math.max(12, size * 0.34)}
            height={Math.max(12, size * 0.34)}
            viewBox="0 0 20 20"
            style={{ position: "absolute", right: -3, top: -4 }}
          >
            <Circle cx={10} cy={10} r={10} fill={colors.background} />
            <Path d="M4 7 7 9 10 4 13 9 16 7 14 14H6Z" fill="#f0c866" />
          </Svg>
        </View>
      )}
    </View>
  );
});
