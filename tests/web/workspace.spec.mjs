// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: Playwright runs directly without Turborepo caching.

import { randomUUID } from "node:crypto";
import { test as base, expect } from "@playwright/test";

const test = base.extend({
  workspace: async ({ context, page }, use) => {
    const prefix = `UI regression ${randomUUID()}`;
    const owned = { agents: new Set(), boards: new Set(), tickets: new Set() };
    const status = await context.request.get("/api/onboarding");
    expect(status.ok()).toBeTruthy();
    const credentials = {
      email: process.env.LONORA_UI_TEST_EMAIL ?? "ci@example.com",
      password: process.env.LONORA_UI_TEST_PASSWORD ?? "ci-only-owner-password",
    };
    if (!(await status.json()).owner_initialized) {
      const initialized = await context.request.post("/api/onboarding", {
        data: {
          ...credentials,
          bootstrap_token: process.env.LONORA_BOOTSTRAP_TOKEN ?? "lonora-ui-bootstrap-ci-only-2026",
        },
      });
      expect(initialized.status()).toBe(201);
    }
    const login = await context.request.post("/api/auth/login", { data: credentials });
    expect(login.status()).toBe(200);
    const headers = { "X-CSRF-Token": (await login.json()).csrf };
    const post = async (path, data) => {
      const response = await context.request.post(`/api${path}`, { data, headers });
      expect(response.ok(), `POST ${path}`).toBeTruthy();
      return response.json();
    };
    const remember = (kind, row) => {
      owned[kind].add(row.id);
      return row;
    };
    const agent = remember(
      "agents",
      await post("/agents", { name: prefix, avatar: "orb", color: "#818cf8" }),
    );
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await context.addInitScript(() => {
      if (!localStorage.getItem("lonora.locale")) localStorage.setItem("lonora.locale", "en");
    });
    try {
      await use({ agent, prefix, post, remember, headers });
      expect(errors).toEqual([]);
    } finally {
      // Only IDs created by this fixture or explicitly remembered by its test.
      for (const kind of ["tickets", "boards", "agents"])
        for (const id of owned[kind]) {
          const response = await context.request.delete(`/api/${kind}/${id}`, { headers });
          expect([200, 404]).toContain(response.status());
        }
    }
  },
});

