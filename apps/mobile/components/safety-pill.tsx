// The thread header's status pill and its sheet, the same projection and text as Web.
import type { Resource, TradingReadiness } from "@lonora/contracts";
import {
  isolate,
  operationStatusText,
  readinessTime,
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
import { colors } from "./ui";

/**
 * The header's one status pill and its sheet. The thread screen reads the agent's live
 * state once (``useAgentLiveState``) and passes its readiness here.
 */
export function SafetyPill({ readiness }: { readiness: TradingReadiness | null }) {
  const { locale, rtl, t } = useSession();
  const [open, setOpen] = useState(false);
  const [accounts, setAccounts] = useState<Resource[]>([]);
  const text = tradingSafetyText(locale);
  // With more than one account the line and the sheet name the account of each item.
  const trading = readiness !== null;
  useEffect(() => {
    if (!open && !trading) return;
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
  }, [open, trading]);
  if (!readiness) return null;
  const several = accounts.length > 1;
  const accountName = (id: string) => {
    if (!several) return null;
    const index = accounts.findIndex((row) => row.id === id);
    return index < 0 ? null : brokerIdentityLabel(accounts[index], index, t);
  };
  const line = tradingReadinessLine(readiness, locale, new Date(), accountName);
  const tone = tradingReadinessTone(readiness);
  const tint =
    tone === "ready" ? colors.success : tone === "held" ? colors.warning : colors.secondary;
  const align = rtl ? "right" : "left";
  const body = { color: colors.foreground, fontSize: 14, textAlign: align } as const;
  const muted = { ...body, color: colors.secondary, fontSize: 13 } as const;
  const heading = { ...body, fontWeight: "600", fontSize: 15 } as const;
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
              <Text style={heading}>{text.level}</Text>
              <Text style={body}>{text[readiness.level]}</Text>
              {readiness.grants.map((grant) => (
                <Text key={`${grant.account_id}:${grant.symbols.join(",")}`} style={body}>
                  {[
                    grant.full_delegation ? text.fullDelegation : text.grants,
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
