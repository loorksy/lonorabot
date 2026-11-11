import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { Journal, OwnerAction, TradeApproval, VisualAction } from "@lonora/contracts";
import {
  conversationTimeline,
  isWorking,
  type MentionAddress,
  nearConversationBottom,
  retriedRunIds,
  stopTargets,
  turnActivity,
} from "@lonora/core";
import { GroupAvatar, Icon } from "@lonora/ui-web";
import {
  Fragment,
  type ReactNode,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { AgentAvatar } from "../components/ai/AgentAvatar";
import { FilePreviewPanel } from "../components/common/FilePreviewPanel";
import { GenuiHost } from "../components/genui";
import { OwnerActionCard, useOwnerActions } from "../components/owner-actions/OwnerActionCard";
import { TradeApprovalCard, useTradeApprovals } from "../components/trading/TradeApprovals";
import { useTheme } from "../hooks/useTheme";
import { useThreads } from "../hooks/useThreads";
import type { Agent, Message as ApiMessage, Resource, Run } from "../lib/api";
import { api, isRequestCancelled } from "../lib/api";
import { stickToLatest } from "../lib/chat-scroll";
import { draftKey, readComposerDraft } from "../lib/composer-drafts";
import { failedReplies } from "../lib/failed-replies";
import { isOutgoingMessage } from "../lib/outgoing-messages";
import { streamForRun } from "../lib/response_streaming";
import { activityTimeline, stepsSeconds, streamVisible } from "../lib/stream-timeline";
import { userError } from "../lib/user_error";
import { useClient } from "../providers/ClientProvider";
import { ownerDisplayName, useShellData } from "../shell/data";
import type { TaskView } from "../shell/domain/api";
import { usePopover } from "../shell/lists/Popover";
import { useNetworkPhase } from "../shell/NetworkStrip";
import { useNavigation } from "../shell/navigation";
import { useSheets } from "../shell/sheets/SheetHost";
import { useToast } from "../shell/Toast";
import {
  AgentErrorCard,
  type FailureFamily,
  OrderLine,
  OrderSheetBody,
  PeerCard,
  peersByMessage,
  QuestionCard,
  Steps,
  TaskCard,
} from "./Cards";
import { Composer, type ComposerSend } from "./Composer";
import {
  type ConversationApi,
  ConversationContext,
  type ConversationMessage,
  type MessageReaction,
  REACTIONS,
  voicePart,
} from "./context";
import { hasGenUi } from "./GenUiPart";
import { mentionPattern } from "./Markdown";
import { type LiveReply, Message, TypingBubble } from "./Message";
import { useChatPrefs } from "./prefs";
import { WALL_LEVELS, wallDefs } from "./wallpaper";
import "./conversation.css";

/* The conversation (reference chatPage/messages, Desktop-37 3726-3820, 5601-5621): day pills in
   the flow and a floating day while the owner scrolls, older pages behind skeleton bubbles, the
   ↓ button with the count of new answers, typing and streaming, the owner's cards in place. */

const CHAT_PAGE = 60;

function dayKey(iso: string) {
  const d = new Date(iso);
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}
function dayLabel(iso: string, locale: string) {
  const d = new Date(iso);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const day = new Date(d);
  day.setHours(0, 0, 0, 0);
  const diff = Math.round((today.getTime() - day.getTime()) / 864e5);
  if (diff <= 0) return t`Today`;
  if (diff === 1) return t`Yesterday`;
  const tag = locale.startsWith("ar") ? "ar-u-nu-latn" : locale;
  if (diff < 7) return d.toLocaleDateString(tag, { weekday: "long" });
  return d.toLocaleDateString(tag, {
    day: "numeric",
    month: "long",
    ...(d.getFullYear() !== today.getFullYear() ? { year: "numeric" } : {}),
  });
}

type Row =
  | { kind: "message"; id: string; message: ConversationMessage }
  | { kind: "approval"; id: string; approval: TradeApproval; at: string }
  | { kind: "owner_action"; id: string; action: OwnerAction; at: string }
  | { kind: "order"; id: string; journal: Journal; at: string }
  | { kind: "task"; id: string; task: TaskView; at: string };

export function Conversation({
  threadId,
  agentId,
  agents,
  conversationName,
  onOpenChart,
  knownRuns,
  aroundSeq,
  jumpTo,
  groupLead,
}: {
  threadId: string;
  /** The direct chat's agent; "" in a group. */
  agentId: string;
  agents: Agent[];
  conversationName?: string;
  onOpenChart?: (id: string) => void;
  knownRuns?: Run[];
  aroundSeq?: number;
  /** A card to bring into view on arrival («حسم» from another conversation's sheet). */
  jumpTo?: string;
  groupLead?: string;
}) {
  const agent = agents.find((row) => row.id === agentId);
  const isGroup = !agentId;
  const hiddenBefore =
    useShellData().inbox.find((entry) => entry.thread_id === threadId)?.hidden_before_seq ?? 0;
  const thread = useThreads(undefined, threadId, knownRuns, hiddenBefore);
  const { owner, events, revision, streams, seedStreams, connected, refresh } = useClient();
  const { theme } = useTheme();
  const prefs = useChatPrefs();
  const toast = useToast();
  const popover = usePopover();
  const sheets = useSheets();
  const nav = useNavigation();
  const approvals = useTradeApprovals(threadId);
  const ownerActions = useOwnerActions(threadId);
  const [artifacts, setArtifacts] = useState<Resource[]>([]);
  const [journal, setJournal] = useState<Journal[]>([]);
  const [tasks, setTasks] = useState<TaskView[]>([]);
  const [collaboration, setCollaboration] = useState<Resource | null>(null);
  const [peers, setPeers] = useState<Resource[]>([]);
  const [preview, setPreview] = useState<Resource | null>(null);
  const [reply, setReply] = useState<ApiMessage | null>(
    () => readComposerDraft(draftKey(owner.id, threadId)).reply,
  );
  const [editing, setEditing] = useState<ApiMessage | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [reactions, setReactions] = useState<Map<string, MessageReaction[]>>(new Map());
  const [stopped, setStopped] = useState<Set<string>>(new Set());
  const [jump, setJump] = useState<string | null>(jumpTo ? `${jumpTo}#arrival` : null);
  const [actionError, setActionError] = useState<unknown>();
  // Offline, the header's network strip explains failed background reads; the owner's own
  // action failing still shows.
  const net = useNetworkPhase(connected);
  const error =
    actionError ??
    (net === "off" || net === "connecting"
      ? undefined
      : (thread.error ?? approvals.error ?? ownerActions.error));

  useLayoutEffect(() => wallDefs(), []);
  // «عرض الطلب» / «حسم» in the AgentSheet: bring that card into view. A card that names
  // another conversation is left to the sheet, which opens that conversation instead.
  useEffect(() => {
    const listener = (event: Event) => {
      const detail = (event as CustomEvent<{ id: string; thread_id?: string | null }>).detail;
      if (!detail?.id || (detail.thread_id && detail.thread_id !== threadId)) return;
      event.preventDefault();
      setJump(`${detail.id}#${Date.now()}`);
    };
    window.addEventListener("lonora:jump", listener);
    return () => window.removeEventListener("lonora:jump", listener);
  }, [threadId]);

  /* ---- side data: files, order lines, the collaboration session */
  useEffect(() => {
    void revision;
    let live = true;
    void api
      .get<Resource[]>(`/artifacts?thread_id=${threadId}`)
      .then((rows) => live && setArtifacts(rows))
      .catch(() => undefined);
    void api
      .get<Journal[]>(`/trading/journal?thread_id=${encodeURIComponent(threadId)}`)
      .then(
        (rows) =>
          live &&
          setJournal(
            rows.filter((row) => (row as Journal & { thread_id?: string }).thread_id === threadId),
          ),
      )
      .catch(() => live && setJournal([]));
    void api
      .get<TaskView[]>(`/tasks?thread_id=${encodeURIComponent(threadId)}`)
      .then((rows) => live && setTasks(rows))
      .catch(() => undefined);
    void api
      .get<Resource[]>(`/peer-messages?thread_id=${encodeURIComponent(threadId)}`)
      .then((rows) => live && setPeers(rows))
      .catch(() => undefined);
    void api
      .get<Resource | null>(`/threads/${threadId}/collaboration`)
      .then((row) => live && setCollaboration(row))
      .catch(() => live && setCollaboration(null));
    return () => {
      live = false;
    };
  }, [threadId, revision]);

  useEffect(() => {
    seedStreams(thread.runs);
  }, [thread.runs, seedStreams]);
  // A stream with a gap is read again from its run (at most every 500 ms).
  const repairing = useRef(new Map<string, number>());
  useEffect(() => {
    void connected;
    for (const stream of Object.values(streams)) {
      if (!stream.gap || stream.thread_id !== threadId) continue;
      const last = repairing.current.get(stream.run_id) ?? 0;
      if (Date.now() - last < 500) continue;
      repairing.current.set(stream.run_id, Date.now());
      void api
        .get<Run>(`/runs/${stream.run_id}`)
        .then((run) => seedStreams([run]))
        .catch(() => undefined);
    }
  }, [streams, threadId, seedStreams, connected]);

  /* ---- a search hit: page around it and bring it into view */
  const loadAround = useRef(thread.around);
  loadAround.current = thread.around;
  useEffect(() => {
    if (aroundSeq == null) return;
    let live = true;
    void loadAround
      .current(aroundSeq)
      .then((rows) => {
        if (!live) return;
        const hit = rows.find((row) => row.seq === aroundSeq);
        // Arriving for a card: the page around its anchor is loaded; the jump stays on it.
        if (jumpTo) return;
        if (hit) setJump(hit.id);
        else toast(t`The message is no longer available.`);
      })
      .catch((error) => {
        if (live && !isRequestCancelled(error)) toast(t`The message is no longer available.`);
      });
    return () => {
      live = false;
    };
  }, [aroundSeq, toast, jumpTo]);

  /* ---- runs: what is active, streaming, failed */
  const runs = thread.runs.filter((run) => run.thread_id === threadId);
  const activeRuns = stopTargets(runs, threadId);
  const streamingRows = runs
    .map((run) => ({ run, stream: streamForRun(run, streams[run.id]) }))
    .filter(({ run, stream }) => streamVisible(run, stream, thread.messages))
    .flatMap(({ run, stream }) => (stream ? [{ run, stream }] : []));
  const streaming = streamingRows.some(({ stream }) => stream.phase === "streaming");
  const working = activeRuns.some((run) => isWorking(run.status));
  const failures = failedReplies(runs, thread.messages);
  const localEvents = events.filter((event) => event.thread_id === threadId);
  const timeline = activityTimeline(thread.messages, runs, streamingRows) as ConversationMessage[];

  const messages = useMemo(
    () =>
      timeline.map((message) => {
        const local = reactions.get(message.id);
        return local ? { ...message, reactions: local } : message;
      }),
    [timeline, reactions],
  );
  const byId = useMemo(() => new Map(messages.map((m) => [m.id, m])), [messages]);
  const runsById = useMemo(() => new Map(runs.map((run) => [run.id, run])), [runs]);
  const previews = new Map(streamingRows.map((row) => [`preview:${row.run.id}`, row]));
  const questions = new Map(
    runs.flatMap((run) => run.input_requests ?? []).map((request) => [request.message_id, request]),
  );
  const artifactMap = useMemo(() => new Map(artifacts.map((row) => [row.id, row])), [artifacts]);
  const previousVisualIds = useMemo(
    () =>
      new Map(
        runs.flatMap((run) => {
          // The run's committed stream names the message even while a local copy of the
          // same generation (seeded before the commit) does not.
          const id = run.stream?.message_id ?? streamForRun(run, streams[run.id])?.message_id;
          return id ? [[id, `preview:${run.id}`] as const] : [];
        }),
      ),
    [runs, streams],
  );
  const peerCards = useMemo(() => peersByMessage(peers), [peers]);
  const mentions = useMemo(() => mentionPattern(agents.map((row) => row.name)), [agents]);
  const callsByMessage = useMemo(() => {
    const out = new Map<string, { run: Run; seconds: number }>();
    for (const run of runs) {
      const id = run.stream?.message_id;
      if (!id) continue;
      out.set(id, {
        run,
        seconds: Math.max(
          1,
          Math.round((Date.parse(run.updated_at) - Date.parse(run.created_at)) / 1000),
        ),
      });
    }
    return out;
  }, [runs]);

  /* ---- the rows: messages, approvals, owner cards, order lines and task cards in server order */
  const rows: Row[] = useMemo(() => {
    const items = conversationTimeline(messages, approvals.rows, ownerActions.rows);
    const out: Row[] = items.map((item) =>
      item.kind === "message"
        ? { kind: "message", id: item.id, message: item.message as ConversationMessage }
        : item.kind === "approval"
          ? { kind: "approval", id: item.id, approval: item.approval, at: item.approval.created_at }
          : { kind: "owner_action", id: item.id, action: item.action, at: item.action.created_at },
    );
    const after = (at: string) =>
      out.findIndex(
        (item) => item.kind === "message" && Date.parse(item.message.created_at) > Date.parse(at),
      );
    const place = (line: Row, index: number) =>
      index < 0 ? out.push(line) : out.splice(index, 0, line);
    // Order lines sit at their anchor (WP-F journal thread_id/timeline_seq).
    for (const row of journal) {
      const seq = (row as Journal & { timeline_seq?: number | null }).timeline_seq;
      const at = row.submitted_at ?? row.updated_at;
      place(
        { kind: "order", id: `order:${row.operation_id}`, journal: row, at },
        seq != null
          ? out.findIndex((item) => item.kind === "message" && item.message.seq > seq)
          : after(at),
      );
    }
    // «أُنشئت مهمة»: a Task created from this conversation, at its creation time.
    for (const task of tasks)
      place(
        { kind: "task", id: `task:${task.id}`, task, at: task.created_at },
        after(task.created_at),
      );
    return out;
  }, [messages, approvals.rows, ownerActions.rows, journal, tasks]);

  /* ---- actions */
  const send: ComposerSend = useCallback(
    (text, attachments, replyTo, address, extra) => {
      thread.queue(text, attachments, replyTo, address, undefined, extra);
    },
    [thread],
  );
  const react = useCallback(
    async (message: ApiMessage, emoji: string | null) => {
      const path = `/threads/${threadId}/messages/${message.id}/reactions`;
      const before = (byId.get(message.id)?.reactions ?? []).filter(
        (row) => row.reactor !== "owner",
      );
      setReactions((old) =>
        new Map(old).set(
          message.id,
          emoji
            ? [
                ...before,
                {
                  reactor: "owner",
                  emoji: emoji as MessageReaction["emoji"],
                  created_at: new Date().toISOString(),
                },
              ]
            : before,
        ),
      );
      try {
        const result = emoji
          ? await api.put<{ reactions: MessageReaction[] }>(
              `${path}/${encodeURIComponent(emoji)}`,
              {},
            )
          : await api.delete<{ reactions: MessageReaction[] }>(path);
        setReactions((old) => new Map(old).set(message.id, result?.reactions ?? []));
      } catch (error) {
        setReactions((old) => {
          const next = new Map(old);
          next.delete(message.id);
          return next;
        });
        toast(userError(error), { type: "error" });
      }
    },
    [threadId, byId, toast],
  );
  const copy = useCallback(
    async (text: string) => {
      try {
        await navigator.clipboard.writeText(text);
        toast(t`Copied`, { type: "success" });
      } catch {
        toast(t`Could not copy`, { type: "error" });
      }
    },
    [toast],
  );
  const toTask = useCallback(
    async (message: ApiMessage) => {
      const owner = message.agent_id ?? agentId ?? agents[0]?.id;
      try {
        const task = await api.post<TaskView>(
          `/tasks?agent_id=${encodeURIComponent(owner ?? "")}&thread_id=${encodeURIComponent(threadId)}`,
          { title: message.content.slice(0, 160) || t`Task`, description: message.content },
        );
        setTasks((old) => [...old.filter((row) => row.id !== task.id), task]);
      } catch (error) {
        toast(userError(error), { type: "error" });
      }
    },
    [agentId, agents, threadId, toast],
  );
  const reactRow = (message: ConversationMessage) => {
    const mine = message.reactions?.find((row) => row.reactor === "owner")?.emoji;
    return (
      // biome-ignore lint/a11y/useSemanticElements: the reference's six quick reactions
      <div className="react-row" role="group" aria-label={t`Quick reaction`}>
        {REACTIONS.map((emoji) => (
          <button
            key={emoji}
            type="button"
            className={`react-btn${mine === emoji ? " on" : ""}`}
            aria-label={t`React ${emoji}`}
            aria-pressed={mine === emoji}
            onClick={() => {
              popover.close();
              void react(message, mine === emoji ? null : emoji);
            }}
          >
            {emoji}
          </button>
        ))}
      </div>
    );
  };
  const item = (
    icon: Parameters<typeof Icon>[0]["name"],
    label: string,
    run: () => void,
    danger = false,
  ) => (
    <button
      type="button"
      className={`pop-item${danger ? " danger" : ""}`}
      role="menuitem"
      onClick={() => {
        popover.close();
        run();
      }}
    >
      <Icon name={icon} />
      <span>{label}</span>
    </button>
  );
  const api_: ConversationApi = {
    threadId,
    ownerId: owner.id,
    threadAgentId: agentId,
    isGroup,
    agents,
    light: theme === "light",
    mentions,
    artifacts: artifactMap,
    byId,
    previousVisualIds,
    onVisualAction: async (action: VisualAction) => {
      if (action.kind === "follow_up") await thread.send(action.text);
      else if (action.kind === "open_artifact")
        setPreview(await api.get<Resource>(`/artifacts/${action.resource_id}`));
      else if (onOpenChart) onOpenChart(action.resource_id);
    },
    onReply: (message) => {
      setEditing(null);
      setReply(message);
    },
    onEdit: (message) => {
      setReply(null);
      setEditing(message);
    },
    onReact: (message, emoji) => void react(message, emoji),
    onRetry: (nonce) => void thread.retry(nonce).catch(() => undefined),
    onDrop: (nonce) => thread.drop(nonce),
    onJump: (id) => {
      if (byId.has(id)) setJump(`${id}#${Date.now()}`);
      else toast(t`The original message is no longer available.`);
    },
    onOpenImage: (artifact) =>
      sheets.open({
        id: "photo",
        bar: true,
        title: t`Photo`,
        body: (
          <div className="sheet-photo-box">
            <img
              className="sheet-photo"
              src={`/api/artifacts/${encodeURIComponent(artifact.id)}/file?preview=true`}
              alt={t`From the conversation`}
              ref={(node) => {
                if (node?.complete && node.naturalWidth) node.parentElement?.classList.add("ld");
              }}
              onLoad={(event) => event.currentTarget.parentElement?.classList.add("ld")}
            />
          </div>
        ),
      }),
    onOpenFile: setPreview,
    onMenu: (message, anchor) => {
      const outgoing = isOutgoingMessage(message) ? message : undefined;
      setSelected(message.id);
      if (outgoing?.delivery === "failed") {
        popover.open(
          anchor,
          <>
            <div className="pop-title">
              <Trans>The message was not sent</Trans>
            </div>
            {item(
              "refresh",
              t`Retry`,
              () => void thread.retry(outgoing.retry_nonce).catch(() => undefined),
            )}
            {item("trash", t`Delete`, () => thread.drop(outgoing.retry_nonce), true)}
          </>,
          t`Message options`,
          { onClose: () => setSelected(null) },
        );
        return;
      }
      const ownText =
        message.role === "user" &&
        !message.attachment_ids.length &&
        !voicePart(message) &&
        !message.superseded_by &&
        message.origin !== "ui_submit";
      popover.open(
        anchor,
        <>
          {reactRow(message)}
          <div className="pop-sep" />
          {item("reply", t`Reply`, () => api_.onReply(message))}
          {!voicePart(message) && item("copy", t`Copy text`, () => void copy(message.content))}
          {ownText && item("edit", t`Edit and resend`, () => api_.onEdit(message))}
          {!hasGenUi(message) &&
            !voicePart(message) &&
            !message.attachment_ids.length &&
            item("task", t`Turn into a task`, () => void toTask(message))}
        </>,
        t`Message options`,
        { cls: "msg-pop", above: true, onClose: () => setSelected(null) },
      );
    },
    onReactPicker: (message, anchor) => {
      setSelected(message.id);
      popover.open(anchor, reactRow(message), t`Quick reaction`, {
        cls: "react-pop",
        above: true,
        onClose: () => setSelected(null),
      });
    },
    onReactionList: (message, anchor) =>
      popover.open(
        anchor,
        <>
          <div className="pop-title">
            <Trans>Reactions</Trans>
          </div>
          {(message.reactions ?? []).map((row) =>
            row.reactor === "owner" ? (
              <button
                key="owner"
                type="button"
                className="pop-item"
                role="menuitem"
                onClick={() => {
                  popover.close();
                  void react(message, null);
                }}
              >
                <span className="pop-emo">{row.emoji}</span>
                <span>
                  <strong>
                    <Trans>You</Trans>
                  </strong>
                  <small>
                    <Trans>Tap to remove</Trans>
                  </small>
                </span>
              </button>
            ) : (
              <div key={row.reactor} className="pop-item static">
                <span className="pop-emo">{row.emoji}</span>
                <span>
                  <strong>{agents.find((a) => a.id === row.reactor)?.name ?? ""}</strong>
                </span>
              </div>
            ),
          )}
        </>,
        t`Reactions`,
        { cls: "react-list" },
      ),
    onCall: () =>
      window.dispatchEvent(new CustomEvent("lonora:start-call", { detail: { agentId } })),
  };

  // A retried reply's error card settles at once, before the runs list catches up.
  const [retriedHere, setRetriedHere] = useState<ReadonlySet<string>>(new Set());
  const retried = useMemo(
    () => new Set([...retriedRunIds(runs), ...retriedHere]),
    [runs, retriedHere],
  );
  const retryRun = useCallback(
    async (run: Run) => {
      await api.post(`/runs/${run.id}/retry`, {});
      setRetriedHere((old) => new Set(old).add(run.id));
      refresh();
    },
    [refresh],
  );
  const fixFailure = useCallback(
    (family: FailureFamily) => nav.go(family === "quota" ? "/app/usage" : "/app/providers"),
    [nav],
  );

  /* ---- scroll: follow the newest unless the owner scrolled up; older pages keep the offset */
  const scroll = useRef<HTMLDivElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const following = useRef(true);
  const anchored = useRef(0);
  const previous = useRef({ first: "", last: "", height: 0, count: 0 });
  const [far, setFar] = useState(false);
  const [fresh, setFresh] = useState(0);
  const [floatDay, setFloatDay] = useState("");
  const userScrollAt = useRef(0);
  const floatTimer = useRef(0);
  const answers = rows.filter(
    (row) => row.kind === "message" && row.message.role !== "user",
  ).length;
  useLayoutEffect(() => {
    const el = scroll.current;
    if (!el) return;
    const first = rows[0]?.id ?? "";
    const last = rows.at(-1)?.id ?? "";
    const old = previous.current;
    if (old.first && first !== old.first && last === old.last) {
      el.scrollTop += el.scrollHeight - old.height;
      if (!following.current) anchored.current = 0;
    } else {
      stickToLatest(
        el,
        following,
        anchored,
        nearConversationBottom(el.scrollHeight, el.clientHeight, el.scrollTop),
      );
      if (!following.current && answers > old.count && old.count)
        setFresh((n) => n + (answers - old.count));
    }
    previous.current = { first, last, height: el.scrollHeight, count: answers };
  }, [rows, answers]);
  // The message column mounts once the first page arrives (before that the empty state).
  const hasContent = rows.length > 0;
  // biome-ignore lint/correctness/useExhaustiveDependencies: re-attach when the column mounts.
  useEffect(() => {
    const target = content.current;
    if (!target) return;
    const observer = new ResizeObserver(() => {
      const el = scroll.current;
      if (!el) return;
      stickToLatest(
        el,
        following,
        anchored,
        nearConversationBottom(el.scrollHeight, el.clientHeight, el.scrollTop),
      );
      previous.current.height = el.scrollHeight;
    });
    observer.observe(target);
    if (scroll.current) observer.observe(scroll.current);
    return () => observer.disconnect();
  }, [hasContent]);
  // A jump (quote, search hit, «عرض الطلب»): ~29% from the top, then the flash.
  useLayoutEffect(() => {
    void rows;
    const el = scroll.current;
    if (!jump || !el) return;
    const id = jump.split("#")[0];
    const target = el.querySelector<HTMLElement>(
      `[data-message-id="${CSS.escape(id)}"],[data-owner-action="${CSS.escape(id)}"]`,
    );
    if (!target) return;
    setJump(null);
    following.current = false;
    const box = el.getBoundingClientRect();
    el.scrollTo({
      top:
        el.scrollTop +
        target.getBoundingClientRect().top -
        box.top -
        Math.max(24, el.clientHeight * 0.29),
      behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth",
    });
    target.classList.remove("flash");
    void target.offsetWidth;
    target.classList.add("flash");
    setTimeout(() => target.classList.remove("flash"), 1700);
  }, [jump, rows]);
  const syncFloat = () => {
    const el = scroll.current;
    if (!el || Date.now() - userScrollAt.current > 900) return;
    const line =
      el.getBoundingClientRect().top + (Number.parseFloat(getComputedStyle(el).paddingTop) || 0);
    let label = "";
    let clash = false;
    for (const d of el.querySelectorAll<HTMLElement>(".messages > .date")) {
      const r = d.getBoundingClientRect();
      if (r.top < line - 2) label = d.textContent ?? "";
      else {
        clash = r.top < line + 40;
        break;
      }
    }
    setFloatDay(label && !clash ? label : "");
    clearTimeout(floatTimer.current);
    floatTimer.current = window.setTimeout(() => setFloatDay(""), 1300);
  };

  /* ---- older pages: a sentinel of skeleton bubbles above the first message */
  const [hasOlder, setHasOlder] = useState(true);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const sentinel = useRef<HTMLDivElement>(null);
  // After a failed read the sentinel must leave the view and come back before the next
  // try: re-observing never fires a tight loop of failing reads.
  const olderFailed = useRef(false);
  const canPage = hasOlder && thread.messages.length >= CHAT_PAGE;
  const loadOlder = useRef(thread.older);
  loadOlder.current = thread.older;
  useEffect(() => {
    const node = sentinel.current;
    const root = scroll.current;
    if (!node || !root || !canPage) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) {
          olderFailed.current = false;
          return;
        }
        if (loadingOlder || olderFailed.current) return;
        setLoadingOlder(true);
        following.current = false;
        anchored.current = 0;
        // The page's own count says whether older history remains; a failed read leaves
        // paging on, so the sentinel tries again once it leaves and comes back into view.
        void loadOlder
          .current()
          .then((read) => {
            if (read === 0) setHasOlder(false);
          })
          .catch(() => {
            olderFailed.current = true;
          })
          .finally(() => setLoadingOlder(false));
      },
      { root, rootMargin: "200px 0px 0px 0px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [canPage, loadingOlder]);

  /* ---- render */
  const locale = document.documentElement.lang || "ar";
  const lastAgent = [...messages]
    .reverse()
    .find((m) => m.role !== "user" && !m.id.startsWith("activity:"));
  const lastIsConversational =
    lastAgent &&
    !hasGenUi(lastAgent) &&
    rows.at(-1)?.kind === "message" &&
    !questions.has(lastAgent.id);
  const lastMine = [...messages].reverse().find((m) => m.role === "user");
  const suggestion =
    lastIsConversational &&
    lastAgent.suggested_reply &&
    lastMine?.content.trim() !== lastAgent.suggested_reply
      ? lastAgent.suggested_reply
      : "";
  let day = "";
  const body: ReactNode[] = [];
  rows.forEach((row, index) => {
    const at = row.kind === "message" ? row.message.created_at : row.at;
    if (!(row.kind === "message" && row.message.id.startsWith("pending:"))) {
      const key = dayKey(at);
      if (key !== day) {
        day = key;
        body.push(
          <div className="date" key={`date:${key}`}>
            <span>{dayLabel(at, locale)}</span>
          </div>,
        );
      }
    }
    const prevRow = rows[index - 1];
    const prev = prevRow?.kind === "message" ? prevRow.message : undefined;
    if (row.kind === "approval") {
      body.push(
        <Message
          key={row.id}
          message={cardMessage(row.id, row.approval.agent_id, row.at, threadId)}
          previous={prev}
          cardKind={row.approval.status === "pending" ? "card" : "line"}
          card={
            <TradeApprovalCard
              row={row.approval}
              busy={approvals.busy != null}
              decide={approvals.decide}
              onRenew={(approval) =>
                void api
                  .post(`/trading/approvals/${approval.id}/renew`, {})
                  .catch((error) => toast(userError(error), { type: "error" }))
              }
            />
          }
        />,
      );
      return;
    }
    if (row.kind === "owner_action") {
      const pending = row.action.status === "pending";
      body.push(
        <Message
          key={row.id}
          message={cardMessage(row.action.id, row.action.agent_id, row.at, threadId)}
          previous={prev}
          cardKind={pending ? "oa" : "line"}
          card={
            <OwnerActionCard
              row={row.action}
              onChanged={ownerActions.update}
              onRenew={(action) =>
                void api
                  .post<OwnerAction>(`/owner-actions/${action.id}/renew`, {})
                  .then(ownerActions.update)
                  .catch((error) => toast(userError(error), { type: "error" }))
              }
              onLatest={(id) => setJump(`${id}#${Date.now()}`)}
            />
          }
        />,
      );
      return;
    }
    if (row.kind === "task") {
      body.push(
        <Message
          key={row.id}
          message={cardMessage(row.id, row.task.agent_id, row.at, threadId)}
          previous={prev}
          cardKind="card"
          card={<TaskCard task={row.task} onOpen={() => nav.go(`/app/tasks/${row.task.id}`)} />}
        />,
      );
      return;
    }
    if (row.kind === "order") {
      body.push(
        <Message
          key={row.id}
          message={cardMessage(row.id, row.journal.agent_id ?? agentId, row.at, threadId)}
          previous={prev}
          cardKind="odl"
          card={
            <OrderLine
              row={row.journal}
              onOpen={(journalRow) => {
                // «حسم العملية»: the operation's own pending resolve card in this chat.
                const resolve = ownerActions.rows.find(
                  (card) =>
                    card.kind === "resolve_operation" &&
                    card.status === "pending" &&
                    card.facts.operation?.operation_id === journalRow.operation_id,
                );
                sheets.open({
                  id: "order",
                  title: t`Trade order`,
                  body: (
                    <OrderSheetBody
                      row={journalRow}
                      onResolve={
                        resolve
                          ? () => {
                              sheets.close();
                              window.dispatchEvent(
                                new CustomEvent("lonora:jump", { detail: { id: resolve.id } }),
                              );
                            }
                          : undefined
                      }
                    />
                  ),
                });
              }}
            />
          }
        />,
      );
      return;
    }
    const message = row.message;
    if (message.id.startsWith("activity:")) {
      const run = runsById.get(message.id.slice("activity:".length));
      if (!run) return;
      const activity = turnActivity(run, localEvents);
      const calls = activity.calls;
      const responder = agents.find((a) => a.id === run.agent_id);
      body.push(
        calls.length && prefs.steps ? (
          <Message
            key={message.id}
            message={{ ...message, id: `preview:${run.id}` }}
            previous={prev}
            live={{
              text: "",
              streaming: false,
              runId: run.id,
              progress: true,
              phase: activity.phase,
            }}
            steps={<Steps calls={calls} running seconds={0} defaultOpen />}
          />
        ) : (
          <TypingBubble
            key={message.id}
            agent={responder}
            named={isGroup || run.agent_id !== agentId}
            runId={run.id}
            phase={activity.phase}
          />
        ),
      );
      return;
    }
    const streamRow = previews.get(message.id);
    if (streamRow) {
      const { run, stream } = streamRow;
      const activity = turnActivity({ ...run, stream }, localEvents);
      const calls = activity.calls;
      const live: LiveReply = {
        phase: activity.phase,
        text: stream.text,
        streaming: stream.phase === "streaming",
        rich: stream.rich_content,
        runId: run.id,
      };
      body.push(
        <Message
          key={message.id}
          message={{ ...message, agent_id: run.agent_id }}
          previous={prev}
          live={live}
          stopped={stream.phase === "cancelled" || stopped.has(run.id)}
          steps={
            prefs.steps && calls.length ? (
              <Steps
                calls={calls}
                running={!stream.text}
                seconds={stream.text ? stepsSeconds(run, calls) : 0}
                defaultOpen={prefs.stepsOpen}
              />
            ) : undefined
          }
        />,
      );
      return;
    }
    const question = questions.get(message.id);
    const peer = peerCards.get(message.id);
    const done = callsByMessage.get(message.id);
    const doneCalls = done ? turnActivity(done.run, localEvents).calls : [];
    body.push(
      <Message
        key={message.id}
        message={message}
        previous={prev}
        selected={selected === message.id}
        stopped={done?.run.status === "cancelled"}
        card={
          peer ? (
            <PeerCard
              message={message}
              peer={peer}
              run={runsById.get(String(peer.payload.run_id ?? ""))}
            />
          ) : question?.choices.length ? (
            <QuestionCard
              request={question}
              onAnswer={(answer, label) => thread.send(label, [], message.id, undefined, answer)}
              onCustom={(text) => thread.send(text, [], message.id)}
            />
          ) : undefined
        }
        steps={
          prefs.steps && doneCalls.length ? (
            <Steps
              calls={doneCalls}
              running={false}
              seconds={done ? stepsSeconds(done.run, doneCalls) || done.seconds : 0}
              defaultOpen={prefs.stepsOpen}
            />
          ) : undefined
        }
      />,
    );
    for (const failure of failures.filter(
      (f) => f.message.id === message.id && !retried.has(f.run.id),
    ))
      body.push(
        <div
          key={`failed:${failure.run.id}`}
          className="msg theirs first k-error"
          data-failed-run-id={failure.run.id}
        >
          <div className="msg-line">
            <AgentErrorCard run={failure.run} onRetry={retryRun} onFix={fixFailure} />
          </div>
        </div>,
      );
  });

  const empty = !rows.length && !activeRuns.length;
  const name = conversationName ?? agent?.name ?? "";
  return (
    <ConversationContext.Provider value={api_}>
      <svg
        className="chat-wall"
        style={{ "--wa": WALL_LEVELS.light.a[theme === "light" ? 1 : 0] } as React.CSSProperties}
        aria-hidden="true"
        focusable="false"
      >
        <rect width="100%" height="100%" fill="url(#lw-p-lonora)" />
      </svg>
      {/* biome-ignore lint/a11y/noStaticElementInteractions: a real scroll by the owner shows the floating day */}
      {/* biome-ignore lint/a11y/useAriaPropsSupportedByRole: the scroller is the named conversation */}
      <div
        ref={scroll}
        className="chat-scroll"
        data-testid="transcript"
        aria-label={t`Conversation`}
        onWheel={(event) => {
          userScrollAt.current = Date.now();
          if (event.deltaY < 0) following.current = false;
        }}
        onTouchStart={() => {
          userScrollAt.current = Date.now();
          following.current = false;
        }}
        onKeyDown={() => {
          userScrollAt.current = Date.now();
        }}
        onScroll={(event) => {
          const el = event.currentTarget;
          const near = nearConversationBottom(el.scrollHeight, el.clientHeight, el.scrollTop);
          following.current = near;
          if (near) anchored.current = el.scrollTop;
          const isFar = el.scrollHeight - el.clientHeight - el.scrollTop > 260;
          setFar(isFar);
          if (!isFar) setFresh(0);
          syncFloat();
        }}
      >
        <GenuiHost value={{ threadId, messages: thread.messages, runs, agents }}>
          {empty ? (
            <ChatEmpty agent={agent} members={agents} name={name} group={isGroup} />
          ) : (
            <div ref={content} className="messages" id="messages">
              {canPage && (
                <div
                  ref={sentinel}
                  className="sk-older"
                  role="status"
                  aria-busy="true"
                  aria-label={t`Loading older messages`}
                >
                  {[58, 36, 64].map((width, i) => (
                    <div
                      key={width}
                      className={`sk-bub${i % 2 ? " mine" : ""}`}
                      style={{ width: `${width}%` }}
                    >
                      <span className="sk sk-line" style={{ width: "90%" }} />
                      {i % 3 ? <span className="sk sk-line" style={{ width: "55%" }} /> : null}
                    </div>
                  ))}
                </div>
              )}
              {body.map((node, index) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: nodes carry their own keys
                <Fragment key={index}>{node}</Fragment>
              ))}
            </div>
          )}
        </GenuiHost>
        {error != null && (
          <div className="msg theirs first k-error" data-chat-error="">
            <div className="err-card" role="alert">
              <div className="err-top">
                <span className="err-ic">
                  <Icon name="alert" />
                </span>
                <strong>{userError(error)}</strong>
              </div>
            </div>
          </div>
        )}
      </div>
      <div className={`float-date${floatDay ? " on" : ""}`} aria-hidden="true">
        <span>{floatDay}</span>
      </div>
      <button
        type="button"
        className={`jump${far ? " on" : ""}`}
        aria-label={
          fresh ? t`Go to the latest messages, ${fresh} new` : t`Go to the latest messages`
        }
        onClick={() => {
          following.current = true;
          setFresh(0);
          scroll.current?.scrollTo({
            top: scroll.current.scrollHeight,
            behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth",
          });
        }}
      >
        <Icon name="down" />
        {fresh > 0 && <span className="jump-n">{fresh}</span>}
      </button>
      <Composer
        key={`composer:${threadId}`}
        threadId={threadId}
        ownerId={owner.id}
        agent={agent}
        agents={agents}
        name={name}
        isGroup={isGroup}
        groupLead={groupLead}
        reply={reply}
        editing={editing}
        streaming={streaming || working}
        suggestion={suggestion}
        collaborationSessionId={collaboration?.id}
        onClearReply={() => setReply(null)}
        onClearEdit={() => setEditing(null)}
        onSend={send}
        onStop={() => {
          setActionError(undefined);
          for (const run of activeRuns) setStopped((old) => new Set(old).add(run.id));
          void Promise.all(activeRuns.map((run) => thread.cancel(run.id))).catch(setActionError);
        }}
        onUploaded={(row) => setArtifacts((old) => [...old.filter((a) => a.id !== row.id), row])}
      />
      {preview && <FilePreviewPanel artifact={preview} onClose={() => setPreview(null)} />}
    </ConversationContext.Provider>
  );
}

/** A card's frame: an agent message with no text (the card is the body). */
function cardMessage(
  id: string,
  agentId: string | null,
  at: string,
  threadId: string,
): ConversationMessage {
  return {
    id,
    thread_id: threadId,
    agent_id: agentId,
    seq: 0,
    role: "assistant",
    content: "",
    reply_to: null,
    attachment_ids: [],
    created_at: at,
  };
}

function ChatEmpty({
  agent,
  members,
  name,
  group,
}: {
  agent?: Agent;
  /** In a group, its members. */
  members: Agent[];
  name: string;
  group: boolean;
}) {
  const { owner, ownerProfile } = useShellData();
  const ownerName = ownerDisplayName(ownerProfile, owner);
  return (
    <div className="chat-empty">
      <div className="arcs" aria-hidden="true" />
      {group
        ? members.length > 0 && (
            <span className="group-av">
              <GroupAvatar members={members} />
            </span>
          )
        : agent && <AgentAvatar agent={agent} />}
      <h2>
        <Trans>Hello {ownerName}</Trans>
      </h2>
      <p>
        {group || !agent ? (
          <Trans>Write to the group, or pick a suggestion below.</Trans>
        ) : (
          <Trans>What shall we do today with {name}?</Trans>
        )}
      </p>
    </div>
  );
}

export type { MentionAddress };
