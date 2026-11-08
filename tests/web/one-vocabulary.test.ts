import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import test from "node:test";
import { showsTradingControl } from "../../packages/core/src/agent-permission";
import {
  approvalStatusText,
  brokerTicketLabel,
  operationStatusText,
  runStatusText,
} from "../../packages/core/src/financial-boundary";
import { peerOutcome } from "../../packages/core/src/peer-outcome";
import { activityCallLabel } from "../../packages/core/src/turn-activity";

const root = new URL("../../", import.meta.url);
const read = (path: string) => readFileSync(new URL(path, root), "utf8");
const retired = [/super ?bot/i, /سوبر ?بوت/, /emergency stop/i, /الإيقاف الطارئ/];

/** Active (not obsolete) msgid/msgstr texts of a Lingui catalog. */
function catalog(path: string): string[] {
  return read(path)
    .split("\n\n")
    .filter((entry) => !entry.startsWith("#~"))
    .flatMap((entry) => [...entry.matchAll(/^msg(?:id|str) "(.*)"$/gm)].map((match) => match[1]));
}

test("no owner-visible text names the retired Super Bot or an Emergency Stop", () => {
  const texts = [
    ...catalog("apps/web/src/i18n/locales/en/messages.po"),
    ...catalog("apps/web/src/i18n/locales/ar/messages.po"),
    // Mobile labels are [Arabic, English] pairs; every quoted literal is checked.
    ...[...read("apps/mobile/lib/i18n.ts").matchAll(/"((?:[^"\\]|\\.)*)"/g)].map((m) => m[1]),
    ...Object.values(
      JSON.parse(read("packages/bus/src/lonora_bus/attention_messages.json")) as Record<
        string,
        Record<string, string>
      >,
    ).flatMap((language) => Object.values(language)),
  ];
  assert.ok(texts.length > 1000, "the catalogs were read");
  for (const text of texts)
    for (const pattern of retired) assert.doesNotMatch(text, pattern, `owner-visible: ${text}`);
  // The shared label tables (core) are owner-visible on both clients too.
  for (const file of readdirSync(new URL("packages/core/src/", root))) {
    if (!file.endsWith(".ts")) continue;
    const source = read(`packages/core/src/${file}`)
      .split("\n")
      .filter((line) => !line.trimStart().startsWith("//") && !line.trimStart().startsWith("*"))
      .join("\n");
    for (const literal of source.matchAll(/"((?:[^"\\]|\\.)*)"/g))
      for (const pattern of retired) assert.doesNotMatch(literal[1], pattern, file);
  }
});

test("Web and Mobile read operation and approval labels from the one shared table", () => {
  for (const status of ["pending", "approved", "rejected", "cancelled", "expired", "completed"]) {
    assert.ok(approvalStatusText(status, "en") && approvalStatusText(status, "ar"));
    assert.notEqual(approvalStatusText(status, "en"), approvalStatusText(status, "ar"));
  }
  assert.equal(approvalStatusText("approved", "en"), "Approved — awaiting broker result");
  assert.equal(approvalStatusText("approved", "ar"), "تمت الموافقة — بانتظار نتيجة الوسيط");
  assert.equal(brokerTicketLabel("ar-SA"), "تذكرة الوسيط");
  assert.equal(operationStatusText("ambiguous", {}, "ar"), "نتيجة غير مؤكدة — لن تُرسل مجددًا");
  // Neither client keeps its own copy of these labels.
  const web = read("apps/web/src/lib/operation-status.ts");
  assert.match(web, /operationStatusText\(/);
  assert.doesNotMatch(web, /Awaiting broker confirmation/);
  assert.match(read("apps/web/src/components/trading/TradeApprovals.tsx"), /approvalStatusText\(/);
  assert.match(read("apps/mobile/components/trade-approval.tsx"), /approvalStatusText\(/);
  const mobile = read("apps/mobile/lib/i18n.ts");
  for (const key of ["approved", "confirmed", "ambiguous", "submitted", "brokerResult"])
    assert.doesNotMatch(mobile, new RegExp(`^  ${key}: \\[`, "m"), key);
  // Run statuses too: one wording on both clients, in both languages.
  assert.equal(runStatusText("waiting_input", "ar"), "بانتظار ردك");
  assert.equal(runStatusText("waiting_takeover", "en"), "Waiting to resume");
  for (const file of [
    "apps/web/src/pages/ActivityList.tsx",
    "apps/web/src/pages/shell/sidebar-activity.tsx",
    "apps/mobile/app/thread.tsx",
    "apps/mobile/app/index.tsx",
    "apps/mobile/components/WorkingIndicator.tsx",
  ]) {
    assert.match(read(file), /runStatusText\(/, file);
    assert.doesNotMatch(read(file), /t\(run\.status\)|Waiting for handover/, file);
  }
});

test("activity rows say what the agent does from registry metadata, never a raw tool id", () => {
  assert.equal(
    activityCallLabel({ toolset: "trading", effect: "financial" }, "en"),
    "Placing a trade action",
  );
  assert.equal(activityCallLabel({ toolset: "trading", effect: "read" }, "en"), "Checking trades");
  assert.equal(activityCallLabel({ toolset: "research", effect: "read" }, "ar"), "يبحث في المصادر");
  assert.equal(activityCallLabel({ toolset: "memory", effect: "change" }, "ar"), "يحفظ في الذاكرة");
  // A family without a separate change label keeps its read label; nothing falls to the id.
  assert.equal(
    activityCallLabel({ toolset: "account", effect: "change" }, "en"),
    "Reading the account",
  );
  assert.equal(activityCallLabel({}, "en"), "Using a tool");
  assert.equal(activityCallLabel({ toolset: "unknown_family" }, "ar"), "يستخدم أداة");
});

test("the trading control appears only for an agent that can trade", () => {
  const research = { role: "general", trading_account_id: null, level: "analysis" as const };
  assert.equal(showsTradingControl(research), false);
  assert.equal(showsTradingControl({ ...research, role: "personal" }), true);
  assert.equal(showsTradingControl({ ...research, trading_account_id: "account" }), true);
  assert.equal(showsTradingControl({ ...research, level: "supervised" }), true);
  assert.equal(showsTradingControl({ ...research, grants: 1 }), true);
  assert.equal(showsTradingControl({ ...research, pendingTrade: true }), true);
});

test("a colleague's result is shown without its machine wrapper", () => {
  const wrapped =
    "<peer_outcome run_id='run-1' status='completed'>\nGold held 2410.\n</peer_outcome>";
  assert.deepEqual(peerOutcome(wrapped), { body: "Gold held 2410.", status: "completed" });
  assert.deepEqual(peerOutcome("Plain reply"), { body: "Plain reply" });
});
