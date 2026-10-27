import type { Agent, Artifact, Message } from "@lonora/contracts";
import { validateRichContent } from "@lonora/core";
import { type ReactNode, useMemo, useState } from "react";
import { Pressable, Text, View } from "react-native";
import { isOutgoingMessage } from "../lib/outgoing-messages";
import { useSession } from "../lib/session";
import { ArtifactFileCard } from "./artifact-file-card";
import { BotAvatar } from "./bot-avatar";
import { ComposerReplyPreview } from "./composer-reply-preview";
import { Markdown } from "./markdown";
import {
  NativeRichResponse,
  type NativeVisualAction,
  nativeRichImageIds,
} from "./native-rich-response";
import { NativeSymbol } from "./native-symbol";
import { colors } from "./ui";
export function MessageBubble({
  message,
  body,
  agent,
  files,
  onArtifact,
  onChartLink,
  onVisualAction,
  onRetry,
  previousVisualMessageId,
  grouped = false,
  reply,
  onReply,
}: {
  message: Message;
  body?: ReactNode;
  agent?: Agent;
  files: Artifact[];
  onArtifact: (id: string) => void;
  onChartLink?: (url: string) => boolean;
  onVisualAction?: NativeVisualAction;
  onRetry?: (nonce: string) => void;
  previousVisualMessageId?: string;
  grouped?: boolean;
  reply?: Message;
  onReply?: (message: Message) => void;
}) {
  const { rtl, locale, t } = useSession();
  const [expanded, setExpanded] = useState(false);
  const isOwner = message.role === "user";
  const tool = message.role === "tool";
  const rich = useMemo(
    () => (message.role === "assistant" ? validateRichContent(message.rich_content) : null),
    [message.rich_content, message.role],
  );
  const imageIds = useMemo(() => nativeRichImageIds(rich), [rich]);
  return (
    <Pressable
      onLongPress={() => onReply?.(message)}
      accessibilityActions={[{ name: "reply", label: t("reply") }]}
      onAccessibilityAction={(event) => {
        if (event.nativeEvent.actionName === "reply") onReply?.(message);
      }}
      style={{
        alignSelf: isOwner ? (rtl ? "flex-start" : "flex-end") : "stretch",
        maxWidth: isOwner ? "88%" : "100%",
        backgroundColor: isOwner ? colors.chatUser : "transparent",
        borderRadius: 18,
        padding: isOwner ? 14 : 0,
        gap: 8,
      }}
    >
      {!grouped && !isOwner && !tool ? (
        <View style={{ flexDirection: rtl ? "row-reverse" : "row", alignItems: "center", gap: 8 }}>
          {agent ? (
            <BotAvatar
              superBot={agent.super_bot_active}
              identity={agent.name}
              color={agent.color}
              variant={agent.avatar}
              size={24}
            />
          ) : null}
          <Text style={{ color: colors.foreground, fontSize: 13, fontWeight: "600" }}>
            {agent?.name ?? t("system")}
          </Text>
          <Text style={{ color: colors.secondary, fontSize: 11 }}>
            {new Date(message.created_at).toLocaleTimeString(locale, {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </Text>
        </View>
      ) : null}
      {reply ? <ComposerReplyPreview message={reply} /> : null}
      {tool ? (
        <View
          style={{
            backgroundColor: colors.muted,
            borderRadius: 12,
            overflow: "hidden",
            borderWidth: 0.5,
            borderColor: colors.border,
          }}
        >
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={t("toolResult")}
            accessibilityState={{ expanded }}
            onPress={() => setExpanded(!expanded)}
            style={{
              flexDirection: rtl ? "row-reverse" : "row",
              padding: 12,
              alignItems: "center",
              gap: 10,
            }}
          >
            <NativeSymbol name="check" size={16} color={colors.secondary} />
            <Text style={{ flex: 1, color: colors.secondary, fontSize: 13 }}>
              {t("toolResult")}
            </Text>
            <NativeSymbol
              name={expanded ? "close" : "chevron"}
              size={14}
              color={colors.secondary}
            />
          </Pressable>
          {expanded ? (
            <Text
              selectable
              style={{
                color: colors.secondary,
                padding: 12,
                fontSize: 13,
                lineHeight: 20,
                writingDirection: "auto",
              }}
            >
              {message.content}
            </Text>
          ) : null}
        </View>
      ) : (
        (body ??
        (rich ? (
          <NativeRichResponse
            content={rich}
            messageId={message.id}
            previousMessageId={previousVisualMessageId}
            threadId={message.thread_id}
            onAction={onVisualAction}
            onChartLink={onChartLink}
          />
        ) : message.content ? (
          <Markdown content={message.content} onChartLink={onChartLink} />
        ) : null))
      )}
      {isOutgoingMessage(message) ? (
        <View style={{ flexDirection: rtl ? "row-reverse" : "row", alignItems: "center", gap: 8 }}>
          <Text style={{ color: colors.secondary, fontSize: 12 }}>
            {t(message.delivery === "failed" ? "sendFailed" : "sending")}
          </Text>
          {message.delivery === "failed" && onRetry ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={t("retry")}
              onPress={() => onRetry(message.retry_nonce)}
              style={{ minHeight: 44, minWidth: 44, justifyContent: "center" }}
            >
              <Text style={{ color: colors.link, fontSize: 13 }}>{t("retry")}</Text>
            </Pressable>
          ) : null}
        </View>
      ) : null}
      {message.attachment_ids
        .filter((id) => !imageIds.has(id))
        .map((id) => (
          <ArtifactFileCard
            key={id}
            id={id}
            artifact={files.find((file) => file.id === id)}
            onOpen={() => onArtifact(id)}
          />
        ))}
    </Pressable>
  );
}
