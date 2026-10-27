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
  const create = async () => {
    const response = await context.request.post("/api/agents", {
      headers,
      data: {
        name: `Native runtime ${randomUUID()}`,
        trading_account_id: data.account,
        trading_symbol: data.symbol,
      },
    });
    expect(response.status()).toBe(201);
    const agent = await response.json();
    const thread = await (
      await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
    ).json();
    return { agent, thread };
  };
  const first = await create();
  return {
    ...first,
    create,
    remove: (id = first.agent.id) => context.request.delete(`/api/agents/${id}`, { headers }),
  };
}
function run(data, status = "queued") {
  const now = new Date().toISOString();
  return {
    id: randomUUID(),
    thread_id: data.thread.id,
    agent_id: data.agent.id,
    parent_run_id: null,
    status,
    trigger: "user",
    input_seq: 1,
    model_metadata: {},
    result: null,
    error_code: null,
    created_at: now,
    updated_at: now,
  };
}
function outgoing(data, body, seq = 1) {
  return {
    id: randomUUID(),
    thread_id: data.thread.id,
    agent_id: null,
    role: "user",
    seq,
    content: body.content,
    attachment_ids: body.attachment_ids ?? [],
    reply_to: body.reply_to ?? null,
    client_nonce: body.client_nonce,
    created_at: new Date().toISOString(),
  };
}
const rich = {
  version: 1,
  parts: [
    {
      type: "ui",
      document: {
        version: 1,
        mode: "example",
        state: { amount: 1000 },
        root: {
          id: "live-calculator",
          type: "column",
          children: [
            {
              id: "amount",
              type: "input",
              label: "Example amount",
              state_key: "amount",
              input_kind: "number",
              minimum: 100,
              maximum: 10000,
              step: 1,
            },
            {
              id: "result",
              type: "metric",
              label: "Twice",
              value: { op: "mul", args: [{ state: "amount" }, 2] },
            },
          ],
        },
      },
    },
  ],
};

