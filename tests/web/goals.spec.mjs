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
    await page.goto(`/app/${agent.id}`);
    await page.getByRole("button", { name: "Chat menu", exact: true }).click();
    await page.locator("#dialog").getByRole("button", { name: "Goals", exact: true }).click();
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
    // The agent list arrives late after this reload: the chat menu waits for it, so it is
    // never opened without the agent's Goals row (the menu keeps the body it opened with).
    const slowAgents = /\/api\/agents(\?.*)?$/;
    await page.route(slowAgents, async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 1500));
      await route.continue();
    });
    await page.reload();
    await expect(page.getByRole("button", { name: "Chat menu", exact: true })).toBeDisabled();
    // The avatar and the name open the agent's info page: not before the agent is there.
    // (Without an agent they are empty, so they are clicked in the page, not by the pointer.)
    const clicked = await page.evaluate(() =>
      [".head-avatar", ".chat-name"].map((selector) => {
        const button = document.querySelector(selector);
        button?.click();
        return Boolean(button);
      }),
    );
    expect(clicked).toEqual([true, true]);
    await expect(page.locator("#dialog[open]")).toHaveCount(0);
    // Sheets are not remembered across a reload: open the goals again from the chat menu.
    await page.getByRole("button", { name: "Chat menu", exact: true }).click();
    await page.unroute(slowAgents);
    await page.locator("#dialog").getByRole("button", { name: "Goals", exact: true }).click();
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
    if (agent)
      expect([200, 404]).toContain(
        (await context.request.delete(`/api/agents/${agent.id}`, { headers })).status(),
      );
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
    await page.route(slowAgents, async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 1500));
      await route.continue();
    });
    await page.goto(`/app/g/${group.id}`);
    const menu = page.getByRole("button", { name: "Chat menu", exact: true });
    await expect(menu).toBeDisabled();
    const clicked = await page.evaluate(() =>
      [".head-avatar", ".chat-name"].map((selector) => {
        const button = document.querySelector(selector);
        button?.click();
        return Boolean(button);
      }),
    );
    expect(clicked).toEqual([true, true]);
    await expect(page.locator("#dialog[open]")).toHaveCount(0);
    await menu.click();
    await page.unroute(slowAgents);
    await page.locator("#dialog").getByRole("button", { name: "Group info", exact: true }).click();
    await expect(page.locator("#dialog").getByText(name).first()).toBeVisible();
  } finally {
    if (group) await context.request.delete(`/api/groups/${group.id}`, { headers });
    if (agent) await context.request.delete(`/api/agents/${agent.id}`, { headers });
    fixture({ ...data, action: "cleanup" });
  }
});
