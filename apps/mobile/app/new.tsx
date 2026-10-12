import { Redirect, useRouter } from "expo-router";
import { useState } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import { AgentAvatar } from "../components/AgentAvatar";
import { Button, colors, ErrorNotice, Field, Header, Loading, Screen } from "../components/ui";
import { api } from "../lib/api";
import { useSession } from "../lib/session";
import type { Agent, Thread } from "../lib/types";

const palette = ["#FF8A4C", "#A78BFA", "#5DA8FF", "#7ED6A0", "#F7CF67", "#F27BA8"];
export default function NewAgent() {
  const { ready, owner, rtl, t, errorText } = useSession();
  const router = useRouter();
  const [name, setName] = useState("");
  const [color, setColor] = useState(palette[0]);
  const [avatar, setAvatar] = useState("orb");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      const agent = await api.post<Agent>("/agents", { name: name.trim(), avatar, color });
      const thread = await api.post<Thread>(
        `/agents/${encodeURIComponent(agent.id)}/conversation`,
        {},
      );
      router.replace({ pathname: "/thread", params: { id: thread.id } });
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Screen>
      <Header
        title={t("newAgent")}
        left={<Button label={t("back")} secondary onPress={() => router.back()} />}
      />
      <ScrollView
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{ padding: 24, gap: 24 }}
      >
        <View style={{ alignItems: "center" }}>
          <AgentAvatar color={color} variant={avatar} size={100} />
        </View>
        <Field label={t("name")} value={name} onChangeText={setName} maxLength={80} autoFocus />
        <Text style={{ color: colors.secondary, textAlign: rtl ? "right" : "left" }}>
          {t("color")}
        </Text>
        <View style={{ flexDirection: rtl ? "row-reverse" : "row", flexWrap: "wrap", gap: 12 }}>
          {palette.map((value) => (
            <Pressable
              key={value}
              accessibilityRole="radio"
              accessibilityState={{ checked: color === value }}
              accessibilityLabel={value}
              onPress={() => setColor(value)}
              style={{
                width: 44,
                height: 44,
                borderRadius: 22,
                backgroundColor: value,
                borderWidth: color === value ? 3 : 0,
                borderColor: colors.foreground,
              }}
            />
          ))}
        </View>
        <Text style={{ color: colors.secondary, textAlign: rtl ? "right" : "left" }}>
          {t("avatar")}
        </Text>
        <View style={{ flexDirection: rtl ? "row-reverse" : "row", gap: 18 }}>
          {["orb", "square"].map((value) => (
            <Pressable
              key={value}
              accessibilityRole="radio"
              accessibilityState={{ checked: avatar === value }}
              accessibilityLabel={`${t("avatar")} ${value}`}
              onPress={() => setAvatar(value)}
              style={{
                padding: 8,
                borderRadius: 14,
                backgroundColor: avatar === value ? colors.accent : "transparent",
              }}
            >
              <AgentAvatar color={color} variant={value} />
            </Pressable>
          ))}
        </View>
        <ErrorNotice text={error} />
        <Button
          label={busy ? t("connecting") : t("create")}
          onPress={() => void create()}
          disabled={busy || !name.trim()}
        />
      </ScrollView>
    </Screen>
  );
}
