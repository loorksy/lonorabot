import type { Agent } from "@lonora/contracts";

export function mentionQuery(textBeforeCaret: string): string | null {
  const match = /(?:^|\s)@([^\s@]*)$/.exec(textBeforeCaret);
  return match ? (match[1] ?? "") : null;
}
export function mentionCandidates(members: Agent[], query: string): Agent[] {
  const needle = query.toLocaleLowerCase();
  return members.filter(
    (agent) => !agent.paused && agent.name.toLocaleLowerCase().includes(needle),
  );
}
