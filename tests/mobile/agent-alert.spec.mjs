import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

test("Expo Arabic inbox shows an agent's own alert with its plain summary", async ({
  page,
  context,
}) => {
  const fixture = JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_agent_alert_browser.py"], { encoding: "utf8" }),
  );
  await context.addCookies(
    fixture.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      sameSite: "Strict",
      httpOnly: cookie.name === "lonora_session",
    })),
  );
  await page.goto("/");
  // Activity lives in the home header's "More" menu.
  await page.getByRole("button", { name: "المزيد", exact: true }).click();
  await page.getByText("النشاط", { exact: true }).click();
  const summary = fixture.notification.parameters.summary;
  await expect(page.getByText("نبّهك وكيلك", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(summary, { exact: true })).toBeVisible();
  await expect(page.getByText("broker:sim-gold-1")).toHaveCount(0);
});
