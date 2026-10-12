// Composer geometry follows Tampletgrok's native thread composer (Apache-2.0); see NOTICE.

import type { Artifact } from "@lonora/contracts";
import { Pressable, Text, TextInput, View } from "react-native";
import { useSession } from "../lib/session";
import { Button, colors } from "./ui";

export function ThreadComposer({
  draft,
  onChange,
  attachments,
  onRemove,
  onAttach,
  onSend,
  busy,
  uploading,
  disabled,
}: {
  draft: string;
  onChange: (value: string) => void;
  attachments: Artifact[];
  onRemove: (id: string) => void;
  onAttach: () => void;
  onSend: () => void;
  busy: boolean;
  uploading: boolean;
  disabled: boolean;
}) {
  const { rtl, t } = useSession();
  return (
    <View
      style={{
        borderTopWidth: 1,
        borderColor: colors.border,
        paddingHorizontal: 16,
        paddingTop: 10,
        paddingBottom: 12,
        gap: 8,
      }}
    >
      {attachments.map((file) => (
        <Pressable
          key={file.id}
          accessibilityLabel={`${t("removeAttachment")}: ${file.payload.name}`}
          onPress={() => onRemove(file.id)}
        >
          <Text style={{ color: colors.secondary, writingDirection: "auto" }}>
            × {file.payload.name}
          </Text>
        </Pressable>
      ))}
      <TextInput
        accessibilityLabel={t("message")}
        placeholder={t("message")}
        value={draft}
        onChangeText={onChange}
        multiline
        maxLength={30000}
        editable={!busy}
        placeholderTextColor={colors.secondary}
        style={{
          color: colors.foreground,
          backgroundColor: colors.muted,
          borderRadius: 18,
          minHeight: 52,
          maxHeight: 160,
          fontSize: 16,
          padding: 14,
          textAlign: rtl ? "right" : "left",
          writingDirection: "auto",
        }}
      />
      <View
        style={{
          flexDirection: rtl ? "row-reverse" : "row",
          justifyContent: "space-between",
          gap: 12,
        }}
      >
        <Button
          label={uploading ? t("connecting") : t("attach")}
          secondary
          onPress={onAttach}
          disabled={busy || uploading || disabled || attachments.length >= 10}
        />
        <Button
          label={busy ? t("connecting") : t("send")}
          onPress={onSend}
          disabled={busy || uploading || disabled || (!draft.trim() && !attachments.length)}
        />
      </View>
    </View>
  );
}
