import { AVATAR_COLORS, AVATAR_FACES, DEFAULT_AVATAR_COLOR, resolveAvatarFace } from "@lonora/core";
import { useState } from "react";
import { Keyboard, Modal, Pressable, ScrollView, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import Svg, { Path } from "react-native-svg";
import type { Label } from "../lib/i18n";
import { useSession } from "../lib/session";
import { BotAvatar } from "./bot-avatar";
import { colors } from "./ui";

const faceLabels: Record<string, Label> = {
  orb: "avatarSignals",
  "face-smile": "avatarSmile",
  "face-thoughtful": "avatarThoughtful",
  "face-happy": "avatarHappy",
  "face-wink": "avatarWink",
  "face-sleepy": "avatarSleepy",
  "face-surprised": "avatarSurprised",
  "face-angry": "avatarAngry",
  "face-playful": "avatarPlayful",
  "face-excited": "avatarExcited",
  "face-skeptical": "avatarSkeptical",
  "face-dreamy": "avatarDreamy",
  "face-focused": "avatarFocused",
  "face-worried": "avatarWorried",
  "face-laugh": "avatarLaugh",
  "face-determined": "avatarDetermined",
};

/** Studio edits a local draft; Done applies it to the surrounding creation/profile form. */
export function AvatarPicker({
  name,
  identity,
  color,
  avatar,
  onChange,
}: {
  name: string;
  identity?: string;
  color: string;
  avatar: string;
  onChange: (avatar: string, color: string) => void;
}) {
  const { rtl, t } = useSession();
  const [open, setOpen] = useState(false);
  const [draftFace, setDraftFace] = useState(avatar);
  const [draftColor, setDraftColor] = useState(color);
  const direction = rtl ? "row-reverse" : "row";
  const begin = () => {
    Keyboard.dismiss();
    setDraftFace(avatar);
    setDraftColor(color);
    setOpen(true);
  };
  return (
    <>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={t("avatarEdit")}
        onPress={begin}
        style={{
          alignSelf: "center",
          width: 112,
          height: 112,
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <BotAvatar identity={identity ?? name} color={color} variant={avatar} size={88} />
        <View
          pointerEvents="none"
          style={{
            position: "absolute",
            right: 0,
            bottom: 4,
            width: 38,
            height: 38,
            borderRadius: 19,
            borderWidth: 2,
            borderColor: colors.background,
            backgroundColor: colors.muted,
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Svg width={18} height={18} viewBox="0 0 24 24" aria-hidden>
            <Path
              d="m15 5 4 4M4 20l4-1L20 7a2.8 2.8 0 0 0-4-4L4 15Z"
              fill="none"
              stroke={colors.foreground}
              strokeWidth={1.8}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </Svg>
        </View>
      </Pressable>
      <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
        <SafeAreaView
          style={{
            flex: 1,
            padding: 16,
            justifyContent: "center",
            alignItems: "center",
            backgroundColor: "#0009",
          }}
        >
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={t("close")}
            onPress={() => setOpen(false)}
            style={{ position: "absolute", inset: 0 }}
          />
          <View
            testID="avatar-studio"
            accessibilityViewIsModal
            style={{
              width: "100%",
              maxWidth: 460,
              maxHeight: "100%",
              backgroundColor: colors.background,
              borderColor: colors.border,
              borderWidth: 1,
              borderRadius: 26,
              overflow: "hidden",
            }}
          >
            <View
              style={{
                flexDirection: direction,
                alignItems: "center",
                paddingHorizontal: 20,
                paddingTop: 12,
                gap: 12,
              }}
            >
              <Text
                accessibilityRole="header"
                style={{
                  flex: 1,
                  color: colors.foreground,
                  fontSize: 18,
                  fontWeight: "600",
                  textAlign: rtl ? "right" : "left",
                }}
              >
                {t("avatarStudio")}
              </Text>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={t("close")}
                onPress={() => setOpen(false)}
                style={{
                  minWidth: 44,
                  minHeight: 44,
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <Text style={{ color: colors.secondary, fontSize: 25 }}>×</Text>
              </Pressable>
            </View>
            <ScrollView
              keyboardShouldPersistTaps="handled"
              contentContainerStyle={{ padding: 20, paddingTop: 8, gap: 18 }}
            >
              <View style={{ alignItems: "center", paddingVertical: 8 }}>
                <BotAvatar
                  identity={identity ?? name}
                  color={draftColor}
                  variant={draftFace}
                  size={126}
                />
              </View>
              <Text
                style={{
                  color: colors.secondary,
                  fontSize: 12,
                  textAlign: rtl ? "right" : "left",
                  lineHeight: 18,
                }}
              >
                {t("avatarStudioHint")}
              </Text>
              <View
                style={{
                  flexDirection: direction,
                  alignItems: "center",
                  borderBottomWidth: 1,
                  borderColor: colors.border,
                  paddingBottom: 8,
                }}
              >
                <Text
                  style={{
                    color: colors.secondary,
                    flex: 1,
                    fontSize: 12,
                    fontWeight: "600",
                    textAlign: rtl ? "right" : "left",
                  }}
                >
                  {t("avatarFace")}
                </Text>
                <Pressable
                  accessibilityRole="button"
                  onPress={() => {
                    setDraftFace("orb");
                    setDraftColor(DEFAULT_AVATAR_COLOR);
                  }}
                  style={{ minHeight: 44, justifyContent: "center", paddingHorizontal: 8 }}
                >
                  <Text style={{ color: colors.secondary, fontSize: 13 }}>{t("avatarReset")}</Text>
                </Pressable>
              </View>
              <View style={{ flexDirection: direction, flexWrap: "wrap", rowGap: 8 }}>
                {AVATAR_FACES.map((face) => {
                  const selected = resolveAvatarFace(draftFace) === face.id;
                  const label = t(faceLabels[face.id] ?? "avatar");
                  return (
                    <View key={face.id} style={{ width: "25%", paddingHorizontal: 3 }}>
                      <Pressable
                        testID={`avatar-face-${face.id}`}
                        accessibilityRole="radio"
                        accessibilityLabel={label}
                        accessibilityState={{ checked: selected }}
                        aria-checked={selected}
                        onPress={() => setDraftFace(face.id)}
                        style={{
                          minHeight: 86,
                          alignItems: "center",
                          justifyContent: "center",
                          gap: 5,
                          borderRadius: 15,
                          borderWidth: 1,
                          borderColor: selected ? draftColor : "transparent",
                          backgroundColor: selected ? colors.muted : "transparent",
                        }}
                      >
                        <View pointerEvents="none">
                          <BotAvatar
                            identity={identity ?? name}
                            color={draftColor}
                            variant={face.id}
                            size={48}
                            paused
                          />
                        </View>
                        <Text
                          numberOfLines={1}
                          style={{
                            color: selected ? colors.foreground : colors.secondary,
                            fontSize: 10,
                            paddingHorizontal: 2,
                          }}
                        >
                          {label}
                        </Text>
                      </Pressable>
                    </View>
                  );
                })}
              </View>
              <Text
                style={{
                  color: colors.secondary,
                  fontSize: 12,
                  fontWeight: "600",
                  borderTopWidth: 1,
                  borderColor: colors.border,
                  paddingTop: 18,
                  textAlign: rtl ? "right" : "left",
                }}
              >
                {t("color")}
              </Text>
              <View style={{ flexDirection: direction, flexWrap: "wrap", gap: 9 }}>
                {AVATAR_COLORS.map((value) => {
                  const selected = value.toLowerCase() === draftColor.toLowerCase();
                  return (
                    <Pressable
                      key={value}
                      accessibilityRole="radio"
                      accessibilityLabel={`${t("color")} ${value}`}
                      accessibilityState={{ checked: selected }}
                      aria-checked={selected}
                      onPress={() => setDraftColor(value)}
                      style={{
                        width: 44,
                        height: 44,
                        borderRadius: 22,
                        padding: 5,
                        borderWidth: 2,
                        borderColor: selected ? colors.foreground : "transparent",
                      }}
                    >
                      <View style={{ flex: 1, borderRadius: 17, backgroundColor: value }} />
                    </Pressable>
                  );
                })}
              </View>
            </ScrollView>
            <View
              style={{
                flexDirection: direction,
                gap: 10,
                borderTopWidth: 1,
                borderColor: colors.border,
                padding: 16,
              }}
            >
              <Pressable
                accessibilityRole="button"
                onPress={() => {
                  onChange(draftFace, draftColor);
                  setOpen(false);
                }}
                style={{
                  flex: 1,
                  minHeight: 46,
                  alignItems: "center",
                  justifyContent: "center",
                  borderRadius: 23,
                  backgroundColor: colors.muted,
                }}
              >
                <Text style={{ color: colors.foreground, fontSize: 15, fontWeight: "600" }}>
                  {t("avatarDone")}
                </Text>
              </Pressable>
              <Pressable
                accessibilityRole="button"
                onPress={() => setOpen(false)}
                style={{
                  minHeight: 46,
                  paddingHorizontal: 14,
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <Text style={{ color: colors.secondary, fontSize: 14 }}>{t("avatarCancel")}</Text>
              </Pressable>
            </View>
          </View>
        </SafeAreaView>
      </Modal>
    </>
  );
}
