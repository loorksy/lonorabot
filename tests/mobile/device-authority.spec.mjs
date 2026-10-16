import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

test("Expo chat reviews and rejects the real durable scoped authorization request", async ({
  page,
  context,
}) => {
  const data = JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify({ action: "init" }),
      encoding: "utf8",
    }),
  );
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
  const response = await context.request.post("/api/agents", {
    headers,
    data: {
      name: `Device review ${randomUUID()}`,
      trading_account_id: data.account,
      trading_symbol: data.symbol,
    },
  });
  expect(response.status()).toBe(201);
  const agent = await response.json();
  try {
    const thread = await (
      await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
    ).json();
    const goal = await (
      await context.request.post("/api/trading/goals", {
        headers,
        data: {
          agent_id: agent.id,
          thread_id: thread.id,
          account_id: data.account,
          symbol: data.symbol,
          title: "Device review plan",
          objective: "Review actual evidence without financial execution",
          maximum_volume: "0.1",
          max_trade_actions: 1,
          steps: [{ id: "review", title: "Read current broker evidence", kind: "analysis" }],
        },
      })
    ).json();
    const proposal = await context.request.post(`/api/agents/${agent.id}/super-bot/proposals`, {
      headers,
      data: { goal_id: goal.id, mode: "supervised" },
    });
    expect(proposal.status()).toBe(201);
    await page.goto(`/thread?id=${thread.id}`);
    await expect(page.getByText("Device review plan", { exact: true })).toBeVisible();
    await expect(page.getByText("سوبر بوت · بانتظار تفويض الجهاز", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "مراجعة الخطة", exact: true }).click();
    await expect(page.getByText("Read current broker evidence", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "رفض", exact: true }).click();
    await expect(page.getByText("سوبر بوت · مرفوض", { exact: true })).toBeVisible();
    await page.reload();
    await expect(page.getByText("سوبر بوت · مرفوض", { exact: true })).toBeVisible();
    expect(
      (await (await context.request.get(`/api/trading/goals/${goal.id}`)).json()).state.autonomous,
    ).toBe(false);
  } finally {
    await context.request.delete(`/api/agents/${agent.id}`, { headers });
  }
});
