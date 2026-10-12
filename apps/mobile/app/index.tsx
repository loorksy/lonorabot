import type { Agent, Group, Run, Thread } from "@lonora/contracts";
import { activeStatuses } from "@lonora/core";
// Inbox structure adapted from Tampletgrok apps/mobile/app/index.tsx; see NOTICE.
import { Redirect, useFocusEffect, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { AppState, FlatList, RefreshControl, Text, View } from "react-native";
import { BotAvatar } from "../components/bot-avatar";
import { ConversationRow } from "../components/conversation-row";
import { GroupAvatar } from "../components/group-avatar";
import { Button, colors, ErrorNotice, Field, Header, Loading, Screen } from "../components/ui";
import { api } from "../lib/api";
import { useSession } from "../lib/session";

type Row = { kind: "agent"; value: Agent } | { kind: "group"; value: Group };

export default function Inbox() {
  const { ready, owner, rtl, t, errorText } = useSession();
  const router = useRouter();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [opening, setOpening] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [nextAgents, nextGroups, nextRuns] = await Promise.all([
        api.get<Agent[]>("/agents"),
        api.get<Group[]>("/groups"),
        api.get<Run[]>("/runs"),
      ]);
      setAgents(nextAgents);
      setGroups(nextGroups);
      setRuns(nextRuns);
      setError(null);
    } catch (reason) {
      setError(errorText(reason));
    }
  }, [errorText]);

  useFocusEffect(
    useCallback(() => {
      if (!ready || !owner) return;
      let disposed = false;
      let timer: ReturnType<typeof setTimeout>;
      const tick = async () => {
        if (AppState.currentState === "active") await refresh();
        if (!disposed) timer = setTimeout(() => void tick(), 5000);
      };
      void tick();
      return () => {
        disposed = true;
        clearTimeout(timer);
      };
    }, [ready, owner, refresh]),
  );

  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  const needle = query.trim().toLowerCase();
  const rows: Row[] = [
    ...agents
      .filter((agent) => agent.name.toLowerCase().includes(needle))
      .map((value) => ({ kind: "agent" as const, value })),
    ...groups
      .filter((group) => group.payload.name.toLowerCase().includes(needle))
      .map((value) => ({ kind: "group" as const, value })),
  ];
  const open = async (row: Row) => {
    if (opening) return;
    setOpening(row.value.id);
    setError(null);
    try {
      let thread: Thread;
      if (row.kind === "agent") {
        thread = await api.post<Thread>(
          `/agents/${encodeURIComponent(row.value.id)}/conversation`,
          {},
        );
      } else {
        router.push({ pathname: "/group-thread", params: { groupId: row.value.id } });
        return;
      }
      router.push({ pathname: "/thread", params: { id: thread.id } });
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setOpening(null);
    }
  };
  return (
    <Screen>
      <Header
        title={t("inbox")}
        left={<Button label={t("settings")} secondary onPress={() => router.push("/settings")} />}
        right={<Button label="+" onPress={() => router.push("/new")} />}
      />
      <View style={{ paddingHorizontal: 16, paddingBottom: 12 }}>
        <Field placeholder={t("search")} value={query} onChangeText={setQuery} />
      </View>
      <ErrorNotice text={error} />
      <FlatList
        data={rows}
        keyExtractor={(row) => `${row.kind}:${row.value.id}`}
        contentContainerStyle={{ paddingBottom: 24, flexGrow: 1 }}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            tintColor={colors.foreground}
            onRefresh={() => {
              setRefreshing(true);
              void refresh().finally(() => setRefreshing(false));
            }}
          />
        }
        ListEmptyComponent={
          <View style={{ padding: 24, gap: 20 }}>
            <Text
              style={{ color: colors.secondary, textAlign: rtl ? "right" : "left", lineHeight: 24 }}
            >
              {needle ? t("noResults") : t("emptyInbox")}
            </Text>
            {!needle ? <Button label={t("newAgent")} onPress={() => router.push("/new")} /> : null}
          </View>
        }
        renderItem={({ item }) => {
          const agent =
            item.kind === "agent"
              ? item.value
              : agents.find((value) => value.id === item.value.payload.member_ids[0]);
          const name = item.kind === "agent" ? item.value.name : item.value.payload.name;
          const run = runs.find(
            (value) => value.agent_id === agent?.id && activeStatuses.includes(value.status),
          );
          return (
            <ConversationRow
              title={name}
              disabled={opening !== null}
              busy={opening === item.value.id}
              onPress={() => void open(item)}
              onLongPress={() =>
                router.push(
                  item.kind === "agent"
                    ? { pathname: "/bot-settings", params: { botId: item.value.id } }
                    : { pathname: "/group-settings", params: { groupId: item.value.id } },
                )
              }
              avatar={
                item.kind === "group" ? (
                  <GroupAvatar
                    members={agents.filter((value) =>
                      item.value.payload.member_ids.includes(value.id),
                    )}
                  />
                ) : (
                  <BotAvatar
                    color={agent?.color ?? "#85858A"}
                    variant={agent?.avatar}
                    working={Boolean(run)}
                  />
                )
              }
              preview={
                item.kind === "group"
                  ? item.value.payload.member_ids
                      .map((memberId) => agents.find((value) => value.id === memberId)?.name)
                      .filter(Boolean)
                      .join(" · ")
                  : item.value.paused
                    ? t("paused")
                    : run
                      ? t(run.status)
                      : item.value.instructions || t("threadsPersist")
              }
            />
          );
        }}
      />
      <View style={{ paddingHorizontal: 16, paddingBottom: 12, gap: 8 }}>
        <Button label={t("artifacts")} secondary onPress={() => router.push("/artifacts")} />
        <Button
          label={t("newGroup")}
          secondary
          onPress={() => router.push("/new-group")}
          disabled={!agents.length}
        />
      </View>
    </Screen>
  );
}
