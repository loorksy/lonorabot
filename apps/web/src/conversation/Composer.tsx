import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { PermissionState } from "@lonora/contracts";
import {
  type MentionAddress,
  type MentionRange,
  mentionAddress,
  mentionCandidates,
  mentionQuery as readMentionQuery,
  rebaseMentions,
  showsTradingControl,
} from "@lonora/core";
import { ICON_PATHS, Icon, type IconName } from "@lonora/ui-web";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { AgentAvatar } from "../components/ai/AgentAvatar";
import type { Agent, Message, Resource } from "../lib/api";
import { api } from "../lib/api";
import {
  appendDraftFiles,
  draftKey,
  finishDraftUpload,
  observeDraftUploads,
  pendingDraftUploads,
  readComposerDraft,
  saveComposerDraft,
  startDraftUpload,
} from "../lib/composer-drafts";
import { userError } from "../lib/user_error";
import { useClient } from "../providers/ClientProvider";
import { usePermissionSheet } from "../shell/PermissionSheet";
import { useToast } from "../shell/Toast";
import { speakerColor } from "./context";
import { snippet } from "./Message";
import { PermissionChip } from "./PermissionMenu";
import { useChatPrefs } from "./prefs";
import { useToolsSheet } from "./ToolsSheet";
import { useThreadOptions } from "./threadOptions";
import { VOICE, voiceFmt, voicePeaks } from "./Voice";

/* The composer (reference composer(), Desktop-37 3828-3870, 404-435): a floating glass card,
   text on top; below: + · the permission chip · the web chip · mic (tap: dictation; hold:
   voice note) · voice call ⇄ send · stop. Enter sends on fine pointers (pref), else
   Ctrl/⌘+Enter; drafts per thread; a reply or edit bar above the text. */

export type ComposerSend = (
  text: string,
  attachments: string[],
  reply: string | null,
  mentions?: MentionAddress,
  extra?: {
    edited_from?: string;
    voice?: { artifact_id: string; duration: number; peaks: number[] };
  },
) => void;

/** The recorder's floating knob and lock live on <body>; they draw the reference's icons. */
const svg = (name: IconName) =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${ICON_PATHS[name]}"/></svg>`;
const fine = () => matchMedia("(pointer: fine)").matches;
const ATTACH = { items: 6, bytes: 8 * 1024 * 1024 };

