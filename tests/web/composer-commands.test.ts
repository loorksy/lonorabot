import assert from "node:assert/strict";
import test from "node:test";
import {
  availableCommands,
  COMMAND_ALIAS,
  type CommandOption,
  commandQuery,
  parseCommand,
  rankCommands,
} from "../../packages/core/src/composer-commands";
import {
  commandPart,
  pendingVoiceRich,
  validateAgentRichContent,
} from "../../packages/core/src/message-parts";
import { validateRichContent } from "../../packages/core/src/visual-response";

/* The composer's / commands (reference Desktop-37 5089-5213): the trigger, which commands a
   chat offers, the ranking of the list, and which message is a command. */
const builtin = (command: CommandOption["command"], name: string, argument = false, sub = "") =>
  ({
    id: command,
    command,
    name,
    alias: COMMAND_ALIAS[command as keyof typeof COMMAND_ALIAS],
    sub,
    argument,
  }) satisfies CommandOption;
const OPTIONS: CommandOption[] = [
  builtin("task", "مهمة", true, "حوّل طلبك إلى مهمة يتابعها الوكيل"),
  builtin("search", "بحث", true, "ابحث في الويب ثم أجب مع المصادر"),
  builtin("summary", "ملخص", false, "لخّص هذه المحادثة"),
  builtin("schedule", "جدولة"),
  builtin("call", "اتصال"),
  builtin("clear", "مسح"),
  { id: "s1", command: "skill", name: "موجز الأخبار", sub: "تلخيص الأخبار", argument: true },
  { id: "s2", command: "skill", name: "بحث متقدم", argument: true },
];
const names = (rows: CommandOption[] | null) => rows?.map((row) => row.name);

test("a «/» opens the list only as the first thing in the message", () => {
  assert.equal(commandQuery("/"), "");
  assert.equal(commandQuery("‏/مل"), "مل");
  assert.equal(commandQuery("hi /x"), null);
  assert.equal(commandQuery("/بحث "), null);
  assert.equal(commandQuery("//"), null);
  assert.equal(commandQuery(""), null);
});

test("a chat offers the commands that work in it, in the reference's order", () => {
  assert.deepEqual(availableCommands({ group: false, trading: true, chart: true, call: true }), [
    "task",
    "search",
    "summary",
    "schedule",
    "chart",
    "call",
    "permission",
    "clear",
  ]);
  // A task and a call are one agent's; a group has its members' permissions.
  assert.deepEqual(availableCommands({ group: true, trading: false, chart: true, call: true }), [
    "search",
    "summary",
    "schedule",
    "chart",
    "permission",
    "clear",
  ]);
  assert.deepEqual(availableCommands({ group: false, trading: false, chart: false, call: false }), [
    "task",
    "search",
    "summary",
    "schedule",
    "clear",
  ]);
});

test("the list keeps what the query matches: commands first, the better match first", () => {
  assert.deepEqual(names(rankCommands(OPTIONS, "")), names(OPTIONS));
  assert.deepEqual(names(rankCommands(OPTIONS, "مل")), ["ملخص"]);
  // The English name finds a command in any language, and folding ignores hamza and ta marbuta.
  assert.deepEqual(names(rankCommands(OPTIONS, "sea")), ["بحث"]);
  assert.deepEqual(names(rankCommands(OPTIONS, "اتصا")), ["اتصال"]);
  assert.deepEqual(names(rankCommands(OPTIONS, "جدوله")), ["جدولة"]);
  // «بح» starts the command and the skill; a word inside a skill's name comes after.
  assert.deepEqual(names(rankCommands(OPTIONS, "بح")), ["بحث", "بحث متقدم"]);
  assert.deepEqual(names(rankCommands(OPTIONS, "الاخبار")), ["موجز الأخبار"]);
  // The sub line is searched last.
  assert.deepEqual(names(rankCommands(OPTIONS, "المصادر")), ["بحث"]);
  assert.deepEqual(rankCommands(OPTIONS, "zz"), []);
  // Past a whole name with nothing left to match, the list closes.
  assert.equal(rankCommands(OPTIONS, "بحثعن"), null);
  assert.equal(rankCommands(OPTIONS, "searching"), null);
});

test("a message is a command by its name or its English name, the longest first", () => {
  const search = parseCommand("/بحث أسعار الذهب", OPTIONS);
  assert.equal(search?.option.command, "search");
  assert.equal(search?.argument, "أسعار الذهب");
  assert.deepEqual([search?.start, search?.end], [0, 4]);
  assert.equal(parseCommand("/search gold", OPTIONS)?.option.command, "search");
  assert.equal(parseCommand("/SEARCH gold", OPTIONS)?.argument, "gold");
  // Bidi marks and spaces before «/» are not part of the command.
  const marked = parseCommand("‏ /بَحث الذهب", OPTIONS);
  assert.deepEqual([marked?.option.command, marked?.start, marked?.end], ["search", 2, 7]);
  assert.equal(parseCommand("/بحثعن", OPTIONS), null);
  assert.equal(parseCommand("بحث /بحث", OPTIONS), null);
  assert.equal(parseCommand("/foo bar", OPTIONS), null);
  // No text yet: still the command, for the caller to ask for the text.
  assert.equal(parseCommand("/مهمة", OPTIONS)?.argument, "");
  assert.equal(parseCommand("/ملخص ", OPTIONS)?.option.command, "summary");
  // A command that takes no text is an ordinary message when text follows: nothing is dropped.
  assert.equal(parseCommand("/ملخص لهذا الأسبوع", OPTIONS), null);
  assert.equal(parseCommand("/clear now", OPTIONS), null);
  const skill = parseCommand("/موجز الأخبار اليوم", OPTIONS);
  assert.deepEqual([skill?.option.id, skill?.argument, skill?.end], ["s1", "اليوم", 13]);
  assert.equal(parseCommand("/بحث متقدم x", OPTIONS)?.option.id, "s2");
});

test("the command part is the server's: kept on an owner message, never on a reply", () => {
  const part = { type: "command", name: "search", argument: "أسعار الذهب", skill_id: null };
  const rich = { version: 1, parts: [part] };
  assert.deepEqual(commandPart({ rich_content: rich as never }), { ...part, skill_name: null });
  assert.equal(validateAgentRichContent(rich), null);
  assert.equal(validateRichContent({ version: 1, parts: [{ ...part, name: "clear" }] }), null);
  assert.equal(validateRichContent({ version: 1, parts: [{ ...part, extra: 1 }] }), null);
  // The text is counted in code points, as the server counts it.
  const emoji = { ...part, argument: "😀".repeat(20000) };
  assert.equal(validateRichContent({ version: 1, parts: [emoji] })?.parts.length, 1);
  const over = { ...part, argument: "x".repeat(30001) };
  assert.equal(validateRichContent({ version: 1, parts: [over] }), null);
  // A sending bubble draws the chip from its body.
  const pending = pendingVoiceRich({ command: { name: "task", argument: "راقب الذهب" } });
  assert.equal(commandPart({ rich_content: pending })?.name, "task");
  assert.equal(pendingVoiceRich({ content: "plain" }), null);
});
