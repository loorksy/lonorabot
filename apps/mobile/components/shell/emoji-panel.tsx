// The emoji panel of «قائمة جديدة» (WhatsApp): recents, the eight sections of the reference's data
// with a tab bar, and a search over the Arabic and English names. Recents are this device's.
import { foldSearch } from "@lonora/core";
import { useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { EMOJI_DATA } from "../../lib/emoji-data";
import type { Label } from "../../lib/i18n";
import { useSession } from "../../lib/session";
import { loadSetting, saveSetting } from "../../lib/storage";
import { useTheme } from "../../lib/theme";
import { Icon, type IconName } from "./icon";

type Emoji = { e: string; ar: string; en: string };
const parse = (section: string): Emoji[] =>
  section
    .split("|")
    .map((entry) => entry.split("~"))
    .filter((parts) => parts[0])
    .map(([e, ar, en]) => ({ e, ar: ar ?? "", en: en ?? "" }));
const TABS: { icon: IconName; label: Label }[] = [
  { icon: "clock", label: "sh_emoRecent" },
  { icon: "smile", label: "sh_emoSmile" },
  { icon: "bot", label: "sh_emoLeaf" },
  { icon: "heart", label: "sh_emoCup" },
  { icon: "task", label: "sh_emoBall" },
  { icon: "trend", label: "sh_emoCar" },
  { icon: "cpu", label: "sh_emoBulb" },
  { icon: "info", label: "sh_emoHash" },
  { icon: "pin", label: "sh_emoFlag" },
];
const RECENT = "lonora.emoji.recent";

export function EmojiPanel({
  onPick,
  onDelete,
}: {
  onPick: (emoji: string) => void;
  onDelete: () => void;
}) {
  const { c } = useTheme();
  const { t, rtl } = useSession();
  const data = useMemo(() => EMOJI_DATA.map(parse), []);
  const [section, setSection] = useState(1);
  const [recent, setRecent] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  useEffect(() => {
    void loadSetting(RECENT)
      .then((stored) => {
        const parsed: unknown = stored ? JSON.parse(stored) : [];
        if (Array.isArray(parsed))
          setRecent(
            parsed.filter((value): value is string => typeof value === "string").slice(0, 24),
          );
      })
      .catch(() => undefined);
  }, []);
  const pick = (emoji: string) => {
    onPick(emoji);
    // A functional update: two quick taps must not overwrite each other.
    setRecent((current) => {
      const next = [emoji, ...current.filter((value) => value !== emoji)].slice(0, 24);
      void saveSetting(RECENT, JSON.stringify(next)).catch(() => undefined);
      return next;
    });
  };
  const q = foldSearch(query);
  const results = useMemo(
    () =>
      q
        ? data
            .flat()
            .filter((emoji) => foldSearch(`${emoji.ar} ${emoji.en}`).includes(q))
            .slice(0, 120)
        : [],
    [data, q],
  );
  const shown = q
    ? results.map((emoji) => emoji.e)
    : section === 0
      ? recent
      : (data[section - 1] ?? []).map((emoji) => emoji.e);
  return (
    <View
      accessibilityLabel={t("sh_emojis")}
      style={{
        height: 300,
        backgroundColor: c.raised,
        borderTopWidth: 1,
        borderTopColor: c.line,
        marginHorizontal: -16,
      }}
    >
      <View
        style={{
          flexDirection: rtl ? "row-reverse" : "row",
          alignItems: "center",
          gap: 8,
          paddingHorizontal: 12,
          paddingVertical: 6,
        }}
      >
        <View
          style={{
            flex: 1,
            height: 36,
            borderRadius: 18,
            backgroundColor: c.fill,
            justifyContent: "center",
          }}
        >
          <TextInput
            accessibilityLabel={t("sh_searchEmoji")}
            placeholder={t("sh_searchEmoji")}
            placeholderTextColor={c.muted}
            value={query}
            onChangeText={setQuery}
            style={{
              color: c.text,
              paddingHorizontal: 14,
              fontSize: 14,
              textAlign: rtl ? "right" : "left",
            }}
          />
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t("sh_delete")}
          onPress={onDelete}
          style={{ width: 36, height: 36, alignItems: "center", justifyContent: "center" }}
        >
          <Icon name="back" size={20} color={c.text} />
        </Pressable>
      </View>
      <ScrollView
        contentContainerStyle={{ flexDirection: "row", flexWrap: "wrap", paddingHorizontal: 8 }}
        keyboardShouldPersistTaps="always"
      >
        {shown.length ? (
          shown.map((emoji) => (
            <Pressable
              key={emoji}
              accessibilityRole="button"
              accessibilityLabel={emoji}
              onPress={() => pick(emoji)}
              style={{
                width: "12.5%",
                aspectRatio: 1,
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <Text style={{ fontSize: 26 }}>{emoji}</Text>
            </Pressable>
          ))
        ) : q ? (
          <Text style={{ color: c.muted, padding: 20 }}>{t("sh_emoNone")}</Text>
        ) : null}
      </ScrollView>
      <View
        accessibilityRole="tablist"
        style={{
          flexDirection: rtl ? "row-reverse" : "row",
          justifyContent: "space-around",
          borderTopWidth: 1,
          borderTopColor: c.line,
          paddingVertical: 6,
        }}
      >
        {TABS.map(({ icon, label }, index) => (
          <Pressable
            key={label}
            accessibilityRole="tab"
            accessibilityLabel={t(label)}
            accessibilityState={{ selected: section === index && !q }}
            onPress={() => {
              setQuery("");
              setSection(index);
            }}
            style={{
              width: 36,
              height: 34,
              alignItems: "center",
              justifyContent: "center",
              borderRadius: 17,
              backgroundColor: section === index && !q ? c.fill : "transparent",
            }}
          >
            <Icon name={icon} size={20} color={section === index && !q ? c.text : c.muted} />
          </Pressable>
        ))}
      </View>
    </View>
  );
}
