import type { Agent, Event, Run } from "@lonora/contracts";
import { activityCallLabel, isWorking, turnActivity } from "@lonora/core";
import { useState } from "react";
import { Pressable, Text, View } from "react-native";
import type { EventConnection } from "../lib/events";
import { useSession } from "../lib/session";
import { useShellColors } from "../lib/theme";
import { BotAvatar } from "./bot-avatar";
import { NativeSymbol } from "./native-symbol";

/** Observable execution only: no generated reasoning or fabricated tool steps. */
export function TurnActivity({
  run,
  events,
  connection,
  agent,
}: {
  run: Run;
  events: Event[];
  connection: EventConnection;
  agent?: Agent;
}) {
  const { t, rtl, locale } = useSession();
  const shell = useShellColors();
  const [expanded, setExpanded] = useState(false);
  const activity = turnActivity(run, events);
  const reconnecting = isWorking(run.status) && connection !== "connected";
  const needsReply = activity.phase === "waiting_input" || activity.phase === "waiting_external";
  const tint =
    activity.phase === "failed"
      ? shell.error
      : reconnecting || needsReply
        ? shell.warning
        : activity.phase === "completed"
          ? shell.success
          : activity.phase === "cancelled"
            ? shell.secondary
            : shell.foreground;
  const label = reconnecting ? t(connection) : t(`activity_${activity.phase}`);
  const hasDetails = Boolean(activity.calls.length || activity.observedAt);
  return (
    <View
      testID={`turn-activity-${run.id}`}
      style={{
        gap: 10,
        paddingVertical: 7,
        maxWidth: 420,
        width: "100%",
        alignSelf: rtl ? "flex-end" : "flex-start",
      }}
    >
      <Pressable
        accessibilityRole={hasDetails ? "button" : undefined}
        accessibilityState={hasDetails ? { expanded } : undefined}
        aria-expanded={hasDetails ? expanded : undefined}
        accessibilityLabel={`${agent?.name ? `${agent.name} · ` : ""}${label}`}
        disabled={!hasDetails}
        onPress={() => setExpanded((value) => !value)}
        style={({ pressed }) => ({
          minHeight: 64,
          flexDirection: rtl ? "row-reverse" : "row",
          gap: 11,
          alignItems: "center",
          paddingHorizontal: 12,
          paddingVertical: 9,
          borderRadius: 20,
          borderWidth: 1,
          borderColor: tint === shell.foreground ? shell.border : `${tint}44`,
          backgroundColor: pressed ? shell.accent : shell.muted,
        })}
      >
        {agent ? (
          <BotAvatar
            color={agent.color}
            identity={agent.id}
            tradesOnItsOwn={agent.trades_on_its_own}
            state={reconnecting ? "connecting" : activity.avatar}
            size={42}
          />
        ) : null}
        <View style={{ flex: 1, gap: 3, minWidth: 0 }}>
          {agent?.name ? (
            <Text
              numberOfLines={1}
              style={{ color: shell.secondary, fontSize: 11, textAlign: rtl ? "right" : "left" }}
            >
              {agent.name}
            </Text>
          ) : null}
          <View
            style={{
              flexDirection: rtl ? "row-reverse" : "row",
              gap: 7,
              alignItems: "center",
            }}
          >
            <View
              accessible={false}
              style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: tint }}
            />
            <Text
              accessibilityLiveRegion="polite"
              style={{
                color: tint,
                fontSize: 13,
                fontWeight: "600",
                flexShrink: 1,
                textAlign: rtl ? "right" : "left",
              }}
            >
              {label}
            </Text>
          </View>
        </View>
        {hasDetails ? (
          <View style={{ transform: [{ rotate: expanded ? "90deg" : rtl ? "180deg" : "0deg" }] }}>
            <NativeSymbol name="chevron" size={12} color={shell.secondary} />
          </View>
        ) : null}
      </Pressable>
      {expanded && hasDetails ? (
        <View
          style={{
            gap: 10,
            paddingHorizontal: 14,
            paddingVertical: 10,
            borderRadius: 14,
            borderWidth: 1,
            borderColor: shell.border,
          }}
        >
          {activity.observedAt ? (
            <Text style={{ color: shell.secondary, fontSize: 12 }}>
              {new Date(activity.observedAt).toLocaleTimeString(locale)}
            </Text>
          ) : null}
          {activity.calls.map((call) => (
            <View
              key={call.id}
              style={{ flexDirection: rtl ? "row-reverse" : "row", gap: 8, alignItems: "center" }}
            >
              <Text
                testID={`turn-step-${call.name}`}
                style={{ color: shell.foreground, fontSize: 12, flex: 1 }}
              >
                {activityCallLabel(call, locale)}
              </Text>
              <Text
                style={{
                  color: call.status === "failed" ? shell.error : shell.secondary,
                  fontSize: 12,
                }}
              >
                {t(`activity_call_${call.status}`)}
              </Text>
              {call.completed_at || call.started_at ? (
                <Text style={{ color: shell.secondary, fontSize: 11 }}>
                  {new Date(call.completed_at ?? (call.started_at as string)).toLocaleTimeString(
                    locale,
                  )}
                </Text>
              ) : null}
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}
