import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

/* «ما يعمل الآن» (mandate 7.1.5) on the phone, in Arabic: every workspace process with the
   agent that started it; one tap stops one process, one tap stops all of them. */
function fixture(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/workspace_running_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}
let data = null;
test.afterEach(() => {
  if (data) fixture({ ...data, action: "cleanup" });
  data = null;
});

test("Expo Arabic: the processes under their agents, stop one, stop all", async ({
  page,
  context,
}) => {
  data = fixture({ action: "init" });
  await context.addCookies(
    data.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      sameSite: "Strict",
      httpOnly: cookie.name === "lonora_session",
    })),
  );
  await page.goto("/");
  await page.getByTestId("tab-settings").click();
  await page.getByTestId("what-is-running").click();
  await expect(page.getByRole("heading", { name: "ما يعمل الآن" }).last()).toBeVisible();
  const rows = page.getByTestId("running-process");
  await expect(rows).toHaveCount(3);
  await expect(page.getByRole("heading", { name: data.trader.name })).toBeVisible();
  await expect(
    page.getByText("python3 listener.py --symbol XAUUSD", { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: data.research.name })).toBeVisible();

  const second = rows.filter({ hasText: "node price-feed.js" });
  await second.getByRole("button", { name: "إيقاف", exact: true }).click();
  await expect(second).toContainText("يجري الإيقاف…");
  await expect
    .poll(() => fixture({ action: "stops" }).stops)
    .toEqual([{ pid: 4102, agent_id: data.trader.id }]);

  await page.getByRole("button", { name: "إيقاف الكل", exact: true }).click();
  await expect(page.getByRole("button", { name: "يجري إيقاف الكل…", exact: true })).toBeVisible();
  await expect.poll(() => fixture({ action: "stops" }).stops.length).toBe(2);

  fixture({ action: "empty" });
  await expect(page.getByTestId("running-empty")).toHaveText("لا شيء يعمل في مساحة العمل.", {
    timeout: 10_000,
  });
});
