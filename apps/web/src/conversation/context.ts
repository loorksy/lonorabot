import { type MessageReaction, REACTION_EMOJIS, type VisualAction } from "@lonora/contracts";
import { createContext, useContext } from "react";
import type { Agent, Message, Resource } from "../lib/api";

/** The six fixed quick reactions (Q28). */
export const REACTIONS = REACTION_EMOJIS;

export type { CallPart, VoicePart } from "@lonora/contracts";
export type { MessageReaction };
/** Message fields phase 3 adds on the server (WP-D, WP-E), read defensively. */
export type ConversationMessage = Message & {
  /** The generative-UI submit origin (T1, GENUI_PLAN §8.4). */
  origin?: string | null;
};

export function partsOf(message: Message): Array<{ type: string } & Record<string, unknown>> {
  const parts = (message.rich_content as { parts?: unknown } | null | undefined)?.parts;
  return Array.isArray(parts) ? (parts as Array<{ type: string } & Record<string, unknown>>) : [];
}
export { callPart, voicePart } from "@lonora/core";

/** HH:mm in Latin digits, as the reference's meta row. */
export const clock = (iso: string | Date) =>
  new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });

/** Agent colours name speakers; darkened in light mode for contrast (reference senderInfo). */
export function agentColor(agent?: Agent | null) {
  const c = agent?.color;
  return /^#[0-9a-f]{6}$/i.test(c || "") ? (c as string) : "#7c83fd";
}
export function speakerColor(agent: Agent | undefined, light: boolean) {
  const c = agentColor(agent);
  return light ? `color-mix(in srgb,${c} 62%,#000)` : c;
}

export type ConversationApi = {
  threadId: string;
  ownerId: string;
  /** v1 rich responses: a stored message's previous preview id (keeps its local state). */
  previousVisualIds: Map<string, string>;
  onVisualAction: (action: VisualAction) => Promise<void>;
  /** The direct chat's agent; empty in a group. */
  threadAgentId: string;
  isGroup: boolean;
  agents: Agent[];
  light: boolean;
  mentions: RegExp | null;
  artifacts: Map<string, Resource>;
  byId: Map<string, ConversationMessage>;
  onReply: (message: Message) => void;
  onEdit: (message: Message) => void;
  onReact: (message: Message, emoji: string | null) => void;
  onRetry: (nonce: string) => void;
  onDrop: (nonce: string) => void;
  onJump: (messageId: string) => void;
  onOpenImage: (artifact: Resource) => void;
  onOpenFile: (artifact: Resource) => void;
  onMenu: (message: ConversationMessage, anchor: HTMLElement) => void;
  onReactPicker: (message: ConversationMessage, anchor: HTMLElement) => void;
  onReactionList: (message: ConversationMessage, anchor: HTMLElement) => void;
  onCall: () => void;
};

export const ConversationContext = createContext<ConversationApi | null>(null);
export function useConversation() {
  const value = useContext(ConversationContext);
  if (!value) throw new Error("conversation_context_missing");
  return value;
}
