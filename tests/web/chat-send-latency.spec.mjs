import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

function deferred() {
  let resolve;
  const promise = new Promise((complete) => {
    resolve = complete;
  });
  return { promise, resolve };
}

async function conversation(context) {
  const fixture = JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify({ action: "init", empty: true }),
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
    "X-CSRF-Token": fixture.cookies.find((cookie) => cookie.name === "lonora_csrf").value,
  };
  const created = await context.request.post("/api/agents", {
    headers,
    data: {
      name: `Immediate chat ${randomUUID()}`,
      trading_account_id: fixture.account,
      trading_symbol: fixture.symbol,
    },
  });
  expect(created.ok()).toBeTruthy();
  const agent = await created.json();
  const thread = await (
    await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
  ).json();
  return { agent, thread, headers };
}

test("message appears before delayed POST and slow runs, survives navigation, then reconciles once", async ({
  page,
  context,
}) => {
  const { agent, thread, headers } = await conversation(context);
  const post = deferred();
  const runs = deferred();
  const committed = deferred();
  let saved;
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "ar"));
  await page.route(`**/api/runs?thread_id=${thread.id}`, async (route) => {
    await runs.promise;
    await route.fulfill({ json: [] });
  });
  await page.route(`**/api/threads/${thread.id}/messages`, async (route) => {
    if (route.request().method() !== "POST") return route.fulfill({ json: [] });
    await post.promise;
    const response = await route.fetch();
    saved = await response.json();
    await route.fulfill({ response });
    committed.resolve();
  });
  try {
    await page.goto("/app");
    await page.locator(`[data-inbox-agent-id="${agent.id}"]`).click();
    const content = "صباح الخير — تظهر الرسالة فورًا";
    await page.getByRole("combobox", { name: "الرسالة", exact: true }).fill(content);
    await page.getByRole("button", { name: "إرسال", exact: true }).click();
    const pending = page.locator("article[data-delivery='sending']");
    await expect(pending).toContainText(content, { timeout: 1000 });
    await expect(pending).toHaveCount(1);
    await expect(page.getByRole("combobox", { name: "الرسالة", exact: true })).toHaveValue("");
    await expect(pending.locator("time")).toHaveCount(0);
    await expect(pending.getByRole("status")).toHaveText("جارٍ الإرسال…");
    await expect(page.locator("[data-stream-run-id]")).toHaveCount(0);

    await page.goBack();
    await expect(page.getByTestId("conversation-inbox")).toBeVisible();
    await page.locator(`[data-inbox-agent-id="${agent.id}"]`).click();
    await expect(pending).toContainText(content, { timeout: 1000 });
    post.resolve();
    await committed.promise;
    await expect(page.locator(`[data-message-id="${saved.message.id}"]`)).toContainText(content);
    await expect(page.locator("article[data-delivery]")).toHaveCount(0);
    await expect(page.getByTestId("transcript").getByText(content, { exact: true })).toHaveCount(1);
    // The independent Run request is deliberately still unresolved here.
    expect(saved.run_ids).toHaveLength(1);
    await expect(page.locator(`[data-progress-run-id="${saved.run_ids[0]}"]`)).toHaveCount(1);
    await expect(page.locator(`[data-activity-phase="queued"]`)).toHaveCount(1);
  } finally {
    post.resolve();
    runs.resolve();
    await context.request.delete(`/api/agents/${agent.id}`, { headers });
  }
});

test("failed pending bubble retries the same receipt while preserving a newer draft", async ({
  page,
  context,
}) => {
  const { agent, thread, headers } = await conversation(context);
  const nonces = [];
  let fail = true;
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  await page.route(`**/api/threads/${thread.id}/messages`, async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    nonces.push(route.request().postDataJSON().client_nonce);
    if (fail) {
      fail = false;
      return route.fulfill({ status: 503, json: { code: "request_failed" } });
    }
    return route.continue();
  });
  try {
    await page.goto(`/app/${agent.id}`);
    const composer = page.getByRole("combobox", { name: "Message", exact: true });
    const content = "Retry this exact message";
    await composer.fill(content);
    await page.getByRole("button", { name: "Send", exact: true }).click();
    const failed = page.locator("article[data-delivery='failed']");
    await expect(failed).toContainText(content);
    await composer.fill("Keep my newer unsent draft");
    await failed.getByRole("button", { name: "Retry", exact: true }).click();
    await expect(page.locator("article[data-delivery]")).toHaveCount(0);
    await expect(page.getByTestId("transcript").getByText(content, { exact: true })).toHaveCount(1);
    await expect(composer).toHaveValue("Keep my newer unsent draft");
    expect(nonces).toHaveLength(2);
    expect(nonces[0]).toBe(nonces[1]);
    const history = await (await context.request.get(`/api/threads/${thread.id}/messages`)).json();
    expect(history.filter((message) => message.content === content)).toHaveLength(1);
  } finally {
    await context.request.delete(`/api/agents/${agent.id}`, { headers });
  }
});

