// Lonora persistent chat. Composer layout adapts OpenUI (MIT, Thesys Inc.; revision9d73d17).
// Existing timeline/runtime boundaries retain their Tampletgrok Apache-2.0 attribution.

import { t } from "@lingui/core/macro";
import { Trans, useLingui } from "@lingui/react/macro";
import type { InputAnswer, SuperBotRequest, TradeApproval, VisualAction } from "@lonora/contracts";
import {
  canCancel,
  conversationTimeline,
  formatTimeSeparator,
  isWorking,
  type MentionAddress,
  type MentionRange,
  mentionAddress,
  mentionCandidates,
  nearConversationBottom,
  needsTimeSeparator,
  mentionQuery as readMentionQuery,
  rebaseMentions,
} from "@lonora/core";
import {
  ArrowDown,
  ArrowUp,
  LoaderCircle,
  Paperclip,
  Plus,
  Settings,
  Square,
  X,
} from "lucide-react";
import {
  Fragment,
  type ReactNode,
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { AgentLiveStatus } from "../../components/ai/AgentLiveStatus";
import { SubagentTasks } from "../../components/ai/CollaborationMarker";
import { WorkingIndicator } from "../../components/ai/primitives";
import { TurnActivity } from "../../components/ai/TurnActivity";
import { FilePreviewPanel } from "../../components/common/FilePreviewPanel";
import { ConversationQuestion } from "../../components/conversation-question";
import { AgentPermissions } from "../../components/permissions/AgentPermissions";
import { SuperBotCard, useSuperBotRequests } from "../../components/trading/SuperBotCards";
import { TradeApprovalCard, useTradeApprovals } from "../../components/trading/TradeApprovals";
import { useThreads } from "../../hooks/useThreads";
import type { Agent, Message, Resource, Run } from "../../lib/api";
import { api } from "../../lib/api";
import { showLatestButton } from "../../lib/chat-scroll";
import {
  appendDraftFiles,
  draftKey,
  finishDraftUpload,
  observeDraftUploads,
  pendingDraftUploads,
  readComposerDraft,
  saveComposerDraft,
  startDraftUpload,
} from "../../lib/composer-drafts";
import { failedReplies } from "../../lib/failed-replies";
import { streamForRun } from "../../lib/response_streaming";
import { activityTimeline, type StreamRow, streamVisible } from "../../lib/stream-timeline";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";
import {
  FailedReplyNotice,
  MessageBubble,
  RecoveryNotice,
  StreamingMessageCard,
} from "./message-cards";
import "./chat-context.css";

export function ThreadViewport({
  threadId,
  agentId,
  agents,
  conversationName,
  onOpenChart,
  knownRuns,
}: {
  conversationName?: string;
  onOpenChart?: (id: string) => void;
  threadId: string;
  agentId: string;
  agents: Agent[];
  knownRuns?: Run[];
}) {
  const agent = agents.find((item) => item.id === agentId);
  const thread = useThreads(undefined, threadId, knownRuns);
  const approvalState = useTradeApprovals(threadId);
  const superBot = useSuperBotRequests(agentId, { threadId });
  const { owner, events, revision, streams, seedStreams, connected } = useClient();
  const repairingStreams = useRef(new Set<string>());
  const lastRepair = useRef(new Map<string, number>());
  const [reply, setReply] = useState<Message | null>(
    () => readComposerDraft(draftKey(owner.id, threadId)).reply,
  );
  const [artifacts, setArtifacts] = useState<Resource[]>([]);
  const [collaboration, setCollaboration] = useState<Resource | null>(null);
  const [peers, setPeers] = useState<Resource[]>([]);
  const [preview, setPreview] = useState<Resource | null>(null);
  const [actionError, setActionError] = useState<unknown>();
  const [artifactError, setArtifactError] = useState<unknown>();
  const [peerError, setPeerError] = useState<unknown>();

  useEffect(() => {
    void threadId;
    setReply(readComposerDraft(draftKey(owner.id, threadId)).reply);
    setPreview(null);
    setActionError(undefined);
    setArtifactError(undefined);
    setPeerError(undefined);
    setArtifacts([]);
    setPeers([]);
  }, [threadId, owner.id]);

  useEffect(() => {
    void revision;
    let live = true;
    void api
      .get<Resource[]>(`/artifacts?thread_id=${threadId}`)
      .then((rows) => {
        if (live) {
          setArtifacts(rows);
          setArtifactError(undefined);
        }
      })
      .catch((error: unknown) => {
        if (live) setArtifactError(error);
      });
    return () => {
      live = false;
    };
  }, [threadId, revision]);

  useEffect(() => {
    void revision;
    let live = true;
    void api
      .get<Resource[]>(`/peer-messages?thread_id=${threadId}`)
      .then((rows) => {
        if (live) {
          setPeers(rows);
          setPeerError(undefined);
        }
      })
      .catch((error: unknown) => {
        if (live) setPeerError(error);
      });
    return () => {
      live = false;
    };
  }, [threadId, revision]);

  useEffect(() => {
    void revision;
    let live = true;
    void api
      .get<Resource | null>(`/threads/${threadId}/collaboration`)
      .then((row) => {
        if (live) setCollaboration(row);
      })
      .catch(() => {
        if (live) setCollaboration(null);
      });
    return () => {
      live = false;
    };
  }, [threadId, revision]);

  useEffect(() => {
    seedStreams(thread.runs);
  }, [thread.runs, seedStreams]);

  useEffect(() => {
    void connected;
    for (const stream of Object.values(streams)) {
      if (
        !stream.gap ||
        stream.thread_id !== threadId ||
        repairingStreams.current.has(stream.run_id) ||
        Date.now() - (lastRepair.current.get(stream.run_id) ?? 0) < 500
      )
        continue;
      const id = stream.run_id;
      repairingStreams.current.add(id);
      lastRepair.current.set(id, Date.now());
      void api
        .get<Run>(`/runs/${id}`)
        .then((run) => seedStreams([run]))
        .catch(() => undefined)
        .finally(() => repairingStreams.current.delete(id));
    }
  }, [streams, threadId, seedStreams, connected]);

  const local = events.filter((event) => event.thread_id === threadId);
  const activeRuns = thread.runs.filter(
    (run) => run.thread_id === threadId && canCancel(run.status),
  );
  const active = activeRuns[0];
  const latestByAgent = new Map<string, Run>();
  for (const run of thread.runs) {
    if (run.thread_id !== threadId) continue;
    const previous = latestByAgent.get(run.agent_id);
    if (!previous || run.created_at > previous.created_at) latestByAgent.set(run.agent_id, run);
  }
  const statusRuns = agentId
    ? activeRuns.length
      ? activeRuns
      : [...latestByAgent.values()].filter((run) => run.agent_id === agentId)
    : [...latestByAgent.values()];
  const inlineFailures = new Set(
    failedReplies(thread.runs, thread.messages).map(({ run }) => run.id),
  );
  const notices = statusRuns.filter(
    (run) =>
      !inlineFailures.has(run.id) &&
      !isWorking(run.status) &&
      (run.status !== "completed" || run.model_metadata.reply_outcome === "silent"),
  );
  const working = activeRuns.some((run) => isWorking(run.status));
  const streamingRows = thread.runs
    .filter((run) => run.thread_id === threadId)
    .map((run) => ({ run, stream: streamForRun(run, streams[run.id]) }))
    .filter(({ run, stream }) => streamVisible(run, stream, thread.messages))
    .sort((a, b) => a.run.created_at.localeCompare(b.run.created_at));

  async function changeRun(action: "resume" | "cancel", id?: string) {
    if (!activeRuns.length) return;
    setActionError(undefined);
    try {
      if (action === "resume") await thread.resume(id ?? active.id);
      else await Promise.all((id ? [id] : activeRuns.map((run) => run.id)).map(thread.cancel));
    } catch (caught) {
      setActionError(caught);
    }
  }

  return (
    <section className="thread-view template-thread">
      {agentId && <AgentLiveStatus agentId={agentId} />}
      {notices.length > 0 && (
        <div className="thread-status template-thread-status">
          {notices.map(
            (run) =>
              run && (
                <div className="template-run-status" key={run.id} data-run-status-id={run.id}>
                  {!agentId && (
                    <span dir="auto">
                      {agents.find((agent) => agent.id === run.agent_id)?.name ?? (
                        <Trans>Agent</Trans>
                      )}
                    </span>
                  )}
                  <WorkingIndicator run={run} />
                  {run.status === "waiting_takeover" && (
                    <button type="button" onClick={() => void changeRun("resume", run.id)}>
                      <Trans>Resume</Trans>
                    </button>
                  )}
                </div>
              ),
          )}
        </div>
      )}
      <RecoveryNotice events={local} />
      {(thread.error ??
        actionError ??
        artifactError ??
        peerError ??
        approvalState.error ??
        superBot.error) != null && (
        <p className="template-thread-error" role="alert">
          {userError(
            thread.error ??
              actionError ??
              artifactError ??
              peerError ??
              approvalState.error ??
              superBot.error,
          )}
        </p>
      )}
      <ThreadMessages
        key={`messages:${threadId}`}
        ownerId={owner.id}
        onVisualAction={async (action) => {
          if (action.kind === "follow_up") {
            await thread.send(action.text);
          } else if (action.kind === "open_artifact") {
            const artifact = await api.get<Resource>(`/artifacts/${action.resource_id}`);
            setPreview(artifact);
          } else if (onOpenChart) {
            await api.get<Resource>(`/charts/${action.resource_id}`);
            onOpenChart(action.resource_id);
          } else {
            throw new Error("visual_action_unavailable");
          }
        }}
        messages={thread.messages}
        streaming={streamingRows.flatMap(({ run, stream }) => (stream ? [{ run, stream }] : []))}
        onAnswer={(answer, label, messageId) =>
          thread.send(label, [], messageId, undefined, answer)
        }
        approvals={approvalState.rows}
        superBotRequests={superBot.rows}
        renderSuperBot={(row) => <SuperBotCard row={row} onChanged={superBot.update} />}
        renderApproval={(row) => (
          <TradeApprovalCard
            row={row}
            busy={approvalState.busy != null}
            decide={approvalState.decide}
          />
        )}
        showSpeakers={!agentId}
        agents={agents}
        artifacts={artifacts}
        peers={peers}
        runs={thread.runs}
        previousVisualMessageIds={
          new Map(
            thread.runs.flatMap((run) => {
              const stream = streamForRun(run, streams[run.id]);
              return stream?.message_id ? [[stream.message_id, `preview:${run.id}`] as const] : [];
            }),
          )
        }
        events={local}
        connected={connected}
        onReply={setReply}
        onPreview={setPreview}
        onOlder={thread.older}
        onRetrySend={thread.retry}
        trailing={
          <div className="thread-progress template-thread-progress">
            <SubagentTasks runs={thread.runs} />
          </div>
        }
      />
      <Composer
        key={`composer:${threadId}`}
        threadId={threadId}
        ownerId={owner.id}
        working={working}
        permissions={
          agent ? (
            <AgentPermissions
              key={`${owner.id}:${agentId}`}
              agent={agent}
              threadId={threadId}
              surface="composer"
            />
          ) : undefined
        }
        reply={reply}
        recipientName={conversationName ?? agents.find((agent) => agent.id === agentId)?.name}
        mentionTargets={agents}
        collaborationSessionId={collaboration?.id}
        mentionAll={Boolean(
          collaboration &&
            !["completed", "cancelled", "expired", "failed"].includes(
              String(collaboration.state?.status),
            ),
        )}
        onClearReply={() => setReply(null)}
        onSend={thread.queue}
        onCancel={() => {
          void changeRun("cancel");
        }}
      />
      {preview && <FilePreviewPanel artifact={preview} onClose={() => setPreview(null)} />}
    </section>
  );
}

export function Composer({
  threadId,
  ownerId = "",
  working,
  reply,
  mentionTargets = [],
  mentionAll = false,
  collaborationSessionId,
  recipientName,
  permissions,
  onClearReply,
  onSend,
  onCancel,
}: {
  threadId: string;
  ownerId?: string;
  working: boolean;
  reply: Message | null;
  mentionTargets?: Agent[];
  mentionAll?: boolean;
  collaborationSessionId?: string;
  recipientName?: string;
  permissions?: ReactNode;
  onClearReply: () => void;
  onSend: (text: string, ids: string[], reply: string | null, mentions?: MentionAddress) => void;
  onCancel: () => void;
}) {
  const storageKey = draftKey(ownerId, threadId);
  const initial = useRef(readComposerDraft(storageKey));
  const [text, setText] = useState(initial.current.text);
  const committedMentions = useRef<MentionRange[]>(initial.current.mentions);
  const caret = useRef(0);
  const [files, setFiles] = useState<Resource[]>(initial.current.files);
  const [sending, setSending] = useState(false);
  const [uploading, setUploading] = useState(() => pendingDraftUploads(storageKey) > 0);
  const [error, setError] = useState<unknown>();
  const [inputOverflow, setInputOverflow] = useState({ top: false, bottom: false });
  const [dragging, setDragging] = useState(false);
  const [mentionQuery, setMentionQuery] = useState<string | null>(null);
  const [highlight, setHighlight] = useState(0);
  const fileInput = useRef<HTMLInputElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const composer = useRef<HTMLFormElement>(null);
  const sendingRef = useRef(false);
  const uploadRef = useRef(pendingDraftUploads(storageKey) > 0);
  const mounted = useRef(true);
  const draftRevision = useRef(0);
  const dragDepth = useRef(0);
  const listboxId = useId();
  const helpId = useId();
  const latestReply = useRef(reply?.id);
  latestReply.current = reply?.id;
  const replyId = reply?.id;
  const currentDraft = useRef({ text, files, mentions: committedMentions.current, reply });
  currentDraft.current = { text, files, mentions: committedMentions.current, reply };
  useEffect(() => {
    saveComposerDraft(storageKey, { text, files, mentions: committedMentions.current, reply });
  }, [storageKey, text, files, reply]);
  useEffect(() => () => saveComposerDraft(storageKey, currentDraft.current), [storageKey]);
  useEffect(
    () =>
      observeDraftUploads(storageKey, () => {
        const pending = pendingDraftUploads(storageKey) > 0;
        uploadRef.current = pending;
        setUploading(pending);
        setFiles(readComposerDraft(storageKey).files);
      }),
    [storageKey],
  );
  const canSend = Boolean(text.trim() || files.length);
  const mentionOptions: Array<Agent | null> = mentionCandidates(
    mentionTargets,
    mentionQuery ?? "",
  ).slice(0, 6);
  if (mentionAll && "all".startsWith((mentionQuery ?? "").toLowerCase())) mentionOptions.push(null);
  const mentionOpen = mentionQuery !== null && mentionOptions.length > 0;
  const activeMention = Math.min(highlight, Math.max(0, mentionOptions.length - 1));
  const settingsCommand = /^\/(?:settings)?$/i.test(text.trim());

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (replyId) textarea.current?.focus();
  }, [replyId]);

  const updateInputOverflow = useCallback(() => {
    const field = textarea.current;
    if (!field) return;
    const maximum = field.scrollHeight - field.clientHeight;
    const next = {
      top: maximum > 1 && field.scrollTop > 1,
      bottom: maximum > 1 && field.scrollTop < maximum - 1,
    };
    setInputOverflow((current) =>
      current.top === next.top && current.bottom === next.bottom ? current : next,
    );
  }, []);

  useLayoutEffect(() => {
    const field = textarea.current;
    if (!field) return;
    const resize = () => {
      // A long recipient name in the placeholder must not expand an empty
      // composer (especially on narrow RTL screens).
      field.style.height = `${text ? Math.max(32, Math.min(measureTextareaHeight(field), 200)) : 32}px`;
      if (!text) field.scrollTop = 0;
      updateInputOverflow();
    };
    resize();
    let lastWidth = field.getBoundingClientRect().width;
    const observer = new ResizeObserver(() => {
      const width = field.getBoundingClientRect().width;
      if (width === lastWidth) return;
      lastWidth = width;
      resize();
    });
    observer.observe(field);
    return () => observer.disconnect();
  }, [text, updateInputOverflow]);

  // OpenUI keeps the transcript behind a floating composer. Publish the actual
  // slot height so attachments, reply previews and multiline drafts never cover
  // the latest answer; no fixed height or delayed layout animation is needed.
  useLayoutEffect(() => {
    const slot = composer.current;
    const thread = slot?.closest<HTMLElement>(".template-thread");
    if (!slot || !thread) return;
    const measure = () =>
      thread.style.setProperty("--chat-composer-height", `${slot.offsetHeight}px`);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(slot);
    return () => {
      observer.disconnect();
      thread.style.removeProperty("--chat-composer-height");
    };
  }, []);

  useEffect(() => {
    if (window.matchMedia("(min-width: 768px)").matches)
      textarea.current?.focus({ preventScroll: true });
  }, []);

  function updateDraft(value: string, position = value.length) {
    committedMentions.current = rebaseMentions(text, value, committedMentions.current);
    caret.current = position;
    draftRevision.current += 1;
    setText(value);
    setMentionQuery(readMentionQuery(value.slice(0, position)));
    setHighlight(0);
  }

  function insertMention(agent: Agent | null) {
    draftRevision.current += 1;
    const before = text.slice(0, caret.current);
    const start = before.lastIndexOf("@");
    if (start < 0) return;
    const token = `@${agent?.name ?? "all"}`;
    const next = `${text.slice(0, start)}${token} ${text.slice(caret.current)}`;
    committedMentions.current = [
      ...rebaseMentions(text, next, committedMentions.current),
      {
        agent_id: agent?.id ?? null,
        session_id: agent ? undefined : collaborationSessionId,
        token,
        start,
        end: start + token.length,
      },
    ];
    caret.current = start + token.length + 1;
    setText(next);
    setMentionQuery(null);
    setHighlight(0);
    textarea.current?.focus();
    requestAnimationFrame(() => textarea.current?.setSelectionRange(caret.current, caret.current));
  }

  async function upload(picked: File[]) {
    if (!picked.length || uploadRef.current) return;
    uploadRef.current = true;
    startDraftUpload(storageKey);
    setUploading(true);
    setError(undefined);
    try {
      const results = await Promise.allSettled(picked.map((file) => api.upload(file, threadId)));
      const uploaded = results.flatMap((result) =>
        result.status === "fulfilled" ? [result.value] : [],
      );
      appendDraftFiles(storageKey, uploaded);
      const failure = results.find((result) => result.status === "rejected");
      if (mounted.current && failure?.status === "rejected") setError(failure.reason);
    } finally {
      uploadRef.current = false;
      finishDraftUpload(storageKey);
      if (mounted.current) setUploading(false);
    }
  }

  function send() {
    if ((!text.trim() && !files.length) || sendingRef.current || uploadRef.current) return;
    sendingRef.current = true;
    setSending(true);
    const revision = draftRevision.current;
    const attachments = files.map((file) => file.id);
    const sentReply = reply?.id ?? null;
    try {
      onSend(
        text.trim() || t`Attached files`,
        attachments,
        sentReply,
        mentionAddress(text, committedMentions.current),
      );
      if (!mounted.current) return;
      currentDraft.current = {
        text: "",
        files: files.filter((file) => !attachments.includes(file.id)),
        mentions: [],
        reply: null,
      };
      saveComposerDraft(storageKey, currentDraft.current);
      if (draftRevision.current === revision) {
        setText("");
        committedMentions.current = [];
        setMentionQuery(null);
      }
      setFiles((old) => old.filter((file) => !attachments.includes(file.id)));
      if ((latestReply.current ?? null) === sentReply) onClearReply();
      setError(undefined);
    } catch (caught) {
      if (mounted.current) setError(caught);
    } finally {
      sendingRef.current = false;
      if (mounted.current) setSending(false);
    }
  }

  function openSettings() {
    updateDraft("");
    window.dispatchEvent(new CustomEvent("lonora:open-settings"));
  }

  return (
    <form
      ref={composer}
      className="composer template-composer"
      data-drafting={Boolean(text)}
      aria-label={t`Message composer`}
      data-dragging={dragging ? "files" : undefined}
      onSubmit={(event) => {
        event.preventDefault();
        void send();
      }}
      onDragEnter={(event) => {
        if (!event.dataTransfer.types.includes("Files")) return;
        event.preventDefault();
        dragDepth.current += 1;
        setDragging(true);
      }}
      onDragOver={(event) => {
        if (event.dataTransfer.types.includes("Files")) event.preventDefault();
      }}
      onDragLeave={(event) => {
        event.preventDefault();
        dragDepth.current = Math.max(0, dragDepth.current - 1);
        if (!dragDepth.current) setDragging(false);
      }}
      onDrop={(event) => {
        if (!event.dataTransfer.files.length) return;
        event.preventDefault();
        dragDepth.current = 0;
        setDragging(false);
        void upload(Array.from(event.dataTransfer.files));
      }}
    >
      {error != null && (
        <div className="template-composer-error" role="alert">
          <span>{userError(error)}</span>
          <button
            type="button"
            className="template-icon-button"
            aria-label={t`Dismiss error`}
            onClick={() => setError(undefined)}
          >
            <X size={14} />
          </button>
        </div>
      )}
      {reply && (
        <div className="reply-preview template-reply-preview" role="status">
          <div>
            <small>
              <Trans>Reply to an earlier message</Trans>
            </small>
            <span dir="auto">{reply.content.slice(0, 140)}</span>
          </div>
          <button
            type="button"
            className="template-icon-button"
            onClick={() => {
              onClearReply();
              textarea.current?.focus();
            }}
            aria-label={t`Remove reply`}
          >
            <X size={14} />
          </button>
        </div>
      )}
      {files.length > 0 && (
        <div className="template-attachment-chips">
          {files.map((file) => {
            const name = String(file.payload.name ?? file.payload.filename ?? "");
            return (
              <div className="template-attachment-chip" key={file.id}>
                <Paperclip size={13} />
                <bdi>{name}</bdi>
                <button
                  type="button"
                  className="template-icon-button"
                  aria-label={t`Remove ${name}`}
                  onClick={() => setFiles((old) => old.filter((item) => item.id !== file.id))}
                >
                  <X size={12} />
                </button>
              </div>
            );
          })}
        </div>
      )}
      {mentionOpen && (
        <div
          id={listboxId}
          role="listbox"
          aria-label={t`Mentions`}
          className="template-composer-menu"
        >
          {mentionOptions.map((agent, index) => (
            <button
              id={`${listboxId}-${index}`}
              key={agent?.id ?? "session-all"}
              type="button"
              role="option"
              aria-selected={index === activeMention}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => insertMention(agent)}
              onMouseMove={() => setHighlight(index)}
            >
              <span className="template-mention-dot" style={{ backgroundColor: agent?.color }} />
              <bdi>@{agent?.name ?? "all"}</bdi>
              {agent?.trading_symbol && <bdi>{agent.trading_symbol}</bdi>}
            </button>
          ))}
        </div>
      )}
      {settingsCommand && !mentionOpen && (
        <div className="template-composer-menu">
          <button type="button" onClick={openSettings}>
            <Settings size={15} />
            <Trans>Settings</Trans>
          </button>
        </div>
      )}
      <div
        className="template-composer-bar"
        data-overflow-top={inputOverflow.top || undefined}
        data-overflow-bottom={inputOverflow.bottom || undefined}
        data-testid="composer-bar"
      >
        <input
          hidden
          ref={fileInput}
          type="file"
          multiple
          onChange={(event) => {
            const picked = Array.from(event.target.files ?? []);
            event.target.value = "";
            void upload(picked);
          }}
        />
        <button
          type="button"
          className="template-icon-button template-attach-button"
          disabled={uploading}
          onClick={() => fileInput.current?.click()}
          aria-label={t`Attach file`}
          title={t`Attach file`}
        >
          {uploading ? (
            <LoaderCircle size={16} className="template-spinning" />
          ) : (
            <Plus size={18} />
          )}
        </button>
        {permissions}
        <div className="template-composer-field">
          <textarea
            ref={textarea}
            aria-label={t`Message`}
            aria-describedby={helpId}
            role="combobox"
            aria-autocomplete="list"
            aria-haspopup="listbox"
            aria-expanded={mentionOpen}
            aria-controls={mentionOpen ? listboxId : undefined}
            aria-activedescendant={mentionOpen ? `${listboxId}-${activeMention}` : undefined}
            placeholder={
              working
                ? t`Add direction while the agent works…`
                : recipientName
                  ? t`Message ${recipientName}`
                  : t`Message your agent…`
            }
            value={text}
            onChange={(event) => updateDraft(event.target.value, event.target.selectionStart)}
            onScroll={updateInputOverflow}
            onSelect={(event) => {
              caret.current = event.currentTarget.selectionStart;
              setMentionQuery(readMentionQuery(text.slice(0, caret.current)));
            }}
            rows={1}
            dir="auto"
            name="chat-message"
            autoComplete="off"
            onPaste={(event) => {
              const picked = Array.from(event.clipboardData.files);
              if (!picked.length) return;
              event.preventDefault();
              void upload(picked);
            }}
            onKeyDown={(event) => {
              if (event.nativeEvent.isComposing || event.keyCode === 229) return;
              if (mentionOpen && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
                event.preventDefault();
                const delta = event.key === "ArrowDown" ? 1 : -1;
                setHighlight(
                  (activeMention + delta + mentionOptions.length) % mentionOptions.length,
                );
              } else if (
                mentionOpen &&
                (event.key === "Enter" || event.key === "Tab") &&
                !event.shiftKey
              ) {
                event.preventDefault();
                const agent = mentionOptions[activeMention];
                if (agent !== undefined) insertMention(agent);
              } else if (mentionOpen && event.key === "Escape") {
                event.preventDefault();
                event.stopPropagation();
                setMentionQuery(null);
              } else if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                if (text.trim().toLocaleLowerCase() === "/settings") openSettings();
                else void send();
              }
            }}
          />
        </div>
        <div className="composer-actions template-composer-actions">
          {(!working || canSend) && (
            <button
              type="submit"
              className="template-icon-button template-send-button"
              aria-label={working ? t`Send direction` : t`Send`}
              title={working ? t`Send direction` : t`Send`}
              disabled={sending || uploading || !canSend}
            >
              {sending ? (
                <LoaderCircle size={16} className="template-spinning" />
              ) : (
                <ArrowUp size={17} strokeWidth={2.2} />
              )}
            </button>
          )}
          {working && (
            <button
              type="button"
              className="template-icon-button template-stop-button"
              onClick={onCancel}
              aria-label={t`Stop`}
              title={t`Stop`}
            >
              <Square size={11} fill="currentColor" />
            </button>
          )}
        </div>
      </div>
      <span id={helpId} className="template-sr-only">
        <Trans>Enter to send · Shift+Enter for a new line</Trans>
      </span>
    </form>
  );
}

