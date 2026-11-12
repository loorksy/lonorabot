// The order line and its sheet, as on Web (Cards.tsx OrderLine / OrderSheetBody): one line per
// financial operation of the chat with its durable state from packages/core (orderLineState):
// «منفَّذ» only with evidence. A tap opens the sheet: the timeline, the evidence and, for an
// operation with no answer, «حسم العملية» to its own settle card.
import type { Journal } from "@lonora/contracts";
import {
  financialBoundaryError,
  type OrderLineState,
  orderLineAction,
  orderLineState,
  orderLineText,
} from "@lonora/core";
import { Pressable, Text, View } from "react-native";
import { fill } from "../lib/i18n";
import { useSession } from "../lib/session";
import { useTheme } from "../lib/theme";
import { Icon, type IconName } from "./shell/icon";
import { Btn } from "./shell/kit";

const TONE: Record<OrderLineState, "wait" | "ok" | "bad" | "off" | "warn"> = {
  requested: "wait",
  sent: "wait",
  accepted: "wait",
  partial: "ok",
  filled: "ok",
  rejected: "bad",
  cancelled: "off",
  blocked: "off",
  uncertain: "warn",
};
function useToneColor() {
  const { c } = useTheme();
  return (tone: (typeof TONE)[OrderLineState]) =>
    tone === "ok" ? c.accent : tone === "bad" ? c.red : tone === "warn" ? c.amber : c.muted;
}

export function OrderLine({ row, onOpen }: { row: Journal; onOpen: (row: Journal) => void }) {
  const { c } = useTheme();
  const { rtl, locale, t } = useSession();
  const color = useToneColor();
  const line = orderLineState(row);
  const action = orderLineAction(row.request, locale);
  const symbol = String(row.request.symbol ?? "");
  const limit = row.request.price != null ? String(row.request.price) : null;
  const summary = `${action.label}${action.volume ? ` ${action.volume}` : ""} ${symbol}`;
  const stateText = orderLineText(line.state, locale);
  const icon: IconName =
    action.direction === "down" ? "trend" : action.direction === "up" ? "trend" : "edit";
  return (
    <Pressable
      testID="order-line"
      accessibilityRole="button"
      accessibilityLabel={fill(t("odOpen"), summary, stateText)}
      onPress={() => onOpen(row)}
      style={{
        flexDirection: rtl ? "row-reverse" : "row",
        alignItems: "center",
        gap: 10,
        padding: 12,
        borderRadius: 14,
        borderWidth: 1,
        borderColor: c.line,
        backgroundColor: c.surface,
      }}
    >
      <View
        style={{ transform: action.direction === "down" ? [{ scaleY: -1 }] : [] }}
        accessible={false}
      >
        <Icon name={icon} size={20} color={c.muted} />
      </View>
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text
          numberOfLines={1}
          style={{
            color: c.text,
            fontSize: 14,
            fontWeight: "700",
            textAlign: rtl ? "right" : "left",
          }}
        >
          {action.label}
          {action.volume ? ` ${action.volume}` : ""} {symbol}
        </Text>
        <Text
          numberOfLines={1}
          style={{ color: c.muted, fontSize: 12, textAlign: rtl ? "right" : "left" }}
        >
          {limit ? `${t("odLimitAt")} ${limit}` : action.direction ? t("odAtMarket") : ""}
          {line.fill_price ? ` · ${line.fill_price}` : ""}
        </Text>
      </View>
      <Text
        testID="order-state"
        style={{ color: color(TONE[line.state]), fontSize: 12, fontWeight: "700" }}
      >
        {stateText}
      </Text>
    </Pressable>
  );
}

/**
 * The order sheet: the timeline, the evidence and, with no answer from the broker, the way to
 * its settle card. Raw operation and account ids are not shown (mandate 17).
 */
export function OrderSheet({ row, onResolve }: { row: Journal; onResolve?: () => void }) {
  const { c } = useTheme();
  const { rtl, locale, t } = useSession();
  const color = useToneColor();
  const line = orderLineState(row);
  const state = line.state;
  const ladder: OrderLineState[] = ["requested", "sent", "accepted", "filled"];
  const final = ["filled", "partial", "rejected", "cancelled", "blocked", "uncertain"];
  const next = final.includes(state) ? [] : ladder.slice(ladder.indexOf(state) + 1);
  const time = (iso?: string | null) =>
    iso ? new Date(iso).toLocaleTimeString("en-GB", { hour12: false }) : "…";
  const code = row.result?.code ? String(row.result.code) : null;
  const details = (row.result?.details ?? {}) as Record<string, unknown>;
  // A rejection or a block names its own reason; never a generic "try again" on money.
  const reason =
    financialBoundaryError(code, locale) ??
    (typeof details.description === "string" && details.description ? details.description : null);
  const evidence =
    state === "filled" || state === "partial"
      ? line.evidence === "owner"
        ? t("odOwnerEvidence")
        : [
            `${t("odFillEvidence")} ${line.ticket ?? "—"}`,
            line.fill_price,
            state === "partial" && line.filled_volume
              ? `${line.filled_volume}/${line.requested_volume ?? "?"}`
              : null,
          ]
            .filter(Boolean)
            .join(" · ")
      : state === "uncertain"
        ? t("odUncertain")
        : state === "rejected"
          ? [t("odRejected"), reason].filter(Boolean).join(" · ")
          : state === "cancelled" || state === "blocked"
            ? line.not_sent
              ? [t("odNotSent"), reason].filter(Boolean).join(" · ")
              : orderLineText("cancelled", locale)
            : t("odWaiting");
  const align = rtl ? "right" : "left";
  const step = (name: OrderLineState, done: boolean) => (
    <View
      key={name}
      style={{ flexDirection: rtl ? "row-reverse" : "row", alignItems: "center", gap: 10 }}
    >
      <View
        style={{
          width: 10,
          height: 10,
          borderRadius: 5,
          backgroundColor: done ? color(TONE[name]) : "transparent",
          borderWidth: 1.5,
          borderColor: done ? color(TONE[name]) : c.line,
        }}
      />
      <Text style={{ flex: 1, color: done ? c.text : c.muted, fontSize: 14, textAlign: align }}>
        {orderLineText(name, locale)}
      </Text>
      <Text style={{ color: c.muted, fontSize: 12 }}>
        {!done
          ? "…"
          : name === "uncertain"
            ? t("odNoAnswer")
            : time(name === "requested" ? row.submitted_at : row.updated_at)}
      </Text>
    </View>
  );
  return (
    <View style={{ gap: 14 }} testID="order-sheet">
      <View style={{ gap: 10 }}>
        {line.steps.map((name) => step(name, true))}
        {next.map((name) => step(name, false))}
      </View>
      <Text
        testID="order-evidence"
        style={{ color: color(TONE[state]), fontSize: 14, lineHeight: 21, textAlign: align }}
      >
        {evidence}
      </Text>
      {state === "uncertain" && onResolve ? (
        <Btn label={t("odResolve")} onPress={onResolve} />
      ) : null}
    </View>
  );
}
