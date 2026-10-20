import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { AgentSkill, Resource } from "@lonora/contracts";
import { useState } from "react";
import { api, isRequestCancelled } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { SEMVER, useAlive } from "./shared";

export function SkillEditor({
  row,
  onChanged,
  onSaved,
  onDeleted,
  onReload,
}: {
  row: Resource<AgentSkill>;
  onChanged: () => void;
  onSaved: (row: Resource<AgentSkill>) => void;
  onDeleted: () => void;
  onReload: () => void;
}) {
  const live = useAlive();
  const [content, setContent] = useState(row.payload.content);
  const [version, setVersion] = useState(row.payload.manifest?.version ?? "");
  const [enabled, setEnabled] = useState(row.payload.enabled !== false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [saved, setSaved] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  return (
    <form
      className="skill-editor"
      onSubmit={async (event) => {
        event.preventDefault();
        if (busy) return;
        setBusy(true);
        setError(undefined);
        try {
          const payload: AgentSkill = { ...row.payload, content, enabled };
          if (row.payload.manifest) payload.manifest = { ...row.payload.manifest, version };
          const result = await api.put<Resource<AgentSkill>>(
            `/skills/${encodeURIComponent(row.id)}`,
            { payload, version: row.version },
          );
          if (live.current) {
            onSaved(result);
            setSaved(true);
            onChanged();
          }
        } catch (cause) {
          if (live.current && !isRequestCancelled(cause)) setError(cause);
        } finally {
          if (live.current) setBusy(false);
        }
      }}
    >
      {row.payload.manifest && (
        <label>
          <Trans>Instruction version</Trans>
          <input
            dir="ltr"
            required
            maxLength={64}
            pattern={SEMVER}
            value={version}
            onChange={(event) => {
              setVersion(event.target.value);
              setSaved(false);
            }}
          />
        </label>
      )}
      <label>
        <Trans>Content</Trans>
        <textarea
          aria-label={t`Content`}
          dir="auto"
          required
          maxLength={16000}
          rows={7}
          value={content}
          onChange={(event) => {
            setContent(event.target.value);
            setSaved(false);
          }}
        />
      </label>
      <label className="check">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(event) => {
            setEnabled(event.target.checked);
            setSaved(false);
          }}
        />
        <Trans>Enabled</Trans>
      </label>
      <p className="muted">
        <Trans>
          Existing tasks keep pinned instructions. Disabling a skill prevents its use at the next
          runtime boundary.
        </Trans>
      </p>
      {error != null && (
        <div role="alert">
          <p>{userError(error)}</p>
          <button type="button" disabled={busy} onClick={onReload}>
            <Trans>Reload</Trans>
          </button>
        </div>
      )}
      <div className="actions">
        {saved && (
          <span role="status">
            <Trans>Saved</Trans>
          </span>
        )}
        <button type="submit" disabled={busy || confirmDelete}>
          <Trans>Save</Trans>
        </button>
        <button
          type="button"
          className="danger"
          disabled={busy}
          onClick={() => setConfirmDelete(true)}
        >
          <Trans>Delete</Trans>
        </button>
      </div>
      {confirmDelete && (
        <div className="skill-delete-confirm">
          <p>
            <Trans>Delete these owner instructions? Existing version blocks will remain.</Trans>
          </p>
          <div className="actions">
            <button type="button" disabled={busy} onClick={() => setConfirmDelete(false)}>
              <Trans>Cancel</Trans>
            </button>
            <button
              type="button"
              className="danger"
              disabled={busy}
              onClick={async () => {
                if (busy) return;
                setBusy(true);
                setError(undefined);
                try {
                  await api.delete(`/skills/${encodeURIComponent(row.id)}`);
                  if (live.current) onDeleted();
                } catch (cause) {
                  if (live.current && !isRequestCancelled(cause)) setError(cause);
                } finally {
                  if (live.current) setBusy(false);
                }
              }}
            >
              <Trans>Delete owner instructions</Trans>
            </button>
          </div>
        </div>
      )}
    </form>
  );
}
