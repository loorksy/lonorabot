// A jump to a message marks it for a moment; a call log calls the agent back; without a voice
// provider the call says that calls are not set up (as Web).
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
        name: `Calls ${randomUUID()}`,
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

test("a jump marks its message; a call log calls back; no voice provider says so", async ({
  page,
  context,
}) => {
  const data = await fixture(context);
  const now = new Date().toISOString();
  const rows = Array.from({ length: 30 }, (_, index) => ({
    id: randomUUID(),
    thread_id: data.thread.id,
    agent_id: data.agent.id,
    role: "assistant",
    seq: index + 1,
    content: `Line ${index + 1}`,
    attachment_ids: [],
    reply_to: null,
    reactions: [],
    created_at: now,
  }));
  rows.push({
    id: randomUUID(),
    thread_id: data.thread.id,
    agent_id: data.agent.id,
    role: "system",
    seq: 31,
    content: "",
    attachment_ids: [],
    reply_to: null,
    reactions: [],
    created_at: now,
    rich_content: {
      version: 1,
      parts: [{ type: "call", direction: "outgoing", duration_seconds: 75, missed: false }],
    },
  });
  rows.push(
    {
      ...rows[30],
      id: randomUUID(),
      seq: 32,
      rich_content: {
        version: 1,
        parts: [{ type: "call", direction: "incoming", duration_seconds: 0, missed: true }],
      },
    },
    { ...rows[0], id: randomUUID(), seq: 33, content: "About line 3", reply_to: rows[2].id },
  );
  await page.route(`**/api/threads/${data.thread.id}/messages*`, (route) =>
    route.fulfill({ json: rows }),
  );
  await page.route("**/api/voice/status", (route) =>
    route.fulfill({ json: { transport_configured: false } }),
  );
  try {
    await page.goto(`/thread?id=${data.thread.id}&around=3`);
    const flashed = page.getByTestId("message-flash");
    await expect(flashed).toContainText("Line 3");
    await expect(flashed).toHaveCount(0, { timeout: 4000 });

    // A tap on a quote marks its message, again on every tap; the mark never resizes it.
    await page.goto(`/thread?id=${data.thread.id}`);
    const quote = page.getByRole("button", { name: "Reply: Line 3", exact: true });
    await quote.click();
    await expect(flashed).toContainText("Line 3");
    const marked = await page.getByText("Line 3", { exact: true }).last().boundingBox();
    await expect(flashed).toHaveCount(0, { timeout: 4000 });
    const plain = await page.getByText("Line 3", { exact: true }).last().boundingBox();
    expect(Math.abs(marked.x - plain.x) + Math.abs(marked.y - plain.y)).toBeLessThan(1);
    expect(marked.width).toBe(plain.width);
    await quote.click();
    await expect(flashed).toContainText("Line 3");

    // A missed call says it can be called back, as Web.
    await expect(page.getByText("Tap to call back", { exact: true })).toBeVisible();
    await page.getByTestId("call-back").first().click();
    await expect(page.getByText(/Calls are not set up/)).toBeVisible();
  } finally {
    await data.remove();
  }
});
