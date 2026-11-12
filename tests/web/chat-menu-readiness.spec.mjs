import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

/* A conversation's menu and its agent's info page open only once the agents are loaded:
   the menu keeps the body it opened with, so it never opens without its agent's rows. */
function fixture(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}

async function signIn(context, data) {
  await context.addCookies(
    data.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
}

async function createAgent(context, data, headers, name) {
  const created = await context.request.post("/api/agents", {
    headers,
    data: { name, trading_account_id: data.account, trading_symbol: data.symbol },
  });
  expect(created.status()).toBe(201);
  return created.json();
}

/** Holds back the agent list until the returned release is called. */
async function holdAgents(page) {
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  const slowAgents = /\/api\/agents(\?.*)?$/;
  await page.route(slowAgents, async (route) => {
    await gate;
    await route.continue();
  });
  return { release, unroute: () => page.unroute(slowAgents) };
}

/** The avatar and the name open the info page: not before the agents are there. Without
    an agent they are empty, so they are clicked in the page, not by the pointer. */
async function expectHeaderInert(page) {
  const clicked = await page.evaluate(() =>
    [".head-avatar", ".chat-name"].map((selector) => {
      const button = document.querySelector(selector);
      button?.click();
      return Boolean(button);
    }),
  );
  expect(clicked).toEqual([true, true]);
  await expect(page.locator("#dialog[open]")).toHaveCount(0);
}

test("an agent's menu waits for the agent list before it opens", async ({ page, context }) => {
  const data = fixture({ action: "init" });
  const headers = {
    "X-CSRF-Token": data.cookies.find((cookie) => cookie.name === "lonora_csrf").value,
  };
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  let agent;
  let held;
  try {
    await signIn(context, data);
    agent = await createAgent(context, data, headers, `Menu ${randomUUID()}`);
    await page.goto(`/app/${agent.id}`);
    const menu = page.getByRole("button", { name: "Chat menu", exact: true });
    await expect(menu).toBeEnabled();
    held = await holdAgents(page);
    await page.reload();
    await expect(menu).toBeDisabled();
    await expectHeaderInert(page);
    held.release();
    await expect(menu).toBeEnabled();
    await held.unroute();
    expect(errors).toEqual([]);
  } finally {
    held?.release();
    if (agent) await context.request.delete(`/api/agents/${agent.id}`, { headers });
    fixture({ ...data, action: "cleanup" });
  }
});

test("a group's menu waits for its member agents before it opens", async ({ page, context }) => {
  const data = fixture({ action: "init" });
  const headers = {
    "X-CSRF-Token": data.cookies.find((cookie) => cookie.name === "lonora_csrf").value,
  };
  let agent;
  let group;
  let held;
  try {
    await signIn(context, data);
    const name = `Member ${randomUUID()}`;
    agent = await createAgent(context, data, headers, name);
    const response = await context.request.post("/api/groups/create", {
      headers,
      data: {
        name: `Group ${randomUUID()}`,
        member_ids: [agent.id],
        participation: "mentions_or_lead",
      },
    });
    expect(response.ok()).toBeTruthy();
    group = await response.json();
    // The group arrives at once, its member agents late: its pages are built from both.
    held = await holdAgents(page);
    await page.goto(`/app/g/${group.id}`);
    await expect(page.locator(".chat-name")).toHaveText(group.payload.name);
    const menu = page.getByRole("button", { name: "Chat menu", exact: true });
    await expect(menu).toBeDisabled();
    await expectHeaderInert(page);
    held.release();
    await expect(menu).toBeEnabled();
    await menu.click();
    await held.unroute();
    await page.locator("#dialog").getByRole("button", { name: "Group info", exact: true }).click();
    await expect(page.locator("#dialog").getByText(name).first()).toBeVisible();
  } finally {
    held?.release();
    if (group) await context.request.delete(`/api/groups/${group.id}`, { headers });
    if (agent) await context.request.delete(`/api/agents/${agent.id}`, { headers });
    fixture({ ...data, action: "cleanup" });
  }
});
