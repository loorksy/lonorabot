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
test("chart sheet expands, yields to chart gestures, dismisses with iframe Escape and restores focus", async ({
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
    const open = page.getByRole("button", { name: "Charts", exact: true });
    await open.click();
    const sheet = page.getByTestId("side-panel");
    await expect(sheet).toHaveAttribute("data-overlay", "true");
    const chart = sheet.locator(`[data-chart-id='${data.chart}']`);
    const canvas = chart.frameLocator(".chart-renderer iframe").locator("canvas").first();
    await expect(canvas).toBeVisible();
    const initial = await sheet.boundingBox();
    expect(initial.height).toBeLessThan(800);
    await sheet.getByRole("button", { name: "Expand chart", exact: true }).click();
    await expect(sheet).toHaveAttribute("data-chart-expanded", "true");
    await expect.poll(async () => (await sheet.boundingBox()).height).toBeGreaterThan(800);
    await sheet.getByRole("button", { name: "Follow Agent", exact: true }).click();
    await expect(sheet.getByRole("button", { name: "Free Browse", exact: true })).toBeVisible();
    await canvas.dispatchEvent("pointerdown", { pointerId: 1, clientX: 50, clientY: 50 });
    await expect(sheet.getByRole("button", { name: "Follow Agent", exact: true })).toBeVisible();
    await canvas.press("Escape");
    await expect(sheet).toHaveCount(0);
    await expect(open).toBeFocused();
    await open.click();
    await sheet.getByRole("button", { name: "Close chart", exact: true }).click();
    await expect(sheet).toHaveCount(0);
  } finally {
    fixture({ ...data, action: "cleanup" });
  }
});
