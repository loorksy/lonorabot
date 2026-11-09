import { plural, t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { Icon } from "@lonora/ui-web";
import { AgentAvatar } from "../components/ai/AgentAvatar";
import { useShellData } from "./data";
import { agentRole } from "./lists/ThreadRow";
import { useNavigation } from "./navigation";

const agentsWord = (count: number) =>
  plural(count, {
    one: "one agent",
    two: "two agents",
    few: "# agents",
    many: "# agents",
    other: "# agents",
  });

/* «إدارة الوكلاء» (the reference's agents route): every agent with its role and whether it is
   on, every group with its size, and «إنشاء مجموعة». A row opens its conversation until the
   agent and group pages arrive (phase 4). */
export function AgentsPage() {
  const data = useShellData();
  const nav = useNavigation();
  return (
    <>
      <h3>
        <Trans>Agents</Trans>
      </h3>
      <div className="group">
        {data.agents.map((agent) => (
          <button
            type="button"
            className="row"
            key={agent.id}
            onClick={() => nav.go(`/app/${agent.id}`)}
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
            <span className={`status ${agent.paused ? "off" : "on"}`}>
              {agent.paused
                ? t({ message: "Paused", context: "agent badge" })
                : t({ message: "Active", context: "agent status" })}
            </span>
            <span className="chevron">
              <Icon name="chev" />
            </span>
          </button>
        ))}
      </div>
      <h3>
        <Trans>Groups</Trans>
      </h3>
      {data.groups.length ? (
        <div className="group">
          {data.groups.map((group) => (
            <button
              type="button"
              className="row"
              key={group.id}
              onClick={() => nav.go(`/app/g/${group.id}`)}
            >
              <Icon name="users" />
              <span className="body">
                <strong>
                  <bdi>{String(group.payload.name)}</bdi>
                </strong>
              </span>
              <span className="value">
                {agentsWord(((group.payload.member_ids ?? []) as string[]).length)}
              </span>
              <span className="chevron">
                <Icon name="chev" />
              </span>
            </button>
          ))}
        </div>
      ) : (
        <div className="empty">
          <Icon name="folder" />
          <div>
            <Trans>No groups yet.</Trans>
          </div>
        </div>
      )}
      <button type="button" className="btn full outline" onClick={() => nav.go("/app/new-group")}>
        <Trans>Create a group</Trans>
      </button>
    </>
  );
}
