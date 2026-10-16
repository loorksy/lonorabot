import type { Agent, AttentionNotification, Group, Run, Thread } from "@lonora/contracts";
import { activeStatuses } from "@lonora/core";
// Inbox structure adapted from Tampletgrok apps/mobile/app/index.tsx; see NOTICE.
import { Redirect, useFocusEffect, useRouter } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { AppState, FlatList, RefreshControl, Text, View } from "react-native";
import { ActionMenu } from "../components/action-menu";
import { AttentionInbox } from "../components/attention-inbox";
import { BotAvatar } from "../components/bot-avatar";
import { ConversationRow } from "../components/conversation-row";
import { GroupAvatar } from "../components/group-avatar";
import { HeaderButton } from "../components/header-button";
import { NativeSymbol } from "../components/native-symbol";
import { Button, colors, ErrorNotice, Field, Loading, Screen } from "../components/ui";
import { api } from "../lib/api";
import { useSession } from "../lib/session";

type InboxEntry = {
  thread_id: string;
  agent_id: string | null;
  group_id: string | null;
  last_message: {
    id: string;
    role: string;
    content: string;
    created_at: string;
    seq: number;
  } | null;
  last_activity_at: string;
};
type Row = { kind: "agent"; value: Agent } | { kind: "group"; value: Group };

