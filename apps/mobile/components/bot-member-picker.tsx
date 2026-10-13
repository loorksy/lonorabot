// Native member list adapted from the template; membership remains server-owned.
import type { Agent } from "@lonora/contracts";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useSession } from "../lib/session";
import { BotAvatar } from "./bot-avatar";
import { NativeSymbol } from "./native-symbol";
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
          <Pressable
            key={agent.id}
            accessibilityRole="checkbox"
            accessibilityLabel={agent.name}
            accessibilityState={{ checked, disabled }}
            disabled={disabled}
            onPress={() =>
              onChange(
                checked
                  ? selected.filter((id) => id !== agent.id)
                  : selected.length < 12
                    ? [...selected, agent.id]
                    : selected,
              )
            }
            style={({ pressed }) => ({
              flexDirection: rtl ? "row-reverse" : "row",
              padding: 14,
              alignItems: "center",
              gap: 12,
              borderTopWidth: index ? StyleSheet.hairlineWidth : 0,
              borderTopColor: colors.border,
              backgroundColor: pressed ? colors.accent : "transparent",
              opacity: disabled ? 0.5 : 1,
            })}
          >
            <BotAvatar identity={agent.name} color={agent.color} variant={agent.avatar} size={36} />
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
            <View
              style={{
                width: 23,
                height: 23,
                borderRadius: 12,
                borderWidth: checked ? 0 : 1,
                borderColor: colors.secondary,
                backgroundColor: checked ? colors.primary : "transparent",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              {checked ? (
                <NativeSymbol name="check" size={15} color={colors.primaryForeground} />
              ) : null}
            </View>
          </Pressable>
        );
      })}
    </View>
  );
}
