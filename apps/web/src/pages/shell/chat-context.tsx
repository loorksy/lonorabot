// Extracted from Tampletgrok's chat workspace boundaries; Apache-2.0. Uses Lonora's persistent runtime.

import { t } from "@lingui/core/macro";
import { Trans, useLingui } from "@lingui/react/macro";
import type { InputAnswer, SuperBotRequest, TradeApproval } from "@lonora/contracts";
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
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { AgentLiveStatus } from "../../components/ai/AgentLiveStatus";
import { SubagentTasks } from "../../components/ai/CollaborationMarker";
import { AgentActivity, WorkingIndicator } from "../../components/ai/primitives";
import { FilePreviewPanel } from "../../components/common/FilePreviewPanel";
import { ConversationQuestion } from "../../components/conversation-question";
import { ToolActivityDisclosure } from "../../components/ToolActivityDisclosure";
import { SuperBotCard, useSuperBotRequests } from "../../components/trading/SuperBotCards";
import { TradeApprovalCard, useTradeApprovals } from "../../components/trading/TradeApprovals";
import { useThreads } from "../../hooks/useThreads";
import type { Agent, Message, Resource, Run } from "../../lib/api";
import { api } from "../../lib/api";
import { streamForRun } from "../../lib/response_streaming";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";
import { MessageBubble, RecoveryNotice, StreamingMessageCard } from "./message-cards";
import "./chat-context.css";

