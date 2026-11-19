// The composer's / commands on mobile, as on Web (conversation/commands.tsx), from the shared
// rules in packages/core (composer-commands): the six commands a chat offers, then the agent's
// enabled skills. «مهمة», «بحث», «ملخص» and a skill are sent as the owner's message with its
// command; «شارت», «اتصال» and «مسح» open what the chat already has. A command grants nothing.
import {
  availableCommands,
  COMMAND_ALIAS,
  type CommandId,
  type CommandOption,
  foldSearch,
} from "@lonora/core";
import { fill, type Label } from "./i18n";

export type CommandRow = CommandOption & { hint?: string };
export type Skill = {
  id: string;
  payload: { name: string; enabled?: boolean; manifest?: { description?: string } };
};

const NAMES: Record<CommandId, Label> = {
  task: "cmdTask",
  search: "cmdSearch",
  summary: "cmdSummary",
  chart: "cmdChart",
  call: "cmdCall",
  clear: "cmdClear",
};

export function commandRows(
  t: (key: Label) => string,
  chat: {
    group: boolean;
    symbol?: string | null;
    trading: boolean;
    name: string;
    callable: boolean;
  },
  skills: readonly Skill[],
): CommandRow[] {
  const subs: Record<CommandId, string> = {
    task: t("cmdTaskSub"),
    search: t("cmdSearchSub"),
    summary: t("cmdSummarySub"),
    chart:
      !chat.group && chat.symbol ? fill(t("cmdChartSymbolSub"), chat.symbol) : t("cmdChartSub"),
    call: fill(t("cmdCallSub"), chat.name),
    clear: t("cmdClearSub"),
  };
  const hints: Partial<Record<CommandId, string>> = {
    task: t("cmdTaskHint"),
    search: t("cmdSearchHint"),
  };
  const taken = new Set(
    (Object.keys(NAMES) as CommandId[]).flatMap((id) => [
      foldSearch(t(NAMES[id])),
      COMMAND_ALIAS[id],
    ]),
  );
  return [
    ...availableCommands({
      group: chat.group,
      chart: chat.group || Boolean(chat.symbol) || chat.trading,
      call: chat.callable,
    }).map((id) => ({
      id,
      command: id,
      name: t(NAMES[id]),
      alias: COMMAND_ALIAS[id],
      sub: subs[id],
      argument: id in hints,
      hint: hints[id],
    })),
    ...skills
      // A skill named like a command would be sent as that command: it is not offered here.
      .filter((row) => row.payload.enabled !== false && !taken.has(foldSearch(row.payload.name)))
      .map((row) => ({
        id: row.id,
        command: "skill" as const,
        name: row.payload.name,
        sub: row.payload.manifest?.description,
        argument: true,
        hint: t("cmdSkillHint"),
      })),
  ];
}

/** The command a send carries, when the typed command is one that is sent. */
export function sentCommand(row: CommandRow, argument: string) {
  return row.command === "task" ||
    row.command === "search" ||
    row.command === "summary" ||
    row.command === "skill"
    ? {
        name: row.command,
        argument,
        ...(row.command === "skill" ? { skill_id: row.id } : {}),
      }
    : null;
}