export default function Inbox() {
  const { ready, owner, rtl, locale, t, errorText } = useSession();
  const router = useRouter();
  const currentOwner = useRef(owner?.id);
  currentOwner.current = owner?.id;
  const [loadedOwner, setLoadedOwner] = useState<string>();
  const [inbox, setInbox] = useState<InboxEntry[]>([]);
  useEffect(() => {
    void owner?.id;
    setInbox([]);
    setAgents([]);
    setGroups([]);
    setRuns([]);
    setAttention([]);
    setLoadedOwner(undefined);
  }, [owner?.id]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [attention, setAttention] = useState<AttentionNotification[]>([]);
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [activity, setActivity] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [opening, setOpening] = useState<string | null>(null);

  const refresh = useCallback(
    async (stillLive: () => boolean = () => true) => {
      const requestOwner = currentOwner.current;
      try {
        const [nextAgents, nextGroups, nextRuns, nextInbox, nextAttention] = await Promise.all([
          api.get<Agent[]>("/agents"),
          api.get<Group[]>("/groups"),
          api.get<Run[]>("/runs"),
          api.get<InboxEntry[]>("/threads/inbox"),
          api.get<AttentionNotification[]>("/attention"),
        ]);
        if (!stillLive() || requestOwner !== currentOwner.current) return;
        setLoadedOwner(requestOwner);
        setInbox(nextInbox);
        setAgents(nextAgents);
        setGroups(nextGroups);
        setRuns(nextRuns);
        setAttention(nextAttention);
        setError(null);
      } catch (reason) {
        if (stillLive() && requestOwner === currentOwner.current) setError(errorText(reason));
      }
    },
    [errorText],
  );

  useFocusEffect(
    useCallback(() => {
      if (!ready || !owner) return;
      let disposed = false;
      let timer: ReturnType<typeof setTimeout>;
      const tick = async () => {
        if (AppState.currentState === "active") await refresh(() => !disposed);
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
  const entries = new Map(
    inbox.map((entry) => [
      entry.agent_id ? `agent:${entry.agent_id}` : `group:${entry.group_id}`,
      entry,
    ]),
  );
  const rows: Row[] = [
    ...agents
      .filter((agent) => agent.name.toLowerCase().includes(needle))
      .map((value) => ({ kind: "agent" as const, value })),
    ...groups
      .filter((group) => group.payload.name.toLowerCase().includes(needle))
      .map((value) => ({ kind: "group" as const, value })),
  ];
  rows.sort((a, b) => {
    const personalA = a.kind === "agent" && a.value.role === "personal";
    const personalB = b.kind === "agent" && b.value.role === "personal";
    if (personalA !== personalB) return personalA ? -1 : 1;
    return (
      entries.get(`${b.kind}:${b.value.id}`)?.last_activity_at ?? b.value.created_at
    ).localeCompare(entries.get(`${a.kind}:${a.value.id}`)?.last_activity_at ?? a.value.created_at);
  });
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
      <View
        style={{
          flexDirection: rtl ? "row-reverse" : "row",
          alignItems: "center",
          justifyContent: "space-between",
          paddingHorizontal: 16,
          paddingTop: 8,
          paddingBottom: 10,
        }}
      >
        <View
          style={{
            width: 44,
            height: 44,
            borderRadius: 22,
            backgroundColor: colors.accent,
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <HeaderButton label={t("settings")} onPress={() => router.push("/settings")}>
            <Text style={{ color: colors.foreground, fontSize: 15, fontWeight: "600" }}>
              {owner.email.slice(0, 2).toUpperCase()}
            </Text>
          </HeaderButton>
        </View>
        <View
          style={{
            flexDirection: rtl ? "row-reverse" : "row",
            padding: 2,
            borderRadius: 22,
            backgroundColor: colors.accent,
          }}
        >
          <HeaderButton
            label={t("activity")}
            active={activity}
            filled={activity}
            onPress={() => setActivity(!activity)}
          >
            <NativeSymbol
              name="activity"
              size={17}
              color={activity ? colors.primaryForeground : colors.foreground}
            />
          </HeaderButton>
          <HeaderButton
            label={t("search")}
            active={searching}
            onPress={() => {
              setSearching(!searching);
              if (searching) setQuery("");
            }}
          >
            <NativeSymbol name="search" size={17} />
          </HeaderButton>
          <HeaderButton label={t("artifacts")} onPress={() => router.push("/artifacts")}>
            <NativeSymbol name="layers" size={17} />
          </HeaderButton>
          <HeaderButton label={t("create")} onPress={() => setCreating(true)}>
            <NativeSymbol name="plus" size={18} />
          </HeaderButton>
        </View>
      </View>
      {searching ? (
        <View style={{ paddingHorizontal: 16, paddingBottom: 8 }}>
          <Field
            placeholder={t("search")}
            value={query}
            onChangeText={setQuery}
            autoFocus
            style={{ minHeight: 44, paddingVertical: 10, borderRadius: 10, fontSize: 17 }}
          />
        </View>
      ) : null}
      <ActionMenu
        visible={creating}
        onClose={() => setCreating(false)}
        actions={[
          { label: t("newAgent"), icon: "agent", onPress: () => router.push("/new") },
          {
            label: t("newGroup"),
            icon: "group",
            disabled: !agents.length,
            onPress: () => router.push("/new-group"),
          },
        ]}
      />
      <ErrorNotice text={error} />
      <FlatList
        data={activity ? [] : rows}
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
        ListHeaderComponent={
          activity ? (
            <View>
              <AttentionInbox
                items={attention}
                agents={agents}
                onSeen={async (id) => {
                  await api.post("/attention/seen", { notification_id: id });
                  setAttention((rows) => rows.filter((row) => row.id !== id));
                }}
              />
              {runs.map((run) => {
                const agent = agents.find((value) => value.id === run.agent_id);
                if (!agent || (needle && !agent.name.toLowerCase().includes(needle))) return null;
                return (
                  <ConversationRow
                    key={run.id}
                    title={agent.name}
                    preview={t(run.status)}
                    time={new Date(run.updated_at).toLocaleTimeString(locale, {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                    avatar={
                      <BotAvatar
                        identity={agent.name}
                        color={agent.color}
                        variant={agent.avatar}
                        working={activeStatuses.includes(run.status)}
                      />
                    }
                    onPress={() =>
                      router.push({ pathname: "/thread", params: { id: run.thread_id } })
                    }
                  />
                );
              })}
            </View>
          ) : null
        }
        ListEmptyComponent={
          loadedOwner !== owner.id ? (
            <Loading />
          ) : activity && runs.length ? null : (
            <View style={{ padding: 24, gap: 20 }}>
              <Text
                style={{
                  color: colors.secondary,
                  textAlign: rtl ? "right" : "left",
                  lineHeight: 24,
                }}
              >
                {needle ? t("noResults") : t("emptyInbox")}
              </Text>
              {!needle ? (
                <Button label={t("newAgent")} onPress={() => router.push("/new")} />
              ) : null}
            </View>
          )
        }
        renderItem={({ item }) => {
          const entry = entries.get(`${item.kind}:${item.value.id}`);
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
                    identity={agent?.name}
                    color={agent?.color ?? "#85858A"}
                    variant={agent?.avatar}
                    working={Boolean(run)}
                  />
                )
              }
              time={(() => {
                const at = new Date(
                  entry?.last_activity_at ?? run?.updated_at ?? item.value.created_at,
                );
                return at.toDateString() === new Date().toDateString()
                  ? at.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" })
                  : at.toLocaleDateString(locale, { month: "short", day: "numeric" });
              })()}
              preview={
                entry?.last_message?.content ||
                (item.kind === "group"
                  ? item.value.payload.member_ids
                      .map((memberId) => agents.find((value) => value.id === memberId)?.name)
                      .filter(Boolean)
                      .join(" · ")
                  : item.value.paused
                    ? t("paused")
                    : run
                      ? t(run.status)
                      : item.value.title || item.value.description || "")
              }
            />
          );
        }}
      />
    </Screen>
  );
}