/** Reset before measuring so a shortened draft contracts without a second frame. */
function measureTextareaHeight(field: HTMLTextAreaElement) {
  const oldOverflow = field.style.overflowY;
  field.style.overflowY = "hidden";
  field.style.height = "0px";
  const height = field.scrollHeight;
  field.style.overflowY = oldOverflow;
  return height;
}

export function ThreadMessages({
  messages: canonicalMessages,
  ownerId = "",
  onVisualAction,
  streaming = [],
  agents,
  artifacts,
  peers = [],
  runs = [],
  onReply,
  onPreview,
  onOlder,
  trailing,
  showSpeakers = true,
  approvals = [],
  renderApproval,
  superBotRequests = [],
  renderSuperBot,
  onAnswer,
  onRetrySend,
  events = [],
  connected = true,
  previousVisualMessageIds,
}: {
  previousVisualMessageIds?: Map<string, string>;
  events?: import("../../lib/api").Event[];
  connected?: boolean;
  ownerId?: string;
  onVisualAction?: (action: VisualAction) => Promise<void>;
  onAnswer?: (answer: InputAnswer, label: string, messageId: string) => Promise<void>;
  onRetrySend?: (nonce: string) => Promise<void>;
  showSpeakers?: boolean;
  messages: Message[];
  streaming?: StreamRow[];
  approvals?: TradeApproval[];
  superBotRequests?: SuperBotRequest[];
  renderSuperBot?: (row: SuperBotRequest) => ReactNode;
  renderApproval?: (row: TradeApproval) => ReactNode;
  agents: Agent[];
  artifacts: Resource[];
  peers?: Resource[];
  runs?: Run[];
  onReply: (message: Message) => void;
  onPreview: (artifact: Resource) => void;
  onOlder: () => Promise<void>;
  trailing?: ReactNode;
}) {
  const messages = activityTimeline(canonicalMessages, runs, streaming);
  const failures = failedReplies(runs, canonicalMessages);
  const previews = new Map(streaming.map((row) => [`preview:${row.run.id}`, row]));
  const { i18n } = useLingui();
  const scroll = useRef<HTMLElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const following = useRef(true);
  const previous = useRef({ first: "", last: "", height: 0 });
  const [showLatest, setShowLatest] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [olderError, setOlderError] = useState<unknown>();
  const byId = new Map(messages.map((message) => [message.id, message]));
  const questions = new Map(
    runs.flatMap((run) => run.input_requests ?? []).map((request) => [request.message_id, request]),
  );
  const runsById = new Map(runs.map((run) => [run.id, run]));
  const peersByMessageId = new Map<string, Resource>();
  for (const peer of peers) {
    const payload = peer.payload;
    for (const id of [
      payload.source_message_id,
      payload.target_message_id,
      payload.source_outcome_message_id,
      payload.target_outcome_message_id,
      ...(Array.isArray(payload.source_outcome_message_ids)
        ? payload.source_outcome_message_ids
        : []),
    ]) {
      if (typeof id === "string") peersByMessageId.set(id, peer);
    }
  }

  useLayoutEffect(() => {
    const element = scroll.current;
    if (!element) return;
    const first = messages[0]?.id ?? "";
    const last = messages.at(-1)?.id ?? "";
    const old = previous.current;
    if (old.first && first !== old.first && last === old.last) {
      element.scrollTop += element.scrollHeight - old.height;
    } else if (following.current) {
      element.scrollTop = element.scrollHeight;
    }
    previous.current = { first, last, height: element.scrollHeight };
    setShowLatest((visible) =>
      showLatestButton(visible, element.scrollHeight - element.clientHeight - element.scrollTop),
    );
  }, [messages]);

  useEffect(() => {
    const transcript = content.current;
    if (!transcript) return;
    const observer = new ResizeObserver(() => {
      const element = scroll.current;
      if (!element) return;
      if (following.current) element.scrollTop = element.scrollHeight;
      previous.current.height = element.scrollHeight;
      setShowLatest((visible) =>
        showLatestButton(visible, element.scrollHeight - element.clientHeight - element.scrollTop),
      );
    });
    observer.observe(transcript);
    // The floating composer changes the viewport's bottom padding. Observe the
    // viewport as well as the content so a growing draft keeps the latest reply
    // visible without disturbing an owner who deliberately scrolled upwards.
    if (scroll.current) observer.observe(scroll.current);
    return () => observer.disconnect();
  }, []);

  async function loadOlder() {
    if (loadingOlder) return;
    setLoadingOlder(true);
    setOlderError(undefined);
    following.current = false;
    try {
      await onOlder();
    } catch (caught) {
      setOlderError(caught);
    } finally {
      setLoadingOlder(false);
    }
  }

  return (
    <div className="template-transcript-region">
      <section
        ref={scroll}
        className="thread-messages template-transcript"
        data-testid="transcript"
        aria-label={t`Conversation`}
        onWheel={(event) => {
          if (event.deltaY < 0) following.current = false;
        }}
        onTouchStart={() => {
          following.current = false;
        }}
        onScroll={(event) => {
          const element = event.currentTarget;
          const nearEnd = nearConversationBottom(
            element.scrollHeight,
            element.clientHeight,
            element.scrollTop,
          );
          following.current = nearEnd;
          setShowLatest((visible) =>
            showLatestButton(
              visible,
              element.scrollHeight - element.clientHeight - element.scrollTop,
            ),
          );
        }}
      >
        <div ref={content} className="template-transcript-content">
          {messages.length >= 100 && (
            <button
              type="button"
              className="template-load-older"
              disabled={loadingOlder}
              onClick={() => void loadOlder()}
            >
              {loadingOlder ? (
                <>
                  <LoaderCircle size={14} className="template-spinning" />
                  <Trans>Loading…</Trans>
                </>
              ) : (
                <Trans>Load earlier messages</Trans>
              )}
            </button>
          )}
          {olderError != null && <p role="alert">{userError(olderError)}</p>}
          {conversationTimeline(messages, approvals, superBotRequests).map((item) => {
            if (item.kind === "super_bot")
              return <Fragment key={item.id}>{renderSuperBot?.(item.request)}</Fragment>;
            if (item.kind === "approval")
              return <Fragment key={item.id}>{renderApproval?.(item.approval)}</Fragment>;
            const message = item.message;
            if (message.id.startsWith("activity:")) {
              const run = runsById.get(message.id.slice("activity:".length));
              return run ? (
                <TurnActivity
                  key={message.id}
                  run={run}
                  events={events}
                  connected={connected}
                  agent={agents.find((agent) => agent.id === run.agent_id)}
                />
              ) : null;
            }
            const preview = previews.get(message.id);
            if (preview)
              return (
                <StreamingMessageCard
                  key={message.id}
                  run={preview.run}
                  stream={preview.stream}
                  events={events}
                  connected={connected}
                  ownerId={ownerId}
                  artifacts={artifacts}
                  onVisualAction={onVisualAction}
                  agent={agents.find((agent) => agent.id === preview.run.agent_id)}
                  showSpeaker={showSpeakers}
                />
              );
            const question = questions.get(message.id);
            const previousMessage =
              messages[messages.findIndex((row) => row.id === message.id) - 1];
            const separator =
              !message.id.startsWith("pending:") &&
              needsTimeSeparator(message.created_at, previousMessage?.created_at);
            return (
              <Fragment key={message.id}>
                {separator && (
                  <div className="template-time-separator">
                    <time dateTime={message.created_at}>
                      {formatTimeSeparator(message.created_at, i18n.locale, {
                        today: t`Today`,
                        yesterday: t`Yesterday`,
                      })}
                    </time>
                  </div>
                )}
                <MessageBubble
                  message={message}
                  previousVisualMessageId={previousVisualMessageIds?.get(message.id)}
                  ownerId={ownerId}
                  onVisualAction={onVisualAction}
                  body={
                    onAnswer && question?.choices.length ? (
                      <ConversationQuestion request={question} onAnswer={onAnswer} />
                    ) : undefined
                  }
                  showSpeaker={showSpeakers}
                  agent={agents.find((agent) => agent.id === message.agent_id)}
                  artifacts={artifacts}
                  replyParent={message.reply_to ? byId.get(message.reply_to) : undefined}
                  onReply={onReply}
                  onPreview={onPreview}
                  onRetrySend={onRetrySend}
                  peer={peersByMessageId.get(message.id)}
                  peerRun={runsById.get(
                    String(peersByMessageId.get(message.id)?.payload.run_id ?? ""),
                  )}
                />
                {failures
                  .filter((failure) => failure.message.id === message.id)
                  .map(({ run }) => (
                    <FailedReplyNotice
                      key={run.id}
                      run={run}
                      agent={agents.find((agent) => agent.id === run.agent_id)}
                      showSpeaker={showSpeakers}
                    />
                  ))}
              </Fragment>
            );
          })}
          {trailing}
        </div>
      </section>
      {showLatest && (
        <button
          type="button"
          className="template-icon-button template-jump-latest"
          aria-label={t`Jump to latest`}
          onClick={() => {
            following.current = true;
            scroll.current?.scrollTo({
              top: scroll.current.scrollHeight,
              behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
                ? "instant"
                : "smooth",
            });
          }}
        >
          <ArrowDown size={17} />
        </button>
      )}
    </div>
  );
}
