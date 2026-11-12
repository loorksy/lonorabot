import type { Agent, Artifact, Message } from "@lonora/contracts";
import { callPart, peerOutcome, validateRichContent, voicePart } from "@lonora/core";
import { type ReactNode, useMemo, useState } from "react";
import { Pressable, Text, View } from "react-native";
import { isOutgoingMessage, outgoingUploads } from "../lib/outgoing-messages";
import { useSession } from "../lib/session";
import { useShellColors } from "../lib/theme";
import { ArtifactFileCard } from "./artifact-file-card";
import { BotAvatar } from "./bot-avatar";
import { ComposerReplyPreview } from "./composer-reply-preview";
import { Markdown } from "./markdown";
import { ReactionChips } from "./message-menu";
import {
  NativeRichResponse,
  type NativeVisualAction,
  nativeRichImageIds,
} from "./native-rich-response";
import { NativeSymbol } from "./native-symbol";
import { UploadRing } from "./upload-ring";
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
  onMenu,
  onReactions,
  onQuote,
  onCancelUploads,
  mark = null,
}: {
  /** ✕ on a sent message's upload ring: the message, never posted, is removed. */
  onCancelUploads?: (nonce: string) => void;
  /** Long press: the message menu (reactions and actions). */
  onMenu?: (message: Message) => void;
  /** A tap on the reactions under the bubble: who reacted. */
  onReactions?: (message: Message) => void;
  /** A tap on the quoted message: jump to it. */
  onQuote?: (message: Message) => void;
  /** Rule N on a card's send that never ran (GENUI_PLAN §8.2), from core `submitMark`. */
  mark?: "superseded" | "not_run" | null;
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
  const shell = useShellColors();
  const [expanded, setExpanded] = useState(false);
  const isOwner = message.role === "user";
  const tool = message.role === "tool";
  const rich = useMemo(
    () => (message.role === "assistant" ? validateRichContent(message.rich_content) : null),
    [message.rich_content, message.role],
  );
  const imageIds = useMemo(() => nativeRichImageIds(rich), [rich]);
  // A voice note or a call log has no text: it is named, never drawn as a blank bubble.
  const voice = voicePart(message);
  const call = callPart(message);
  const clock = (seconds: number) => {
    const s = Math.max(0, Math.round(seconds || 0));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  };
  const partLine = voice
    ? `${t("voiceNote")} · ${clock(voice.duration)}`
    : call
      ? call.missed
        ? t("missedVoiceCall")
        : `${t("voiceCall")} · ${clock(call.duration_seconds)}`
      : null;
  return (
    <Pressable
      onLongPress={() => (onMenu ? onMenu(message) : onReply?.(message))}
      accessibilityActions={[
        ...(onReply ? [{ name: "reply", label: t("reply") }] : []),
        ...(onMenu ? [{ name: "menu", label: t("messageOptions") }] : []),
      ]}
      onAccessibilityAction={(event) => {
        if (event.nativeEvent.actionName === "reply") onReply?.(message);
        if (event.nativeEvent.actionName === "menu") onMenu?.(message);
      }}
      style={{
        alignSelf: isOwner ? (rtl ? "flex-start" : "flex-end") : "stretch",
        maxWidth: isOwner ? "88%" : "100%",
        backgroundColor: isOwner ? shell.chatUser : "transparent",
        borderRadius: 18,
        padding: isOwner ? 14 : 0,
        gap: 8,
      }}
    >
      {!grouped && !isOwner && !tool ? (
        <View style={{ flexDirection: rtl ? "row-reverse" : "row", alignItems: "center", gap: 8 }}>
          {agent ? (
            <BotAvatar
              tradesOnItsOwn={agent.trades_on_its_own}
              identity={agent.id}
              color={agent.color}
              variant={agent.avatar}
              size={24}
            />
          ) : null}
          <Text style={{ color: shell.foreground, fontSize: 13, fontWeight: "600" }}>
            {agent?.name ?? t("system")}
          </Text>
          <Text style={{ color: shell.secondary, fontSize: 11 }}>
            {new Date(message.created_at).toLocaleTimeString(locale, {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </Text>
        </View>
      ) : null}
      {reply ? (
        onQuote ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`${t("reply")}: ${reply.content}`}
            onPress={() => onQuote(reply)}
          >
            <ComposerReplyPreview message={reply} />
          </Pressable>
        ) : (
          <ComposerReplyPreview message={reply} />
        )
      ) : null}
      {tool ? (
        <View
          style={{
            backgroundColor: shell.muted,
            borderRadius: 12,
            overflow: "hidden",
            borderWidth: 0.5,
            borderColor: shell.border,
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
            <NativeSymbol name="check" size={16} color={shell.secondary} />
            <Text style={{ flex: 1, color: shell.secondary, fontSize: 13 }}>{t("toolResult")}</Text>
            <NativeSymbol name={expanded ? "close" : "chevron"} size={14} color={shell.secondary} />
          </Pressable>
          {expanded ? (
            <Text
              selectable
              style={{
                color: shell.secondary,
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
          <Markdown content={peerOutcome(message.content).body} onChartLink={onChartLink} />
        ) : partLine ? (
          <Text style={{ color: shell.secondary, fontSize: 14, writingDirection: "auto" }}>
            {partLine}
          </Text>
        ) : null))
      )}
      {mark ? (
        <Text testID="ui-submit-mark" style={{ color: shell.secondary, fontSize: 12 }}>
          {t(mark === "superseded" ? "uiSubmitEdited" : "uiSubmitNotRun")}
        </Text>
      ) : message.superseded_by ? (
        // Edit and resend (Q21): the replaced message says so.
        <Text testID="message-edited" style={{ color: shell.secondary, fontSize: 12 }}>
          {t("uiSubmitEdited")}
        </Text>
      ) : null}
      {onReactions ? (
        <ReactionChips message={message} onPress={() => onReactions(message)} />
      ) : null}
      {isOutgoingMessage(message) && message.uploading?.length && message.delivery !== "failed" ? (
        <View style={{ flexDirection: rtl ? "row-reverse" : "row", alignItems: "center", gap: 8 }}>
          <UploadRing
            p={(() => {
              const running = outgoingUploads(message.retry_nonce);
              return running.length
                ? running.reduce((sum, file) => sum + file.p, 0) / running.length
                : 0;
            })()}
            label={t("uploadingNow")}
            onCancel={onCancelUploads ? () => onCancelUploads(message.retry_nonce) : undefined}
          />
          <Text style={{ color: shell.secondary, fontSize: 12 }}>{t("uploadingNow")}</Text>
        </View>
      ) : isOutgoingMessage(message) ? (
        <View style={{ flexDirection: rtl ? "row-reverse" : "row", alignItems: "center", gap: 8 }}>
          <Text style={{ color: shell.secondary, fontSize: 12 }}>
            {t(
              message.delivery === "failed"
                ? "sendFailed"
                : message.delivery === "queued"
                  ? "sh_waitingNetwork"
                  : "sending",
            )}
          </Text>
          {message.delivery === "failed" && onRetry && !message.uploading?.length ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={t("retry")}
              onPress={() => onRetry(message.retry_nonce)}
              style={{ minHeight: 44, minWidth: 44, justifyContent: "center" }}
            >
              <Text style={{ color: shell.link, fontSize: 13 }}>{t("retry")}</Text>
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
