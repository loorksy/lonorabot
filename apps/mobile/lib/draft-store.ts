/**
 * Composer drafts on the device, as Web keeps them (localStorage `lonora:composer:v1:`): the
 * text, the finished attachments and the reply of each conversation survive an app restart.
 * Scoped by the draft key (server, owner, conversation); running uploads are never saved (a
 * picked file's bytes cannot be). Sign-out removes every saved draft.
 */
import type { Artifact, Message } from "@lonora/contracts";
import { Platform } from "react-native";
import { composerDraft, editComposerDraft, subscribeDrafts } from "./composer-drafts";
import { registerSessionTeardown } from "./session-lifecycle";

type Saved = { key: string; text: string; attachments: Artifact[]; reply: Message | null };
const PREFIX = "lonora.draft.v1:";
const DIRECTORY = "lonora-drafts";
const MAX_BYTES = 256 * 1024;
let generation = 0;
const writes = new Map<string, Promise<void>>();
const timers = new Map<string, ReturnType<typeof setTimeout>>();
// Conversations whose composer holds an edit (Q21): its text is never saved, so a restart
// cannot leave it behind as a new message.
const editing = new Set<string>();
export function markEditing(key: string, on: boolean) {
  if (on) editing.add(key);
  else editing.delete(key);
  scheduleDraftSave(key);
}

function filename(key: string) {
  let first = 2166136261,
    second = 2654435769;
  for (const char of key) {
    first = Math.imul(first ^ char.charCodeAt(0), 16777619);
    second = Math.imul(second ^ char.charCodeAt(0), 2246822507);
  }
  return `${(first >>> 0).toString(16)}-${(second >>> 0).toString(16)}.json`;
}
async function nativeFile(key: string) {
  const { Directory, File, Paths } = await import("expo-file-system");
  const directory = new Directory(Paths.document, DIRECTORY);
  return { directory, file: new File(directory, filename(key)) };
}
async function read(key: string): Promise<string | null> {
  if (Platform.OS === "web") return globalThis.localStorage?.getItem(PREFIX + key) ?? null;
  const { file } = await nativeFile(key);
  return file.exists ? await file.text() : null;
}
async function write(key: string, raw: string | null) {
  if (Platform.OS === "web") {
    if (raw === null) globalThis.localStorage?.removeItem(PREFIX + key);
    else globalThis.localStorage?.setItem(PREFIX + key, raw);
    return;
  }
  const { directory, file } = await nativeFile(key);
  if (raw === null) {
    if (file.exists) file.delete();
    return;
  }
  directory.create({ intermediates: true, idempotent: true });
  file.write(raw);
}

/** Writes the conversation's current draft; an empty draft removes the saved one. */
export function saveDraft(key: string): Promise<void> {
  const epoch = generation;
  const next = (writes.get(key) ?? Promise.resolve())
    .catch(() => undefined)
    .then(async () => {
      if (epoch !== generation) return;
      const { attachments, reply } = composerDraft(key);
      const text = editing.has(key) ? "" : composerDraft(key).text;
      const empty = !text && !attachments.length && !reply;
      const raw = empty ? null : JSON.stringify({ key, text, attachments, reply } satisfies Saved);
      if (raw && raw.length > MAX_BYTES) return;
      await write(key, raw);
    })
    .catch(() => undefined);
  writes.set(key, next);
  return next;
}
/** Saves shortly after the last change, so typing writes once per pause. */
export function scheduleDraftSave(key: string) {
  clearTimeout(timers.get(key));
  timers.set(
    key,
    setTimeout(() => {
      timers.delete(key);
      void saveDraft(key);
    }, 400),
  );
}

const isArtifact = (value: unknown): value is Artifact =>
  Boolean(value && typeof value === "object" && typeof (value as Artifact).id === "string");
/**
 * Brings a saved draft back when the conversation opens. A draft typed since (anything in
 * memory) is never overwritten. Returns whether a draft was restored.
 */
export async function restoreDraft(key: string): Promise<boolean> {
  const epoch = generation;
  let saved: Saved;
  try {
    const raw = await read(key);
    if (!raw || raw.length > MAX_BYTES || epoch !== generation) return false;
    saved = JSON.parse(raw);
  } catch {
    return false;
  }
  const current = composerDraft(key);
  if (current.text || current.attachments.length || current.reply) return false;
  if (
    !saved ||
    saved.key !== key ||
    typeof saved.text !== "string" ||
    saved.text.length > 30000 ||
    !Array.isArray(saved.attachments) ||
    !saved.attachments.every(isArtifact) ||
    saved.attachments.length > 10 ||
    !(saved.reply === null || isArtifact(saved.reply))
  )
    return false;
  editComposerDraft(key, {
    text: saved.text,
    attachments: saved.attachments,
    reply: saved.reply as Message | null,
  });
  return true;
}

subscribeDrafts(scheduleDraftSave);
registerSessionTeardown(async () => {
  generation += 1;
  editing.clear();
  for (const timer of timers.values()) clearTimeout(timer);
  timers.clear();
  await Promise.allSettled([...writes.values()]);
  writes.clear();
  if (Platform.OS === "web") {
    const storage = globalThis.localStorage;
    if (!storage) return;
    const names: string[] = [];
    for (let index = 0; index < storage.length; index++) {
      const name = storage.key(index);
      if (name?.startsWith(PREFIX)) names.push(name);
    }
    for (const name of names) storage.removeItem(name);
  } else {
    const { Directory, Paths } = await import("expo-file-system");
    const directory = new Directory(Paths.document, DIRECTORY);
    if (directory.exists) directory.delete();
  }
});
