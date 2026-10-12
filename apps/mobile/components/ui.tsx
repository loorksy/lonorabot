// Layout metrics and palette adapted from Tampletgrok's Expo inbox (Apache-2.0).
// See NOTICE for retained attribution. All network behavior uses the Lonora API.
import { appearance } from "@lonora/ui-tokens";
import type { ReactNode } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  type TextInputProps,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useSession } from "../lib/session";

export const colors = {
  background: appearance.dark.background,
  foreground: appearance.dark.foreground,
  muted: appearance.dark.muted,
  secondary: appearance.dark["muted-foreground"],
  border: appearance.dark.border,
  accent: appearance.dark.accent,
  chatUser: appearance.dark["chat-user"],
  error: "#EF8C8C",
  primary: appearance.dark.primary,
};
export function Screen({ children }: { children: ReactNode }) {
  return (
    <SafeAreaView style={styles.screen} edges={["top", "bottom"]}>
      {children}
    </SafeAreaView>
  );
}
export function Header({
  title,
  left,
  right,
}: {
  title: string;
  left?: ReactNode;
  right?: ReactNode;
}) {
  const { rtl } = useSession();
  return (
    <View style={[styles.header, { flexDirection: rtl ? "row-reverse" : "row" }]}>
      {left}
      <Text
        numberOfLines={1}
        accessibilityLabel={title}
        style={[styles.title, { textAlign: rtl ? "right" : "left" }]}
      >
        {title}
      </Text>
      {right}
    </View>
  );
}
export function Button({
  label,
  onPress,
  disabled = false,
  secondary = false,
}: {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  secondary?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        secondary && styles.secondaryButton,
        (pressed || disabled) && { opacity: 0.5 },
      ]}
    >
      <Text style={[styles.buttonLabel, secondary && { color: colors.foreground }]}>{label}</Text>
    </Pressable>
  );
}
export function Field({ label, ...props }: TextInputProps & { label?: string }) {
  const { rtl } = useSession();
  return (
    <View style={{ gap: 8 }}>
      {label ? (
        <Text style={[styles.label, { textAlign: rtl ? "right" : "left" }]}>{label}</Text>
      ) : null}
      <TextInput
        {...props}
        accessibilityLabel={label ?? props.placeholder}
        placeholderTextColor={colors.secondary}
        style={[
          styles.input,
          { textAlign: rtl ? "right" : "left", writingDirection: rtl ? "rtl" : "ltr" },
          props.style,
        ]}
      />
    </View>
  );
}
export function ErrorNotice({ text }: { text?: string | null }) {
  return text ? (
    <Text accessibilityRole="alert" style={styles.error}>
      {text}
    </Text>
  ) : null;
}
export function Loading() {
  return (
    <View style={styles.center}>
      <ActivityIndicator size="large" color={colors.foreground} />
    </View>
  );
}
export const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  header: {
    alignItems: "center",
    gap: 12,
    paddingHorizontal: 16,
    paddingTop: 8,
    paddingBottom: 14,
  },
  title: { flex: 1, color: colors.foreground, fontSize: 26, fontWeight: "700" },
  label: { color: colors.secondary, fontSize: 14 },
  input: {
    minHeight: 48,
    borderRadius: 12,
    backgroundColor: colors.muted,
    color: colors.foreground,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 16,
  },
  button: {
    minHeight: 44,
    minWidth: 44,
    paddingHorizontal: 15,
    paddingVertical: 11,
    borderRadius: 22,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.primary,
  },
  secondaryButton: { backgroundColor: colors.accent },
  buttonLabel: { color: colors.background, fontWeight: "600", fontSize: 14 },
  error: { color: colors.error, paddingHorizontal: 20, paddingVertical: 8, textAlign: "center" },
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.background,
  },
  card: { borderRadius: 14, padding: 18, backgroundColor: colors.muted, gap: 12 },
});
