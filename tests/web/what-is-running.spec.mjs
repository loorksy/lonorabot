import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

/* «ما يعمل الآن» (mandate 7.1.5): every workspace process with the agent that started it;
   one tap stops one process, one tap stops all of them. The Gateway keeps the listing and
   carries out the stops; here the listing is seeded and the stop requests are read back. */
function fixture(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/workspace_running_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}
let data = null;
const errors = [];
test.beforeEach(async ({ page, context }) => {
  data = fixture({ action: "init" });
  await context.addCookies(
    data.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  page.on("pageerror", (error) => errors.push(error.message));
});
test.afterEach(() => {
  expect(errors.splice(0)).toEqual([]);
  if (data) fixture({ ...data, action: "cleanup" });
  data = null;
});

test("every process with its agent; one tap stops one, one tap stops all", async ({
  page,
  context,
}) => {
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  await page.goto("/app/settings");
  await page.getByRole("button", { name: /What is running/ }).click();
  await expect(page).toHaveURL(/\/app\/running$/);
  const main = page.locator("main");
  const rows = main.getByTestId("running-process");
  await expect(rows).toHaveCount(3);
  const trader = main.getByRole("region", { name: data.trader.name });
  await expect(trader.getByTestId("running-process")).toHaveCount(2);
  await expect(trader).toContainText("python3 listener.py --symbol XAUUSD");
  await expect(main.getByRole("region", { name: data.research.name })).toContainText(
    "python3 scrape.py",
  );
  // No process id, agent id or raw data in the view (section 17).
  await expect(main).not.toContainText("4101");
  await expect(main).not.toContainText(data.trader.id);

  await trader.getByRole("button", { name: "Stop node price-feed.js" }).click();
  await expect(trader.getByRole("status")).toHaveText("Stopping…");
  await expect
    .poll(() => fixture({ action: "stops" }).stops)
    .toEqual([{ pid: 4102, agent_id: data.trader.id }]);

  await main.getByTestId("stop-all").click();
  await expect(main.getByTestId("stop-all")).toBeDisabled();
  await expect.poll(() => fixture({ action: "stops" }).stops.length).toBe(2);
  expect(fixture({ action: "stops" }).stops).toContainEqual({ pid: null, agent_id: null });

  // The Gateway carries the stops out and an agent starts another process: the view
  // follows the server, and both kinds of stop are offered again.
  fixture({ ...data, action: "carried_out" });
  await expect(rows).toHaveCount(1, { timeout: 10_000 });
  await expect(main.getByTestId("stop-all")).toBeEnabled();
  await expect(main.getByRole("button", { name: "Stop python3 restarted.py" })).toBeEnabled();

  fixture({ action: "empty" });
  await expect(main).toContainText("Nothing is running in the workspace.", { timeout: 10_000 });

  // A list the workspace has not refreshed for a minute says so and takes no stop.
  fixture({ ...data, action: "stale" });
  await expect(main.getByTestId("running-stale")).toBeVisible({ timeout: 10_000 });
  await expect(main.getByTestId("stop-all")).toBeDisabled();
});

test("the view in Arabic, right to left", async ({ page, context }) => {
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "ar"));
  await page.goto("/app/running");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  const main = page.locator("main");
  await expect(main.getByTestId("running-process")).toHaveCount(3);
  await expect(main.getByTestId("stop-all")).toHaveText("إيقاف الكل");
  await expect(main).toContainText("كل عملية يشغّلها وكلاؤك في مساحة العمل");
  // Commands stay left to right inside the Arabic page.
  await expect(main.locator("bdi[dir=ltr]").first()).toBeVisible();
});
