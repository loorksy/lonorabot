import assert from "node:assert/strict";
import test from "node:test";
import { appOpenReporter, ownerDay } from "../../packages/core/src/app-open";

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

test("the owner day starts at 04:00 on the device's clock, as on the server", () => {
  // 00:30 and 03:59 in Riyadh on the 12th belong to the 11th; 04:00 starts the 12th.
  assert.equal(ownerDay(new Date("2026-11-11T21:30:00Z"), "Asia/Riyadh"), "2026-11-11");
  assert.equal(ownerDay(new Date("2026-11-12T00:59:00Z"), "Asia/Riyadh"), "2026-11-11");
  assert.equal(ownerDay(new Date("2026-11-12T01:00:00Z"), "Asia/Riyadh"), "2026-11-12");
  assert.equal(ownerDay(new Date("2026-03-01T02:00:00Z"), "UTC"), "2026-02-28");
  assert.equal(ownerDay(new Date("2027-01-01T03:00:00Z"), "UTC"), "2026-12-31");
});

test("an open after midnight does not use up the morning's first open", async () => {
  const sent: { timezone: string }[] = [];
  // Local times on the device's own clock: a late session, the morning, the next night.
  let clock = new Date(2026, 10, 12, 0, 30);
  const report = appOpenReporter(
    async (body) => {
      sent.push(body);
    },
    () => clock,
  );
  report();
  assert.equal(sent.length, 1);
  clock = new Date(2026, 10, 12, 3, 59);
  report();
  assert.equal(sent.length, 1);
  clock = new Date(2026, 10, 12, 7, 0);
  report();
  assert.equal(sent.length, 2);
  clock = new Date(2026, 10, 13, 1, 0);
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
