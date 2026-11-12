import type { ExecutionReceipt } from "@lonora/contracts";
import { orderLineAction } from "@lonora/core";
import { Text, View } from "react-native";
import type { Label } from "../lib/i18n";
import { useSession } from "../lib/session";
import { colors } from "./ui";

/**
 * The Execution Receipt (mandate 10.3, 11.2), drawn natively: the server posts it when the
 * broker confirms an operation, with the broker's own facts. The agent's reason is
 * labelled as the agent's words; it never reads as verified before the account state was
 * read back. Same record and same facts as the web card.
 */
export function ExecutionReceiptCard({ row }: { row: ExecutionReceipt }) {
  const { t, rtl, locale } = useSession();
  const align = rtl ? "right" : "left";
  const facts: [Label, string | null | undefined][] = [["receiptTicket", row.ticket]];
  if (row.kind === "fill") facts.push(["receiptVolume", row.volume], ["fillPrice", row.price]);
  else if (row.kind === "order")
    facts.push(
      ["receiptVolume", row.volume],
      ["orderPrice", row.price],
      ["stopLoss", row.stop_loss],
      ["takeProfit", row.take_profit],
    );
  else if (row.kind === "modify")
    facts.push(
      ["newPrice", row.price],
      ["newStopLoss", row.stop_loss],
      ["newTakeProfit", row.take_profit],
    );
  const status =
    row.verification === "verified"
      ? t("accountVerified")
      : row.verification === "unverified"
        ? t("accountUnverified")
        : row.verification === "pending"
          ? t("accountChecking")
          : null;
  return (
    <View
      testID="execution-receipt"
      style={{ borderWidth: 1, borderColor: colors.border, padding: 12, gap: 8 }}
    >
      <Text style={{ color: colors.secondary, textAlign: align }}>
        {t("executionReceipt")} · <Text style={{ writingDirection: "ltr" }}>{row.symbol}</Text>
      </Text>
      <Text style={{ color: colors.foreground, fontWeight: "700", textAlign: align }}>
        {orderLineAction({ action: row.action }, locale).label}
        {row.partial ? ` · ${t("partiallyFilled")}` : ""}
      </Text>
      <View style={{ flexDirection: rtl ? "row-reverse" : "row", flexWrap: "wrap", gap: 12 }}>
        {facts
          .filter(([, value]) => value != null && value !== "")
          .map(([label, value]) => (
            <View key={label}>
              <Text style={{ color: colors.secondary, textAlign: align }}>{t(label)}</Text>
              <Text style={{ color: colors.foreground, writingDirection: "ltr", textAlign: align }}>
                {value}
              </Text>
            </View>
          ))}
        {row.stop_loss_removed ? (
          <View>
            <Text style={{ color: colors.secondary, textAlign: align }}>{t("stopLoss")}</Text>
            <Text style={{ color: colors.foreground }}>{t("removedValue")}</Text>
          </View>
        ) : null}
        {row.take_profit_removed ? (
          <View>
            <Text style={{ color: colors.secondary, textAlign: align }}>{t("takeProfit")}</Text>
            <Text style={{ color: colors.foreground }}>{t("removedValue")}</Text>
          </View>
        ) : null}
      </View>
      <Text
        testID="execution-receipt-status"
        style={{ color: colors.foreground, textAlign: align }}
      >
        {t("confirmedByBroker")}
        {status ? ` · ${status}` : ""}
      </Text>
      {row.reason ? (
        <View testID="execution-receipt-reason">
          <Text style={{ color: colors.secondary, textAlign: align }}>{t("agentWords")}</Text>
          <Text style={{ color: colors.foreground, writingDirection: "auto" }}>{row.reason}</Text>
        </View>
      ) : null}
    </View>
  );
}
