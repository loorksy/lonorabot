// Native rendering of shared template avatar geometry; see NOTICE.
import {
  AVATAR_CENTER,
  AVATAR_SHAPES,
  AVATAR_VIEWBOX,
  avatarIdentitySeed,
  organicAvatarPath,
  resolveAvatarColor,
} from "@lonora/core";
import { useEffect, useId } from "react";
import { View } from "react-native";
import Animated, {
  cancelAnimation,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withRepeat,
  withTiming,
} from "react-native-reanimated";
import Svg, { Circle, Defs, Ellipse, G, LinearGradient, Path, Rect, Stop } from "react-native-svg";
import { colors } from "./ui";
export function BotAvatar({
  color,
  size = 54,
  working = false,
  variant = "orb",
  identity = "",
}: {
  color: string;
  size?: number;
  working?: boolean;
  variant?: string;
  identity?: string;
}) {
  const id = useId().replace(/[^a-zA-Z0-9]/g, "");
  const colorDef = resolveAvatarColor(identity, color);
  const seed = avatarIdentitySeed(identity || color);
  const phase = useSharedValue(0);
  const reducedMotion = useReducedMotion();
  useEffect(() => {
    cancelAnimation(phase);
    phase.value = 0;
    if (working && !reducedMotion)
      phase.value = withRepeat(withTiming(1, { duration: 1800 }), -1, true);
    return () => cancelAnimation(phase);
  }, [working, reducedMotion, phase]);
  const motion = useAnimatedStyle(() => ({
    transform: [
      { scale: 1 + phase.value * 0.03 },
      { rotate: variant === "organic" ? `${phase.value * 5 - 2.5}deg` : "0deg" },
    ],
  }));
  const path =
    variant === "square" || variant === "diamond" ? AVATAR_SHAPES.squircle : AVATAR_SHAPES[variant];
  return (
    <View style={{ width: size, height: size }}>
      <Animated.View style={[{ width: size, height: size }, motion]}>
        {variant === "organic" ? (
          <Svg width={size} height={size} viewBox="-60 -60 120 120">
            <Path d={organicAvatarPath(seed)} fill={colorDef.hex} />
            <Rect x={-14} y={-12} width={7} height={24} rx={3.5} fill={colorDef.eyeColor} />
            <Rect x={7} y={-12} width={7} height={24} rx={3.5} fill={colorDef.eyeColor} />
          </Svg>
        ) : path ? (
          <Svg width={size} height={size} viewBox={AVATAR_VIEWBOX}>
            <Defs>
              <LinearGradient id={id} x1="0" x2="1" y1="0" y2="1">
                <Stop offset="0" stopColor={colorDef.light} />
                <Stop offset="1" stopColor={colorDef.dark} />
              </LinearGradient>
            </Defs>
            <Path
              d={path}
              fill={`url(#${id})`}
              transform={
                variant === "diamond" ? `rotate(45 ${AVATAR_CENTER} ${AVATAR_CENTER})` : undefined
              }
            />
            <G fill={colorDef.eyeColor}>
              <Ellipse cx={AVATAR_CENTER - 29} cy={AVATAR_CENTER - 8} rx={10} ry={7} />
              <Ellipse cx={AVATAR_CENTER + 29} cy={AVATAR_CENTER - 8} rx={10} ry={7} />
            </G>
          </Svg>
        ) : (
          <Svg width={size} height={size} viewBox="0 0 100 100">
            <Circle cx={50} cy={50} r={50} fill={colorDef.hex} />
            <Rect x={16} y={28} width={68} height={44} rx={23} fill={colors.background} />
            <Rect x={33} y={41.5} width={11} height={17} rx={5} fill={colors.foreground} />
            <Rect x={56} y={41.5} width={11} height={17} rx={5} fill={colors.foreground} />
          </Svg>
        )}
      </Animated.View>
      {working ? (
        <View
          style={{
            position: "absolute",
            right: 0,
            bottom: 0,
            width: Math.max(7, size * 0.18),
            height: Math.max(7, size * 0.18),
            borderRadius: size,
            backgroundColor: colors.warning,
          }}
        />
      ) : null}
    </View>
  );
}
