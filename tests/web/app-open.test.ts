import assert from "node:assert/strict";
import test from "node:test";
import { appOpenReporter } from "../../packages/core/src/app-open";

test("the app reports one open per local date, with the device zone", async () => {
  const sent: { timezone: string }[] = [];
  let clock = new Date("2026-11-12T05:00:00Z");
  const report = appOpenReporter(
    async (body) => {
      sent.push(body);
    },
    () => clock,
  );
  report();
  report();
  assert.equal(sent.length, 1);
  assert.equal(sent[0]?.timezone, Intl.DateTimeFormat().resolvedOptions().timeZone);
  clock = new Date("2026-11-14T05:00:00Z");
  report();
  assert.equal(sent.length, 2);
});

test("a failed report is sent again on the same date", async () => {
  let calls = 0;
  const report = appOpenReporter(async () => {
    calls += 1;
    if (calls === 1) throw new Error("offline");
  });
  report();
  await new Promise((resolve) => setTimeout(resolve, 0));
  report();
  assert.equal(calls, 2);
});