test("SSE acknowledgement replaces pending text before its HTTP response returns", async ({
  page,
  context,
}) => {
  const { agent, thread, headers } = await conversation(context);
  const responseGate = deferred();
  const committed = deferred();
  let saved;
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  await page.route(`**/api/threads/${thread.id}/messages`, async (route) => {
    if (route.request().method() !== "POST") return route.fulfill({ json: [] });
    const response = await route.fetch();
    saved = await response.json();
    committed.resolve();
    await responseGate.promise;
    await route.fulfill({ response });
  });
  try {
    await page.goto(`/app/${agent.id}`);
    const content = "Confirmed by the live event";
    await page.getByRole("combobox", { name: "Message", exact: true }).fill(content);
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await committed.promise;
    await expect(page.locator(`[data-message-id="${saved.message.id}"]`)).toContainText(content);
    await expect(page.locator("article[data-delivery]")).toHaveCount(0);
    responseGate.resolve();
    await expect(page.getByRole("combobox", { name: "Message", exact: true })).toHaveValue("");
    await expect(page.getByTestId("transcript").getByText(content, { exact: true })).toHaveCount(1);
  } finally {
    responseGate.resolve();
    await context.request.delete(`/api/agents/${agent.id}`, { headers });
  }
});

test("drafts stay with their conversation across switches and reload", async ({
  page,
  context,
}) => {
  const a = await conversation(context),
    b = await conversation(context);
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  try {
    await page.goto(`/app/${a.agent.id}`);
    const field = page.getByRole("combobox", { name: "Message", exact: true });
    await field.fill("Unsent draft A");
    await page
      .locator(".tpl-sidebar")
      .getByRole("button", { name: b.agent.name, exact: true })
      .click();
    await expect(field).toHaveValue("");
    await field.fill("Unsent draft B");
    await page
      .locator(".tpl-sidebar")
      .getByRole("button", { name: a.agent.name, exact: true })
      .click();
    await expect(field).toHaveValue("Unsent draft A");
    await page.reload();
    await expect(field).toHaveValue("Unsent draft A");
    await page
      .locator(".tpl-sidebar")
      .getByRole("button", { name: b.agent.name, exact: true })
      .click();
    await expect(field).toHaveValue("Unsent draft B");
  } finally {
    await context.request.delete(`/api/agents/${a.agent.id}`, { headers: a.headers });
    await context.request.delete(`/api/agents/${b.agent.id}`, { headers: b.headers });
  }
});

test("failed outbox survives reload without auto-resubmitting and retries the original nonce", async ({
  page,
  context,
}) => {
  const { agent, thread, headers } = await conversation(context);
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const nonces = [];
  let fail = true;
  await page.route(`**/api/threads/${thread.id}/messages`, (route) => {
    if (route.request().method() !== "POST") return route.continue();
    nonces.push(route.request().postDataJSON().client_nonce);
    return fail
      ? route.fulfill({ status: 503, json: { code: "request_failed" } })
      : route.continue();
  });
  try {
    await page.goto(`/app/${agent.id}`);
    const field = page.getByRole("combobox", { name: "Message", exact: true });
    await field.fill("Recover this receipt");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(field).toHaveValue("");
    await expect(page.locator('[data-delivery="failed"]')).toContainText("Recover this receipt");
    await field.fill("A newer draft is separate");
    await page.reload();
    await expect(field).toHaveValue("A newer draft is separate");
    await expect(page.locator('[data-delivery="failed"]')).toHaveCount(1);
    expect(nonces).toHaveLength(1);
    fail = false;
    await page.getByRole("button", { name: "Retry", exact: true }).click();
    await expect(page.locator("article[data-delivery]")).toHaveCount(0);
    await expect(
      page.getByTestId("transcript").getByText("Recover this receipt", { exact: true }),
    ).toHaveCount(1);
    await expect(field).toHaveValue("A newer draft is separate");
    expect(nonces).toEqual([nonces[0], nonces[0]]);
  } finally {
    await context.request.delete(`/api/agents/${agent.id}`, { headers });
  }
});

test("concurrent optimistic messages keep submission order as earlier acknowledgements arrive", async ({
  page,
  context,
}) => {
  const { agent, thread, headers } = await conversation(context);
  const first = deferred(),
    second = deferred();
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  await page.route(`**/api/threads/${thread.id}/messages`, async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const content = route.request().postDataJSON().content;
    await (content === "First queued message" ? first.promise : second.promise);
    return route.continue();
  });
  try {
    await page.goto(`/app/${agent.id}`);
    const field = page.getByRole("combobox", { name: "Message", exact: true });
    await field.fill("First queued message");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(field).toHaveValue("");
    await field.fill("Second queued message");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(page.locator("article[data-delivery]")).toHaveCount(2);
    first.resolve();
    await expect(page.locator("article[data-delivery]")).toHaveCount(1);
    const order = await page
      .locator(".template-message.user .template-user-text")
      .allTextContents();
    expect(order).toEqual(["First queued message", "Second queued message"]);
    second.resolve();
    await expect(page.locator("article[data-delivery]")).toHaveCount(0);
    expect(
      await page.locator(".template-message.user .template-user-text").allTextContents(),
    ).toEqual(order);
  } finally {
    first.resolve();
    second.resolve();
    await context.request.delete(`/api/agents/${agent.id}`, { headers });
  }
});

