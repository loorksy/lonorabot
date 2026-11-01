import type { AgentMarketMode } from "@lonora/core";
import { Text, View } from "react-native";
import { useSession } from "../lib/session";
import { type BrokerPair, BrokerPairPicker } from "./broker-pair-picker";
import { SettingsGroup, SettingsRow } from "./settings-group";
import { colors } from "./ui";

export function AgentMarketPicker({
  mode,
  pair,
  onMode,
  onPair,
  allowFixed = false,
}: {
  mode: AgentMarketMode;
  pair: BrokerPair;
  onMode: (mode: AgentMarketMode) => void;
  onPair: (pair: BrokerPair) => void;
  allowFixed?: boolean;
}) {
  const { t, rtl } = useSession();
  return (
    <View testID="agent-market-picker-native" style={{ gap: 12 }}>
      <SettingsGroup
        title={t("agentMarketScope")}
        footer={mode === "fixed" ? t("keepFixedMarketHint") : t("defaultMarketHint")}
      >
        {(
          [...(allowFixed ? ["fixed" as const] : []), "general", "market"] as AgentMarketMode[]
        ).map((value) => (
          <SettingsRow
            key={value}
            testID={`agent-market-mode-${value}-native`}
            title={t(
              value === "fixed"
                ? "keepFixedMarket"
                : value === "general"
                  ? "generalAgent"
                  : "defaultMarket",
            )}
            value={mode === value ? t("active") : undefined}
            onPress={() => onMode(value)}
          />
        ))}
      </SettingsGroup>
      {mode === "market" && <BrokerPairPicker value={pair} onChange={onPair} />}
      {mode === "fixed" && (
        <Text style={{ color: colors.secondary, textAlign: rtl ? "right" : "left" }}>
          {pair.trading_symbol}
        </Text>
      )}
    </View>
  );
}
