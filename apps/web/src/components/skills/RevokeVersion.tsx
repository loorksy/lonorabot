import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { SkillRevocationReason } from "@lonora/contracts";
import { useState } from "react";
import { isRequestCancelled } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { reasonLabel, SEMVER, useAlive } from "./shared";

export function RevokeVersion({
  disabled,
  onRevoke,
}: {
  disabled: boolean;
  onRevoke: (skillId: string, version: string, reason: SkillRevocationReason) => Promise<void>;
}) {
  const live = useAlive();
  const [skillId, setSkillId] = useState("");
  const [version, setVersion] = useState("");
  const [reason, setReason] = useState<SkillRevocationReason>("owner_revoked");
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  return (
    <form
      className="skill-editor"
      onSubmit={async (event) => {
        event.preventDefault();
        if (!confirm) {
          setConfirm(true);
          return;
        }
        if (disabled || busy) return;
        setBusy(true);
        setError(undefined);
        try {
          await onRevoke(skillId, version, reason);
          if (live.current) {
            setSkillId("");
            setVersion("");
            setConfirm(false);
          }
        } catch (cause) {
          if (live.current && !isRequestCancelled(cause)) setError(cause);
          if (live.current) setConfirm(false);
        } finally {
          if (live.current) setBusy(false);
        }
      }}
    >
      <h3>
        <Trans>Block an earlier version</Trans>
      </h3>
      <label>
        <Trans>Skill ID</Trans>
        <input
          dir="ltr"
          required
          maxLength={80}
          pattern="[a-z0-9][a-z0-9_-]{0,79}"
          value={skillId}
          disabled={busy || confirm}
          onChange={(event) => setSkillId(event.target.value)}
        />
      </label>
      <label>
        <Trans>Instruction version</Trans>
        <input
          dir="ltr"
          required
          maxLength={64}
          pattern={SEMVER}
          value={version}
          disabled={busy || confirm}
          onChange={(event) => setVersion(event.target.value)}
        />
      </label>
      <label>
        <Trans>Reason</Trans>
        <select
          value={reason}
          disabled={busy || confirm}
          onChange={(event) => setReason(event.target.value as SkillRevocationReason)}
        >
          {(["owner_revoked", "regression", "unsafe", "superseded"] as const).map((value) => (
            <option value={value} key={value}>
              {reasonLabel(value)}
            </option>
          ))}
        </select>
      </label>
      {confirm && (
        <p>
          <Trans>This permanent block cannot be undone. Confirm the exact skill and version.</Trans>{" "}
          <bdi dir="ltr">
            {skillId}@{version}
          </bdi>
        </p>
      )}
      {error != null && <p role="alert">{userError(error)}</p>}
      <div className="actions">
        {confirm && (
          <button type="button" disabled={busy} onClick={() => setConfirm(false)}>
            <Trans>Cancel</Trans>
          </button>
        )}
        <button type="submit" disabled={disabled || busy} className={confirm ? "danger" : ""}>
          {confirm ? t`Block version permanently` : t`Review version block`}
        </button>
      </div>
    </form>
  );
}
