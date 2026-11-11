import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

/* The conversation's ⋮ menu and header (reference chat-menu, Desktop-37 9256-9257): a popover
   beside the button, info goes to the agent or group page, «مسح المحادثة» hides the history
   (Q1) and nothing is ever deleted. */
function fixture(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/agent_pages_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}
let data = null;
let headers = {};
const deletes = [];
const errors = [];
test.beforeEach(async ({ page, context }) => {
  data = fixture({ action: "init" });
  data.groups = [];
  data.agents = [];
  headers = { "X-CSRF-Token": data.cookies.find((row) => row.name === "lonora_csrf").value };
  await context.addCookies(
    data.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (request.method() === "DELETE" && /^\/api\/(agents|groups)\//.test(path)) deletes.push(path);
  });
});
test.afterEach(() => {
  expect(deletes).toEqual([]);
  expect(errors.splice(0)).toEqual([]);
  if (data) fixture({ ...data, action: "cleanup" });
  data = null;
});

const menuItems = (page) => page.getByRole("menu", { name: "Chat menu" }).getByRole("menuitem");

test("the ⋮ menu is a popover beside its button, in the reference's order", async ({ page }) => {
  await page.goto(`/app/${data.trader.id}`);
  const button = page.getByRole("button", { name: "Chat menu", exact: true });
  await button.click();
  const menu = page.getByRole("menu", { name: "Chat menu" });
  await expect(menu).toBeVisible();
  await expect(page.locator("#dialog[open]")).toHaveCount(0);
  await expect(button).toHaveAttribute("aria-expanded", "true");
  await expect(menuItems(page)).toHaveText([
    "Agent info",
    "Chart",
    "Status and safety",
    "Watches",
    "New task",
    "Agent files",
    "Clear the chat",
  ]);
  await expect(menu.locator(".pop-sep")).toHaveCount(1);
  await expect(menu.getByRole("menuitem", { name: "Clear the chat" })).toHaveClass(/danger/);
  // Beside the button: the menu's top edge is just under it.
  const [anchor, box] = [await button.boundingBox(), await menu.boundingBox()];
  expect(box.y - (anchor.y + anchor.height)).toBeLessThan(12);
  await page.keyboard.press("Escape");
  await expect(menu).toHaveCount(0);
  // A sheet opened from the menu gives focus back to ⋮ when it closes.
  await button.click();
  await page.getByRole("menuitem", { name: "Chart" }).click();
  await expect(page.locator("#dialog")).toHaveAttribute("open", "");
  await page.keyboard.press("Escape");
  await expect(page.locator("#dialog")).not.toHaveAttribute("open", "");
  await expect(button).toBeFocused();

  // A research agent has no chart, no watches; a group has no agent files.
  await page.goto(`/app/${data.research.id}`);
  await page.getByRole("button", { name: "Chat menu", exact: true }).click();
  await expect(menuItems(page)).toHaveText([
    "Agent info",
    "New task",
    "Agent files",
    "Clear the chat",
  ]);
  await page.goto(`/app/g/${data.group.id}`);
  await page.getByRole("button", { name: "Chat menu", exact: true }).click();
  await expect(menuItems(page)).toHaveText(["Group info", "Chart", "New task", "Clear the chat"]);
});

test("info goes to the agent or group page from the avatar, the name and the menu", async ({
  page,
}) => {
  await page.goto(`/app/${data.trader.id}`);
  await page.locator(".chat-head .head-avatar").click();
  await expect(page).toHaveURL(new RegExp(`/app/agent/${data.trader.id}$`));
  await page.goBack();
  await page.locator(".chat-head .chat-name").click();
  await expect(page).toHaveURL(new RegExp(`/app/agent/${data.trader.id}$`));
  await page.goBack();
  await page.getByRole("button", { name: "Chat menu", exact: true }).click();
  await page.getByRole("menuitem", { name: "Agent info" }).click();
  await expect(page).toHaveURL(new RegExp(`/app/agent/${data.trader.id}$`));
  await expect(page.locator("#dialog[open]")).toHaveCount(0);

  await page.goto(`/app/g/${data.group.id}`);
  await page.locator(".chat-head .head-avatar").click();
  await expect(page).toHaveURL(new RegExp(`/app/group/${data.group.id}$`));
  await page.goBack();
  await page.getByRole("button", { name: "Chat menu", exact: true }).click();
  await page.getByRole("menuitem", { name: "Group info" }).click();
  await expect(page).toHaveURL(new RegExp(`/app/group/${data.group.id}$`));
});

