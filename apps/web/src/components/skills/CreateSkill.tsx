import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { useState } from "react";
import { api, isRequestCancelled } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { SEMVER, useAlive } from "./shared";

export function CreateSkill({ agentId, onChanged }: { agentId: string; onChanged: () => void }) {
  const live = useAlive();
  const [name, setName] = useState("");
  const [purpose, setPurpose] = useState("");
  const [skillId, setSkillId] = useState("");
  const [version, setVersion] = useState("1.0.0");
  const [content, setContent] = useState("");
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  return (
    <details className="card skill-create">
      <summary>
        <Trans>Add owner instructions</Trans>
      </summary>
      <form
        className="skill-editor"
        onSubmit={async (event) => {
          event.preventDefault();
          if (busy) return;
          setBusy(true);
          setError(undefined);
          try {
            await api.post("/skills", {
              agent_id: agentId,
              payload: {
                name: skillId,
                content,
                enabled: true,
                manifest: {
                  id: skillId,
                  version,
                  title: name.trim(),
                  description: purpose.trim(),
                  source: "owner",
                  stability: "stable",
                  activation: { mode: "explicit", intents: [], triggers: [] },
                  risk_class: "read_only",
                  required_tools: [],
                  required_capabilities: [],
                  dependencies: [],
                  conflicts: [],
                  priority: 50,
                  context_budget: 16000,
                },
              },
            });
            if (live.current) {
              setName("");
              setPurpose("");
              setSkillId("");
              setVersion("1.0.0");
              setContent("");
              onChanged();
            }
          } catch (cause) {
            if (live.current && !isRequestCancelled(cause)) setError(cause);
          } finally {
            if (live.current) setBusy(false);
          }
        }}
      >
        <label>
          <Trans>Skill ID</Trans>
          <input
            dir="ltr"
            required
            maxLength={80}
            pattern="[a-z0-9][a-z0-9_-]{0,79}"
            value={skillId}
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
            onChange={(event) => setVersion(event.target.value)}
          />
        </label>
        <label>
          <Trans>Title</Trans>
          <input
            required
            maxLength={160}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label>
          <Trans>Purpose</Trans>
          <input
            required
            maxLength={1000}
            value={purpose}
            onChange={(event) => setPurpose(event.target.value)}
          />
        </label>
        <label>
          <Trans>Content</Trans>
          <textarea
            aria-label={t`Content`}
            dir="auto"
            required
            rows={5}
            maxLength={16000}
            value={content}
            onChange={(event) => setContent(event.target.value)}
          />
        </label>
        <p className="muted">
          <Trans>
            New owner skills use explicit activation and read-only metadata. They do not install
            code or grant permissions.
          </Trans>
        </p>
        {error != null && <p role="alert">{userError(error)}</p>}
        <button type="submit" disabled={busy || !name.trim() || !purpose.trim() || !skillId}>
          <Trans>Add</Trans>
        </button>
      </form>
    </details>
  );
}
