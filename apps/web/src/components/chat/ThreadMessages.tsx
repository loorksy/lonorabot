// Adapted from Tampletgrok's ThreadView follow-tail and transcript framing; Apache-2.0.
import { t } from "@lingui/core/macro";
import { Trans, useLingui } from "@lingui/react/macro";
import { ArrowDown, LoaderCircle, Sparkles } from "lucide-react";
import { Fragment, type ReactNode, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { Agent, Message, Resource } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { MessageBubble } from "./MessageBubble";

export function ThreadMessages({
  messages,
  agents,
  artifacts,
  onReply,
  onPreview,
  onOlder,
  trailing,
}: {
  messages: Message[];
  agents: Agent[];
  artifacts: Resource[];
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
    setAtEnd(element.scrollHeight - element.clientHeight - element.scrollTop < 80);
  }, [messages]);

  useEffect(() => {
    const transcript = content.current;
    if (!transcript) return;
    const observer = new ResizeObserver(() => {
      const element = scroll.current;
      if (!element) return;
      if (following.current) element.scrollTop = element.scrollHeight;
      previous.current.height = element.scrollHeight;
      setAtEnd(element.scrollHeight - element.clientHeight - element.scrollTop < 80);
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
          const nearEnd = element.scrollHeight - element.clientHeight - element.scrollTop < 80;
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
          {!messages.length && (
            <div className="empty template-thread-empty">
              <div className="template-empty-glyph">
                <Sparkles size={30} strokeWidth={1.2} />
              </div>
              <h2>
                <Trans>A workspace that remembers</Trans>
              </h2>
              <p>
                <Trans>
                  Start a conversation. Your agent keeps its memory and continues scheduled work
                  here.
                </Trans>
              </p>
            </div>
          )}
          {messages.map((message, index) => {
            const previousMessage = messages[index - 1];
            const day = new Date(message.created_at).toDateString();
            const separator =
              !previousMessage || new Date(previousMessage.created_at).toDateString() !== day;
            return (
              <Fragment key={message.id}>
                {separator && (
                  <div className="template-time-separator">
                    <time dateTime={message.created_at}>
                      {new Date(message.created_at).toLocaleDateString(i18n.locale, {
                        day: "numeric",
                        month: "short",
                        year: "numeric",
                      })}
                    </time>
                  </div>
                )}
                <MessageBubble
                  message={message}
                  agent={agents.find((agent) => agent.id === message.agent_id)}
                  artifacts={artifacts}
                  replyParent={message.reply_to ? byId.get(message.reply_to) : undefined}
                  onReply={onReply}
                  onPreview={onPreview}
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
