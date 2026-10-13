// Adapted from Tampletgrok's native time separator (Apache-2.0); see NOTICE.
import { formatTimeSeparator } from "@lonora/core";
import { Text } from "react-native";
import { useSession } from "../lib/session";
import { colors } from "./ui";

export function TimeSeparator({ createdAt }: { createdAt: string }) {
  const { locale, t } = useSession();
  const title = formatTimeSeparator(createdAt, locale, {
    today: t("today"),
    yesterday: t("yesterday"),
  });
  return (
    <Text
      accessibilityRole="header"
      style={{ color: colors.secondary, fontSize: 12, textAlign: "center", marginVertical: 12 }}
    >
      {title}
    </Text>
  );
}
