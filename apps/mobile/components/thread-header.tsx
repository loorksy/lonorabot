// Title capsule and bar controls adapted from the native thread screen; see NOTICE.
import type { ReactNode } from "react";
import { Pressable, Text, View } from "react-native";
import { useSession } from "../lib/session";
import { HeaderButton } from "./header-button";
import { NativeSymbol } from "./native-symbol";
import { colors } from "./ui";
export function ThreadHeader({
  title,
  avatar,
  settingsLabel,
  onBack,
  onSettings,
  onActions,
}: {
  title: string;
  avatar?: ReactNode;
  settingsLabel: string;
  onBack: () => void;
  onSettings: () => void;
  onActions: () => void;
}) {
  const { rtl, t } = useSession();
  return (
    <View
      style={{
        flexDirection: rtl ? "row-reverse" : "row",
        paddingHorizontal: 12,
        paddingTop: 4,
        paddingBottom: 8,
        alignItems: "center",
        gap: 8,
      }}
    >
      <HeaderButton label={t("back")} onPress={onBack}>
        <View style={{ transform: [{ scaleX: rtl ? -1 : 1 }] }}>
          <NativeSymbol name="back" size={23} />
        </View>
      </HeaderButton>
      <View style={{ flex: 1, alignItems: "center" }}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={settingsLabel}
          onPress={onSettings}
          style={({ pressed }) => ({
            maxWidth: "100%",
            flexDirection: rtl ? "row-reverse" : "row",
            alignItems: "center",
            gap: 8,
            paddingVertical: 6,
            paddingHorizontal: 10,
            borderRadius: 22,
            backgroundColor: colors.muted,
            opacity: pressed ? 0.6 : 1,
          })}
        >
          {avatar}
          <Text
            numberOfLines={1}
            style={{ flexShrink: 1, fontSize: 17, color: colors.foreground, fontWeight: "600" }}
          >
            {title}
          </Text>
        </Pressable>
      </View>
      <HeaderButton label={t("actions")} onPress={onActions}>
        <NativeSymbol name="more" size={21} />
      </HeaderButton>
    </View>
  );
}
