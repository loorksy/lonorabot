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

export type MentionRange = {
  agent_id: string | null;
  session_id?: string;
  token: string;
  start: number;
  end: number;
};
export type MentionAddress = {
  agent_ids: string[];
  all: boolean;
  collaboration_session_id?: string;
};

/** Rebase committed identity ranges through one text edit; editing a token uncommits it. */
export function rebaseMentions(
  before: string,
  after: string,
  ranges: MentionRange[],
): MentionRange[] {
  let start = 0;
  while (start < before.length && start < after.length && before[start] === after[start]) start++;
  let end = before.length,
    nextEnd = after.length;
  while (end > start && nextEnd > start && before[end - 1] === after[nextEnd - 1]) {
    end--;
    nextEnd--;
  }
  const delta = after.length - before.length;
  return ranges.flatMap((range) =>
    range.end <= start
      ? [range]
      : range.start >= end
        ? [{ ...range, start: range.start + delta, end: range.end + delta }]
        : [],
  );
}

export function mentionAddress(text: string, ranges: MentionRange[]): MentionAddress {
  const valid = ranges.filter((range) => text.slice(range.start, range.end) === range.token);
  return {
    agent_ids: [...new Set(valid.flatMap((range) => (range.agent_id ? [range.agent_id] : [])))],
    all: valid.some((range) => range.agent_id === null),
    collaboration_session_id: valid.find((range) => range.agent_id === null)?.session_id,
  };
}

/** A direct chat offers every other agent as a guest; its own agent is never one. There is
    no cap on how many the owner names (mandate P1). */
export function guestCandidates(
  candidates: Agent[],
  _committed: readonly Pick<MentionRange, "agent_id">[],
  direct: boolean,
  /** A direct chat's own agent: never a guest. */
  self?: string | null,
): Agent[] {
  return direct ? candidates.filter((agent) => agent.id !== self) : candidates;
}
