// Native composer structure and metrics adapted from the template; see NOTICE.

import type { Agent, Artifact, Message } from "@lonora/contracts";
import { mentionCandidates, mentionQuery } from "@lonora/core";
import { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { useSession } from "../lib/session";
import { BotAvatar } from "./bot-avatar";
import { ComposerReplyPreview } from "./composer-reply-preview";
import { HeaderButton } from "./header-button";
import { NativeSymbol } from "./native-symbol";
import { colors } from "./ui";
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
  disabled,
  working = false,
  members = [],
  reply,
  onCancelReply,
}: {
  draft: string;
  onChange: (value: string) => void;
  attachments: Artifact[];
  onRemove: (id: string) => void;
  onAttach: () => void;
  onSend: () => void;
  onStop?: () => void;
  busy: boolean;
  uploading: boolean;
  disabled: boolean;
  working?: boolean;
  members?: Agent[];
  reply?: Message | null;
  onCancelReply?: () => void;
}) {
  const { rtl, t } = useSession();
  const [inputHeight, setInputHeight] = useState(44);
  const [cursor, setCursor] = useState(0);
  const textBeforeCaret = draft.slice(0, cursor);
  const query = mentionQuery(textBeforeCaret);
  const candidates = query === null ? [] : mentionCandidates(members, query).slice(0, 6);
  useEffect(() => {
    if (!draft) {
      setInputHeight(44);
      setCursor(0);
    }
  }, [draft]);
  const canSend = Boolean(draft.trim() || attachments.length) && !disabled && !busy && !uploading;
  return (
    <View
      style={{
        paddingHorizontal: 16,
        paddingBottom: 10,
        paddingTop: 8,
        gap: 8,
        backgroundColor: colors.background,
      }}
    >
      {reply ? <ComposerReplyPreview message={reply} onClose={onCancelReply} /> : null}
      {candidates.length ? (
        <View style={{ backgroundColor: colors.muted, borderRadius: 14, overflow: "hidden" }}>
          {candidates.map((agent) => (
            <Pressable
              key={agent.id}
              accessibilityRole="button"
              accessibilityLabel={`@${agent.name}`}
              onPress={() => {
                const prefix = textBeforeCaret.replace(/@[^\s@]*$/, `@${agent.name} `);
                onChange(prefix + draft.slice(cursor));
                setCursor(prefix.length);
              }}
              style={({ pressed }) => ({
                flexDirection: rtl ? "row-reverse" : "row",
                alignItems: "center",
                gap: 10,
                paddingHorizontal: 14,
                paddingVertical: 10,
                backgroundColor: pressed ? colors.accent : "transparent",
              })}
            >
              <BotAvatar
                identity={agent.name}
                color={agent.color}
                variant={agent.avatar}
                size={24}
              />
              <Text style={{ color: colors.foreground, fontSize: 15 }}>{agent.name}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}
      {attachments.length ? (
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
                backgroundColor: colors.muted,
                maxWidth: 220,
              }}
            >
              <NativeSymbol name="file" size={16} color={colors.secondary} />
              <Text
                numberOfLines={1}
                style={{
                  color: colors.foreground,
                  fontSize: 13,
                  flexShrink: 1,
                  writingDirection: "auto",
                }}
              >
                {file.payload.name}
              </Text>
              <NativeSymbol name="close" size={14} color={colors.secondary} />
            </Pressable>
          ))}
        </ScrollView>
      ) : null}
      <View style={{ flexDirection: rtl ? "row-reverse" : "row", alignItems: "flex-end", gap: 10 }}>
        <View
          style={{
            width: 44,
            height: 44,
            borderRadius: 22,
            backgroundColor: colors.muted,
            alignItems: "center",
            justifyContent: "center",
            borderWidth: 0.5,
            borderColor: colors.border,
          }}
        >
          <HeaderButton
            label={t("attach")}
            onPress={onAttach}
            disabled={busy || uploading || disabled || attachments.length >= 10}
          >
            {uploading ? (
              <ActivityIndicator color={colors.secondary} size="small" />
            ) : (
              <NativeSymbol name="plus" size={18} color={colors.secondary} />
            )}
          </HeaderButton>
        </View>
        <View
          style={{
            flex: 1,
            minHeight: 44,
            borderRadius: 22,
            flexDirection: rtl ? "row-reverse" : "row",
            alignItems: "flex-end",
            paddingHorizontal: 4,
            backgroundColor: colors.muted,
            borderWidth: 0.5,
            borderColor: colors.border,
          }}
        >
          <TextInput
            accessibilityLabel={t("message")}
            placeholder={t("message")}
            value={draft}
            onChangeText={(value) => {
              setCursor(Math.max(0, Math.min(value.length, cursor + value.length - draft.length)));
              onChange(value);
            }}
            onSelectionChange={(event) => setCursor(event.nativeEvent.selection.start)}
            multiline
            onContentSizeChange={(event) =>
              setInputHeight(Math.max(44, Math.min(132, event.nativeEvent.contentSize.height)))
            }
            maxLength={30000}
            editable={!busy && !disabled}
            placeholderTextColor={colors.secondary}
            blurOnSubmit={false}
            textAlignVertical="top"
            style={{
              flex: 1,
              minHeight: 44,
              height: inputHeight,
              maxHeight: 132,
              fontSize: 17,
              lineHeight: 22,
              paddingTop: 11,
              paddingBottom: 11,
              paddingHorizontal: 12,
              color: colors.foreground,
              textAlign: rtl ? "right" : "left",
              writingDirection: "auto",
            }}
          />
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={t("send")}
            disabled={!canSend}
            onPress={onSend}
            style={({ pressed }) => ({
              marginBottom: 8,
              width: 32,
              height: 28,
              borderRadius: 14,
              backgroundColor: colors.primary,
              alignItems: "center",
              justifyContent: "center",
              opacity: pressed || !canSend ? 0.4 : 1,
            })}
          >
            {busy ? (
              <ActivityIndicator size="small" color={colors.primaryForeground} />
            ) : (
              <NativeSymbol name="send" size={16} color={colors.primaryForeground} />
            )}
          </Pressable>
        </View>
        {working && onStop ? (
          <View
            style={{
              width: 44,
              height: 44,
              borderRadius: 22,
              borderWidth: 1,
              borderColor: colors.border,
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <HeaderButton label={t("cancel")} onPress={onStop} disabled={busy}>
              <NativeSymbol name="stop" size={18} />
            </HeaderButton>
          </View>
        ) : null}
      </View>
    </View>
  );
}
