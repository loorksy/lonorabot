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
