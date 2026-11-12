// The composer's / commands on mobile, as on Web: what a chat offers, Arabic names typed or
// the English alias, skills after the commands, and what a send carries.
import assert from "node:assert/strict";
import test from "node:test";
import { commandRows, sentCommand } from "../../apps/mobile/lib/commands";
import { translate } from "../../apps/mobile/lib/i18n";
import { parseCommand, rankCommands } from "../../packages/core/src/composer-commands";

const ar = (key: Parameters<typeof translate>[1]) => translate("ar", key);
const chat = { group: false, symbol: "XAUUSD", trading: true, name: "وكيل الذهب", callable: true };
const skills = [
  { id: "s1", payload: { name: "تحليل الذهب", manifest: { description: "Read gold" } } },
  { id: "s2", payload: { name: "off", enabled: false } },
  { id: "s3", payload: { name: "مهمة" } },
];

test("a direct chat offers the six commands, then its enabled skills not named like a command", () => {
  const rows = commandRows(ar, chat, skills);
  assert.deepEqual(
    rows.map((row) => row.command),
    ["task", "search", "summary", "chart", "call", "clear", "skill"],
  );
  assert.equal(rows[0].name, "مهمة");
  assert.equal(rows[3].sub, "افتح شارت XAUUSD");
  assert.equal(rows[6].id, "s1");
});

test("a group has no task and no call; a paused agent no call; no symbol and no trading, no chart", () => {
  assert.deepEqual(
    commandRows(ar, { ...chat, group: true }, []).map((row) => row.command),
    ["search", "summary", "chart", "clear"],
  );
  assert.deepEqual(
    commandRows(ar, { ...chat, symbol: null, trading: false, callable: false }, []).map(
      (row) => row.command,
    ),
    ["task", "search", "summary", "clear"],
  );
});

test("typed in Arabic or by its English alias; a send carries what was asked", () => {
  const rows = commandRows(ar, chat, skills);
  assert.equal(rankCommands(rows, "مه")?.[0].command, "task");
  assert.equal(rankCommands(rows, "sea")?.[0].command, "search");
  const task = parseCommand("/مهمة راقب 2,425", rows);
  assert.ok(task);
  assert.equal(task.option.command, "task");
  assert.deepEqual(sentCommand(task.option, task.argument), {
    name: "task",
    argument: "راقب 2,425",
  });
  const skill = parseCommand("/تحليل الذهب اليوم", rows);
  assert.ok(skill);
  assert.deepEqual(sentCommand(skill.option, skill.argument), {
    name: "skill",
    argument: "اليوم",
    skill_id: "s1",
  });
  // A command that sends nothing is run, not sent; with text after it, it is no command.
  const chart = parseCommand("/شارت", rows);
  assert.ok(chart);
  assert.equal(sentCommand(chart.option, ""), null);
  assert.equal(parseCommand("/شارت الذهب", rows), null);
});