export function ThreadViewport({
  threadId,
  agentId,
  agents,
  conversationName,
}: {
  conversationName?: string;
  threadId: string;
  agentId: string;
  agents: Agent[];
}) {
  const thread = useThreads(undefined, threadId);
  const approvalState = useTradeApprovals(threadId);
  const superBot = useSuperBotRequests(agentId, { threadId });
  const { events, revision, streams, seedStreams, connected } = useClient();
  const repairingStreams = useRef(new Set<string>());
  const lastRepair = useRef(new Map<string, number>());
  const [reply, setReply] = useState<Message | null>(null);
  const [artifacts, setArtifacts] = useState<Resource[]>([]);
  const [collaboration, setCollaboration] = useState<Resource | null>(null);
  const [peers, setPeers] = useState<Resource[]>([]);
  const [preview, setPreview] = useState<Resource | null>(null);
  const [actionError, setActionError] = useState<unknown>();
  const [artifactError, setArtifactError] = useState<unknown>();
  const [peerError, setPeerError] = useState<unknown>();

  useEffect(() => {
    void threadId;
    setReply(null);
    setPreview(null);
    setActionError(undefined);
    setArtifactError(undefined);
    setPeerError(undefined);
    setArtifacts([]);
    setPeers([]);
  }, [threadId]);

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
  const notices = statusRuns.filter(
    (run) =>
      !isWorking(run.status) &&
      (run.status !== "completed" || run.model_metadata.reply_outcome === "silent"),
  );
  const working = activeRuns.some((run) => isWorking(run.status));
  const messageIds = new Set(thread.messages.map((message) => message.id));
  const streamingRows = thread.runs
    .filter((run) => run.thread_id === threadId)
    .map((run) => ({ run, stream: streamForRun(run, streams[run.id]) }))
    .filter(
      ({ stream }) =>
        stream?.text &&
        stream.phase !== "discarded" &&
        (!stream.message_id || !messageIds.has(stream.message_id)),
    )
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
        messages={thread.messages}
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
        onReply={setReply}
        onPreview={setPreview}
        onOlder={thread.older}
        trailing={
          <>
            {streamingRows.map(
              ({ run, stream }) =>
                stream && (
                  <StreamingMessageCard
                    key={`${run.id}:${stream.turn_id}`}
                    run={run}
                    showSpeaker={!agentId}
                    stream={stream}
                    agent={agents.find((agent) => agent.id === run.agent_id)}
                  />
                ),
            )}
            <div className="thread-progress template-thread-progress">
              <AgentActivity
                events={local}
                runs={thread.runs.filter(
                  (run) => !streamingRows.some((entry) => entry.run.id === run.id),
                )}
                agents={agents}
              />
              <ToolActivityDisclosure events={local} />
              <SubagentTasks runs={thread.runs} />
            </div>
          </>
        }
      />
      <Composer
        key={`composer:${threadId}`}
        threadId={threadId}
        working={working}
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
        onSend={thread.send}
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
  working,
  reply,
  mentionTargets = [],
  mentionAll = false,
  collaborationSessionId,
  recipientName,
  onClearReply,
  onSend,
  onCancel,
}: {
  threadId: string;
  working: boolean;
  reply: Message | null;
  mentionTargets?: Agent[];
  mentionAll?: boolean;
  collaborationSessionId?: string;
  recipientName?: string;
  onClearReply: () => void;
  onSend: (
    text: string,
    ids: string[],
    reply: string | null,
    mentions?: MentionAddress,
  ) => Promise<void>;
  onCancel: () => void;
}) {
  const [text, setText] = useState("");
  const committedMentions = useRef<MentionRange[]>([]);
  const caret = useRef(0);
  const [files, setFiles] = useState<Resource[]>([]);
  const [sending, setSending] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<unknown>();
  const [expanded, setExpanded] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [mentionQuery, setMentionQuery] = useState<string | null>(null);
  const [highlight, setHighlight] = useState(0);
  const fileInput = useRef<HTMLInputElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const bar = useRef<HTMLDivElement>(null);
  const attach = useRef<HTMLButtonElement>(null);
  const actions = useRef<HTMLDivElement>(null);
  const sendingRef = useRef(false);
  const uploadRef = useRef(false);
  const mounted = useRef(true);
  const draftRevision = useRef(0);
  const dragDepth = useRef(0);
  const listboxId = useId();
  const helpId = useId();
  const latestReply = useRef(reply?.id);
  latestReply.current = reply?.id;
  const replyId = reply?.id;
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

  useLayoutEffect(() => {
    const field = textarea.current;
    if (!field) return;
    const resize = () => {
      const height = Math.min(measureTextareaHeight(field), 120);
      if (!text) setExpanded(false);
      else if (height > 36 || text.includes("\n")) setExpanded(true);
      else if (bar.current && attach.current && actions.current) {
        const styles = window.getComputedStyle(bar.current);
        const available =
          bar.current.clientWidth -
          Number.parseFloat(styles.paddingInlineStart) -
          Number.parseFloat(styles.paddingInlineEnd) -
          attach.current.offsetWidth -
          actions.current.offsetWidth -
          2 * Number.parseFloat(styles.columnGap) -
          16;
        // Keep Tampletgrok's collapse slack so one-line/expanded widths cannot oscillate.
        if (measureTextareaHeight(field, Math.max(24, available)) <= 36) setExpanded(false);
      }
      field.style.height = `${Math.max(24, height)}px`;
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
  }, [text]);

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
    setUploading(true);
    setError(undefined);
    try {
      const results = await Promise.allSettled(picked.map((file) => api.upload(file, threadId)));
      if (!mounted.current) return;
      const uploaded = results.flatMap((result) =>
        result.status === "fulfilled" ? [result.value] : [],
      );
      setFiles((old) => [...old, ...uploaded]);
      const failure = results.find((result) => result.status === "rejected");
      if (failure?.status === "rejected") setError(failure.reason);
    } finally {
      uploadRef.current = false;
      if (mounted.current) setUploading(false);
    }
  }

  async function send() {
    if ((!text.trim() && !files.length) || sendingRef.current || uploadRef.current) return;
    sendingRef.current = true;
    setSending(true);
    const revision = draftRevision.current;
    const attachments = files.map((file) => file.id);
    const sentReply = reply?.id ?? null;
    try {
      await onSend(
        text.trim() || t`Attached files`,
        attachments,
        sentReply,
        mentionAddress(text, committedMentions.current),
      );
      if (!mounted.current) return;
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
      className="composer template-composer"
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
            const name = String(file.payload.filename ?? "");
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
        ref={bar}
        className="template-composer-bar"
        data-expanded={expanded}
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
          ref={attach}
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
        <div ref={actions} className="composer-actions template-composer-actions">
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

/** Tampletgrok's textarea measurement, preserving the measured field's inline styles. */
function measureTextareaHeight(field: HTMLTextAreaElement, width?: number) {
  const oldOverflow = field.style.overflowY;
  const oldWidth = field.style.width;
  field.style.overflowY = "hidden";
  if (width !== undefined) field.style.width = `${width}px`;
  field.style.height = "0px";
  const height = field.scrollHeight;
  field.style.overflowY = oldOverflow;
  field.style.width = oldWidth;
  return height;
}

export function ThreadMessages({
  messages,
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
}: {
  onAnswer?: (answer: InputAnswer, label: string, messageId: string) => Promise<void>;
  showSpeakers?: boolean;
  messages: Message[];
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
  const { i18n } = useLingui();
  const scroll = useRef<HTMLElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const following = useRef(true);
  const previous = useRef({ first: "", last: "", height: 0 });
  const [atEnd, setAtEnd] = useState(true);
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
    setAtEnd(nearConversationBottom(element.scrollHeight, element.clientHeight, element.scrollTop));
  }, [messages]);

  useEffect(() => {
    const transcript = content.current;
    if (!transcript) return;
    const observer = new ResizeObserver(() => {
      const element = scroll.current;
      if (!element) return;
      if (following.current) element.scrollTop = element.scrollHeight;
      previous.current.height = element.scrollHeight;
      setAtEnd(
        nearConversationBottom(element.scrollHeight, element.clientHeight, element.scrollTop),
      );
    });
    observer.observe(transcript);
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
          setAtEnd(nearEnd);
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
            const question = questions.get(message.id);
            const previousMessage =
              messages[messages.findIndex((row) => row.id === message.id) - 1];
            const separator = needsTimeSeparator(message.created_at, previousMessage?.created_at);
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
                  peer={peersByMessageId.get(message.id)}
                  peerRun={runsById.get(
                    String(peersByMessageId.get(message.id)?.payload.run_id ?? ""),
                  )}
                />
              </Fragment>
            );
          })}
          {trailing}
        </div>
      </section>
      {!atEnd && (
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
