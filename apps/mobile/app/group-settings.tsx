// Native group membership sheet adapted from Tampletgrok; see NOTICE.

import type { Agent, Group } from "@lonora/contracts";
import { Redirect, useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { ScrollView, Text } from "react-native";
import { BotMemberPicker } from "../components/bot-member-picker";
import { SheetHeader } from "../components/sheet-header";
import { colors, ErrorNotice, Field, Loading, Screen } from "../components/ui";
import { agents as agentApi } from "../lib/agents";
import { groups } from "../lib/groups";
import { useSession } from "../lib/session";

export default function GroupSettings() {
  const { groupId } = useLocalSearchParams<{ groupId: string }>();
  const router = useRouter();
  const { ready, owner, rtl, t, errorText } = useSession();
  const [group, setGroup] = useState<Group | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!owner || !groupId) return;
    let live = true;
    void Promise.all([groups.get(groupId), agentApi.list()])
      .then(([row, roster]) => {
        if (live) {
          setGroup(row);
          setAgents(roster);
        }
      })
      .catch((reason) => {
        if (live) setError(errorText(reason));
      });
    return () => {
      live = false;
    };
  }, [groupId, owner, errorText]);
  const save = async () => {
    if (!group) return;
    setBusy(true);
    setError(null);
    try {
      setGroup(await groups.update(group, { ...group.payload, name: group.payload.name.trim() }));
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
        title={t("groupSettings")}
        onClose={() => router.back()}
        action={t("save")}
        onAction={() => void save()}
        disabled={busy || !group?.payload.name.trim() || !group.payload.member_ids.length}
      />
      <ErrorNotice text={error} />
      {group ? (
        <ScrollView contentContainerStyle={{ padding: 20, gap: 16 }}>
          <Field
            label={t("name")}
            value={group.payload.name}
            maxLength={80}
            onChangeText={(name) => {
              setGroup({ ...group, payload: { ...group.payload, name } });
              setSaved(false);
            }}
          />
          <Text style={{ color: colors.secondary, textAlign: rtl ? "right" : "left" }}>
            {t("members")}
          </Text>
          <BotMemberPicker
            agents={agents}
            selected={group.payload.member_ids}
            disabled={busy}
            onChange={(member_ids) => {
              setGroup({ ...group, payload: { ...group.payload, member_ids } });
              setSaved(false);
            }}
          />
          <Text
            style={{ color: colors.secondary, lineHeight: 24, textAlign: rtl ? "right" : "left" }}
          >
            {t("participation")}: {t("mentionsOrLead")}
          </Text>
          {saved ? (
            <Text style={{ color: colors.success, textAlign: "center" }}>{t("saved")}</Text>
          ) : null}
        </ScrollView>
      ) : error ? null : (
        <Loading />
      )}
    </Screen>
  );
}
