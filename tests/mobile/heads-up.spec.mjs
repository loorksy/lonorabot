// The heads-up on mobile, as on Web: an agent's answer in another chat slides in at the top
// with «Reply»; a tap opens that chat; a muted chat stays silent.
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
  const create = async (name) => {
    const agent = await (
      await context.request.post("/api/agents", {
        headers,
        data: { name, trading_account_id: data.account, trading_symbol: data.symbol },
      })
    ).json();
    const thread = await (
      await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
    ).json();
    // A message makes the chat a row of the inbox.
    await context.request.post(`/api/threads/${thread.id}/messages`, {
      headers,
      data: { content: "hello", client_nonce: randomUUID() },
    });
    return { agent, thread };
  };
  return {
    headers,
    create,
    remove: (id) => context.request.delete(`/api/agents/${id}`, { headers }),
  };
}

/** The owner's live stream, scripted: `push(event)` delivers one more event to every socket. */
async function scriptedStream(page) {
  const sockets = new Set();
  let cursor = 1000;
  await page.routeWebSocket("**/api/ws/events", (socket) => {
    socket.onMessage(() => {
      sockets.add(socket);
      socket.send(JSON.stringify({ type: "ready", cursor }));
    });
    socket.onClose(() => sockets.delete(socket));
  });
  return {
    ready: () => sockets.size,
    push: (thread, agent, content) => {
      cursor += 1;
      const now = new Date().toISOString();
      for (const socket of sockets)
        socket.send(
          JSON.stringify({
            cursor,
            kind: "message.created",
            thread_id: thread,
            agent_id: agent,
            run_id: null,
            created_at: now,
            payload: {
              id: randomUUID(),
              thread_id: thread,
              agent_id: agent,
              role: "assistant",
              seq: 50,
              content,
              attachment_ids: [],
              reply_to: null,
              created_at: now,
            },
          }),
        );
    },
  };
}

test("an answer in another chat shows at the top; Reply opens it; a muted chat stays silent", async ({
  page,
  context,
}) => {
  test.setTimeout(60000);
  const data = await fixture(context);
  const gold = await data.create(`Gold ${randomUUID().slice(0, 6)}`),
    euro = await data.create(`Euro ${randomUUID().slice(0, 6)}`);
  await context.request.post("/api/threads/prefs", {
    headers: data.headers,
    data: { thread_ids: [euro.thread.id], muted: true },
  });
  const stream = await scriptedStream(page);
  try {
    await page.goto("/");
    await expect(page.getByText(gold.agent.name, { exact: true })).toBeVisible();
    await expect.poll(stream.ready).toBeGreaterThan(0);
    // A muted chat stays silent.
    stream.push(euro.thread.id, euro.agent.id, "EURUSD at 1.0850, no trade.");
    const banner = page.getByTestId("heads-up");
    await page.waitForTimeout(1200);
    await expect(banner).toHaveCount(0);
    stream.push(gold.thread.id, gold.agent.id, "Gold broke 2,425; I added 0.05.");
    await expect(banner).toContainText("Gold broke 2,425; I added 0.05.");
    await expect(banner).toContainText(gold.agent.name);
    await banner.getByRole("button", { name: "Reply", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`id=${gold.thread.id}`));
    await expect(banner).toHaveCount(0);
    // In the open chat its own answers do not show at the top.
    await page.waitForTimeout(1500);
    stream.push(gold.thread.id, gold.agent.id, "Stop moved to break-even.");
    await page.waitForTimeout(800);
    await expect(page.getByTestId("heads-up")).toHaveCount(0);
  } finally {
    await data.remove(gold.agent.id);
    await data.remove(euro.agent.id);
  }
});
