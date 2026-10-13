// Template toolbar geometry retained from its native inbox; see NOTICE.
import type { ReactNode } from "react";
import { Pressable } from "react-native";
import { colors } from "./ui";

export function HeaderButton({
  label,
  onPress,
  children,
  active = false,
  disabled = false,
  filled = false,
}: {
  label: string;
  onPress: () => void;
  children: ReactNode;
  active?: boolean;
  disabled?: boolean;
  filled?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ selected: active, disabled }}
      disabled={disabled}
      onPress={onPress}
      hitSlop={2}
      style={({ pressed }) => ({
        width: 40,
        height: 40,
        borderRadius: 20,
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: filled ? colors.primary : active || pressed ? colors.muted : "transparent",
        opacity: disabled ? 0.4 : 1,
      })}
    >
      {children}
    </Pressable>
  );
}
