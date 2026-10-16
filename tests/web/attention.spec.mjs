import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

test("durable notification is shared across views and stays read after reload", async ({
  page,
  context,
}) => {
  const fixture = JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_attention_browser.py"], { encoding: "utf8" }),
  );
  await context.addCookies(
    fixture.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      sameSite: "Strict",
      httpOnly: cookie.name === "lonora_session",
    })),
  );
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  await page.goto("/app/activity");
  const inbox = page.getByTestId("attention-inbox");
  const alert = inbox.locator(`[data-attention-id="${fixture.notification.id}"]`);
  await expect(alert.getByText("Emergency Stop is active", { exact: true })).toBeVisible();
  await page.reload();
  await expect(alert).toHaveCount(1);
  await alert.getByRole("button", { name: "Mark as read", exact: true }).click();
  await expect(alert).toHaveCount(0);
  await page.reload();
  await expect(inbox.getByText("No new notifications", { exact: true })).toBeVisible();
  const controls = await (await context.request.get("/api/trading/controls")).json();
  expect(controls).toMatchObject({ enabled: false, emergency_stop: true });
});
