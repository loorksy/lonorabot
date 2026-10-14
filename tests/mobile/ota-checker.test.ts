import assert from "node:assert/strict";
import { test } from "node:test";
import { createUpdateChecker } from "../../apps/mobile/lib/ota-checker";

test("checks serialize and throttle; downloads activate only on next launch", async () => {
  let now = 0;
  let checks = 0;
  let fetches = 0;
  let release: ((value: { isAvailable: boolean }) => void) | undefined;
  const checker = createUpdateChecker(
    {
      check: () => {
        checks++;
        return new Promise((resolve) => {
          release = resolve;
        });
      },
      fetch: async () => {
        fetches++;
      },
    },
    { now: () => now, interval: 100 },
  );
  const pending = checker.check();
  await checker.check();
  assert.equal(checks, 1);
  release?.({ isAvailable: true });
  await pending;
  assert.equal(fetches, 1);
  await checker.check();
  assert.equal(checks, 1);
  now = 100;
  const next = checker.check();
  release?.({ isAvailable: false });
  await next;
  assert.equal(checks, 2);
});

test("rollback fetched and stopped checker never downloads late response", async () => {
  let fetched = 0;
  const rollback = createUpdateChecker({
    check: async () => ({ isAvailable: false, isRollBackToEmbedded: true }),
    fetch: async () => {
      fetched++;
    },
  });
  await rollback.check();
  assert.equal(fetched, 1);
  let release: ((value: { isAvailable: boolean }) => void) | undefined;
  const checker = createUpdateChecker({
    check: () =>
      new Promise((resolve) => {
        release = resolve;
      }),
    fetch: async () => {
      fetched++;
    },
  });
  const pending = checker.check();
  checker.stop();
  release?.({ isAvailable: true });
  await pending;
  await checker.check();
  assert.equal(fetched, 1);
});

test("network failure is bounded and does not break session", async () => {
  let failures = 0;
  const checker = createUpdateChecker(
    {
      check: async () => {
        throw new Error("offline");
      },
      fetch: async () => {
        throw new Error("unexpected");
      },
    },
    {
      onFailure: () => {
        failures++;
      },
    },
  );
  await checker.check();
  await checker.check();
  assert.equal(failures, 1);
});
