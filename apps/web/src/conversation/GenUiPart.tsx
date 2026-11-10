import { Trans } from "@lingui/react/macro";
import { RichResponse } from "../components/visual/RichResponse";
import type { Message } from "../lib/api";
import { partsOf, useConversation } from "./context";

/* THE single mount point for generated interfaces inside a message (track T1 fills it with the
   lonora-ui v2 renderer as a lazy chunk). Until then today's v1 rich responses render here,
   read-only as they are. A message whose rich_content carries a `ui` part is a ui message. */

export const hasGenUi = (message: Message) => partsOf(message).some((part) => part.type === "ui");

export function GenUiPart({ message, live }: { message: Message; live: boolean }) {
  const ctx = useConversation();
  return (
    <div
      className="ui-lead"
      data-live={live || undefined}
      data-visual-previous={ctx.previousVisualIds.get(message.id)}
    >
      <RichResponse
        content={message.rich_content}
        fallback={message.content}
        ownerId={ctx.ownerId}
        threadId={message.thread_id}
        messageId={message.id}
        previousMessageId={ctx.previousVisualIds.get(message.id)}
        artifacts={[...ctx.artifacts.values()]}
        onAction={ctx.onVisualAction}
      />
    </div>
  );
}

/** The quoted owner bubble of a card submit (origin "ui_submit"; T1 owns its v2 look). */
export function GenUiSubmitQuote({ message }: { message: Message }) {
  return (
    <span className="text">
      <span className="cmd-chip">
        <Trans>Interface</Trans>
      </span>{" "}
      {message.content}
    </span>
  );
}
