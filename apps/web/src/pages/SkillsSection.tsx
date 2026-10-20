import { Trans } from "@lingui/react/macro";
import type { SkillCatalog, SkillRevocationReason, SkillVersionControls } from "@lonora/contracts";
import { useEffect, useState } from "react";
import { CreateSkill } from "../components/skills/CreateSkill";
import { RevokeVersion } from "../components/skills/RevokeVersion";
import { SkillCard } from "../components/skills/SkillCard";
import { reasonLabel, useAlive } from "../components/skills/shared";
import { api, isRequestCancelled } from "../lib/api";
import { userError } from "../lib/user_error";
import { useClient } from "../providers/ClientProvider";
import "../components/skills/skills.css";

const PAGE_SIZE = 50;

export function SkillsSection({ agentId }: { agentId: string }) {
  const { owner } = useClient();
  return <ScopedSkills key={`${owner.id}:${agentId}`} agentId={agentId} />;
}

function ScopedSkills({ agentId }: { agentId: string }) {
  const { revision, refresh } = useClient();
  const live = useAlive();
  const [catalog, setCatalog] = useState<SkillCatalog | null>(null);
  const [controls, setControls] = useState<SkillVersionControls | null>(null);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<unknown>();
  const [loading, setLoading] = useState(false);
  const [reload, setReload] = useState(0);
  const path = `/agents/${encodeURIComponent(agentId)}/skills`;
  const changed = () => {
    setReload((value) => value + 1);
    refresh();
  };
  useEffect(() => {
    void revision;
    void reload;
    let current = true;
    setLoading(true);
    void Promise.all([
      api.get<SkillCatalog>(`${path}/catalog?offset=${offset}&limit=${PAGE_SIZE}`),
      api.get<SkillVersionControls>(`${path}/revocations`),
    ])
      .then(([nextCatalog, nextControls]) => {
        if (!current) return;
        setCatalog(nextCatalog);
        setControls((previous) =>
          previous && previous.revision > nextControls.revision ? previous : nextControls,
        );
        setError(undefined);
      })
      .catch((cause) => {
        if (current && !isRequestCancelled(cause)) setError(cause);
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, [path, offset, revision, reload]);
  const revoke = async (skillId: string, version: string, reason: SkillRevocationReason) => {
    if (!controls) return;
    try {
      const value = await api.post<SkillVersionControls>(`${path}/revocations`, {
        skill_id: skillId,
        version,
        reason,
        expected_revision: controls.revision,
      });
      if (live.current) {
        setControls((previous) =>
          previous && previous.revision > value.revision ? previous : value,
        );
        changed();
      }
    } catch (cause) {
      // A stale revision must be reviewed again, never silently resubmitted.
      if (live.current) changed();
      throw cause;
    }
  };
  return (
    <div className="skills-section" data-agent-skills={agentId}>
      <p className="muted skills-guidance">
        <Trans>
          Skills guide how this agent works. They do not grant trading permissions. This catalog
          shows current instructions; active tasks keep their pinned versions.
        </Trans>
      </p>
      {error != null && <p role="alert">{userError(error)}</p>}
      <div className="skills-toolbar">
        <h2>
          <Trans>Skill catalog</Trans>
        </h2>
        <button type="button" onClick={changed} disabled={loading}>
          <Trans>Reload</Trans>
        </button>
      </div>
      {!catalog && loading && (
        <p role="status">
          <Trans>Loading…</Trans>
        </p>
      )}
      {catalog?.items.map((item) => (
        <SkillCard
          key={item.id}
          item={item}
          path={path}
          revoked={Boolean(
            controls?.revoked.some(
              (row) => row.skill_id === item.id && row.version === item.version,
            ),
          )}
          canRevoke={controls !== null}
          onRevoke={(version) => revoke(item.id, version, "owner_revoked")}
          onChanged={changed}
        />
      ))}
      {catalog && catalog.total === 0 && (
        <p className="muted">
          <Trans>No skills available.</Trans>
        </p>
      )}
      {catalog && (offset > 0 || catalog.next_offset !== null) && (
        <div className="actions">
          <button
            type="button"
            disabled={offset === 0 || loading}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            <Trans>Previous</Trans>
          </button>
          <button
            type="button"
            disabled={catalog.next_offset === null || loading}
            onClick={() => {
              if (catalog.next_offset !== null) setOffset(catalog.next_offset);
            }}
          >
            <Trans>Next</Trans>
          </button>
        </div>
      )}
      <CreateSkill agentId={agentId} onChanged={changed} />
      <details className="card skills-blocked-versions">
        <summary>
          <Trans>Blocked versions</Trans> ({controls?.revoked.length ?? 0})
        </summary>
        <p className="muted">
          <Trans>
            Blocking an exact version is permanent for this agent, including retained tasks and
            deleted or reinstalled skills. It takes effect at the next runtime boundary.
          </Trans>
        </p>
        {controls && (
          <p className="muted">
            <Trans>Version controls revision</Trans>: <bdi dir="ltr">{controls.revision}</bdi>
          </p>
        )}
        {controls?.revoked.map((item) => (
          <div className="skills-revoked-row" key={`${item.skill_id}:${item.version}`}>
            <bdi dir="ltr">
              {item.skill_id}@{item.version}
            </bdi>
            <span>{reasonLabel(item.reason)}</span>
            <time dateTime={item.revoked_at}>{new Date(item.revoked_at).toLocaleString()}</time>
          </div>
        ))}
        <RevokeVersion disabled={!controls} onRevoke={revoke} />
      </details>
    </div>
  );
}
