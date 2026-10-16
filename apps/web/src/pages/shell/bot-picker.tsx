// Adapted for Lonora from Tampletgrok pages/shell/bot-picker.tsx; Apache-2.0.

import { t } from "@lingui/core/macro";
import { Trans, useLingui } from "@lingui/react/macro";
import {
  AgentAvatar,
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@lonora/ui-web";
import { Plus, Users } from "lucide-react";
import { useMemo, useState } from "react";
import { PersonalAgentBadge } from "../../components/ai/PersonalAgentBadge";
import type { Agent } from "../../lib/api";

export function NewConversationPicker({
  agents,
  onCreateAgent,
  onOpenAgent,
  onCreateGroup,
}: {
  agents: Agent[];
  onCreateAgent: () => void;
  onOpenAgent: (agentId: string) => void;
  onCreateGroup: () => void;
}) {
  const { t } = useLingui();
  const [query, setQuery] = useState("");
  const needle = query.trim().toLocaleLowerCase();
  const matched = useMemo(
    () => agents.filter((agent) => !needle || agent.name.toLocaleLowerCase().includes(needle)),
    [agents, needle],
  );

  return (
    <Command
      shouldFilter={false}
      className="tpl-create-picker"
      data-testid="new-conversation-picker"
    >
      <div className="tpl-picker-input">
        <span>
          <Trans>To:</Trans>
        </span>
        <CommandInput
          value={query}
          onValueChange={setQuery}
          placeholder={t`Search agents`}
          aria-label={t`Search agents`}
        />
      </div>
      <CommandList>
        <CommandGroup>
          <CommandItem value="create-agent" onSelect={onCreateAgent} data-testid="create-new-agent">
            <Plus size={16} strokeWidth={1.8} aria-hidden="true" />
            <Trans>Create new agent</Trans>
          </CommandItem>
          {matched.map((agent) => (
            <CommandItem
              key={agent.id}
              value={agent.id}
              onSelect={() => onOpenAgent(agent.id)}
              data-testid={`picker-agent-${agent.id}`}
            >
              <AgentAvatar
                name={agent.name}
                color={agent.color}
                shape={agent.avatar}
                className="tpl-picker-avatar"
              />
              <span className="tpl-truncate" dir="auto">
                {agent.name}
                <PersonalAgentBadge agent={agent} />
              </span>
            </CommandItem>
          ))}
          {needle && !matched.length ? (
            <p className="tpl-picker-empty">
              <Trans>No agents match</Trans>
            </p>
          ) : null}
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup>
          <CommandItem value="create-group" onSelect={onCreateGroup} data-testid="create-new-group">
            <Users size={16} strokeWidth={1.8} aria-hidden="true" />
            <Trans>Create new group</Trans>
          </CommandItem>
        </CommandGroup>
        <CommandEmpty>
          <Trans>No agents match</Trans>
        </CommandEmpty>
      </CommandList>
    </Command>
  );
}

export function AgentPicker({
  agents,
  value,
  onChange,
}: {
  agents: Agent[];
  value: string;
  onChange: (id: string) => void;
}) {
  return (
    <select aria-label={t`Agent`} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{t`Choose an agent`}</option>
      {agents.map((a) => (
        <option key={a.id} value={a.id}>
          {a.name}
        </option>
      ))}
    </select>
  );
}
