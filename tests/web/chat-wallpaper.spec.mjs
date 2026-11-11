import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

/* «خلفية المحادثة» (reference wallSheet, Desktop-37 4946-4961, 9124-9125): a preference of this
   device, chosen from the ⋮ menu or from settings. The chat behind the sheet follows each tap,
   the sheet stays open, and the layer fades in only with the page that opens the chat. */
function fixture(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/agent_pages_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}
let data = null;
const errors = [];
test.beforeEach(async ({ page, context }) => {
  data = fixture({ action: "init" });
  data.groups = [];
  data.agents = [];
  await context.addCookies(
    data.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript(() => {
    localStorage.setItem("lonora.locale", "en");
    // A stored choice this build does not know falls back to the default pattern.
    if (!localStorage.getItem("lonora.wall")) localStorage.setItem("lonora.wall", '{"id":"zzz"}');
  });
  page.on("pageerror", (error) => errors.push(error.message));
});
test.afterEach(() => {
  expect(errors.splice(0)).toEqual([]);
  if (data) fixture({ ...data, action: "cleanup" });
  data = null;
});

const fill = (page) => page.locator(".chat-wall rect").getAttribute("fill");
const alpha = (page) =>
  page.locator(".chat-wall").evaluate((node) => node.style.getPropertyValue("--wa"));
const stored = (page) => page.evaluate(() => JSON.parse(localStorage.getItem("lonora.wall")));

test("the pattern and its clarity are chosen from the ⋮ menu and kept on this device", async ({
  page,
}) => {
  await page.goto(`/app/${data.research.id}`);
  await expect.poll(() => fill(page)).toBe("url(#lw-p-lonora)");
  expect(await alpha(page)).toBe("0.1");
  await page.getByRole("button", { name: "Chat menu", exact: true }).click();
  await page.getByRole("menuitem", { name: "Chat background" }).click();
  const sheet = page.locator("#dialog");
  await expect(sheet).toHaveAttribute("open", "");
  await expect(sheet.getByRole("heading", { name: "Chat background" })).toBeVisible();
  const patterns = sheet.getByRole("radiogroup", { name: "Wallpaper pattern" }).getByRole("radio");
  await expect(patterns).toHaveText(["Lonora", "Agents", "Market", "Calm", "None"]);
  await expect(patterns.nth(0)).toHaveAttribute("aria-checked", "true");
  await expect(patterns.nth(0).locator(".wall-art")).toHaveCount(1);
  await expect(patterns.nth(4).locator(".wall-art")).toHaveCount(0);
  const levels = sheet.getByRole("radiogroup", { name: "Drawing clarity" }).getByRole("radio");
  await expect(levels).toHaveText(["Light", "Medium", "Clearer"]);
  await expect(levels.nth(0)).toHaveAttribute("aria-checked", "true");

  // The chat behind the sheet follows at once and the sheet stays open.
  await patterns.nth(2).click();
  await expect.poll(() => fill(page)).toBe("url(#lw-p-market)");
  await expect(patterns.nth(2)).toHaveAttribute("aria-checked", "true");
  await expect(patterns.nth(2).locator(".wall-name svg")).toHaveCount(1);
  await levels.nth(2).click();
  await expect.poll(() => alpha(page)).toBe("0.21");
  await expect(sheet).toHaveAttribute("open", "");
  expect(await stored(page)).toEqual({ id: "market", level: "strong" });

  // «بدون» removes the layer and switches the clarity off without forgetting it.
  await patterns.nth(4).click();
  await expect(page.locator(".chat-wall")).toHaveCount(0);
  for (const index of [0, 1, 2]) await expect(levels.nth(index)).toBeDisabled();
  await patterns.nth(3).click();
  await expect.poll(() => fill(page)).toBe("url(#lw-p-calm)");
  await expect(levels.nth(2)).toBeEnabled();
  await expect(levels.nth(2)).toHaveAttribute("aria-checked", "true");

  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Chat menu", exact: true })).toBeFocused();
  await page.reload();
  await expect.poll(() => fill(page)).toBe("url(#lw-p-calm)");
  expect(await alpha(page)).toBe("0.21");
  // The light theme draws the same level fainter.
  await page.evaluate(() => localStorage.setItem("lonora.theme", '"light"'));
  await page.reload();
  await expect.poll(() => alpha(page)).toBe("0.17");
});

test("settings shows the chosen pattern and opens the same sheet", async ({ page }) => {
  await page.goto("/app/settings");
  const row = page.locator(".group .row", { hasText: "Chat background" });
  await expect(row.locator(".value")).toHaveText("Lonora");
  // In the reference's order: under language and theme, above «تجربة المحادثة».
  await expect(
    page.locator(".group", { has: page.locator(".prefs-row") }).locator(".row strong"),
  ).toHaveText(["Chat background", "Chat experience", "Accessibility"]);
  await row.click();
  const sheet = page.locator("#dialog");
  await expect(sheet).toHaveAttribute("open", "");
  // No conversation is mounted here: the sheet builds the patterns itself.
  await expect(page.locator("#lw-defs pattern")).toHaveCount(4);
  await sheet.getByRole("radio", { name: "Calm" }).click();
  await expect(row.locator(".value")).toHaveText("Calm");
  await expect(sheet).toHaveAttribute("open", "");
});

test("the layer fades in with the page that opens the chat, never under reduced motion", async ({
  page,
}) => {
  const open = async () => {
    await page.goto("/app");
    await page.locator(`.thread[data-key="agent:${data.research.id}"]`).first().click();
    await expect(page.locator(".chat-wall")).toHaveCount(1);
    return page.locator(".chat-wall").evaluate((node) => {
      const style = getComputedStyle(node);
      return [
        node.parentElement.classList.contains("page-enter"),
        style.animationName,
        style.animationDuration,
      ];
    });
  };
  expect(await open()).toEqual([true, "wall-in", "0.3s"]);
  await page.emulateMedia({ reducedMotion: "reduce" });
  expect(await open()).toEqual([false, "none", "0s"]);
});
