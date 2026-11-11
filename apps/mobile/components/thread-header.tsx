// Title capsule and bar controls adapted from the native thread screen; see NOTICE.
import type { ReactNode } from "react";
import { Pressable, Text, View } from "react-native";
import { useSession } from "../lib/session";
import { useShellColors } from "../lib/theme";
import { HeaderButton } from "./header-button";
import { NativeSymbol } from "./native-symbol";
export function ThreadHeader({
  title,
  avatar,
  settingsLabel,
  onBack,
  onSettings,
  onActions,
  onCall,
  safety,
}: {
  title: string;
  avatar?: ReactNode;
  settingsLabel: string;
  onBack: () => void;
  onSettings: () => void;
  onActions: () => void;
  onCall?: () => void;
  /** An agent thread shows its one safety pill: can it trade now, what stops it. */
  safety?: ReactNode;
}) {
  const { rtl, t } = useSession();
  const shell = useShellColors();
  return (
    <View>
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
            <NativeSymbol name="back" size={23} color={shell.foreground} />
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
              backgroundColor: shell.muted,
              opacity: pressed ? 0.6 : 1,
            })}
          >
            {avatar}
            <Text
              numberOfLines={1}
              style={{ flexShrink: 1, fontSize: 17, color: shell.foreground, fontWeight: "600" }}
            >
              {title}
            </Text>
          </Pressable>
        </View>
        {onCall ? (
          <HeaderButton label={t("callAgent")} onPress={onCall}>
            <NativeSymbol name="call" size={21} color={shell.foreground} />
          </HeaderButton>
        ) : null}
        <HeaderButton label={t("actions")} onPress={onActions}>
          <NativeSymbol name="more" size={21} color={shell.foreground} />
        </HeaderButton>
      </View>
      {safety ?? null}
    </View>
  );
}
