import type { Agent, Artifact, Message } from "@lonora/contracts";
import { Pressable, Text, View } from "react-native";
import { useSession } from "../lib/session";
import { BotAvatar } from "./bot-avatar";
import { colors } from "./ui";

export function MessageBubble({
  message,
  agent,
  files,
  onArtifact,
}: {
  message: Message;
  agent?: Agent;
  files: Artifact[];
  onArtifact: (id: string) => void;
}) {
  const { rtl, locale, t } = useSession();
  const isOwner = message.role === "user";
  return (
    <View
      style={{
        alignSelf: isOwner ? (rtl ? "flex-start" : "flex-end") : "stretch",
        maxWidth: isOwner ? "90%" : "100%",
        backgroundColor: isOwner ? colors.chatUser : "transparent",
        borderRadius: 18,
        padding: isOwner ? 14 : 4,
        gap: 8,
      }}
    >
      <View style={{ flexDirection: rtl ? "row-reverse" : "row", alignItems: "center", gap: 8 }}>
        {agent && !isOwner ? (
          <BotAvatar color={agent.color} variant={agent.avatar} size={24} />
        ) : null}
        <Text style={{ color: colors.secondary, fontSize: 12 }}>
          {isOwner ? t("you") : message.role === "tool" ? t("tool") : (agent?.name ?? t("system"))}
        </Text>
        <Text style={{ color: colors.secondary, fontSize: 11 }}>
          {new Date(message.created_at).toLocaleTimeString(locale, {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </Text>
      </View>
      <Text
        selectable
        style={{
          color: colors.foreground,
          fontSize: message.role === "tool" ? 13 : 16,
          lineHeight: 25,
          writingDirection: "auto",
        }}
      >
        {message.content}
      </Text>
      {message.attachment_ids.map((id) => (
        <Pressable key={id} accessibilityRole="button" onPress={() => onArtifact(id)}>
          <Text style={{ color: colors.secondary, fontSize: 13, writingDirection: "auto" }}>
            ↗ {files.find((file) => file.id === id)?.payload.name ?? t("attach")}
          </Text>
        </Pressable>
      ))}
    </View>
  );
}
