import { t } from "@lingui/core/macro";
import { AgentAvatar as Avatar } from "@lonora/ui-web";
import type { Agent } from "../../lib/api";
export function AgentAvatar({ agent, working = false }: { agent: Agent; working?: boolean }) {
  return (
    <Avatar
      name={agent.name}
      color={agent.color}
      shape={agent.avatar}
      working={working}
      superBot={agent.super_bot_active}
      superBotLabel={t`Super Bot enabled`}
    />
  );
}
