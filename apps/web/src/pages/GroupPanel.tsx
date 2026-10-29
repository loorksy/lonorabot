// Modified for Lonora from Tampletgrok group panel boundaries; Apache-2.0.
import { Trans } from "@lingui/react/macro";
import { useState } from "react";
import { AgentAvatar } from "../components/ai/AgentAvatar";
import { type Agent, api, type Payload, type Resource } from "../lib/api";
import { resources } from "../lib/rpc";
import { userError } from "../lib/user_error";
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
          maxLength={80}
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
              role="switch"
              data-lonora-switch="true"
              aria-checked={members.includes(agent.id)}
              checked={members.includes(agent.id)}
              onChange={(event) =>
                setMembers((values) =>
                  event.target.checked
                    ? values.length < 12
                      ? [...values, agent.id]
                      : values
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

export function GroupSettings({
  group,
  agents,
  onSave,
}: {
  group: Resource;
  agents: Agent[];
  onSave: () => void;
}) {
  const [name, setName] = useState(String(group.payload.name ?? ""));
  const [members, setMembers] = useState<string[]>((group.payload.member_ids ?? []) as string[]);
  const [error, setError] = useState<unknown>();
  return (
    <form
      className="card"
      onSubmit={async (e) => {
        e.preventDefault();
        try {
          const payload: Payload = { ...group.payload, name, member_ids: members };
          await resources("/groups").update(group, payload);
          onSave();
        } catch (err) {
          setError(err);
        }
      }}
    >
      <label>
        <Trans>Group name</Trans>
        <input value={name} required onChange={(e) => setName(e.target.value)} />
      </label>
      {agents.map((a) => (
        <label className="check" key={a.id}>
          <input
            type="checkbox"
            role="switch"
            data-lonora-switch="true"
            aria-checked={members.includes(a.id)}
            checked={members.includes(a.id)}
            onChange={(e) =>
              setMembers((old) =>
                e.target.checked
                  ? old.length < 12
                    ? [...old, a.id]
                    : old
                  : old.filter((id) => id !== a.id),
              )
            }
          />
          {a.name}
        </label>
      ))}
      <button type="submit" disabled={!members.length}>
        <Trans>Save members</Trans>
      </button>
      {error != null && <p role="alert">{userError(error)}</p>}
    </form>
  );
}
