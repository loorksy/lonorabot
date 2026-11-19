import { t } from "@lingui/core/macro";
import type { CommandPart } from "@lonora/contracts";
import {
  availableCommands,
  COMMAND_ALIAS,
  type CommandId,
  type CommandOption,
  foldSearch,
} from "@lonora/core";
import { Icon, type IconName } from "@lonora/ui-web";
import type { Agent } from "../lib/api";
import { useCallStarter } from "../shell/call/CallPages";
import { domainApi } from "../shell/domain/api";
import { useLoad } from "../shell/domain/hooks";

/* The composer's / commands (reference commandOptions and runCommand, Desktop-37 5089-5104,
   5192-5199): the six commands a chat offers, then the agent's enabled skills. «مهمة»,
   «بحث», «ملخص» and a skill are sent as the owner's message; the others open what the chat
   already has (the chart, the call, the clear confirm). */
export type CommandRow = CommandOption & { icon: IconName; hint?: string };

const ICONS: Record<CommandId, IconName> = {
  task: "task",
  search: "globe",
  summary: "news",
  chart: "chart",
  call: "phone",
  clear: "trash",
};

function commandName(id: CommandId): string {
  if (id === "task") return t({ message: "task", context: "slash command" });
  if (id === "search") return t({ message: "search", context: "slash command" });
  if (id === "summary") return t({ message: "summary", context: "slash command" });
  if (id === "chart") return t({ message: "chart", context: "slash command" });
  if (id === "call") return t({ message: "call", context: "slash command" });
  return t({ message: "clear", context: "slash command" });
}

/** The chip of a sent command, from what the server kept of it; a skill shows its name. */
export function CommandChip({ part }: { part: CommandPart }) {
  return (
    <span className="cmd-chip">
      <Icon name={part.name === "skill" ? "bolt" : ICONS[part.name]} />
      <span dir="auto">
        {part.name === "skill"
          ? part.skill_name || t({ message: "skill", context: "slash command" })
          : commandName(part.name)}
      </span>
    </span>
  );
}

export function useComposerCommands({
  threadId,
  agent,
  name,
  isGroup,
  trading,
  wanted,
}: {
  threadId: string;
  agent?: Agent;
  name: string;
  isGroup: boolean;
  trading: boolean;
  /** The owner has typed «/» in this chat: the agent's skills are loaded then, not before. */
  wanted: boolean;
}) {
  const starter = useCallStarter();
  const skills = useLoad(
    agent && !isGroup && wanted ? () => domainApi.skills(agent.id) : null,
    `skills:${agent?.id}`,
  );
  const symbol = agent?.trading_symbol;
  const subs: Record<CommandId, string> = {
    task: t`Turn your request into a task the agent follows`,
    search: t`Search the web, then answer with sources`,
    summary: t`Summarize this conversation`,
    chart: !isGroup && symbol ? t`Open the ${symbol} chart` : t`Open the market chart`,
    call: t`Start a voice call with ${name}`,
    clear: t`Clear this conversation's messages`,
  };
  const hints: Partial<Record<CommandId, string>> = {
    task: t`Task title`,
    search: t`What are you looking for?`,
  };
  const taken = new Set(
    (Object.keys(ICONS) as CommandId[]).flatMap((id) => [
      foldSearch(commandName(id)),
      COMMAND_ALIAS[id],
    ]),
  );
  const rows: CommandRow[] = [
    ...availableCommands({
      group: isGroup,
      chart: isGroup || Boolean(symbol) || trading,
      call: Boolean(agent) && !agent?.paused,
    }).map((id) => ({
      id,
      command: id,
      name: commandName(id),
      alias: COMMAND_ALIAS[id],
      sub: subs[id],
      argument: id in hints,
      icon: ICONS[id],
      hint: hints[id],
    })),
    ...(skills.data ?? [])
      // A skill named like a command would be sent as that command: it is not offered here.
      .filter((row) => row.payload.enabled !== false && !taken.has(foldSearch(row.payload.name)))
      .map((row) => ({
        id: row.id,
        command: "skill" as const,
        name: row.payload.name,
        sub: row.payload.manifest?.description,
        argument: true,
        icon: "bolt" as const,
        hint: t`Apply it to what? (optional)`,
      })),
  ];
  /** Opens what a command that sends nothing stands for. */
  const run = (command: CommandRow["command"]) => {
    if (command === "chart") window.dispatchEvent(new CustomEvent("lonora:open-chart"));
    else if (command === "call") {
      // Through the call's own start: without a voice provider it explains how to set one up.
      if (agent) void starter.start(agent, threadId);
    } else if (command === "clear") window.dispatchEvent(new CustomEvent("lonora:clear-chat"));
  };
  return { rows, run };
}
