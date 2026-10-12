import { Trans } from "@lingui/react/macro";
import { useState } from "react";
import type { Agent, Payload, Resource } from "../../lib/api";
import { resources } from "../../lib/rpc";
import { userError } from "../../lib/user_error";
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
            checked={members.includes(a.id)}
            onChange={(e) =>
              setMembers((old) =>
                e.target.checked ? [...old, a.id] : old.filter((id) => id !== a.id),
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
