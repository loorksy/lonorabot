import { Trans } from "@lingui/react/macro";
import { useEffect, useState } from "react";
import { ThreadViewport } from "../components/chat/ThreadViewport";
import { GroupAvatar } from "../components/groups/GroupAvatar";
import { GroupMembers } from "../components/groups/GroupMembers";
import { GroupSettings } from "../components/groups/GroupSettings";
import { type Agent, api, type Resource } from "../lib/api";
import { resources } from "../lib/rpc";
import { userError } from "../lib/user_error";
import { useClient } from "../providers/ClientProvider";
export function Group({ agents }: { agents: Agent[] }) {
  const { revision, refresh } = useClient();
  const [groups, setGroups] = useState<Resource[]>([]);
  const [selected, setSelected] = useState("");
  const [name, setName] = useState("");
  const [members, setMembers] = useState<string[]>([]);
  const [error, setError] = useState<unknown>();
  const [settings, setSettings] = useState(false);
  useEffect(() => {
    // The durable revision (or explicit refresh tick) invalidates this fetched state.
    void revision;
    void resources("/groups").list().then(setGroups).catch(setError);
  }, [revision]);
  const group = groups.find((g) => g.id === selected);
  const threadId = String(group?.state?.thread_id ?? "");
  return (
    <div className="group-page">
      <div className="page-header">
        <h1>
          <Trans>Groups</Trans>
        </h1>
        <select value={selected} onChange={(e) => setSelected(e.target.value)}>
          <option value="">
            <Trans>Choose a group</Trans>
          </option>
          {groups.map((g) => (
            <option key={g.id} value={g.id}>
              {String(g.payload.name)}
            </option>
          ))}
        </select>
      </div>
      {error != null && <p role="alert">{userError(error)}</p>}
      {group ? (
        <>
          <div className="row">
            <GroupAvatar name={String(group.payload.name)} />
            <GroupMembers
              agents={agents}
              memberIds={(group.payload.member_ids ?? []) as string[]}
            />
            <button type="button" onClick={() => setSettings((v) => !v)}>
              <Trans>Group settings</Trans>
            </button>
          </div>
          {settings && (
            <GroupSettings
              key={group.version}
              group={group}
              agents={agents}
              onSave={() => {
                refresh();
                setSettings(false);
              }}
            />
          )}
          {threadId && <ThreadViewport threadId={threadId} agentId="" agents={agents} />}
        </>
      ) : (
        <form
          className="card"
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              const g = await api.post<Resource>("/groups/create", {
                name,
                member_ids: members,
                participation: "mentions_or_lead",
              });
              setSelected(g.id);
              setName("");
              refresh();
            } catch (err) {
              setError(err);
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
            <input value={name} required onChange={(e) => setName(e.target.value)} />
          </label>
          {agents.map((a) => (
            <label key={a.id} className="check">
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
          <button type="submit" className="primary" disabled={!members.length}>
            <Trans>Create group</Trans>
          </button>
        </form>
      )}
    </div>
  );
}
