import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { Icon } from "@lonora/ui-web";
import { type ReactNode, useRef } from "react";
import type { Agent, Message as ApiMessage, Resource } from "../lib/api";
import { isOutgoingMessage } from "../lib/outgoing-messages";
import {
  type ConversationMessage,
  callPart,
  clock,
  partsOf,
  speakerColor,
  useConversation,
  voicePart,
} from "./context";
import { GenUiPart, GenUiSubmitQuote, hasGenUi } from "./GenUiPart";
import { TextBody } from "./Markdown";
import { VoiceNote, voiceFmt } from "./Voice";

/* ONE Message component for every kind (reference msgMarkup, Desktop-37 3785-3801): text and
   Markdown, photos with a caption, files, voice notes, call log bubbles, generated interfaces,
   streaming answers with steps, and the owner's states (ticks, queued, failed). Cards (owner
   decisions, approvals, orders, notices, errors) come in as `card` and keep the same frame. */

export type LiveReply = {
  /** turnActivity phase (preparing, writing, queued…): data-activity-phase. */
  phase?: string;
  /** A typing/steps row for a run with no text yet: data-progress-run-id. */
  progress?: boolean;
  text: string;
  /** The answer is still being written (caret). */
  streaming: boolean;
  rich?: ApiMessage["rich_content"];
  runId: string;
};

type Props = {
  message: ConversationMessage;
  previous?: ConversationMessage;
  /** A card in the agent's frame (owner decision, approval, question, order line). */
  card?: ReactNode;
  /** k-* class for cards, as the reference: k-card, k-line, k-oa, k-odl. */
  cardKind?: "card" | "line" | "oa" | "odl";
  live?: LiveReply;
  steps?: ReactNode;
  stopped?: boolean;
  selected?: boolean;
};

const SWIPE = { lock: 12, ratio: 1.4, max: 72, ready: 56 };

function senderOf(message: ApiMessage) {
  return message.role === "user" ? "user" : (message.agent_id ?? "agent");
}
function startsRun(message: ApiMessage, previous?: ApiMessage) {
  if (!previous) return true;
  if (senderOf(previous) !== senderOf(message)) return true;
  return Boolean(callPart(previous) || callPart(message));
}

export function Ticks({ message }: { message: ConversationMessage }) {
  if (message.role !== "user") return null;
  const outgoing = isOutgoingMessage(message) ? message : undefined;
  if (outgoing?.delivery === "failed") return null;
  if (outgoing) {
    // Q6: a queued message says why it waits; one being sent just shows the clock.
    const label = outgoing.delivery === "queued" ? t`Waiting for the network…` : t`Waiting to send`;
    return (
      <span className="ticks wait" role="status" aria-label={label}>
        <Icon name="clock" />
      </span>
    );
  }
  return message.consumed ? (
    <span className="ticks read">
      <Icon name="checks" />
      <span className="sr-only">{t`Read`}</span>
    </span>
  ) : (
    <span className="ticks">
      <Icon name="check" />
      <span className="sr-only">{t`Sent`}</span>
    </span>
  );
}

export function snippet(message?: ApiMessage | null): string {
  if (!message) return "";
  const call = callPart(message);
  const voice = voicePart(message);
  const text = call
    ? call.missed
      ? t`Missed voice call`
      : t`Voice call`
    : voice
      ? t`Voice message (${voiceFmt(voice.duration)})`
      : message.content;
  return text.length > 120 ? `${text.slice(0, 120)}…` : text;
}

function Quote({ id }: { id: string }) {
  const ctx = useConversation();
  const original = ctx.byId.get(id);
  const agent = ctx.agents.find((row) => row.id === original?.agent_id);
  const mine = original?.role === "user";
  const color = mine ? "var(--mint)" : speakerColor(agent, ctx.light);
  return (
    <button
      type="button"
      className="quote"
      style={{ "--q": color } as React.CSSProperties}
      aria-label={t`Go to the quoted message`}
      onClick={(event) => {
        event.stopPropagation();
        ctx.onJump(id);
      }}
    >
      <span className="quote-name">
        {original ? (mine ? t`You` : (agent?.name ?? "Lonora")) : t`Message`}
      </span>
      <span className="quote-text">
        {original && voicePart(original) && <Icon name="mic" />}
        {original && hasGenUi(original) && <Icon name="sparkle" />}
        {original ? snippet(original) : t`The original message is no longer available.`}
      </span>
    </button>
  );
}

