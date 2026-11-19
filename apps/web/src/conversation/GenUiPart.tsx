import { Trans } from "@lingui/react/macro";
import { RichResponse } from "../components/visual/RichResponse";
import type { Message } from "../lib/api";
import { partsOf, useConversation } from "./context";

/* THE single mount point for generated interfaces inside a message: RichResponse draws each
   v2 card through `renderUiPart` (the lazily loaded `UiCard`) and a stored v1 part through its
   own read-only renderer (docs/genui.md). A message whose rich_content carries a `ui` part is a
   ui message. */

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

/** The quoted owner bubble of a card submit (origin "ui_submit", docs/genui.md §7). */
export function GenUiSubmitQuote({ message }: { message: Message }) {
  return (
    <span className="text">
      <span className="cmd-chip">
        <Trans>Interface</Trans>
      </span>{" "}
      <span>{message.content}</span>
    </span>
  );
}
