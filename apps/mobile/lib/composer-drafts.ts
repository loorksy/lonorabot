import type { Artifact, Message } from "@lonora/contracts";
import { registerSessionTeardown } from "./session-lifecycle";

export type ComposerDraft = {
  text: string;
  attachments: Artifact[];
  reply: Message | null;
  revision: number;
};
const empty: ComposerDraft = { text: "", attachments: [], reply: null, revision: 0 };
const drafts = new Map<string, ComposerDraft>();

/** Unsent input survives navigation, scoped to the same server, owner and conversation. */
export function composerDraft(key: string): ComposerDraft {
  return drafts.get(key) ?? empty;
}
export function editComposerDraft(key: string, patch: Partial<Omit<ComposerDraft, "revision">>) {
  const previous = composerDraft(key);
  const next = { ...previous, ...patch, revision: previous.revision + 1 };
  drafts.set(key, next);
  return next;
}

/** A completed local enqueue cannot erase input typed while storage was being written. */
export function consumeComposerDraft(key: string, revision: number): ComposerDraft {
  const current = composerDraft(key);
  if (current.revision !== revision) return current;
  const next = { ...empty, revision: revision + 1 };
  drafts.set(key, next);
  return next;
}

registerSessionTeardown(async () => drafts.clear());
