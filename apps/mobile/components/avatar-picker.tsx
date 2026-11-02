import type { AvatarStateId } from "@lonora/core";
import { useState } from "react";
import { Modal, Pressable, ScrollView, Text, View } from "react-native";
import type { Label } from "../lib/i18n";
import { useSession } from "../lib/session";
import { BotAvatar } from "./bot-avatar";
import { SheetHeader } from "./sheet-header";
import { colors, Screen } from "./ui";

const previews: readonly { state: AvatarStateId; label: Label }[] = [
  { state: "waiting", label: "live_waiting" },
  { state: "thinking", label: "activity_thinking" },
  { state: "searching", label: "activity_searching" },
  { state: "inspecting", label: "activity_reading" },
  { state: "analyzing", label: "activity_analyzing" },
  { state: "writing", label: "activity_writing" },
  { state: "executing", label: "activity_executing" },
  { state: "learning", label: "activity_learning" },
  { state: "sending", label: "activity_sending" },
  { state: "connecting", label: "connecting" },
  { state: "success", label: "activity_completed" },
  { state: "error", label: "activity_failed" },
];

/** Appearance is shared; this gallery previews motion without changing agent activity. */
export function AvatarPicker({
  name,
  color,
  avatar,
}: {
  name: string;
  color: string;
  avatar: string;
}) {
  const { rtl, t } = useSession();
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<AvatarStateId>("waiting");
  return (
    <>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${t("avatar")} · ${t("preview")}`}
        onPress={() => setOpen(true)}
        style={{ alignSelf: "center", alignItems: "center", gap: 10, paddingVertical: 12 }}
      >
        <BotAvatar identity={name} color={color} variant={avatar} size={88} />
        <Text style={{ color: colors.secondary, fontSize: 13 }}>{t("preview")}</Text>
      </Pressable>
      <Modal
        visible={open}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setOpen(false)}
      >
        <Screen>
          <SheetHeader title={`${t("avatar")} · ${t("preview")}`} onClose={() => setOpen(false)} />
          <ScrollView contentContainerStyle={{ padding: 24, gap: 24 }}>
            <View style={{ alignItems: "center", paddingVertical: 20, gap: 16 }}>
              <BotAvatar identity={name} color={color} variant={avatar} size={168} state={state} />
              <Text style={{ color: colors.foreground, fontSize: 18, fontWeight: "600" }}>
                {t(previews.find((item) => item.state === state)?.label ?? "live_waiting")}
              </Text>
            </View>
            <View style={{ flexDirection: rtl ? "row-reverse" : "row", gap: 10, flexWrap: "wrap" }}>
              {previews.map((preview) => (
                <Pressable
                  key={preview.state}
                  accessibilityRole="button"
                  accessibilityLabel={t(preview.label)}
                  accessibilityState={{ selected: state === preview.state }}
                  onPress={() => setState(preview.state)}
                  style={{
                    minHeight: 44,
                    paddingHorizontal: 16,
                    paddingVertical: 12,
                    borderRadius: 22,
                    backgroundColor: state === preview.state ? colors.accent : colors.muted,
                    borderWidth: 1,
                    borderColor: state === preview.state ? colors.foreground : colors.border,
                  }}
                >
                  <Text style={{ color: colors.foreground, fontSize: 13 }}>{t(preview.label)}</Text>
                </Pressable>
              ))}
            </View>
          </ScrollView>
        </Screen>
      </Modal>
    </>
  );
}