function Reactions({ message }: { message: ConversationMessage }) {
  const ctx = useConversation();
  const rows = (message.reactions ?? []).filter((row) => row.emoji);
  if (!rows.length) return null;
  const unique = [...new Set(rows.map((row) => row.emoji))];
  const label = rows
    .map(
      (row) =>
        `${row.reactor === "owner" ? t`You` : (ctx.agents.find((a) => a.id === row.reactor)?.name ?? "")} ${row.emoji}`,
    )
    .join("، ");
  return (
    <button
      type="button"
      className={`reacts${rows.some((row) => row.reactor === "owner") ? " has-mine" : ""}`}
      aria-label={t`Reactions: ${label}`}
      onClick={(event) => ctx.onReactionList(message, event.currentTarget)}
    >
      <span aria-hidden="true">{unique.join("")}</span>
      {rows.length > 1 && <span className="n">{rows.length}</span>}
    </button>
  );
}

/** The image types the browser shows in an <img> (SVG in the image context, never inline). */
export function isImage(artifact?: Resource) {
  const mime = String(
    artifact?.payload.media_type ?? artifact?.payload.mime_type ?? "",
  ).toLowerCase();
  return /^image\/(png|jpeg|gif|webp|avif|svg\+xml)$/.test(mime);
}

function Attachments({ ids, caption }: { ids: string[]; caption?: ReactNode }) {
  const ctx = useConversation();
  const items = ids.map((id) => ({ id, artifact: ctx.artifacts.get(id) }));
  const images = items.filter(({ artifact }) => isImage(artifact));
  const files = items.filter((item) => !images.includes(item));
  return (
    <>
      {images.map(({ id, artifact }) => (
        <button
          key={id}
          type="button"
          className="img-msg"
          data-artifact-id={id}
          aria-label={t`Photo, tap to view`}
          onClick={() => artifact && ctx.onOpenImage(artifact)}
        >
          <img
            src={`/api/artifacts/${encodeURIComponent(id)}/file?preview=true`}
            alt=""
            decoding="async"
            // The shimmer stops once the photo has downloaded (reference .ld).
            ref={(node) => {
              if (node?.complete && node.naturalWidth) node.parentElement?.classList.add("ld");
            }}
            onLoad={(event) => event.currentTarget.parentElement?.classList.add("ld")}
            width={Number(artifact?.payload.width) || 4}
            height={Number(artifact?.payload.height) || 3}
          />
        </button>
      ))}
      {images.length > 0 && caption}
      {files.map(({ id, artifact }) => (
        <FileChip key={id} id={id} artifact={artifact} />
      ))}
      {!images.length && caption}
    </>
  );
}

function FileChip({ id, artifact }: { id: string; artifact?: Resource }) {
  const ctx = useConversation();
  const size = Number(artifact?.payload.size ?? artifact?.payload.size_bytes ?? 0);
  const kb = Math.max(1, Math.ceil(size / 1024));
  return (
    <button
      type="button"
      className="file-chip"
      data-artifact-id={id}
      onClick={() => artifact && ctx.onOpenFile(artifact)}
    >
      <Icon name="file" />
      <span>
        <strong>{String(artifact?.payload.name ?? artifact?.payload.filename ?? t`File`)}</strong>
        <small>{t`${kb} KB`}</small>
      </span>
    </button>
  );
}

function CallBubble({ message }: { message: ConversationMessage }) {
  const ctx = useConversation();
  const call = callPart(message);
  if (!call) return null;
  const label = call.missed ? t`Missed voice call` : t`Voice call`;
  const minutes = Math.floor(call.duration_seconds / 60);
  const seconds = String(call.duration_seconds % 60).padStart(2, "0");
  return (
    // The owner's own call sits on the owner's side; the agent's call on the agent's.
    <div
      className={`msg ${call.direction === "outgoing" ? "mine" : "theirs"} first k-call`}
      data-message-id={message.id}
      data-call-direction={call.direction}
    >
      <div className="msg-line">
        <button
          type="button"
          className={`bubble call-bubble${call.missed ? " missed" : ""}`}
          aria-label={t`${label}. Tap to call back`}
          onClick={ctx.onCall}
        >
          <span className="call-ico">
            <Icon name="phone" />
          </span>
          <span className="call-body">
            <strong>{label}</strong>
            <small>
              {call.missed ? (
                <Trans>Tap to call back</Trans>
              ) : (
                <span className="ltr">{`${minutes}:${seconds}`}</span>
              )}
            </small>
          </span>
          <span className="meta">
            <time dateTime={message.created_at}>{clock(message.created_at)}</time>
          </span>
        </button>
      </div>
    </div>
  );
}

