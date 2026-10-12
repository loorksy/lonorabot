// Adapted from Tampletgrok's native time separator (Apache-2.0); see NOTICE.
import { Text } from "react-native";
import { useSession } from "../lib/session";
import { colors } from "./ui";

export function TimeSeparator({ createdAt }: { createdAt: string }) {
  const { locale, t } = useSession();
  const day = new Date(createdAt);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  const title =
    day.toDateString() === today.toDateString()
      ? t("today")
      : day.toDateString() === yesterday.toDateString()
        ? t("yesterday")
        : day.toLocaleDateString(locale, { year: "numeric", month: "short", day: "numeric" });
  return (
    <Text
      accessibilityRole="header"
      style={{ color: colors.secondary, fontSize: 12, textAlign: "center", marginVertical: 12 }}
    >
      {title}
    </Text>
  );
}
