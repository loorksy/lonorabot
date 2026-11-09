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
    await page.getByRole("button", { name: "Chat menu", exact: true }).click();
    await page.locator("#dialog").getByRole("button", { name: "Chart", exact: true }).click();
    const sheet = page.locator("#dialog");
    await expect(sheet).toHaveClass(/expandable/);
    const chart = sheet.locator(`[data-chart-id='${data.chart}']`);
    const canvas = chart.frameLocator(".chart-renderer iframe").locator("canvas").first();
    await expect(canvas).toBeVisible();
    const initial = await sheet.boundingBox();
    expect(initial.height).toBeLessThan(800);
    await sheet.getByRole("button", { name: "Full screen", exact: true }).click();
    await expect(sheet).toHaveClass(/expanded/);
    await expect.poll(async () => (await sheet.boundingBox()).height).toBeGreaterThan(800);
    await sheet.getByRole("button", { name: "Follow Agent", exact: true }).click();
    await expect(sheet.getByRole("button", { name: "Free Browse", exact: true })).toBeVisible();
    await canvas.dispatchEvent("pointerdown", { pointerId: 1, clientX: 50, clientY: 50 });
    await expect(sheet.getByRole("button", { name: "Follow Agent", exact: true })).toBeVisible();
    await canvas.press("Escape");
    await expect(sheet).not.toHaveAttribute("open", "");
    // The dialog gives focus back to the button that opened it.
    const menu = page.getByRole("button", { name: "Chat menu", exact: true });
    await expect(menu).toBeFocused();
    await menu.click();
    await sheet.getByRole("button", { name: "Chart", exact: true }).click();
    await expect(canvas).toBeVisible();
    await sheet.getByRole("button", { name: "Close", exact: true }).click();
    await expect(sheet).not.toHaveAttribute("open", "");
  } finally {
    fixture({ ...data, action: "cleanup" });
  }
});