export function TypingBubble({
  agent,
  named,
  runId,
  phase,
}: {
  agent?: Agent;
  named: boolean;
  runId?: string;
  phase?: string;
}) {
  const ctx = useConversation();
  return (
    // biome-ignore lint/a11y/useAriaPropsSupportedByRole: the typing row is named for assistive technology
    <div
      className="msg theirs first"
      data-progress-run-id={runId}
      data-turn-run-id={runId}
      data-activity-phase={phase}
      aria-label={named && agent ? t`${agent.name} is typing` : t`Typing`}
    >
      <div className="msg-line">
        <div className="bubble typing">
          {named && agent && (
            <span className="sender" style={{ color: speakerColor(agent, ctx.light) }}>
              {agent.name}
            </span>
          )}
          <span className="dots" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
        </div>
      </div>
    </div>
  );
}

export function Message({
  message,
  previous,
  card,
  cardKind,
  live,
  steps,
  stopped,
  selected,
}: Props) {
  const ctx = useConversation();
  const press = useRef<{
    id: number;
    x: number;
    y: number;
    timer: number;
    locked: boolean;
    dx: number;
  } | null>(null);
  const root = useRef<HTMLDivElement>(null);
  if (callPart(message)) return <CallBubble message={message} />;
  const mine = message.role === "user";
  const agent = ctx.agents.find((row) => row.id === message.agent_id);
  const first = startsRun(message, previous);
  const guest =
    !ctx.isGroup && !mine && Boolean(message.agent_id) && message.agent_id !== ctx.threadAgentId;
  const outgoing = isOutgoingMessage(message) ? message : undefined;
  const failed = outgoing?.delivery === "failed";
  const voice = voicePart(message);
  const genUi =
    !mine &&
    (hasGenUi(message) ||
      Boolean(
        live?.rich && partsOf({ ...message, rich_content: live.rich }).some((p) => p.type === "ui"),
      ));
  const superseded = Boolean(message.superseded_by);
  const submitted = mine && message.origin === "ui_submit";
  const images = message.attachment_ids.some((id) => isImage(ctx.artifacts.get(id)));
  const kindClass = card
    ? ` k-card${cardKind && cardKind !== "card" ? ` k-${cardKind}` : ""}`
    : voice
      ? " k-voice"
      : genUi
        ? " k-ui"
        : images
          ? " k-image"
          : "";
  const bubbleClass = card
    ? "wide"
    : genUi
      ? "wide ui-bubble"
      : voice
        ? "voice-bubble"
        : images
          ? `img-bubble${message.content ? " has-caption" : ""}`
          : "";
  const name =
    (ctx.isGroup || guest) && !mine && first ? (
      <span className="sender" style={{ color: speakerColor(agent, ctx.light) }}>
        {agent?.name ?? "Lonora"}
      </span>
    ) : null;
  const text = live ? live.text : message.content;
  let body: ReactNode;
  if (card) body = card;
  else if (submitted) body = <GenUiSubmitQuote message={message} />;
  else if (voice) body = <VoiceNote part={voice} messageId={message.id} />;
  else if (genUi)
    body = (
      <GenUiPart
        message={
          live
            ? {
                ...message,
                // The preview's edits live under preview:<run>; the canonical message
                // reads them back through previousVisualIds when its run links it.
                id: `preview:${live.runId}`,
                content: live.text,
                rich_content: live.rich ?? null,
              }
            : message
        }
        live={Boolean(live?.streaming)}
      />
    );
  else {
    const textNode =
      text || live ? (
        <TextBody
          text={text}
          agent={!mine}
          mentions={ctx.mentions}
          caret={Boolean(live?.streaming)}
        />
      ) : null;
    body = message.attachment_ids.length ? (
      <Attachments
        ids={message.attachment_ids}
        caption={
          images && text ? (
            <span className="text caption">
              <TextBody text={text} agent={false} mentions={ctx.mentions} />
            </span>
          ) : (
            textNode
          )
        }
      />
    ) : (
      <>
        {steps}
        {textNode}
      </>
    );
  }
  const note = stopped ? (
    <span className="stopped">
      <Trans>You stopped the reply</Trans>
    </span>
  ) : superseded ? (
    <span className="edited">
      <Trans>Edited</Trans>
    </span>
  ) : null;
  const interactive = !card && !outgoing && !message.id.startsWith("preview:");
  const endPress = () => {
    const p = press.current;
    if (!p) return;
    clearTimeout(p.timer);
    press.current = null;
    const el = root.current;
    const bubble = el?.querySelector<HTMLElement>(".bubble");
    if (bubble) bubble.style.transform = "";
    el?.classList.remove("swipe-ready");
    const hint = el?.querySelector<HTMLElement>(".swipe-hint");
    if (hint) hint.style.opacity = "0";
    if (p.locked && Math.abs(p.dx) >= SWIPE.ready) ctx.onReply(message);
  };
  return (
    // biome-ignore lint/a11y/noStaticElementInteractions: right-click opens the same menu as the chevron button
    <div
      ref={root}
      className={`msg ${mine ? "mine" : "theirs"}${first ? " first" : ""}${kindClass}${selected ? " selected" : ""}${superseded ? " superseded" : ""}`}
      data-message-id={message.id}
      data-mid={message.id}
      data-delivery={outgoing?.delivery}
      data-stream-run-id={live && !live.progress ? live.runId : undefined}
      data-progress-run-id={live?.progress ? live.runId : undefined}
      data-turn-run-id={live?.runId}
      data-activity-phase={live?.phase}
      onContextMenu={
        interactive
          ? (event) => {
              event.preventDefault();
              ctx.onMenu(
                message,
                event.currentTarget.querySelector(".bubble") ?? event.currentTarget,
              );
            }
          : undefined
      }
    >
      <div className="msg-line">
        <div
          className={`bubble ${bubbleClass}${live?.streaming ? " is-streaming" : ""}`.trim()}
          onPointerDown={
            interactive
              ? (event) => {
                  if (event.button > 0 || (event.target as HTMLElement).closest("button,a,input"))
                    return;
                  const target = event.currentTarget;
                  press.current = {
                    id: event.pointerId,
                    x: event.clientX,
                    y: event.clientY,
                    locked: false,
                    dx: 0,
                    timer: window.setTimeout(() => {
                      press.current = null;
                      navigator.vibrate?.(12);
                      ctx.onMenu(message, target);
                    }, 450),
                  };
                }
              : undefined
          }
          onPointerMove={(event) => {
            const p = press.current;
            if (!p || p.id !== event.pointerId) return;
            const dx = event.clientX - p.x;
            const dy = event.clientY - p.y;
            if (!p.locked) {
              if (Math.hypot(dx, dy) < SWIPE.lock) return;
              clearTimeout(p.timer);
              if (Math.abs(dx) <= SWIPE.ratio * Math.abs(dy)) {
                press.current = null;
                return;
              }
              p.locked = true;
            }
            const rtl = getComputedStyle(event.currentTarget).direction === "rtl";
            // agent bubbles move toward the middle (inline end); own bubbles either way
            const toward = rtl ? -dx : dx;
            const pull = mine ? Math.abs(dx) : Math.max(0, toward);
            const clamped = Math.min(SWIPE.max, pull);
            p.dx = clamped;
            const sign = mine ? Math.sign(dx) : rtl ? -1 : 1;
            event.currentTarget.style.transform = `translateX(${sign * clamped}px)`;
            const el = root.current;
            const hint = el?.querySelector<HTMLElement>(".swipe-hint");
            if (hint) hint.style.opacity = String(Math.min(1, clamped / SWIPE.ready));
            const ready = clamped >= SWIPE.ready;
            if (ready && !el?.classList.contains("swipe-ready")) navigator.vibrate?.(8);
            el?.classList.toggle("swipe-ready", ready);
          }}
          onPointerUp={endPress}
          onPointerCancel={endPress}
          onPointerLeave={(event) => {
            if (press.current && !press.current.locked && event.buttons === 0) endPress();
          }}
        >
          {name}
          {message.reply_to && <Quote id={message.reply_to} />}
          {body}
          {!card && (
            <span className="meta">
              {note}
              {!outgoing && <time dateTime={message.created_at}>{clock(message.created_at)}</time>}
              <Ticks message={message} />
            </span>
          )}
          {interactive && (
            <button
              type="button"
              className="msg-more"
              aria-label={t`Message options`}
              aria-haspopup="menu"
              onClick={(event) => ctx.onMenu(message, event.currentTarget)}
            >
              <Icon name="down" />
            </button>
          )}
        </div>
        {failed && outgoing ? (
          <button
            type="button"
            className="msg-fail"
            aria-label={t`The message was not sent. Options`}
            onClick={(event) => ctx.onMenu(message, event.currentTarget)}
          >
            !
          </button>
        ) : interactive ? (
          <button
            type="button"
            className="msg-react"
            aria-label={t`React to the message`}
            onClick={(event) => ctx.onReactPicker(message, event.currentTarget)}
          >
            <Icon name="smile" />
          </button>
        ) : null}
        {interactive && (
          <span className="swipe-hint" aria-hidden="true">
            <Icon name="reply" />
          </span>
        )}
      </div>
      {failed && outgoing && (
        <button
          type="button"
          className="fail-note"
          onClick={() => ctx.onRetry(outgoing.retry_nonce)}
        >
          <Trans>Not sent · tap to retry</Trans>
        </button>
      )}
      <Reactions message={message} />
    </div>
  );
}
