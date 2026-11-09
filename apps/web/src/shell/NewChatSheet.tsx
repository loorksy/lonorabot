import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { GroupAvatar, Icon } from "@lonora/ui-web";
import { useCallback } from "react";
import { AgentAvatar } from "../components/ai/AgentAvatar";
import type { Agent, Resource } from "../lib/api";
import { useShellData } from "./data";
import { agentRole } from "./lists/ThreadRow";
import { useNavigation } from "./navigation";
import { useSheets } from "./sheets/SheetHost";

/* «محادثة جديدة»: a new agent or group, then the agents and the groups that already exist. */
function Body({
  agents,
  groups,
  onGo,
}: {
  agents: Agent[];
  groups: Resource[];
  onGo: (path: string) => void;
}) {
  return (
    <>
      <div className="group">
        <button type="button" className="row" onClick={() => onGo("/app/new-agent")}>
          <span className="avatar icon-av">
            <Icon name="userPlus" />
          </span>
          <span className="body">
            <strong>
              <Trans>New agent</Trans>
            </strong>
            <small>
              <Trans>Its own role, model and permissions</Trans>
            </small>
          </span>
        </button>
        <button type="button" className="row" onClick={() => onGo("/app/new-group")}>
          <span className="avatar icon-av">
            <Icon name="users" />
          </span>
          <span className="body">
            <strong>
              <Trans>New group</Trans>
            </strong>
            <small>
              <Trans>Several agents in one chat</Trans>
            </small>
          </span>
        </button>
      </div>
      <h3>
        <Trans>Agents</Trans>
      </h3>
      <div className="group">
        {agents.map((agent) => (
          <button
            type="button"
            className="row"
            key={agent.id}
            data-new-chat-agent={agent.id}
            onClick={() => onGo(`/app/${agent.id}`)}
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
            {agent.paused && (
              <span className="status off">{t({ message: "Paused", context: "agent badge" })}</span>
            )}
          </button>
        ))}
      </div>
      {groups.length > 0 && (
        <>
          <h3>
            <Trans>Groups</Trans>
          </h3>
          <div className="group">
            {groups.map((group) => {
              const members = agents.filter((agent) =>
                ((group.payload.member_ids ?? []) as string[]).includes(agent.id),
              );
              return (
                <button
                  type="button"
                  className="row"
                  key={group.id}
                  onClick={() => onGo(`/app/g/${group.id}`)}
                >
                  <span className="group-av">
                    <GroupAvatar members={members} />
                  </span>
                  <span className="body">
                    <strong>
                      <bdi>{String(group.payload.name)}</bdi>
                    </strong>
                    <small>
                      <bdi>{String(group.payload.purpose ?? "")}</bdi>
                    </small>
                  </span>
                </button>
              );
            })}
          </div>
        </>
      )}
      <button type="button" className="btn full ghost" onClick={() => onGo("/app/agents")}>
        <Trans>Manage agents</Trans>
      </button>
    </>
  );
}

export function useNewChatSheet() {
  const sheets = useSheets();
  const nav = useNavigation();
  const data = useShellData();
  return useCallback(() => {
    sheets.open({
      id: "new-chat",
      title: t`New chat`,
      body: <Body agents={data.agents} groups={data.groups} onGo={nav.go} />,
    });
  }, [sheets, nav.go, data.agents, data.groups]);
}
