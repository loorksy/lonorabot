import type {
  Agent,
  Artifact,
  Group,
  Message,
  Run,
  Thread,
  TradeApproval,
} from "@lonora/contracts";
import {
  activeStatuses,
  type ConversationItem,
  conversationTimeline,
  type MentionAddress,
  needsTimeSeparator,
} from "@lonora/core";
// Persistent-thread navigation follows Tampletgrok's native thread screen; see NOTICE.
import * as DocumentPicker from "expo-document-picker";
import { Redirect, useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
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
import { GroupAvatar } from "../components/group-avatar";
import { Markdown } from "../components/markdown";
import { MessageBubble } from "../components/message-bubble";
import { NativeSymbol } from "../components/native-symbol";
import { ThreadComposer } from "../components/thread-composer";
import { ThreadHeader } from "../components/thread-header";
import { TimeSeparator } from "../components/time-separator";
import { TradeApprovalCard } from "../components/trade-approval";
import { Button, colors, ErrorNotice, Loading, Screen } from "../components/ui";
import { WorkingIndicator } from "../components/WorkingIndicator";
import { ApiError, api, upload } from "../lib/api";
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
  const { ready, owner, rtl, t, errorText } = useSession();
  const router = useRouter();
  const voice = useVoiceSession();
  const [thread, setThread] = useState<Thread | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [collaborationActive, setCollaborationActive] = useState(false);
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
  const receipt = useRef<{ signature: string; nonce: string } | null>(null);
  const reportError = useRef(errorText);
  reportError.current = errorText;

  const snapshot = useCallback(
    async (stillLive: () => boolean = () => true) => {
      if (!id) return;
      try {
        const [nextMessages, nextRuns, nextFiles, nextApprovals, collaboration] = await Promise.all(
          [
            api.get<Message[]>(`/threads/${encodeURIComponent(id)}/messages`),
            api.get<Run[]>(`/runs?thread_id=${encodeURIComponent(id)}`),
            api.get<Artifact[]>(`/artifacts?thread_id=${encodeURIComponent(id)}`),
            api.get<TradeApproval[]>(`/trading/approvals?thread_id=${encodeURIComponent(id)}`),
            api.get<{ state: { status: string } } | null>(
              `/threads/${encodeURIComponent(id)}/collaboration`,
            ),
          ],
        );
        if (!stillLive()) return;
        setMessages((old) => mergeMessages(old, nextMessages));
        setCollaborationActive(
          Boolean(
            collaboration &&
              !["completed", "cancelled", "expired", "failed"].includes(collaboration.state.status),
          ),
        );
        setRuns(nextRuns);
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
        setLoaded(true);
      } catch (reason) {
        if (stillLive()) setError(errorText(reason));
      }
    },
    [id, errorText],
  );

  useEffect(() => {
    setThread(null);
    setMessages([]);
    setRuns([]);
    setApprovals([]);
    setCollaborationActive(false);
    setAttachments([]);
    setFiles([]);
    setDraft("");
    setReply(null);
    setHasOlder(true);
    following.current = true;
    setAtEnd(true);
    setLoaded(false);
    receipt.current = null;
    if (!id || !owner) return;
    let live = true;
    void Promise.all([
      api.get<Thread>(`/threads/${encodeURIComponent(id)}`),
      api.get<Agent[]>("/agents"),
      api.get<Group[]>("/groups"),
    ])
      .then(([nextThread, nextAgents, nextGroups]) => {
        if (live) {
          setThread(nextThread);
          setAgents(nextAgents);
          setGroups(nextGroups);
        }
      })
      .catch((reason) => {
        if (live) setError(reportError.current(reason));
      });
    return () => {
      live = false;
    };
  }, [id, owner]);

  useFocusEffect(
    useCallback(() => {
      if (!ready || !owner || !id) return;
      let disposed = false;
      let timer: ReturnType<typeof setTimeout>;
      const tick = async () => {
        if (AppState.currentState === "active") await snapshot(() => !disposed);
        if (!disposed) timer = setTimeout(() => void tick(), 2500);
      };
      void Promise.all([api.get<Agent[]>("/agents"), api.get<Group[]>("/groups")])
        .then(([nextAgents, nextGroups]) => {
          if (!disposed) {
            setAgents(nextAgents);
            setGroups(nextGroups);
          }
        })
        .catch((reason) => {
          if (!disposed) setError(reportError.current(reason));
        });
      void tick();
      return () => {
        disposed = true;
        clearTimeout(timer);
      };
    }, [ready, owner, id, snapshot]),
  );

  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  const agent = agents.find((value) => value.id === thread?.agent_id);
  const group = groups.find((value) => value.id === thread?.group_id);
  const title = agent?.name ?? group?.payload.name ?? thread?.title ?? t("inbox");
  const send = async (mentions?: MentionAddress) => {
    if (busy || uploading || !thread || (!draft.trim() && !attachments.length)) return;
    const content = draft.trim() || t("attach");
    const attachment_ids = attachments.map((file) => file.id);
    const signature = JSON.stringify({
      content,
      attachment_ids,
      reply_to: reply?.id ?? null,
      mentions,
    });
    if (receipt.current?.signature !== signature)
      receipt.current = {
        signature,
        nonce: `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`,
      };
    setBusy(true);
    setError(null);
    try {
      await api.post(`/threads/${encodeURIComponent(id)}/messages`, {
        content,
        attachment_ids,
        reply_to: reply?.id ?? null,
        client_nonce: receipt.current.nonce,
        mention_agent_ids: mentions?.agent_ids ?? [],
        mention_all: mentions?.all ?? false,
      });
      following.current = true;
      setAtEnd(true);
      setDraft("");
      setAttachments([]);
      setReply(null);
      receipt.current = null;
      await snapshot();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setBusy(false);
    }
  };
  const attach = async () => {
    if (!thread || uploading || attachments.length >= 10) return;
    setUploading(true);
    setError(null);
    try {
      const result = await DocumentPicker.getDocumentAsync({
        copyToCacheDirectory: true,
        multiple: false,
      });
      if (!result.canceled) {
        const file = await upload(result.assets[0], id);
        setAttachments((old) => [...old, file]);
      }
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setUploading(false);
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
              identity={agent.name}
              color={agent.color}
              variant={agent.avatar}
              size={28}
              working={runs.some((run) => activeStatuses.includes(run.status))}
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
            onPress: () =>
              router.push({
                pathname: "/charts",
                params: { threadId: id, ...(agent ? { botId: agent.id } : {}) },
              }),
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
      <ErrorNotice text={error} />
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
                messages,
                approvals.filter((row) => row.thread_id === id),
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
                const previous = messages[messages.findIndex((row) => row.id === message.id) - 1];
                return (
                  <View>
                    {needsTimeSeparator(message.created_at, previous?.created_at) ? (
                      <TimeSeparator createdAt={message.created_at} />
                    ) : null}
                    <MessageBubble
                      message={message}
                      reply={messages.find((row) => row.id === message.reply_to)}
                      onReply={setReply}
                      grouped={Boolean(
                        previous &&
                          previous.role === message.role &&
                          previous.agent_id === message.agent_id &&
                          new Date(message.created_at).getTime() -
                            new Date(previous.created_at).getTime() <
                            180000,
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
                <View style={{ gap: 12 }}>
                  {runs
                    .filter(
                      (run) =>
                        activeStatuses.includes(run.status) &&
                        run.stream?.phase === "streaming" &&
                        run.stream.text &&
                        (!run.stream.message_id ||
                          !messages.some((message) => message.id === run.stream?.message_id)),
                    )
                    .map((run) => (
                      <View key={run.id} accessibilityLabel={t("running")} style={{ gap: 8 }}>
                        <Markdown content={run.stream?.text ?? ""} />
                      </View>
                    ))}
                  {runs.some((run) => activeStatuses.includes(run.status)) ? (
                    <WorkingIndicator />
                  ) : null}
                </View>
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
          reply={reply}
          onCancelReply={() => setReply(null)}
          onChange={setDraft}
          attachments={attachments}
          onRemove={(fileId) => setAttachments((old) => old.filter((file) => file.id !== fileId))}
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
