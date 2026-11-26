// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: This Playwright scenario runs without Turborepo caching.
// An honest live connection (B3): a stream that stays silent after its ready frame shows
// «Reconnecting…» within 45 s, and the new stream resumes from the last event it consumed.
import { execFileSync } from "node:child_process";
import { expect, test } from "../ui-test.mjs";

function fixture(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_streaming.py", "browser"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}

test("a stream silent after ready shows Reconnecting within 45 s and resumes from its cursor", async ({
  page,
  context,
  cleanup,
}) => {
  test.setTimeout(60_000);
  const data = fixture({ action: "init" });
  cleanup(() => fixture({ ...data, action: "cleanup" }));
  const login = await context.request.post("/api/auth/login", {
    data: {
      email: process.env.LONORA_UI_TEST_EMAIL ?? "ci@example.com",
      password: process.env.LONORA_UI_TEST_PASSWORD ?? "ci-only-owner-password",
    },
  });
  expect(login.ok()).toBeTruthy();
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const write = (text) =>
    fixture({
      ...data,
      parent: data.run,
      action: "peer_activity",
      kind: "run.delta",
      payload: { turn_id: data.turn, text },
    });
  const streams = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname === "/api/events/stream") streams.push(url.searchParams);
  });
  // The page's timers follow a clock the test moves: 45 s pass for the page at once, and the
  // server sends nothing meanwhile (its pings are 15 s of real time apart).
  await page.clock.install();
  await page.goto(`/app/g/${data.group}`);
  const preview = page.locator(`[data-stream-run-id='${data.run.id}']`);
  await expect(preview).toContainText(data.text);
  write("LIVE before the silence ");
  await expect(preview).toContainText("LIVE before the silence");
  const thread = await (await context.request.get(`/api/events?thread_id=${data.thread}`)).json();
  const written = thread.find((event) => event.payload.text === "LIVE before the silence ");
  const later = await (await context.request.get(`/api/events?cursor=${written.cursor}`)).json();
  const last = Math.max(written.cursor, ...later.map((event) => event.cursor));
  const reconnecting = page.getByRole("status").filter({ hasText: "Reconnecting…" });
  await expect(reconnecting).toHaveCount(0);
  // Stop the clock so the strip can be read before the reconnect delay ends.
  await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 1000);
  await page.clock.fastForward(45_000);
  await expect(reconnecting).toBeVisible();
  expect(streams).toHaveLength(1);
  await page.clock.runFor(1000);
  await expect(page.getByRole("status").filter({ hasText: "Connection restored" })).toBeVisible();
  await page.clock.resume();
  // The new stream asks for the events after the last one consumed, not a live start.
  expect(streams).toHaveLength(2);
  expect(streams[1].get("cursor")).toBe(String(last));
  expect(streams[1].has("live")).toBe(false);
  write("LIVE after the resume");
  await expect(preview).toContainText(`${data.text}LIVE before the silence LIVE after the resume`);
});
