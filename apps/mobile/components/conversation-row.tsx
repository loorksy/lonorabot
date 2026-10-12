// Adapted from Tampletgrok's native Inbox conversation rows (Apache-2.0); see NOTICE.
import type { ReactNode } from "react";
import { Pressable, Text, View } from "react-native";
import { useSession } from "../lib/session";
import { colors } from "./ui";

export function ConversationRow({
  title,
  preview,
  avatar,
  onPress,
  onLongPress,
  disabled = false,
  busy = false,
}: {
  title: string;
  preview: string;
  avatar: ReactNode;
  onPress: () => void;
  onLongPress?: () => void;
  disabled?: boolean;
  busy?: boolean;
}) {
  const { rtl } = useSession();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={title}
      disabled={disabled}
      onPress={onPress}
      onLongPress={onLongPress}
      style={({ pressed }) => ({
        flexDirection: rtl ? "row-reverse" : "row",
        alignItems: "center",
        paddingHorizontal: 16,
        paddingVertical: 12,
        gap: 12,
        opacity: pressed || busy ? 0.55 : 1,
      })}
    >
      {avatar}
      <View style={{ flex: 1, gap: 5 }}>
        <Text
          numberOfLines={1}
          style={{
            color: colors.foreground,
            fontSize: 17,
            fontWeight: "600",
            textAlign: rtl ? "right" : "left",
          }}
        >
          {title}
        </Text>
        <Text
          numberOfLines={1}
          style={{ color: colors.secondary, fontSize: 15, textAlign: rtl ? "right" : "left" }}
        >
          {preview}
        </Text>
      </View>
    </Pressable>
  );
}
