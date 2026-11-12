// The composer's running uploads, as on Web: each picked file uploads on its own with its
// progress and a cancel. A finished file joins the conversation's draft attachments; files
// handed to a message sent before they finished settle on that message instead.
import type { Artifact } from "@lonora/contracts";
import { composerDraft, editComposerDraft } from "./composer-drafts";
import { registerSessionTeardown } from "./session-lifecycle";

export type PickedFile = { name: string; size: number; media_type: string };
export type ComposerUpload = PickedFile & {
  id: string;
  /** 0..1 */
  p: number;
  /** Handed to a sent message: its file no longer joins the draft. */
  sent: boolean;
  /** The uploaded file, once it is up. */
  result?: Artifact;
  cancel: () => void;
  done: Promise<Artifact>;
};
type Transfer = (progress: (p: number) => void, signal: AbortSignal) => Promise<Artifact>;

const running = new Map<string, ComposerUpload[]>();
const listeners = new Set<() => void>();
const none: ComposerUpload[] = [];
// Per conversation: a file's progress re-renders only its own conversation.
const versions = new Map<string, number>();

function moved(key: string) {
  versions.set(key, (versions.get(key) ?? 0) + 1);
  for (const listener of listeners) listener();
}
function set(key: string, rows: ComposerUpload[]) {
  if (rows.length) running.set(key, rows);
  else running.delete(key);
  moved(key);
}
export const composerUploads = (key: string): ComposerUpload[] => running.get(key) ?? none;
export const uploadsVersion = (key: string) => versions.get(key) ?? 0;
export function subscribeUploads(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function startUpload(key: string, file: PickedFile, transfer: Transfer): ComposerUpload {
  const controller = new AbortController();
  const upload: ComposerUpload = {
    ...file,
    id: crypto.randomUUID(),
    p: 0,
    sent: false,
    cancel: () => controller.abort(),
    done: Promise.resolve(null as unknown as Artifact),
  };
  const leave = () =>
    set(
      key,
      composerUploads(key).filter((row) => row !== upload),
    );
  upload.done = transfer((p) => {
    upload.p = p;
    // A new list, so a reader that compares lists sees the progress; a sent message's ring
    // reads the version.
    if (!upload.sent) set(key, [...composerUploads(key)]);
    else moved(key);
  }, controller.signal).then(
    (row) => {
      upload.result = row;
      leave();
      if (!upload.sent)
        editComposerDraft(key, { attachments: [...composerDraft(key).attachments, row] });
      return row;
    },
    (cause) => {
      leave();
      throw cause;
    },
  );
  // A cancelled or failed upload is reported by its caller; nothing is left unhandled here.
  upload.done.catch(() => undefined);
  set(key, [...composerUploads(key), upload]);
  return upload;
}

export function cancelUpload(key: string, id: string) {
  composerUploads(key)
    .find((row) => row.id === id)
    ?.cancel();
}

/** A send that could not be admitted gives its running uploads back to the composer. */
export function handBack(key: string, rows: readonly ComposerUpload[]) {
  const back = rows.filter((row) => row.sent);
  for (const row of back) row.sent = false;
  const finished = back.flatMap((row) => (row.result ? [row.result] : []));
  if (finished.length)
    editComposerDraft(key, { attachments: [...composerDraft(key).attachments, ...finished] });
  const running = back.filter((row) => !row.result);
  if (running.length) set(key, [...composerUploads(key), ...running]);
  else if (finished.length) moved(key);
}
/** Send while files upload: the running uploads move to the message; the composer is clear. */
export function handOver(key: string): ComposerUpload[] {
  const rows = composerUploads(key);
  for (const row of rows) row.sent = true;
  set(key, []);
  return rows;
}

registerSessionTeardown(async () => {
  for (const rows of running.values()) for (const row of rows) row.cancel();
  running.clear();
  for (const key of [...versions.keys()]) moved(key);
});
