import type {
  Agent,
  Artifact,
  Event,
  ExecutionReceipt,
  Group,
  InputAnswer,
  Message,
  MessageReaction,
  OwnerAction,
  ReactionEmoji,
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
  liveAvatarState,
  type MentionAddress,
  mergeOwnerAction,
  needsTimeSeparator,
  projectRunEvents,
  retryableFailure,
  runStatusText,
  seedStream,
  stopTargets,
  streamForRun,
  submitMark,
  turnActivity,
} from "@lonora/core";
// Persistent-thread navigation follows Tampletgrok's native thread screen; see NOTICE.
import * as Clipboard from "expo-clipboard";
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
import { AgentPermissions } from "../components/agent-permissions";
import { BotAvatar } from "../components/bot-avatar";
import { useChartSheet } from "../components/chart-sheet";
import { ConversationQuestion } from "../components/conversation-question";
import { ExecutionReceiptCard } from "../components/execution-receipt";
import { CardHost, type CardHostValue } from "../components/genui/host";
import { GroupAvatar } from "../components/group-avatar";
import { MessageBubble } from "../components/message-bubble";
import { type MessageMenuActions, useMessageMenu } from "../components/message-menu";
import { NativeSymbol } from "../components/native-symbol";
import { OwnerActionCard } from "../components/owner-action-card";
import { SafetyPill } from "../components/safety-pill";
import { Icon } from "../components/shell/icon";
import { GroupBox, Row } from "../components/shell/kit";
import { useSheets } from "../components/shell/sheets";
import { useToast } from "../components/shell/toast";
import { ThreadComposer } from "../components/thread-composer";
import { ThreadHeader } from "../components/thread-header";
import { TimeSeparator } from "../components/time-separator";
import { TradeApprovalCard } from "../components/trade-approval";
import { TurnActivity } from "../components/turn-activity";
import { Button, ErrorNotice, Loading, Screen } from "../components/ui";
import { useAgentLiveState } from "../lib/agent-live-state";
import { ApiError, api, SessionRequestCancelled, uploadTransfer } from "../lib/api";
import {
  type ComposerDraft,
  composerDraft,
  consumeComposerDraft,
  editComposerDraft,
} from "../lib/composer-drafts";
import {
  composerUploads,
  handBack,
  handOver,
  startUpload,
  subscribeUploads,
  uploadsVersion,
} from "../lib/composer-uploads";
import {
  type ConversationSnapshot,
  conversationCache,
  type InboxSnapshot,
} from "../lib/conversation-cache";
import { projectConversation } from "../lib/conversation-projection";
import { markEditing, restoreDraft } from "../lib/draft-store";
import { type EventConnection, subscribeOwnerEvents } from "../lib/events";
import { taskFromMessage, withOwnerReaction } from "../lib/message-actions";
import {
  acknowledgeOutgoing,
  cancelOutgoingUploads,
  dropOutgoing,
  enqueueOutgoing,
  failOutgoing,
  hydrateOutgoing,
  type OutgoingIntent,
  OutgoingUploadFailed,
  outgoingKey,
  outgoingMessages,
  outgoingUploads,
  settleOutgoingUploads,
  subscribeFlushed,
  subscribeOutgoing,
  waitsForNetwork,
} from "../lib/outgoing-messages";
import { useSession } from "../lib/session";
import { useShellColors, useTheme } from "../lib/theme";
import { useVoiceSession } from "../lib/voice-session";

function mergeMessages(previous: Message[], incoming: Message[]): Message[] {
  const rows = new Map(previous.map((row) => [row.id, row]));
  for (const row of incoming) rows.set(row.id, row);
  return [...rows.values()].sort((a, b) => a.seq - b.seq);
}