export function Composer({
  threadId,
  ownerId,
  agent,
  agents,
  name,
  isGroup,
  groupLead,
  reply,
  editing,
  streaming,
  suggestion,
  collaborationSessionId,
  onClearReply,
  onClearEdit,
  onSend,
  onStop,
  onUploaded,
}: {
  threadId: string;
  ownerId: string;
  agent?: Agent;
  agents: Agent[];
  name: string;
  isGroup: boolean;
  groupLead?: string;
  reply: Message | null;
  editing: Message | null;
  streaming: boolean;
  /** The agent's own suggested reply (Q23); never a client default. */
  suggestion: string;
  collaborationSessionId?: string;
  onClearReply: () => void;
  onClearEdit: () => void;
  onSend: ComposerSend;
  onStop: () => void;
  onUploaded: (row: Resource) => void;
}) {
  const storageKey = draftKey(ownerId, threadId);
  const initial = useRef(readComposerDraft(storageKey));
  const [text, setText] = useState(initial.current.text);
  const [files, setFiles] = useState<Resource[]>(initial.current.files);
  const [uploading, setUploading] = useState(() => pendingDraftUploads(storageKey) > 0);
  const [error, setError] = useState<unknown>();
  const [dragging, setDragging] = useState(false);
  const [mention, setMention] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState<string | null>(null);
  const [highlight, setHighlight] = useState(0);
  const [listening, setListening] = useState(false);
  const committed = useRef<MentionRange[]>(initial.current.mentions);
  const caret = useRef(0);
  const field = useRef<HTMLTextAreaElement>(null);
  const form = useRef<HTMLFormElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const dictation = useRef<{ stop: () => void } | null>(null);
  const dragDepth = useRef(0);
  const prefs = useChatPrefs();
  const toast = useToast();
  const micSheet = usePermissionSheet();
  const tools = useToolsSheet();
  const options = useThreadOptions(threadId);
  const { revision } = useClient();
  const [permission, setPermission] = useState<PermissionState | null>(null);

  useEffect(() => {
    void revision;
    if (!agent) return;
    let live = true;
    void api
      .get<PermissionState>(`/agents/${encodeURIComponent(agent.id)}/permissions`)
      .then((row) => live && setPermission(row))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [agent, revision]);

  /* ---- drafts */
  const current = useRef({ text, files, mentions: committed.current, reply });
  current.current = { text, files, mentions: committed.current, reply };
  useEffect(() => {
    saveComposerDraft(storageKey, { text, files, mentions: committed.current, reply });
  }, [storageKey, text, files, reply]);
  useEffect(() => () => saveComposerDraft(storageKey, current.current), [storageKey]);
  useEffect(
    () =>
      observeDraftUploads(storageKey, () => {
        setUploading(pendingDraftUploads(storageKey) > 0);
        setFiles(readComposerDraft(storageKey).files);
      }),
    [storageKey],
  );
  // The edit bar takes the old text.
  useEffect(() => {
    if (!editing) return;
    setText(editing.content);
    committed.current = [];
    requestAnimationFrame(() => {
      const el = field.current;
      if (!el) return;
      el.focus({ preventScroll: true });
      el.setSelectionRange(el.value.length, el.value.length);
    });
  }, [editing]);
  useEffect(() => {
    if (reply) field.current?.focus({ preventScroll: true });
  }, [reply]);
  useEffect(() => {
    if (fine() && innerWidth > 767) field.current?.focus({ preventScroll: true });
  }, []);

  /* ---- 28px → min(164px, 34vh); the slot height pads the messages */
  useLayoutEffect(() => {
    const el = field.current;
    if (!el) return;
    void text;
    el.style.height = "28px";
    const cap = Math.min(164, Math.round(window.innerHeight * 0.34));
    el.style.height = `${Math.max(28, Math.min(cap, el.scrollHeight))}px`;
    el.style.overflowY = el.scrollHeight > cap ? "auto" : "hidden";
  }, [text]);
  useLayoutEffect(() => {
    const slot = form.current;
    const main = slot?.closest<HTMLElement>("main");
    if (!slot || !main) return;
    const measure = () => main.style.setProperty("--bottom-h", `${slot.offsetHeight + 10}px`);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(slot);
    return () => {
      observer.disconnect();
      main.style.removeProperty("--bottom-h");
    };
  }, []);

  /* ---- mentions: group members (+ القائد, متوقف, @الكل); a direct chat: other agents */
  const memberIds = isGroup
    ? agents.map((row) => row.id)
    : agents.filter((row) => row.id !== agent?.id).map((row) => row.id);
  const pool = agents.filter((row) => memberIds.includes(row.id));
  const candidates =
    mention !== null && mention !== dismissed ? mentionCandidates(pool, mention).slice(0, 6) : [];
  const all =
    isGroup &&
    mention !== null &&
    mention !== dismissed &&
    "الكلall".includes(mention.toLowerCase());
  const options_: Array<Agent | null> = [...candidates, ...(all ? [null] : [])];
  const assistOpen = prefs.assist && options_.length > 0;
  const active = Math.min(highlight, Math.max(0, options_.length - 1));

  const update = (value: string, position = value.length) => {
    committed.current = rebaseMentions(text, value, committed.current);
    caret.current = position;
    setText(value);
    setMention(readMentionQuery(value.slice(0, position)));
    setHighlight(0);
  };
  const pick = (target: Agent | null) => {
    const before = text.slice(0, caret.current);
    const start = before.lastIndexOf("@");
    if (start < 0) return;
    // An LRM keeps a Latin name in order inside Arabic text.
    const label = target ? target.name : t`all`;
    const token = `@${label}`;
    const next = `${text.slice(0, start)}${token} ${text.slice(caret.current)}`;
    committed.current = [
      ...rebaseMentions(text, next, committed.current),
      {
        agent_id: target?.id ?? null,
        session_id: target ? undefined : collaborationSessionId,
        token,
        start,
        end: start + token.length,
      },
    ];
    caret.current = start + token.length + 1;
    setText(next);
    setMention(null);
    requestAnimationFrame(() => {
      field.current?.focus();
      field.current?.setSelectionRange(caret.current, caret.current);
    });
  };

  /* ---- attachments: chips in the composer; ≤6 items ≤8MB; caption rides with the first photo */
  const upload = useCallback(
    async (picked: File[]) => {
      if (!picked.length) return;
      const room = ATTACH.items - files.length;
      const fit = picked.filter((file) => file.size <= ATTACH.bytes).slice(0, Math.max(0, room));
      if (fit.length < picked.length)
        toast(t`Up to 6 photos and files, 8 MB each`, { type: "warn" });
      if (!fit.length) return;
      startDraftUpload(storageKey);
      setUploading(true);
      setError(undefined);
      try {
        const results = await Promise.allSettled(fit.map((file) => api.upload(file, threadId)));
        const done = results.flatMap((r) => (r.status === "fulfilled" ? [r.value] : []));
        appendDraftFiles(storageKey, done);
        for (const row of done) onUploaded(row);
        const failure = results.find((r) => r.status === "rejected");
        if (failure?.status === "rejected") setError(failure.reason);
      } finally {
        finishDraftUpload(storageKey);
        setUploading(false);
      }
    },
    [files.length, storageKey, threadId, toast, onUploaded],
  );

  const canSend = Boolean(text.trim() || files.length) && !uploading;
  const send = () => {
    if (!canSend) return;
    const ids = files.map((file) => file.id);
    const body = text.trim() || (ids.length ? t`Attached files` : "");
    onSend(body, ids, reply?.id ?? null, mentionAddress(text, committed.current), {
      ...(editing ? { edited_from: editing.id } : {}),
    });
    navigator.vibrate?.(6);
    setText("");
    committed.current = [];
    setMention(null);
    setFiles([]);
    current.current = { text: "", files: [], mentions: [], reply: null };
    saveComposerDraft(storageKey, current.current);
    if (reply) onClearReply();
    if (editing) onClearEdit();
    setError(undefined);
  };

  /* ---- dictation: the browser speech API, lang ar, interim results (Q25) */
  const toggleDictation = () => {
    type Recognition = {
      lang: string;
      interimResults: boolean;
      continuous: boolean;
      onresult: (event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void;
      onerror: (event: { error: string }) => void;
      onend: () => void;
      start: () => void;
      stop: () => void;
    };
    const SR =
      (
        window as unknown as {
          SpeechRecognition?: new () => Recognition;
          webkitSpeechRecognition?: new () => Recognition;
        }
      ).SpeechRecognition ??
      (window as unknown as { webkitSpeechRecognition?: new () => Recognition })
        .webkitSpeechRecognition;
    if (!SR) {
      toast(t`Dictation is not available here — hold the microphone to record a voice message.`);
      return;
    }
    if (dictation.current) {
      dictation.current.stop();
      return;
    }
    const rec = new SR();
    rec.lang = document.documentElement.lang?.startsWith("en") ? "en" : "ar";
    rec.interimResults = true;
    rec.continuous = false;
    const base = text.trim() ? text.replace(/\s*$/, " ") : "";
    rec.onresult = (event) => {
      let said = "";
      for (const result of Array.from(event.results)) said += result[0].transcript;
      update(base + said);
    };
    rec.onerror = (event) => {
      if (event.error === "not-allowed") micSheet("mic");
      else if (event.error === "service-not-allowed")
        toast(
          t`Dictation is not available in this browser; hold the microphone to record a voice message`,
          { type: "warn" },
        );
      else if (event.error === "audio-capture")
        toast(t`No microphone was found on this device`, { type: "warn" });
      else if (event.error === "network")
        toast(t`Dictation needs an internet connection`, { type: "warn" });
      else if (event.error === "no-speech")
        toast(t`We heard nothing. Try again.`, { type: "info" });
      else if (event.error !== "aborted") toast(t`Dictation failed`, { type: "error" });
    };
    rec.onend = () => {
      dictation.current = null;
      setListening(false);
    };
    try {
      rec.start();
      dictation.current = rec;
      navigator.vibrate?.(8);
      setListening(true);
    } catch {
      toast(t`Dictation could not start.`);
    }
  };

  /* ---- the voice recorder: hold the mic 350ms; slide 110px to cancel, 70px up to lock */
  const recorder = useVoiceRecorder({
    onSend: async (blob, duration, peaks) => {
      try {
        const file = new File([blob], `voice-${Date.now()}.webm`, {
          type: blob.type || "audio/webm",
        });
        const row = await api.upload(file, threadId);
        onUploaded(row);
        onSend("", [], reply?.id ?? null, undefined, {
          voice: { artifact_id: row.id, duration, peaks },
        });
        if (reply) onClearReply();
      } catch (cause) {
        toast(userError(cause), { type: "error" });
      }
    },
    onDenied: () => micSheet("mic"),
    onUnavailable: () => toast(t`The microphone is not available on this page.`, { type: "warn" }),
    onShort: () => toast(t`Hold the microphone to record, release to send.`),
  });

  const trading = agent
    ? agent.template === "trading" ||
      showsTradingControl({
        role: agent.role,
        trading_account_id: agent.trading_account_id,
        level: permission?.effective_level,
        grants: permission?.active_authorities.length,
      })
    : false;
  const replyTarget = editing ?? reply;
  const showSuggestion =
    Boolean(suggestion) &&
    !text.trim() &&
    !files.length &&
    !replyTarget &&
    !listening &&
    !recorder.active &&
    !streaming;
  const classes = [
    "composer",
    canSend || text.trim() ? "has-text" : "",
    replyTarget ? "is-replying" : "",
    // Send turns into ■ while the agent works; typing a direction brings send back (steering).
    streaming && !text.trim() && !files.length ? "is-streaming" : "",
    showSuggestion ? "has-suggest" : "",
    listening ? "listening" : "",
    recorder.active ? "recording" : "",
    recorder.in ? "rec-in" : "",
  ]
    .filter(Boolean)
    .join(" ");
  const replyAgent = agents.find((row) => row.id === replyTarget?.agent_id);
  return (
    <form
      ref={form}
      className={classes}
      noValidate
      aria-label={t`Message composer`}
      data-dragging={dragging || undefined}
      onSubmit={(event) => {
        event.preventDefault();
        send();
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
      onDragLeave={() => {
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
      {assistOpen && (
        <div className="assist" data-type="mention">
          <div
            className="as-list"
            role="listbox"
            id={`assist-${threadId}`}
            aria-label={t`Mention an agent`}
          >
            <div className="as-sec" role="presentation">
              {isGroup ? (
                <Trans>Group members</Trans>
              ) : (
                <Trans>Bring an agent into the conversation</Trans>
              )}
            </div>
            {options_.map((row, index) => (
              <button
                key={row?.id ?? "all"}
                id={`assist-${threadId}-${index}`}
                type="button"
                role="option"
                aria-selected={index === active}
                className={`as-row${index === active ? " on" : ""}`}
                onMouseDown={(event) => event.preventDefault()}
                onMouseMove={() => setHighlight(index)}
                onClick={() => pick(row)}
              >
                {row ? (
                  <span className="as-av">
                    <AgentAvatar agent={row} />
                  </span>
                ) : (
                  <span className="as-ic">
                    <Icon name="users" />
                  </span>
                )}
                <span className="as-body">
                  <span className="as-t">
                    <span dir="auto">@{row ? row.name : t`all`}</span>
                  </span>
                  {row && <small>{row.description || row.role}</small>}
                </span>
                {row && (row.id === groupLead || row.paused) && (
                  <span className="as-end tag">{row.id === groupLead ? t`Lead` : t`Paused`}</span>
                )}
              </button>
            ))}
          </div>
          {fine() && (
            <div className="as-foot" aria-hidden="true">
              <span>
                <kbd>↑</kbd>
                <kbd>↓</kbd>
                <Trans>Move</Trans>
              </span>
              <span>
                <kbd>↵</kbd>
                <Trans>Pick</Trans>
              </span>
              <span>
                <kbd>Esc</kbd>
                <Trans>Close</Trans>
              </span>
            </div>
          )}
        </div>
      )}
      <div className="composer-card">
        {replyTarget && (
          <div
            className={`reply-bar${editing ? " edit-bar" : ""}`}
            style={
              {
                "--q": editing
                  ? "var(--accent-ink)"
                  : replyTarget.role === "user"
                    ? "var(--mint)"
                    : speakerColor(replyAgent, document.documentElement.dataset.theme === "light"),
              } as React.CSSProperties
            }
          >
            <div className="reply-bar-body">
              <span className="quote-name">
                {editing ? (
                  <>
                    <Icon name="edit" />
                    <Trans>Edit the message</Trans>
                  </>
                ) : replyTarget.role === "user" ? (
                  <Trans>Reply to your message</Trans>
                ) : (
                  <Trans>Reply to {replyAgent?.name ?? "Lonora"}</Trans>
                )}
              </span>
              <span className="quote-text">{snippet(replyTarget)}</span>
            </div>
            <button
              type="button"
              className="icon"
              aria-label={editing ? t`Cancel the edit` : t`Cancel the reply`}
              onClick={() => {
                if (editing) {
                  onClearEdit();
                  setText("");
                } else onClearReply();
                field.current?.focus();
              }}
            >
              <Icon name="close" />
            </button>
          </div>
        )}
        {files.length > 0 && (
          // biome-ignore lint/a11y/useSemanticElements: the reference's attachment chips
          <div className="att-row" role="list" aria-label={t`Attachments`}>
            {files.map((file) => {
              const label = String(file.payload.name ?? file.payload.filename ?? "");
              const image = String(file.payload.media_type ?? "").startsWith("image/");
              return (
                // biome-ignore lint/a11y/useSemanticElements: one chip of the row
                <div key={file.id} className={`att ${image ? "image" : "file"}`} role="listitem">
                  {image ? (
                    <img
                      src={`/api/artifacts/${encodeURIComponent(file.id)}/file?preview=true`}
                      alt=""
                    />
                  ) : (
                    <>
                      <span className="att-ic">
                        <Icon name="file" />
                      </span>
                      <span className="att-n">
                        <b>{label}</b>
                        <small>{t`${Math.max(1, Math.ceil(Number(file.payload.size ?? 0) / 1024))} KB`}</small>
                      </span>
                    </>
                  )}
                  <button
                    type="button"
                    className="att-x"
                    aria-label={t`Remove ${label}`}
                    onClick={() => setFiles((old) => old.filter((row) => row.id !== file.id))}
                  >
                    <Icon name="close" />
                  </button>
                </div>
              );
            })}
          </div>
        )}
        <div className="ta-wrap">
          <div className="ta-mirror" aria-hidden="true" />
          <textarea
            ref={field}
            name="message"
            rows={1}
            aria-label={t`Message to ${name}`}
            placeholder={listening ? t`Listening… speak now` : t`Message ${name}`}
            autoComplete="off"
            enterKeyHint="enter"
            role="combobox"
            aria-expanded={assistOpen}
            aria-autocomplete="list"
            aria-controls={assistOpen ? `assist-${threadId}` : undefined}
            aria-activedescendant={assistOpen ? `assist-${threadId}-${active}` : undefined}
            value={text}
            onChange={(event) => update(event.target.value, event.target.selectionStart)}
            onSelect={(event) => {
              caret.current = event.currentTarget.selectionStart;
              setMention(readMentionQuery(text.slice(0, caret.current)));
            }}
            onPaste={(event) => {
              const picked = Array.from(event.clipboardData.files);
              if (!picked.length) return;
              event.preventDefault();
              void upload(picked);
            }}
            onKeyDown={(event) => {
              if (event.nativeEvent.isComposing || event.keyCode === 229) return;
              if (assistOpen && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
                event.preventDefault();
                const delta = event.key === "ArrowDown" ? 1 : -1;
                setHighlight((active + delta + options_.length) % options_.length);
                return;
              }
              if (assistOpen && (event.key === "Enter" || event.key === "Tab") && !event.shiftKey) {
                event.preventDefault();
                const row = options_[active];
                if (row !== undefined) pick(row);
                return;
              }
              if (assistOpen && event.key === "Escape") {
                event.preventDefault();
                event.stopPropagation();
                setDismissed(mention);
                return;
              }
              if (event.key === "Escape" && replyTarget) {
                event.preventDefault();
                if (editing) onClearEdit();
                else onClearReply();
                return;
              }
              const end =
                getComputedStyle(event.currentTarget).direction === "rtl"
                  ? "ArrowLeft"
                  : "ArrowRight";
              if (
                showSuggestion &&
                !text &&
                (event.key === "Tab" || event.key === end) &&
                !event.shiftKey
              ) {
                event.preventDefault();
                update(suggestion);
                return;
              }
              if (event.key !== "Enter" || event.shiftKey) return;
              const enterSends = prefs.enterSend && fine();
              if (enterSends || event.ctrlKey || event.metaKey) {
                event.preventDefault();
                send();
              }
            }}
          />
          <div className="ta-suggest" hidden={!showSuggestion}>
            <span className="sg-text" dir="auto">
              {suggestion}
            </span>
            <button
              type="button"
              className="sg-take"
              aria-label={t`Use the suggestion: ${suggestion}`}
              title={t`Use the suggestion (Tab)`}
              onClick={() => {
                update(suggestion);
                if (fine()) field.current?.focus({ preventScroll: true });
                navigator.vibrate?.(6);
              }}
            >
              <Icon name="chev" />
            </button>
          </div>
        </div>
        <div className="composer-row">
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
            className="icon cbtn"
            aria-label={t`Attachments and tools`}
            title={t`Attachments and tools`}
            disabled={uploading}
            onClick={() =>
              tools.open({
                agent,
                isGroup,
                trading,
                permission,
                webSearch: options.webSearch,
                onWebSearch: options.setWebSearch,
                onFiles: () => fileInput.current?.click(),
                onPhotos: (camera) => {
                  const input = document.createElement("input");
                  input.type = "file";
                  input.accept = "image/*";
                  if (camera) input.setAttribute("capture", "environment");
                  else input.multiple = true;
                  input.onchange = () => void upload(Array.from(input.files ?? []));
                  input.click();
                },
                onVoiceNote: () => recorder.startLocked(),
              })
            }
          >
            <Icon name="plus" />
          </button>
          <PermissionChip
            threadId={threadId}
            agent={agent}
            isGroup={isGroup}
            trading={trading}
            permission={permission}
            onChanged={setPermission}
          />
          {options.webSearch && (
            <button
              type="button"
              className="icon cbtn tool-on"
              aria-label={t`Web search is on, tap to turn it off`}
              title={t`Web search`}
              onClick={() => {
                void options.setWebSearch(false);
                toast(t`Web search turned off`);
              }}
            >
              <Icon name="globe" />
            </button>
          )}
          <span className="grow" />
          <button
            type="button"
            className="icon cbtn mic"
            aria-label={t`Dictation, or hold to record a voice message`}
            title={t`Tap to dictate · hold for a voice message`}
            {...recorder.micHandlers(toggleDictation)}
          >
            <Icon name="mic" />
          </button>
          <button
            type="button"
            className="icon voice"
            aria-label={t`Voice conversation`}
            title={t`Voice conversation`}
            onClick={() =>
              window.dispatchEvent(
                new CustomEvent("lonora:start-call", { detail: { agentId: agent?.id } }),
              )
            }
          >
            <svg
              className="wave-ico"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              aria-hidden="true"
            >
              <path d="M3.5 10.5v3M7.5 8v8M16.5 8v8M20.5 10.5v3" />
              <path className="wa" d="M12 5v14" />
            </svg>
          </button>
          <button
            type="submit"
            className="icon send"
            aria-label={t`Send the message`}
            title={t`Send`}
          >
            <Icon name="arrowUp" />
          </button>
          <button
            type="button"
            className="icon stop"
            aria-label={t`Stop the reply`}
            title={t`Stop`}
            onClick={onStop}
          >
            <Icon name="stop" />
          </button>
        </div>
        {recorder.bar}
      </div>
      {error != null && (
        <p className="form-error" role="alert">
          {userError(error)}
        </p>
      )}
      {dragging && (
        <div className="drop-zone on" aria-hidden="true">
          <div>
            <Icon name="fileUp" />
            <strong>
              <Trans>Drop here to attach</Trans>
            </strong>
            <small>
              <Trans>Photos and files up to 8 MB</Trans>
            </small>
          </div>
        </div>
      )}
    </form>
  );
}

/* ---- the recorder */
function useVoiceRecorder({
  onSend,
  onDenied,
  onUnavailable,
  onShort,
}: {
  onSend: (blob: Blob, duration: number, peaks: number[]) => Promise<void>;
  onDenied: () => void;
  onUnavailable: () => void;
  onShort: () => void;
}) {
  const [active, setActive] = useState(false);
  const [entered, setEntered] = useState(false);
  const [locked, setLocked] = useState(false);
  const [paused, setPaused] = useState(false);
  const [leaving, setLeaving] = useState<"send" | "cancel" | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [wave, setWave] = useState<number[]>([]);
  const rec = useRef<{
    start: number;
    paused: number;
    pausedAt: number;
    levels: number[];
    chunks: Blob[];
    stream?: MediaStream;
    media?: MediaRecorder;
    ctx?: AudioContext;
    analyser?: AnalyserNode;
    raf: number;
    last: number;
  } | null>(null);
  const press = useRef<{
    id: number;
    x: number;
    y: number;
    timer: number;
    recording: boolean;
  } | null>(null);
  const suppress = useRef(0);
  const knob = useRef<HTMLDivElement | null>(null);
  const lock = useRef<HTMLDivElement | null>(null);

  const cleanupFloat = () => {
    knob.current?.remove();
    lock.current?.remove();
    knob.current = null;
    lock.current = null;
  };
  const finish = async (mode: "send" | "cancel", quiet = false) => {
    const r = rec.current;
    if (!r) return;
    rec.current = null;
    cancelAnimationFrame(r.raf);
    const seconds = ((r.pausedAt || performance.now()) - r.start - r.paused) / 1000;
    const send = mode === "send" && seconds >= VOICE.min;
    setLeaving(send ? "send" : "cancel");
    knob.current?.classList.add("out", send ? "sent" : "cancel");
    lock.current?.classList.remove("in");
    const stop = () => {
      for (const track of r.stream?.getTracks() ?? []) track.stop();
      void r.ctx?.close().catch(() => undefined);
    };
    setTimeout(
      () => {
        cleanupFloat();
        setActive(false);
        setEntered(false);
        setLocked(false);
        setPaused(false);
        setLeaving(null);
        setElapsed(0);
        setWave([]);
      },
      send ? 180 : 320,
    );
    if (!send) {
      try {
        if (r.media && r.media.state !== "inactive") r.media.stop();
      } catch {
        // already stopped
      }
      stop();
      if (mode === "send" && !quiet) onShort();
      else if (!quiet) navigator.vibrate?.([8, 40, 8]);
      return;
    }
    const media = r.media;
    const blob: Blob | null =
      media && media.state !== "inactive"
        ? await new Promise((resolve) => {
            media.onstop = () =>
              resolve(
                r.chunks.length
                  ? new Blob(r.chunks, { type: media.mimeType || "audio/webm" })
                  : null,
              );
            try {
              media.stop();
            } catch {
              resolve(null);
            }
          })
        : null;
    stop();
    if (blob) await onSend(blob, Math.round(seconds * 10) / 10, voicePeaks(r.levels));
  };
  const tick = (now: number) => {
    const r = rec.current;
    if (!r) return;
    const seconds = ((r.pausedAt || now) - r.start - r.paused) / 1000;
    if (!r.pausedAt && now - r.last >= VOICE.sample && r.analyser) {
      r.last = now;
      const buf = new Uint8Array(r.analyser.fftSize);
      r.analyser.getByteTimeDomainData(buf);
      let sum = 0;
      for (const b of buf) {
        const v = (b - 128) / 128;
        sum += v * v;
      }
      const level = Math.min(1, Math.sqrt(sum / buf.length) * 5);
      r.levels.push(level);
      setWave(r.levels.slice(-VOICE.live));
      knob.current?.style.setProperty("--lvl", level.toFixed(2));
    }
    setElapsed(seconds);
    if (seconds >= VOICE.max) {
      void finish("send");
      return;
    }
    r.raf = requestAnimationFrame(tick);
  };
  const begin = async (startLocked: boolean, mic?: HTMLElement) => {
    const media = navigator.mediaDevices;
    if (
      !(media && "getUserMedia" in media && "MediaRecorder" in window && window.isSecureContext)
    ) {
      onUnavailable();
      return;
    }
    navigator.vibrate?.(12);
    const r = {
      start: performance.now(),
      paused: 0,
      pausedAt: 0,
      levels: [],
      chunks: [],
      raf: 0,
      last: 0,
    } as NonNullable<typeof rec.current>;
    rec.current = r;
    setActive(true);
    setLocked(startLocked);
    if (!startLocked && mic) {
      const b = mic.getBoundingClientRect();
      const cx = b.left + b.width / 2;
      const cy = b.top + b.height / 2;
      const k = document.createElement("div");
      k.className = "vrec-knob";
      k.style.left = `${cx}px`;
      k.style.top = `${cy}px`;
      k.innerHTML = `<span class="vring"></span><span class="vk">${svg("mic")}</span>`;
      const l = document.createElement("div");
      l.className = "vrec-lock";
      l.style.left = `${cx}px`;
      l.style.top = `${cy - 136}px`;
      l.innerHTML = `${svg("lock")}<span class="vl-up">${svg("up")}</span>`;
      document.body.append(k, l);
      knob.current = k;
      lock.current = l;
    }
    requestAnimationFrame(() => {
      setEntered(true);
      knob.current?.classList.add("in");
      lock.current?.classList.add("in");
    });
    r.raf = requestAnimationFrame(tick);
    try {
      const stream = await media.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      if (rec.current !== r) {
        for (const track of stream.getTracks()) track.stop();
        return;
      }
      r.stream = stream;
      const mime =
        ["audio/webm;codecs=opus", "audio/mp4", "audio/webm"].find((type) =>
          MediaRecorder.isTypeSupported?.(type),
        ) ?? "";
      r.media = new MediaRecorder(stream, {
        ...(mime ? { mimeType: mime } : {}),
        audioBitsPerSecond: 32000,
      });
      r.media.ondataavailable = (event) => {
        if (event.data?.size) r.chunks.push(event.data);
      };
      r.media.start(250);
      r.ctx = new AudioContext();
      r.analyser = r.ctx.createAnalyser();
      r.analyser.fftSize = 512;
      r.ctx.createMediaStreamSource(stream).connect(r.analyser);
    } catch (cause) {
      if (rec.current !== r) return;
      void finish("cancel", true);
      const nameOf = (cause as { name?: string })?.name;
      if (nameOf === "NotAllowedError" || nameOf === "SecurityError") onDenied();
      else onUnavailable();
    }
  };
  const doLock = () => {
    if (!rec.current || locked) return;
    setLocked(true);
    navigator.vibrate?.(14);
    lock.current?.classList.add("locked");
    knob.current?.classList.add("out");
    setTimeout(cleanupFloat, 260);
  };
  const track = (dx: number, dy: number, rtl: boolean) => {
    const toward = Math.max(0, rtl ? dx : -dx);
    const up = Math.max(0, -dy);
    const horiz = toward >= up;
    const dir = rtl ? 1 : -1;
    if (knob.current)
      knob.current.style.transform = horiz
        ? `translateX(${dir * Math.min(toward, VOICE.cancel)}px)`
        : `translateY(${-Math.min(up, VOICE.lock)}px)`;
    lock.current?.style.setProperty("--pl", (horiz ? 0 : Math.min(1, up / VOICE.lock)).toFixed(3));
    if (horiz && toward >= VOICE.cancel) void finish("cancel");
    else if (!horiz && up >= VOICE.lock) doLock();
  };
  useEffect(() => {
    if (!active) return;
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        void finish("cancel", true);
      } else if (
        locked &&
        event.key === "Enter" &&
        !(event.target as HTMLElement).closest?.("textarea")
      ) {
        event.preventDefault();
        void finish("send");
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  });
  const bar = active ? (
    <div
      className={`vrec-bar${locked ? " locked" : ""}${paused ? " paused" : ""}${leaving === "send" ? " is-sent" : leaving === "cancel" ? " is-cancel" : ""}`}
    >
      <button
        type="button"
        className="icon vrec-del"
        aria-label={t`Delete the recording`}
        onClick={() => void finish("cancel")}
      >
        <Icon name="trash" />
      </button>
      <span className="vrec-dot" aria-hidden="true" />
      <span className="vrec-time ltr" role="timer" aria-label={t`Recording length`}>
        {voiceFmt(elapsed)}
      </span>
      <span className="vrec-wave" aria-hidden="true">
        {Array.from({ length: VOICE.live }, (_, i) => {
          const v = wave[i - (VOICE.live - wave.length)];
          return (
            // biome-ignore lint/suspicious/noArrayIndexKey: fixed live bars
            <i key={i} style={{ height: v == null ? undefined : `${Math.round(14 + v * 86)}%` }} />
          );
        })}
      </span>
      <span className="vrec-hint">
        <Icon name="chevR" />
        <span>
          <Trans>Slide to cancel</Trans>
        </span>
      </span>
      <button
        type="button"
        className="icon vrec-pause"
        aria-label={paused ? t`Continue recording` : t`Pause recording`}
        onClick={() => {
          const r = rec.current;
          if (!r) return;
          if (r.pausedAt) {
            r.paused += performance.now() - r.pausedAt;
            r.pausedAt = 0;
            r.media?.resume();
            setPaused(false);
          } else {
            r.pausedAt = performance.now();
            r.media?.pause();
            setPaused(true);
          }
        }}
      >
        <Icon name={paused ? "mic" : "pause"} />
      </button>
      <button
        type="button"
        className="icon vrec-send"
        aria-label={t`Send the voice message`}
        onClick={() => void finish("send")}
      >
        <Icon name="arrowUp" />
      </button>
    </div>
  ) : null;
  return {
    active,
    in: entered,
    bar,
    startLocked: () => void begin(true),
    micHandlers: (onTap: () => void) => ({
      onPointerDown: (event: React.PointerEvent<HTMLButtonElement>) => {
        if (event.button > 0 || rec.current) return;
        const target = event.currentTarget;
        press.current = {
          id: event.pointerId,
          x: event.clientX,
          y: event.clientY,
          recording: false,
          timer: window.setTimeout(() => {
            if (press.current) press.current.recording = true;
            void begin(false, target);
          }, VOICE.hold),
        };
        try {
          target.setPointerCapture(event.pointerId);
        } catch {
          // ignored
        }
      },
      onPointerMove: (event: React.PointerEvent<HTMLButtonElement>) => {
        const p = press.current;
        if (!p || p.id !== event.pointerId) return;
        const dx = event.clientX - p.x;
        const dy = event.clientY - p.y;
        if (!p.recording) {
          if (Math.hypot(dx, dy) > 12) {
            clearTimeout(p.timer);
            press.current = null;
          }
          return;
        }
        if (rec.current && !locked)
          track(dx, dy, getComputedStyle(event.currentTarget).direction === "rtl");
      },
      onPointerUp: (event: React.PointerEvent<HTMLButtonElement>) => {
        const p = press.current;
        if (!p || p.id !== event.pointerId) return;
        press.current = null;
        clearTimeout(p.timer);
        if (!p.recording) return;
        suppress.current = Date.now() + 400;
        if (rec.current && !locked) void finish("send");
      },
      onPointerCancel: () => {
        const p = press.current;
        press.current = null;
        if (p) clearTimeout(p.timer);
        if (p?.recording && rec.current && !locked) void finish("cancel");
      },
      onClick: () => {
        if (Date.now() < suppress.current || rec.current) return;
        onTap();
      },
    }),
  };
}
