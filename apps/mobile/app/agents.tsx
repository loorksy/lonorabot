// «إدارة الوكلاء» (the reference's agents route): every agent with its role and whether it is on,
// every group with its size, and «إنشاء مجموعة». A row opens its conversation until the agent and
// group pages exist (phase 4).
import { rowKey } from "@lonora/core";
import { Redirect, useRouter } from "expo-router";
import { ScrollView, Text, View } from "react-native";
import { CircleButton, PageHeader } from "../components/shell/chrome";
import { useOpenChat } from "../components/shell/chat-list";
import { Btn, Empty, GroupBox, Row, RowAvatar, SectionTitle, SkRows, useAgentRole } from "../components/shell/kit";
import { Icon } from "../components/shell/icon";
import { Loading } from "../components/ui";
import { agentsWord } from "../lib/i18n";
import { useLists } from "../lib/lists-state";
import { useSession } from "../lib/session";
import { useShellData } from "../lib/shell-data";
import { useTheme } from "../lib/theme";

export default function Agents() {
  const { ready, owner, t, locale } = useSession();
  const { c } = useTheme();
  const router = useRouter();
  const data = useShellData();
  const lists = useLists();
  const open = useOpenChat();
  const role = useAgentRole();
  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <PageHeader title={t("sh_fAgents")} actions={<CircleButton icon="plus" label={t("sh_createAgent")} onPress={() => router.push("/new")} />} />
      {!data.loaded ? (
        <SkRows count={5} />
      ) : (
        <ScrollView contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: 40 }}>
          <SectionTitle>{t("sh_fAgents")}</SectionTitle>
          <GroupBox>
            {data.agents.map((agent, index) => {
              const row = lists.rows.find((candidate) => candidate.key === rowKey("agent", agent.id));
              return (
                <Row
                  key={agent.id}
                  testID={`agent-row-${agent.id}`}
                  last={index === data.agents.length - 1}
                  lead={row ? <RowAvatar row={row} agents={data.agents} size={44} /> : null}
                  title={agent.name}
                  sub={role(agent)}
                  trailing={
                    <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                      <View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: agent.paused ? c.muted : c["accent-ink"] }} />
                      <Text style={{ color: agent.paused ? c.muted : c["accent-ink"], fontSize: 12 }}>{agent.paused ? t("sh_paused") : t("sh_active")}</Text>
                      <Icon name="chev" size={18} color={c.faint} />
                    </View>
                  }
                  onPress={() => row && void open(row)}
                />
              );
            })}
          </GroupBox>
          <SectionTitle>{t("sh_fGroups")}</SectionTitle>
          {data.groups.length ? (
            <GroupBox>
              {data.groups.map((group, index) => {
                const row = lists.rows.find((candidate) => candidate.key === rowKey("group", group.id));
                return (
                  <Row
                    key={group.id}
                    last={index === data.groups.length - 1}
                    lead={<Icon name="users" size={22} color={c.muted} />}
                    title={String(group.payload.name)}
                    trailing={
                      <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                        <Text style={{ color: c.muted, fontSize: 14 }}>{agentsWord(locale, group.payload.member_ids.length)}</Text>
                        <Icon name="chev" size={18} color={c.faint} />
                      </View>
                    }
                    onPress={() => row && void open(row)}
                  />
                );
              })}
            </GroupBox>
          ) : (
            <Empty>{t("sh_noGroupsYet")}</Empty>
          )}
          <Btn full variant="outline" label={t("sh_createGroup")} onPress={() => router.push("/new-group")} />
        </ScrollView>
      )}
    </View>
  );
}
