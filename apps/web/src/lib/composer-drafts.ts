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

/** A file on its way to the server: in the composer's tray, or in a bubble once sent. */
export type DraftUpload = {
  id: string;
  name: string;
  size: number;
  media_type: string;
  /** A picture's local address while it uploads. */
  preview?: string;
  /** How much has been sent, 0 to 1. */
  p: number;
  done: Promise<Resource>;
  cancel: () => void;
  /** Taken by a sent message: the file no longer returns to the draft. */
  sent: boolean;
};
const uploads = new Map<string, DraftUpload[]>();
const uploadListeners = new Map<string, Set<() => void>>();
const NONE: readonly DraftUpload[] = [];
/** The uploads of a draft that are still running; a new list whenever one moves. */
export const draftUploads = (key: string): readonly DraftUpload[] => uploads.get(key) ?? NONE;
export const pendingDraftUploads = (key: string) => draftUploads(key).length;
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
function setUploads(key: string, list: DraftUpload[]) {
  if (list.length) uploads.set(key, list);
  else uploads.delete(key);
  notifyDraftUpload(key);
}
/**
 * Starts an upload for a draft. `run` does the transfer, reporting progress and stopping
 * when its signal aborts. A finished file joins the draft, even after the composer has
 * gone, unless a sent message took the upload first.
 */
export function trackDraftUpload(
  key: string,
  file: File,
  run: (progress: (p: number) => void, signal: AbortSignal) => Promise<Resource>,
  moved: () => void = () => {},
): DraftUpload {
  const controller = new AbortController();
  const settled = () => {
    if (upload.preview) URL.revokeObjectURL(upload.preview);
    setUploads(
      key,
      draftUploads(key).filter((item) => item !== upload),
    );
  };
  const upload: DraftUpload = {
    id: crypto.randomUUID(),
    name: file.name,
    size: file.size,
    media_type: file.type,
    preview: file.type.startsWith("image/") ? URL.createObjectURL(file) : undefined,
    p: 0,
    sent: false,
    cancel: () => controller.abort(),
    done: run((p) => {
      upload.p = p;
      // A new list, so a reader that compares lists sees the progress.
      if (!upload.sent) setUploads(key, [...draftUploads(key)]);
      moved();
    }, controller.signal).then(
      (row) => {
        settled();
        if (!upload.sent) appendDraftFiles(key, [row]);
        return row;
      },
      (cause) => {
        settled();
        throw cause;
      },
    ),
  };
  setUploads(key, [...draftUploads(key), upload]);
  return upload;
}
/** The draft's running uploads, handed to the message being sent. */
export function takeDraftUploads(key: string): DraftUpload[] {
  const taken = [...draftUploads(key)];
  for (const upload of taken) upload.sent = true;
  if (taken.length) setUploads(key, []);
  return taken;
}
export function appendDraftFiles(key: string, files: Resource[]) {
  const draft = readComposerDraft(key);
  const byId = new Map([...draft.files, ...files].map((file) => [file.id, file]));
  saveComposerDraft(key, { ...draft, files: [...byId.values()] });
  notifyDraftUpload(key);
}
