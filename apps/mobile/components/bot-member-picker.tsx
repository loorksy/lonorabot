// Native member list adapted from the template; membership remains server-owned.
import type { Agent } from "@lonora/contracts";
import { StyleSheet, Switch, Text, View } from "react-native";
import { useSession } from "../lib/session";
import { BotAvatar } from "./bot-avatar";
import { colors } from "./ui";
export function BotMemberPicker({
  agents,
  selected,
  onChange,
  disabled = false,
}: {
  agents: Agent[];
  selected: string[];
  onChange: (ids: string[]) => void;
  disabled?: boolean;
}) {
  const { rtl } = useSession();
  return (
    <View style={{ borderRadius: 16, backgroundColor: colors.muted, overflow: "hidden" }}>
      {agents.map((agent, index) => {
        const checked = selected.includes(agent.id);
        return (
          <View
            key={agent.id}
            style={{
              flexDirection: rtl ? "row-reverse" : "row",
              padding: 14,
              alignItems: "center",
              gap: 12,
              borderTopWidth: index ? StyleSheet.hairlineWidth : 0,
              borderTopColor: colors.border,
              opacity: disabled ? 0.5 : 1,
            }}
          >
            <BotAvatar
              superBot={agent.super_bot_active}
              identity={agent.name}
              color={agent.color}
              variant={agent.avatar}
              size={36}
            />
            <View style={{ flex: 1, gap: 3 }}>
              <Text
                style={{
                  color: colors.foreground,
                  fontSize: 17,
                  textAlign: rtl ? "right" : "left",
                }}
              >
                {agent.name}
              </Text>
              {agent.title ? (
                <Text
                  numberOfLines={1}
                  style={{
                    color: colors.secondary,
                    fontSize: 13,
                    textAlign: rtl ? "right" : "left",
                  }}
                >
                  {agent.title}
                </Text>
              ) : null}
            </View>
            <Switch
              accessibilityLabel={agent.name}
              value={checked}
              disabled={disabled || (!checked && selected.length >= 12)}
              onValueChange={(enabled) =>
                onChange(
                  enabled ? [...selected, agent.id] : selected.filter((id) => id !== agent.id),
                )
              }
              trackColor={{ true: "#8d7bff" }}
            />
          </View>
        );
      })}
    </View>
  );
}
