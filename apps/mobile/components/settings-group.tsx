import type { ReactNode } from "react";
import { Text, View } from "react-native";
import { useSession } from "../lib/session";
import { colors, styles } from "./ui";

export function SettingsGroup({ title, children }: { title: string; children: ReactNode }) {
  const { rtl } = useSession();
  return (
    <View style={styles.card}>
      <Text style={{ color: colors.secondary, textAlign: rtl ? "right" : "left" }}>{title}</Text>
      {children}
    </View>
  );
}