test("native bridge locally enqueues and clears before delayed ACK, then shows actual stream phases and rich UI", async ({
  page,
  context,
}) => {
  test.setTimeout(60000);
  const data = await fixture(context),
    responseRun = run(data);
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  let release,
    blocked = false,
    socket,
    cursor = 10,
    body,
    canonical;
  const waiting = new Promise((resolve) => {
    release = resolve;
  });
  let serverRuns = [],
    serverMessages = [];
  await page.route(`**/api/runs?thread_id=${data.thread.id}`, async (route) => {
    if (blocked) await waiting;
    await route.fulfill({ json: serverRuns });
  });
  await page.route(`**/api/threads/${data.thread.id}/messages`, async (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: serverMessages });
    body = route.request().postDataJSON();
    await waiting;
    canonical = outgoing(data, body);
    serverMessages = [canonical];
    serverRuns = [responseRun];
    return route.fulfill({
      status: 202,
      json: { message: canonical, run_ids: [responseRun.id], runs: [responseRun] },
    });
  });
  await page.routeWebSocket("**/api/ws/events", (ws) => {
    socket = ws;
    ws.onMessage((raw) => {
      const auth = JSON.parse(raw);
      expect(auth).toMatchObject({ cursor: 0, live: true });
      ws.send(JSON.stringify({ type: "ready", cursor }));
    });
  });
  const event = (kind, payload = {}) =>
    socket.send(
      JSON.stringify({
        cursor: ++cursor,
        kind,
        thread_id: data.thread.id,
        agent_id: data.agent.id,
        run_id: responseRun.id,
        payload,
        created_at: new Date().toISOString(),
      }),
    );
  try {
    await page.goto(`/thread?id=${data.thread.id}`);
    const composer = page.getByRole("textbox", { name: "Message…", exact: true });
    await expect(composer).toBeVisible();
    await expect(page.getByTestId("conversation-transcript")).toBeVisible();
    await composer.fill("Hello native local outbox");
    blocked = true;
    const started = Date.now();
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(page.getByText("Hello native local outbox", { exact: true })).toBeVisible();
    await expect(composer).toHaveValue("");
    const localMs = Date.now() - started;
    expect(localMs).toBeLessThan(1500);
    await composer.fill("Keep this newer unsent draft");
    await page.waitForTimeout(1500);
    await expect(composer).toHaveValue("Keep this newer unsent draft");
    expect(serverRuns).toHaveLength(0);
    release();
    const activity = page.getByTestId(`turn-activity-${responseRun.id}`);
    await expect(activity).toContainText("Queued");
    await expect(page.getByText("Hello native local outbox", { exact: true })).toHaveCount(1);
    await expect(composer).toHaveValue("Keep this newer unsent draft");
    responseRun.status = "running";
    event("run.running");
    const identity = { turn_id: "actual-turn", fence: 1, generation: 1, input_seq: 1 };
    event("run.reply_started", { ...identity, sequence: 0 });
    await expect(activity).toContainText("Thinking");
    event("tool.started", { call_id: "call-one", name: "web_search" });
    await expect(activity).toContainText("Searching");
    await activity.getByRole("button").click();
    await expect(activity).toContainText("web_search");
    event("tool.completed", { call_id: "call-one", name: "web_search", ok: true });
    event("run.delta", { ...identity, sequence: 1, text: "This arrives before completion. " });
    await expect(page.getByText("This arrives before completion.", { exact: true })).toBeVisible();
    await expect(activity).toContainText("Writing a response");
    event("run.rich_partial", { ...identity, sequence: 2, rich_content: rich });
    const visual = page.getByTestId("native-visual-live-calculator");
    await expect(visual).toBeVisible();
    const amount = visual.getByRole("textbox", { name: "Example amount", exact: true });
    await amount.fill("250");
    await expect(amount).toHaveValue("250");
    await expect(visual.getByText("500", { exact: true })).toBeVisible();
    // Final canonical message follows the accepted stream; edited local input survives that ID change.
    const answer = {
      ...outgoing(data, { content: "Canonical fallback" }, 2),
      agent_id: data.agent.id,
      role: "assistant",
      rich_content: rich,
      client_nonce: undefined,
    };
    responseRun.stream = {
      ...identity,
      sequence: 2,
      text: "This arrives before completion. ",
      truncated: false,
      phase: "committed",
      message_id: answer.id,
      rich_content: rich,
    };
    serverMessages = [canonical, answer];
    event("run.reply_committed", { ...responseRun.stream });
    event("message.created", answer);
    responseRun.status = "completed";
    event("run.completed");
    await expect(visual).toHaveCount(1);
    await expect(visual.getByText("500", { exact: true })).toBeVisible();
    await expect(page.getByText("Canonical fallback", { exact: true })).toHaveCount(0);
    await expect(composer).toHaveValue("Keep this newer unsent draft");
    expect(errors).toEqual([]);
    console.log(
      JSON.stringify({
        native_bridge_local_ms: localMs,
        progressive_text: true,
        validated_rich: true,
        final_local_state_preserved: true,
      }),
    );
  } finally {
    release();
    await data.remove();
  }
});

test("native failed outgoing message retries same nonce after reload and navigation retains unsent drafts", async ({
  page,
  context,
}) => {
  test.setTimeout(60000);
  const data = await fixture(context),
    other = await data.create();
  const posted = [],
    saved = [];
  let fail = true;
  await page.route(`**/api/threads/${data.thread.id}/messages`, async (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: saved });
    const body = route.request().postDataJSON();
    posted.push(body);
    if (fail) return route.fulfill({ status: 503, json: { code: "request_failed" } });
    const message = outgoing(data, body);
    saved.push(message);
    return route.fulfill({ status: 202, json: { message, run_ids: [], runs: [] } });
  });
  try {
    await page.goto(`/thread?id=${data.thread.id}`);
    const composer = page.getByRole("textbox", { name: "Message…", exact: true });
    await expect(page.getByTestId("conversation-transcript")).toBeVisible();
    await composer.fill("Recover me once");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(page.getByText("Message not sent", { exact: true })).toBeVisible();
    await expect(composer).toHaveValue("");
    await page.reload();
    await expect(page.getByText("Recover me once", { exact: true })).toHaveCount(1);
    fail = false;
    await page.getByRole("button", { name: "Retry", exact: true }).click();
    await expect(page.getByText("Message not sent", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Recover me once", { exact: true })).toHaveCount(1);
    expect(posted).toHaveLength(2);
    expect(posted[1].client_nonce).toBe(posted[0].client_nonce);
    await composer.fill("Retained draft on native A");
    await page.getByRole("button", { name: "Back", exact: true }).click();
    await page.getByText(other.agent.name, { exact: true }).click();
    await composer.fill("Independent native B");
    await page.getByRole("button", { name: "Back", exact: true }).click();
    await page.getByText(data.agent.name, { exact: true }).click();
    await expect(composer).toHaveValue("Retained draft on native A");
  } finally {
    await data.remove();
    await data.remove(other.agent.id);
  }
});
