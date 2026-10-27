import type {
  Agent,
  Artifact,
  Event,
  Group,
  InputAnswer,
  Message,
  Run,
  Thread,
  TradeApproval,
} from "@lonora/contracts";
import {
  accumulateStream,
  activeStatuses,
  type ConversationItem,
  conversationTimeline,
  type LiveReplyStream,
  type MentionAddress,
  needsTimeSeparator,
  projectRunEvents,
  seedStream,
  streamForRun,
  turnActivity,
} from "@lonora/core";
// Persistent-thread navigation follows Tampletgrok's native thread screen; see NOTICE.
import * as DocumentPicker from "expo-document-picker";
import { Redirect, useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import {
  AppState,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  Text,
  View,
} from "react-native";
import { ActionMenu } from "../components/action-menu";
import { AgentLiveStatus } from "../components/agent-live-status";
import { BotAvatar } from "../components/bot-avatar";
import { useChartSheet } from "../components/chart-sheet";
import { ConversationQuestion } from "../components/conversation-question";
import { GroupAvatar } from "../components/group-avatar";
import { MessageBubble } from "../components/message-bubble";
import { NativeSymbol } from "../components/native-symbol";
import { SuperBotCard, useSuperBotRequests } from "../components/super-bot-cards";
import { ThreadComposer } from "../components/thread-composer";
import { ThreadHeader } from "../components/thread-header";
import { TimeSeparator } from "../components/time-separator";
import { TradeApprovalCard } from "../components/trade-approval";
import { TurnActivity } from "../components/turn-activity";
import { Button, colors, ErrorNotice, Loading, Screen } from "../components/ui";
import { ApiError, api, upload } from "../lib/api";
import {
  type ComposerDraft,
  composerDraft,
  consumeComposerDraft,
  editComposerDraft,
} from "../lib/composer-drafts";
import {
  type ConversationSnapshot,
  conversationCache,
  type InboxSnapshot,
} from "../lib/conversation-cache";
import { projectConversation } from "../lib/conversation-projection";
import { type EventConnection, subscribeOwnerEvents } from "../lib/events";
import {
  acknowledgeOutgoing,
  enqueueOutgoing,
  failOutgoing,
  hydrateOutgoing,
  type OutgoingIntent,
  outgoingKey,
  outgoingMessages,
  subscribeOutgoing,
} from "../lib/outgoing-messages";
import { useSession } from "../lib/session";
import { useVoiceSession } from "../lib/voice-session";

function mergeMessages(previous: Message[], incoming: Message[]): Message[] {
  const rows = new Map(previous.map((row) => [row.id, row]));
  for (const row of incoming) rows.set(row.id, row);
  return [...rows.values()].sort((a, b) => a.seq - b.seq);
}

export default function Conversation({ threadId }: { threadId?: string } = {}) {
  const params = useLocalSearchParams<{ id: string }>();
  const id = threadId ?? params.id;
  const { ready, owner, server, rtl, t, errorText } = useSession();
  const scope = useMemo(
    () => (owner ? conversationCache.activate(server, owner.id) : null),
    [server, owner],
  );
  const cacheKey = `thread:${id}`;
  const [hydrated, setHydrated] = useState<{ scope: typeof scope; id: string }>();
  const router = useRouter();
  const voice = useVoiceSession();
  const chartSheet = useChartSheet();
  const [thread, setThread] = useState<Thread | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [collaborationActive, setCollaborationActive] = useState(false);
  const [collaborationSessionId, setCollaborationSessionId] = useState<string>();
  const [approvals, setApprovals] = useState<TradeApproval[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [draft, setDraft] = useState("");
  const [reply, setReply] = useState<Message | null>(null);
  const [attachments, setAttachments] = useState<Artifact[]>([]);
  const [files, setFiles] = useState<Artifact[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [hasOlder, setHasOlder] = useState(true);
  const [actionsVisible, setActionsVisible] = useState(false);
  const list = useRef<FlatList<ConversationItem>>(null);
  const following = useRef(true);
  const [atEnd, setAtEnd] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [stateRevision, setStateRevision] = useState(0);
  const superBot = useSuperBotRequests(thread?.agent_id ?? undefined, id, stateRevision);
  const [events, setEvents] = useState<Event[]>([]);
  const [streams, setStreams] = useState<Record<string, LiveReplyStream>>({});
  const [connection, setConnection] = useState<EventConnection>("connecting");
  const sendLocks = useRef(new Set<string>());
  const deliveries = useRef(new Set<string>());
  const selected = useRef({ id, scope });
  selected.current = { id, scope };
  const canonical = useRef(messages);
  canonical.current = messages;
  const outboxKey = outgoingKey(server, owner?.id ?? "signed-out", id);
  const outgoing = useSyncExternalStore(
    subscribeOutgoing,
    useCallback(() => outgoingMessages(outboxKey), [outboxKey]),
  );
  const updateDraft = (patch: Partial<Omit<ComposerDraft, "revision">>) => {
    const next = editComposerDraft(outboxKey, patch);
    setDraft(next.text);
    setAttachments(next.attachments);
    setReply(next.reply);
  };
  const current = () =>
    selected.current.id === id &&
    selected.current.scope === scope &&
    conversationCache.current(scope);
  const snapshotRef = useRef<() => Promise<void>>(async () => undefined);
  useEffect(() => {
    void hydrateOutgoing(outboxKey);
  }, [outboxKey]);
  const reportError = useRef(errorText);
  reportError.current = errorText;

  const snapshot = useCallback(
    async (stillLive: () => boolean = () => true) => {
      if (!id || !conversationCache.current(scope)) return;
      try {
        const primary = Promise.all([
          api.get<Message[]>(`/threads/${encodeURIComponent(id)}/messages`),
          api.get<Run[]>(`/runs?thread_id=${encodeURIComponent(id)}`),
        ]).then(([nextMessages, nextRuns]) => {
          if (
            !stillLive() ||
            !conversationCache.current(scope) ||
            selected.current.id !== id ||
            selected.current.scope !== scope
          )
            return;
          setMessages((old) => mergeMessages(old, nextMessages));
          acknowledgeOutgoing(outboxKey, nextMessages);
          setStreams((old) => {
            const next = { ...old };
            for (const run of nextRuns) {
              const value = seedStream(next[run.id], run);
              if (value) next[run.id] = value;
            }
            return next;
          });
          setRuns((old) => projectRunEvents([...old, ...nextRuns], [], id));
          setLoaded(true);
          setError(null);
        });
        const auxiliary = Promise.all([
          api.get<Artifact[]>(`/artifacts?thread_id=${encodeURIComponent(id)}`),
          api.get<TradeApproval[]>(`/trading/approvals?thread_id=${encodeURIComponent(id)}`),
          api.get<{ id: string; state: { status: string } } | null>(
            `/threads/${encodeURIComponent(id)}/collaboration`,
          ),
          api.get<Agent[]>("/agents"),
        ]).then(([nextFiles, nextApprovals, collaboration, refreshedAgents]) => {
          if (
            !stillLive() ||
            !conversationCache.current(scope) ||
            selected.current.id !== id ||
            selected.current.scope !== scope
          )
            return;
          setAgents(refreshedAgents);
          setStateRevision((value) => value + 1);
          setCollaborationSessionId(collaboration?.id);
          setCollaborationActive(
            Boolean(
              collaboration &&
                !["completed", "cancelled", "expired", "failed"].includes(
                  collaboration.state.status,
                ),
            ),
          );
          setFiles(nextFiles);
          setApprovals((old) =>
            nextApprovals.map((row) => {
              const previous = old.find((item) => item.id === row.id);
              const rank = { pending: 0, approved: 1, rejected: 1, completed: 2, cancelled: 2 };
              return previous &&
                (rank[previous.status] > rank[row.status] ||
                  (previous.status === row.status && previous.results.length > row.results.length))
                ? previous
                : row;
            }),
          );
          setError(null);
        });
        await Promise.all([primary, auxiliary]);
      } catch (reason) {
        if (
          stillLive() &&
          conversationCache.current(scope) &&
          selected.current.id === id &&
          selected.current.scope === scope
        )
          setError(reportError.current(reason));
      }
    },
    [id, scope, outboxKey],
  );

  snapshotRef.current = snapshot;
  useEffect(() => {
    const cached = conversationCache.get<ConversationSnapshot>(scope, cacheKey);
    const inbox = conversationCache.get<InboxSnapshot>(scope, "inbox");
    setHydrated({ scope, id });
    setThread(cached?.thread ?? null);
    setAgents(cached?.agents ?? inbox?.agents ?? []);
    setGroups(cached?.groups ?? inbox?.groups ?? []);
    setMessages(cached?.messages ?? []);
    setRuns(cached?.runs ?? []);
    setApprovals(cached?.approvals ?? []);
    setCollaborationActive(cached?.collaborationActive ?? false);
    setCollaborationSessionId(cached?.collaborationSessionId);
    const savedDraft = composerDraft(outboxKey);
    setAttachments(savedDraft.attachments);
    setFiles(cached?.files ?? []);
    setDraft(savedDraft.text);
    setReply(savedDraft.reply);
    setUploading(false);
    setHasOlder(cached?.hasOlder ?? true);
    following.current = true;
    setAtEnd(true);
    setLoaded(cached?.loaded ?? false);
    setEvents([]);
    setStreams({});
    if (!id || !owner) return;
    let live = true;
    void api
      .get<Thread>(`/threads/${encodeURIComponent(id)}`)
      .then((nextThread) => {
        if (live && conversationCache.current(scope)) {
          setThread(nextThread);
        }
      })
      .catch((reason) => {
        if (live && conversationCache.current(scope)) {
          if (reason instanceof ApiError && reason.status === 404) {
            conversationCache.remove(scope, cacheKey);
            setThread(null);
            setMessages([]);
            setLoaded(false);
          }
          setError(reportError.current(reason));
        }
      });
    return () => {
      live = false;
    };
  }, [id, scope, cacheKey, owner, outboxKey]);

  useEffect(() => {
    if (hydrated?.scope !== scope || hydrated.id !== id || !thread || !loaded) return;
    conversationCache.set<ConversationSnapshot>(scope, cacheKey, {
      thread,
      agents,
      groups,
      messages: messages.slice(-1000),
      runs,
      files,
      approvals,
      collaborationActive,
      collaborationSessionId,
      loaded,
      hasOlder: hasOlder || messages.length > 1000,
    });
  }, [
    scope,
    cacheKey,
    id,
    hydrated,
    thread,
    loaded,
    agents,
    groups,
    messages,
    runs,
    files,
    approvals,
    collaborationActive,
    collaborationSessionId,
    hasOlder,
  ]);

  useFocusEffect(
    useCallback(() => {
      if (!ready || !owner || !id) return;
      let disposed = false;
      let timer: ReturnType<typeof setTimeout> | undefined;
      let queued: ReturnType<typeof setTimeout> | undefined;
      let refreshing = false;
      let refreshAgain = false;
      const refresh = async () => {
        if (disposed) return;
        if (refreshing) {
          refreshAgain = true;
          return;
        }
        refreshing = true;
        try {
          do {
            refreshAgain = false;
            await snapshotRef.current();
          } while (refreshAgain && !disposed);
        } finally {
          refreshing = false;
        }
      };
      const schedule = () => {
        if (queued || disposed) return;
        queued = setTimeout(() => {
          queued = undefined;
          void refresh();
        }, 150);
      };
      const unsubscribe = subscribeOwnerEvents(
        server,
        (event) => {
          if (disposed || event.thread_id !== id) return;
          setRuns((old) => projectRunEvents(old, [event], id));
          setEvents((old) =>
            [...old, event]
              .filter((row) => row.kind !== "run.delta" || row.cursor === event.cursor)
              .slice(-250),
          );
          if (event.run_id)
            setStreams((old) => {
              const value = accumulateStream(old[event.run_id as string], event);
              if (!value) return old;
              if (value.gap) schedule();
              return { ...old, [value.run_id]: value };
            });
          if (event.kind === "message.created") {
            const value = event.payload;
            if (
              typeof value.id === "string" &&
              typeof value.content === "string" &&
              typeof value.seq === "number" &&
              value.thread_id === id &&
              Array.isArray(value.attachment_ids)
            ) {
              const message = value as unknown as Message;
              setMessages((old) => mergeMessages(old, [message]));
              acknowledgeOutgoing(outboxKey, [message]);
            }
          }
          if (
            ![
              "run.delta",
              "run.rich_partial",
              "run.reply_started",
              "run.progress",
              "tool.started",
              "tool.completed",
              "tool.cancelled",
            ].includes(event.kind)
          )
            schedule();
        },
        () => void refresh(),
        (state) => {
          if (!disposed) setConnection(state);
        },
      );
      // A slow snapshot is recovery only; token delivery uses the durable stream.
      const fallback = () => {
        if (!disposed) {
          if (AppState.currentState === "active") void refresh();
          timer = setTimeout(fallback, 15000);
        }
      };
      timer = setTimeout(fallback, 15000);
      void Promise.all([api.get<Agent[]>("/agents"), api.get<Group[]>("/groups")])
        .then(([nextAgents, nextGroups]) => {
          if (!disposed) {
            setAgents(nextAgents);
            setGroups(nextGroups);
          }
        })
        .catch(() => undefined);
      return () => {
        disposed = true;
        unsubscribe();
        if (timer) clearTimeout(timer);
        if (queued) clearTimeout(queued);
      };
    }, [ready, owner, id, server, outboxKey]),
  );

  const acceptedNonces = new Set(messages.map((message) => message.client_nonce).filter(Boolean));
  const visibleMessages = projectConversation(
    mergeMessages(
      messages,
      outgoing.filter((row) => !acceptedNonces.has(row.nonce)).map((row) => row.message),
    ),
    runs,
    streams,
  );
  const deliver = async (intent: OutgoingIntent, targetKey: string, targetId: string) => {
    if (!conversationCache.current(scope) || deliveries.current.has(intent.nonce)) return;
    deliveries.current.add(intent.nonce);
    try {
      const accepted = await api.post<{ message: Message; run_ids: string[]; runs?: Run[] }>(
        `/threads/${encodeURIComponent(targetId)}/messages`,
        intent.body,
      );
      const cached = conversationCache.get<ConversationSnapshot>(scope, `thread:${targetId}`);
      if (cached)
        conversationCache.set(scope, `thread:${targetId}`, {
          ...cached,
          messages: mergeMessages(cached.messages, [accepted.message]),
        });
      if (!conversationCache.current(scope)) return;
      acknowledgeOutgoing(targetKey, [accepted.message]);
      if (
        selected.current.id === targetId &&
        selected.current.scope === scope &&
        conversationCache.current(scope)
      ) {
        setMessages((old) => mergeMessages(old, [accepted.message]));
        if (accepted.runs?.length)
          setRuns((old) => {
            const projected = new Map(old.map((run) => [run.id, run]));
            for (const run of accepted.runs ?? []) {
              const prior = projected.get(run.id);
              if (!prior || Date.parse(run.updated_at) >= Date.parse(prior.updated_at))
                projected.set(run.id, run);
            }
            return [...projected.values()];
          });
        void snapshotRef.current();
      }
    } catch (reason) {
      const confirmed = canonical.current.find(
        (message) => message.thread_id === targetId && message.client_nonce === intent.nonce,
      );
      if (confirmed) {
        acknowledgeOutgoing(targetKey, [confirmed]);
        return;
      }
      failOutgoing(targetKey, intent.nonce);
      if (selected.current.id === targetId && selected.current.scope === scope)
        setError(reportError.current(reason));
      throw reason;
    } finally {
      deliveries.current.delete(intent.nonce);
    }
  };
  const retryOutgoing = async (nonce: string) => {
    const prior = outgoingMessages(outboxKey).find((row) => row.nonce === nonce);
    if (prior?.message.delivery !== "failed" || deliveries.current.has(nonce)) return;
    try {
      await deliver(
        await enqueueOutgoing(
          outboxKey,
          id,
          prior.fingerprint,
          prior.body,
          Math.max(0, ...messages.map((row) => row.seq)),
        ),
        outboxKey,
        id,
      );
    } catch {
      /* The failed intent remains available for retry. */
    }
  };

  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  const agent = agents.find((value) => value.id === thread?.agent_id);
  const group = groups.find((value) => value.id === thread?.group_id);
  const title = agent?.name ?? group?.payload.name ?? thread?.title ?? t("inbox");
  const send = async (mentions?: MentionAddress, followUp?: string) => {
    if (
      sendLocks.current.has(outboxKey) ||
      uploading ||
      !thread ||
      (!followUp?.trim() && !draft.trim() && !attachments.length)
    )
      return;
    const submittedDraft = composerDraft(outboxKey);
    const content = followUp?.trim() || draft.trim() || t("attach");
    const attachment_ids = followUp ? [] : attachments.map((file) => file.id);
    const reply_to = followUp ? null : (reply?.id ?? null);
    const targetKey = outboxKey,
      targetId = id;
    const body = {
      content,
      attachment_ids,
      reply_to,
      mention_agent_ids: mentions?.agent_ids ?? [],
      mention_all: mentions?.all ?? false,
      collaboration_session_id: mentions?.collaboration_session_id,
    };
    const fingerprint = JSON.stringify([targetId, body]);
    sendLocks.current.add(targetKey);
    setError(null);
    let intent: OutgoingIntent;
    try {
      intent = await enqueueOutgoing(
        targetKey,
        targetId,
        fingerprint,
        body,
        Math.max(0, ...messages.map((message) => message.seq)),
      );
      const nextDraft = followUp
        ? composerDraft(targetKey)
        : consumeComposerDraft(targetKey, submittedDraft.revision);
      if (current()) {
        following.current = true;
        setAtEnd(true);
        if (!followUp) {
          setDraft(nextDraft.text);
          setAttachments(nextDraft.attachments);
          setReply(nextDraft.reply);
        }
      }
    } catch (reason) {
      if (current()) setError(errorText(reason));
      if (followUp) throw reason;
      return;
    } finally {
      sendLocks.current.delete(targetKey);
    }
    try {
      await deliver(intent, targetKey, targetId);
    } catch (reason) {
      if (followUp) throw reason;
    }
  };
  const answerQuestion = async (answer: InputAnswer, label: string, messageId: string) => {
    const body = { content: label, reply_to: messageId, input_answer: answer, attachment_ids: [] };
    const intent = await enqueueOutgoing(
      outboxKey,
      id,
      JSON.stringify([id, body]),
      body,
      Math.max(0, ...messages.map((message) => message.seq)),
    );
    if (current()) {
      following.current = true;
      setAtEnd(true);
    }
    await deliver(intent, outboxKey, id);
  };
  const questions = new Map(
    runs.flatMap((run) => run.input_requests ?? []).map((request) => [request.message_id, request]),
  );
  const attach = async () => {
    if (!thread || uploading || attachments.length >= 10) return;
    const targetId = id,
      targetKey = outboxKey;
    setUploading(true);
    setError(null);
    try {
      const result = await DocumentPicker.getDocumentAsync({
        copyToCacheDirectory: true,
        multiple: false,
      });
      if (!result.canceled) {
        if (!conversationCache.current(scope)) return;
        const file = await upload(result.assets[0], targetId);
        if (!conversationCache.current(scope)) return;
        const next = editComposerDraft(targetKey, {
          attachments: [...composerDraft(targetKey).attachments, file],
        });
        if (current()) setAttachments(next.attachments);
      }
    } catch (reason) {
      if (current()) setError(errorText(reason));
    } finally {
      if (current()) setUploading(false);
    }
  };
  const changeRun = async (run: Run, action: "cancel" | "resume") => {
    setBusy(true);
    setError(null);
    try {
      await api.post(`/runs/${run.id}/${action}`, {});
      await snapshot();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setBusy(false);
    }
  };
  const older = async () => {
    if (!messages.length || busy) return;
    following.current = false;
    setBusy(true);
    try {
      const rows = await api.get<Message[]>(
        `/threads/${encodeURIComponent(id)}/messages?before=${messages[0].seq}`,
      );
      setMessages((old) => mergeMessages(old, rows));
      setHasOlder(rows.length === 100);
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Screen>
      <ThreadHeader
        title={title}
        settingsLabel={group ? t("groupSettings") : t("agentSettings")}
        onBack={() => (router.canGoBack() ? router.back() : router.replace("/"))}
        onSettings={() => {
          if (agent) router.push({ pathname: "/bot-settings", params: { botId: agent.id } });
          else if (group)
            router.push({ pathname: "/group-settings", params: { groupId: group.id } });
        }}
        onActions={() => setActionsVisible(true)}
        onCall={agent && thread ? () => void voice.start(agent, thread.id) : undefined}
        avatar={
          agent ? (
            <BotAvatar
              superBot={agent.super_bot_active}
              identity={agent.name}
              color={agent.color}
              variant={agent.avatar}
              size={28}
              state={(() => {
                const active = [...runs]
                  .reverse()
                  .find((run) => activeStatuses.includes(run.status));
                return active ? turnActivity(active, events).avatar : "waiting";
              })()}
            />
          ) : group ? (
            <GroupAvatar
              members={agents.filter((value) => group.payload.member_ids.includes(value.id))}
              size={28}
            />
          ) : undefined
        }
      />
      <ActionMenu
        visible={actionsVisible}
        onClose={() => setActionsVisible(false)}
        actions={[
          {
            label: t("charts"),
            icon: "chart",
            onPress: () => chartSheet.open({ threadId: id, ...(agent ? { botId: agent.id } : {}) }),
          },
          ...(agent
            ? [
                {
                  label: t("routines"),
                  icon: "clock" as const,
                  onPress: () => router.push({ pathname: "/routine", params: { botId: agent.id } }),
                },
              ]
            : []),
          {
            label: t("artifacts"),
            icon: "layers",
            onPress: () => router.push({ pathname: "/artifacts", params: { threadId: id } }),
          },
          {
            label: group ? t("groupSettings") : t("agentSettings"),
            icon: "settings",
            onPress: () => {
              if (agent) router.push({ pathname: "/bot-settings", params: { botId: agent.id } });
              else if (group)
                router.push({ pathname: "/group-settings", params: { groupId: group.id } });
            },
          },
        ]}
      />
      <ErrorNotice text={error || superBot.error} />
      {runs
        .filter(
          (run) =>
            run.status === "waiting_input" ||
            run.status === "waiting_takeover" ||
            run.status === "failed",
        )
        .slice(0, 1)
        .map((run) => (
          <View
            key={run.id}
            style={{
              flexDirection: rtl ? "row-reverse" : "row",
              alignItems: "center",
              gap: 12,
              paddingHorizontal: 16,
              paddingBottom: 10,
            }}
          >
            <Text
              style={{
                flex: 1,
                color: run.status === "failed" ? colors.error : colors.secondary,
                textAlign: rtl ? "right" : "left",
              }}
            >
              {agents.find((value) => value.id === run.agent_id)?.name} · {t(run.status)}
              {run.error_code ? ` · ${errorText(new ApiError(run.error_code, 0))}` : ""}
            </Text>
            {activeStatuses.includes(run.status) ||
            run.status === "waiting_input" ||
            run.status === "waiting_takeover" ? (
              <Button
                label={t("cancel")}
                secondary
                disabled={busy}
                onPress={() => void changeRun(run, "cancel")}
              />
            ) : null}
            {run.status === "waiting_takeover" ? (
              <Button
                label={t("resume")}
                secondary
                disabled={busy}
                onPress={() => void changeRun(run, "resume")}
              />
            ) : null}
          </View>
        ))}
      {thread?.agent_id && <AgentLiveStatus agentId={thread.agent_id} />}
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <View style={{ flex: 1 }}>
          {!loaded || !thread ? (
            <Loading />
          ) : (
            <FlatList
              ref={list}
              testID="conversation-transcript"
              inverted
              data={conversationTimeline(
                visibleMessages,
                approvals.filter((row) => row.thread_id === id),
                superBot.rows,
              ).reverse()}
              keyExtractor={(item) => item.id}
              maintainVisibleContentPosition={{ minIndexForVisible: 0 }}
              keyboardShouldPersistTaps="handled"
              keyboardDismissMode="on-drag"
              scrollEventThrottle={16}
              onScroll={(event) => {
                const near = event.nativeEvent.contentOffset.y <= 80;
                following.current = near;
                setAtEnd(near);
              }}
              onContentSizeChange={() => {
                if (following.current) list.current?.scrollToOffset({ offset: 0, animated: false });
              }}
              contentContainerStyle={{
                paddingHorizontal: 16,
                paddingVertical: 14,
                flexGrow: 1,
                gap: 12,
              }}
              ListFooterComponent={
                messages.length >= 100 && hasOlder ? (
                  <Button
                    label={t("older")}
                    secondary
                    disabled={busy}
                    onPress={() => void older()}
                  />
                ) : null
              }
              ListEmptyComponent={
                <Text style={{ color: colors.secondary, textAlign: "center", padding: 24 }}>
                  {t("waitingMessage")}
                </Text>
              }
              renderItem={({ item }) => {
                if (item.kind === "super_bot")
                  return <SuperBotCard row={item.request} onChange={superBot.update} />;
                if (item.kind === "approval")
                  return (
                    <TradeApprovalCard
                      row={item.approval}
                      onChange={(updated) =>
                        setApprovals((old) =>
                          old.map((row) => (row.id === updated.id ? updated : row)),
                        )
                      }
                    />
                  );
                const message = item.message;
                const question = questions.get(message.id);
                const previous =
                  visibleMessages[visibleMessages.findIndex((row) => row.id === message.id) - 1];
                const responseRun = message.id.startsWith("preview:")
                  ? runs.find((run) => `preview:${run.id}` === message.id)
                  : undefined;
                return (
                  <View>
                    {needsTimeSeparator(message.created_at, previous?.created_at) ? (
                      <TimeSeparator createdAt={message.created_at} />
                    ) : null}
                    {responseRun ? (
                      <TurnActivity
                        run={{
                          ...responseRun,
                          stream: streamForRun(responseRun, streams[responseRun.id]),
                        }}
                        events={events}
                        connection={connection}
                        agent={agents.find((value) => value.id === responseRun.agent_id)}
                      />
                    ) : null}
                    <MessageBubble
                      onChartLink={(value) => {
                        try {
                          const url = new URL(value, server);
                          if (url.origin !== new URL(server).origin || url.pathname !== "/charts")
                            return false;
                          chartSheet.open({
                            threadId: id,
                            ...(agent ? { botId: agent.id } : {}),
                            chartId: url.searchParams.get("chartId") ?? undefined,
                          });
                          return true;
                        } catch {
                          return false;
                        }
                      }}
                      onVisualAction={async (action) => {
                        if (action.kind === "follow_up") await send(undefined, action.text);
                        else if (action.kind === "open_chart")
                          chartSheet.open({
                            threadId: id,
                            ...(agent ? { botId: agent.id } : {}),
                            chartId: action.resource_id,
                          });
                        else
                          router.push({
                            pathname: "/artifact",
                            params: { artifactId: action.resource_id },
                          });
                      }}
                      message={message}
                      body={
                        question?.choices.length ? (
                          <ConversationQuestion request={question} onAnswer={answerQuestion} />
                        ) : undefined
                      }
                      reply={messages.find((row) => row.id === message.reply_to)}
                      onReply={
                        message.id.startsWith("preview:")
                          ? undefined
                          : (value) => updateDraft({ reply: value })
                      }
                      onRetry={(nonce) => void retryOutgoing(nonce)}
                      previousVisualMessageId={(() => {
                        const settled = runs.find(
                          (run) =>
                            (streams[run.id]?.message_id ?? run.stream?.message_id) === message.id,
                        );
                        return settled ? `preview:${settled.id}` : undefined;
                      })()}
                      grouped={Boolean(
                        responseRun ||
                          (previous &&
                            previous.role === message.role &&
                            previous.agent_id === message.agent_id &&
                            new Date(message.created_at).getTime() -
                              new Date(previous.created_at).getTime() <
                              180000),
                      )}
                      agent={agents.find((value) => value.id === message.agent_id)}
                      files={files}
                      onArtifact={(fileId) =>
                        router.push({ pathname: "/artifact", params: { artifactId: fileId } })
                      }
                    />
                  </View>
                );
              }}
              ListHeaderComponent={
                outgoing.some((row) => row.message.delivery === "sending") ? (
                  <Text
                    accessibilityLiveRegion="polite"
                    style={{ color: colors.secondary, padding: 8 }}
                  >
                    {t("sending")}
                  </Text>
                ) : null
              }
            />
          )}
          {!atEnd && (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={t("jumpLatest")}
              onPress={() => {
                following.current = true;
                setAtEnd(true);
                list.current?.scrollToOffset({ offset: 0, animated: false });
              }}
              style={{
                position: "absolute",
                bottom: 12,
                alignSelf: "center",
                width: 44,
                height: 44,
                borderRadius: 22,
                alignItems: "center",
                justifyContent: "center",
                backgroundColor: colors.accent,
                borderColor: colors.border,
                borderWidth: 1,
              }}
            >
              <NativeSymbol name="download" />
            </Pressable>
          )}
        </View>
        <ThreadComposer
          draft={draft}
          members={agents}
          mentionAll={collaborationActive}
          collaborationSessionId={collaborationSessionId}
          reply={reply}
          onCancelReply={() => updateDraft({ reply: null })}
          onChange={(text) => updateDraft({ text })}
          attachments={attachments}
          onRemove={(fileId) =>
            updateDraft({ attachments: attachments.filter((file) => file.id !== fileId) })
          }
          onAttach={() => void attach()}
          onSend={(mentions) => void send(mentions)}
          busy={busy}
          uploading={uploading}
          disabled={!thread}
          working={runs.some((run) => activeStatuses.includes(run.status))}
          onStop={() => {
            const run = runs.find((value) => activeStatuses.includes(value.status));
            if (run) void changeRun(run, "cancel");
          }}
        />
      </KeyboardAvoidingView>
    </Screen>
  );
}
