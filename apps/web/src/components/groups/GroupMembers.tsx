import { Trans } from "@lingui/react/macro";
import type { Agent } from "../../lib/api";
import { AgentAvatar } from "../agents/AgentAvatar";
export function GroupMembers({ agents, memberIds }: { agents: Agent[]; memberIds: string[] }) {
  return (
    <div className="group-members">
      <span>
        <Trans>Members</Trans>
      </span>
      {agents
        .filter((a) => memberIds.includes(a.id))
        .map((a) => (
          <span key={a.id}>
            <AgentAvatar agent={a} />
            {a.name}
          </span>
        ))}
    </div>
  );
}
