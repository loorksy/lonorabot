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
      identity={agent.id}
      name={agent.name}
      color={agent.color}
      shape={agent.avatar}
      working={working}
      state={state}
      tradesOnItsOwn={agent.trades_on_its_own}
      tradesOnItsOwnLabel={t`Trades on its own`}
    />
  );
}
