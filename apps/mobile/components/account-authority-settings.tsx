import type { Agent } from "@lonora/contracts";
import { AgentPermissions } from "./agent-permissions";

/** Settings and the chat composer share the same server-backed permission flow. */
export function AccountAuthoritySettings({ agent }: { agent: Agent }) {
  return <AgentPermissions agent={agent} settings />;
}