test("send, cancel and reload retain one real transcript", async ({ page, context, workspace }) => {
  const { agent, prefix } = workspace;
  await page.goto(`/app/${agent.id}`);
  await expect(page.getByTestId("transcript")).toHaveCount(1);
  const message = `${prefix} persistent message`;
  await page.getByRole("combobox", { name: "Message", exact: true }).fill(message);
  const sent = page.waitForResponse(
    (response) =>
      /\/api\/threads\/[^/]+\/messages$/.test(new URL(response.url()).pathname) &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Send", exact: true }).click();
  const receipt = await (await sent).json();
  expect(receipt.run_ids).toHaveLength(1);
  await expect(page.getByTestId("transcript").getByText(message, { exact: true })).toHaveCount(1);
  const cancelled = page.waitForResponse((response) =>
    response.url().endsWith(`/api/runs/${receipt.run_ids[0]}/cancel`),
  );
  await page.getByRole("button", { name: "Stop", exact: true }).click();
  expect((await cancelled).ok()).toBeTruthy();
  await expect
    .poll(
      async () =>
        (await (await context.request.get(`/api/runs/${receipt.run_ids[0]}`)).json()).status,
    )
    .toBe("cancelled");
  await page.reload();
  await expect(page.getByTestId("transcript")).toHaveCount(1);
  await expect(page.getByTestId("transcript").getByText(message, { exact: true })).toHaveCount(1);
  const threads = await (await context.request.get(`/api/threads?agent_id=${agent.id}`)).json();
  expect(threads.filter((thread) => !thread.group_id)).toHaveLength(1);
  const messages = await (
    await context.request.get(`/api/threads/${receipt.message.thread_id}/messages`)
  ).json();
  expect(messages.filter((row) => row.content === message)).toHaveLength(1);
});

test("ticket modal and profile creation remain usable under StrictMode and Back", async ({
  page,
  workspace,
}) => {
  const { agent, prefix, post, remember } = workspace;
  const board = remember("boards", await post("/boards", { payload: { title: prefix } }));
  await page.goto("/app/board");
  await page.getByRole("button", { name: "New ticket", exact: true }).click();
  let dialog = page.getByRole("dialog", { name: "New ticket", exact: true });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel("Task", { exact: true }).fill(`${prefix} task`);
  await dialog.getByLabel("Board", { exact: true }).selectOption(board.id);
  await dialog.getByLabel("Agent", { exact: true }).selectOption(agent.id);
  const saved = page.waitForResponse(
    (response) => response.url().endsWith("/api/tickets") && response.request().method() === "POST",
  );
  await dialog.getByRole("button", { name: "Save", exact: true }).click();
  const ticket = remember("tickets", await (await saved).json());
  await page.getByTestId(`board-card-${ticket.id}`).click();
  dialog = page.getByRole("dialog", { name: "Task details", exact: true });
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await page.getByTestId(`board-card-${ticket.id}`).click();
  await page.goBack();
  await expect(dialog).toHaveCount(0);
  await expect(page).toHaveURL(/\/app\/board$/);
  await page.goto(`/app/${agent.id}`);
  await page.locator(".tpl-chat-identity").click();
  await expect(page.getByTestId("side-panel")).toBeVisible();
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await page.getByTestId("create-new-agent").click();
  await expect(page.getByTestId("new-conversation-picker")).toHaveCount(0);
  await page
    .getByTestId("side-panel")
    .getByLabel("Name", { exact: true })
    .fill(`${prefix} teammate`);
  const created = page.waitForResponse(
    (response) => response.url().endsWith("/api/agents") && response.request().method() === "POST",
  );
  await page
    .getByTestId("side-panel")
    .getByRole("button", { name: "Create agent", exact: true })
    .click();
  const teammate = remember("agents", await (await created).json());
  await expect(page).toHaveURL(new RegExp(`/app/${teammate.id}$`));
  await page
    .locator(".tpl-chat-header")
    .getByRole("button", { name: "Settings", exact: true })
    .click();
  await expect(page.getByRole("dialog", { name: "Workspace settings", exact: true })).toBeVisible();
  await page.goBack();
  await expect(page.getByRole("dialog", { name: "Workspace settings", exact: true })).toHaveCount(
    0,
  );
  await expect(page).toHaveURL(new RegExp(`/app/${teammate.id}$`));
});

test("tablet and Arabic phone layouts preserve navigation and unknown-route recovery", async ({
  page,
  workspace,
}) => {
  const { agent } = workspace;
  await page.setViewportSize({ width: 800, height: 900 });
  await page.goto(`/app/${agent.id}`);
  await page.locator(".tpl-chat-identity").click();
  const panel = page.getByTestId("side-panel");
  await expect(panel).toBeVisible();
  expect((await panel.boundingBox()).width).toBeGreaterThan(350);
  const close = panel.getByRole("button", { name: "Close context panel", exact: true });
  await close.click();
  await expect(panel).toHaveCount(0);
  expect((await page.getByTestId("transcript").boundingBox()).width).toBeGreaterThan(350);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => localStorage.setItem("lonora.locale", "ar"));
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await page.getByRole("button", { name: "فتح قائمة التنقل", exact: true }).click();
  await expect(page.locator(".tpl-sidebar")).toHaveAttribute("data-mobile-open", "true");
  await page.goBack();
  await expect(page.locator(".tpl-sidebar")).toHaveAttribute("data-mobile-open", "false");
  await expect(page).toHaveURL(new RegExp(`/app/${agent.id}$`));
  const dimensions = await page.evaluate(() => ({
    width: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width + 1);
  await page.goto("/app/unavailable/regression-route");
  await expect(page.locator("main h1")).toBeVisible();
  await page.locator("main a[href='/app']").click();
  await expect(page.getByTestId("transcript")).toBeVisible();
});

test("retry after a committed message response is lost reuses its real receipt", async ({
  page,
  context,
  workspace,
}) => {
  const { agent, prefix, post } = workspace;
  const message = `${prefix} accepted before connection loss`;
  const nonces = [];
  const ownedRuns = new Set();
  let lostReceipt;
  let loseResponse = true;
  await page.route("**/api/threads/*/messages", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    nonces.push(route.request().postDataJSON().client_nonce);
    if (!loseResponse) return route.continue();
    loseResponse = false;
    // Commit through the real API, then drop only the response seen by the browser.
    const response = await route.fetch();
    expect(response.ok()).toBeTruthy();
    lostReceipt = await response.json();
    for (const id of lostReceipt.run_ids) ownedRuns.add(id);
    await route.abort("failed");
  });
  const messageResponse = () =>
    page.waitForResponse(
      (response) =>
        /\/api\/threads\/[^/]+\/messages$/.test(new URL(response.url()).pathname) &&
        response.request().method() === "POST",
    );
  try {
    await page.goto(`/app/${agent.id}`);
    const composer = page.getByRole("combobox", { name: "Message", exact: true });
    await composer.fill(message);
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(page.locator(".template-composer-error")).toBeVisible();
    await expect(composer).toHaveValue(message);
    expect(lostReceipt.run_ids).toHaveLength(1);

    const retryResponse = messageResponse();
    await page.getByRole("button", { name: "Send direction", exact: true }).click();
    const recovered = await (await retryResponse).json();
    for (const id of recovered.run_ids) ownedRuns.add(id);
    expect(nonces).toHaveLength(2);
    expect(nonces[1]).toBe(nonces[0]);
    expect(recovered.message.id).toBe(lostReceipt.message.id);
    expect(recovered.run_ids).toEqual(lostReceipt.run_ids);
    await expect(composer).toHaveValue("");
    const threadId = recovered.message.thread_id;
    const committedMessages = await (
      await context.request.get(`/api/threads/${threadId}/messages`)
    ).json();
    expect(committedMessages.filter((row) => row.content === message)).toHaveLength(1);
    const committedRuns = await (
      await context.request.get(`/api/runs?thread_id=${threadId}`)
    ).json();
    expect(committedRuns).toHaveLength(1);

    // Sending identical content again after confirmation is a new deliberate intent.
    await composer.fill(message);
    const repeatedResponse = messageResponse();
    await page.getByRole("button", { name: "Send direction", exact: true }).click();
    const repeated = await (await repeatedResponse).json();
    for (const id of repeated.run_ids) ownedRuns.add(id);
    expect(nonces).toHaveLength(3);
    expect(nonces[2]).not.toBe(nonces[0]);
    expect(repeated.message.id).not.toBe(recovered.message.id);
    const deliberateMessages = await (
      await context.request.get(`/api/threads/${threadId}/messages`)
    ).json();
    expect(deliberateMessages.filter((row) => row.content === message)).toHaveLength(2);
  } finally {
    for (const id of ownedRuns) await post(`/runs/${id}/cancel`, {});
  }
});
