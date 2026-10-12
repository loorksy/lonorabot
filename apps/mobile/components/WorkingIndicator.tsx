// Modified from Tampletgrok apps/mobile/components/WorkingIndicator.tsx (Apache-2.0); see NOTICE.
import type { Run } from "@lonora/contracts";
import { isWorking } from "@lonora/core";
import { useEffect } from "react";
import { Text, View } from "react-native";
import Animated, {
  cancelAnimation,
  Easing,
  interpolate,
  type SharedValue,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withRepeat,
  withTiming,
} from "react-native-reanimated";
import { useSession } from "../lib/session";
import { colors } from "./ui";

function Dot({
  progress,
  offset,
  still,
}: {
  progress: SharedValue<number>;
  offset: number;
  still: boolean;
}) {
  const style = useAnimatedStyle(() => {
    if (still) return { opacity: 0.55 };
    const phase = (progress.value + offset) % 1;
    return {
      opacity: interpolate(phase, [0, 0.5, 1], [0.25, 1, 0.25]),
      transform: [{ scale: interpolate(phase, [0, 0.5, 1], [0.85, 1.15, 0.85]) }],
    };
  });
  return (
    <Animated.View
      style={[{ width: 7, height: 7, borderRadius: 4, backgroundColor: colors.secondary }, style]}
    />
  );
}
export function WorkingIndicator({ compact = false, run }: { compact?: boolean; run?: Run }) {
  const { t } = useSession();
  const still = useReducedMotion();
  const progress = useSharedValue(0);
  const working = run ? isWorking(run.status) : true;
  useEffect(() => {
    if (still || !working) return;
    progress.value = withRepeat(
      withTiming(1, { duration: 1100, easing: Easing.linear }),
      -1,
      false,
    );
    return () => cancelAnimation(progress);
  }, [progress, still, working]);
  if (run && !working) return <Text style={{ color: colors.secondary }}>{t(run.status)}</Text>;
  return (
    <View
      accessibilityLabel={t(run?.status ?? "running")}
      style={{
        flexDirection: "row",
        alignItems: "center",
        gap: 6,
        padding: compact ? 0 : 12,
        alignSelf: "flex-start",
      }}
    >
      {(compact ? [0] : [0, 1, 2]).map((index) => (
        <Dot key={index} progress={progress} offset={index / 3} still={Boolean(still)} />
      ))}
    </View>
  );
}
