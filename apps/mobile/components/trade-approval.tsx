import type { TradeApproval } from "@lonora/contracts";
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
  const { t, errorText, rtl } = useSession();
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
      {row.execution_mode === "shadow" && (
        <Text style={{ color: colors.secondary }}>{t("shadowMode")}</Text>
      )}
      {row.requests.map((request, index) => (
        <View key={String(request.operation_id ?? index)}>
          <Text style={{ color: colors.foreground, writingDirection: "ltr" }}>
            {[
              request.action,
              request.symbol,
              request.volume,
              request.price,
              request.stop_loss,
              request.take_profit,
              request.position_id,
              request.order_id,
            ]
              .filter((value) => value != null)
              .join(" · ")}
          </Text>
          {request.clear_stop_loss === true && (
            <Text style={{ color: colors.foreground }}>{t("clearStopLoss")}</Text>
          )}
          {request.clear_take_profit === true && (
            <Text style={{ color: colors.foreground }}>{t("clearTakeProfit")}</Text>
          )}
        </View>
      ))}
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
        <Text style={{ color: colors.secondary }}>{t(row.status)}</Text>
      )}
      {row.results.map((result) => (
        <View key={result.operation_id}>
          <Text style={{ color: colors.foreground }}>{t(result.status)}</Text>
          <Text style={{ color: colors.foreground, writingDirection: "ltr" }}>
            {[result.broker_id, result.code, result.details.price, result.details.description]
              .filter((value) => value != null)
              .join(" · ")}
          </Text>
        </View>
      ))}
      <ErrorNotice text={error} />
    </View>
  );
}
