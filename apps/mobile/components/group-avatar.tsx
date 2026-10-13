// Adapted from Tampletgrok apps/mobile/components/group-avatar.tsx (Apache-2.0); see NOTICE.

import type { Agent } from "@lonora/contracts";
import { Text, View, type ViewStyle } from "react-native";
import { BotAvatar } from "./bot-avatar";
import { NativeSymbol } from "./native-symbol";
import { colors } from "./ui";

export function GroupAvatar({ members, size = 54 }: { members: Agent[]; size?: number }) {
  if (!members.length)
    return (
      <View
        style={{
          width: size,
          height: size,
          borderRadius: size / 2,
          alignItems: "center",
          justifyContent: "center",
          backgroundColor: colors.accent,
        }}
      >
        <NativeSymbol name="group" size={size * 0.4} color={colors.secondary} />
      </View>
    );
  if (members.length === 1)
    return (
      <BotAvatar
        identity={members[0].name}
        color={members[0].color}
        variant={members[0].avatar}
        size={size}
      />
    );
  const pair = members.length === 2;
  const miniSize = Math.round(size * (pair ? 0.65 : 0.54));
  const positions: ViewStyle[] = pair
    ? [
        { top: 0, left: 0 },
        { right: 0, bottom: 0 },
      ]
    : [
        { top: 0, left: (size - miniSize) / 2 },
        { bottom: 0, left: 0 },
        { right: 0, bottom: 0 },
      ];
  return (
    <View style={{ width: size, height: size }}>
      {members.slice(0, members.length > 3 ? 2 : 3).map((member, index) => (
        <View
          key={member.id}
          style={{ position: "absolute", ...positions[index], zIndex: index + 1 }}
        >
          <BotAvatar
            identity={member.name}
            color={member.color}
            variant={member.avatar}
            size={miniSize}
          />
        </View>
      ))}
      {members.length > 3 ? (
        <View
          style={{
            position: "absolute",
            right: 0,
            bottom: 0,
            zIndex: 3,
            width: miniSize,
            height: miniSize,
            borderRadius: miniSize / 2,
            backgroundColor: colors.accent,
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Text style={{ color: colors.foreground, fontSize: 11 }}>+{members.length - 2}</Text>
        </View>
      ) : null}
    </View>
  );
}
