import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

function fixture(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}

test("a goal is a plan under the agent's level: pause, same-thread wake and cancellation, no autonomy switch", async ({
  page,
  context,
}) => {
  const data = fixture({ action: "init" });
  let agent;
  let releaseAgents;
  const headers = {
    "X-CSRF-Token": data.cookies.find((cookie) => cookie.name === "lonora_csrf").value,
  };
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
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
    const created = await context.request.post("/api/agents", {
      headers,
      data: {
        name: `Goal UI ${randomUUID()}`,
        trading_account_id: data.account,
        trading_symbol: data.symbol,
      },
    });
    expect(created.status()).toBe(201);
    agent = await created.json();
    const conversation = await context.request.post(`/api/agents/${agent.id}/conversation`, {
      headers,
      data: {},
    });
    expect(conversation.ok()).toBeTruthy();
    const thread = await conversation.json();
    const goalResponse = await context.request.post("/api/trading/goals", {
      headers,
      data: {
        agent_id: agent.id,
        thread_id: thread.id,
        title: "Review market evidence",
        objective: "Wait and review without an automatic financial order.",
        account_id: data.account,
        symbol: data.symbol,
        maximum_volume: "0.1",
        max_trade_actions: 2,
        steps: [{ id: "review", title: "Read current broker evidence", kind: "analysis" }],
      },
    });
    expect(goalResponse.status()).toBe(201);
    const goal = await goalResponse.json();
    // «الأهداف» is a row of the agent's page; a trading agent's plans keep their card there.
    const openGoals = async () => {
      await page.goto(`/app/agent/${agent.id}`);
      await page.getByRole("button", { name: "Goals", exact: true }).click();
      await expect(page).toHaveURL(/\/app\/goals\?agent=/);
    };
    await openGoals();
    const card = page.locator(`[data-goal-id='${goal.id}']`);
    await expect(card.getByText(goal.payload.title, { exact: true })).toBeVisible();
    // No second authority system: no per-goal autonomy switch, limit knobs or Super Bot.
    await expect(
      card.getByLabel("Allow autonomous trading for this goal", { exact: true }),
    ).toHaveCount(0);
    await expect(card.getByLabel("Maximum volume", { exact: true })).toHaveCount(0);
    await expect(card.getByText(/Super Bot/)).toHaveCount(0);
    await expect(
      card.getByText(/This goal is a plan under the agent's trading level and signed grant/),
    ).toBeVisible();
    const current = await (await context.request.get(`/api/trading/goals/${goal.id}`)).json();
    expect(current.state).not.toHaveProperty("autonomous");
    await card.getByRole("button", { name: "Pause", exact: true }).click();
    await expect(card.getByRole("button", { name: "Resume", exact: true })).toBeVisible();
    // The agent list arrives late when the conversation opens: the avatar and the name wait
    // for it (the ⋮ menu is a popover and opens at once, as for a group).
    const slowAgents = /\/api\/agents(\?.*)?$/;
    const agentsGate = new Promise((resolve) => {
      releaseAgents = resolve;
    });
    await page.route(slowAgents, async (route) => {
      await agentsGate;
      await route.continue();
    });
    await page.goto(`/app/${agent.id}`);
    // The avatar and the name open the agent's info page: not before the agent is there.
    // (Before it they may be absent or empty, so any there are clicked in the page.)
    await page.evaluate(() => {
      for (const selector of [".head-avatar", ".chat-name"])
        document.querySelector(selector)?.click();
    });
    await expect(page.locator("#dialog[open]")).toHaveCount(0);
    await expect(page).toHaveURL(new RegExp(`/app/${agent.id}$`));
    releaseAgents();
    await page.unroute(slowAgents);
    await openGoals();
    await expect(card.getByRole("button", { name: "Resume", exact: true })).toBeVisible();
    await card.getByRole("button", { name: "Resume", exact: true }).click();
    await expect(card.getByRole("button", { name: "Pause", exact: true })).toBeVisible();
    const waking = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/trading/goals/${goal.id}/wake`) &&
        response.request().method() === "POST",
    );
    await card.getByRole("button", { name: "Review now", exact: true }).click();
    const wake = await (await waking).json();
    const run = await (await context.request.get(`/api/runs/${wake.id}`)).json();
    expect(run.thread_id).toBe(thread.id);
    expect(run.agent_id).toBe(agent.id);
    await card.getByText("Execution history", { exact: true }).click();
    await expect(card.getByText("No financial executions yet.", { exact: true })).toBeVisible();
    await card.getByRole("button", { name: "Cancel goal", exact: true }).click();
    await expect(card.getByRole("button", { name: "Cancel goal", exact: true })).toBeDisabled();
    await expect
      .poll(
        async () =>
          (await (await context.request.get(`/api/trading/goals/${goal.id}`)).json()).state.status,
      )
      .toBe("cancelled");
    expect(errors).toEqual([]);
  } finally {
    releaseAgents?.();
    if (agent)
      expect([200, 404]).toContain(
        (await context.request.delete(`/api/agents/${agent.id}`, { headers })).status(),
      );
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
  let releaseAgents;
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
    const name = `Member ${randomUUID()}`;
    const created = await context.request.post("/api/agents", {
      headers,
      data: { name, trading_account_id: data.account, trading_symbol: data.symbol },
    });
    expect(created.status()).toBe(201);
    agent = await created.json();
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
    const slowAgents = /\/api\/agents(\?.*)?$/;
    const agentsGate = new Promise((resolve) => {
      releaseAgents = resolve;
    });
    await page.route(slowAgents, async (route) => {
      await agentsGate;
      await route.continue();
    });
    await page.goto(`/app/g/${group.id}`);
    await expect(page.locator(".chat-name")).toHaveText(group.payload.name);
    // The ⋮ menu is a popover built from the group itself: it opens at once.
    const menu = page.getByRole("button", { name: "Chat menu", exact: true });
    await expect(menu).toBeEnabled();
    await menu.click();
    await page.getByRole("menuitem", { name: "Group info" }).click();
    await expect(page).toHaveURL(new RegExp(`/app/group/${group.id}$`));
    releaseAgents();
    await page.unrouteAll({ behavior: "wait" });
    await expect(page.locator("main").getByText(name).first()).toBeVisible();
  } finally {
    releaseAgents?.();
    if (group) await context.request.delete(`/api/groups/${group.id}`, { headers });
    if (agent) await context.request.delete(`/api/agents/${agent.id}`, { headers });
    fixture({ ...data, action: "cleanup" });
  }
});
