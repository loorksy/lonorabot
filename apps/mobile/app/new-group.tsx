import { Redirect, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { Pressable, ScrollView, Text } from "react-native";
import { AgentAvatar } from "../components/AgentAvatar";
import { Button, colors, ErrorNotice, Field, Header, Loading, Screen } from "../components/ui";
import { api } from "../lib/api";
import { useSession } from "../lib/session";
import type { Agent, Group } from "../lib/types";

export default function NewGroup() {
  const { ready, owner, rtl, t, errorText } = useSession();
  const router = useRouter();
  const [name, setName] = useState("");
  const [agents, setAgents] = useState<Agent[]>([]);
  const [members, setMembers] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (owner)
      void api
        .get<Agent[]>("/agents")
        .then(setAgents)
        .catch((reason) => setError(errorText(reason)));
  }, [owner, errorText]);
  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  const create = async () => {
    setBusy(true);
    setError(null);
    try {
      const group = await api.post<Group & { thread_id: string }>("/groups/create", {
        name: name.trim(),
        member_ids: members,
        participation: "mentions_or_lead",
      });
      router.replace({ pathname: "/thread", params: { id: group.thread_id } });
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Screen>
      <Header
        title={t("newGroup")}
        left={<Button label={t("back")} secondary onPress={() => router.back()} />}
      />
      <ScrollView
        contentContainerStyle={{ padding: 24, gap: 20 }}
        keyboardShouldPersistTaps="handled"
      >
        <Field label={t("name")} value={name} onChangeText={setName} maxLength={80} autoFocus />
        <Text style={{ color: colors.secondary, textAlign: rtl ? "right" : "left" }}>
          {t("chooseMembers")}
        </Text>
        {agents.map((agent) => (
          <Pressable
            key={agent.id}
            accessibilityRole="checkbox"
            accessibilityState={{ checked: members.includes(agent.id) }}
            accessibilityLabel={agent.name}
            onPress={() =>
              setMembers((old) =>
                old.includes(agent.id)
                  ? old.filter((id) => id !== agent.id)
                  : old.length < 12
                    ? [...old, agent.id]
                    : old,
              )
            }
            style={{
              flexDirection: rtl ? "row-reverse" : "row",
              alignItems: "center",
              gap: 12,
              padding: 12,
              borderRadius: 14,
              backgroundColor: members.includes(agent.id) ? colors.accent : colors.muted,
            }}
          >
            <AgentAvatar color={agent.color} size={40} variant={agent.avatar} />
            <Text
              style={{
                color: colors.foreground,
                flex: 1,
                fontSize: 17,
                textAlign: rtl ? "right" : "left",
              }}
            >
              {agent.name}
            </Text>
            <Text style={{ color: colors.foreground }}>
              {members.includes(agent.id) ? "✓" : "○"}
            </Text>
          </Pressable>
        ))}
        <ErrorNotice text={error} />
        <Button
          label={busy ? t("connecting") : t("create")}
          onPress={() => void create()}
          disabled={busy || !name.trim() || !members.length}
        />
      </ScrollView>
    </Screen>
  );
}
