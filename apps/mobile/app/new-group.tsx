import type { Agent, Group } from "@lonora/contracts";
import { Redirect, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { ScrollView, Text } from "react-native";
import { BotMemberPicker } from "../components/bot-member-picker";
import { SheetHeader } from "../components/sheet-header";
import { Button, colors, ErrorNotice, Field, Loading, Screen } from "../components/ui";
import { api } from "../lib/api";
import { useSession } from "../lib/session";

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
      <SheetHeader title={t("newGroup")} />
      <ScrollView
        contentContainerStyle={{ padding: 24, gap: 20 }}
        keyboardShouldPersistTaps="handled"
      >
        <Field label={t("name")} value={name} onChangeText={setName} maxLength={80} autoFocus />
        <Text style={{ color: colors.secondary, textAlign: rtl ? "right" : "left" }}>
          {t("chooseMembers")}
        </Text>
        <BotMemberPicker agents={agents} selected={members} onChange={setMembers} disabled={busy} />
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
