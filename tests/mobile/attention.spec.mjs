import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

// The fixture's agent holds an uncertain trade, which rightly refuses its deletion: it is
// paused after the test, so it never wakes in later tests.
let fixtureAgent;
test.afterEach(() => {
  if (!fixtureAgent) return;
  execFileSync(".venv/bin/python", ["tests/browser_agents.py"], {
    input: JSON.stringify({ action: "pause", ids: [fixtureAgent] }),
    encoding: "utf8",
  });
  fixtureAgent = undefined;
});

test("Expo Arabic attention uses durable server state and read does not grant trading", async ({
  page,
  context,
}) => {
  const fixture = JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_attention_browser.py"], { encoding: "utf8" }),
  );
  fixtureAgent = fixture.agent?.id;
  await context.addCookies(
    fixture.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      sameSite: "Strict",
      httpOnly: cookie.name === "lonora_session",
    })),
  );
  await page.goto("/");
  await page.getByTestId("tab-updates").click();
  // This owner may hold earlier alerts from other specs: read them all, one at a time.
  await expect(page.getByText("التداول الجديد متوقف", { exact: true }).first()).toBeVisible();
  const read = page.getByRole("button", { name: "تحديد كمقروء", exact: true });
  while (await read.count()) {
    const before = await read.count();
    await read.first().click();
    await expect(read).toHaveCount(before - 1);
  }
  await expect(page.getByText("التداول الجديد متوقف", { exact: true })).toHaveCount(0);
  await page.reload();
  await page.getByTestId("tab-updates").click();
  await expect(page.getByText("لا توجد تنبيهات جديدة", { exact: true })).toBeVisible();
  const controls = await (await context.request.get("/api/trading/controls")).json();
  expect(controls).toMatchObject({ enabled: false, emergency_stop: true });
});
