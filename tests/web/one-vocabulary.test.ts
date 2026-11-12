import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import test from "node:test";
import { showsTradingControl } from "../../packages/core/src/agent-permission";
import {
  approvalStatusText,
  brokerTicketLabel,
  financialBoundaryError,
  financialResultReason,
  operationStatusText,
  runStatusText,
} from "../../packages/core/src/financial-boundary";
import { peerOutcome } from "../../packages/core/src/peer-outcome";
import { activityCallLabel } from "../../packages/core/src/turn-activity";

const root = new URL("../../", import.meta.url);
const read = (path: string) => readFileSync(new URL(path, root), "utf8");
const retired = [
  /super ?bot/i,
  /سوبر ?بوت/,
  /emergency stop/i,
  /الإيقاف الطارئ/,
  // Amendment 1: Lonora has no Stop control.
  /stop new trading/i,
  /resume trading/i,
  /start trading/i,
  /استئناف التداول/,
  /بدء التداول/,
];

/** Active (not obsolete) msgid/msgstr texts of a Lingui catalog. */
function catalog(path: string): string[] {
  return read(path)
    .split("\n\n")
    .filter((entry) => !entry.startsWith("#~"))
    .flatMap((entry) => [...entry.matchAll(/^msg(?:id|str) "(.*)"$/gm)].map((match) => match[1]));
}

test("no owner-visible text names the retired Super Bot, an Emergency Stop or a Stop control", () => {
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
    "apps/mobile/app/thread.tsx",
    "apps/mobile/app/(tabs)/tasks.tsx",
    "apps/mobile/components/WorkingIndicator.tsx",
  ]) {
    assert.match(read(file), /runStatusText\(/, file);
    assert.doesNotMatch(read(file), /t\(run\.status\)|Waiting for handover/, file);
  }
});

test("an uncertain broker result never tells the owner to try again, on either client", () => {
  const codes = [
    "broker_result_ambiguous",
    "execution_interrupted_after_send",
    "broker_result_mismatch",
    "operation_in_progress",
    // A LonoraError raised after the send boundary is recorded as uncertain with its code.
    "broker_connection_unavailable",
    "broker_disabled",
  ];
  for (const code of codes) {
    const en = financialResultReason("ambiguous", code, "en");
    const ar = financialResultReason("ambiguous", code, "ar-SA");
    assert.match(en ?? "", /will not be sent again/, code);
    assert.match(ar ?? "", /لن يُرسل/, code);
    for (const text of [en ?? "", ar ?? ""]) {
      assert.doesNotMatch(text, /try again|retry|was not sent|so this was not sent/i, code);
      assert.doesNotMatch(text, /أعد المحاولة|حاول|لم يُرسل/, code);
    }
  }
  assert.equal(
    financialResultReason("ambiguous", null, "en"),
    financialResultReason("ambiguous", "broker_result_ambiguous", "en"),
  );
  // A known not-sent cause keeps its reason; a settled or confirmed result needs none.
  assert.equal(
    financialResultReason("failed", "risk_daily_loss_limit", "ar"),
    financialBoundaryError("risk_daily_loss_limit", "ar"),
  );
  assert.equal(financialResultReason("failed", "unknown_code", "en"), null);
  assert.equal(financialResultReason("confirmed", "target_state_matched", "en"), null);
  assert.equal(financialResultReason("resolved", "owner_attested_executed", "en"), null);
  // Both approval cards read this one lookup.
  for (const file of [
    "apps/web/src/components/trading/TradeApprovals.tsx",
    "apps/mobile/components/trade-approval.tsx",
  ])
    assert.match(read(file), /financialResultReason\(result\.status, result\.code/, file);
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
  // Labels checked against the live registry: each states the action the tool takes.
  const cases: [string, string, "read" | "change" | "financial", string, string][] = [
    ["owner_notify", "voice", "change", "Notifying you", "يرسل لك تنبيهًا"],
    ["owner_call_request", "voice", "change", "Preparing a call", "يجهّز اتصالًا"],
    ["owner_attention_list", "voice", "read", "Checking what needs you", "يراجع ما ينتظرك"],
    ["owner_action_propose", "trading", "change", "Preparing a card for you", "يجهّز بطاقة لك"],
    [
      "trade_restriction_create",
      "trading",
      "change",
      "Updating trading safeguards",
      "يحدّث ضوابط التداول",
    ],
    ["wait_for_input", "tasks", "change", "Waiting for your reply", "ينتظر ردك"],
    ["market_position_size", "trading", "read", "Sizing a position", "يحسب حجم المركز"],
    ["skill_package_create", "memory", "change", "Working on a skill", "يعمل على مهارة"],
    ["skills_list", "memory", "read", "Reviewing skills", "يراجع المهارات"],
    ["memory_write", "memory", "change", "Saving to memory", "يحفظ في الذاكرة"],
    ["market_decision_record", "intelligence", "change", "Recording analysis", "يسجّل التحليل"],
    ["model_request", "intelligence", "change", "Changing its model", "يغيّر نموذجه"],
    ["model_list", "intelligence", "read", "Checking its models", "يراجع نماذجه"],
    ["agent_create", "collaboration", "change", "Creating an agent", "ينشئ وكيلًا"],
    ["agent_inspect", "collaboration", "read", "Reviewing an agent's work", "يراجع عمل وكيل"],
    ["agent_control", "collaboration", "change", "Steering an agent's work", "يوجّه عمل وكيل"],
    ["supervision_change", "collaboration", "change", "Setting supervision", "يضبط الإشراف"],
    ["peer_send", "collaboration", "change", "Messaging agents", "يراسل الوكلاء"],
    [
      "news_feed_subscribe",
      "research",
      "change",
      "Subscribing to a news feed",
      "يشترك في موجز أخبار",
    ],
    ["news_feed_read", "research", "read", "Searching sources", "يبحث في المصادر"],
    ["capabilities_list", "research", "read", "Checking capabilities", "يراجع القدرات"],
    ["watch_cancel", "market", "change", "Updating a market watch", "يحدّث مراقبة للسوق"],
    ["watch_create", "market", "change", "Setting a market watch", "يضبط مراقبة للسوق"],
    ["chart_set_timeframe", "charts", "change", "Working on a chart", "يعمل على رسم بياني"],
  ];
  for (const [name, toolset, effect, en, ar] of cases) {
    assert.equal(activityCallLabel({ name, toolset, effect }, "en"), en, name);
    assert.equal(activityCallLabel({ name, toolset, effect }, "ar"), ar, name);
  }
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

test("Arabic owner text names equity with one term", () => {
  // «حقوق الملكية» everywhere; «السيولة» (liquidity) and «قيمة الحساب» (account value)
  // named the same figure on the grant card, the pill and the account summary.
  const sources = [
    "packages/core/src/owner-actions.ts",
    "packages/core/src/trading-readiness.ts",
    "packages/core/src/agent-status.ts",
    "packages/core/src/account-authority-labels.ts",
    "packages/core/src/trade-action-labels.ts",
    "apps/web/src/components/permissions/permission-labels.ts",
    "apps/web/src/i18n/locales/ar/messages.po",
    "apps/mobile/lib/i18n.ts",
  ].map(read);
  for (const text of sources) {
    assert.ok(!text.includes("السيولة"), "liquidity used for equity");
    assert.ok(!/msgid "Equity"\nmsgstr "(?!حقوق الملكية)/.test(text), "Equity translated twice");
  }
  assert.ok(sources.some((text) => text.includes("حقوق الملكية")));
});
