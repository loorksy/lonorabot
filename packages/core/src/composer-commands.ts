/**
 * The composer's / commands (reference commandOptions, assistUpdate and parseCommand,
 * Desktop-37 5089-5213), without their labels: the caller gives each option its name in the
 * owner's language. A command is the first thing in a message; it grants nothing.
 */
import { foldSearch } from "./search-fold";

export type CommandId =
  | "task"
  | "search"
  | "summary"
  | "schedule"
  | "chart"
  | "call"
  | "permission"
  | "clear";
/** The English name of each command, typed in any language. */
export const COMMAND_ALIAS: Record<CommandId, string> = {
  task: "task",
  search: "search",
  summary: "summary",
  schedule: "schedule",
  chart: "chart",
  call: "call",
  permission: "permissions",
  clear: "clear",
};
export type CommandOption = {
  /** The command's id, or a skill's resource id. */
  id: string;
  command: CommandId | "skill";
  /** The name the list shows and the owner types after «/». */
  name: string;
  alias?: string;
  sub?: string;
  /** Whether text follows the command (a task's title, a search, what a skill applies to). */
  argument: boolean;
};
const MARKS = "‎‏";

/** The query after a «/» that starts the message (bidi marks allowed), else null. */
export function commandQuery(beforeCaret: string): string | null {
  return new RegExp(`^[${MARKS}]*/([^\\s/]*)$`).exec(beforeCaret)?.[1] ?? null;
}

/** The built-in commands a chat offers, in the reference's order. A task is one agent's. */
export function availableCommands(chat: {
  group: boolean;
  trading: boolean;
  chart: boolean;
  call: boolean;
}): CommandId[] {
  const offered: [CommandId, boolean][] = [
    ["task", !chat.group],
    ["search", true],
    ["summary", true],
    ["schedule", true],
    ["chart", chat.chart],
    ["call", !chat.group && chat.call],
    ["permission", chat.group || chat.trading],
    ["clear", true],
  ];
  return offered.filter(([, shown]) => shown).map(([id]) => id);
}

function score(option: CommandOption, query: string): number | null {
  const name = foldSearch(option.name);
  if (name.startsWith(query)) return 1;
  if (
    foldSearch(option.alias ?? "")
      .split(" ")
      .some((word) => word.startsWith(query))
  )
    return 1.5;
  if (name.split(" ").some((word) => word.startsWith(query))) return 2;
  if (name.includes(query)) return 3;
  return foldSearch(option.sub ?? "").includes(query) ? 4 : null;
}

/**
 * The options a query matches: commands before skills, then the better match, then the given
 * order. Null when the query has run past a whole name, so the list closes.
 */
export function rankCommands<T extends CommandOption>(options: T[], query: string): T[] | null {
  const wanted = foldSearch(query);
  if (!wanted) return options;
  const ranked = options
    .map((option, index) => ({ option, index, score: score(option, wanted) }))
    .filter((row): row is typeof row & { score: number } => row.score !== null)
    .sort(
      (a, b) =>
        Number(a.option.command === "skill") - Number(b.option.command === "skill") ||
        a.score - b.score ||
        a.index - b.index,
    )
    .map((row) => row.option);
  const finished = options.some((option) =>
    [option.name, option.alias ?? ""].some((label) => {
      const full = foldSearch(label);
      return full && wanted.length > full.length && wanted.startsWith(full);
    }),
  );
  return !ranked.length && finished ? null : ranked;
}

/** How much of `body` spells `label`, ending at a space or the end; null when it does not. */
function typed(body: string, label: string): number | null {
  const full = foldSearch(label);
  for (let end = 1; full && end <= body.length; end++) {
    const folded = foldSearch(body.slice(0, end));
    if (folded.length > full.length) return null;
    if (folded === full && (end === body.length || /\s/.test(body[end]))) return end;
  }
  return null;
}

/**
 * A message that is a command: its option, the text after it, and where the typed command
 * ends in `text`. The longest name or alias wins. A command that takes no text is not one
 * when text follows it, so nothing the owner typed is dropped.
 */
export function parseCommand<T extends CommandOption>(
  text: string,
  options: T[],
): { option: T; argument: string; start: number; end: number } | null {
  const start = new RegExp(`^[${MARKS}\\s]*`).exec(text)?.[0].length ?? 0;
  if (text[start] !== "/") return null;
  const body = text.slice(start + 1);
  const labels = options
    .flatMap((option) => [option.name, option.alias ?? ""].map((label) => ({ option, label })))
    .sort((a, b) => foldSearch(b.label).length - foldSearch(a.label).length);
  for (const { option, label } of labels) {
    const length = typed(body, label);
    if (length === null) continue;
    const argument = body.slice(length).trim();
    return argument && !option.argument
      ? null
      : { option, argument, start, end: start + 1 + length };
  }
  return null;
}
