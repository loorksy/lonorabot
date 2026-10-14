import type {
  Agent,
  Artifact,
  Group,
  Message,
  Run,
  Thread,
  TradeApproval,
} from "@lonora/contracts";
import { activeStatuses, needsTimeSeparator } from "@lonora/core";
// Persistent-thread navigation follows Tampletgrok's native thread screen; see NOTICE.
import * as DocumentPicker from "expo-document-picker";
import { Redirect, useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { AppState, FlatList, KeyboardAvoidingView, Platform, Text, View } from "react-native";
import { ActionMenu } from "../components/action-menu";
import { BotAvatar } from "../components/bot-avatar";
import { GroupAvatar } from "../components/group-avatar";
import { Markdown } from "../components/markdown";
import { MessageBubble } from "../components/message-bubble";
import { ThreadComposer } from "../components/thread-composer";
import { ThreadHeader } from "../components/thread-header";
import { TimeSeparator } from "../components/time-separator";
import { TradeApprovalCard } from "../components/trade-approval";
import { Button, colors, ErrorNotice, Loading, Screen } from "../components/ui";
import { WorkingIndicator } from "../components/WorkingIndicator";
import { ApiError, api, upload } from "../lib/api";
import { useSession } from "../lib/session";

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
  const [thread, setThread] = useState<Thread | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
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
  const list = useRef<FlatList<Message>>(null);
  const lastMessage = useRef<string | null>(null);
  const receipt = useRef<{ signature: string; nonce: string } | null>(null);
  const reportError = useRef(errorText);
  reportError.current = errorText;

  const snapshot = useCallback(
    async (stillLive: () => boolean = () => true) => {
      if (!id) return;
      try {
        const [nextMessages, nextRuns, nextFiles, nextApprovals] = await Promise.all([
          api.get<Message[]>(`/threads/${encodeURIComponent(id)}/messages`),
          api.get<Run[]>(`/runs?thread_id=${encodeURIComponent(id)}`),
          api.get<Artifact[]>(`/artifacts?thread_id=${encodeURIComponent(id)}`),
          api.get<TradeApproval[]>(`/trading/approvals?thread_id=${encodeURIComponent(id)}`),
        ]);
        if (!stillLive()) return;
        setMessages((old) => mergeMessages(old, nextMessages));
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
        const latest = nextMessages.at(-1)?.id ?? null;
        if (latest && lastMessage.current !== latest) {
          lastMessage.current = latest;
          requestAnimationFrame(() => list.current?.scrollToEnd({ animated: false }));
        }
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
    setAttachments([]);
    setFiles([]);
    setDraft("");
    setReply(null);
    setHasOlder(true);
    lastMessage.current = null;
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
  const send = async () => {
    if (busy || uploading || !thread || (!draft.trim() && !attachments.length)) return;
    const content = draft.trim() || t("attach");
    const attachment_ids = attachments.map((file) => file.id);
    const signature = JSON.stringify({ content, attachment_ids, reply_to: reply?.id ?? null });
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
      });
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
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <FlatList
          ref={list}
          data={messages}
          keyExtractor={(message) => message.id}
          contentContainerStyle={{
            paddingHorizontal: 16,
            paddingVertical: 14,
            flexGrow: 1,
            gap: 12,
          }}
          ListHeaderComponent={
            messages.length >= 100 && hasOlder ? (
              <Button label={t("older")} secondary disabled={busy} onPress={() => void older()} />
            ) : null
          }
          ListEmptyComponent={
            <Text style={{ color: colors.secondary, textAlign: "center", padding: 24 }}>
              {thread ? t("waitingMessage") : t("connecting")}
            </Text>
          }
          renderItem={({ item, index }) => (
            <View>
              {needsTimeSeparator(item.created_at, messages[index - 1]?.created_at) ? (
                <TimeSeparator createdAt={item.created_at} />
              ) : null}
              <MessageBubble
                message={item}
                reply={messages.find((row) => row.id === item.reply_to)}
                onReply={setReply}
                grouped={
                  index > 0 &&
                  messages[index - 1].role === item.role &&
                  messages[index - 1].agent_id === item.agent_id &&
                  new Date(item.created_at).getTime() -
                    new Date(messages[index - 1].created_at).getTime() <
                    180000
                }
                agent={agents.find((value) => value.id === item.agent_id)}
                files={files}
                onArtifact={(fileId) =>
                  router.push({ pathname: "/artifact", params: { artifactId: fileId } })
                }
              />
            </View>
          )}
          ListFooterComponent={
            <View style={{ gap: 12 }}>
              {approvals
                .filter((row) => row.thread_id === id)
                .map((row) => (
                  <TradeApprovalCard
                    key={row.id}
                    row={row}
                    onChange={(updated) =>
                      setApprovals((old) =>
                        old.map((item) => (item.id === updated.id ? updated : item)),
                      )
                    }
                  />
                ))}
              {runs
                .filter(
                  (run) =>
                    activeStatuses.includes(run.status) &&
                    run.stream?.phase === "streaming" &&
                    run.stream.text,
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
        <ThreadComposer
          draft={draft}
          members={
            group ? agents.filter((value) => group.payload.member_ids.includes(value.id)) : []
          }
          reply={reply}
          onCancelReply={() => setReply(null)}
          onChange={setDraft}
          attachments={attachments}
          onRemove={(fileId) => setAttachments((old) => old.filter((file) => file.id !== fileId))}
          onAttach={() => void attach()}
          onSend={() => void send()}
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
