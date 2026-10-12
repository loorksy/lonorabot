import { Trans } from "@lingui/react/macro";
import { useEffect, useRef } from "react";
import type { Agent, Message, Resource } from "../../lib/api";
import { MessageBubble } from "./MessageBubble";
export function ThreadMessages({
  messages,
  agents,
  artifacts,
  onReply,
  onPreview,
  onOlder,
}: {
  messages: Message[];
  agents: Agent[];
  artifacts: Resource[];
  onReply: (message: Message) => void;
  onPreview: (artifact: Resource) => void;
  onOlder: () => void;
}) {
  const end = useRef<HTMLDivElement>(null);
  const lastMessageId = messages.at(-1)?.id;
  useEffect(() => {
    // The durable revision (or explicit refresh tick) invalidates this fetched state.
    void lastMessageId;
    end.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [lastMessageId]);
  return (
    <div className="thread-messages">
      {messages.length >= 100 && (
        <button type="button" onClick={onOlder}>
          <Trans>Load earlier messages</Trans>
        </button>
      )}
      {!messages.length && (
        <div className="empty">
          <h2>
            <Trans>A workspace that remembers</Trans>
          </h2>
          <p>
            <Trans>
              Start a conversation. Your agent keeps its memory and continues scheduled work here.
            </Trans>
          </p>
        </div>
      )}
      {messages.map((m) => (
        <MessageBubble
          key={m.id}
          message={m}
          agent={agents.find((a) => a.id === m.agent_id)}
          artifacts={artifacts}
          onReply={onReply}
          onPreview={onPreview}
        />
      ))}
      <div ref={end} />
    </div>
  );
}
