// Adapted from Tampletgrok's Shell Composer; Apache-2.0. Modified for Lonora's real API.
import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { ArrowUp, LoaderCircle, Mic, Paperclip, Plus, Settings, Square, X } from "lucide-react";
import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import type { Agent, Message, Resource } from "../../lib/api";
import { api } from "../../lib/api";
import { userError } from "../../lib/user_error";

export function Composer({
  threadId,
  working,
  reply,
  mentionTargets = [],
  onClearReply,
  onSend,
  onCancel,
  onVoice,
  voiceOpen = false,
}: {
  threadId: string;
  working: boolean;
  reply: Message | null;
  mentionTargets?: Agent[];
  onClearReply: () => void;
  onSend: (text: string, ids: string[], reply: string | null) => Promise<void>;
  onCancel: () => void;
  onVoice?: () => void;
  voiceOpen?: boolean;
}) {
  const [text, setText] = useState("");
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
  const mentionOptions = mentionTargets
    .filter(
      (agent) =>
        !agent.paused &&
        agent.name.toLocaleLowerCase().includes((mentionQuery ?? "").toLocaleLowerCase()),
    )
    .slice(0, 6);
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

  function updateDraft(value: string) {
    draftRevision.current += 1;
    setText(value);
    const mention = /(?:^|\s)@([^\s@]*)$/.exec(value);
    setMentionQuery(mention ? (mention[1] ?? "") : null);
    setHighlight(0);
  }

  function insertMention(agent: Agent) {
    draftRevision.current += 1;
    setText((value) => value.replace(/@[^\s@]*$/, `@${agent.name} `));
    setMentionQuery(null);
    setHighlight(0);
    textarea.current?.focus();
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
      await onSend(text.trim() || t`Attached files`, attachments, sentReply);
      if (!mounted.current) return;
      if (draftRevision.current === revision) {
        setText("");
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
              key={agent.id}
              type="button"
              role="option"
              aria-selected={index === activeMention}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => insertMention(agent)}
              onMouseMove={() => setHighlight(index)}
            >
              <span className="template-mention-dot" style={{ backgroundColor: agent.color }} />
              <span dir="auto">@{agent.name}</span>
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
            placeholder={working ? t`Add direction while the agent works…` : t`Message your agent…`}
            value={text}
            onChange={(event) => updateDraft(event.target.value)}
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
                if (agent) insertMention(agent);
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
          {onVoice && !text.trim() && (
            <button
              type="button"
              className="template-icon-button template-voice-button"
              aria-label={t`Voice`}
              title={t`Voice`}
              aria-expanded={voiceOpen}
              onClick={onVoice}
            >
              <Mic size={16} />
            </button>
          )}
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
