// Order lines on mobile, as on Web (Q30): one line per operation of the chat at its anchor,
// with its durable state; «Filled» only with evidence; the sheet shows the timeline and the
// evidence, never the raw operation or account id.
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

async function fixture(context) {
  const data = JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify({ action: "init", empty: true }),
      encoding: "utf8",
    }),
  );
  await context.addCookies(
    data.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const headers = { "X-CSRF-Token": data.cookies.find((row) => row.name === "lonora_csrf").value };
  const agent = await (
    await context.request.post("/api/agents", {
      headers,
      data: {
        name: `Orders ${randomUUID()}`,
        trading_account_id: data.account,
        trading_symbol: data.symbol,
      },
    })
  ).json();
  const thread = await (
    await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
  ).json();
  return {
    agent,
    thread,
    remove: () => context.request.delete(`/api/agents/${agent.id}`, { headers }),
  };
}

test("each operation of the chat is a line at its anchor; the sheet shows the evidence", async ({
  page,
  context,
}) => {
  const data = await fixture(context);
  const now = new Date().toISOString();
  const message = (seq, content) => ({
    id: randomUUID(),
    thread_id: data.thread.id,
    agent_id: seq === 1 ? null : data.agent.id,
    role: seq === 1 ? "user" : "assistant",
    seq,
    content,
    attachment_ids: [],
    reply_to: null,
    reactions: [],
    created_at: now,
  });
  const filledId = randomUUID(),
    uncertainId = randomUUID();
  const journal = [
    {
      operation_id: filledId,
      account_id: "account-raw-id",
      status: "confirmed",
      request: { action: "buy", symbol: "XAUUSD", volume: 0.1 },
      result: {
        status: "confirmed",
        broker_id: "771234",
        details: { price: 2400.5, volume: 0.1, verification: { status: "verified" } },
      },
      submitted_at: now,
      updated_at: now,
      thread_id: data.thread.id,
      timeline_seq: 1,
    },
    {
      operation_id: uncertainId,
      account_id: "account-raw-id",
      status: "ambiguous",
      request: { action: "close_position", symbol: "XAUUSD", volume: 0.05, position: "771234" },
      result: {},
      submitted_at: now,
      updated_at: now,
      thread_id: data.thread.id,
      timeline_seq: 2,
    },
    {
      operation_id: randomUUID(),
      account_id: "account-raw-id",
      status: "filled",
      request: { action: "sell", symbol: "EURUSD", volume: 1 },
      result: {},
      submitted_at: now,
      updated_at: now,
      thread_id: "another-thread",
      timeline_seq: 1,
    },
  ];
  await page.route(`**/api/threads/${data.thread.id}/messages*`, (route) =>
    route.fulfill({
      json: [message(1, "Buy gold"), message(2, "Bought."), message(3, "Closing half.")],
    }),
  );
  await page.route("**/api/trading/journal?thread_id=*", (route) =>
    route.fulfill({ json: journal }),
  );
  try {
    await page.goto(`/thread?id=${data.thread.id}`);
    const lines = page.getByTestId("order-line");
    await expect(lines).toHaveCount(2);
    await expect(page.getByText("EURUSD")).toHaveCount(0);
    const filled = page.getByRole("button", { name: /^Order Buy 0\.1 XAUUSD: Filled/ });
    await expect(filled).toBeVisible();
    const uncertain = page.getByRole("button", { name: /XAUUSD: Unconfirmed/ });
    await expect(uncertain).toBeVisible();

    await filled.click();
    await expect(page.getByText("Trade order", { exact: true })).toBeVisible();
    await expect(page.getByTestId("order-evidence")).toContainText(
      "Fill evidence: ticket 771234 · 2400.5",
    );
    await expect(page.getByTestId("order-sheet")).not.toContainText(filledId);
    await expect(page.getByTestId("order-sheet")).not.toContainText("account-raw-id");
    await page.reload();

    await uncertain.click();
    await expect(page.getByTestId("order-evidence")).toContainText(
      "«Filled» is never shown before the evidence",
    );
    await expect(page.getByTestId("order-sheet")).toContainText("No answer from the broker");
  } finally {
    await data.remove();
  }
});
