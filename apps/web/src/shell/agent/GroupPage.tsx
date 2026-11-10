import { plural, t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { GroupAvatar, Icon } from "@lonora/ui-web";
import { useEffect, useState } from "react";
import { AgentAvatar } from "../../components/ai/AgentAvatar";
import { type Agent, api, type Resource } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useShellData } from "../data";
import { agentRole } from "../lists/ThreadRow";
import { clearDirty, markDirty, useNavigation } from "../navigation";
import { SkPage, SkRows } from "../Skeleton";
import { NotFoundPage } from "../StatePage";
import { useSheets } from "../sheets/SheetHost";
import { useToast } from "../Toast";
import "./agent.css";

export const agentsWord = (count: number) =>
  plural(count, {
    one: "one agent",
    two: "two agents",
    few: "# agents",
    many: "# agents",
    other: "# agents",
  });

const memberIds = (group: Resource) => (group.payload.member_ids ?? []) as string[];
const leadOf = (group: Resource) =>
  typeof group.payload.lead_agent_id === "string" ? group.payload.lead_agent_id : null;

/** The members, the lead first (the reference's cluster order). */
function members(group: Resource, agents: readonly Agent[]) {
  const ids = memberIds(group);
  const lead = leadOf(group);
  return (lead && ids.includes(lead) ? [lead, ...ids.filter((id) => id !== lead)] : ids)
    .map((id) => agents.find((agent) => agent.id === id))
    .filter((agent): agent is Agent => Boolean(agent));
}

/* The group page (route group): the cluster, name, size and purpose, the members (the lead
   reads «المنسق»), «إضافة وكيل», «فتح محادثة المجموعة». No deletion (Q1, Q44). */
export function GroupPage({ groupId }: { groupId: string }) {
  const data = useShellData();
  const nav = useNavigation();
  const sheets = useSheets();
  const group = data.groups.find((row) => row.id === groupId);
  if (!group)
    return data.groupsLoading ? (
      <SkPage>
        <SkRows count={4} />
      </SkPage>
    ) : (
      <NotFoundPage />
    );
  const list = members(group, data.agents);
  const lead = leadOf(group);
  const outside = data.agents.filter(
    (agent) => agent.role !== "delegated" && !memberIds(group).includes(agent.id),
  );
  const purpose = String(group.payload.purpose ?? "");
  return (
    <>
      <div className="hero">
        {list.length ? (
          <span className="group-av">
            <GroupAvatar members={list} />
          </span>
        ) : (
          <span className="avatar icon-av">
            <Icon name="users" />
          </span>
        )}
        <h2>
          <bdi>{String(group.payload.name)}</bdi>
        </h2>
        <p>{agentsWord(memberIds(group).length)}</p>
      </div>
      {purpose && (
        <p className="muted">
          <bdi>{purpose}</bdi>
        </p>
      )}
      <h3>
        <Trans>Members</Trans>
      </h3>
      <div className="group">
        {list.map((agent) => (
          <button
            type="button"
            className="row"
            key={agent.id}
            onClick={() => nav.go(`/app/agent/${agent.id}`)}
          >
            <AgentAvatar agent={agent} />
            <span className="body">
              <strong>
                <bdi>{agent.name}</bdi>
              </strong>
              <small>{agent.id === lead ? t`Coordinator` : <bdi>{agentRole(agent)}</bdi>}</small>
            </span>
            <span className="chevron">
              <Icon name="chev" />
            </span>
          </button>
        ))}
      </div>
      {outside.length > 0 && (
        <button
          type="button"
          className="btn full outline"
          onClick={() =>
            sheets.open({
              id: "group-member",
              title: t`Add an agent`,
              body: <AddMembers group={group} candidates={outside} onDone={() => sheets.close()} />,
            })
          }
        >
          <Trans>Add an agent</Trans>
        </button>
      )}
      <button
        type="button"
        className="btn full primary"
        onClick={() => nav.go(`/app/g/${group.id}`)}
      >
        <Trans>Open the group chat</Trans>
      </button>
      <p className="note">
        <Trans>
          Each member keeps its own permissions. The group has no shared financial authority.
        </Trans>
      </p>
    </>
  );
}

