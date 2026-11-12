// Native composer structure and metrics adapted from the template; see NOTICE.

import type { Agent, Artifact, Message } from "@lonora/contracts";
import {
  commandQuery,
  guestCandidates,
  type MentionAddress,
  type MentionRange,
  mentionAddress,
  mentionCandidates,
  mentionQuery,
  rankCommands,
  rebaseMentions,
} from "@lonora/core";
import { type ReactNode, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Platform,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
} from "react-native";
import type { CommandRow } from "../lib/commands";
import type { ComposerUpload } from "../lib/composer-uploads";
import { fill } from "../lib/i18n";
import { useSession } from "../lib/session";
import { useShellColors } from "../lib/theme";
import { BotAvatar } from "./bot-avatar";
import { ComposerReplyPreview } from "./composer-reply-preview";
import { NativeSymbol } from "./native-symbol";
import { UploadRing } from "./upload-ring";
export function ThreadComposer({
  draft,
  onChange,
  attachments,
  onRemove,
  onAttach,
  onSend,
  onStop,
  busy,
  uploading,
  uploads = [],
  onCancelUpload,
  disabled,
  working = false,
  members = [],
  mentionAll = false,
  direct = false,
  self,
  collaborationSessionId,
  reply,
  onCancelReply,
  editing,
  onCancelEdit,
  commands = [],
  onCommand,
  permissionControl,
}: {
  draft: string;
  onChange: (value: string) => void;
  attachments: Artifact[];
  onRemove: (id: string) => void;
  onAttach: () => void;
  onSend: (mentions?: MentionAddress) => void;
  onStop?: () => void;
  busy: boolean;
  /** The picker is open or files are being read: the «+» waits. */
  uploading: boolean;
  /** Files uploading into this draft, each with its ring and cancel. */
  uploads?: ComposerUpload[];
  onCancelUpload?: (id: string) => void;
  disabled: boolean;
  working?: boolean;
  members?: Agent[];
  mentionAll?: boolean;
  /** A direct chat: other agents join as guests. */
  direct?: boolean;
  /** A direct chat's own agent: never offered as a guest. */
  self?: string | null;
  collaborationSessionId?: string;
  reply?: Message | null;
  onCancelReply?: () => void;
  /** The / commands this chat offers (lib/commands), and what picking one does. */
  commands?: CommandRow[];
  onCommand?: (row: CommandRow) => void;
  /** Edit and resend (Q21): the owner's message this send replaces. */
  editing?: Message | null;
  onCancelEdit?: () => void;
  permissionControl?: ReactNode;
}) {
  const { rtl, t } = useSession();
  const shell = useShellColors();
  const [inputHeight, setInputHeight] = useState(32);
  const [cursor, setCursor] = useState(0);
  const committed = useRef<MentionRange[]>([]);
  const textBeforeCaret = draft.slice(0, cursor);
  const query = mentionQuery(textBeforeCaret);
  const candidates: Array<Agent | null> =
    query === null
      ? []
      : guestCandidates(mentionCandidates(members, query), committed.current, direct, self).slice(
          0,
          6,
        );
  if (query !== null && mentionAll && "all".startsWith(query.toLowerCase())) candidates.push(null);
  // «/» at the start of a message: the chat's commands, best match first (never in an edit).
  const commandTyped = editing ? null : commandQuery(textBeforeCaret);
  const ranked = commandTyped === null ? null : rankCommands(commands, commandTyped);
  useEffect(() => {
    if (!draft) {
      committed.current = [];
      setInputHeight(32);
      setCursor(0);
    }
  }, [draft]);
  // A message may be sent while its files upload: it goes out once they are up (as on Web).
  const canSend =
    Boolean(draft.trim() || attachments.length || uploads.length) &&
    !disabled &&
    !busy &&
    !uploading;
  return (
    <View
      style={{
        paddingHorizontal: 12,
        paddingBottom: 12,
        paddingTop: 8,
        gap: 8,
        backgroundColor: shell.background,
      }}
    >
      {editing ? (
        <ComposerReplyPreview message={editing} onClose={onCancelEdit} editing />
      ) : reply ? (
        <ComposerReplyPreview message={reply} onClose={onCancelReply} />
      ) : null}
      {ranked?.length ? (
        <View
          role="list"
          accessibilityLabel={t("cmdList")}
          style={{ backgroundColor: shell.muted, borderRadius: 14, overflow: "hidden" }}
        >
          {ranked.slice(0, 8).map((row) => (
            <Pressable
              key={row.id}
              accessibilityRole="button"
              accessibilityLabel={`/${row.name}`}
              onPress={() => {
                const rest = draft.slice(cursor).replace(/^\S*[ \t]*/, "");
                if (row.argument) {
                  const next = `/${row.name} ${rest}`;
                  onChange(next);
                  setCursor(row.name.length + 2);
                } else {
                  onChange(rest);
                  setCursor(0);
                  onCommand?.(row);
                }
              }}
              style={({ pressed }) => ({
                flexDirection: rtl ? "row-reverse" : "row",
                alignItems: "center",
                gap: 10,
                paddingHorizontal: 14,
                paddingVertical: 10,
                backgroundColor: pressed ? shell.accent : "transparent",
              })}
            >
              <Text style={{ color: shell.foreground, fontSize: 15, fontWeight: "600" }}>
                /{row.name}
              </Text>
              {row.sub ? (
                <Text
                  numberOfLines={1}
                  style={{
                    flex: 1,
                    color: shell.secondary,
                    fontSize: 13,
                    writingDirection: "auto",
                  }}
                >
                  {row.sub}
                </Text>
              ) : null}
            </Pressable>
          ))}
        </View>
      ) : candidates.length ? (
        <View style={{ backgroundColor: shell.muted, borderRadius: 14, overflow: "hidden" }}>
          {candidates.map((agent) => (
            <Pressable
              key={agent?.id ?? "session-all"}
              accessibilityRole="button"
              accessibilityLabel={`@${agent?.name ?? "all"}`}
              onPress={() => {
                const start = textBeforeCaret.lastIndexOf("@");
                const token = `@${agent?.name ?? "all"}`;
                const prefix = `${draft.slice(0, start)}${token} `;
                const next = prefix + draft.slice(cursor);
                committed.current = [
                  ...rebaseMentions(draft, next, committed.current),
                  {
                    agent_id: agent?.id ?? null,
                    session_id: agent ? undefined : collaborationSessionId,
                    token,
                    start,
                    end: start + token.length,
                  },
                ];
                onChange(next);
                setCursor(prefix.length);
              }}
              style={({ pressed }) => ({
                flexDirection: rtl ? "row-reverse" : "row",
                alignItems: "center",
                gap: 10,
                paddingHorizontal: 14,
                paddingVertical: 10,
                backgroundColor: pressed ? shell.accent : "transparent",
              })}
            >
              <BotAvatar
                identity={agent?.id ?? "all"}
                color={agent?.color ?? shell.accent}
                variant={agent?.avatar}
                size={24}
              />
              <Text style={{ color: shell.foreground, fontSize: 15 }}>{agent?.name ?? "@all"}</Text>
              {agent?.trading_symbol ? (
                <Text style={{ color: shell.secondary, writingDirection: "ltr" }}>
                  {agent.trading_symbol}
                </Text>
              ) : null}
            </Pressable>
          ))}
        </View>
      ) : null}
      {attachments.length || uploads.length ? (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={{ gap: 8, flexDirection: rtl ? "row-reverse" : "row" }}
        >
          {attachments.map((file) => (
            <Pressable
              key={file.id}
              accessibilityRole="button"
              accessibilityLabel={`${t("removeAttachment")}: ${file.payload.name}`}
              onPress={() => onRemove(file.id)}
              style={{
                flexDirection: rtl ? "row-reverse" : "row",
                alignItems: "center",
                gap: 8,
                borderRadius: 12,
                paddingHorizontal: 12,
                paddingVertical: 10,
                backgroundColor: shell.muted,
                maxWidth: 220,
              }}
            >
              <NativeSymbol name="file" size={16} color={shell.secondary} />
              <Text
                numberOfLines={1}
                style={{
                  color: shell.foreground,
                  fontSize: 13,
                  flexShrink: 1,
                  writingDirection: "auto",
                }}
              >
                {file.payload.name}
              </Text>
              <NativeSymbol name="close" size={14} color={shell.secondary} />
            </Pressable>
          ))}
          {uploads.map((file) => (
            <View
              key={file.id}
              testID="composer-upload"
              style={{
                flexDirection: rtl ? "row-reverse" : "row",
                alignItems: "center",
                gap: 8,
                borderRadius: 12,
                paddingHorizontal: 10,
                paddingVertical: 6,
                backgroundColor: shell.muted,
                maxWidth: 220,
              }}
            >
              <UploadRing
                p={file.p}
                label={fill(t("uploadingFile"), file.name)}
                onCancel={onCancelUpload ? () => onCancelUpload(file.id) : undefined}
              />
              <Text
                numberOfLines={1}
                style={{
                  color: shell.foreground,
                  fontSize: 13,
                  flexShrink: 1,
                  writingDirection: "auto",
                }}
              >
                {file.name}
              </Text>
            </View>
          ))}
        </ScrollView>
      ) : null}
      <View style={{ flexDirection: rtl ? "row-reverse" : "row", alignItems: "flex-end", gap: 10 }}>
        <View
          testID="thread-composer-input-native"
          style={{
            flex: 1,
            minWidth: 0,
            minHeight: 56,
            borderRadius: 28,
            flexDirection: rtl ? "row-reverse" : "row",
            alignItems: "flex-end",
            gap: 8,
            paddingHorizontal: 11,
            paddingVertical: 11,
            backgroundColor: shell.muted,
            borderWidth: 0.5,
            borderColor: shell.border,
          }}
        >
          <View
            testID="thread-composer-attach-native"
            style={{ width: 32, height: 32, alignItems: "center", justifyContent: "center" }}
          >
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={t("attach")}
              hitSlop={6}
              style={{ width: 32, height: 32, alignItems: "center", justifyContent: "center" }}
              onPress={onAttach}
              disabled={busy || uploading || disabled || attachments.length + uploads.length >= 10}
            >
              {uploading ? (
                <ActivityIndicator color={shell.secondary} size="small" />
              ) : (
                <NativeSymbol name="plus" size={18} color={shell.secondary} />
              )}
            </Pressable>
          </View>
          {permissionControl}
          <TextInput
            accessibilityLabel={t("message")}
            placeholder={t("message")}
            value={draft}
            onChangeText={(value) => {
              committed.current = rebaseMentions(draft, value, committed.current);
              setCursor(Math.max(0, Math.min(value.length, cursor + value.length - draft.length)));
              onChange(value);
            }}
            onKeyPress={(event) => {
              if (Platform.OS !== "web") return;
              const keyboard = event as unknown as {
                key: string;
                shiftKey: boolean;
                keyCode: number;
                nativeEvent: { isComposing?: boolean };
                preventDefault: () => void;
              };
              if (
                keyboard.key === "Enter" &&
                !keyboard.shiftKey &&
                !keyboard.nativeEvent.isComposing &&
                keyboard.keyCode !== 229 &&
                canSend
              ) {
                keyboard.preventDefault();
                onSend(mentionAddress(draft, committed.current));
              }
            }}
            onSelectionChange={(event) => setCursor(event.nativeEvent.selection.start)}
            multiline
            onContentSizeChange={(event) =>
              setInputHeight(Math.max(32, Math.min(160, event.nativeEvent.contentSize.height)))
            }
            maxLength={30000}
            editable={!disabled}
            placeholderTextColor={shell.secondary}
            blurOnSubmit={false}
            textAlignVertical="top"
            underlineColorAndroid="transparent"
            selectionColor={shell.foreground}
            style={{
              flex: 1,
              minHeight: 32,
              height: inputHeight,
              maxHeight: 160,
              fontSize: 16,
              lineHeight: 24,
              paddingVertical: 4,
              paddingHorizontal: 0,
              borderWidth: 0,
              backgroundColor: "transparent",
              includeFontPadding: false,
              color: shell.foreground,
              textAlign: rtl ? "right" : "left",
              writingDirection: "auto",
            }}
          />
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={t("send")}
            disabled={!canSend}
            onPress={() => onSend(mentionAddress(draft, committed.current))}
            hitSlop={6}
            testID="thread-composer-send-native"
            style={({ pressed }) => ({
              width: 32,
              height: 32,
              borderRadius: 16,
              backgroundColor: shell.primary,
              alignItems: "center",
              justifyContent: "center",
              opacity: pressed || !canSend ? 0.4 : 1,
            })}
          >
            {busy ? (
              <ActivityIndicator size="small" color={shell.primaryForeground} />
            ) : (
              <NativeSymbol name="send" size={16} color={shell.primaryForeground} />
            )}
          </Pressable>
          {working && onStop ? (
            <View
              style={{
                width: 32,
                height: 32,
                borderRadius: 16,
                backgroundColor: shell.primary,
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={t("cancel")}
                onPress={onStop}
                disabled={busy}
                style={{ width: 32, height: 32, alignItems: "center", justifyContent: "center" }}
              >
                <NativeSymbol name="stop" size={16} color={shell.primaryForeground} />
              </Pressable>
            </View>
          ) : null}
        </View>
      </View>
    </View>
  );
}
