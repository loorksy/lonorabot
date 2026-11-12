/** What a lonora-ui v2 card needs from its conversation (the mobile twin of the web
 * `GenuiHost`): the thread's messages, Runs and agents for its lock, its never-run marks and
 * whether a send may go now, and the thread's own submit, so the accepted submission joins
 * the conversation like any message the owner sends. */
import type { Agent, Message, Run, UiSubmitInput } from "@lonora/contracts";
import { createContext, type ReactNode, useContext } from "react";

export type CardSubmit = { content: ""; client_nonce: string; ui_submit: UiSubmitInput };

export type CardHostValue = {
  threadId: string;
  messages: readonly Message[];
  runs: readonly Run[];
  agents: readonly Agent[];
  /** Posts a card submission to the thread and merges what the server accepted. */
  submit: (body: CardSubmit) => Promise<void>;
  /** Reads one message again by its place in the thread (after «تعديل»: its card state),
   * wherever it sits in the history, and merges it. */
  reread: (message: Message) => Promise<void>;
};

const Host = createContext<CardHostValue | null>(null);

export function CardHost({ value, children }: { value: CardHostValue; children: ReactNode }) {
  return <Host.Provider value={value}>{children}</Host.Provider>;
}

export function useCardHost(): CardHostValue | null {
  return useContext(Host);
}
