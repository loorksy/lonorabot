import { Redirect, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import { NativeSymbol } from "../components/native-symbol";
import { SettingsGroup } from "../components/settings-group";
import { SheetHeader } from "../components/sheet-header";
import { Button, colors, ErrorNotice, Field, Loading, Screen, styles } from "../components/ui";
import { api } from "../lib/api";
import { fill } from "../lib/i18n";
import { useSession } from "../lib/session";

type ProfileLine = {
  text: string;
  origin: "you_said" | "observed" | "earlier";
  author_agent_name: string | null;
  created_at: string | null;
};
type ProfileLines = { version: number; lines: ProfileLine[] };

// A profile line's leading markdown bullet ("- " or "* "), kept when it is corrected.
const bullet = (text: string) => /^[-*]\s+/.exec(text)?.[0];

/* «ما أعرفه عنك» (8.4): every line of the owner profile with its origin, what the owner said or
   what was observed. The owner corrects or deletes a line; the server records it as his word. */
export default function OwnerKnowledge() {
  const { ready, owner, t, rtl, errorText } = useSession();
  const [known, setKnown] = useState<ProfileLines | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ text: string; value: string } | null>(null);
  const [busy, setBusy] = useState(false);
  useFocusEffect(
    useCallback(() => {
      if (!owner) return;
      let live = true;
      void api
        .get<ProfileLines>("/owner/profile/lines")
        .then((value) => {
          if (live) {
            setKnown(value);
            setError(null);
          }
        })
        .catch((cause) => {
          if (live) setError(errorText(cause));
        });
      return () => {
        live = false;
      };
    }, [owner, errorText]),
  );
  const correct = (text: string, replacement: string | null) => {
    if (!known || busy) return;
    setBusy(true);
    void api
      .post<ProfileLines>("/owner/profile/lines", { version: known.version, text, replacement })
      .then((value) => {
        setKnown(value);
        setEditing(null);
        setError(null);
      })
      .catch((cause) => setError(errorText(cause)))
      .finally(() => setBusy(false));
  };
  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  const origin = (line: ProfileLine) =>
    line.origin === "you_said"
      ? t("youSaid")
      : line.origin === "earlier"
        ? t("earlier")
        : line.author_agent_name
          ? fill(t("observedBy"), { name: line.author_agent_name })
          : t("observed");
  const align = rtl ? "right" : "left";
  return (
    <Screen>
      <SheetHeader title={t("whatIKnow")} />
      <ScrollView contentContainerStyle={{ padding: 20, gap: 16 }}>
        <ErrorNotice text={error} />
        <Text style={{ color: colors.secondary, fontSize: 14, textAlign: align }}>
          {t("whatIKnowHint")}
        </Text>
        {!known ? (
          <Text style={{ color: colors.secondary, textAlign: align }}>{t("connecting")}</Text>
        ) : known.lines.length === 0 ? (
          <Text style={{ color: colors.secondary, textAlign: align }}>{t("nothingKnown")}</Text>
        ) : (
          <SettingsGroup>
            {known.lines.map((line) => (
              <View
                key={line.text}
                testID="known-line"
                style={{ padding: 14, gap: 8, borderBottomWidth: 0.5, borderColor: colors.accent }}
              >
                {editing?.text === line.text ? (
                  <View style={{ gap: 10 }}>
                    <Field
                      label={t("correctFact")}
                      value={editing.value}
                      maxLength={2000}
                      onChangeText={(value) => setEditing({ ...editing, value })}
                    />
                    <View style={{ flexDirection: rtl ? "row-reverse" : "row", gap: 10 }}>
                      <Button
                        label={t("saveCorrection")}
                        disabled={busy || !editing.value.trim()}
                        onPress={() =>
                          correct(line.text, (bullet(line.text) ?? "") + editing.value.trim())
                        }
                      />
                      <Button
                        label={t("cancelCorrection")}
                        secondary
                        onPress={() => setEditing(null)}
                      />
                    </View>
                  </View>
                ) : (
                  <View style={{ flexDirection: rtl ? "row-reverse" : "row", gap: 12 }}>
                    <View style={{ flex: 1, gap: 4 }}>
                      <Text
                        style={{
                          color: colors.foreground,
                          fontSize: 16,
                          textAlign: align,
                          writingDirection: "auto",
                        }}
                      >
                        {line.text.replace(/^[-*]\s*/, "")}
                      </Text>
                      <Text style={[styles.label, { textAlign: align }]}>{origin(line)}</Text>
                    </View>
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel={t("correctFact")}
                      hitSlop={10}
                      onPress={() =>
                        setEditing({
                          text: line.text,
                          value: line.text.slice(bullet(line.text)?.length ?? 0),
                        })
                      }
                    >
                      <NativeSymbol name="edit" size={18} />
                    </Pressable>
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel={t("deleteFact")}
                      hitSlop={10}
                      disabled={busy}
                      onPress={() => correct(line.text, null)}
                    >
                      <NativeSymbol name="close" size={18} />
                    </Pressable>
                  </View>
                )}
              </View>
            ))}
          </SettingsGroup>
        )}
      </ScrollView>
    </Screen>
  );
}
