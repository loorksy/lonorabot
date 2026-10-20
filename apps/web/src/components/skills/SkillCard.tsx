import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type {
  AgentSkill,
  Resource,
  SkillCatalogDetail,
  SkillCatalogEntry,
} from "@lonora/contracts";
import { useState } from "react";
import { api, isRequestCancelled } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { SkillEditor } from "./SkillEditor";
import { SkillMetadata } from "./SkillMetadata";
import { sourceLabel, statusLabel, useAlive } from "./shared";

export function SkillCard({
  item,
  path,
  revoked,
  canRevoke,
  onRevoke,
  onChanged,
}: {
  item: SkillCatalogEntry;
  path: string;
  revoked: boolean;
  canRevoke: boolean;
  onRevoke: (version: string) => Promise<void>;
  onChanged: () => void;
}) {
  const live = useAlive();
  const [detail, setDetail] = useState<SkillCatalogDetail | null>(null);
  const [resource, setResource] = useState<Resource<AgentSkill> | null>(null);
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const available = item.available && !revoked;
  const load = async () => {
    if (busy) return;
    setBusy(true);
    setError(undefined);
    try {
      const [nextDetail, nextResource] = await Promise.all([
        api.get<SkillCatalogDetail>(`${path}/catalog/${encodeURIComponent(item.id)}`),
        item.resource_id && item.source !== "builtin"
          ? api.get<Resource<AgentSkill>>(`/skills/${encodeURIComponent(item.resource_id)}`)
          : Promise.resolve(null),
      ]);
      if (live.current) {
        setDetail(nextDetail);
        setResource(nextResource);
        setLoaded(true);
      }
    } catch (cause) {
      if (live.current && !isRequestCancelled(cause)) setError(cause);
    } finally {
      if (live.current) setBusy(false);
    }
  };
  return (
    <details
      className="card skill-card"
      data-skill-id={item.id}
      data-skill-available={available}
      onToggle={(event) => {
        if (event.currentTarget.open && !loaded && !busy) void load();
      }}
    >
      <summary>
        <span className="skill-card-identity">
          <strong>{item.title}</strong>
          <bdi dir="ltr">
            {item.id}
            {item.version ? ` · ${item.version}` : ""}
          </bdi>
        </span>
        <span className={available ? "skill-status" : "skill-status unavailable"}>
          {available ? t`Available` : statusLabel(revoked ? "skill_version_revoked" : item.code)}
        </span>
      </summary>
      <p className="muted">{sourceLabel(item.source)}</p>
      {item.description && <p>{item.description}</p>}
      {item.code && !available && <code dir="ltr">{item.code}</code>}
      {busy && !loaded && (
        <p role="status">
          <Trans>Loading…</Trans>
        </p>
      )}
      {error != null && <p role="alert">{userError(error)}</p>}
      {(!loaded || error != null) && (
        <button type="button" disabled={busy} onClick={() => void load()}>
          <Trans>Reload</Trans>
        </button>
      )}
      {detail?.manifest && <SkillMetadata manifest={detail.manifest} />}
      {detail && !resource && (
        <pre className="skill-instructions" dir="auto">
          {detail.content}
        </pre>
      )}
      {resource && (
        <SkillEditor
          key={`${resource.id}:${resource.version}`}
          row={resource}
          onChanged={onChanged}
          onSaved={setResource}
          onReload={() => void load()}
          onDeleted={() => {
            setResource(null);
            setDetail(null);
            setLoaded(false);
            onChanged();
          }}
        />
      )}
      {(confirm || (item.version && !revoked)) && !item.id.includes("@") && (
        <div className="skill-revoke">
          {confirm ? (
            <>
              <p>
                <bdi dir="ltr">
                  {item.id}@{confirm}
                </bdi>
                <br />
                <Trans>
                  Block this exact version permanently? Retained tasks using it will stop at their
                  next runtime boundary.
                </Trans>
              </p>
              <div className="actions">
                <button type="button" disabled={busy} onClick={() => setConfirm(null)}>
                  <Trans>Cancel</Trans>
                </button>
                <button
                  type="button"
                  className="danger"
                  disabled={busy || !canRevoke}
                  onClick={async () => {
                    if (!confirm || busy) return;
                    setBusy(true);
                    setError(undefined);
                    try {
                      await onRevoke(confirm);
                      if (live.current) setConfirm(null);
                    } catch (cause) {
                      if (live.current && !isRequestCancelled(cause)) setError(cause);
                    } finally {
                      if (live.current) setBusy(false);
                    }
                  }}
                >
                  <Trans>Block version permanently</Trans>
                </button>
              </div>
            </>
          ) : (
            <button
              type="button"
              className="danger"
              disabled={!canRevoke || busy}
              onClick={() => setConfirm(item.version)}
            >
              <Trans>Block this version</Trans>
            </button>
          )}
        </div>
      )}
    </details>
  );
}
