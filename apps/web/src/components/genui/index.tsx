/** The single mount point of lonora-ui v2 cards in the message renderer (GENUI_PLAN §2.4).
 *
 * The renderer calls `renderUiPart(part, index, host)` for every rich part; it returns the
 * lazily loaded `<UiCard/>` for a v2 card and null for anything else (text and stored v1
 * parts keep their own renderer). The conversation provides `GenuiHost` once around its
 * message list, so the card can read the thread's messages, Runs and agents for its lock,
 * its never-run marks and whether a send may go now.
 */
import { t } from "@lingui/core/macro";
import type { Agent, Message, Run, VisualResponsePart } from "@lonora/contracts";
import { isUiPart, submitMark } from "@lonora/core";
import { createContext, lazy, type ReactNode, Suspense, useContext } from "react";

const UiCard = lazy(() => import("./UiCard"));

export type GenuiHostValue = {
  threadId: string;
  messages: readonly Message[];
  runs: readonly Run[];
  agents: readonly Agent[];
};
const Host = createContext<GenuiHostValue | null>(null);

export function GenuiHost({ value, children }: { value: GenuiHostValue; children: ReactNode }) {
  return <Host.Provider value={value}>{children}</Host.Provider>;
}

export function useGenuiHost(): GenuiHostValue | null {
  return useContext(Host);
}

/** Where the card sits: its message (a real id once committed, `preview:<run>` while it
 * streams), the thread and the agent that wrote it. */
export type UiPartHost = {
  messageId: string;
  threadId: string;
  agentId?: string | null;
};

export function renderUiPart(
  part: VisualResponsePart,
  index: number,
  host: UiPartHost,
): ReactNode | null {
  if (!isUiPart(part)) return null;
  return (
    <Suspense key={`ui:${index}`} fallback={null}>
      <UiCard part={part} index={index} host={host} />
    </Suspense>
  );
}

/** The reference's message note slot (Desktop-37:3798) on a card's send whose Run never
 * started (rule N): «مُعدّلة» after «تعديل», «لم يُنفَّذ» otherwise. */
export function SubmitMark({ message }: { message: Message }) {
  const host = useGenuiHost();
  const mark = host ? submitMark(message, host.runs) : (message.ui_mark ?? null);
  if (!mark) return null;
  return (
    <span className="template-message-note" data-ui-mark={mark}>
      {mark === "superseded" ? t`Edited` : t`Not carried out`}
    </span>
  );
}
