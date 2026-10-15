import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

test("approval remains causal in chat, resolves in place and reconnect clears recovered fetch failure", async ({
  page,
  context,
}) => {
  const fixture = JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify({ action: "init" }),
      encoding: "utf8",
    }),
  );
  await context.addCookies(
    fixture.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  const headers = {
    "X-CSRF-Token": fixture.cookies.find((row) => row.name === "lonora_csrf").value,
  };
  const created = await context.request.post("/api/agents", {
    headers,
    data: {
      name: `Web chronology ${randomUUID()}`,
      trading_account_id: fixture.account,
      trading_symbol: fixture.symbol,
    },
  });
  const agent = await created.json();
  const thread = await (
    await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
  ).json();
  const messages = [1, 2].map((seq) => ({
    id: `chronology-${seq}`,
    seq,
    thread_id: thread.id,
    agent_id: agent.id,
    role: "assistant",
    content: seq === 1 ? "before approval" : "after broker result",
    created_at: "2026-10-15T12:00:00Z",
    reply_to: null,
    attachment_ids: [],
  }));
  const approval = {
    id: randomUUID(),
    thread_id: thread.id,
    agent_id: agent.id,
    run_id: "run",
    timeline_seq: 2,
    created_at: messages[1].created_at,
    status: "pending",
    requests: [{ action: "buy", symbol: "EURUSDm", volume: "0.01" }],
    results: [],
  };
  let failing = true;
  await page.route(`**/api/threads/${thread.id}/messages*`, (route) =>
    failing
      ? route.fulfill({ status: 503, json: { code: "request_failed" } })
      : route.fulfill({ json: messages }),
  );
  await page.route("**/api/trading/approvals?*", (route) => route.fulfill({ json: [approval] }));
  await page.route(`**/api/trading/approvals/${approval.id}/decision`, (route) => {
    approval.status = "rejected";
    return route.fulfill({ json: approval });
  });
  try {
    await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
    await page.goto(`/app/${agent.id}`);
    await expect(page.locator(".template-thread-error")).toHaveCount(1);
    failing = false;
    await page.evaluate(() => window.dispatchEvent(new Event("online")));
    await expect(page.getByText("after broker result", { exact: true })).toBeVisible();
    await expect(page.locator(".template-thread-error")).toHaveCount(0);
    const card = page.locator(`[data-trade-approval="${approval.id}"]`);
    await expect(card).toHaveCount(1);
    const before = await page.getByText("before approval", { exact: true }).boundingBox();
    const after = await page.getByText("after broker result", { exact: true }).boundingBox();
    const anchor = await card.boundingBox();
    expect(before.y).toBeLessThan(anchor.y);
    expect(after.y).toBeGreaterThan(anchor.y);
    await card.getByRole("button", { name: "Reject", exact: true }).click();
    await expect(card.getByText("Rejected", { exact: true })).toBeVisible();
    await page.reload();
    await expect(card.getByText("Rejected", { exact: true })).toBeVisible();
    await expect(card).toHaveCount(1);
    expect((await card.boundingBox()).y).toBeLessThan(
      (await page.getByText("after broker result", { exact: true }).boundingBox()).y,
    );
  } finally {
    await context.request.delete(`/api/agents/${agent.id}`, { headers });
  }
});
