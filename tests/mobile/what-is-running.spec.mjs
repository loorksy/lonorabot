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
  await expect(rows.filter({ hasText: "python3 listener.py --symbol XAUUSD" })).toHaveCount(1);
  await expect(page.getByRole("heading", { name: data.research.name })).toBeVisible();

  const second = rows.filter({ hasText: "node price-feed.js" });
  // Each Stop button names its process for a screen reader.
  await second.getByRole("button", { name: "إيقاف node price-feed.js", exact: true }).click();
  await expect(second).toContainText("يجري الإيقاف…");
  await expect
    .poll(() => fixture({ action: "stops" }).stops)
    .toEqual([{ pid: 4102, agent_id: data.trader.id }]);

  await page.getByRole("button", { name: "إيقاف الكل", exact: true }).click();
  await expect(page.getByRole("button", { name: "يجري إيقاف الكل…", exact: true })).toBeVisible();
  await expect.poll(() => fixture({ action: "stops" }).stops.length).toBe(2);

  // The Gateway carries the stops out and an agent starts another process: both kinds of
  // stop are offered again.
  fixture({ ...data, action: "carried_out" });
  await expect(rows).toHaveCount(1, { timeout: 10_000 });
  await expect(page.getByRole("button", { name: "إيقاف الكل", exact: true })).toBeEnabled();
  await expect(
    page.getByRole("button", { name: "إيقاف python3 restarted.py", exact: true }),
  ).toBeEnabled();

  fixture({ action: "empty" });
  await expect(page.getByTestId("running-empty")).toHaveText("لا شيء يعمل في مساحة العمل.", {
    timeout: 10_000,
  });

  // Before the workspace has ever answered, the screen does not claim nothing is running.
  fixture({ action: "unknown" });
  await expect(page.getByTestId("running-unknown")).toHaveText(
    "لم تُجب مساحة العمل بعد، فلا يُعرف ما يعمل الآن.",
    { timeout: 10_000 },
  );
  await expect(page.getByTestId("running-empty")).toHaveCount(0);
});
