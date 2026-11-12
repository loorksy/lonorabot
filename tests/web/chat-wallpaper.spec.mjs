import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

/* The chat's wallpaper (reference Desktop-37 850-851): Lonora's pattern at its light level, and
   the layer fades in only with the page that opens the chat. */
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

test("the chat draws Lonora's pattern at its light level, fainter in the light theme", async ({
  page,
}) => {
  await page.goto(`/app/${data.research.id}`);
  await expect.poll(() => fill(page)).toBe("url(#lw-p-lonora)");
  expect(await alpha(page)).toBe("0.1");
  await page.evaluate(() => localStorage.setItem("lonora.theme", '"light"'));
  await page.reload();
  await expect.poll(() => alpha(page)).toBe("0.085");
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
