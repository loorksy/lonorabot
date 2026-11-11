import { t } from "@lingui/core/macro";
import type { CommandPart } from "@lonora/contracts";
import { availableCommands, COMMAND_ALIAS, type CommandId, type CommandOption } from "@lonora/core";
import { Icon, type IconName } from "@lonora/ui-web";
import type { Agent } from "../lib/api";
import { useCallStarter } from "../shell/call/CallPages";
import { domainApi } from "../shell/domain/api";
import { useLoad } from "../shell/domain/hooks";
import { useNavigation } from "../shell/navigation";

/* The composer's / commands (reference commandOptions and runCommand, Desktop-37 5089-5104,
   5192-5199): the eight commands a chat offers, then the agent's enabled skills. «مهمة»,
   «بحث», «ملخص» and a skill are sent as the owner's message; the others open what the chat
   already has (the schedule page, the chart, the call, the permissions, the clear confirm). */
export type CommandRow = CommandOption & { icon: IconName; hint?: string };

const ICONS: Record<CommandId, IconName> = {
  task: "task",
  search: "globe",
  summary: "news",
  schedule: "clock",
  chart: "chart",
  call: "phone",
  permission: "shield",
  clear: "trash",
};

function commandName(id: CommandId): string {
  if (id === "task") return t({ message: "task", context: "slash command" });
  if (id === "search") return t({ message: "search", context: "slash command" });
  if (id === "summary") return t({ message: "summary", context: "slash command" });
  if (id === "schedule") return t({ message: "schedule", context: "slash command" });
  if (id === "chart") return t({ message: "chart", context: "slash command" });
  if (id === "call") return t({ message: "call", context: "slash command" });
  if (id === "permission") return t({ message: "permissions", context: "slash command" });
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
  const nav = useNavigation();
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
    schedule: t`One time or repeating`,
    chart: !isGroup && symbol ? t`Open the ${symbol} chart` : t`Open the market chart`,
    call: t`Start a voice call with ${name}`,
    permission: isGroup ? t`Group members' permissions` : t`Change the agent's permissions`,
    clear: t`Clear this conversation's messages`,
  };
  const hints: Partial<Record<CommandId, string>> = {
    task: t`Task title`,
    search: t`What are you looking for?`,
  };
  const rows: CommandRow[] = [
    ...availableCommands({
      group: isGroup,
      trading,
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
      .filter((row) => row.payload.enabled !== false)
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
  const run = (command: CommandRow["command"], form: HTMLFormElement | null) => {
    if (command === "schedule")
      nav.go(
        `/app/new-schedule${agent && !isGroup ? `?agent=${encodeURIComponent(agent.id)}` : ""}`,
      );
    else if (command === "chart") window.dispatchEvent(new CustomEvent("lonora:open-chart"));
    else if (command === "call") {
      // Through the call's own start: without a voice provider it explains how to set one up.
      if (agent) void starter.start(agent, threadId);
    } else if (command === "permission") {
      if (isGroup) window.dispatchEvent(new CustomEvent("lonora:members-permissions"));
      else
        requestAnimationFrame(() => form?.querySelector<HTMLButtonElement>(".mode-chip")?.click());
    } else if (command === "clear") window.dispatchEvent(new CustomEvent("lonora:clear-chat"));
  };
  return { rows, run };
}
