// The thread header's safety pill and its sheet, the same projection and text as Web.
import type { Agent, Resource, TradingControls, TradingReadiness } from "@lonora/contracts";
import {
  isolate,
  moneyLimitsLine,
  operationStatusText,
  pauseClassLabel,
  readinessTime,
  tradingBrake,
  tradingReadinessLine,
  tradingReadinessTone,
  tradingSafetyText,
} from "@lonora/core";
import { useEffect, useState } from "react";
import { Modal, Pressable, ScrollView, Text, View } from "react-native";
import { api } from "../lib/api";
import { brokerIdentityLabel } from "../lib/broker-identity";
import { useSession } from "../lib/session";
import { NativeSymbol } from "./native-symbol";
import { Button, colors, ErrorNotice } from "./ui";

/** One brake for every agent and the owner's manual orders; exits stay allowed. */
export const stopNewTrading: TradingControls = { enabled: false, emergency_stop: true };
/** One tap, no passkey: it widens no authority. */
export const resumeTrading: TradingControls = { enabled: true, emergency_stop: false };

/**
 * The header's one safety pill and its sheet. The thread screen reads the agent's live
 * state once (``useAgentLiveState``) and passes its readiness here; a brake change
 * refreshes that one read.
 */
export function SafetyPill({
  readiness,
  agents,
  onChanged,
}: {
  readiness: TradingReadiness | null;
  agents: Agent[];
  onChanged: () => Promise<void>;
}) {
  const { locale, rtl, errorText, t } = useSession();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [accounts, setAccounts] = useState<Resource[]>([]);
  const text = tradingSafetyText(locale);
  // With more than one account the line and the sheet name the account of each item.
  const accountIds = new Set(
    readiness
      ? [
          ...readiness.money_limits.map((item) => item.account_id),
          ...readiness.grants.map((item) => item.account_id),
          ...readiness.restrictions.map((item) => item.account_id),
          ...readiness.unresolved_operations.map((item) => item.account_id),
        ]
      : [],
  );
  const several = accountIds.size > 1;
  useEffect(() => {
    if (!open && !several) return;
    let live = true;
    void api
      .get<Resource[]>("/trading/connections")
      .then((rows) => {
        if (live) setAccounts(rows);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [open, several]);
  if (!readiness) return null;
  const accountName = (id: string) => {
    if (!several) return null;
    const index = accounts.findIndex((row) => row.id === id);
    return index < 0 ? null : brokerIdentityLabel(accounts[index], index, t);
  };
  const agentName = (id: string | null) => {
    const name = agents.find((agent) => agent.id === id)?.name;
    return name ? `${text.setByAgent} · ${isolate(name)}` : text.setByAgent;
  };
  const line = tradingReadinessLine(readiness, locale, new Date(), accountName);
  const tone = tradingReadinessTone(readiness);
  const tint =
    tone === "ready" ? colors.success : tone === "held" ? colors.warning : colors.secondary;
  const brake = tradingBrake(readiness.global_trading, locale);
  const align = rtl ? "right" : "left";
  const body = { color: colors.foreground, fontSize: 14, textAlign: align } as const;
  const muted = { ...body, color: colors.secondary, fontSize: 13 } as const;
  const heading = { ...body, fontWeight: "600", fontSize: 15 } as const;
  const change = async (controls: TradingControls) => {
    setBusy(true);
    try {
      await api.put<TradingControls>("/trading/controls", controls);
      setError(null);
      await onChanged();
    } catch (caught) {
      setError(errorText(caught));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${text.open}: ${line}`}
        testID="safety-pill"
        onPress={() => setOpen(true)}
        style={({ pressed }) => ({
          alignSelf: "center",
          flexDirection: rtl ? "row-reverse" : "row",
          alignItems: "center",
          gap: 6,
          maxWidth: "92%",
          minHeight: 30,
          marginTop: -2,
          marginBottom: 6,
          paddingHorizontal: 10,
          paddingVertical: 5,
          borderRadius: 15,
          borderWidth: 1,
          borderColor: `${tint}55`,
          backgroundColor: pressed ? colors.accent : colors.muted,
        })}
      >
        <View
          accessible={false}
          style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: tint }}
        />
        <Text
          numberOfLines={1}
          style={{ color: colors.foreground, fontSize: 12, flexShrink: 1, textAlign: align }}
        >
          {line}
        </Text>
      </Pressable>
      <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
        <View
          style={{
            flex: 1,
            backgroundColor: colors.overlay,
            justifyContent: "flex-end",
            padding: 12,
          }}
        >
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={text.close}
            onPress={() => setOpen(false)}
            style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0 }}
          />
          <View
            testID="safety-sheet"
            accessibilityViewIsModal
            style={{
              maxHeight: "86%",
              borderRadius: 18,
              backgroundColor: colors.accent,
              overflow: "hidden",
            }}
          >
            <ScrollView contentContainerStyle={{ padding: 18, gap: 10 }}>
              <View
                style={{
                  flexDirection: rtl ? "row-reverse" : "row",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}
              >
                <Text accessibilityRole="header" style={{ ...heading, fontSize: 17 }}>
                  {text.title}
                </Text>
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={text.close}
                  hitSlop={8}
                  onPress={() => setOpen(false)}
                >
                  <NativeSymbol name="close" size={20} />
                </Pressable>
              </View>
              <Text style={body}>{line}</Text>
              <Text style={heading} testID="safety-trading-state">
                {brake.status}
                {readiness.global_trading.since
                  ? ` · ${text.since} ${readinessTime(readiness.global_trading.since, locale)}`
                  : ""}
              </Text>
              <Text style={muted}>{brake.hint}</Text>
              <Button
                label={brake.action}
                secondary={!brake.stopped}
                disabled={busy}
                onPress={() => void change(brake.stopped ? resumeTrading : stopNewTrading)}
              />
              <ErrorNotice text={error} />
              <Text style={heading}>{text.level}</Text>
              <Text style={body}>{text[readiness.level]}</Text>
              {readiness.grants.map((grant) => (
                <Text key={`${grant.account_id}:${grant.symbols.join(",")}`} style={body}>
                  {[
                    text.grants,
                    accountName(grant.account_id),
                    grant.symbol_scope === "account"
                      ? text.allPairs
                      : grant.symbols.map(isolate).join(rtl ? "، " : ", "),
                    grant.valid_until
                      ? `${text.until} ${readinessTime(grant.valid_until, locale)}`
                      : text.untilStopped,
                    grant.allow_manual_positions ? text.manualIncluded : text.manualExcluded,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </Text>
              ))}
              <Text style={heading}>{text.pauses}</Text>
              {readiness.restrictions.length ? (
                readiness.restrictions.map((item) => (
                  <Text key={item.id} style={body}>
                    {[
                      accountName(item.account_id),
                      pauseClassLabel(item.action_class, locale),
                      item.symbol ? isolate(item.symbol) : text.allPairs,
                      item.applies_to === "all_agents" ? text.allAgents : text.thisAgent,
                      item.includes_owner_manual ? text.includesManual : null,
                      item.source === "owner_ui"
                        ? text.setByYou
                        : item.source === "owner_message"
                          ? text.fromYourMessage
                          : agentName(item.created_by_agent_id),
                      item.state === "scheduled"
                        ? `${text.starts} ${readinessTime(item.valid_from, locale)}`
                        : item.valid_until
                          ? `${text.until} ${readinessTime(item.valid_until, locale)}`
                          : text.noEnd,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </Text>
                ))
              ) : (
                <Text style={muted}>{text.noPauses}</Text>
              )}
              {readiness.restrictions.length ? <Text style={muted}>{text.onlyYouLift}</Text> : null}
              {!readiness.exits_allowed && (
                <Text style={{ ...body, color: colors.warning }}>{text.exitsFrozen}</Text>
              )}
              <Text style={heading}>{text.moneyLimits}</Text>
              {readiness.money_limits.map((limits) => (
                <Text key={limits.account_id} style={body}>
                  {[accountName(limits.account_id), moneyLimitsLine(limits, locale)]
                    .filter(Boolean)
                    .join(" · ")}
                </Text>
              ))}
              <Text style={heading}>{text.unresolved}</Text>
              {readiness.unresolved_operations.length ? (
                <>
                  {readiness.unresolved_operations.map((operation) => (
                    <Text key={operation.operation_id} style={body}>
                      {[
                        accountName(operation.account_id),
                        isolate(operation.symbol),
                        operationStatusText(operation.status, {}, locale),
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </Text>
                  ))}
                  <Text style={muted}>{text.uncertainHint}</Text>
                </>
              ) : (
                <Text style={muted}>{text.noUnresolved}</Text>
              )}
            </ScrollView>
          </View>
        </View>
      </Modal>
    </>
  );
}
