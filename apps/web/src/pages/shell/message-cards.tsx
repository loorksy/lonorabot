// Lonora message cards adapted from Tampletgrok's ThreadView; Apache-2.0.
import { t } from "@lingui/core/macro";
import { Trans, useLingui } from "@lingui/react/macro";
import { plainTextLinkParts } from "@lonora/chat-ui/markdown";
import { ChatMarkdown } from "@lonora/chat-ui/web";
import { ArrowRight, CornerUpLeft, MessagesSquare } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArtifactFileCard } from "../../components/ArtifactFileCard";
import { AgentAvatar } from "../../components/ai/AgentAvatar";
import { WorkingIndicator } from "../../components/ai/primitives";
import type { Agent, Event, Message, ReplyStreamSnapshot, Resource, Run } from "../../lib/api";
import { isOutgoingMessage } from "../../lib/outgoing-messages";
import { userError } from "../../lib/user_error";

export function FailedReplyNotice({
  run,
  agent,
  showSpeaker,
}: {
  run: Run;
  agent?: Agent;
  showSpeaker: boolean;
}) {
  return (
    <article
      className="message template-message assistant template-reply-failure"
      data-failed-run-id={run.id}
      role="alert"
    >
      <div className="template-message-frame">
        {showSpeaker && (
          <div className="template-speaker">
            {agent && <AgentAvatar agent={agent} />}
            <strong dir="auto">{agent?.name ?? <Trans>Agent</Trans>}</strong>
          </div>
        )}
        <div className="message-body template-message-body" dir="auto">
          {userError({ code: run.error_code })}
        </div>
      </div>
    </article>
  );
}

