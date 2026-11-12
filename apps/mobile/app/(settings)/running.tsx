import { Redirect, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { ScrollView, Text, View } from "react-native";
import { SettingsGroup, SettingsRow } from "../../components/settings-group";
import { SheetHeader } from "../../components/sheet-header";
import { Button, colors, ErrorNotice, Loading, Screen } from "../../components/ui";
import { api } from "../../lib/api";
import { fill } from "../../lib/i18n";
import { useSession } from "../../lib/session";

type Process = {
  pid: number;
  agent_id: string;
  agent_name: string;
  command: string;
  started_at: string | null;
  stopping: boolean;
};
type Running = { listed_at: string | null; processes: Process[]; stopping_all: boolean };

/** How often the open screen asks again (the Gateway lists the workspace every 10 s). */
const REFRESH_MS = 4000;
const clock = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });

/* «ما يعمل الآن» (mandate 7.1.5): every process in the owner's workspace with the agent that
   started it; one tap stops one process, one tap stops all of them. */
export default function RunningScreen() {
  const { ready, owner, t, rtl, errorText } = useSession();
  const [view, setView] = useState<Running | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [asked, setAsked] = useState<Set<string>>(new Set());
  const load = useCallback(() => {
    void api
      .get<Running>("/workspace/running")
      .then((value) => {
        setView(value);
        setError(null);
      })
      .catch((cause) => setError(errorText(cause)));
  }, [errorText]);
  useFocusEffect(
    useCallback(() => {
      if (!owner) return;
      load();
      const timer = setInterval(load, REFRESH_MS);
      return () => clearInterval(timer);
    }, [owner, load]),
  );
  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;

  const processes = view?.processes ?? [];
  const stopAll = (view?.stopping_all ?? false) || asked.has("all");
  const key = (item: Process) => `${item.agent_id}:${item.pid}`;
  const send = (path: string, body: object, mark: string) => {
    setAsked((current) => new Set(current).add(mark));
    void api
      .post(path, body)
      .then(load)
      .catch((cause) => {
        setAsked((current) => {
          const next = new Set(current);
          next.delete(mark);
          return next;
        });
        setError(errorText(cause));
      });
  };
  const agents = [...new Set(processes.map((item) => item.agent_id))];
  return (
    <Screen>
      <SheetHeader title={t("running_title")} />
      <ScrollView contentContainerStyle={{ padding: 20, gap: 20 }}>
        <ErrorNotice text={error} />
        <View testID="stop-all">
          <Button
            label={stopAll ? t("running_stoppingAll") : t("running_stopAll")}
            disabled={!processes.length || stopAll}
            onPress={() => send("/workspace/running/stop-all", {}, "all")}
          />
        </View>
        {view && !processes.length ? (
          <Text
            testID="running-empty"
            style={{ color: colors.secondary, textAlign: rtl ? "right" : "left" }}
          >
            {t("running_empty")}
          </Text>
        ) : null}
        {agents.map((agentId) => {
          const own = processes.filter((item) => item.agent_id === agentId);
          return (
            <SettingsGroup key={agentId} title={own[0]?.agent_name ?? ""}>
              {own.map((item) => {
                const stopping = item.stopping || stopAll || asked.has(key(item));
                return (
                  <SettingsRow
                    key={key(item)}
                    testID="running-process"
                    icon="activity"
                    title={item.command || t("running_noCommand")}
                    detail={
                      item.started_at
                        ? fill(t("running_started"), clock(item.started_at))
                        : undefined
                    }
                    value={stopping ? t("running_stopping") : undefined}
                    trailing={
                      stopping ? null : (
                        <Button
                          secondary
                          label={t("running_stop")}
                          onPress={() =>
                            send(
                              "/workspace/running/stop",
                              { pid: item.pid, agent_id: item.agent_id },
                              key(item),
                            )
                          }
                        />
                      )
                    }
                  />
                );
              })}
            </SettingsGroup>
          );
        })}
        <Text
          style={{ color: colors.secondary, lineHeight: 22, textAlign: rtl ? "right" : "left" }}
        >
          {t("running_note")}
        </Text>
      </ScrollView>
    </Screen>
  );
}
