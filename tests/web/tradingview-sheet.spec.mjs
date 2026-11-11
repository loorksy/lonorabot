import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

function fixture(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_rakazo_ui.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}
test("chart sheet expands, dismisses with Escape and restores focus (Q37: the reference's look)", async ({
  page,
  context,
}) => {
  test.setTimeout(60000);
  const data = fixture({ action: "init" });
  await page.setViewportSize({ width: 390, height: 844 });
  try {
    await context.addCookies(
      data.cookies.map((cookie) => ({
        ...cookie,
        url: test.info().project.use.baseURL,
        httpOnly: cookie.name === "lonora_session",
        sameSite: "Strict",
      })),
    );
    await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
    await page.goto(`/app/${data.agent}`);
    await page.getByRole("button", { name: "Chat menu", exact: true }).click();
    await page.locator("#dialog").getByRole("button", { name: "Chart", exact: true }).click();
    const sheet = page.locator("#dialog");
    await expect(sheet).toHaveClass(/expandable/);
    // The conversation has no pair: its latest chart, on that chart's own timeframe, drawn
    // from the broker's candles with the reference's SVG.
    await expect(sheet.getByRole("tab", { name: "15m" })).toHaveAttribute("aria-selected", "true");
    const candles = sheet.locator("svg.chart > g > rect");
    await expect(candles.first()).toBeVisible();
    // The chart's RSI(14) is an oscillator: its own labelled pane, never the price scale.
    const pane = sheet.locator('svg.chart [data-overlay="pane"]');
    await expect(pane).toContainText("RSI 14");
    expect(await pane.locator("polyline").count()).toBeGreaterThan(0);
    expect(await sheet.locator('svg.chart [data-overlay="indicator"]').count()).toBe(0);
    const initial = await sheet.boundingBox();
    expect(initial.height).toBeLessThan(800);
    await sheet.getByRole("button", { name: "Full screen", exact: true }).click();
    await expect(sheet).toHaveClass(/expanded/);
    await expect.poll(async () => (await sheet.boundingBox()).height).toBeGreaterThan(800);
    await page.keyboard.press("Escape");
    await expect(sheet).not.toHaveAttribute("open", "");
    // The dialog gives focus back to the button that opened it.
    const menu = page.getByRole("button", { name: "Chat menu", exact: true });
    await expect(menu).toBeFocused();
    await menu.click();
    await sheet.getByRole("button", { name: "Chart", exact: true }).click();
    await expect(candles.first()).toBeVisible();
    await sheet.getByRole("button", { name: "Close", exact: true }).click();
    await expect(sheet).not.toHaveAttribute("open", "");
  } finally {
    fixture({ ...data, action: "cleanup" });
  }
});
