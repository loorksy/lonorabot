import type { Agent, OwnerAction, TradingMode } from "@lonora/contracts";
import {
  mandateLine,
  modeChangeLine,
  ownerActionText,
  showsTradingControl,
  tradingSubLine,
} from "@lonora/core";
import { useEffect, useState } from "react";
import { Modal, Pressable, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { api } from "../lib/api";
import { agentShowingMandate, otherTradingMode } from "../lib/mandate-mode";
import { useSession } from "../lib/session";
import { SettingsGroup, SettingsRow } from "./settings-group";
import { Icon } from "./shell/icon";
import { useToast } from "./shell/toast";
import { colors } from "./ui";

type Props = {
  agent: Agent;
  hasTradingAccount?: boolean;
  settings?: boolean;
  /** The parent stores this mode on the agent. The control reads that field. */
  onMode?: (mode: TradingMode) => void;
};

/** The Mandate control. No connected account: nothing (Q9). Drafts grant nothing. */
export function AgentPermissions(props: Props) {
  const { owner } = useSession();
  if (
    !owner ||
    !showsTradingControl({ ...props.agent, hasTradingAccount: props.hasTradingAccount })
  )
    return null;
  return <ModeControl key={`${owner.id}:${props.agent.id}`} {...props} />;
}

function ModeControl({ agent, settings = false, onMode }: Props) {
  const { rtl, errorText } = useSession();
  const insets = useSafeAreaInsets();
  const toast = useToast();
  const locale = rtl ? "ar" : "en";
  const words = ownerActionText(locale);
  const [open, setOpen] = useState(false);
  const [card, setCard] = useState<OwnerAction | null>();
  const [busy, setBusy] = useState(false);
  const mode: TradingMode | null =
    agent.trading_mode === "full" || agent.trading_mode === "ask" ? agent.trading_mode : null;
  const other = otherTradingMode(mode);
  useEffect(() => {
    if (!open) return;
    let live = true;
    void api
      .get<OwnerAction | null>(`/owner-actions/mandate?agent_id=${encodeURIComponent(agent.id)}`)
      .then((row) => live && setCard(row))
      .catch(() => live && setCard(null));
    return () => {
      live = false;
    };
  }, [agent.id, open]);
  const showCard = async () => {
    setBusy(true);
    try {
      setCard(
        await api.post<OwnerAction>(
          `/owner-actions/mandate?agent_id=${encodeURIComponent(agent.id)}`,
          {},
        ),
      );
    } catch (reason) {
      toast(errorText(reason), { type: "error" });
    } finally {
      setBusy(false);
    }
  };
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
      <View
        accessibilityViewIsModal
        style={{
          flex: 1,
          backgroundColor: colors.background,
          paddingTop: insets.top + 20,
          paddingLeft: insets.left + 20,
          paddingRight: insets.right + 20,
          paddingBottom: insets.bottom + 20,
          gap: 12,
        }}
      >
        <Text
          accessibilityRole="header"
          style={{ color: colors.foreground, fontSize: 18, textAlign: rtl ? "right" : "left" }}
        >
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
            <Text
              style={{ color: colors.foreground, fontSize: 17, textAlign: rtl ? "right" : "left" }}
            >
              {other === "full" ? words.modeFull : words.modeAsk}
            </Text>
          </Pressable>
        ) : other && card === null ? (
          <Pressable
            accessibilityRole="button"
            disabled={busy}
            onPress={() => void showCard()}
            style={{ minHeight: 44, justifyContent: "center" }}
          >
            <Text style={{ color: colors.foreground, textAlign: rtl ? "right" : "left" }}>
              {words.mandateRequest}
            </Text>
          </Pressable>
        ) : null}
        <Pressable
          accessibilityRole="button"
          onPress={() => setOpen(false)}
          style={{ minHeight: 44, justifyContent: "center" }}
        >
          <Text style={{ color: colors.secondary, textAlign: rtl ? "right" : "left" }}>
            {rtl ? "إغلاق" : "Close"}
          </Text>
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
        style={{
          minHeight: 44,
          flexDirection: rtl ? "row-reverse" : "row",
          alignItems: "center",
          gap: 4,
          paddingHorizontal: 6,
        }}
      >
        <Icon name={mode === "full" ? "alert" : "shield"} size={14} color={colors.secondary} />
        <Text numberOfLines={1} style={{ color: colors.foreground }}>
          {mode === "full" ? words.modeFull : mode === "ask" ? words.modeAsk : "…"}
        </Text>
      </Pressable>
      {sheet}
    </>
  );
}
