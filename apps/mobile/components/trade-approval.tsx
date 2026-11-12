import type { TradeApproval } from "@lonora/contracts";
import {
  approvalStatusText,
  brokerTicketLabel,
  financialResultReason,
  operationStatusText,
} from "@lonora/core";
import { useRef, useState } from "react";
import { Text, View } from "react-native";
import { api } from "../lib/api";
import { useSession } from "../lib/session";
import { Button, colors, ErrorNotice } from "./ui";

export function TradeApprovalCard({
  row,
  onChange,
}: {
  row: TradeApproval;
  onChange: (value: TradeApproval) => void;
}) {
  const { t, errorText, rtl, locale } = useSession();
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const [error, setError] = useState<string>();
  async function decide(decision: "approve" | "reject") {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError(undefined);
    try {
      onChange(
        await api.post<TradeApproval>(`/trading/approvals/${row.id}/decision`, { decision }),
      );
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  return (
    <View style={{ borderWidth: 1, borderColor: colors.border, padding: 12, gap: 8 }}>
      <Text style={{ color: colors.foreground, textAlign: rtl ? "right" : "left" }}>
        {t("tradeApproval")}
      </Text>
      {row.requests.map((request, index) => (
        <View key={String(request.operation_id ?? index)}>
          <Text style={{ color: colors.foreground, writingDirection: "ltr" }}>
            {[request.action, request.symbol, request.volume]
              .filter((value) => value != null)
              .join(" · ")}
          </Text>
          {(
            [
              ["approvalPrice", request.price],
              ["stopLoss", request.stop_loss],
              ["takeProfit", request.take_profit],
              ["approvalTicket", request.position_id ?? request.order_id],
            ] as const
          )
            .filter(([, value]) => value != null)
            .map(([label, value]) => (
              <Text
                key={label}
                style={{ color: colors.foreground, textAlign: rtl ? "right" : "left" }}
              >
                {t(label)}: <Text style={{ writingDirection: "ltr" }}>{String(value)}</Text>
              </Text>
            ))}
          {request.clear_stop_loss === true && (
            <Text style={{ color: colors.foreground }}>{t("clearStopLoss")}</Text>
          )}
          {request.clear_take_profit === true && (
            <Text style={{ color: colors.foreground }}>{t("clearTakeProfit")}</Text>
          )}
        </View>
      ))}
      {row.tolerance ? (
        <Text style={{ color: colors.secondary }}>
          {t("validWithin")}{" "}
          {row.reference_price ? `${row.reference_price} ± ${row.tolerance}` : `± ${row.tolerance}`}
        </Text>
      ) : null}
      {row.reason ? (
        <View testID="trade-approval-reason">
          <Text style={{ color: colors.secondary }}>{t("agentWords")}</Text>
          <Text style={{ color: colors.foreground, writingDirection: "auto" }}>{row.reason}</Text>
        </View>
      ) : null}
      {row.status === "pending" ? (
        <View style={{ flexDirection: rtl ? "row-reverse" : "row", gap: 8 }}>
          <Button label={t("approve")} disabled={busy} onPress={() => void decide("approve")} />
          <Button
            label={t("reject")}
            secondary
            disabled={busy}
            onPress={() => void decide("reject")}
          />
        </View>
      ) : (
        <Text style={{ color: colors.secondary }}>{approvalStatusText(row.status, locale)}</Text>
      )}
      {row.results.map((result) => {
        // Shared with Web: the evidence-backed stage ("Not sent" when it never reached
        // the broker) and why, in the owner's language instead of a raw code. An
        // uncertain result always says it will not be sent again.
        const reason = financialResultReason(result.status, result.code, locale);
        return (
          <View key={result.operation_id}>
            <Text style={{ color: colors.foreground }}>
              {operationStatusText(result.status, result.details, locale)}
            </Text>
            {reason && (
              <Text style={{ color: colors.foreground, textAlign: rtl ? "right" : "left" }}>
                {reason}
              </Text>
            )}
            {result.broker_id != null && (
              <Text style={{ color: colors.foreground, textAlign: rtl ? "right" : "left" }}>
                {brokerTicketLabel(locale)}:{" "}
                <Text style={{ writingDirection: "ltr" }}>{result.broker_id}</Text>
              </Text>
            )}
            {[result.details.price, result.details.description].some((value) => value != null) && (
              <Text style={{ color: colors.foreground, writingDirection: "ltr" }}>
                {[result.details.price, result.details.description]
                  .filter((value) => value != null)
                  .join(" · ")}
              </Text>
            )}
          </View>
        );
      })}
      <ErrorNotice text={error} />
    </View>
  );
}
