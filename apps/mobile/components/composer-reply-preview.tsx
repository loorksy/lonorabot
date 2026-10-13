import type { Message } from "@lonora/contracts";
import { Pressable, Text, View } from "react-native";
import { useSession } from "../lib/session";
import { NativeSymbol } from "./native-symbol";
import { colors } from "./ui";
export function ComposerReplyPreview({
  message,
  onClose,
}: {
  message: Message;
  onClose?: () => void;
}) {
  const { rtl, t } = useSession();
  return (
    <View
      style={{
        flexDirection: rtl ? "row-reverse" : "row",
        alignItems: "center",
        gap: 10,
        padding: 12,
        borderRadius: 12,
        backgroundColor: colors.muted,
      }}
    >
      <View style={{ width: 2, height: 32, backgroundColor: colors.secondary, borderRadius: 1 }} />
      <View style={{ flex: 1, gap: 3 }}>
        <Text style={{ color: colors.secondary, fontSize: 12, textAlign: rtl ? "right" : "left" }}>
          {t("reply")}
        </Text>
        <Text
          numberOfLines={2}
          style={{
            color: colors.foreground,
            fontSize: 13,
            lineHeight: 18,
            writingDirection: "auto",
            textAlign: rtl ? "right" : "left",
          }}
        >
          {message.content || t("attachments")}
        </Text>
      </View>
      {onClose ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t("cancelReply")}
          hitSlop={8}
          onPress={onClose}
        >
          <NativeSymbol name="close" size={16} color={colors.secondary} />
        </Pressable>
      ) : null}
    </View>
  );
}
