import { Redirect, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { AppState, ScrollView, Text, View } from "react-native";
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
type Running = {
  listed_at: string | null;
  stale: boolean;
  processes: Process[];
  stopping_all: boolean;
};

/** How often the open screen asks again (the Gateway lists the workspace every 10 s). */
const REFRESH_MS = 4000;
/** The start, with its day: a background process may have started days ago. */
const when = (iso: string, locale: string) =>
  new Date(iso).toLocaleString(locale === "ar" ? "ar" : "en-GB", {
    dateStyle: "short",
    timeStyle: "short",
  });
/** A command line is left to right inside an Arabic screen (Unicode isolate). */
const isolated = (text: string) => `\u2066${text}\u2069`;

/* «ما يعمل الآن» (mandate 7.1.5): every process in the owner's workspace with the agent that
   started it; one tap stops one process, one tap stops all of them. */
export default function RunningScreen() {
  const { ready, owner, t, rtl, locale, errorText } = useSession();
  const [view, setView] = useState<Running | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [asked, setAsked] = useState<Set<string>>(new Set());
  const load = useCallback(() => {
    void api
      .get<Running>("/workspace/running")
      .then((value) => {
        // Each answer says what is being stopped; taps it has seen are no longer pending.
        setView(value);
        setAsked(new Set());
        setError(null);
      })
      .catch((cause) => setError(errorText(cause)));
  }, [errorText]);
  useFocusEffect(
    useCallback(() => {
      if (!owner) return;
      load();
      const timer = setInterval(() => {
        if (AppState.currentState === "active") load();
      }, REFRESH_MS);
      return () => clearInterval(timer);
    }, [owner, load]),
  );
  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;

  const processes = view?.processes ?? [];
  const stopAll = (view?.stopping_all ?? false) || asked.has("all");
  // An out-of-date list (the workspace has not answered for a minute) takes no stop.
  const stale = view?.stale ?? false;
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
            disabled={!processes.length || stopAll || stale}
            onPress={() => send("/workspace/running/stop-all", {}, "all")}
          />
        </View>
        {stale && view?.listed_at ? (
          <Text
            testID="running-stale"
            accessibilityRole="alert"
            style={{ color: colors.secondary, textAlign: rtl ? "right" : "left" }}
          >
            {fill(t("running_stale"), when(view.listed_at, locale))}
          </Text>
        ) : null}
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
                    title={item.command ? isolated(item.command) : t("running_noCommand")}
                    detail={
                      item.started_at
                        ? fill(t("running_started"), when(item.started_at, locale))
                        : undefined
                    }
                    value={stopping ? t("running_stopping") : undefined}
                    trailing={
                      stopping ? null : (
                        <Button
                          secondary
                          label={t("running_stop")}
                          accessibilityLabel={fill(t("running_stopOne"), item.command)}
                          disabled={stale}
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