function AddMembers({
  group,
  candidates,
  onDone,
}: {
  group: Resource;
  candidates: Agent[];
  onDone: () => void;
}) {
  const data = useShellData();
  const toast = useToast();
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const room = 12 - memberIds(group).length;
  const save = async () => {
    if (!picked.size || busy) return;
    setBusy(true);
    try {
      await api.put(`/groups/${group.id}`, {
        version: group.version,
        payload: { ...group.payload, member_ids: [...memberIds(group), ...picked] },
      });
      data.refresh();
      onDone();
    } catch (failure) {
      toast(userError(failure), { type: "error" });
      setBusy(false);
    }
  };
  return (
    <>
      <div className="group">
        {candidates.map((agent) => {
          const on = picked.has(agent.id);
          return (
            // biome-ignore lint/a11y/useSemanticElements: a whole row toggles, as in the reference
            <button
              type="button"
              key={agent.id}
              className={`row reach-opt${on ? " on" : ""}`}
              role="checkbox"
              aria-checked={on}
              disabled={!on && picked.size >= room}
              onClick={() =>
                setPicked((old) => {
                  const next = new Set(old);
                  if (on) next.delete(agent.id);
                  else next.add(agent.id);
                  return next;
                })
              }
            >
              <AgentAvatar agent={agent} />
              <span className="body">
                <strong>
                  <bdi>{agent.name}</bdi>
                </strong>
                <small>
                  <bdi>{agentRole(agent)}</bdi>
                </small>
              </span>
              <span className={`pick-box${on ? " on" : ""}`} aria-hidden="true">
                {on && <Icon name="check" />}
              </span>
            </button>
          );
        })}
      </div>
      <button
        type="button"
        className="btn full primary"
        disabled={!picked.size || busy}
        onClick={() => void save()}
      >
        <Trans>Add</Trans>
      </button>
    </>
  );
}

/* «مجموعة جديدة» (route new-group): name, purpose, member check rows (prefilled from the
   selection) and المنسق (a member; the first chosen by default). POST /api/groups/create. */
export function NewGroupPage({
  initialMembers = [],
  initialName = "",
}: {
  initialMembers?: string[];
  initialName?: string;
}) {
  const data = useShellData();
  const nav = useNavigation();
  const toast = useToast();
  const [name, setName] = useState(initialName);
  const [purpose, setPurpose] = useState("");
  const [picked, setPicked] = useState<string[]>(initialMembers);
  // The reference's select: the first preselected member, else the first agent listed.
  const [lead, setLead] = useState(
    initialMembers[0] ?? data.agents.find((agent) => agent.role !== "delegated")?.id ?? "",
  );
  const [busy, setBusy] = useState(false);
  const [tried, setTried] = useState(false);
  const [error, setError] = useState<unknown>();
  const agents = data.agents.filter((agent) => agent.role !== "delegated");
  const dirty = Boolean(name.trim() || purpose.trim() || picked.length !== initialMembers.length);
  useEffect(() => {
    if (dirty) markDirty();
    else clearDirty();
    return () => clearDirty();
  }, [dirty]);
  const nameErr = tried && !name.trim() ? t`Enter the group's name.` : "";
  const submit = async () => {
    setTried(true);
    if (!name.trim() || busy) return;
    if (!picked.length) return toast(t`Choose at least one member.`, { type: "warn" });
    const coordinator = lead;
    if (!picked.includes(coordinator))
      return toast(t`The coordinator must be one of the group's members.`, { type: "warn" });
    setBusy(true);
    setError(undefined);
    try {
      const row = await api.post<Resource>("/groups/create", {
        name: name.trim(),
        purpose: purpose.trim(),
        member_ids: picked,
        lead_agent_id: coordinator,
        participation: "mentions_or_lead",
      });
      clearDirty();
      data.addGroup(row);
      data.refresh();
      nav.go(`/app/group/${row.id}`, { replace: true });
    } catch (failure) {
      setError(failure);
      setBusy(false);
    }
  };
  return (
    <form
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <label className="field">
        <span>
          <Trans>Group name</Trans>
        </span>
        <input
          name="name"
          required
          maxLength={80}
          value={name}
          aria-invalid={Boolean(nameErr)}
          onChange={(event) => setName(event.target.value)}
        />
        {nameErr && <small className="field-err">{nameErr}</small>}
      </label>
      <label className="field">
        <span>
          <Trans>Purpose</Trans>
        </span>
        <input
          name="purpose"
          maxLength={160}
          value={purpose}
          onChange={(event) => setPurpose(event.target.value)}
        />
      </label>
      <h3>
        <Trans>Members</Trans>
      </h3>
      {agents.map((agent) => (
        <label className="check" key={agent.id}>
          <span>
            <bdi>{agent.name}</bdi>
          </span>
          <input
            type="checkbox"
            className="switch"
            role="switch"
            name="members"
            value={agent.id}
            checked={picked.includes(agent.id)}
            aria-checked={picked.includes(agent.id)}
            disabled={!picked.includes(agent.id) && picked.length >= 12}
            onChange={(event) => {
              const next = event.target.checked
                ? [...picked, agent.id]
                : picked.filter((id) => id !== agent.id);
              setPicked(next);
            }}
          />
        </label>
      ))}
      <label className="field">
        <span>
          <Trans>Coordinator</Trans>
        </span>
        <select name="leader" value={lead} onChange={(event) => setLead(event.target.value)}>
          {agents.map((agent) => (
            <option key={agent.id} value={agent.id}>
              {agent.name}
            </option>
          ))}
        </select>
      </label>
      {error != null && <p role="alert">{userError(error)}</p>}
      <div className="actions">
        <button type="submit" className="btn primary" disabled={busy}>
          <Trans>Create the group</Trans>
        </button>
      </div>
    </form>
  );
}
