import type { Agent, Routine, Run } from "@lonora/contracts";
import { Redirect, useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { ScrollView, Switch, Text, View } from "react-native";
import { SheetHeader } from "../components/sheet-header";
import { Button, colors, ErrorNotice, Field, Loading, Screen, styles } from "../components/ui";
import { WorkingIndicator } from "../components/WorkingIndicator";
import { agents as agentApi } from "../lib/agents";
import { routines } from "../lib/routine";
import { useSession } from "../lib/session";

export default function RoutineScreen() {
  const { botId } = useLocalSearchParams<{ botId?: string }>();
  const { ready, owner, t, errorText, rtl } = useSession();
  const router = useRouter();
  const [rows, setRows] = useState<Routine[] | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selected, setSelected] = useState<Routine | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    const [list, roster] = await Promise.all([routines.list(botId), agentApi.list()]);
    setRows(list);
    setAgents(roster);
    setError(null);
  }, [botId]);
  useFocusEffect(
    useCallback(() => {
      if (!owner) return;
      let live = true;
      void Promise.all([routines.list(botId), agentApi.list()])
        .then(([list, roster]) => {
          if (live) {
            setRows(list);
            setAgents(roster);
            setError(null);
          }
        })
        .catch((cause) => {
          if (live) setError(errorText(cause));
        });
      return () => {
        live = false;
      };
    }, [owner, botId, errorText]),
  );
  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  return (
    <Screen>
      <SheetHeader
        title={t("routines")}
        onClose={selected ? () => setSelected(null) : undefined}
        action={!selected ? t("create") : undefined}
        onAction={() => setSelected("new")}
        disabled={!agents.length}
      />
      <ErrorNotice text={error} />
      {selected ? (
        <RoutineForm
          key={selected === "new" ? "new" : selected.id}
          routine={selected === "new" ? null : selected}
          agents={agents}
          initialAgent={botId}
          onSaved={async () => {
            await load();
            setSelected(null);
          }}
        />
      ) : rows === null && !error ? (
        <Loading />
      ) : (
        <ScrollView contentContainerStyle={{ padding: 20, gap: 16 }}>
          <Text
            style={{ color: colors.secondary, lineHeight: 24, textAlign: rtl ? "right" : "left" }}
          >
            {t("routineHint")}
          </Text>
          {rows?.map((row) => (
            <View key={row.id} style={styles.card}>
              <Text
                style={{
                  color: colors.foreground,
                  fontWeight: "600",
                  textAlign: rtl ? "right" : "left",
                }}
              >
                {agents.find((agent) => agent.id === row.agent_id)?.name}
              </Text>
              <Text style={{ color: colors.foreground, textAlign: rtl ? "right" : "left" }}>
                {row.prompt}
              </Text>
              <Text selectable style={{ color: colors.secondary }}>
                {row.cron ?? `${row.interval_seconds}s`} · {row.timezone}
              </Text>
              <Text style={{ color: colors.secondary }}>
                {t(row.enabled ? "enabled" : "paused")} · {t("nextRun")}:{" "}
                {new Date(row.next_run_at).toLocaleString()}
              </Text>
              <Button label={t("edit")} secondary onPress={() => setSelected(row)} />
              <RoutineHistory
                id={row.id}
                onThread={(id) => router.push({ pathname: "/thread", params: { id } })}
              />
            </View>
          ))}
          {rows?.length === 0 && (
            <Text style={{ color: colors.secondary }}>{t("emptyRoutines")}</Text>
          )}
          {error && (
            <Button
              label={t("retry")}
              secondary
              onPress={() => {
                void load().catch((cause) => setError(errorText(cause)));
              }}
            />
          )}
        </ScrollView>
      )}
    </Screen>
  );
}
function RoutineForm({
  routine,
  agents,
  initialAgent,
  onSaved,
}: {
  routine: Routine | null;
  agents: Agent[];
  initialAgent?: string;
  onSaved: () => Promise<void>;
}) {
  const { t, errorText, rtl } = useSession();
  const [agent, setAgent] = useState(routine?.agent_id ?? initialAgent ?? agents[0]?.id ?? "");
  const [prompt, setPrompt] = useState(routine?.prompt ?? "");
  const [enabled, setEnabled] = useState(routine?.enabled ?? true);
  const [mode, setMode] = useState<"interval" | "cron">(routine?.cron ? "cron" : "interval");
  const [minutes, setMinutes] = useState(String((routine?.interval_seconds ?? 3600) / 60));
  const [cron, setCron] = useState(routine?.cron ?? "0 9 * * 1-5");
  const [timezone, setTimezone] = useState(
    routine?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone,
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    setError(null);
    try {
      const input = {
        prompt: prompt.trim(),
        interval_seconds: mode === "interval" ? Number(minutes) * 60 : null,
        cron: mode === "cron" ? cron : null,
        timezone,
        enabled,
      };
      if (routine) await routines.update(routine, input);
      else await routines.create(agent, input);
      await onSaved();
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      setBusy(false);
    }
  }
  return (
    <ScrollView
      contentContainerStyle={{ padding: 20, gap: 16 }}
      keyboardShouldPersistTaps="handled"
    >
      <ErrorNotice text={error} />
      {!routine && (
        <View style={{ gap: 8 }}>
          {agents.map((row) => (
            <Button
              key={row.id}
              label={row.name}
              secondary={row.id !== agent}
              disabled={busy}
              onPress={() => setAgent(row.id)}
            />
          ))}
        </View>
      )}
      <Field
        label={t("routineTask")}
        value={prompt}
        onChangeText={setPrompt}
        multiline
        maxLength={8000}
        style={{ minHeight: 120, textAlignVertical: "top" }}
      />
      <View style={{ flexDirection: rtl ? "row-reverse" : "row", gap: 10 }}>
        <Button
          label={t("interval")}
          secondary={mode !== "interval"}
          onPress={() => setMode("interval")}
        />
        <Button label={t("cron")} secondary={mode !== "cron"} onPress={() => setMode("cron")} />
      </View>
      {mode === "interval" ? (
        <Field
          label={t("minutes")}
          value={minutes}
          onChangeText={setMinutes}
          keyboardType="numeric"
        />
      ) : (
        <Field label={t("cron")} value={cron} onChangeText={setCron} autoCapitalize="none" />
      )}
      <Field
        label={t("timezone")}
        value={timezone}
        onChangeText={setTimezone}
        autoCapitalize="none"
      />
      <View
        style={{
          flexDirection: rtl ? "row-reverse" : "row",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <Text style={{ color: colors.foreground }}>{t("enabled")}</Text>
        <Switch accessibilityLabel={t("enabled")} value={enabled} onValueChange={setEnabled} />
      </View>
      <Button
        label={t("save")}
        disabled={
          busy ||
          !agent ||
          !prompt.trim() ||
          (mode === "interval" && !(Number(minutes) >= 1 && Number(minutes) <= 525600))
        }
        onPress={() => void save()}
      />
      {routine && (
        <Button
          label={t("delete")}
          secondary
          disabled={busy}
          onPress={() => {
            setBusy(true);
            void routines
              .remove(routine.id)
              .then(onSaved)
              .catch((cause) => setError(errorText(cause)))
              .finally(() => setBusy(false));
          }}
        />
      )}
    </ScrollView>
  );
}
function RoutineHistory({ id, onThread }: { id: string; onThread: (id: string) => void }) {
  const { t, errorText } = useSession();
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <View style={{ gap: 10 }}>
      <Button
        label={t("history")}
        secondary
        disabled={busy}
        onPress={() => {
          setBusy(true);
          void routines
            .history(id)
            .then((value) => {
              setRuns(value);
              setError(null);
            })
            .catch((cause) => setError(errorText(cause)))
            .finally(() => setBusy(false));
        }}
      />
      <ErrorNotice text={error} />
      {runs?.length === 0 ? (
        <Text style={{ color: colors.secondary }}>{t("noHistory")}</Text>
      ) : (
        runs?.map((run) => (
          <View key={run.id} style={{ gap: 8 }}>
            <Text style={{ color: colors.secondary }}>
              {new Date(run.created_at).toLocaleString()}
            </Text>
            <WorkingIndicator run={run} />
            <Button
              label={t("openConversation")}
              secondary
              onPress={() => onThread(run.thread_id)}
            />
          </View>
        ))
      )}
    </View>
  );
}
