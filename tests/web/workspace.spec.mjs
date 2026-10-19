// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: Playwright runs directly without Turborepo caching.
import { execFileSync } from "node:child_process";

import { randomUUID } from "node:crypto";
import { test as base, expect } from "@playwright/test";

import { brokerFixture } from "./broker-fixture.mjs";

// Reuse this worker's authenticated session, not repeated password logins that
// consume the real anti-brute-force budget. Each test still has its own context.
let authenticatedSession;

const test = base.extend({
  workspace: async ({ context, page }, use) => {
    const prefix = `UI regression ${randomUUID()}`;
    const owned = {
      agents: new Set(),
      boards: new Set(),
      tickets: new Set(),
      routines: new Set(),
      skills: new Set(),
    };
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
    if (authenticatedSession) await context.addCookies(authenticatedSession.cookies);
    if (
      !authenticatedSession ||
      (await context.request.get("/api/auth/session")).status() !== 200
    ) {
      const login = await context.request.post("/api/auth/login", { data: credentials });
      expect(login.status()).toBe(200);
      authenticatedSession = { cookies: await context.cookies(), csrf: (await login.json()).csrf };
    }
    const headers = { "X-CSRF-Token": authenticatedSession.csrf };
    const broker = await brokerFixture(context, headers);
    const post = async (path, data) => {
      if (path === "/agents") data = { ...data, ...broker.binding };
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
      await use({ agent, prefix, post, remember, headers, broker });
      expect(errors).toEqual([]);
    } finally {
      await broker.close();
      // Only IDs created by this fixture or explicitly remembered by its test.
      for (const kind of ["skills", "routines", "tickets", "boards", "agents"])
        for (const id of owned[kind]) {
          const response = await context.request.delete(`/api/${kind}/${id}`, { headers });
          expect([200, 404]).toContain(response.status());
        }
    }
  },
});

test("refresh waits for the real session without flashing sign-in or workspace sections", async ({
  page,
  context,
  workspace,
}) => {
  const { agent } = workspace;
  await context.addInitScript(() => {
    localStorage.setItem("lonora.theme", JSON.stringify("light"));
  });
  let release;
  let started;
  const gated = new Promise((resolve) => {
    release = resolve;
  });
  const requested = new Promise((resolve) => {
    started = resolve;
  });
  await page.route("**/api/auth/session", async (route) => {
    const response = await route.fetch();
    expect(response.status()).toBe(200);
    started();
    await gated;
    await route.fulfill({ response });
  });
  try {
    await page.goto(`/app/${agent.id}`, { waitUntil: "domcontentloaded" });
    await requested;
    await expect(page.getByTestId("workspace-loading")).toBeVisible();
    await expect(page.getByRole("button", { name: "Sign in", exact: true })).toHaveCount(0);
    await expect(page.getByTestId("transcript")).toHaveCount(0);
    await expect(page.locator(".tpl-shell")).toHaveCount(0);
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    release();
    await expect(page.getByTestId("transcript")).toHaveCount(1);
    await expect(page.getByTestId("workspace-loading")).toHaveCount(0);
    await page.reload();
    await expect(page.getByTestId("transcript")).toHaveCount(1);
  } finally {
    release();
  }
});

test("owner shadow mode persists through reload without enabling live trading", async ({
  page,
  context,
  workspace,
}) => {
  const { agent } = workspace;
  await page.goto(`/app/${agent.id}`);
  await page.getByRole("button", { name: `Agent settings: ${agent.name}`, exact: true }).click();
  let control = page.getByRole("checkbox", {
    name: "Shadow trading — virtual orders only",
    exact: true,
  });
  await expect(control).not.toBeChecked();
  // The controlled checkbox reflects the server response, not an optimistic
  // checked state before the owner mode is actually persisted.
  await control.click();
  await expect(control).toBeChecked();
  await expect
    .poll(async () => {
      const agents = await (await context.request.get("/api/agents")).json();
      return agents.find((row) => row.id === agent.id).execution_mode;
    })
    .toBe("shadow");
  await expect(page.getByText("Shadow observations", { exact: false })).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: `Agent settings: ${agent.name}`, exact: true }).click();
  control = page.getByRole("checkbox", {
    name: "Shadow trading — virtual orders only",
    exact: true,
  });
  await expect(control).toBeChecked();
  const controls = await (await context.request.get("/api/trading/controls")).json();
  expect(controls.enabled).toBe(false);
});

