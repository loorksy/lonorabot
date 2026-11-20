import type { TradeApproval } from "@lonora/contracts";
import {
  approvalEndTone,
  approvalStatusText,
  brokerPriceLabel,
  brokerTicketLabel,
  brokerWordsLabel,
  failedResultFallback,
  financialResultReason,
  isolate,
  operationStatusText,
  orderLineAction,
} from "@lonora/core";
import { useRef, useState } from "react";
import { Text, View } from "react-native";
import { api } from "../lib/api";
import { ApiError } from "../lib/api-error";
import { useSession } from "../lib/session";
import { EvidenceLine, FactRows } from "./card-facts";
import { Icon } from "./shell/icon";
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
      // Decided elsewhere (its row, its slot, another device): a second tap shows the
      // record as the server holds it now (mandate 10.2.3).
      if (row.thread_id) {
        const rows = await api
          .get<TradeApproval[]>(`/trading/approvals?thread_id=${encodeURIComponent(row.thread_id)}`)
          .catch(() => []);
        const current = rows.find((item) => item.id === row.id);
        if (current) onChange(current);
      }
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  const symbol = row.requests.find((request) => request.symbol)?.symbol;
  const align = { textAlign: rtl ? ("right" as const) : ("left" as const) };
  // ok only once every result is confirmed; never a success look on a failure (0.4).
  const tone = approvalEndTone(row);
  return (
    <View
      testID="trade-approval"
      style={{ borderWidth: 1, borderColor: colors.border, padding: 12, gap: 8 }}
    >
      {/* The kicker with its shield on the reading side, as the web card's (v38). */}
      <View style={{ flexDirection: rtl ? "row-reverse" : "row", alignItems: "center", gap: 6 }}>
        <Icon name="shield" size={14} color={colors.secondary} />
        <Text style={[{ color: colors.secondary, fontSize: 13, fontWeight: "600" }, align]}>
          {t("tradeApproval")}
          {symbol ? ` · ${isolate(String(symbol))}` : ""}
        </Text>
      </View>
      {row.requests.map((request, index) => {
        // The request in words and its volume («شراء 0.10»), never a raw action id.
        const action = orderLineAction(request, locale);
        const market = request.action === "buy" || request.action === "sell";
        // Its facts as the web card's label/value rows (v38 `.oa-dl`).
        const rows: { label: string; value: string; ltr?: boolean }[] = [];
        if (market) rows.push({ label: t("approvalEntry"), value: t("approvalAtMarket") });
        else if (request.price != null)
          rows.push({ label: t("approvalEntry"), value: String(request.price), ltr: true });
        if (request.stop_loss != null)
          rows.push({ label: t("stopLoss"), value: String(request.stop_loss), ltr: true });
        if (request.take_profit != null)
          rows.push({ label: t("takeProfit"), value: String(request.take_profit), ltr: true });
        if (request.clear_stop_loss === true)
          rows.push({ label: t("stopLoss"), value: t("clearStopLoss") });
        if (request.clear_take_profit === true)
          rows.push({ label: t("takeProfit"), value: t("clearTakeProfit") });
        const ticket = request.position_id ?? request.order_id;
        if (ticket != null)
          rows.push({ label: t("approvalTicket"), value: String(ticket), ltr: true });
        return (
          <View key={String(request.operation_id ?? index)} style={{ gap: 6 }}>
            <Text style={[{ color: colors.foreground, fontSize: 16, fontWeight: "700" }, align]}>
              {action.label}
              {action.volume ? ` ${isolate(action.volume)}` : ""}
            </Text>
            <FactRows rows={rows} />
          </View>
        );
      })}
      {row.tolerance ? (
        <FactRows
          rows={[
            {
              label: t("validWithin"),
              // Isolated left-to-right with no-break spaces: «2346.80 ± 1.50» stays whole and in
              // order inside the Arabic card (v38).
              value: `\u2066${row.reference_price ? `${row.reference_price}\u00a0±\u00a0` : "±\u00a0"}${row.tolerance}\u2069`,
            },
          ]}
        />
      ) : null}
      {row.reason ? (
        <EvidenceLine tone="plain" icon="chat" testID="trade-approval-reason">
          <Text style={[{ color: colors.foreground }, align]}>
            <Text style={{ fontWeight: "700" }}>{t("agentWords")}</Text>
            {": "}
            <Text style={{ writingDirection: "auto" }}>{row.reason}</Text>
          </Text>
        </EvidenceLine>
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
        <EvidenceLine
          tone={tone === "wait" ? "plain" : tone}
          icon={
            tone === "ok"
              ? "check"
              : tone === "wait"
                ? "clock"
                : tone === "warn"
                  ? "alert"
                  : "close"
          }
          testID={`trade-approval-status-${tone}`}
        >
          <Text style={[{ color: colors.foreground }, align]}>
            {approvalStatusText(row.status, locale)}
          </Text>
        </EvidenceLine>
      )}
      {/* A confirmed result is shown once: as its Execution Receipt (10.3). */}
      {row.results
        .filter((result) => result.status !== "confirmed")
        .map((result) => {
          // Shared with Web: the evidence-backed stage ("Not sent" when it never reached
          // the broker) and why, in the owner's language instead of a raw code. An
          // uncertain result always says it will not be sent again; only a result known not
          // to have executed falls back to the error catalog, and a code it does not know
          // reads the shared fallback, as on Web.
          const reason =
            financialResultReason(result.status, result.code, locale) ??
            (result.status === "failed" && result.code
              ? errorText(new ApiError(result.code, 0), failedResultFallback(locale))
              : null);
          const prices = (["price", "execution_price"] as const).filter(
            (key) => result.details[key] != null && result.details[key] !== "",
          );
          const words = result.details.description;
          return (
            <EvidenceLine
              key={result.operation_id}
              tone={result.status === "failed" ? "bad" : "warn"}
              icon="alert"
              testID={`trade-approval-result-${result.status}`}
            >
              <Text style={[{ color: colors.foreground, fontWeight: "600" }, align]}>
                {operationStatusText(result.status, result.details, locale)}
              </Text>
              {/* In the web line's order: status, ticket, reason, prices, the broker's words. */}
              {result.broker_id != null && (
                <Text style={[{ color: colors.foreground }, align]}>
                  {brokerTicketLabel(locale)}:{" "}
                  <Text style={{ writingDirection: "ltr" }}>{result.broker_id}</Text>
                </Text>
              )}
              {reason ? <Text style={[{ color: colors.foreground }, align]}>{reason}</Text> : null}
              {prices.map((key) => (
                <Text
                  key={key}
                  testID={`trade-approval-result-${key}`}
                  style={[{ color: colors.foreground }, align]}
                >
                  {brokerPriceLabel(key, locale)}:{" "}
                  <Text style={{ writingDirection: "ltr" }}>{String(result.details[key])}</Text>
                </Text>
              ))}
              {/* The broker's own sentence, labelled as its words, after our reason. */}
              {words != null && words !== "" ? (
                <Text
                  testID="trade-approval-broker-words"
                  style={[{ color: colors.foreground }, align]}
                >
                  <Text style={{ fontWeight: "700" }}>{brokerWordsLabel(locale)}</Text>
                  {": "}
                  <Text style={{ writingDirection: "auto" }}>{String(words)}</Text>
                </Text>
              ) : null}
            </EvidenceLine>
          );
        })}
      <ErrorNotice text={error} />
    </View>
  );
}
