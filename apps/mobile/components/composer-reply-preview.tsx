import type { Message } from "@lonora/contracts";
import { Pressable, Text, View } from "react-native";
import { useSession } from "../lib/session";
import { useShellColors } from "../lib/theme";
import { NativeSymbol } from "./native-symbol";
export function ComposerReplyPreview({
  message,
  onClose,
}: {
  message: Message;
  onClose?: () => void;
}) {
  const { rtl, t } = useSession();
  const shell = useShellColors();
  return (
    <View
      style={{
        flexDirection: rtl ? "row-reverse" : "row",
        alignItems: "center",
        gap: 10,
        padding: 12,
        borderRadius: 12,
        backgroundColor: shell.muted,
      }}
    >
      <View style={{ width: 2, height: 32, backgroundColor: shell.secondary, borderRadius: 1 }} />
      <View style={{ flex: 1, gap: 3 }}>
        <Text style={{ color: shell.secondary, fontSize: 12, textAlign: rtl ? "right" : "left" }}>
          {t("reply")}
        </Text>
        <Text
          numberOfLines={2}
          style={{
            color: shell.foreground,
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
          <NativeSymbol name="close" size={16} color={shell.secondary} />
        </Pressable>
      ) : null}
    </View>
  );
}