test("the menu opens while the agents are still loading", async ({ page }) => {
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  await page.route(/\/api\/agents(\?.*)?$/, async (route) => {
    await gate;
    await route.continue();
  });
  // A group's menu is built from the group: it opens at once.
  await page.goto(`/app/g/${data.group.id}`);
  await expect(page.locator(".chat-name")).toHaveText(data.group.payload.name);
  const button = page.getByRole("button", { name: "Chat menu", exact: true });
  await expect(button).toBeEnabled();
  await button.click();
  await expect(page.getByRole("menuitem", { name: "Group info" })).toBeVisible();
  // An agent's chat: a tap before the agent arrives opens the menu once it does.
  await page.goto(`/app/${data.trader.id}`);
  await expect(button).toBeEnabled();
  await button.click();
  await expect(page.getByRole("menu", { name: "Chat menu" })).toHaveCount(0);
  release();
  await expect(page.getByRole("menuitem", { name: "Agent info" })).toBeVisible();
  await page.unrouteAll({ behavior: "wait" });
});

test("«New task» keeps the chat's agent, and a group's coordinator", async ({ page }) => {
  await page.goto(`/app/${data.trader.id}`);
  await page.getByRole("button", { name: "Chat menu", exact: true }).click();
  await page.getByRole("menuitem", { name: "New task" }).click();
  await expect(page).toHaveURL(new RegExp(`/app/new-task\\?agent=${data.trader.id}$`));
  await page.goto(`/app/g/${data.group.id}`);
  await page.getByRole("button", { name: "Chat menu", exact: true }).click();
  await page.getByRole("menuitem", { name: "New task" }).click();
  await expect(page).toHaveURL(new RegExp(`/app/new-task\\?agent=${data.research.id}$`));
});

test("«Clear the chat» asks, hides the history for the owner and drops the draft", async ({
  page,
  context,
}) => {
  const thread = await (
    await context.request.post(`/api/agents/${data.research.id}/conversation`, {
      headers,
      data: {},
    })
  ).json();
  const sent = await context.request.post(`/api/threads/${thread.id}/messages`, {
    headers,
    data: { content: "A message to clear", client_nonce: randomUUID() },
  });
  expect(sent.ok()).toBeTruthy();
  await page.goto(`/app/${data.research.id}`);
  const transcript = page.getByTestId("transcript");
  await expect(transcript).toContainText("A message to clear");
  await page.locator(".composer textarea").fill("An unsent draft");
  await page.getByRole("button", { name: "Chat menu", exact: true }).click();
  await page.getByRole("menuitem", { name: "Clear the chat" }).click();
  const sheet = page.locator("#dialog");
  await expect(sheet).toHaveAttribute("aria-label", "Clear the chat");
  await expect(sheet).toContainText("The agent and its record stay.");
  await sheet.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(transcript).toContainText("A message to clear");
  await page.getByRole("button", { name: "Chat menu", exact: true }).click();
  await page.getByRole("menuitem", { name: "Clear the chat" }).click();
  const clearing = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === `/api/threads/${thread.id}/clear` &&
      response.request().method() === "POST",
  );
  await sheet.getByRole("button", { name: "Clear", exact: true }).click();
  expect((await clearing).ok()).toBeTruthy();
  await expect(transcript).not.toContainText("A message to clear");
  await expect(page.locator(".composer textarea")).toHaveValue("");
  await page.reload();
  await expect(page.locator(".chat-head .chat-name")).toContainText(data.research.name);
  await expect(page.getByTestId("transcript")).not.toContainText("A message to clear");
  await expect(page.locator(".composer textarea")).toHaveValue("");
});

test("the group's «Members» chip lists each member's permission", async ({ page }) => {
  await page.goto(`/app/g/${data.group.id}`);
  await page.locator(".composer .mode-chip").click();
  const sheet = page.locator("#dialog");
  await expect(sheet).toHaveAttribute("aria-label", "Members' permissions");
  await expect(sheet.locator(".row", { hasText: data.research.name })).toContainText(
    "Gathers and summarises information · no permissions",
  );
  const trader = sheet.locator("button.row", { hasText: data.trader.name });
  await expect(trader).toContainText("Ask me");
  await trader.click();
  await expect(page).toHaveURL(new RegExp(`/app/${data.trader.id}$`));
});
