import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

test("Expo approval buttons show durable real broker receipts", async ({ page, context }) => {
  const fixture = (data) =>
    JSON.parse(
      execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
        input: JSON.stringify(data),
        encoding: "utf8",
      }),
    );
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
  const created = await context.request.post("/api/agents", {
    headers,
    data: { name: `Mobile approval ${randomUUID()}` },
  });
  expect(created.status()).toBe(201);
  const agent = await created.json();
  try {
    const conversation = await context.request.post(`/api/agents/${agent.id}/conversation`, {
      headers,
      data: {},
    });
    const thread = await conversation.json();
    const approval = {
      id: randomUUID(),
      thread_id: thread.id,
      status: "pending",
      requests: [
        { action: "close_position", symbol: "BTCUSD.demo", position_id: "manual-ticket-5" },
      ],
      results: [],
    };
    let decisions = 0;
    await page.route("**/api/trading/approvals?*", (route) => route.fulfill({ json: [approval] }));
    await page.route(`**/api/trading/approvals/${approval.id}/decision`, async (route) => {
      expect(route.request().postDataJSON()).toEqual({ decision: "approve" });
      decisions++;
      approval.status = "completed";
      approval.results = [
        {
          operation_id: "fixed-operation",
          status: "confirmed",
          broker_id: "manual-ticket-5",
          details: { price: "65000.25" },
        },
      ];
      await route.fulfill({ json: approval });
    });
    await page.goto(`/thread?id=${thread.id}`);
    await expect(
      page.getByText("close_position · BTCUSD.demo · manual-ticket-5", { exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "موافقة", exact: true }).click();
    await expect(page.getByText("manual-ticket-5 · 65000.25", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "موافقة", exact: true })).toHaveCount(0);
    await page.reload();
    await expect(page.getByText("manual-ticket-5 · 65000.25", { exact: true })).toBeVisible();
    expect(decisions).toBe(1);
  } finally {
    await context.request.delete(`/api/agents/${agent.id}`, { headers });
    fixture({ ...data, action: "cleanup" });
  }
});
