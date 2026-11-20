import type { ExecutionReceipt } from "@lonora/contracts";
import { orderLineAction, ownerActionText } from "@lonora/core";
import { Text, View } from "react-native";
import type { Label } from "../lib/i18n";
import { useSession } from "../lib/session";
import { EvidenceLine, FactRows } from "./card-facts";
import { Icon } from "./shell/icon";
import { colors } from "./ui";

/**
 * The Execution Receipt (mandate 10.3, 11.2), drawn natively: the server posts it when the
 * broker confirms an operation, with the broker's own facts. The agent's reason is
 * labelled as the agent's words, and the owner's own order says so; it never reads as
 * verified before the account state was read back. Same record and same facts as the web card.
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
      {/* The kicker with its check on the reading side, as the web card's (v38). */}
      <View style={{ flexDirection: rtl ? "row-reverse" : "row", alignItems: "center", gap: 6 }}>
        <Icon name="check" size={14} color={colors.secondary} />
        <Text style={{ color: colors.secondary, textAlign: align }}>
          {t("executionReceipt")} · <Text style={{ writingDirection: "ltr" }}>{row.symbol}</Text>
        </Text>
      </View>
      <Text style={{ color: colors.foreground, fontWeight: "700", textAlign: align }}>
        {orderLineAction({ action: row.action }, locale).label}
        {row.partial ? ` · ${t("partiallyFilled")}` : ""}
        {row.agent_id == null ? ` · ${ownerActionText(locale).byYou}` : ""}
      </Text>
      {/* The broker's facts as the Trade Approval's label/value rows (v38 `.oa-dl`), as on Web. */}
      <FactRows
        rows={[
          ...facts
            .filter(([, value]) => value != null && value !== "")
            .map(([label, value]) => ({ label: t(label), value: String(value), ltr: true })),
          ...(row.stop_loss_removed ? [{ label: t("stopLoss"), value: t("removedValue") }] : []),
          ...(row.take_profit_removed
            ? [{ label: t("takeProfit"), value: t("removedValue") }]
            : []),
        ]}
      />
      <EvidenceLine
        tone={
          row.verification === "unverified"
            ? "warn"
            : row.verification === "pending"
              ? "plain"
              : "ok"
        }
        icon={
          row.verification === "unverified"
            ? "alert"
            : row.verification === "pending"
              ? "hourglass"
              : "check"
        }
      >
        <Text
          testID="execution-receipt-status"
          style={{ color: colors.foreground, textAlign: align }}
        >
          {t("confirmedByBroker")}
          {status ? ` · ${status}` : ""}
        </Text>
      </EvidenceLine>
      {row.reason ? (
        <EvidenceLine tone="plain" icon="chat" testID="execution-receipt-reason">
          <Text style={{ color: colors.foreground, textAlign: align }}>
            <Text style={{ fontWeight: "700" }}>{t("agentWords")}</Text>
            {": "}
            <Text style={{ writingDirection: "auto" }}>{row.reason}</Text>
          </Text>
        </EvidenceLine>
      ) : null}
    </View>
  );
}
