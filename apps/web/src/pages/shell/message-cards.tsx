// Lonora message cards adapted from Tampletgrok's ThreadView; Apache-2.0.
import { t } from "@lingui/core/macro";
import { Trans, useLingui } from "@lingui/react/macro";
import { ChatMarkdown } from "@lonora/chat-ui/web";
import { CornerUpLeft } from "lucide-react";
import { ArtifactFileCard } from "../../components/ArtifactFileCard";
import { AgentAvatar } from "../../components/ai/AgentAvatar";
import type { Agent, Event, Message, Resource } from "../../lib/api";

export function MessageBubble({
  message,
  agent,
  artifacts,
  replyParent,
  onReply,
  onPreview,
}: {
  message: Message;
  agent?: Agent;
  artifacts: Resource[];
  replyParent?: Message;
  onReply: (message: Message) => void;
  onPreview: (artifact: Resource) => void;
}) {
  const { i18n } = useLingui();
  const user = message.role === "user";
  return (
    <article className={`message template-message ${message.role}`} data-message-id={message.id}>
      <div className="template-message-frame">
        {!user && (
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
          <ChatMarkdown>{message.content}</ChatMarkdown>
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
          <time
            dateTime={message.created_at}
            title={new Date(message.created_at).toLocaleString(i18n.locale)}
          >
            {new Date(message.created_at).toLocaleTimeString(i18n.locale, {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </time>
          <button
            type="button"
            className="template-icon-button"
            onClick={() => onReply(message)}
            aria-label={t`Reply`}
            title={t`Reply`}
          >
            <CornerUpLeft size={14} />
          </button>
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
