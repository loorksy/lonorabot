// Search, agent chips and native list layout adapted from Tampletgrok; see ../NOTICE.

import type { Agent, Thread } from "@lonora/contracts";
import { Redirect, useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useMemo, useRef, useState } from "react";
import { FlatList, Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import { BotAvatar } from "../components/bot-avatar";
import { NativeSymbol } from "../components/native-symbol";
import { SheetHeader } from "../components/sheet-header";
import { Button, colors, ErrorNotice, Field, Loading, Screen } from "../components/ui";
import { api } from "../lib/api";
import { type ArtifactRecord, formatFileSize, mimeBadge } from "../lib/artifacts";
import { useSession } from "../lib/session";

export default function ArtifactsScreen() {
  const { ready, owner, t, rtl, locale, errorText } = useSession();
  const router = useRouter();
  const { threadId } = useLocalSearchParams<{ threadId?: string }>();
  const [items, setItems] = useState<ArtifactRecord[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [query, setQuery] = useState("");
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);

  const load = useCallback(async () => {
    const requestGeneration = ++generation.current;
    try {
      const [nextItems, nextAgents, nextThreads] = await Promise.all([
        api.get<ArtifactRecord[]>("/artifacts"),
        api.get<Agent[]>("/agents"),
        api.get<Thread[]>("/threads"),
      ]);
      if (requestGeneration !== generation.current) return;
      setItems(nextItems);
      setAgents(nextAgents);
      setThreads(nextThreads);
      setError(null);
    } catch (reason) {
      if (requestGeneration === generation.current) setError(errorText(reason));
    } finally {
      if (requestGeneration === generation.current) setLoading(false);
    }
  }, [errorText]);

  useFocusEffect(
    useCallback(() => {
      if (!ready || !owner) return;
      void load();
      return () => {
        generation.current += 1;
      };
    }, [ready, owner, load]),
  );
  const agentByThread = useMemo(
    () => new Map(threads.map((thread) => [thread.id, thread.agent_id])),
    [threads],
  );
  const agentId = (item: ArtifactRecord) =>
    item.agent_id ?? (item.thread_id ? agentByThread.get(item.thread_id) : null);
  const needle = query.trim().toLocaleLowerCase(locale);
  const filtered = items.filter(
    (item) =>
      (!threadId || item.thread_id === threadId) &&
      (!activeAgent || agentId(item) === activeAgent) &&
      (!needle ||
        `${item.payload.name} ${item.payload.media_type}`
          .toLocaleLowerCase(locale)
          .includes(needle)),
  );

  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  return (
    <Screen>
      <SheetHeader title={t("artifacts")} />
      <View style={{ paddingHorizontal: 16, paddingBottom: 12 }}>
        <Field placeholder={t("artifactSearch")} value={query} onChangeText={setQuery} />
      </View>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={{ flexGrow: 0, maxHeight: 56 }}
        contentContainerStyle={{
          gap: 8,
          paddingHorizontal: 16,
          paddingBottom: 12,
          flexDirection: rtl ? "row-reverse" : "row",
        }}
      >
        <Button
          label={t("artifacts")}
          secondary={activeAgent !== null}
          onPress={() => setActiveAgent(null)}
        />
        {agents.map((agent) => (
          <Button
            key={agent.id}
            label={agent.name}
            secondary={activeAgent !== agent.id}
            onPress={() => setActiveAgent(agent.id)}
          />
        ))}
      </ScrollView>
      <ErrorNotice text={error} />
      {error ? (
        <View style={{ padding: 16 }}>
          <Button label={t("retry")} secondary onPress={() => void load()} />
        </View>
      ) : null}
      {loading ? (
        <Loading />
      ) : (
        <FlatList
          data={filtered}
          keyExtractor={(item) => item.id}
          contentContainerStyle={{ flexGrow: 1, paddingBottom: 24 }}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              tintColor={colors.foreground}
              onRefresh={() => {
                setRefreshing(true);
                void load().finally(() => setRefreshing(false));
              }}
            />
          }
          ListEmptyComponent={
            <Text
              style={{
                color: colors.secondary,
                padding: 24,
                lineHeight: 24,
                textAlign: rtl ? "right" : "left",
              }}
            >
              {needle || activeAgent ? t("noResults") : t("emptyArtifacts")}
            </Text>
          }
          renderItem={({ item }) => {
            const agent = agents.find((value) => value.id === agentId(item));
            return (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={item.payload.name}
                onPress={() =>
                  router.push({ pathname: "/artifact", params: { artifactId: item.id } })
                }
                style={({ pressed }) => ({
                  flexDirection: rtl ? "row-reverse" : "row",
                  alignItems: "center",
                  gap: 12,
                  paddingHorizontal: 16,
                  paddingVertical: 14,
                  opacity: pressed ? 0.5 : 1,
                })}
              >
                <View
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: 8,
                    backgroundColor: colors.muted,
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <NativeSymbol name="file" size={17} color={colors.secondary} />
                </View>
                <View style={{ flex: 1, gap: 5 }}>
                  <View
                    style={{
                      flexDirection: rtl ? "row-reverse" : "row",
                      alignItems: "center",
                      gap: 8,
                    }}
                  >
                    <Text
                      numberOfLines={1}
                      style={{
                        color: colors.foreground,
                        flex: 1,
                        fontSize: 16,
                        fontWeight: "600",
                        textAlign: rtl ? "right" : "left",
                      }}
                    >
                      {item.payload.name}
                    </Text>
                    <Text
                      style={{
                        color: colors.secondary,
                        fontSize: 10,
                        backgroundColor: colors.muted,
                        borderRadius: 4,
                        paddingHorizontal: 5,
                        paddingVertical: 3,
                      }}
                    >
                      {mimeBadge(item.payload.media_type)}
                    </Text>
                  </View>
                  <View
                    style={{
                      flexDirection: rtl ? "row-reverse" : "row",
                      gap: 6,
                      alignItems: "center",
                    }}
                  >
                    {agent ? (
                      <BotAvatar
                        identity={agent.name}
                        color={agent.color}
                        variant={agent.avatar}
                        size={14}
                      />
                    ) : null}
                    <Text
                      numberOfLines={1}
                      style={{
                        color: colors.secondary,
                        fontSize: 12,
                        textAlign: rtl ? "right" : "left",
                      }}
                    >
                      {[
                        agent?.name,
                        formatFileSize(item.payload.size, locale),
                        item.created_at
                          ? new Date(item.created_at).toLocaleDateString(locale)
                          : null,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </Text>
                  </View>
                </View>
              </Pressable>
            );
          }}
        />
      )}
    </Screen>
  );
}
