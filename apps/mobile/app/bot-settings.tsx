// Agent profile sheet follows Tampletgrok's native profile structure; see NOTICE.

import type { Agent } from "@lonora/contracts";
import { Redirect, useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { ScrollView, Switch, Text, View } from "react-native";
import { BotAvatar } from "../components/bot-avatar";
import { SheetHeader } from "../components/sheet-header";
import { Button, colors, ErrorNotice, Field, Loading, Screen, styles } from "../components/ui";
import { agents } from "../lib/agents";
import { api } from "../lib/api";
import { useSession } from "../lib/session";

type Memory = { content: string; version: number };
export default function BotSettings() {
  const { botId } = useLocalSearchParams<{ botId: string }>();
  const { ready, owner, rtl, t, errorText } = useSession();
  const router = useRouter();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [memory, setMemory] = useState<Memory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    if (!owner || !botId) return;
    let live = true;
    void agents
      .list()
      .then((rows) => {
        if (live) {
          const value = rows.find((row) => row.id === botId);
          if (value) setAgent(value);
          else setError(t("agentMissing"));
        }
      })
      .catch((reason) => {
        if (live) setError(errorText(reason));
      });
    void api
      .get<Memory>(`/agents/${encodeURIComponent(botId)}/memory`)
      .then((value) => {
        if (live) setMemory(value);
      })
      .catch((reason) => {
        if (live) setError(errorText(reason));
      });
    return () => {
      live = false;
    };
  }, [botId, owner, errorText, t]);
  const save = async () => {
    if (!agent) return;
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      setAgent(
        await agents.update(agent.id, {
          name: agent.name.trim(),
          avatar: agent.avatar,
          color: agent.color,
          instructions: agent.instructions,
          paused: agent.paused,
        }),
      );
      if (memory)
        setMemory(
          await api.put<Memory>(`/agents/${encodeURIComponent(botId)}/memory`, {
            content: memory.content,
            version: memory.version,
          }),
        );
      setSaved(true);
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setBusy(false);
    }
  };
  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  return (
    <Screen>
      <SheetHeader
        title={t("agentSettings")}
        onClose={() => router.back()}
        action={t("save")}
        onAction={() => void save()}
        disabled={busy || !agent?.name.trim()}
      />
      <ErrorNotice text={error} />
      {agent ? (
        <ScrollView
          contentContainerStyle={{ padding: 20, gap: 22 }}
          keyboardShouldPersistTaps="handled"
        >
          <View style={{ alignItems: "center" }}>
            <BotAvatar color={agent.color} variant={agent.avatar} size={90} />
          </View>
          <Field
            label={t("name")}
            value={agent.name}
            maxLength={80}
            onChangeText={(name) => {
              setAgent({ ...agent, name });
              setSaved(false);
            }}
          />
          <Field
            label={t("color")}
            value={agent.color}
            maxLength={7}
            autoCapitalize="none"
            onChangeText={(color) => setAgent({ ...agent, color })}
            style={{ writingDirection: "ltr", textAlign: "left" }}
          />
          <View style={{ flexDirection: rtl ? "row-reverse" : "row", gap: 12 }}>
            {["orb", "square"].map((avatar) => (
              <Button
                key={avatar}
                label={t(avatar === "orb" ? "avatarRound" : "avatarSquare")}
                secondary={agent.avatar !== avatar}
                onPress={() => setAgent({ ...agent, avatar })}
              />
            ))}
          </View>
          <Field
            label={t("instructions")}
            value={agent.instructions}
            onChangeText={(instructions) => setAgent({ ...agent, instructions })}
            maxLength={16000}
            multiline
            style={{ minHeight: 130, textAlignVertical: "top" }}
          />
          <View
            style={[
              styles.card,
              { flexDirection: rtl ? "row-reverse" : "row", alignItems: "center" },
            ]}
          >
            <Text style={{ color: colors.foreground, flex: 1, textAlign: rtl ? "right" : "left" }}>
              {t("paused")}
            </Text>
            <Switch
              accessibilityLabel={t("paused")}
              value={agent.paused}
              onValueChange={(paused) => setAgent({ ...agent, paused })}
            />
          </View>
          {memory ? (
            <View style={{ gap: 8 }}>
              <Field
                label={t("memory")}
                value={memory.content}
                onChangeText={(content) => setMemory({ ...memory, content })}
                maxLength={30000}
                multiline
                style={{ minHeight: 180, textAlignVertical: "top" }}
              />
              <Text
                style={{
                  color: colors.secondary,
                  lineHeight: 22,
                  textAlign: rtl ? "right" : "left",
                }}
              >
                {t("memoryHint")}
              </Text>
            </View>
          ) : null}
          {saved ? (
            <Text style={{ color: "#7ED6A0", textAlign: "center" }}>{t("saved")}</Text>
          ) : null}
          <Button
            label={t("routines")}
            secondary
            onPress={() => router.push({ pathname: "/routine", params: { botId } })}
          />
        </ScrollView>
      ) : error ? null : (
        <Loading />
      )}
    </Screen>
  );
}
