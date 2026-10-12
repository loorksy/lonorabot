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
  TextInput,
  View,
} from "react-native";
import { AgentAvatar } from "../components/AgentAvatar";
import { Button, colors, ErrorNotice, Header, Loading, Screen } from "../components/ui";
import { ApiError, api, upload } from "../lib/api";
import { useSession } from "../lib/session";
import {
  type Agent,
  type Artifact,
  activeStatuses,
  type Group,
  type Message,
  type Run,
  type Thread,
} from "../lib/types";

function mergeMessages(previous: Message[], incoming: Message[]): Message[] {
  const rows = new Map(previous.map((row) => [row.id, row]));
  for (const row of incoming) rows.set(row.id, row);
  return [...rows.values()].sort((a, b) => a.seq - b.seq);
}

export default function Conversation() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { ready, owner, rtl, locale, t, errorText } = useSession();
  const router = useRouter();
  const [thread, setThread] = useState<Thread | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [draft, setDraft] = useState("");
  const [attachments, setAttachments] = useState<Artifact[]>([]);
  const [files, setFiles] = useState<Artifact[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [hasOlder, setHasOlder] = useState(true);
  const list = useRef<FlatList<Message>>(null);
  const lastMessage = useRef<string | null>(null);
  const receipt = useRef<{ signature: string; nonce: string } | null>(null);
  const reportError = useRef(errorText);
  reportError.current = errorText;

  const snapshot = useCallback(
    async (stillLive: () => boolean = () => true) => {
      if (!id) return;
      try {
        const [nextMessages, nextRuns, nextFiles] = await Promise.all([
          api.get<Message[]>(`/threads/${encodeURIComponent(id)}/messages`),
          api.get<Run[]>(`/runs?thread_id=${encodeURIComponent(id)}`),
          api.get<Artifact[]>(`/artifacts?thread_id=${encodeURIComponent(id)}`),
        ]);
        if (!stillLive()) return;
        setMessages((old) => mergeMessages(old, nextMessages));
        setRuns(nextRuns);
        setFiles(nextFiles);
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
    setAttachments([]);
    setFiles([]);
    setDraft("");
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
    const signature = JSON.stringify({ content, attachment_ids });
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
        client_nonce: receipt.current.nonce,
      });
      setDraft("");
      setAttachments([]);
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
      <Header
        title={title}
        left={
          <Button
            label={t("back")}
            secondary
            onPress={() => (router.canGoBack() ? router.back() : router.replace("/"))}
          />
        }
        right={
          agent ? (
            <AgentAvatar
              color={agent.color}
              variant={agent.avatar}
              size={38}
              working={runs.some((run) => activeStatuses.includes(run.status))}
            />
          ) : undefined
        }
      />
      <ErrorNotice text={error} />
      {runs
        .filter((run) => run.status !== "completed" && run.status !== "cancelled")
        .slice(0, 5)
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
            gap: 16,
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
          renderItem={({ item }) => {
            const author = agents.find((value) => value.id === item.agent_id);
            const isOwner = item.role === "user";
            return (
              <View
                style={{
                  alignSelf: isOwner ? (rtl ? "flex-start" : "flex-end") : "stretch",
                  maxWidth: isOwner ? "90%" : "100%",
                  backgroundColor: isOwner ? colors.chatUser : "transparent",
                  borderRadius: 18,
                  padding: isOwner ? 14 : 4,
                  gap: 8,
                }}
              >
                <View
                  style={{
                    flexDirection: rtl ? "row-reverse" : "row",
                    alignItems: "center",
                    gap: 8,
                  }}
                >
                  {author && !isOwner ? (
                    <AgentAvatar color={author.color} variant={author.avatar} size={24} />
                  ) : null}
                  <Text style={{ color: colors.secondary, fontSize: 12 }}>
                    {isOwner
                      ? t("you")
                      : item.role === "tool"
                        ? t("tool")
                        : (author?.name ?? t("system"))}
                  </Text>
                  <Text style={{ color: colors.secondary, fontSize: 11 }}>
                    {new Date(item.created_at).toLocaleTimeString(locale, {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </Text>
                </View>
                <Text
                  selectable
                  style={{
                    color: colors.foreground,
                    fontSize: item.role === "tool" ? 13 : 16,
                    lineHeight: 25,
                    writingDirection: "auto",
                  }}
                >
                  {item.content}
                </Text>
                {item.attachment_ids.map((fileId) => (
                  <Text
                    key={fileId}
                    style={{ color: colors.secondary, fontSize: 13, writingDirection: "auto" }}
                  >
                    ↗ {files.find((file) => file.id === fileId)?.payload.name ?? t("attach")}
                  </Text>
                ))}
              </View>
            );
          }}
        />
        <View
          style={{
            borderTopWidth: 1,
            borderColor: colors.border,
            paddingHorizontal: 16,
            paddingTop: 10,
            paddingBottom: 12,
            gap: 8,
          }}
        >
          {attachments.map((file) => (
            <Pressable
              key={file.id}
              accessibilityLabel={`${t("removeAttachment")}: ${file.payload.name}`}
              onPress={() => setAttachments((old) => old.filter((value) => value.id !== file.id))}
            >
              <Text style={{ color: colors.secondary, writingDirection: "auto" }}>
                × {file.payload.name}
              </Text>
            </Pressable>
          ))}
          <TextInput
            accessibilityLabel={t("message")}
            placeholder={t("message")}
            value={draft}
            onChangeText={setDraft}
            multiline
            maxLength={30000}
            editable={!busy}
            placeholderTextColor={colors.secondary}
            style={{
              color: colors.foreground,
              backgroundColor: colors.muted,
              borderRadius: 18,
              minHeight: 52,
              maxHeight: 160,
              fontSize: 16,
              padding: 14,
              textAlign: rtl ? "right" : "left",
              writingDirection: "auto",
            }}
          />
          <View
            style={{
              flexDirection: rtl ? "row-reverse" : "row",
              justifyContent: "space-between",
              gap: 12,
            }}
          >
            <Button
              label={uploading ? t("connecting") : t("attach")}
              secondary
              onPress={() => void attach()}
              disabled={busy || uploading || !thread || attachments.length >= 10}
            />
            <Button
              label={busy ? t("connecting") : t("send")}
              onPress={() => void send()}
              disabled={busy || uploading || !thread || (!draft.trim() && !attachments.length)}
            />
          </View>
        </View>
      </KeyboardAvoidingView>
    </Screen>
  );
}
