/** Recoverable owner/thread-scoped drafts, never canonical conversation history. */
import type { MentionRange } from "@lonora/core";
import type { Message, Resource } from "./api";

export type ComposerDraft = {
  text: string;
  files: Resource[];
  mentions: MentionRange[];
  reply: Message | null;
};
const prefix = "lonora:composer:v1:";
const drafts = new Map<string, ComposerDraft>();
export const draftKey = (ownerId: string, threadId: string) =>
  prefix + JSON.stringify([ownerId, threadId]);
const empty = (): ComposerDraft => ({ text: "", files: [], mentions: [], reply: null });
export function readComposerDraft(key: string): ComposerDraft {
  const current = drafts.get(key);
  if (current) return current;
  try {
    const value = JSON.parse(localStorage.getItem(key) ?? "null") as ComposerDraft | null;
    if (
      value &&
      typeof value.text === "string" &&
      value.text.length <= 60000 &&
      Array.isArray(value.files) &&
      value.files.length <= 100 &&
      value.files.every((file) => typeof file.id === "string" && !!file.payload) &&
      Array.isArray(value.mentions) &&
      value.mentions.length <= 100 &&
      (value.reply === null ||
        (typeof value.reply?.id === "string" && typeof value.reply.content === "string"))
    ) {
      drafts.set(key, value);
      return value;
    }
  } catch {
    /* Memory-only drafts remain available when browser storage is denied. */
  }
  return empty();
}
export function saveComposerDraft(key: string, draft: ComposerDraft) {
  drafts.set(key, draft);
  try {
    if (draft.text || draft.files.length || draft.reply)
      localStorage.setItem(key, JSON.stringify(draft));
    else localStorage.removeItem(key);
  } catch {
    /* A blocked/full storage never prevents composing or sending. */
  }
}
if (typeof window !== "undefined")
  window.addEventListener("lonora:session-reset", () => {
    drafts.clear();
    try {
      for (const key of Object.keys(localStorage))
        if (key.startsWith(prefix)) localStorage.removeItem(key);
    } catch {
      /* Storage may be disabled. */
    }
  });

const uploadCounts = new Map<string, number>();
const uploadListeners = new Map<string, Set<() => void>>();
export const pendingDraftUploads = (key: string) => uploadCounts.get(key) ?? 0;
export function observeDraftUploads(key: string, listener: () => void) {
  const listeners = uploadListeners.get(key) ?? new Set();
  listeners.add(listener);
  uploadListeners.set(key, listeners);
  return () => {
    listeners.delete(listener);
  };
}
function notifyDraftUpload(key: string) {
  for (const listener of uploadListeners.get(key) ?? []) listener();
}
export function startDraftUpload(key: string) {
  uploadCounts.set(key, pendingDraftUploads(key) + 1);
  notifyDraftUpload(key);
}
export function finishDraftUpload(key: string) {
  uploadCounts.set(key, Math.max(0, pendingDraftUploads(key) - 1));
  notifyDraftUpload(key);
}
export function appendDraftFiles(key: string, files: Resource[]) {
  const draft = readComposerDraft(key);
  const byId = new Map([...draft.files, ...files].map((file) => [file.id, file]));
  saveComposerDraft(key, { ...draft, files: [...byId.values()] });
  notifyDraftUpload(key);
}
