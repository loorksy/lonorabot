// An honest live connection (B3): a socket that goes silent after its ready frame shows the
// working turn as «Reconnecting» within 45 s, and the new socket resumes from the last event.
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "../ui-test.mjs";

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
  const response = await context.request.post("/api/agents", {
    headers,
    data: {
      name: `Live connection ${randomUUID()}`,
      trading_account_id: data.account,
      trading_symbol: data.symbol,
    },
  });
  expect(response.status()).toBe(201);
  const agent = await response.json();
  const thread = await (
    await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
  ).json();
  return {
    agent,
    thread,
    remove: () => context.request.delete(`/api/agents/${agent.id}`, { headers }),
  };
}

test("a socket silent after ready shows Reconnecting within 45 s and resumes from its cursor", async ({
  page,
  context,
  cleanup,
}) => {
  test.setTimeout(60_000);
  const data = await fixture(context);
  cleanup(() => data.remove());
  const now = new Date().toISOString();
  const run = {
    id: randomUUID(),
    thread_id: data.thread.id,
    agent_id: data.agent.id,
    parent_run_id: null,
    status: "running",
    trigger: "user",
    input_seq: 1,
    model_metadata: {},
    result: null,
    error_code: null,
    created_at: now,
    updated_at: now,
  };
  await page.route(`**/api/runs?thread_id=${data.thread.id}`, (route) =>
    route.fulfill({ json: [run] }),
  );
  // The owner's message the run answers: the turn's activity line is drawn under it.
  const asked = {
    id: randomUUID(),
    thread_id: data.thread.id,
    agent_id: null,
    role: "user",
    seq: 1,
    content: "Watch gold for me",
    attachment_ids: [],
    reply_to: null,
    client_nonce: randomUUID(),
    created_at: now,
  };
  await page.route(`**/api/threads/${data.thread.id}/messages`, (route) =>
    route.fulfill({ json: [asked] }),
  );
  // A scripted server: a socket's first frame gets ready, a resume also gets the events after its
  // cursor, and nothing else is ever sent. Without a ping, a socket is silent between events.
  const log = [],
    sockets = new Set(),
    resumes = [];
  let head = 10;
  await page.routeWebSocket("**/api/ws/events", (socket) => {
    socket.onMessage((raw) => {
      const hello = JSON.parse(raw);
      if (!hello.live) resumes.push(hello);
      socket.send(JSON.stringify({ type: "ready", cursor: hello.live ? head : hello.cursor }));
      for (const event of log)
        if (!hello.live && event.cursor > hello.cursor) socket.send(JSON.stringify(event));
      sockets.add(socket);
    });
    socket.onClose(() => sockets.delete(socket));
  });
  const push = (kind, payload) => {
    const event = {
      cursor: ++head,
      kind,
      thread_id: data.thread.id,
      agent_id: data.agent.id,
      run_id: run.id,
      payload,
      created_at: new Date().toISOString(),
    };
    log.push(event);
    for (const socket of sockets) socket.send(JSON.stringify(event));
  };
  const turn = { turn_id: "silent-turn", fence: 1, generation: 1, input_seq: 1 };
  // The page's timers follow a clock the test moves: 45 s pass for the page at once.
  await page.clock.install();
  await page.goto(`/thread?id=${data.thread.id}`);
  const activity = page.getByTestId(`turn-activity-${run.id}`);
  await expect(activity).toBeVisible();
  await expect.poll(() => sockets.size).toBeGreaterThan(0);
  push("run.reply_started", { ...turn, sequence: 0 });
  push("run.delta", { ...turn, sequence: 1, text: "Before the silence. " });
  await expect(page.getByText("Before the silence.", { exact: true })).toBeVisible();
  await expect(activity).toContainText("Writing a response");
  // Stop the clock so the label can be read before the 1.5 s reconnect delay ends.
  await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 1000);
  await page.clock.fastForward(45_000);
  await expect(activity).toContainText("Reconnecting");
  expect(resumes).toHaveLength(0);
  await page.clock.runFor(1500);
  await expect.poll(() => resumes.length).toBeGreaterThan(0);
  await page.clock.resume();
  await expect(activity).toContainText("Writing a response");
  // Every new socket asks for the events after the last one it consumed, not a live start.
  for (const hello of resumes) expect(hello).toEqual({ cursor: head });
  push("run.delta", { ...turn, sequence: 2, text: "After the resume." });
  await expect(
    page.getByText("Before the silence. After the resume.", { exact: true }),
  ).toHaveCount(1);
});
