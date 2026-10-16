import type { Agent } from "@lonora/contracts";
import { Text } from "react-native";
import { useSession } from "../lib/session";

export function PersonalAgentBadge({ agent }: { agent?: Agent | null }) {
  const { t } = useSession();
  if (agent?.role !== "personal") return null;
  return (
    <Text
      accessibilityRole="image"
      accessibilityLabel={t("personalAgent")}
      style={{ color: "#b8860b", fontSize: 17 }}
    >
      ★
    </Text>
  );
}
