import { Trans } from "@lingui/react/macro";
import type { Agent } from "../../lib/api";
import { AgentAvatar } from "./AgentAvatar";
export function AgentPanel({ agent, onSettings }: { agent: Agent; onSettings: () => void }) {
  return (
    <div className="agent-panel">
      <AgentAvatar agent={agent} />
      <div>
        <strong>{agent.name}</strong>
        <span className="muted">
          {agent.paused ? <Trans>Paused</Trans> : <Trans>Persistent agent</Trans>}
        </span>
      </div>
      <button type="button" onClick={onSettings}>
        <Trans>Instructions</Trans>
      </button>
    </div>
  );
}