test("recoverable task failure shows authoritative review and resumes the same Run", async ({
  page,
  context,
  workspace,
}) => {
  const { agent, headers } = workspace;
  const session = await (await context.request.get("/api/auth/session")).json();
  const thread = await (
    await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
  ).json();
  const task = await (
    await context.request.post(`/api/tasks?agent_id=${agent.id}&thread_id=${thread.id}`, {
      headers,
      data: {
        title: "Recover actual status",
        steps: [{ id: "read", title: "Read", side_effect: "read_only" }],
      },
    })
  ).json();
  const tickets = await (await context.request.get("/api/tickets")).json();
  const ticket = tickets.find((row) => row.id === task.id);
  execFileSync(".venv/bin/python", ["tests/check_task_browser.py"], {
    input: JSON.stringify({
      owner_id: session.id,
      task_id: task.id,
      run_id: ticket.payload.run_id,
    }),
    encoding: "utf8",
  });
  await page.goto(`/app/${agent.id}`);
  const live = page.getByTestId("agent-live-state");
  await expect(live).toHaveAttribute("data-state", "action_required");
  await live.locator("summary").click();
  await expect(live.getByText("Task needs review", { exact: true })).toBeVisible();
  await live.getByRole("button", { name: "Resume", exact: true }).click();
  await expect
    .poll(async () => (await (await context.request.get(`/api/tasks/${task.id}`)).json()).status)
    .toBe("queued");
  const restored = await (await context.request.get(`/api/tasks/${task.id}`)).json();
  expect(restored.attempt).toBe(2);
  expect(restored.runs).toHaveLength(1);
  expect(restored.runs[0].id).toBe(ticket.payload.run_id);
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
  await page
    .getByTestId("side-panel")
    .getByLabel("Broker account", { exact: true })
    .selectOption(agent.trading_account_id);
  await page.getByRole("button", { name: "Choose trading pair", exact: true }).click();
  await page.getByRole("option", { name: agent.trading_symbol, exact: true }).click();
  const created = page.waitForResponse(
    (response) => response.url().endsWith("/api/agents") && response.request().method() === "POST",
  );
  await page
    .getByTestId("side-panel")
    .getByRole("button", { name: "Create agent", exact: true })
    .click();
  const teammate = remember("agents", await (await created).json());
  await expect(page).toHaveURL(new RegExp(`/app/${teammate.id}$`));
  await page.locator(".tpl-account-trigger").click();
  await page.getByRole("menuitem", { name: "Settings", exact: true }).click();
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
  await expect(page.getByTestId("conversation-inbox")).toBeVisible();
  await expect(page.getByTestId("transcript")).toHaveCount(0);
  await page.locator(`[data-inbox-agent-id="${agent.id}"]`).click();
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

test("knowledge and recurring trading work use durable API edits", async ({
  page,
  context,
  workspace,
}) => {
  const { agent, prefix, remember, headers } = workspace;
  await page.goto(`/app/${agent.id}`);
  await page.locator(".tpl-chat-identity").click();
  await page
    .getByTestId("side-panel")
    .getByRole("button", { name: "Knowledge", exact: true })
    .click();
  const panel = page.getByTestId("side-panel");
  await panel.getByRole("button", { name: "Skills", exact: true }).click();
  await panel.getByLabel("Title", { exact: true }).fill(`${prefix} market checklist`);
  await panel
    .getByLabel("Content", { exact: true })
    .fill("Read current positions and spreads before preparing an order.");
  const createdSkill = page.waitForResponse(
    (response) => response.url().endsWith("/api/skills") && response.request().method() === "POST",
  );
  await panel.getByRole("button", { name: "Add", exact: true }).click();
  const skill = remember("skills", await (await createdSkill).json());
  const item = panel
    .locator("details")
    .filter({ has: page.locator("summary", { hasText: `${prefix} market checklist` }) });
  await item.locator("summary").click();
  await item
    .getByLabel("Content", { exact: true })
    .fill("Check the economic calendar and spread before preparing an order.");
  const editedSkill = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/skills/${skill.id}`) && response.request().method() === "PUT",
  );
  await item.getByRole("button", { name: "Save", exact: true }).click();
  const version = await (await editedSkill).json();
  expect(version.version).toBe(skill.version + 1);
  expect(version.payload.content).toContain("economic calendar");
  await page.goto("/app/routines");
  await page.getByRole("button", { name: "Create routine", exact: true }).click();
  let dialog = page.getByRole("dialog", { name: "Create routine", exact: true });
  await dialog.getByRole("combobox", { name: "Agent", exact: true }).selectOption(agent.id);
  await dialog.getByLabel("Task", { exact: true }).fill(`${prefix} scheduled market review`);
  await dialog.getByLabel("Every · minutes", { exact: true }).fill("17");
  await dialog.getByLabel("Timezone", { exact: true }).fill("UTC");
  const createdRoutine = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/routines/${agent.id}`) &&
      response.request().method() === "POST",
  );
  await dialog.getByRole("button", { name: "Save", exact: true }).click();
  const routine = remember("routines", await (await createdRoutine).json());
  expect(routine.interval_seconds).toBe(1020);
  const row = page.getByTestId(`routine-row-${routine.id}`);
  await row.getByRole("button", { name: "Edit", exact: true }).click();
  dialog = page.getByRole("dialog", { name: "Edit routine", exact: true });
  await dialog
    .getByLabel("Task", { exact: true })
    .fill(`${prefix} revised scheduled market review`);
  const updatedRoutine = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/routines/${routine.id}`) &&
      response.request().method() === "PUT",
  );
  await dialog.getByRole("button", { name: "Save", exact: true }).click();
  expect((await (await updatedRoutine).json()).prompt).toContain("revised");
  await row.getByRole("button", { name: "Pause", exact: true }).click();
  await expect
    .poll(
      async () =>
        (await (await context.request.get(`/api/routines?agent_id=${agent.id}`)).json()).find(
          (entry) => entry.id === routine.id,
        )?.enabled,
    )
    .toBe(false);
  await row.locator("summary", { hasText: "Execution history" }).click();
  await expect(row.getByText("No executions yet", { exact: true })).toBeVisible();
  await page.goto(`/app/${agent.id}?settings=trading`);
  await expect(page.getByRole("dialog", { name: "Workspace settings", exact: true })).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`/app/${agent.id}$`));
  // The test owns this routine; no scheduler or provider credentials are needed.
  const durable = await context.request.get(`/api/skills/${skill.id}`, { headers });
  expect((await durable.json()).payload.content).toContain("economic calendar");
});

test("financial approval buttons persist decisions and display broker receipts after refresh", async ({
  page,
  context,
}) => {
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
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const post = async (path, body) => {
    const response = await context.request.post(`/api${path}`, { headers, data: body });
    expect(response.ok()).toBeTruthy();
    return response.json();
  };
  const agent = await post("/agents", {
    name: `Approval UI ${randomUUID()}`,
    trading_account_id: data.account,
    trading_symbol: data.symbol,
  });
  try {
    const thread = await post(`/agents/${agent.id}/conversation`, {});
    const approval = {
      id: randomUUID(),
      thread_id: thread.id,
      status: "pending",
      requests: [
        {
          operation_id: "fixed-operation",
          action: "buy_limit",
          symbol: "EURUSD.demo",
          volume: "0.1",
          price: "99",
          stop_loss: "98",
          take_profit: "102",
        },
      ],
      results: [],
    };
    let decisions = 0;
    await page.route("**/api/trading/approvals?*", (route) => route.fulfill({ json: [approval] }));
    await page.route(`**/api/trading/approvals/${approval.id}/decision`, async (route) => {
      decisions++;
      expect(route.request().postDataJSON()).toEqual({ decision: "approve" });
      approval.status = "completed";
      approval.results = [
        {
          operation_id: "fixed-operation",
          status: "confirmed",
          broker_id: "native-ticket-42",
          details: { price: "99.02" },
        },
      ];
      await route.fulfill({ json: approval });
    });
    await page.goto(`/app/${agent.id}`);
    const card = page.locator(`[data-trade-approval='${approval.id}']`);
    await expect(card.getByText("EURUSD.demo", { exact: true })).toBeVisible();
    await expect(card.locator("[data-trade-result]")).toHaveCount(0);
    await card.getByRole("button", { name: "Approve", exact: true }).click();
    await expect(card.locator("[data-trade-result='confirmed']")).toBeVisible();
    await expect(card.getByText("native-ticket-42", { exact: true })).toBeVisible();
    await expect(card.getByText("99.02", { exact: true })).toBeVisible();
    await expect(card.getByRole("button", { name: "Approve", exact: true })).toHaveCount(0);
    await page.reload();
    await expect(card.getByText("native-ticket-42", { exact: true })).toBeVisible();
    expect(decisions).toBe(1);
    // A rejection is never rendered as broker success, including after reconnection.
    approval.results = [
      {
        operation_id: "fixed-operation",
        status: "failed",
        code: "TRADE_RETCODE_INVALID_VOLUME",
        details: { description: "Invalid volume" },
      },
    ];
    await page.reload();
    await expect(card.locator("[data-trade-result='failed']")).toBeVisible();
    await expect(card.getByText("TRADE_RETCODE_INVALID_VOLUME", { exact: true })).toBeVisible();
    await expect(card.getByText("Invalid volume", { exact: true })).toBeVisible();
  } finally {
    await context.request.delete(`/api/agents/${agent.id}`, { headers });
    fixture({ ...data, action: "cleanup" });
  }
});

test("cancelled durable task stays cancelled on the board after reload and has no generic edit/run bypass", async ({
  page,
  workspace,
}) => {
  const { agent, prefix, post, remember } = workspace;
  const thread = await post(`/agents/${agent.id}/conversation`, {});
  const task = await post(`/tasks?agent_id=${agent.id}&thread_id=${thread.id}`, {
    title: `${prefix} cancelled durable work`,
  });
  const details = await (await page.request.get(`/api/tickets/${task.id}`)).json();
  remember("tickets", { id: task.id });
  remember("boards", { id: details.payload.board_id });
  const stopped = await post("/tasks/control", {
    task_id: task.id,
    action: "cancel",
    expected_version: task.version,
  });
  expect(stopped.status).toBe("cancelled");
  await page.goto("/app/board");
  await page
    .getByRole("combobox", { name: "Board", exact: true })
    .selectOption(details.payload.board_id);
  const column = page
    .locator(".workspace-board-column")
    .filter({ has: page.getByRole("heading", { name: /Cancelled/ }) });
  await expect(column.getByTestId(`board-card-${task.id}`)).toBeVisible();
  await page.reload();
  await page
    .getByRole("combobox", { name: "Board", exact: true })
    .selectOption(details.payload.board_id);
  await page.getByTestId(`board-card-${task.id}`).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("status")).toHaveText("Cancelled");
  await expect(dialog.getByRole("button", { name: "Save", exact: true })).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: "Run task", exact: true })).toHaveCount(0);
});

test("agent deletion requires confirmation and Personal Agent keeps its gold role badge", async ({
  page,
  context,
  workspace,
}) => {
  const { agent } = workspace;
  const agents = await (await context.request.get("/api/agents")).json();
  const personal = agents.find((row) => row.role === "personal");
  expect(personal).toBeTruthy();
  await page.goto(`/app/${personal.id}`);
  await expect(
    page
      .locator(`[data-roster-agent-id="${personal.id}"]`)
      .getByRole("img", { name: "Personal Agent", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: `Agent settings: ${personal.name}`, exact: true }).click();
  await expect(
    page.getByText("Your Personal Agent cannot be deleted.", { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Delete agent", exact: true })).toHaveCount(0);

  await page.goto(`/app/${agent.id}`);
  await expect(
    page
      .locator(`[data-roster-agent-id="${agent.id}"]`)
      .getByRole("img", { name: "Personal Agent", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: `Agent settings: ${agent.name}`, exact: true }).click();
  await page.getByRole("button", { name: "Delete agent", exact: true }).click();
  const confirmation = page.getByRole("alertdialog", {
    name: "Delete agent permanently?",
    exact: true,
  });
  await expect(confirmation).toContainText(agent.name);
  await confirmation.getByRole("button", { name: "Cancel", exact: true }).click();
  expect(
    (await (await context.request.get("/api/agents")).json()).some((row) => row.id === agent.id),
  ).toBe(true);
  await page.getByRole("button", { name: "Delete agent", exact: true }).click();
  // A failed API request must keep the agent and confirmation available for retry.
  await page.route(`**/api/agents/${agent.id}`, async (route) => {
    if (route.request().method() === "DELETE")
      await route.fulfill({ status: 409, json: { detail: "agent_busy" } });
    else await route.continue();
  });
  await confirmation.getByRole("button", { name: "Delete permanently", exact: true }).click();
  await expect(
    confirmation.getByRole("button", { name: "Delete permanently", exact: true }),
  ).toBeEnabled();
  await expect(page).toHaveURL(new RegExp(`/app/${agent.id}$`));
  expect(
    (await (await context.request.get("/api/agents")).json()).some((row) => row.id === agent.id),
  ).toBe(true);
  await page.unroute(`**/api/agents/${agent.id}`);
  const deleted = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/agents/${agent.id}`) &&
      response.request().method() === "DELETE",
  );
  await confirmation.getByRole("button", { name: "Delete permanently", exact: true }).click();
  expect((await deleted).ok()).toBe(true);
  await expect(page).toHaveURL(new RegExp(`/app/${personal.id}$`));
  await expect(page.locator(`[data-roster-agent-id="${agent.id}"]`)).toHaveCount(0);
  await page.reload();
  expect(
    (await (await context.request.get("/api/agents")).json()).some((row) => row.id === agent.id),
  ).toBe(false);
  await expect(page.locator(`[data-roster-agent-id="${agent.id}"]`)).toHaveCount(0);
});
