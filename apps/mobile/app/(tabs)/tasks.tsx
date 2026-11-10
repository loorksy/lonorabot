// المهام: the agents' runs as they are now. The task pages themselves arrive with phase 4.
import { activeStatuses, runStatusText } from "@lonora/core";
import { Redirect, useRouter } from "expo-router";
import { ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { AgentFace, Empty, GroupBox, Row } from "../../components/shell/kit";
import { Loading } from "../../components/ui";
import { useSession } from "../../lib/session";
import { useShellData } from "../../lib/shell-data";
import { useTheme } from "../../lib/theme";

export default function Tasks() {
  const { ready, owner, t, rtl, locale } = useSession();
  const { c } = useTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const data = useShellData();
  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  const runs = data.runs.filter((run) => data.agents.some((agent) => agent.id === run.agent_id));
  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <Text
        accessibilityRole="header"
        style={{
          color: c.text,
          fontSize: 28,
          fontWeight: "700",
          paddingHorizontal: 20,
          paddingTop: insets.top + 14,
          paddingBottom: 6,
          textAlign: rtl ? "right" : "left",
        }}
      >
        {t("sh_tasks")}
      </Text>
      <ScrollView contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: 130 }}>
        {runs.length ? (
          <GroupBox>
            {runs.map((run, index) => {
              const agent = data.agents.find((value) => value.id === run.agent_id);
              if (!agent) return null;
              return (
                <Row
                  key={run.id}
                  last={index === runs.length - 1}
                  lead={
                    <AgentFace
                      agent={agent}
                      working={activeStatuses.includes(run.status)}
                      size={44}
                    />
                  }
                  title={agent.name}
                  sub={runStatusText(run.status, locale)}
                  onPress={() =>
                    router.push({ pathname: "/thread", params: { id: run.thread_id } })
                  }
                />
              );
            })}
          </GroupBox>
        ) : (
          <Empty icon="task">{t("sh_noTasksSaved")}</Empty>
        )}
      </ScrollView>
    </View>
  );
}