export function MessageBubble({
  message,
  agent,
  artifacts,
  replyParent,
  onReply,
  onPreview,
  peer,
  peerRun,
  showSpeaker = true,
  body,
  onRetrySend,
}: {
  message: Message;
  body?: ReactNode;
  onRetrySend?: (nonce: string) => Promise<void>;
  agent?: Agent;
  artifacts: Resource[];
  replyParent?: Message;
  onReply: (message: Message) => void;
  onPreview: (artifact: Resource) => void;
  peer?: Resource;
  peerRun?: Run;
  showSpeaker?: boolean;
}) {
  const { i18n } = useLingui();
  if (peer) return <PeerMessageCard message={message} peer={peer} run={peerRun} />;
  const user = message.role === "user";
  const outgoing = isOutgoingMessage(message) ? message : undefined;
  let partOffset = 0;
  const literalParts = user
    ? plainTextLinkParts(message.content).map((part) => {
        const offset = partOffset;
        partOffset += part.value.length;
        return { ...part, offset };
      })
    : [];
  return (
    <article
      className={`message template-message ${message.role}`}
      data-message-id={message.id}
      data-delivery={outgoing?.delivery}
    >
      <div className={`template-message-frame${body ? " has-interactive-body" : ""}`}>
        {!user && showSpeaker && (
          <div className="template-speaker">
            {agent && <AgentAvatar agent={agent} />}
            <strong dir="auto">{agent?.name ?? <Trans>Agent</Trans>}</strong>
          </div>
        )}
        <div className="message-body template-message-body" dir="auto">
          {message.reply_to && (
            <blockquote className="template-message-quote">
              {replyParent ? (
                replyParent.content.slice(0, 180)
              ) : (
                <Trans>Reply to an earlier message</Trans>
              )}
            </blockquote>
          )}
          {body ??
            (message.content && (
              <div className="template-message-text">
                {user ? (
                  <div className="template-user-text">
                    {literalParts.map((part) =>
                      part.type === "link" ? (
                        <a
                          key={part.offset}
                          href={part.href}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {part.value}
                        </a>
                      ) : (
                        <span key={part.offset}>{part.value}</span>
                      ),
                    )}
                  </div>
                ) : (
                  <ChatMarkdown>{message.content}</ChatMarkdown>
                )}
              </div>
            ))}
          {message.attachment_ids.map((id) => {
            const file = artifacts.find((artifact) => artifact.id === id);
            return file ? (
              <ArtifactFileCard key={id} artifact={file} onPreview={() => onPreview(file)} />
            ) : (
              <a
                className="template-unresolved-attachment"
                key={id}
                href={`/api/artifacts/${id}/file`}
              >
                <Trans>Attachment</Trans>
              </a>
            );
          })}
        </div>
        <div className="message-meta template-message-meta">
          {!outgoing && (
            <time
              dateTime={message.created_at}
              title={new Date(message.created_at).toLocaleString(i18n.locale)}
            >
              {new Date(message.created_at).toLocaleTimeString(i18n.locale, {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </time>
          )}
          {outgoing ? (
            outgoing.delivery === "failed" ? (
              <button
                type="button"
                className="template-icon-button"
                onClick={() => void onRetrySend?.(outgoing.retry_nonce).catch(() => undefined)}
              >
                <Trans>Retry</Trans>
              </button>
            ) : (
              <span role="status">
                <Trans>Sending…</Trans>
              </span>
            )
          ) : (
            <button
              type="button"
              className="template-icon-button"
              onClick={() => onReply(message)}
              aria-label={t`Reply`}
              title={t`Reply`}
            >
              <CornerUpLeft size={14} />
            </button>
          )}
        </div>
      </div>
    </article>
  );
}

/** Actual persisted agent requests and results, with links to their two continuous conversations. */
export function PeerMessageCard({
  message,
  peer,
  run,
}: {
  message: Message;
  peer: Resource;
  run?: Run;
}) {
  const payload = peer.payload;
  const request =
    payload.source_message_id === message.id || payload.target_message_id === message.id;
  const wrapped =
    /^<peer_outcome\b[^>]*status=['"]([^'"]+)['"][^>]*>\n([\s\S]*)\n<\/peer_outcome>$/.exec(
      message.content,
    );
  const body = wrapped?.[2] ?? message.content;
  const sourceName = String(payload.source_agent_name ?? "");
  const targetName = String(payload.target_agent_name ?? "");
  const sender = request ? sourceName : targetName;
  const recipient = request ? targetName : sourceName;
  const fromId = String((request ? payload.source_agent_id : payload.target_agent_id) ?? "");
  const toId = String((request ? payload.target_agent_id : payload.source_agent_id) ?? "");
  const fromThread = String((request ? payload.source_thread_id : payload.target_thread_id) ?? "");
  const toThread = String((request ? payload.target_thread_id : payload.source_thread_id) ?? "");
  const status = wrapped?.[1] ?? run?.status ?? String(payload.status ?? "queued");
  return (
    <article
      className="message template-message assistant template-peer-card"
      data-message-id={message.id}
      data-peer-message-id={peer.id}
      data-peer-kind={request ? "request" : "outcome"}
    >
      <div className="template-message-frame">
        <div className="template-peer-heading">
          <MessagesSquare size={15} aria-hidden="true" />
          <span>
            <Trans>Agent collaboration</Trans>
          </span>
        </div>
        <div className="template-peer-participants">
          {fromId ? (
            <Link
              to={`/app/${encodeURIComponent(fromId)}?thread=${encodeURIComponent(fromThread)}`}
            >
              <bdi>{sender || <Trans>Agent</Trans>}</bdi>
            </Link>
          ) : (
            <bdi>{sender || <Trans>Agent</Trans>}</bdi>
          )}
          <ArrowRight size={13} aria-hidden="true" />
          {toId ? (
            <Link to={`/app/${encodeURIComponent(toId)}?thread=${encodeURIComponent(toThread)}`}>
              <bdi>{recipient || <Trans>Agent</Trans>}</bdi>
            </Link>
          ) : (
            <bdi>{recipient || <Trans>Agent</Trans>}</bdi>
          )}
        </div>
        <div className="message-body template-message-body" dir="auto">
          {!(status === "cancelled" && body === "cancelled") && <ChatMarkdown>{body}</ChatMarkdown>}
        </div>
        <div className="template-peer-status">
          {request && run ? (
            <WorkingIndicator run={run} />
          ) : status === "cancelled" ? (
            <Trans>Cancelled</Trans>
          ) : status === "failed" ? (
            <Trans>Failed</Trans>
          ) : status === "completed" ? (
            <Trans>Completed</Trans>
          ) : (
            <Trans>Queued</Trans>
          )}
        </div>
      </div>
    </article>
  );
}

export function RecoveryNotice({ events }: { events: Event[] }) {
  return events.some((e) => e.kind.includes("recover")) ? (
    <p className="notice">
      <Trans>The task resumed from its saved state after reconnection.</Trans>
    </p>
  ) : null;
}

/** A preview from a real fenced model turn, replaced only by its identified durable message. */
export function StreamingMessageCard({
  run,
  stream,
  agent,
  showSpeaker = true,
}: {
  run: Run;
  stream: ReplyStreamSnapshot;
  agent?: Agent;
  showSpeaker?: boolean;
}) {
  return (
    <article
      className="message template-message assistant template-streaming-card"
      data-stream-run-id={run.id}
      data-stream-turn-id={stream.turn_id}
      data-stream-sequence={stream.sequence}
    >
      <div className="template-message-frame">
        {showSpeaker && (
          <div className="template-speaker">
            {agent && <AgentAvatar agent={agent} />}
            <strong dir="auto">{agent?.name ?? <Trans>Agent</Trans>}</strong>
          </div>
        )}
        <div className="message-body template-message-body template-message-text" dir="auto">
          <ChatMarkdown streaming={stream.phase === "streaming"}>{stream.text}</ChatMarkdown>
        </div>
        <div className="message-meta template-message-meta">
          {stream.phase === "streaming" && (
            <span role="status">
              {agent && <AgentAvatar agent={agent} state="writing" />}
              <Trans>Writing</Trans>
            </span>
          )}
        </div>
        {stream.truncated && (
          <p className="muted">
            <Trans>The full response will appear when complete.</Trans>
          </p>
        )}
      </div>
    </article>
  );
}
