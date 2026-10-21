import { Pressable, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useSession } from "../lib/session";
import { useVoiceSession } from "../lib/voice-session";
import { BotAvatar } from "./bot-avatar";
import { HeaderButton } from "./header-button";
import { NativeSymbol } from "./native-symbol";
import { TradeApprovalCard } from "./trade-approval";
import { colors, ErrorNotice } from "./ui";

export function VoiceOverlay() {
  const call = useVoiceSession();
  const { t, rtl } = useSession();
  const insets = useSafeAreaInsets();
  if (!call.origin)
    return call.error ? (
      <View
        style={{
          position: "absolute",
          top: insets.top + 8,
          left: 12,
          right: 12,
          zIndex: 100,
          backgroundColor: colors.accent,
          borderRadius: 22,
          padding: 12,
        }}
      >
        <ErrorNotice text={call.error} />
        <HeaderButton label={t("close")} onPress={call.dismissError}>
          <NativeSymbol name="close" />
        </HeaderButton>
      </View>
    ) : null;
  const agent = call.origin.agent;
  if (call.minimized)
    return (
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={t("reopenCall")}
        onPress={() => call.minimize(false)}
        style={{
          position: "absolute",
          top: insets.top + 6,
          alignSelf: "center",
          zIndex: 100,
          borderRadius: 40,
          backgroundColor: colors.accent,
          borderColor: colors.border,
          borderWidth: 1,
          padding: 8,
          flexDirection: rtl ? "row-reverse" : "row",
          alignItems: "center",
          gap: 10,
        }}
      >
        <BotAvatar
          superBot={agent.super_bot_active}
          identity={agent.name}
          variant={agent.avatar}
          color={agent.color}
          size={28}
          working={call.connected}
        />
        <Text style={{ color: colors.foreground, fontWeight: "600" }}>{agent.name}</Text>
        <NativeSymbol name="call" size={19} />
      </Pressable>
    );
  const approvals = call.approvals.slice(-5);
  return (
    <View
      style={{
        position: "absolute",
        left: 12,
        right: 12,
        bottom: insets.bottom + 90,
        zIndex: 100,
        maxHeight: "75%",
        borderRadius: 32,
        borderWidth: 1,
        borderColor: colors.border,
        backgroundColor: colors.accent,
        padding: 14,
        gap: 10,
      }}
    >
      <View style={{ flexDirection: rtl ? "row-reverse" : "row", alignItems: "center", gap: 10 }}>
        <View
          accessibilityLabel={
            call.connected
              ? t(call.activity.phase === "speaking" ? "callSpeaking" : "callListening")
              : t("connecting")
          }
          style={{ transform: [{ scale: 1 + call.activity.level * 0.12 }] }}
        >
          <BotAvatar
            superBot={agent.super_bot_active}
            identity={agent.name}
            variant={agent.avatar}
            color={agent.color}
            size={52}
            working={call.activity.phase === "speaking" || call.activity.level > 0.04}
          />
        </View>
        <View
          style={{
            flex: 1,
            flexDirection: "row",
            alignItems: "center",
            justifyContent: "center",
            gap: 3,
            height: 38,
          }}
        >
          {[0.3, 0.7, 0.5, 1, 0.6, 0.85, 0.4].map((factor, index) => (
            <View
              key={String(index)}
              style={{
                width: 4,
                borderRadius: 4,
                height: 4 + call.activity.level * factor * 30,
                backgroundColor: agent.color,
              }}
            />
          ))}
        </View>
        <HeaderButton label={t(call.muted ? "unmuteCall" : "muteCall")} onPress={call.toggleMuted}>
          <NativeSymbol name={call.muted ? "mic-off" : "mic"} />
        </HeaderButton>
        <HeaderButton label={t("endCall")} onPress={() => void call.end()}>
          <NativeSymbol name="close" color={colors.error} size={24} />
        </HeaderButton>
        <HeaderButton label={t("minimizeCall")} onPress={() => call.minimize(true)}>
          <NativeSymbol name="minimize" size={20} />
        </HeaderButton>
      </View>
      <ErrorNotice text={call.error} />
      {approvals.length ? (
        <ScrollView style={{ maxHeight: 300 }} contentContainerStyle={{ gap: 10 }}>
          {approvals.map((row) => (
            <TradeApprovalCard key={row.id} row={row} onChange={call.updateApproval} />
          ))}
        </ScrollView>
      ) : null}
    </View>
  );
}
