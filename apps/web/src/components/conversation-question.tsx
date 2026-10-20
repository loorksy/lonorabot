import { Trans } from "@lingui/react/macro";
import type { InputAnswer, InputRequest } from "@lonora/contracts";
import { Check } from "lucide-react";
import { useRef, useState } from "react";
import { isRequestCancelled } from "../lib/api";
import { userError } from "../lib/user_error";
import { useClient } from "../providers/ClientProvider";
import "./conversation-question.css";

/** Informational answers use the normal message path, never a financial grant. */
export function ConversationQuestion({
  request,
  onAnswer,
}: {
  request: InputRequest;
  onAnswer: (answer: InputAnswer, label: string, messageId: string) => Promise<void>;
}) {
  const { refresh } = useClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const pending = useRef(false);
  async function answer(choice: InputRequest["choices"][number]) {
    if (pending.current || request.status !== "pending") return;
    pending.current = true;
    setBusy(true);
    setError(undefined);
    try {
      await onAnswer(
        { run_id: request.run_id, question_id: request.id, choice_id: choice.id },
        choice.label,
        request.message_id,
      );
    } catch (cause) {
      if (!isRequestCancelled(cause)) setError(cause);
    } finally {
      pending.current = false;
      setBusy(false);
      refresh();
    }
  }
  return (
    <section
      className="conversation-question"
      data-question-id={request.id}
      aria-label={request.question}
    >
      <p className="conversation-question-title" dir="auto">
        {request.question}
      </p>
      <div className="conversation-question-options">
        {request.choices.map((choice, index) => (
          <button
            key={choice.id}
            type="button"
            disabled={busy || request.status !== "pending"}
            aria-pressed={request.selected_choice_id === choice.id}
            onClick={() => void answer(choice)}
          >
            <span className="conversation-question-letter" aria-hidden="true">
              {String.fromCharCode(65 + index)}
            </span>
            <span dir="auto">{choice.label}</span>
            {request.selected_choice_id === choice.id && <Check size={18} aria-hidden="true" />}
          </button>
        ))}
      </div>
      <span className="conversation-question-status" role="status">
        {request.status === "pending" ? (
          <Trans>Choose an option</Trans>
        ) : request.status === "answered" ? (
          <Trans>Answered</Trans>
        ) : (
          <Trans>Question closed</Trans>
        )}
      </span>
      {error != null && <p role="alert">{userError(error)}</p>}
    </section>
  );
}
