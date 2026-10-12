// Adapted for Lonora from Tampletgrok pages/shell/command-palette.tsx; Apache-2.0.
import { Trans, useLingui } from "@lingui/react/macro";
import {
  AgentAvatar,
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandShortcut,
} from "@lonora/ui-web";
import { useEffect, useMemo, useState } from "react";
import type { Agent } from "../../lib/api";

export function SwitchAgentDialog({
  open,
  onOpenChange,
  agents,
  onSelectAgent,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agents: Agent[];
  onSelectAgent: (agentId: string) => void;
}) {
  const { t } = useLingui();
  const [search, setSearch] = useState("");
  const modKey = /Mac|iPhone|iPad|iPod/i.test(navigator.platform || navigator.userAgent)
    ? "⌘"
    : "Ctrl";
  const filteredAgents = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    return agents.filter((agent) => !needle || agent.name.toLocaleLowerCase().includes(needle));
  }, [agents, search]);

  useEffect(() => {
    if (!open) setSearch("");
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (!(event.metaKey || event.ctrlKey) || event.altKey || event.shiftKey || event.repeat)
        return;
      if (!/^[1-9]$/.test(event.key)) return;
      const agent = filteredAgents[Number(event.key) - 1];
      if (!agent) return;
      event.preventDefault();
      onSelectAgent(agent.id);
      onOpenChange(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [filteredAgents, onOpenChange, onSelectAgent, open]);

  return (
    <CommandDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t`Switch agent`}
      description={t`Search agents and switch conversations`}
      className="tpl-switch-dialog"
    >
      <Command shouldFilter={false} data-testid="switch-agent-dialog">
        <CommandInput
          value={search}
          onValueChange={setSearch}
          placeholder={t`Search agents`}
          aria-label={t`Search agents`}
          data-testid="switch-agent-search"
        />
        <CommandList>
          <CommandEmpty>
            <Trans>No agents match</Trans>
          </CommandEmpty>
          <CommandGroup>
            {filteredAgents.map((agent, index) => (
              <CommandItem
                key={agent.id}
                value={agent.id}
                onSelect={() => {
                  onSelectAgent(agent.id);
                  onOpenChange(false);
                }}
                className="tpl-switch-row"
                data-testid={`switch-agent-${agent.id}`}
              >
                <AgentAvatar
                  name={agent.name}
                  color={agent.color}
                  shape={agent.avatar}
                  className="tpl-roster-avatar"
                />
                <span className="tpl-truncate" dir="auto">
                  {agent.name}
                </span>
                {index < 9 ? (
                  <CommandShortcut>
                    <kbd dir="ltr">{`${modKey}${index + 1}`}</kbd>
                  </CommandShortcut>
                ) : null}
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
      </Command>
    </CommandDialog>
  );
}
