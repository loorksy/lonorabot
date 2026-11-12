// Web's upload ring: a file's progress around a cancel ✕ (role progressbar).
import { Pressable, View } from "react-native";
import Svg, { Circle } from "react-native-svg";
import { useSession } from "../lib/session";
import { useTheme } from "../lib/theme";
import { Icon } from "./shell/icon";

export function UploadRing({
  p,
  label,
  onCancel,
  size = 28,
}: {
  /** 0..1 */
  p: number;
  label: string;
  onCancel?: () => void;
  size?: number;
}) {
  const { c } = useTheme();
  const { t } = useSession();
  const r = size / 2 - 2;
  const length = 2 * Math.PI * r;
  const value = Math.round(Math.max(0, Math.min(1, p)) * 100);
  const ring = (
    <View
      role="progressbar"
      accessibilityLabel={label}
      accessibilityValue={{ min: 0, max: 100, now: value }}
      aria-valuenow={value}
      style={{ width: size, height: size, alignItems: "center", justifyContent: "center" }}
    >
      <Svg
        width={size}
        height={size}
        style={{ position: "absolute", transform: [{ rotate: "-90deg" }] }}
      >
        <Circle cx={size / 2} cy={size / 2} r={r} stroke={c.line} strokeWidth={2.5} fill="none" />
        <Circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke={c.accent}
          strokeWidth={2.5}
          fill="none"
          strokeDasharray={`${length}`}
          strokeDashoffset={length * (1 - value / 100)}
          strokeLinecap="round"
        />
      </Svg>
      {onCancel ? <Icon name="close" size={size * 0.45} color={c.muted} /> : null}
    </View>
  );
  if (!onCancel) return ring;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${t("cancelUpload")}: ${label}`}
      hitSlop={8}
      onPress={onCancel}
    >
      {ring}
    </Pressable>
  );
}
