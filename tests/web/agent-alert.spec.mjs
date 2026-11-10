import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

for (const locale of ["ar", "en"]) {
  test(`an agent's own alert shows its plain summary (${locale})`, async ({ page, context }) => {
    const fixture = JSON.parse(
      execFileSync(".venv/bin/python", ["tests/check_agent_alert_browser.py"], {
        encoding: "utf8",
      }),
    );
    await context.addCookies(
      fixture.cookies.map((cookie) => ({
        ...cookie,
        url: test.info().project.use.baseURL,
        sameSite: "Strict",
        httpOnly: cookie.name === "lonora_session",
      })),
    );
    await page.addInitScript((value) => localStorage.setItem("lonora.locale", value), locale);
    await page.goto("/app/updates");
    const alert = page.locator(`[data-attention-id="${fixture.notification.id}"]`);
    const label = locale === "ar" ? "نبّهك وكيلك" : "Your agent alerted you";
    await expect(alert.getByText(label, { exact: true })).toBeVisible();
    const summary = alert.getByTestId("attention-summary");
    await expect(summary).toHaveText(fixture.notification.parameters.summary);
    // Mixed Arabic text with a ticker and a price follows its own direction.
    await expect(summary).toHaveAttribute("dir", "auto");
    await expect(alert).not.toContainText(fixture.notification.id);
    await expect(alert).not.toContainText("broker:sim-gold-1");
    // Opening it reads it: the unread dot goes, the row stays in «التنبيهات».
    await expect(alert.locator(".dot")).toHaveCount(1);
    await alert.click();
    await page.goto("/app/updates");
    await expect(alert.locator(".dot")).toHaveCount(0);
  });
}
