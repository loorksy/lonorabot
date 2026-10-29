import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { Payload, Resource } from "@lonora/contracts";
import { useEffect, useMemo, useState } from "react";
import { resources } from "../lib/rpc";
import { userError } from "../lib/user_error";
import { useClient } from "../providers/ClientProvider";

// Skills and scratchpad share versioned resource editing, with distinct real API paths.
export function ScratchpadSection({
  agentId,
  kind,
}: {
  agentId: string;
  kind: "skills" | "scratchpad";
}) {
  const { revision, refresh } = useClient();
  const service = useMemo(() => resources(kind === "skills" ? "/skills" : "/scratchpad"), [kind]);
  const [rows, setRows] = useState<Resource[] | null>(null);
  const [error, setError] = useState<unknown>();
  useEffect(() => {
    void revision;
    let live = true;
    void service
      .list(agentId)
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
  }, [agentId, revision, service]);
  const [title, setTitle] = useState("");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <>
      {error != null && <p role="alert">{userError(error)}</p>}
      <form
        className="card"
        onSubmit={async (event) => {
          event.preventDefault();
          setBusy(true);
          setError(undefined);
          try {
            await service.create(
              kind === "skills"
                ? { name: title.trim(), content: draft, enabled: true }
                : { title: title.trim(), content: draft },
              agentId,
            );
            setTitle("");
            setDraft("");
            refresh();
          } catch (cause) {
            setError(cause);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          <Trans>Title</Trans>
          <input
            required
            maxLength={80}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
        </label>
        <label>
          <Trans>Content</Trans>
          <textarea
            aria-label={t`Content`}
            required
            rows={5}
            maxLength={16000}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
          />
        </label>
        <button type="submit" disabled={busy || !title.trim()}>
          <Trans>Add</Trans>
        </button>
      </form>
      {rows === null && !error ? (
        <p role="status">
          <Trans>Loading…</Trans>
        </p>
      ) : (
        rows?.map((row) => (
          <KnowledgeItem
            key={`${row.id}:${row.version}`}
            row={row}
            skills={kind === "skills"}
            onSave={async (payload) => {
              await service.update(row, payload);
              refresh();
            }}
            onDelete={async () => {
              await service.delete(row.id);
              refresh();
            }}
          />
        ))
      )}
    </>
  );
}
function KnowledgeItem({
  row,
  skills,
  onSave,
  onDelete,
}: {
  row: Resource;
  skills: boolean;
  onSave: (payload: Payload) => Promise<void>;
  onDelete: () => Promise<void>;
}) {
  const [title, setTitle] = useState(String(row.payload.name ?? row.payload.title ?? ""));
  const [content, setContent] = useState(String(row.payload.content ?? ""));
  const [enabled, setEnabled] = useState(row.payload.enabled !== false);
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  async function act(action: () => Promise<void>) {
    setBusy(true);
    setError(undefined);
    try {
      await action();
    } catch (cause) {
      setError(cause);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="card">
      <summary>{String(row.payload.name ?? row.payload.title ?? "")}</summary>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void act(() =>
            onSave({
              ...row.payload,
              [skills ? "name" : "title"]: title.trim(),
              content,
              ...(skills ? { enabled } : {}),
            }),
          );
        }}
      >
        <label>
          <Trans>Title</Trans>
          <input
            required
            maxLength={80}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
        </label>
        <label>
          <Trans>Content</Trans>
          <textarea
            aria-label={t`Content`}
            required
            rows={5}
            maxLength={16000}
            value={content}
            onChange={(event) => setContent(event.target.value)}
          />
        </label>
        {skills && (
          <label className="check">
            <input
              type="checkbox"
              role="switch"
              data-lonora-switch="true"
              aria-checked={enabled}
              checked={enabled}
              onChange={(event) => setEnabled(event.target.checked)}
            />
            <Trans>Enabled</Trans>
          </label>
        )}
        {error != null && <p role="alert">{userError(error)}</p>}
        <div className="actions">
          <button type="submit" disabled={busy}>
            <Trans>Save</Trans>
          </button>
          <button
            type="button"
            className="danger"
            disabled={busy}
            onClick={() => void act(onDelete)}
          >
            <Trans>Delete</Trans>
          </button>
        </div>
      </form>
    </details>
  );
}
