import { Trans } from "@lingui/react/macro";
import type { Message } from "../../lib/api";
export function Transcript({ messages }: { messages: Message[] }) {
  return (
    <details>
      <summary>
        <Trans>Conversation transcript</Trans>
      </summary>
      {messages.slice(-8).map((m) => (
        <p key={m.id} dir="auto">
          {m.content}
        </p>
      ))}
    </details>
  );
}
