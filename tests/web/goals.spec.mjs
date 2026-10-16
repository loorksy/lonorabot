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

test("owner reviews a durable goal and controls limits, autonomy, pause, same-thread wake and cancellation", async ({
  page,
  context,
}) => {
  const data = fixture({ action: "init" });
  const device = await context.newCDPSession(page);
  await device.send("WebAuthn.enable");
  await device.send("WebAuthn.addVirtualAuthenticator", {
    options: {
      protocol: "ctap2",
      transport: "internal",
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
      automaticPresenceSimulation: true,
    },
  });
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
    await page.getByRole("button", { name: `Agent settings: ${agent.name}`, exact: true }).click();
    await page.getByRole("button", { name: "Goals", exact: true }).click();
    const card = page.locator(`[data-goal-id='${goal.id}']`);
    await expect(card.getByText(goal.payload.title, { exact: true })).toBeVisible();
    const autonomy = card.getByLabel("Allow autonomous trading for this goal", { exact: true });
    await expect(autonomy).not.toBeChecked();
    await card.getByLabel("Maximum volume", { exact: true }).fill("0.2");
    // The controlled value follows durable server admission, not an optimistic toggle.
    await autonomy.click();
    await expect(autonomy).not.toBeChecked();
    // A first activation attempt explains missing enrollment and opens its
    // real registration flow instead of leaving the user at a dead-end error.
    await card
      .getByRole("button", { name: "Activate with device authentication", exact: true })
      .click();
    await expect(card.getByLabel("Confirm account password", { exact: true })).toBeVisible();
    await card
      .getByLabel("Confirm account password", { exact: true })
      .fill("ci-only-owner-password");
    await card.getByRole("button", { name: "Register this device", exact: true }).click();
    await expect(card.getByLabel("Confirm account password", { exact: true })).toHaveCount(0);
    await card
      .getByRole("button", { name: "Activate with device authentication", exact: true })
      .click();
    await expect(autonomy).toBeChecked();
    const current = await (await context.request.get(`/api/trading/goals/${goal.id}`)).json();
    expect(current.state.autonomous).toBe(true);
    expect(current.payload.maximum_volume).toBe("0.2");
    await card.getByRole("button", { name: "Pause", exact: true }).click();
    await expect(card.getByRole("button", { name: "Resume", exact: true })).toBeVisible();
    await page.reload();
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
    await expect(autonomy).toBeDisabled();
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

test("signed Shadow goal is visibly virtual and cannot inherit live authority after mode changes", async ({
  page,
  context,
}) => {
  const data = fixture({ action: "init" });
  const headers = {
    "X-CSRF-Token": data.cookies.find((cookie) => cookie.name === "lonora_csrf").value,
  };
  await context.addCookies(
    data.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const device = await context.newCDPSession(page);
  await device.send("WebAuthn.enable");
  await device.send("WebAuthn.addVirtualAuthenticator", {
    options: {
      protocol: "ctap2",
      transport: "internal",
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
      automaticPresenceSimulation: true,
    },
  });
  let agent;
  try {
    agent = await (
      await context.request.post("/api/agents", {
        headers,
        data: {
          name: `Shadow goal ${randomUUID()}`,
          trading_account_id: data.account,
          trading_symbol: data.symbol,
        },
      })
    ).json();
    expect(
      (
        await context.request.put(`/api/agents/${agent.id}/execution-mode`, {
          headers,
          data: { execution_mode: "shadow" },
        })
      ).ok(),
    ).toBeTruthy();
    const thread = await (
      await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
    ).json();
    const goalResponse = await context.request.post("/api/trading/goals", {
      headers,
      data: {
        agent_id: agent.id,
        thread_id: thread.id,
        account_id: data.account,
        symbol: data.symbol,
        title: "Shadow plan review",
        objective: "Review source evidence without a real broker order",
        maximum_volume: "0.1",
        max_trade_actions: 1,
        steps: [{ id: "review", title: "Inspect actual market evidence", kind: "analysis" }],
      },
    });
    expect(goalResponse.status()).toBe(201);
    const goal = await goalResponse.json();
    expect(goal.execution_mode).toBe("shadow");
    const proposed = await context.request.post(`/api/agents/${agent.id}/super-bot/proposals`, {
      headers,
      data: { goal_id: goal.id, mode: "autonomous" },
    });
    expect(proposed.status()).toBe(201);
    const request = await proposed.json();
    await page.goto(`/app/${agent.id}`);
    const card = page.locator(`[data-super-bot-id='${request.id}']`);
    await expect(
      card.getByText("Shadow trading — virtual orders only", { exact: true }),
    ).toBeVisible();
    await card.getByRole("button", { name: "Register a passkey", exact: true }).click();
    // Password inputs deliberately have no textbox role in every engine.
    await page
      .getByLabel("Confirm account password", { exact: true })
      .fill("ci-only-owner-password");
    await page.getByRole("button", { name: "Register this device", exact: true }).click();
    await expect(page.getByLabel("Confirm account password", { exact: true })).toHaveCount(0);
    await card
      .getByRole("button", { name: "Activate with device authentication", exact: true })
      .click();
    await expect(card.getByText("Super Bot · Active", { exact: true })).toBeVisible();
    const active = await (await context.request.get(`/api/trading/goals/${goal.id}`)).json();
    expect(active.state).toMatchObject({ execution_mode: "shadow", autonomous: true });
    expect((await (await context.request.get("/api/trading/controls")).json()).enabled).toBe(false);
    expect(
      (
        await context.request.put(`/api/agents/${agent.id}/execution-mode`, {
          headers,
          data: { execution_mode: "live" },
        })
      ).ok(),
    ).toBeTruthy();
    await page.reload();
    await expect(card.getByText("Super Bot · Stopped", { exact: true })).toBeVisible();
    await expect(
      card.getByText("Shadow trading — virtual orders only", { exact: true }),
    ).toBeVisible();
    const paused = await (await context.request.get(`/api/trading/goals/${goal.id}`)).json();
    expect(paused.state).toMatchObject({
      execution_mode: "shadow",
      autonomous: false,
      status: "paused",
    });
  } finally {
    if (agent) await context.request.delete(`/api/agents/${agent.id}`, { headers });
    fixture({ ...data, action: "cleanup" });
  }
});
