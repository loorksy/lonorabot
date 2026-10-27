import type { Agent, Event, Run } from "@lonora/contracts";
import { turnActivity } from "@lonora/core";
import { useState } from "react";
import { Pressable, Text, View } from "react-native";
import type { EventConnection } from "../lib/events";
import { useSession } from "../lib/session";
import { BotAvatar } from "./bot-avatar";
import { NativeSymbol } from "./native-symbol";
import { colors } from "./ui";

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
  const [expanded, setExpanded] = useState(false);
  const activity = turnActivity(run, events);
  const active = ["queued", "leased", "running", "waiting_input", "waiting_takeover"].includes(
    run.status,
  );
  return (
    <View testID={`turn-activity-${run.id}`} style={{ gap: 6, paddingVertical: 6 }}>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ expanded }}
        aria-expanded={expanded}
        accessibilityLabel={t(`activity_${activity.phase}`)}
        onPress={() => setExpanded((value) => !value)}
        style={{
          minHeight: 44,
          flexDirection: rtl ? "row-reverse" : "row",
          gap: 8,
          alignItems: "center",
        }}
      >
        {agent ? (
          <BotAvatar
            color={agent.color}
            identity={agent.name}
            superBot={agent.super_bot_active}
            state={activity.avatar}
            size={24}
          />
        ) : null}
        <Text
          accessibilityLiveRegion="polite"
          style={{
            color: colors.secondary,
            fontSize: 13,
            flex: 1,
            textAlign: rtl ? "right" : "left",
          }}
        >
          {agent?.name ? `${agent.name} · ` : ""}
          {t(`activity_${activity.phase}`)}
          {active && connection !== "connected" ? ` · ${t(connection)}` : ""}
        </Text>
        <NativeSymbol name={expanded ? "close" : "chevron"} size={12} color={colors.secondary} />
      </Pressable>
      {expanded ? (
        <View style={{ gap: 8, paddingHorizontal: 8 }}>
          {activity.observedAt ? (
            <Text style={{ color: colors.secondary, fontSize: 12 }}>
              {new Date(activity.observedAt).toLocaleTimeString(locale)}
            </Text>
          ) : null}
          {activity.calls.map((call) => (
            <View
              key={call.id}
              style={{ flexDirection: rtl ? "row-reverse" : "row", gap: 8, alignItems: "center" }}
            >
              <Text selectable style={{ color: colors.foreground, fontSize: 12, flex: 1 }}>
                {call.name}
              </Text>
              <Text
                style={{
                  color: call.status === "failed" ? colors.error : colors.secondary,
                  fontSize: 12,
                }}
              >
                {t(`activity_call_${call.status}`)}
              </Text>
              {call.completed_at || call.started_at ? (
                <Text style={{ color: colors.secondary, fontSize: 11 }}>
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
