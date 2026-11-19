import { useLingui } from "@lingui/react";
import { ownerProfileLabel, preferenceFieldLabel, preferenceValueText } from "@lonora/core";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { userError } from "../lib/user_error";

type LineChange = { change: "added" | "removed"; text: string };
type FieldChange = { field: string; before: unknown; after: unknown };
export type MemoryRevision = {
  id: string;
  document: "owner_profile" | "owner_preferences" | "agent_memory";
  author: "owner" | "agent" | "system";
  author_agent_name: string | null;
  from_owner_message: boolean;
  change: string;
  created_at: string;
  changes: (LineChange | FieldChange)[];
  changes_truncated: boolean;
};

/** Attributed changes, each with a one-tap undo of that change alone; later ones stay. */
export function MemoryRevisions({
  url,
  revision,
  version,
  onRestored,
}: {
  url: string;
  revision: number;
  version: (document: MemoryRevision["document"]) => number | undefined;
  onRestored: (document: MemoryRevision["document"]) => void;
}) {
  const { i18n } = useLingui();
  const locale = i18n.locale;
  const label = (key: Parameters<typeof ownerProfileLabel>[0]) => ownerProfileLabel(key, locale);
  const [rows, setRows] = useState<MemoryRevision[]>([]);
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState<string | null>(null);
  const [restored, setRestored] = useState<string | null>(null);
  useEffect(() => {
    void revision;
    let live = true;
    void api
      .get<MemoryRevision[]>(url)
      .then((value) => {
        if (live) {
          setRows(value);
          setError(undefined);
        }
      })
      .catch((cause) => {
        if (live) setError(cause);
      });
    return () => {
      live = false;
    };
  }, [url, revision]);
  const author = (row: MemoryRevision) => {
    const who =
      row.author === "owner"
        ? label("byOwner")
        : row.author === "system"
          ? label("bySystem")
          : (row.author_agent_name ?? label("removedAgent"));
    const parts = [who];
    if (row.from_owner_message) parts.push(label("fromYourMessage"));
    if (row.change === "revert") parts.push(label("restoredChange"));
    if (row.change === "restore") parts.push(label("restoredVersion"));
    return parts.join(" · ");
  };
  return (
    <section className="card memory-revisions" aria-label={label("history")}>
      <h3>{label("history")}</h3>
      {error != null && <p role="alert">{userError(error)}</p>}
      {restored && <p role="status">{label("restored")}</p>}
      {rows.length === 0 ? (
        <p className="muted">{label("noHistory")}</p>
      ) : (
        <ol className="revision-list">
          {rows.map((row) => (
            <li key={row.id} data-document={row.document}>
              <p>
                <strong>{author(row)}</strong>{" "}
                <time dateTime={row.created_at}>
                  {new Date(row.created_at).toLocaleString(locale)}
                </time>
              </p>
              <ul className="revision-changes">
                {row.changes.map((item, index) =>
                  "field" in item ? (
                    // biome-ignore lint/suspicious/noArrayIndexKey: changes are positional
                    <li key={index}>
                      {preferenceFieldLabel(item.field, locale) ?? item.field}:{" "}
                      <bdi>{preferenceValueText(item.field, item.before, locale)}</bdi> →{" "}
                      <bdi>{preferenceValueText(item.field, item.after, locale)}</bdi>
                    </li>
                  ) : (
                    // biome-ignore lint/suspicious/noArrayIndexKey: changes are positional
                    <li key={index} data-change={item.change}>
                      <span className="muted">
                        {label(item.change === "added" ? "added" : "removed")}:
                      </span>{" "}
                      <bdi dir="auto">{item.text}</bdi>
                    </li>
                  ),
                )}
                {row.changes_truncated && <li className="muted">{label("more")}</li>}
              </ul>
              <button
                type="button"
                disabled={busy !== null}
                onClick={async () => {
                  setBusy(row.id);
                  setError(undefined);
                  setRestored(null);
                  try {
                    await api.post(`/memory/revisions/${encodeURIComponent(row.id)}/revert`, {
                      version: version(row.document) ?? null,
                    });
                    setRestored(row.id);
                    onRestored(row.document);
                  } catch (cause) {
                    setError(cause);
                  } finally {
                    setBusy(null);
                  }
                }}
              >
                {label(row.document === "owner_preferences" ? "restoreSettings" : "restore")}
              </button>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
