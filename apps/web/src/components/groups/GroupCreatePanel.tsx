// Modified for Lonora; source attribution in THIRD_PARTY_NOTICES.md. Apache-2.0.
import { Trans } from "@lingui/react/macro";
import { useState } from "react";
import { type Agent, api, type Resource } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { AgentAvatar } from "../agents/AgentAvatar";
export function GroupCreatePanel({
  agents,
  onCreated,
}: {
  agents: Agent[];
  onCreated: (group: Resource) => void;
}) {
  const [name, setName] = useState("");
  const [members, setMembers] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  return (
    <form
      className="tpl-profile-form"
      onSubmit={async (event) => {
        event.preventDefault();
        setBusy(true);
        setError(undefined);
        try {
          onCreated(
            await api.post<Resource>("/groups/create", {
              name: name.trim(),
              member_ids: members,
              participation: "mentions_or_lead",
            }),
          );
        } catch (failure) {
          setError(failure);
        } finally {
          setBusy(false);
        }
      }}
    >
      <h2>
        <Trans>Create a group</Trans>
      </h2>
      <p className="muted">
        <Trans>Mention agents with @name. Without a mention, the first member responds.</Trans>
      </p>
      <label>
        <Trans>Group name</Trans>
        <input
          required
          maxLength={120}
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      <fieldset className="tpl-members">
        <legend>
          <Trans>Members</Trans>
        </legend>
        {agents.map((agent) => (
          <label className="check" key={agent.id}>
            <input
              type="checkbox"
              checked={members.includes(agent.id)}
              onChange={(event) =>
                setMembers((values) =>
                  event.target.checked
                    ? [...values, agent.id]
                    : values.filter((id) => id !== agent.id),
                )
              }
            />
            <AgentAvatar agent={agent} />
            <span dir="auto">{agent.name}</span>
          </label>
        ))}
      </fieldset>
      {!agents.length && (
        <p className="muted">
          <Trans>Create agents before starting a group.</Trans>
        </p>
      )}
      {error != null && <p role="alert">{userError(error)}</p>}
      <button type="submit" className="primary" disabled={!name.trim() || !members.length || busy}>
        <Trans>Create group</Trans>
      </button>
    </form>
  );
}
