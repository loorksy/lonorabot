import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

// The fixture's agent goes after each test, so it never counts against the agent cap.
let fixtureAgent;
test.afterEach(async ({ context }) => {
  if (!fixtureAgent) return;
  const csrf = (await context.cookies()).find((cookie) => cookie.name === "lonora_csrf");
  await context.request.delete(`/api/agents/${fixtureAgent}`, {
    headers: { "X-CSRF-Token": csrf?.value ?? "" },
  });
  fixtureAgent = undefined;
});

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
    // «يحتاج انتباهك» is a tab of the floating bar.
    await page.getByTestId("tab-updates").click();
    const text = fixture.notification.parameters.summary;
    await expect(page.getByText("نبّهك وكيلك", { exact: true }).first()).toBeVisible();
    const shown = page.getByTestId("attention-summary").filter({ hasText: text });
    await expect(shown).toHaveText(text);
    await expect(shown).toHaveCSS("direction", direction);
    await expect(page.getByText("broker:sim-gold-1")).toHaveCount(0);
  });
}