test("local enqueue failure preserves the submitted draft", async ({ page, context }) => {
  const { agent, thread, headers } = await conversation(context);
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  let posts = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().includes(`/threads/${thread.id}/messages`))
      posts += 1;
  });
  try {
    await page.goto(`/app/${agent.id}`);
    const field = page.getByRole("combobox", { name: "Message", exact: true });
    await field.fill("Keep this draft if local acceptance fails");
    await page.evaluate(() => {
      window.__uuid = crypto.randomUUID.bind(crypto);
      crypto.randomUUID = () => {
        throw Error("Controlled local queue failure");
      };
    });
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(field).toHaveValue("Keep this draft if local acceptance fails");
    await expect(page.locator("article[data-delivery]")).toHaveCount(0);
    expect(posts).toBe(0);
    await page.evaluate(() => {
      crypto.randomUUID = window.__uuid;
    });
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(field).toHaveValue("");
    await expect(
      page
        .getByTestId("transcript")
        .getByText("Keep this draft if local acceptance fails", { exact: true }),
    ).toHaveCount(1);
  } finally {
    await context.request.delete(`/api/agents/${agent.id}`, { headers });
  }
});

test("validated interactive preview appears before completion and preserves edits when the canonical run link arrives late", async ({
  page,
  context,
}) => {
  const { agent, thread, headers } = await conversation(context);
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const now = "2026-10-27T10:00:00Z";
  const input = {
    id: randomUUID(),
    thread_id: thread.id,
    agent_id: agent.id,
    seq: 1,
    role: "user",
    content: "An illustrative calculator",
    created_at: now,
    reply_to: null,
    attachment_ids: [],
  };
  const rich = {
    version: 1,
    parts: [
      { type: "text", text: "Illustrative local calculation." },
      {
        type: "ui",
        document: {
          version: 1,
          mode: "example",
          state: { quantity: 2 },
          root: {
            id: "layout",
            type: "column",
            children: [
              {
                id: "quantity",
                type: "input",
                input_kind: "number",
                state_key: "quantity",
                label: "Quantity",
                step: 1,
              },
              {
                id: "total",
                type: "metric",
                label: "Illustrative total",
                value: { op: "mul", args: [{ state: "quantity" }, 10] },
              },
            ],
          },
        },
      },
    ],
  };
  const run = {
    id: randomUUID(),
    thread_id: thread.id,
    agent_id: agent.id,
    parent_run_id: null,
    status: "running",
    input_seq: 1,
    trigger: "user",
    error_code: null,
    result: null,
    model_metadata: {},
    created_at: now,
    updated_at: now,
    stream: {
      input_seq: 1,
      turn_id: "illustration-turn",
      fence: 1,
      generation: 1,
      sequence: 1,
      text: "Illustrative local calculation.",
      truncated: false,
      phase: "streaming",
      message_id: null,
      rich_content: rich,
    },
  };
  let rows = [input];
  await page.route(`**/api/threads/${thread.id}/messages*`, (route) =>
    route.request().method() === "GET" ? route.fulfill({ json: rows }) : route.continue(),
  );
  await page.route(`**/api/runs?thread_id=${thread.id}`, (route) => route.fulfill({ json: [run] }));
  let mutations = 0;
  page.on("request", (request) => {
    if (request.method() !== "GET" && request.url().includes("/api/")) mutations += 1;
  });
  try {
    await page.goto(`/app/${agent.id}`);
    const preview = page.locator(`[data-stream-run-id="${run.id}"]`);
    await expect(preview.locator(".native-visual-response")).toBeVisible();
    await expect(preview.locator('[data-activity-phase="writing"]')).toHaveCount(1);
    await preview.getByRole("spinbutton", { name: "Quantity", exact: true }).fill("4");
    await expect(preview.locator('[data-visual-value="total"]')).toHaveText("40");
    const final = {
      ...input,
      id: randomUUID(),
      seq: 2,
      role: "assistant",
      content: run.stream.text,
      rich_content: rich,
    };
    rows = [input, final];
    // Deliberately expose canonical history before its independent run projection.
    await page.evaluate(() => window.dispatchEvent(new Event("online")));
    const canonical = page.locator(`[data-message-id="${final.id}"]`);
    await expect(canonical).toBeVisible();
    run.status = "completed";
    run.updated_at = "2026-10-27T10:00:01Z";
    run.stream = { ...run.stream, phase: "committed", message_id: final.id };
    await page.evaluate(() => window.dispatchEvent(new Event("online")));
    await expect(preview).toHaveCount(0);
    await expect(canonical.getByRole("spinbutton", { name: "Quantity", exact: true })).toHaveValue(
      "4",
    );
    await expect(canonical.locator('[data-visual-value="total"]')).toHaveText("40");
    await page.reload();
    await expect(canonical.getByRole("spinbutton", { name: "Quantity", exact: true })).toHaveValue(
      "4",
    );
    expect(mutations).toBe(0);
  } finally {
    await context.request.delete(`/api/agents/${agent.id}`, { headers });
  }
});
