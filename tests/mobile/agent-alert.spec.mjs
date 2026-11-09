import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

// The Arabic interface shows an Arabic and an English summary, each in its own direction.
for (const [name, summary, direction] of [
  ["Arabic", undefined, "rtl"],
  ["English", "Gold closed at the 2310.5 stop loss", "ltr"],
]) {
  test(`Expo Arabic inbox shows an agent's own ${name} alert in its own direction`, async ({
    page,
    context,
  }) => {
    const fixture = JSON.parse(
      execFileSync(
        ".venv/bin/python",
        ["tests/check_agent_alert_browser.py", ...(summary ? [summary] : [])],
        { encoding: "utf8" },
      ),
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
    const text = fixture.notification.parameters.summary;
    await expect(page.getByText("نبّهك وكيلك", { exact: true }).first()).toBeVisible();
    const shown = page.getByTestId("attention-summary").filter({ hasText: text });
    await expect(shown).toHaveText(text);
    await expect(shown).toHaveCSS("direction", direction);
    await expect(page.getByText("broker:sim-gold-1")).toHaveCount(0);
  });
}
