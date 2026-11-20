import type { Agent, OwnerAction, PermissionState, TradingMode } from "@lonora/contracts";
import { mandateLine, modeChangeLine, ownerActionText, tradingSubLine } from "@lonora/core";
import { useEffect, useState } from "react";
import { Modal, Pressable, Text, View } from "react-native";
import { api } from "../lib/api";
import { agentShowingMandate, otherTradingMode } from "../lib/mandate-mode";
import { useSession } from "../lib/session";
import { SettingsGroup, SettingsRow } from "./settings-group";
import { useToast } from "./shell/toast";
import { colors } from "./ui";

type Props = {
  agent: Agent;
  threadId?: string;
  revision?: number;
  settings?: boolean;
  pendingTrade?: boolean;
  onState?: (state: PermissionState | null) => void;
  /** The parent stores this mode on the agent. The control reads that field. */
  onMode?: (mode: TradingMode) => void;
};

/** The Mandate control. No connected account: nothing (Q9). Drafts grant nothing. */
export function AgentPermissions(props: Props) {
  const { owner } = useSession();
  if (!owner || props.agent.role === "delegated") return null;
  if (!props.agent.trading_account_id) return null;
  return <ModeControl key={`${owner.id}:${props.agent.id}:${props.revision ?? 0}`} {...props} />;
}

function ModeControl({ agent, settings = false, onState, onMode }: Props) {
  const { rtl, errorText } = useSession();
  const toast = useToast();
  const locale = rtl ? "ar" : "en";
  const words = ownerActionText(locale);
  const [open, setOpen] = useState(false);
  const [card, setCard] = useState<OwnerAction | null>(null);
  const [busy, setBusy] = useState(false);
  const mode: TradingMode | null =
    agent.trading_mode === "full" || agent.trading_mode === "ask" ? agent.trading_mode : null;
  const other = otherTradingMode(mode);
  useEffect(() => {
    let live = true;
    void api
      .get<PermissionState>(`/agents/${encodeURIComponent(agent.id)}/permissions`)
      .then((row) => live && onState?.(row))
      .catch(() => live && onState?.(null));
    void api
      .get<OwnerAction | null>(`/owner-actions/mandate?agent_id=${encodeURIComponent(agent.id)}`)
      .then((row) => live && setCard(row))
      .catch(() => live && setCard(null));
    return () => {
      live = false;
    };
  }, [agent.id, onState]);
  const apply = async (next: TradingMode) => {
    if (!card || busy) return;
    setBusy(true);
    try {
      const updated = await api.post<OwnerAction>(
        `/owner-actions/${encodeURIComponent(card.id)}/decision`,
        { decision: "confirm", trading_mode: next },
      );
      const shown = agentShowingMandate(agent, updated.result);
      toast(modeChangeLine(agent.name, shown.trading_mode, updated.result.withdrawn ?? 0, locale), {
        type: "success",
      });
      onMode?.(shown.trading_mode);
      setOpen(false);
    } catch (reason) {
      toast(errorText(reason), { type: "error" });
    } finally {
      setBusy(false);
    }
  };
  const line = mandateLine(mode, locale);
  const sub = tradingSubLine(0, mode, locale);
  const sheet = (
    <Modal visible={open} animationType="slide" onRequestClose={() => setOpen(false)}>
      <View style={{ flex: 1, backgroundColor: colors.background, padding: 20, gap: 12 }}>
        <Text style={{ color: colors.foreground, fontSize: 18, textAlign: rtl ? "right" : "left" }}>
          {words.mandateTitle} · {agent.name}
        </Text>
        {mode && (
          <Text style={{ color: colors.foreground, textAlign: rtl ? "right" : "left" }}>
            {words.mandateNow}: {mode === "full" ? words.modeFull : words.modeAsk}
          </Text>
        )}
        {mode && (
          <Text style={{ color: colors.secondary, textAlign: rtl ? "right" : "left" }}>
            {mode === "full" ? words.modeFullLine : words.modeAskLine}
          </Text>
        )}
        {other && card ? (
          <Pressable
            accessibilityRole="button"
            disabled={busy}
            onPress={() => void apply(other)}
            style={{ minHeight: 44, justifyContent: "center" }}
          >
            <Text style={{ color: colors.foreground, fontSize: 17 }}>
              {other === "full" ? words.modeFull : words.modeAsk}
            </Text>
          </Pressable>
        ) : (
          <Text style={{ color: colors.secondary, textAlign: rtl ? "right" : "left" }}>
            {rtl ? "لا توجد بطاقة تفويض لهذا الوكيل بعد." : "This agent has no Mandate card yet."}
          </Text>
        )}
        <Pressable accessibilityRole="button" onPress={() => setOpen(false)}>
          <Text style={{ color: colors.secondary }}>{rtl ? "إغلاق" : "Close"}</Text>
        </Pressable>
      </View>
    </Modal>
  );
  if (settings)
    return (
      <SettingsGroup title={rtl ? "التداول" : "Trading"}>
        <SettingsRow
          title={line ?? (rtl ? "التفويض غير معروف" : "Trading mode unknown")}
          detail={sub ?? undefined}
          onPress={() => setOpen(true)}
          testID="mandate-settings-row"
        />
        {sheet}
      </SettingsGroup>
    );
  return (
    <>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={line ?? undefined}
        testID="permission-chip"
        onPress={() => setOpen(true)}
        style={{ minHeight: 44, justifyContent: "center", paddingHorizontal: 8 }}
      >
        <Text style={{ color: colors.foreground }}>
          {mode === "full" ? words.modeFull : mode === "ask" ? words.modeAsk : "…"}
        </Text>
      </Pressable>
      {sheet}
    </>
  );
}
