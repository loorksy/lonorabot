import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

/* A conversation's ⋮ menu is a popover built from the conversation itself: it opens at once.
   Its header (avatar and name) opens the agent's sheet only once the agent is loaded. */
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
  // Waits for a held request still being continued, so none is handled twice.
  return { release, unroute: () => page.unrouteAll({ behavior: "wait" }) };
}

/** The avatar and the name open nothing before the agent is there. While the agents load they
    may be absent or empty, so any there are clicked in the page, not by the pointer. */
async function expectHeaderInert(page, path) {
  await page.evaluate(() => {
    for (const selector of [".head-avatar", ".chat-name"])
      document.querySelector(selector)?.click();
  });
  await expect(page.locator("#dialog[open]")).toHaveCount(0);
  await expect(page).toHaveURL(path);
}

test("an agent's menu opens at once; its header waits for the agent", async ({ page, context }) => {
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
    await expect(menu).toBeEnabled();
    await expectHeaderInert(page, new RegExp(`/app/${agent.id}$`));
    held.release();
    await held.unroute();
    expect(errors).toEqual([]);
  } finally {
    held?.release();
    if (agent) await context.request.delete(`/api/agents/${agent.id}`, { headers });
    fixture({ ...data, action: "cleanup" });
  }
});

test("a group's menu opens before its member agents arrive", async ({ page, context }) => {
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
    // The ⋮ menu is a popover built from the group itself: it opens at once.
    const menu = page.getByRole("button", { name: "Chat menu", exact: true });
    await expect(menu).toBeEnabled();
    await menu.click();
    await page.getByRole("menuitem", { name: "Group info" }).click();
    await expect(page).toHaveURL(new RegExp(`/app/group/${group.id}$`));
    held.release();
    await held.unroute();
    await expect(page.locator("main").getByText(name).first()).toBeVisible();
  } finally {
    held?.release();
    if (group) await context.request.delete(`/api/groups/${group.id}`, { headers });
    if (agent) await context.request.delete(`/api/agents/${agent.id}`, { headers });
    fixture({ ...data, action: "cleanup" });
  }
});
