// «محادثة جديدة»: a new agent or group, then the agents and the groups that already exist, and
// «إدارة الوكلاء». Rows open the conversation; the sheet reads the live data.
import { rowKey } from "@lonora/core";
import { useRouter } from "expo-router";
import { Text, View } from "react-native";
import { useLists } from "../../lib/lists-state";
import { useSession } from "../../lib/session";
import { useShellData } from "../../lib/shell-data";
import { useTheme } from "../../lib/theme";
import { useOpenChat } from "./chat-list";
import { Btn, GroupBox, IconDisc, Row, RowAvatar, SectionTitle, useAgentRole } from "./kit";
import { useSheets } from "./sheets";

function Body() {
  const { c } = useTheme();
  const { t } = useSession();
  const data = useShellData();
  const lists = useLists();
  const sheets = useSheets();
  const router = useRouter();
  const open = useOpenChat();
  const role = useAgentRole();
  const go = (path: "/new-group" | "/agents") => {
    sheets.close();
    router.push(path);
  };
  const rowFor = (kind: "agent" | "group", id: string) =>
    lists.rows.find((row) => row.key === rowKey(kind, id));
  return (
    <View>
      <GroupBox>
        <Row
          last
          lead={<IconDisc name="users" />}
          title={t("sh_newGroup")}
          sub={t("sh_newGroupSub")}
          onPress={() => go("/new-group")}
        />
      </GroupBox>
      <SectionTitle>{t("sh_fAgents")}</SectionTitle>
      <GroupBox>
        {data.agents.map((agent, index) => {
          const row = rowFor("agent", agent.id);
          return (
            <Row
              key={agent.id}
              testID={`new-chat-agent-${agent.id}`}
              last={index === data.agents.length - 1}
              lead={row ? <RowAvatar row={row} agents={data.agents} size={44} /> : null}
              title={agent.name}
              sub={role(agent)}
              trailing={
                agent.paused ? (
                  <Text style={{ color: c.muted, fontSize: 12 }}>{t("sh_paused")}</Text>
                ) : null
              }
              onPress={() => {
                sheets.close();
                if (row) void open(row);
              }}
            />
          );
        })}
      </GroupBox>
      {data.groups.length ? (
        <>
          <SectionTitle>{t("sh_fGroups")}</SectionTitle>
          <GroupBox>
            {data.groups.map((group, index) => {
              const row = rowFor("group", group.id);
              return (
                <Row
                  key={group.id}
                  last={index === data.groups.length - 1}
                  lead={row ? <RowAvatar row={row} agents={data.agents} size={44} /> : null}
                  title={String(group.payload.name)}
                  sub={String((group.payload as { purpose?: string }).purpose ?? "")}
                  onPress={() => {
                    sheets.close();
                    if (row) void open(row);
                  }}
                />
              );
            })}
          </GroupBox>
        </>
      ) : null}
      <View style={{ alignItems: "center", paddingVertical: 8 }}>
        <Btn variant="ghost" label={t("sh_manageAgents")} onPress={() => go("/agents")} />
      </View>
    </View>
  );
}

export function useNewChatSheet() {
  const sheets = useSheets();
  const { t } = useSession();
  return () => sheets.open({ id: "new-chat", title: t("sh_newChat"), body: <Body /> });
}
