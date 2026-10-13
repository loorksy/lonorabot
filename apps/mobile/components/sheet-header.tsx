// Native sheet text buttons adapted from the template's portable fallback; see NOTICE.
import { useRouter } from "expo-router";
import { Pressable, Text, View } from "react-native";
import { useSession } from "../lib/session";
import { colors } from "./ui";
export function SheetHeader({
  title,
  onClose,
  action,
  onAction,
  disabled,
}: {
  title: string;
  onClose?: () => void;
  action?: string;
  onAction?: () => void;
  disabled?: boolean;
}) {
  const router = useRouter();
  const { rtl, t } = useSession();
  return (
    <View
      style={{
        flexDirection: rtl ? "row-reverse" : "row",
        alignItems: "center",
        minHeight: 56,
        paddingHorizontal: 20,
        gap: 12,
      }}
    >
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={t("back")}
        hitSlop={8}
        onPress={onClose ?? (() => (router.canGoBack() ? router.back() : router.replace("/")))}
        style={{ minWidth: 44, paddingVertical: 10 }}
      >
        <Text style={{ color: colors.foreground, fontSize: 17 }}>{t("back")}</Text>
      </Pressable>
      <Text
        accessibilityRole="header"
        numberOfLines={1}
        style={{
          flex: 1,
          color: colors.foreground,
          fontSize: 17,
          fontWeight: "600",
          textAlign: "center",
        }}
      >
        {title}
      </Text>
      {action && onAction ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={action}
          disabled={disabled}
          hitSlop={8}
          onPress={onAction}
          style={{ minWidth: 44, paddingVertical: 10, opacity: disabled ? 0.4 : 1 }}
        >
          <Text
            style={{
              color: colors.foreground,
              fontSize: 17,
              fontWeight: "600",
              textAlign: rtl ? "left" : "right",
            }}
          >
            {action}
          </Text>
        </Pressable>
      ) : (
        <View style={{ width: 44 }} />
      )}
    </View>
  );
}
