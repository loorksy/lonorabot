import { AVATAR_COLORS } from "@lonora/core";
import { useState } from "react";
import { Modal, Pressable, ScrollView, Text, View } from "react-native";
import { useSession } from "../lib/session";
import { BotAvatar } from "./bot-avatar";
import { SheetHeader } from "./sheet-header";
import { colors, Screen } from "./ui";
export function AvatarPicker({
  name,
  color,
  avatar,
  onChange,
}: {
  name: string;
  color: string;
  avatar: string;
  onChange: (avatar: string, color: string) => void;
}) {
  const { rtl, t } = useSession();
  const [open, setOpen] = useState(false);
  return (
    <>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={t("avatar")}
        onPress={() => setOpen(true)}
        style={{ alignSelf: "center", alignItems: "center", gap: 10, paddingVertical: 12 }}
      >
        <BotAvatar identity={name} color={color} variant={avatar} size={88} />
        <Text style={{ color: colors.secondary, fontSize: 13 }}>{t("edit")}</Text>
      </Pressable>
      <Modal
        visible={open}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setOpen(false)}
      >
        <Screen>
          <SheetHeader title={t("avatar")} onClose={() => setOpen(false)} />
          <ScrollView contentContainerStyle={{ padding: 24, gap: 24 }}>
            <View style={{ alignItems: "center", paddingVertical: 20 }}>
              <BotAvatar identity={name} color={color} variant={avatar} size={110} />
            </View>
            <Text
              style={{ color: colors.secondary, textAlign: rtl ? "right" : "left", fontSize: 13 }}
            >
              {t("color")}
            </Text>
            <View style={{ flexDirection: rtl ? "row-reverse" : "row", gap: 14, flexWrap: "wrap" }}>
              {AVATAR_COLORS.map((value) => (
                <Pressable
                  key={value}
                  accessibilityRole="radio"
                  accessibilityLabel={value}
                  accessibilityState={{ checked: value.toLowerCase() === color.toLowerCase() }}
                  onPress={() => onChange(avatar, value)}
                  style={{
                    width: 42,
                    height: 42,
                    borderRadius: 21,
                    backgroundColor: value,
                    borderWidth: value.toLowerCase() === color.toLowerCase() ? 3 : 0,
                    borderColor: colors.foreground,
                  }}
                />
              ))}
            </View>
          </ScrollView>
        </Screen>
      </Modal>
    </>
  );
}
