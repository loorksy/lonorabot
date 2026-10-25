import { t } from "@lingui/core/macro";
import type { AvatarStateId } from "@lonora/core";
import { AgentAvatar as Avatar } from "@lonora/ui-web";
import type { Agent } from "../../lib/api";
export function AgentAvatar({
  agent,
  working = false,
  state,
}: {
  agent: Agent;
  working?: boolean;
  state?: AvatarStateId;
}) {
  return (
    <Avatar
      name={agent.name}
      color={agent.color}
      shape={agent.avatar}
      working={working}
      state={state}
      superBot={agent.super_bot_active}
      superBotLabel={t`Super Bot enabled`}
    />
  );
}