export default function Conversation({ threadId }: { threadId?: string } = {}) {
  const params = useLocalSearchParams<{ id: string; around?: string | string[] }>();
  const id = threadId ?? params.id;
  const aroundRaw = Array.isArray(params.around) ? params.around[0] : params.around;
  const aroundNum = Number(aroundRaw);
  const around = Number.isInteger(aroundNum) && aroundNum > 0 ? aroundNum : null;
  const { ready, owner, server, rtl, locale, t, errorText } = useSession();
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
  const [ownerActions, setOwnerActions] = useState<OwnerAction[]>([]);
  const [receipts, setReceipts] = useState<ExecutionReceipt[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [draft, setDraft] = useState("");
  const [reply, setReply] = useState<Message | null>(null);
  // Edit and resend (Q21): the owner's message the next send replaces.
  const [editing, setEditing] = useState<Message | null>(null);
  // The owner's quick reactions as the server last answered them, until a snapshot carries them.
  const [reactions, setReactions] = useState<ReadonlyMap<string, MessageReaction[]>>(new Map());
  const reactionTurns = useRef(new Map<string, number>());
  const dropReactionOverrides = useCallback((rows: readonly Message[]) => {
    setReactions((old) => {
      if (!rows.some((row) => old.has(row.id))) return old;
      const next = new Map(old);
      for (const row of rows) if (!reactionTurns.current.has(row.id)) next.delete(row.id);
      return next;
    });
  }, []);
  const toast = useToast();
  const menuActions = useRef<() => MessageMenuActions>(() => {
    throw new Error("message_menu_unset");
  });
  const menu = useMessageMenu(useCallback(() => menuActions.current(), []));
  const sheets = useSheets();
  const editingKey = useRef<string | null>(null);
  const closeSheet = sheets.close;
  // A new conversation: the open menu, the edit and the reactions belong to the last one.
  // biome-ignore lint/correctness/useExhaustiveDependencies: `id` is the conversation that changed
  useEffect(() => {
    closeSheet();
    setEditing(null);
    setReactions(new Map());
    // Leaving the conversation ends an edit: its text does not stay behind as a new message.
    return () => {
      if (editingKey.current) {
        editComposerDraft(editingKey.current, { text: "" });
        markEditing(editingKey.current, false);
      }
      editingKey.current = null;
    };
  }, [id]);
  const [attachments, setAttachments] = useState<Artifact[]>([]);
  const [files, setFiles] = useState<Artifact[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [hasOlder, setHasOlder] = useState(true);
  const [actionsVisible, setActionsVisible] = useState(false);
  const list = useRef<FlatList<ConversationItem>>(null);
  const following = useRef(around == null);
  const jumped = useRef<number | null>(null);
  const shell = useShellColors();
  const [atEnd, setAtEnd] = useState(around == null);
  const [loaded, setLoaded] = useState(false);
  const [permissionRevision, setPermissionRevision] = useState(0);
  const permissionAgent = useRef(thread?.agent_id);
  permissionAgent.current = thread?.agent_id;
  // One live-state read for the header's safety pill and the background-activity strip.
  const liveState = useAgentLiveState(thread?.agent_id ?? undefined);
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
  const { c: shellTheme } = useTheme();
  const uploads = useSyncExternalStore(
    subscribeUploads,
    useCallback(() => composerUploads(outboxKey), [outboxKey]),
  );
  // Every upload's progress, a sent message's ring included.
  const uploadTick = useSyncExternalStore(
    subscribeUploads,
    useCallback(() => uploadsVersion(outboxKey), [outboxKey]),
  );
  // A finished upload has joined the stored draft: the composer shows it.
  // biome-ignore lint/correctness/useExhaustiveDependencies: `uploadTick` is the change signal
  useEffect(() => {
    setAttachments(composerDraft(outboxKey).attachments);
  }, [uploadTick, outboxKey]);
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
    // The draft this conversation had before the app restarted.
    let live = true;
    void restoreDraft(outboxKey).then((restored) => {
      if (!live || !restored) return;
      const saved = composerDraft(outboxKey);
      setDraft(saved.text);
      setAttachments(saved.attachments);
      setReply(saved.reply);
    });
    return () => {
      live = false;
    };
  }, [outboxKey]);
  // A message that waited for the network and went out by itself (Q6) joins this transcript,
  // and the snapshot brings the run it started.
  useEffect(
    () =>
      subscribeFlushed((key, message) => {
        if (key !== outboxKey || !conversationCache.current(scope)) return;
        setMessages((old) => mergeMessages(old, [message]));
        void snapshotRef.current();
      }),
    [outboxKey, scope],
  );
  const reportError = useRef(errorText);
  reportError.current = errorText;
  const say = useRef(t);
  say.current = t;

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
          // The server's reactions are the truth again for every message it sent.
          dropReactionOverrides(nextMessages);
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
          api.get<OwnerAction[]>(`/owner-actions?thread_id=${encodeURIComponent(id)}`),
          // Side data of its own: a failed read never stops the cards above from refreshing.
          api
            .get<ExecutionReceipt[]>(`/trading/receipts?thread_id=${encodeURIComponent(id)}`)
            .catch(() => [] as ExecutionReceipt[]),
        ]).then(
          ([nextFiles, nextApprovals, collaboration, refreshedAgents, nextCards, nextReceipts]) => {
            if (
              !stillLive() ||
              !conversationCache.current(scope) ||
              selected.current.id !== id ||
              selected.current.scope !== scope
            )
              return;
            setAgents(refreshedAgents);
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
            setOwnerActions((old) =>
              nextCards.map((row) => {
                const previous = old.find((item) => item.id === row.id);
                return previous ? mergeOwnerAction(previous, row) : row;
              }),
            );
            setApprovals((old) =>
              nextApprovals.map((row) => {
                const previous = old.find((item) => item.id === row.id);
                const rank = {
                  pending: 0,
                  approved: 1,
                  rejected: 1,
                  expired: 1,
                  withdrawn: 1,
                  drifted: 1,
                  completed: 2,
                  cancelled: 2,
                };
                return previous &&
                  (rank[previous.status] > rank[row.status] ||
                    (previous.status === row.status &&
                      previous.results.length > row.results.length))
                  ? previous
                  : row;
              }),
            );
            setReceipts(nextReceipts);
            setError(null);
          },
        );
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
    [id, scope, outboxKey, dropReactionOverrides],
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
    setOwnerActions([]);
    setReceipts([]);
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
          if (
            !disposed &&
            event.agent_id === permissionAgent.current &&
            ["agent.permission.updated", "account_authority.updated"].includes(event.kind)
          )
            setPermissionRevision((value) => value + 1);
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
          // An edit marks its original «مُعدّلة» on every client without a refetch.
          if (event.kind === "message.updated") {
            const value = event.payload;
            if (
              typeof value.id === "string" &&
              value.thread_id === id &&
              typeof value.content === "string" &&
              typeof value.seq === "number"
            ) {
              const message = value as unknown as Message;
              setMessages((old) =>
                old.some((row) => row.id === message.id) ? mergeMessages(old, [message]) : old,
              );
            }
          }
          if (event.kind === "message.reaction_updated") {
            const value = event.payload;
            if (
              value.thread_id === id &&
              typeof value.message_id === "string" &&
              Array.isArray(value.reactions)
            ) {
              const rows = value.reactions as MessageReaction[];
              setReactions((old) => new Map(old).set(value.message_id as string, rows));
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
  // A card's submission is sent at once, never through the auto-flushed outbox (docs/genui.md §7): the
  // server writes its bubble, and a retry after a failure is the owner's tap, not ours.
  /* A fixed card, drawn the same in its own row and in a trusted slot (mandate 10.2.3):
     one live record, one set of server actions. */
  const ownerActionCard = (action: OwnerAction) => (
    <OwnerActionCard
      row={action}
      onChange={(updated) => {
        setOwnerActions((old) =>
          old.map((row) => (row.id === updated.id ? mergeOwnerAction(row, updated) : row)),
        );
        // A decided card changes what the header pill says (a lifted pause,
        // Resume, a signed grant): read it now, not at the next poll.
        void liveState.refresh();
      }}
    />
  );
  const approvalCard = (approval: TradeApproval) => (
    <TradeApprovalCard
      row={approval}
      onChange={(updated) => {
        setApprovals((old) => old.map((row) => (row.id === updated.id ? updated : row)));
        void liveState.refresh();
      }}
    />
  );
  const cardHost: CardHostValue = {
    slot: ({ card, record }) => {
      if (card === "trade_approval") {
        const approval = approvals.find((row) => row.id === record && row.thread_id === id);
        return approval ? approvalCard(approval) : null;
      }
      const action = ownerActions.find(
        (row) => row.id === record && row.thread_id === id && row.kind === "settle_operation",
      );
      return action ? ownerActionCard(action) : null;
    },
    threadId: id,
    messages,
    runs,
    agents,
    reread: async (message) => {
      const rows = await api.get<Message[]>(
        `/threads/${encodeURIComponent(id)}/messages?around=${message.seq}&limit=1`,
      );
      const fresh = rows.filter((row) => row.id === message.id);
      if (!fresh.length || selected.current.id !== id || selected.current.scope !== scope) return;
      setMessages((old) => mergeMessages(old, fresh));
    },
    submit: async (body) => {
      const accepted = await api.post<{ message: Message; runs?: Run[] }>(
        `/threads/${encodeURIComponent(id)}/messages`,
        body,
      );
      const cached = conversationCache.get<ConversationSnapshot>(scope, `thread:${id}`);
      if (cached)
        conversationCache.set(scope, `thread:${id}`, {
          ...cached,
          messages: mergeMessages(cached.messages, [accepted.message]),
        });
      if (selected.current.id !== id || selected.current.scope !== scope) return;
      setMessages((old) => mergeMessages(old, [accepted.message]));
      if (accepted.runs?.length)
        setRuns((old) => {
          const projected = new Map(old.map((run) => [run.id, run]));
          for (const run of accepted.runs ?? []) {
            // A Run event that arrived before this response is newer: keep it.
            const prior = projected.get(run.id);
            if (!prior || Date.parse(run.updated_at) >= Date.parse(prior.updated_at))
              projected.set(run.id, run);
          }
          return [...projected.values()];
        });
      void snapshotRef.current();
    },
  };
  const deliver = async (sent: OutgoingIntent, targetKey: string, targetId: string) => {
    if (!conversationCache.current(scope) || deliveries.current.has(sent.nonce)) return;
    deliveries.current.add(sent.nonce);
    let intent = sent;
    try {
      // A message sent while its files were still uploading is posted once they are up;
      // its uploads cancelled, it is gone and nothing is posted.
      if (outgoingUploads(sent.nonce).length) {
        let ready: OutgoingIntent | null;
        try {
          ready = await settleOutgoingUploads(targetKey, sent.nonce);
        } catch (reason) {
          // An upload failed: the message, never posted, goes back to the composer with the
          // files that did arrive, so the owner's text is not lost.
          if (reason instanceof OutgoingUploadFailed) {
            const back = reason.intent.body;
            const typed =
              typeof back.content === "string" && back.content !== say.current("attach")
                ? back.content
                : "";
            const quoted = canonical.current.find((row) => row.id === back.reply_to) ?? null;
            const now = composerDraft(targetKey);
            const restored = editComposerDraft(targetKey, {
              text: now.text || typed,
              attachments: [...now.attachments, ...reason.finished],
              reply: now.reply ?? quoted,
            });
            if (selected.current.id === targetId && selected.current.scope === scope) {
              setDraft(restored.text);
              setAttachments(restored.attachments);
              setReply(restored.reply);
              setError(reportError.current(reason.cause));
            }
            return;
          }
          if (selected.current.id === targetId && !(reason instanceof SessionRequestCancelled))
            setError(reportError.current(reason));
          return;
        }
        if (!ready) return;
        intent = ready;
      }
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
      // Q6: plain text the API never answered waits for the network and goes out by itself.
      if (waitsForNetwork(reason, intent.body)) {
        failOutgoing(targetKey, intent.nonce, "queued");
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
    // Files that never arrived cannot be sent again: only «حذف» is left.
    if (prior.message.uploading?.length) return;
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

  // A search hit: load the page centred on it, then leave the latest-message pin so the
  // list can rest on that message instead of the bottom.
  useEffect(() => {
    if (around == null || !id) return;
    let live = true;
    following.current = false;
    setAtEnd(false);
    void api
      .get<Message[]>(`/threads/${encodeURIComponent(id)}/messages?around=${around}`)
      .then((rows) => {
        if (!live) return;
        setMessages((old) => mergeMessages(old, rows));
        dropReactionOverrides(rows);
        if (!rows.some((row) => row.seq === around)) setError(say.current("messageGone"));
      })
      .catch((reason) => {
        if (live) setError(reportError.current(reason));
      });
    return () => {
      live = false;
    };
  }, [around, id, dropReactionOverrides]);
  // Messages drawn as a question's card instead of their rich content (MessageBubble
  // `body`): a slot in them is not drawn, so it never hides a fixed card's row (10.2.3).
  const undrawn = useMemo(
    () =>
      new Set(
        runs
          .flatMap((run) => run.input_requests ?? [])
          .filter((request) => request.choices.length)
          .map((request) => request.message_id),
      ),
    [runs],
  );
  useEffect(() => {
    if (around == null || !loaded || jumped.current === around) return;
    const index = conversationTimeline(
      visibleMessages,
      approvals.filter((row) => row.thread_id === id),
      ownerActions.filter((row) => row.thread_id === id),
      undrawn,
      receipts.filter((row) => row.thread_id === id),
    )
      .reverse()
      .findIndex((item) => item.kind === "message" && item.seq === around);
    if (index < 0) return;
    jumped.current = around;
    following.current = false;
    requestAnimationFrame(() => {
      list.current?.scrollToIndex({ index, viewPosition: 0.3, animated: false });
    });
  }, [around, loaded, visibleMessages, approvals, ownerActions, receipts, id, undrawn]);

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
      (!followUp?.trim() && !draft.trim() && !attachments.length && !uploads.length) ||
      // An edit replaces the message with new text, never with files alone.
      (!followUp && editing && !draft.trim())
    )
      return;
    const submittedDraft = composerDraft(outboxKey);
    const content = followUp?.trim() || draft.trim() || t("attach");
    const attachment_ids = followUp ? [] : attachments.map((file) => file.id);
    // Files still uploading go with the message, which waits for them.
    const handed = followUp ? [] : handOver(outboxKey);
    const edit = followUp ? null : editing;
    const reply_to = followUp || edit ? null : (reply?.id ?? null);
    const targetKey = outboxKey,
      targetId = id;
    const body = {
      content,
      attachment_ids,
      reply_to,
      mention_agent_ids: mentions?.agent_ids ?? [],
      mention_all: mentions?.all ?? false,
      collaboration_session_id: mentions?.collaboration_session_id,
      ...(edit ? { edited_from: edit.id } : {}),
    };
    const fingerprint = JSON.stringify([targetId, body, handed.map((file) => file.id)]);
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
        handed,
        followUp ? [] : attachments,
      );
      const nextDraft = followUp
        ? composerDraft(targetKey)
        : consumeComposerDraft(targetKey, submittedDraft.revision);
      if (current()) {
        following.current = true;
        setAtEnd(true);
        if (edit) {
          editingKey.current = null;
          markEditing(targetKey, false);
          setEditing(null);
        }
        if (!followUp) {
          setDraft(nextDraft.text);
          setAttachments(nextDraft.attachments);
          setReply(nextDraft.reply);
        }
      }
    } catch (reason) {
      // The picked files go back to the composer with the text.
      handBack(targetKey, handed);
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
  // «+»: Files or Photos from the system picker (no storage or camera permission), several
  // at once; each file uploads on its own with a ring and a cancel, as on Web.
  const pick = async (kind: "files" | "photos") => {
    if (!thread || uploading) return;
    const room = 10 - attachments.length - uploads.length;
    if (room <= 0) return;
    const targetId = id,
      targetKey = outboxKey;
    setUploading(true);
    setError(null);
    try {
      const result = await DocumentPicker.getDocumentAsync({
        copyToCacheDirectory: true,
        multiple: true,
        ...(kind === "photos" ? { type: "image/*" } : {}),
      });
      if (result.canceled || !conversationCache.current(scope)) return;
      if (result.assets.length > room) setError(t("attachLimit"));
      for (const asset of result.assets.slice(0, room)) {
        const upload = startUpload(
          targetKey,
          {
            name: asset.name,
            size: asset.size ?? 0,
            media_type: asset.mimeType ?? "application/octet-stream",
          },
          uploadTransfer(asset, targetId),
        );
        upload.done.catch((reason) => {
          // A cancelled upload is the owner's choice, not an error.
          if (reason instanceof SessionRequestCancelled || upload.sent) return;
          if (selected.current.id === targetId) setError(reportError.current(reason));
        });
      }
    } catch (reason) {
      if (current()) setError(errorText(reason));
    } finally {
      if (current()) setUploading(false);
    }
  };
  const attach = () =>
    sheets.open({
      id: "attach",
      title: t("addToConversation"),
      body: (
        <GroupBox>
          <Row
            lead={<Icon name="file" size={22} color={shellTheme.text} />}
            title={t("pickFiles")}
            onPress={() => {
              sheets.close();
              void pick("files");
            }}
          />
          <Row
            lead={<Icon name="image" size={22} color={shellTheme.text} />}
            title={t("pickPhotos")}
            sub={t("attachLimit")}
            last
            onPress={() => {
              sheets.close();
              void pick("photos");
            }}
          />
        </GroupBox>
      ),
    });
  // Stop cancels every cancellable Run of the thread, a queued card submission included,
  // as web does (docs/genui.md §7, rule L).
  const stopActive = async () => {
    if (!id) return;
    const active = stopTargets(runs, id);
    if (!active.length) return;
    setBusy(true);
    setError(null);
    try {
      await Promise.all(active.map((run) => api.post(`/runs/${run.id}/cancel`, {})));
      await snapshot();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setBusy(false);
    }
  };
  const react = async (message: Message, emoji: ReactionEmoji | null) => {
    const path = `/threads/${encodeURIComponent(id)}/messages/${encodeURIComponent(message.id)}/reactions`;
    const before = reactions.get(message.id) ?? message.reactions;
    const turn = (reactionTurns.current.get(message.id) ?? 0) + 1;
    reactionTurns.current.set(message.id, turn);
    const latest = () => reactionTurns.current.get(message.id) === turn;
    setReactions((old) =>
      new Map(old).set(message.id, withOwnerReaction(before, emoji, new Date().toISOString())),
    );
    try {
      const result = emoji
        ? await api.put<{ reactions: MessageReaction[] }>(
            `${path}/${encodeURIComponent(emoji)}`,
            {},
          )
        : await api.delete<{ reactions: MessageReaction[] }>(path);
      if (latest()) setReactions((old) => new Map(old).set(message.id, result.reactions));
    } catch (reason) {
      if (!latest()) return;
      setReactions((old) => {
        const next = new Map(old);
        if (before) next.set(message.id, before);
        else next.delete(message.id);
        return next;
      });
      toast(errorText(reason), { type: "error" });
    } finally {
      if (latest()) reactionTurns.current.delete(message.id);
    }
  };
  menuActions.current = () => ({
    onReply: (message) => {
      if (editing) endEdit();
      updateDraft({ reply: message });
    },
    onCopy: (message) =>
      void Clipboard.setStringAsync(message.content).then(
        (done) =>
          done === false
            ? toast(t("copyFailed"), { type: "error" })
            : toast(t("copied"), { type: "success" }),
        () => toast(t("copyFailed"), { type: "error" }),
      ),
    onEdit: (message) => {
      editingKey.current = outboxKey;
      markEditing(outboxKey, true);
      setEditing(message);
      updateDraft({ text: message.content, reply: null });
    },
    onTask: (message) => {
      const owner = message.agent_id ?? thread?.agent_id ?? agents[0]?.id ?? "";
      void api
        .post(
          `/tasks?agent_id=${encodeURIComponent(owner)}&thread_id=${encodeURIComponent(id)}`,
          taskFromMessage(message),
        )
        .then(
          () => {
            toast(t("taskCreated"), { type: "success" });
            liveState.refresh();
          },
          (reason) => toast(errorText(reason), { type: "error" }),
        );
    },
    onReact: (message, emoji) => void react(message, emoji),
    onRetry: (nonce) => void retryOutgoing(nonce),
    onDrop: (nonce) => dropOutgoing(outboxKey, nonce),
    reactorName: (reactor) => agents.find((row) => row.id === reactor)?.name ?? t("system"),
  });
  /** An edit ends without sending: its text leaves the composer with it. */
  function endEdit() {
    if (editingKey.current) markEditing(editingKey.current, false);
    editingKey.current = null;
    setEditing(null);
    updateDraft({ text: "" });
  }
  // A tap on a quote: the list rests on the quoted message (loaded around it when needed).
  const jumpTo = (message: Message) => {
    jumped.current = null;
    router.setParams({ around: String(message.seq) });
  };
  // Q22: Retry re-asks only an owner's reply, as the server and Web's error card do; the
  // banner shows one run, so mobile offers it for the newest such failure only.
  const retry = retryableFailure(
    runs.filter((run) => run.thread_id === id),
    Date.now(),
  );
  const changeRun = async (run: Run, action: "cancel" | "resume" | "retry") => {
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
    <Screen background={shell.background}>
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
        safety={
          agent ? (
            <SafetyPill
              readiness={liveState.state?.trading_readiness ?? null}
              agents={agents}
              onChanged={liveState.refresh}
            />
          ) : undefined
        }
        avatar={
          agent ? (
            <BotAvatar
              tradesOnItsOwn={agent.trades_on_its_own}
              identity={agent.id}
              color={agent.color}
              variant={agent.avatar}
              size={28}
              state={(() => {
                const active = [...runs]
                  .reverse()
                  .find((run) => activeStatuses.includes(run.status));
                // Between runs the avatar follows the agent's server phase.
                if (!active) return liveAvatarState(liveState.state);
                if (connection !== "connected") return "connecting";
                return turnActivity(
                  { ...active, stream: streamForRun(active, streams[active.id]) },
                  events,
                ).avatar;
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
                color: run.status === "failed" ? shell.error : shell.secondary,
                textAlign: rtl ? "right" : "left",
              }}
            >
              {agents.find((value) => value.id === run.agent_id)?.name} ·{" "}
              {runStatusText(run.status, locale)}
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
            {retry?.run.id === run.id ? (
              <Button
                label={t("retry")}
                secondary
                disabled={busy || !retry.ready}
                onPress={() => void changeRun(run, "retry")}
              />
            ) : null}
          </View>
        ))}
      {thread?.agent_id && (
        <AgentLiveStatus
          state={liveState.state}
          error={liveState.error}
          refresh={liveState.refresh}
        />
      )}
      <KeyboardAvoidingView
        testID="thread-keyboard-layout-native"
        style={{ flex: 1, minHeight: 0 }}
        behavior={Platform.OS === "ios" ? "padding" : "height"}
      >
        <View style={{ flex: 1 }}>
          {!loaded || !thread ? (
            <Loading />
          ) : (
            <CardHost value={cardHost}>
              <FlatList
                ref={list}
                testID="conversation-transcript"
                inverted
                data={conversationTimeline(
                  visibleMessages,
                  approvals.filter((row) => row.thread_id === id),
                  ownerActions.filter((row) => row.thread_id === id),
                  undrawn,
                  receipts.filter((row) => row.thread_id === id),
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
                  if (following.current)
                    list.current?.scrollToOffset({ offset: 0, animated: false });
                }}
                onScrollToIndexFailed={(info) => {
                  list.current?.scrollToOffset({
                    offset: info.averageItemLength * info.index,
                    animated: false,
                  });
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
                  <Text style={{ color: shell.secondary, textAlign: "center", padding: 24 }}>
                    {t("waitingMessage")}
                  </Text>
                }
                renderItem={({ item }) => {
                  if (item.kind === "receipt") return <ExecutionReceiptCard row={item.receipt} />;
                  if (item.kind === "owner_action") return ownerActionCard(item.action);
                  if (item.kind === "approval") return approvalCard(item.approval);
                  const message = item.message;
                  const question = questions.get(message.id);
                  const previous =
                    visibleMessages[visibleMessages.findIndex((row) => row.id === message.id) - 1];
                  const responseRun = message.id.startsWith("preview:")
                    ? runs.find((run) => `preview:${run.id}` === message.id)
                    : undefined;
                  return (
                    <View testID={item.seq === around ? "around-message" : undefined}>
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
                        mark={submitMark(message)}
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
                        message={
                          reactions.has(message.id)
                            ? { ...message, reactions: reactions.get(message.id) }
                            : message
                        }
                        onMenu={message.id.startsWith("preview:") ? undefined : menu.open}
                        onReactions={menu.reactions}
                        onQuote={jumpTo}
                        onCancelUploads={(nonce) => cancelOutgoingUploads(outboxKey, nonce)}
                        body={
                          question?.choices.length ? (
                            <ConversationQuestion request={question} onAnswer={answerQuestion} />
                          ) : undefined
                        }
                        reply={messages.find((row) => row.id === message.reply_to)}
                        onReply={
                          message.id.startsWith("preview:")
                            ? undefined
                            : (value) => {
                                if (editing) endEdit();
                                updateDraft({ reply: value });
                              }
                        }
                        onRetry={(nonce) => void retryOutgoing(nonce)}
                        previousVisualMessageId={(() => {
                          const settled = runs.find(
                            (run) =>
                              (streams[run.id]?.message_id ?? run.stream?.message_id) ===
                              message.id,
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
                      style={{ color: shell.secondary, padding: 8 }}
                    >
                      {t("sending")}
                    </Text>
                  ) : null
                }
              />
            </CardHost>
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
                backgroundColor: shell.accent,
                borderColor: shell.border,
                borderWidth: 1,
              }}
            >
              <NativeSymbol name="download" />
            </Pressable>
          )}
        </View>
        <ThreadComposer
          permissionControl={
            agent && !thread?.group_id ? (
              <AgentPermissions
                agent={agent}
                threadId={id}
                revision={permissionRevision}
                pendingTrade={approvals.some(
                  (row) =>
                    row.thread_id === id && row.agent_id === agent.id && row.status === "pending",
                )}
              />
            ) : undefined
          }
          draft={draft}
          members={agents}
          direct={!thread?.group_id}
          self={thread?.group_id ? null : agent?.id}
          mentionAll={collaborationActive}
          collaborationSessionId={collaborationSessionId}
          reply={reply}
          onCancelReply={() => updateDraft({ reply: null })}
          editing={editing}
          onCancelEdit={endEdit}
          onChange={(text) => updateDraft({ text })}
          attachments={attachments}
          onRemove={(fileId) =>
            updateDraft({ attachments: attachments.filter((file) => file.id !== fileId) })
          }
          onAttach={attach}
          uploads={uploads}
          onCancelUpload={(uploadId) => {
            for (const file of uploads) if (file.id === uploadId) file.cancel();
          }}
          onSend={(mentions) => void send(mentions)}
          busy={busy}
          uploading={uploading}
          disabled={!thread}
          working={runs.some((run) => activeStatuses.includes(run.status))}
          onStop={() => void stopActive()}
        />
      </KeyboardAvoidingView>
    </Screen>
  );
}
