import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

/* The composer's / commands (reference commandOptions, assistUpdate, runCommand and cmdMarkup,
   Desktop-37 5089-5247): a «/» that starts the message opens the same floating list as @;
   «مهمة», «بحث», «ملخص» and a skill are sent as the owner's message with the command the
   server keeps; the others open what the chat already has. */
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
    if (!localStorage.getItem("lonora.locale")) localStorage.setItem("lonora.locale", "en");
  });
  page.on("pageerror", (error) => errors.push(error.message));
});
test.afterEach(() => {
  expect(errors.splice(0)).toEqual([]);
  if (data) fixture({ ...data, action: "cleanup" });
  data = null;
});

const field = (page) => page.getByRole("combobox");
const rows = (page) => page.getByRole("listbox", { name: "Commands" }).getByRole("option");
const names = (page) => rows(page).locator("strong > span");

test("the / list: this chat's commands in order, filtered, and picked with a hint", async ({
  page,
}) => {
  await page.goto(`/app/${data.trader.id}`);
  await field(page).fill("/");
  await expect(names(page)).toHaveText([
    "/task",
    "/search",
    "/summary",
    "/chart",
    "/call",
    "/clear",
  ]);
  await expect(page.locator(".assist[data-type=command] .as-sec")).toHaveText("Commands");
  await expect(rows(page).nth(0).locator("em")).toHaveText("Task title");
  await expect(rows(page).nth(5).locator(".as-ic")).toHaveClass(/danger/);
  // The typed part is marked, and only what matches stays.
  await field(page).fill("/sum");
  await expect(names(page)).toHaveText(["/summary"]);
  await expect(rows(page).locator("strong b")).toHaveText("sum");
  await field(page).fill("/zz");
  await expect(page.locator(".as-empty")).toHaveText("No command by that name");
  await expect(rows(page)).toHaveCount(0);
  // A «/» that does not start the message is text.
  await field(page).fill("see /task");
  await expect(page.locator(".assist")).toHaveCount(0);
  // A command that takes text stays in the field as plain text, with its hint.
  await field(page).fill("/sea");
  await page.keyboard.press("Enter");
  await expect(field(page)).toHaveValue("/search ");
  await expect(page.locator(".ta-mirror mark.cmd")).toHaveText("/search");
  await expect(page.locator(".ta-mirror .ghost")).toHaveText("What are you looking for?");
  await expect(page.locator(".assist")).toHaveCount(0);
  // Esc closes the list until the «/» is gone; @ still works after it.
  await field(page).fill("/");
  await page.keyboard.press("Escape");
  await expect(page.locator(".assist")).toHaveCount(0);
  await field(page).fill("/tas");
  await expect(page.locator(".assist")).toHaveCount(0);
  await field(page).fill("");
  await field(page).fill("/tas");
  await expect(names(page)).toHaveText(["/task"]);

  // An agent that does not trade has no chart; a group has no task or call.
  await page.goto(`/app/${data.research.id}`);
  await field(page).fill("/");
  await expect(names(page)).toHaveText(["/task", "/search", "/summary", "/call", "/clear"]);
  await page.goto(`/app/g/${data.group.id}`);
  await field(page).fill("/");
  await expect(names(page)).toHaveText(["/search", "/summary", "/chart", "/clear"]);
});

test("in Arabic the commands are Arabic and their English names still find them", async ({
  page,
  context,
}) => {
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "ar"));
  await page.goto(`/app/${data.research.id}`);
  const list = page.getByRole("listbox", { name: "الأوامر" });
  await field(page).fill("/بح");
  await expect(list.getByRole("option").locator("strong > span")).toHaveText(["/بحث"]);
  await expect(list.getByRole("option").locator(".as-end")).toHaveText("/search");
  await field(page).fill("/sum");
  await expect(list.getByRole("option").locator("strong > span")).toHaveText(["/ملخص"]);
});

test("a / command reaches the server with its command and draws its chip", async ({ page }) => {
  await page.goto(`/app/${data.research.id}`);
  const sent = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && /\/api\/threads\/[^/]+\/messages$/.test(request.url()))
      sent.push(request.postDataJSON());
  });
  // A task with no title asks for it and sends nothing.
  await field(page).fill("/task");
  await page.keyboard.press("Escape");
  await page.keyboard.press("Enter");
  await expect(page.locator("#toast")).toHaveText("Write the task title after ‎/task");
  await expect(field(page)).toHaveValue("/task");
  expect(sent).toEqual([]);

  await field(page).fill("/search gold prices");
  await page.keyboard.press("Enter");
  await expect(field(page)).toHaveValue("");
  const bubble = page.locator(".msg.mine .bubble").last();
  await expect(bubble.locator(".cmd-chip")).toHaveText("search");
  await expect(bubble.locator(".text").first()).toHaveText("search gold prices");
  await expect.poll(() => sent.length).toBe(1);
  expect(sent[0].content).toBe("/search gold prices");
  expect(sent[0].command).toEqual({ name: "search", argument: "gold prices" });
  // The chip is what the server kept, so it is still there from the server's copy.
  await page.reload();
  await expect(page.locator(".msg.mine .bubble .cmd-chip")).toHaveText("search");

  // «ملخص» is sent at once; text that is not a command stays text, with no chip.
  await field(page).fill("/summ");
  await page.keyboard.press("Enter");
  await expect.poll(() => sent.length).toBe(2);
  expect(sent[1]).toMatchObject({ content: "/summary", command: { name: "summary" } });
  await expect(page.locator(".msg.mine .bubble").last()).toHaveText(/summary\s+the conversation/);
  await field(page).fill("/foo bar");
  await page.keyboard.press("Enter");
  await expect.poll(() => sent.length).toBe(3);
  expect(sent[2].command).toBeUndefined();
  await expect(page.locator(".msg.mine .bubble").last().locator(".cmd-chip")).toHaveCount(0);
});

test("the commands that send nothing open what the chat already has", async ({ page }) => {
  await page.goto(`/app/${data.trader.id}`);
  const sent = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && /\/api\/threads\/[^/]+\/messages$/.test(request.url()))
      sent.push(request.url());
  });
  const sheet = page.locator("#dialog");
  const run = async (typed) => {
    // A sheet that is still closing keeps the page behind it inert: wait for it to go.
    await expect(sheet).not.toHaveAttribute("open", "");
    await field(page).fill(typed);
    await expect(field(page)).toHaveValue(typed);
    await page.keyboard.press("Enter");
    await expect(field(page)).toHaveValue("");
  };
  await run("/chart");
  await expect(sheet).toHaveAttribute("open", "");
  await page.keyboard.press("Escape");
  await expect(sheet).not.toHaveAttribute("open", "");
  // The clear confirm is the chat menu's own: nothing is hidden until it is confirmed.
  await run("/clear");
  await expect(sheet.getByRole("heading", { name: "Clear the chat" })).toBeVisible();
  await sheet.getByRole("button", { name: "Cancel" }).click();
  // Without a voice provider the call explains how to set one up (Q58).
  const voice = await (await page.request.get("/api/voice/status")).json();
  if (!voice.transport_configured) {
    await run("/call");
    await expect(sheet).toContainText("Calls are not set up");
    await page.keyboard.press("Escape");
  }
  expect(sent).toEqual([]);
});
