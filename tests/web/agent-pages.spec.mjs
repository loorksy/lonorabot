import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

/* Phase 4a (docs/ui-reference/CAPABILITY_MAP.md, Phase 4): the agent page, its identity form,
   supervision, the trades page with the owner's own close through the executor, the chart
   sheet with real candles, the group page and «مجموعة جديدة», on a real database. Nothing in
   the UI may delete an agent or a group (Q1, Q44). */
function fixture(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/agent_pages_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}
let data = null;
const deletes = [];
const errors = [];
test.beforeEach(async ({ page, context }) => {
  data = fixture({ action: "init" });
  data.groups = [];
  data.agents = [];
  await context.addCookies(
    data.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  page.on("pageerror", (error) => {
    console.log("pageerror:", error.message);
    errors.push(error.message);
  });
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (request.method() === "DELETE" && /^\/api\/(agents|groups)\//.test(path)) deletes.push(path);
  });
});
test.afterEach(() => {
  expect(deletes).toEqual([]);
  expect(errors.splice(0)).toEqual([]);
  if (data) fixture({ ...data, action: "cleanup" });
  data = null;
});

test("the trading agent's page: level, trading and safety, watches, and the on/off button", async ({
  page,
}) => {
  await page.goto(`/app/agent/${data.trader.id}`);
  const main = page.locator("main");
  await expect(main.locator(".hero h2")).toHaveText(data.trader.name);
  await expect(main.locator(".hero .badge")).toHaveText("Ask me");
  await expect(main).toContainText("Trading and safety");
  await expect(main).toContainText("Ask me on every order");
  await expect(main.locator(".wt-row strong")).toHaveText(
    new RegExp(`${data.symbol}\\W*below\\W*200`),
  );
  // «يشرف على» belongs to supervisors only (reference canSupervise).
  await expect(main.getByRole("heading", { name: "Supervises" })).toHaveCount(0);
  // Q1, Q44: the agent page never offers to delete the agent.
  await expect(main.getByRole("button", { name: /delete|remove the agent/i })).toHaveCount(0);
  for (const row of [
    "Identity and model",
    "Knowledge",
    "Skills",
    "Goals",
    "Scheduled tasks",
    "Files",
    "Trades",
  ])
    await expect(main.getByRole("button", { name: row, exact: true })).toBeVisible();
  const patch = page.waitForRequest(
    (request) =>
      request.method() === "PATCH" && request.url().endsWith(`/api/agents/${data.trader.id}`),
  );
  await main.getByRole("button", { name: "Stop the agent", exact: true }).click();
  expect((await patch).postDataJSON()).toEqual({ paused: true });
  await expect(main.getByRole("button", { name: "Turn the agent on", exact: true })).toBeVisible();
  await main.getByRole("button", { name: "Turn the agent on", exact: true }).click();
  await expect(main.getByRole("button", { name: "Stop the agent", exact: true })).toBeVisible();
  // «الهوية والنموذج» opens the form with the pair from the account's own symbols.
  await main.getByRole("button", { name: "Identity and model", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/app/identity/${data.trader.id}$`));
  await expect(main.getByRole("combobox", { name: "Pair", exact: true })).toHaveValue(data.symbol);
  const save = page.waitForRequest(
    (request) =>
      request.method() === "PATCH" && request.url().endsWith(`/api/agents/${data.trader.id}`),
  );
  await main.getByLabel("Name", { exact: true }).fill(`${data.trader.name} 2`);
  await main.getByRole("button", { name: "Save", exact: true }).click();
  // A rename alone never sends a scope change.
  expect((await save).postDataJSON()).toEqual({
    name: `${data.trader.name} 2`,
    description: "Follows gold",
  });
});

test("Lonora's page has no on/off button (Q38); a research agent has no level badge", async ({
  page,
}) => {
  const agents = await (await page.request.get("/api/agents")).json();
  const lonora = agents.find((agent) => agent.role === "personal");
  await page.goto(`/app/agent/${lonora.id}`);
  const main = page.locator("main");
  await expect(main.locator(".hero h2")).toHaveText(lonora.name);
  await expect(main).toContainText("Supervises");
  await expect(main.getByRole("button", { name: "Stop the agent" })).toHaveCount(0);
  await expect(main.getByRole("button", { name: "Turn the agent on" })).toHaveCount(0);
  await page.goto(`/app/agent/${data.research.id}`);
  await expect(main.locator(".hero h2")).toHaveText(data.research.name);
  await expect(main.locator(".hero .badge")).toHaveCount(0);
  await expect(main.getByRole("button", { name: "Stop the agent", exact: true })).toBeVisible();
});

test("supervision: add from the picker, remove from the row; never money authority", async ({
  page,
}) => {
  const supervisor = await (
    await page.request.post("/api/agents/create", {
      headers: {
        "X-CSRF-Token": data.cookies.find((cookie) => cookie.name === "lonora_csrf").value,
      },
      data: { template: "supervisor", name: `Overseer ${data.trader.id.slice(0, 6)}` },
    })
  ).json();
  data.agents.push(supervisor.id);
  await page.goto(`/app/agent/${supervisor.id}`);
  const main = page.locator("main");
  await expect(main).toContainText("It does not supervise any agent now.");
  await main.getByRole("button", { name: "Add agents to supervise", exact: true }).click();
  const sheet = page.locator("#dialog");
  await expect(sheet).toContainText("This gives it no execution authority.");
  await sheet.getByRole("checkbox", { name: new RegExp(data.trader.name) }).click();
  const grant = page.waitForRequest(
    (request) =>
      request.method() === "POST" && new URL(request.url()).pathname === "/api/supervision",
  );
  await sheet.getByRole("button", { name: "Add", exact: true }).click();
  expect((await grant).postDataJSON()).toEqual({
    supervisor_id: supervisor.id,
    supervised_id: data.trader.id,
  });
  await expect(main.locator(".row", { hasText: data.trader.name })).toBeVisible();
  // The supervised agent's page names its supervisor.
  await page.goto(`/app/agent/${data.trader.id}`);
  await expect(main.locator(".sup-line")).toContainText(supervisor.name);
  await page.goto(`/app/agent/${supervisor.id}`);
  const revoke = page.waitForRequest((request) =>
    /\/api\/supervision\/[^/]+\/revoke$/.test(new URL(request.url()).pathname),
  );
  await main
    .locator(".row", { hasText: data.trader.name })
    .getByRole("button", { name: "Remove" })
    .click();
  await revoke;
  await expect(main).toContainText("It does not supervise any agent now.");
});

test("the trading and safety row opens the sheet over the agent page; closing stays there", async ({
  page,
}) => {
  await page.goto(`/app/agent/${data.trader.id}`);
  const main = page.locator("main");
  const url = page.url();
  await main.getByRole("button", { name: /Trading · New trades · Restrictions/ }).click();
  const sheet = page.locator("#dialog");
  await expect(sheet.getByTestId("agent-live-state")).toBeVisible();
  expect(page.url()).toBe(url);
  await page.keyboard.press("Escape");
  await expect(sheet).not.toBeVisible();
  await expect(page).toHaveURL(url);
  await expect(main.locator(".hero h2")).toHaveText(data.trader.name);
});

test("a trading agent with no linked account links one through the broker form", async ({
  page,
}) => {
  await page.route("**/api/trading/connections", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );
  await page.route("**/api/agents", async (route) => {
    const response = await route.fetch();
    const agents = await response.json();
    await route.fulfill({
      response,
      json: agents.map((agent) =>
        agent.id === data.trader.id ? { ...agent, trading_account_id: null } : agent,
      ),
    });
  });
  await page.goto(`/app/agent/${data.trader.id}`);
  await page
    .locator("main")
    .getByRole("button", { name: /No trading account linked/ })
    .click();
  await expect(page).toHaveURL(/\/app\/broker$/);
});

test("the call button follows Q58 when no voice provider is configured", async ({ page }) => {
  const status = await (await page.request.get("/api/voice/status")).json();
  test.skip(status.transport_configured, "a voice provider is configured in this environment");
  await page.goto(`/app/agent/${data.trader.id}`);
  const call = page.locator("main .hero-actions").getByRole("button", { name: "Call" });
  await expect(call).toHaveAttribute("aria-disabled", "true");
  // Shown dimmed but still tappable: the tap explains why and where to set it up.
  await call.click({ force: true });
  const sheet = page.locator("#dialog");
  await expect(sheet).toContainText("Calls are not set up");
  await sheet.getByRole("button", { name: "Open voice settings", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/provider\/openai$/);
});

test("trades: the owner's own close goes through the executor; the order log shows states", async ({
  page,
}) => {
  await page.goto(`/app/trades/${data.trader.id}`);
  const main = page.locator("main");
  const card = main.locator("[data-position-id]").first();
  await expect(card).toContainText(data.symbol);
  await expect(card).toContainText("0.1");
  // The agent's operations under the reference's names, with the broker's evidence.
  const row = (state) => main.locator(`.od-row[data-order-state="${state}"]`);
  await expect(row("filled")).toContainText(`Buy 0.3 ${data.symbol}`);
  await expect(row("filled")).toContainText("At market price");
  await expect(row("filled")).toContainText("211.00");
  await expect(row("partial")).toContainText("0.2 / 0.5");
  await expect(row("partial")).toContainText("Partly filled");
  await expect(row("partial")).toContainText("209.5");
  // A placed limit order: «مقبول لدى الوسيط», and no price the broker did not give.
  await expect(row("accepted")).toContainText("Limit order");
  await expect(row("accepted")).not.toContainText("205");
  await expect(row("rejected")).toContainText("Stop order");
  await expect(row("rejected")).not.toContainText("220");
  await expect(row("cancelled")).toContainText("Close the trade");
  const position = await card.getAttribute("data-position-id");
  await card.getByRole("button", { name: "Close the trade", exact: true }).click();
  const execute = page.waitForRequest(
    (request) =>
      request.method() === "POST" && new URL(request.url()).pathname === "/api/trading/execute",
  );
  await page
    .locator("#dialog")
    .getByRole("button", { name: "Close the trade", exact: true })
    .click();
  const body = (await execute).postDataJSON();
  expect(body).toMatchObject({
    action: "close_position",
    account_id: data.account,
    symbol: data.symbol,
    position_id: position,
  });
  expect(typeof body.operation_id).toBe("string");
  await expect(main.locator("[data-position-id]")).toHaveCount(0);
});

test("the chart sheet draws the broker's candles for the agent's pair (Q37)", async ({ page }) => {
  await page.goto(`/app/${data.trader.id}`);
  await page.getByRole("button", { name: "Chat menu", exact: true }).click();
  await page.locator("#dialog").getByRole("button", { name: "Chart", exact: true }).click();
  const sheet = page.locator("#dialog");
  await expect(sheet).toHaveClass(/expandable/);
  await sheet.getByRole("tab", { name: "15m" }).click();
  await expect(sheet.locator("svg.chart > g > rect").first()).toBeVisible();
  expect(await sheet.locator("svg.chart > g > rect").count()).toBeGreaterThan(8);
  await sheet.getByRole("button", { name: "Full screen", exact: true }).click();
  await expect(sheet).toHaveClass(/expanded/);
});

test("the group page and «مجموعة جديدة» with purpose and coordinator; no deletion", async ({
  page,
}) => {
  await page.goto(`/app/group/${data.group.id}`);
  const main = page.locator("main");
  await expect(main.locator(".hero h2")).toHaveText(data.group.payload.name);
  await expect(main).toContainText("Gold research");
  await expect(main.locator(".row", { hasText: data.research.name })).toContainText("Coordinator");
  await expect(main.getByRole("button", { name: /delete/i })).toHaveCount(0);
  await page.goto("/app/new-group");
  await main.getByLabel("Group name", { exact: true }).fill(`${data.group.payload.name} 2`);
  await main.getByLabel("Purpose", { exact: true }).fill("Second desk");
  await main.getByRole("switch", { name: data.trader.name }).check();
  await main.getByRole("switch", { name: data.research.name }).check();
  await main
    .getByRole("combobox", { name: "Coordinator", exact: true })
    .selectOption(data.research.id);
  const create = page.waitForResponse(
    (response) => new URL(response.url()).pathname === "/api/groups/create",
  );
  await main.getByRole("button", { name: "Create the group", exact: true }).click();
  const response = await create;
  const group = await response.json();
  data.groups.push(group.id);
  expect(response.request().postDataJSON()).toMatchObject({
    purpose: "Second desk",
    lead_agent_id: data.research.id,
    member_ids: [data.trader.id, data.research.id],
  });
  await expect(page).toHaveURL(new RegExp(`/app/group/${group.id}$`));
});

test("watches: pause, resume and cancel with undo, each through the watch's control route", async ({
  page,
}) => {
  await page.goto(`/app/agent/${data.trader.id}`);
  const main = page.locator("main");
  const watch = main.locator(".wt-row");
  const control = () =>
    page.waitForRequest(
      (request) =>
        request.method() === "POST" &&
        new URL(request.url()).pathname === `/api/watches/${data.watch}/control`,
    );
  let sent = control();
  await watch.getByRole("button", { name: "Pause for now", exact: true }).click();
  expect((await sent).postDataJSON()).toEqual({ action: "pause" });
  await expect(watch).toContainText("Paused for now");
  sent = control();
  await watch.getByRole("button", { name: "Resume", exact: true }).click();
  expect((await sent).postDataJSON()).toEqual({ action: "resume" });
  await expect(watch).not.toContainText("Paused for now");
  sent = control();
  await watch.getByRole("button", { name: "Cancel", exact: true }).click();
  expect((await sent).postDataJSON()).toEqual({ action: "cancel" });
  await expect(main.locator(".wt-row")).toHaveCount(0);
  sent = control();
  await page.locator("#toast").getByRole("button", { name: "Undo" }).click();
  expect((await sent).postDataJSON()).toEqual({ action: "resume" });
  await expect(main.locator(".wt-row")).toHaveCount(1);
  sent = control();
  await watch.getByRole("button", { name: "Extend two hours", exact: true }).click();
  expect((await sent).postDataJSON()).toEqual({ action: "extend", hours: 2 });
  await expect(page.locator("#toast")).toContainText("Extended until");
  await main.getByRole("button", { name: "New watch", exact: true }).click();
  await expect(page).toHaveURL(
    new RegExp(`/app/new-schedule\\?agent=${data.trader.id}&kind=condition$`),
  );
});

test("«وكيل جديد»: the supervision switch sends the agents it supervises; the model stays automatic", async ({
  page,
}) => {
  await page.goto("/app/new-agent");
  const main = page.locator("main");
  await main.getByRole("radio", { name: /^Research agent/ }).check();
  await main.getByRole("switch", { name: "Supervise other agents", exact: true }).click();
  await main.getByRole("button", { name: "Next", exact: true }).click();
  await expect(main.getByRole("combobox", { name: "Model", exact: true })).toHaveValue("");
  await main
    .getByLabel("Agent name", { exact: true })
    .fill(`Watcher ${data.trader.id.slice(0, 6)}`);
  await main.getByLabel("Description", { exact: true }).fill("Keeps an eye on the desk");
  await main.getByRole("switch", { name: data.trader.name }).check();
  const creation = page.waitForResponse(
    (response) => new URL(response.url()).pathname === "/api/agents/create",
  );
  await main.getByRole("button", { name: "Create the agent", exact: true }).click();
  const response = await creation;
  const agent = await response.json();
  data.agents.push(agent.id);
  const body = response.request().postDataJSON();
  expect(body).toMatchObject({ template: "research", supervises: [data.trader.id] });
  expect(body).not.toHaveProperty("model");
  await expect(page).toHaveURL(new RegExp(`/app/agent/${agent.id}$`));
  await expect(main.locator(".row", { hasText: data.trader.name })).toBeVisible();
});

test("«تعديل الوقف والهدف»: one operation per body, a retry reuses it, a clear is explicit", async ({
  page,
}) => {
  const bodies = [];
  let dropFirst = true;
  await page.route("**/api/trading/execute", async (route) => {
    const body = route.request().postDataJSON();
    if (body.action !== "modify_position") return route.continue();
    bodies.push(body);
    // The first send is lost before it reaches the server: the button keeps its operation.
    if (dropFirst) {
      dropFirst = false;
      return route.abort("failed");
    }
    return route.continue();
  });
  await page.goto(`/app/trades/${data.trader.id}`);
  const main = page.locator("main");
  const card = main.locator("[data-position-id]").first();
  const position = await card.getAttribute("data-position-id");
  const sheet = page.locator("#dialog");
  const modify = async (stop) => {
    await card.getByRole("button", { name: "Edit stop and target", exact: true }).click();
    await sheet.getByLabel("Stop loss", { exact: true }).fill(stop);
    await sheet.getByRole("button", { name: "Save", exact: true }).click();
  };
  await modify("205");
  await expect(card.getByRole("alert")).toBeVisible();
  await modify("205");
  await expect.poll(() => bodies.length).toBe(2);
  await expect(card.locator("[data-operation-status]")).toBeVisible();
  await modify("206");
  await expect.poll(() => bodies.length).toBe(3);
  await modify("");
  await expect.poll(() => bodies.length).toBe(4);
  expect(bodies[0].operation_id).toBe(bodies[1].operation_id);
  expect(bodies[2].operation_id).not.toBe(bodies[1].operation_id);
  expect(bodies[3].operation_id).not.toBe(bodies[2].operation_id);
  expect(bodies[3]).toMatchObject({ position_id: position, clear_stop_loss: true });
  expect(bodies[3]).not.toHaveProperty("stop_loss");
  // The card reports the last action: the clear, with the server's answer.
  await expect(card.locator("[data-operation-status]")).toBeVisible();
  await expect(card.getByRole("alert")).toHaveCount(0);
});

test("identity: a saved pair missing from the account's list is kept; a rename sends no market", async ({
  page,
}) => {
  // The account no longer lists the agent's saved pair.
  await page.route("**/api/market/symbols*", (route) => route.fulfill({ json: ["EURUSD"] }));
  await page.goto(`/app/identity/${data.trader.id}`);
  const main = page.locator("main");
  const pair = main.getByRole("combobox", { name: "Pair", exact: true });
  await expect(pair).toHaveValue(data.symbol);
  const save = page.waitForRequest(
    (request) =>
      request.method() === "PATCH" && request.url().endsWith(`/api/agents/${data.trader.id}`),
  );
  await main.getByLabel("Name", { exact: true }).fill(`${data.trader.name} 3`);
  await main.getByRole("button", { name: "Save", exact: true }).click();
  expect((await save).postDataJSON()).toEqual({
    name: `${data.trader.name} 3`,
    description: "Follows gold",
  });
});

test("identity: a trading agent with no account sends a market only when the owner picks one", async ({
  page,
}) => {
  const csrf = data.cookies.find((cookie) => cookie.name === "lonora_csrf").value;
  const headers = { "X-CSRF-Token": csrf };
  const current = await (await page.request.get(`/api/agents/${data.trader.id}`)).json();
  const cleared = await page.request.patch(`/api/agents/${data.trader.id}`, {
    headers,
    data: {
      scope_mode: "flexible",
      trading_account_id: null,
      trading_symbol: null,
      expected_scope_revision: current.scope_revision,
    },
  });
  expect(cleared.ok()).toBeTruthy();
  await page.goto(`/app/identity/${data.trader.id}`);
  const main = page.locator("main");
  const account = main.getByRole("combobox", { name: "Trading account", exact: true });
  await expect(account).toHaveValue("");
  await expect(main.getByRole("combobox", { name: "Pair", exact: true })).toHaveCount(0);
  let save = page.waitForRequest(
    (request) =>
      request.method() === "PATCH" && request.url().endsWith(`/api/agents/${data.trader.id}`),
  );
  await main.getByLabel("Name", { exact: true }).fill(`${data.trader.name} 4`);
  await main.getByRole("button", { name: "Save", exact: true }).click();
  expect((await save).postDataJSON()).toEqual({
    name: `${data.trader.name} 4`,
    description: "Follows gold",
  });
  // The owner picks the account: the pair comes from its symbols and the market is sent.
  await page.goto(`/app/identity/${data.trader.id}`);
  await account.selectOption(data.account);
  await expect(main.getByRole("combobox", { name: "Pair", exact: true })).toHaveValue(data.symbol);
  await expect(main.locator(".note[role=status]")).toContainText("flexible default");
  save = page.waitForRequest(
    (request) =>
      request.method() === "PATCH" && request.url().endsWith(`/api/agents/${data.trader.id}`),
  );
  await main.getByRole("button", { name: "Save", exact: true }).click();
  expect((await save).postDataJSON()).toMatchObject({
    scope_mode: "flexible",
    trading_account_id: data.account,
    trading_symbol: data.symbol,
    expected_scope_revision: current.scope_revision + 1,
  });
});

test("«وكيل جديد» with a fixed model sends it", async ({ page }) => {
  const agents = await (await page.request.get("/api/agents")).json();
  const lonora = agents.find((agent) => agent.role === "personal");
  // One configured model, as the personal agent's summary lists the owner's models.
  await page.route(`**/api/agents/${lonora.id}/model/summary`, async (route) => {
    const summary = await (await route.fetch()).json();
    await route.fulfill({
      json: {
        ...summary,
        available: [{ provider: "openai", model: "gpt-fixture", name: "Fixture model" }],
      },
    });
  });
  let body = null;
  await page.route("**/api/agents/create", (route) => {
    body = route.request().postDataJSON();
    return route.abort("failed");
  });
  await page.goto("/app/new-agent");
  const main = page.locator("main");
  await main.getByRole("radio", { name: /^General agent/ }).check();
  await main.getByRole("button", { name: "Next", exact: true }).click();
  await main.getByLabel("Agent name", { exact: true }).fill("Model fixture");
  await main.getByLabel("Description", { exact: true }).fill("Uses one model");
  await main
    .getByRole("combobox", { name: "Model", exact: true })
    .selectOption({ label: "Fixture model" });
  await main.getByRole("button", { name: "Create the agent", exact: true }).click();
  await expect.poll(() => body).not.toBeNull();
  expect(body).toMatchObject({
    template: "general",
    model: { provider: "openai", model: "gpt-fixture" },
  });
});

test("the group page adds an agent with the group's version; the members list grows", async ({
  page,
}) => {
  const agents = await (await page.request.get("/api/agents")).json();
  const lonora = agents.find((agent) => agent.role === "personal");
  await page.goto(`/app/group/${data.group.id}`);
  const main = page.locator("main");
  await main.getByRole("button", { name: "Add an agent", exact: true }).click();
  const sheet = page.locator("#dialog");
  await sheet.getByRole("checkbox", { name: new RegExp(lonora.name) }).click();
  const put = page.waitForRequest(
    (request) =>
      request.method() === "PUT" &&
      new URL(request.url()).pathname === `/api/groups/${data.group.id}`,
  );
  await sheet.getByRole("button", { name: "Add", exact: true }).click();
  const body = (await put).postDataJSON();
  expect(body.version).toBe(data.group.version);
  expect(body.payload.member_ids).toEqual([data.trader.id, data.research.id, lonora.id]);
  expect(body.payload).toMatchObject({ purpose: "Gold research", lead_agent_id: data.research.id });
  await expect(main.locator(".row", { hasText: lonora.name })).toBeVisible();
  await expect(main.locator(".hero p")).toHaveText("3 agents");
});

test("the recovery page shows the broker session's real outage", async ({ page }) => {
  fixture({ action: "degrade", account: data.account });
  await page.goto(`/app/recovery?account=${data.account}`);
  const main = page.locator("main");
  await expect(main.locator(".hero h2")).toHaveText("The broker connection dropped");
  await expect(main).toContainText("Execution state");
  await expect(main).toContainText("Paused for now");
  await main.getByRole("button", { name: "State details", exact: true }).click();
  await expect(page.locator("#dialog")).toContainText("broker_unreachable");
});

test("the avatar pencil on the agent and identity pages saves a Lonora shape", async ({ page }) => {
  for (const path of [`/app/agent/${data.trader.id}`, `/app/identity/${data.trader.id}`]) {
    await page.goto(path);
    await page.locator("main .pencil").click();
    const studio = page.getByTestId("avatar-studio");
    await expect(studio.locator("[data-face-option]")).toHaveCount(16);
    const face = path.includes("identity") ? "face-happy" : "face-wink";
    await studio.locator(`[data-face-option="${face}"]`).click();
    const patch = page.waitForRequest(
      (request) =>
        request.method() === "PATCH" && request.url().endsWith(`/api/agents/${data.trader.id}`),
    );
    await studio.getByTestId("avatar-studio-save").click();
    expect((await patch).postDataJSON()).toMatchObject({ avatar: face });
    await expect(studio).toHaveCount(0);
  }
});

test("after a reload the card reports the newer operation, not an older pending one", async ({
  page,
}) => {
  // The older modify is still pending and its row time keeps moving; the newer one is done.
  fixture({ action: "seed_modifies", account: data.account });
  await page.goto(`/app/trades/${data.trader.id}`);
  const card = page.locator("main [data-position-id]").first();
  await expect(card.locator("[data-operation-status]")).toHaveAttribute(
    "data-operation-status",
    "confirmed",
  );
  await page.reload();
  await expect(card.locator("[data-operation-status]")).toHaveAttribute(
    "data-operation-status",
    "confirmed",
  );
});

test("the card shows the last action: a refused close, then a modify that went through", async ({
  page,
}) => {
  let refuse = true;
  await page.route("**/api/trading/execute", (route) => {
    const body = route.request().postDataJSON();
    if (body.action === "close_position" && refuse) {
      refuse = false;
      return route.fulfill({ status: 409, json: { code: "emergency_stop" } });
    }
    return route.continue();
  });
  await page.goto(`/app/trades/${data.trader.id}`);
  const card = page.locator("main [data-position-id]").first();
  const sheet = page.locator("#dialog");
  await card.getByRole("button", { name: "Close the trade", exact: true }).click();
  await sheet.getByRole("button", { name: "Close the trade", exact: true }).click();
  await expect(card.getByRole("alert")).toBeVisible();
  await card.getByRole("button", { name: "Edit stop and target", exact: true }).click();
  await sheet.getByLabel("Stop loss", { exact: true }).fill("205");
  await sheet.getByRole("button", { name: "Save", exact: true }).click();
  await expect(card.locator("[data-operation-status]")).toHaveAttribute(
    "data-operation-status",
    "confirmed",
  );
  await expect(card.getByRole("alert")).toHaveCount(0);
});

test("the chart sheet follows a new chart on its pair without reopening", async ({ page }) => {
  await page.goto(`/app/${data.trader.id}`);
  await page.getByRole("button", { name: "Chat menu", exact: true }).click();
  await page.locator("#dialog").getByRole("button", { name: "Chart", exact: true }).click();
  const body = page.locator("#dialog .chart-body");
  await expect(body).toBeVisible();
  await expect(body).not.toHaveAttribute("data-chart-id", /.+/);
  const csrf = data.cookies.find((cookie) => cookie.name === "lonora_csrf").value;
  const created = await page.request.post("/api/charts", {
    headers: { "X-CSRF-Token": csrf },
    data: {
      agent_id: data.trader.id,
      thread_id: null,
      payload: {
        account_id: data.account,
        symbol: data.symbol,
        timeframe: "15m",
        indicators: [],
        annotations: [],
      },
    },
  });
  expect(created.ok()).toBeTruthy();
  const chart = await created.json();
  await expect(body).toHaveAttribute("data-chart-id", chart.id);
  await page.request.delete(`/api/charts/${chart.id}`, { headers: { "X-CSRF-Token": csrf } });
});

test("a streamed scene update re-reads only that scene; a chart moved off the pair is dropped", async ({
  page,
}) => {
  const csrf = data.cookies.find((cookie) => cookie.name === "lonora_csrf").value;
  const created = await page.request.post("/api/charts", {
    headers: { "X-CSRF-Token": csrf },
    data: {
      agent_id: data.trader.id,
      thread_id: null,
      payload: {
        account_id: data.account,
        symbol: data.symbol,
        timeframe: "15m",
        indicators: [],
        annotations: [],
      },
    },
  });
  expect(created.ok()).toBeTruthy();
  const chart = await created.json();
  await page.goto(`/app/${data.trader.id}`);
  // The menu takes the agent the workspace shows: wait for the trader, not the first paint.
  await expect(
    page.getByRole("region", { name: "Workspace" }).getByRole("button", { name: data.trader.name }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Chat menu", exact: true }).click();
  await page.locator("#dialog").getByRole("button", { name: "Chart", exact: true }).click();
  const body = page.locator("#dialog .chart-body");
  await expect(body).toHaveAttribute("data-chart-id", chart.id);
  await body.getByRole("tab", { name: "15m" }).click();
  await expect(body.locator("svg.chart")).toBeVisible();
  const lists = [];
  const candles = [];
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (request.method() === "GET" && path === "/api/charts") lists.push(path);
    if (path === "/api/market/candles") candles.push(path);
  });
  const scene = page.waitForRequest(
    (request) => new URL(request.url()).pathname === `/api/charts/${chart.id}/scene`,
  );
  fixture({
    action: "chart_events",
    events: [
      { id: chart.id, agent_id: data.trader.id },
      // Another agent's chart this sheet never listed.
      { id: crypto.randomUUID(), agent_id: data.research.id },
      { id: chart.id, agent_id: data.trader.id },
    ],
  });
  await scene;
  await page.waitForTimeout(1500);
  expect(lists).toEqual([]);
  expect(candles).toEqual([]);
  // A scene for this agent's chart the sheet has not listed: exactly one re-list.
  const relist = page.waitForRequest(
    (request) => request.method() === "GET" && new URL(request.url()).pathname === "/api/charts",
  );
  fixture({
    action: "chart_events",
    events: [{ id: crypto.randomUUID(), agent_id: data.trader.id }],
  });
  await relist;
  await page.waitForTimeout(1500);
  expect(lists.length).toBe(1);
  await expect(body).toHaveAttribute("data-chart-id", chart.id);
  fixture({ action: "move_chart", chart: chart.id, to: "EURUSD" });
  await expect(body).not.toHaveAttribute("data-chart-id", /.+/);
  expect(lists.length).toBe(2);
  await page.request.delete(`/api/charts/${chart.id}`, { headers: { "X-CSRF-Token": csrf } });
});

test("after a failed chart list, the agent's next scene update lists again", async ({ page }) => {
  const csrf = data.cookies.find((cookie) => cookie.name === "lonora_csrf").value;
  const created = await page.request.post("/api/charts", {
    headers: { "X-CSRF-Token": csrf },
    data: {
      agent_id: data.trader.id,
      thread_id: null,
      payload: {
        account_id: data.account,
        symbol: data.symbol,
        timeframe: "15m",
        indicators: [],
        annotations: [],
      },
    },
  });
  expect(created.ok()).toBeTruthy();
  const chart = await created.json();
  // The sheet's first list fails once; every later request reaches the server.
  let failed = false;
  await page.route(
    (url) => url.pathname === "/api/charts" && url.searchParams.has("agent_id"),
    (route) => {
      if (failed) return route.continue();
      failed = true;
      return route.fulfill({ status: 503, json: { detail: "unavailable" } });
    },
  );
  await page.goto(`/app/${data.trader.id}`);
  await expect(
    page.getByRole("region", { name: "Workspace" }).getByRole("button", { name: data.trader.name }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Chat menu", exact: true }).click();
  await page.locator("#dialog").getByRole("button", { name: "Chart", exact: true }).click();
  const body = page.locator("#dialog .chart-body");
  await expect(body).toBeVisible();
  await expect.poll(() => failed).toBe(true);
  await expect(body).not.toHaveAttribute("data-chart-id", /.+/);
  fixture({ action: "chart_events", events: [{ id: chart.id, agent_id: data.trader.id }] });
  await expect(body).toHaveAttribute("data-chart-id", chart.id);
  await page.request.delete(`/api/charts/${chart.id}`, { headers: { "X-CSRF-Token": csrf } });
});

test("a broker outage: the heads-up and the updates list open the recovery page", async ({
  page,
}) => {
  await page.goto("/app");
  await expect(page.locator(".desktop-list")).toBeVisible();
  fixture({ action: "degrade", account: data.account });
  const headsUp = page.locator("#headsup");
  const open = headsUp.getByRole("button", { name: "Outage and recovery", exact: true });
  await expect(open).toBeVisible({ timeout: 15000 });
  await open.click();
  await expect(page).toHaveURL(
    new RegExp(`/app/recovery\\?account=${encodeURIComponent(data.account)}$`),
  );
  await expect(page.locator("main .hero h2")).toHaveText("The broker connection dropped");
  // The updates page's notification row opens its details, and they open the same page.
  await page.goto("/app/updates");
  await page
    .locator("main [data-attention-id]", { hasText: "Broker connection needs review" })
    .first()
    .click();
  await page.getByRole("button", { name: "Review the connection", exact: true }).click();
  await expect(page).toHaveURL(
    new RegExp(`/app/recovery\\?account=${encodeURIComponent(data.account)}$`),
  );
});

test("desktop: the agent page sits in the 720px column, centred", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/app/agent/${data.trader.id}`);
  const column = page.locator("main > .ag-scope");
  await expect(column.locator(".hero h2")).toHaveText(data.trader.name);
  const box = await column.boundingBox();
  const main = await page.locator("main").boundingBox();
  expect(box.width).toBeLessThanOrEqual(720);
  const left = box.x - main.x;
  const right = main.x + main.width - (box.x + box.width);
  expect(Math.abs(left - right)).toBeLessThanOrEqual(2);
});

test("the agent page's rows open T7's pages filtered to that agent", async ({ page }) => {
  const main = page.locator("main");
  const rows = [
    ["Knowledge", "knowledge", `Knowledge of ${data.trader.name}`],
    ["Skills", "skills", `Skills of ${data.trader.name}`],
    ["Goals", "goals", null],
    ["Scheduled tasks", "routines", "Schedule a task"],
    ["Files", "artifacts", `Files of ${data.trader.name}`],
  ];
  for (const [label, path, text] of rows) {
    await page.goto(`/app/agent/${data.trader.id}`);
    await main.getByRole("button", { name: label, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/app/${path}\\?agent=${data.trader.id}$`));
    await expect(main.locator(".domain-page")).toBeVisible();
    await expect(main).not.toContainText("Page not found");
    if (text) await expect(main).toContainText(text);
  }
});

test("identity: the agent's instructions are edited on its identity form", async ({ page }) => {
  await page.goto(`/app/identity/${data.research.id}`);
  const main = page.locator("main");
  const save = page.waitForRequest(
    (request) =>
      request.method() === "PATCH" && request.url().endsWith(`/api/agents/${data.research.id}`),
  );
  await main.getByLabel("Instructions", { exact: true }).fill("Cite every source.");
  await main.getByRole("button", { name: "Save", exact: true }).click();
  expect((await save).postDataJSON()).toEqual({
    name: data.research.name,
    description: "Reads",
    instructions: "Cite every source.",
  });
});

test("the group page renames the group and removes a member; a removed coordinator is cleared", async ({
  page,
}) => {
  await page.goto(`/app/group/${data.group.id}`);
  const main = page.locator("main");
  await main.getByRole("button", { name: "Edit the group", exact: true }).click();
  const sheet = page.locator("#dialog");
  await sheet.getByLabel("Group name", { exact: true }).fill("Gold desk");
  await sheet.getByRole("checkbox", { name: new RegExp(data.research.name) }).click();
  const put = page.waitForRequest(
    (request) =>
      request.method() === "PUT" &&
      new URL(request.url()).pathname === `/api/groups/${data.group.id}`,
  );
  await sheet.getByRole("button", { name: "Save", exact: true }).click();
  const body = (await put).postDataJSON();
  expect(body.version).toBe(data.group.version);
  expect(body.payload).toMatchObject({
    name: "Gold desk",
    member_ids: [data.trader.id],
    lead_agent_id: null,
    purpose: "Gold research",
  });
  await expect(main.locator(".hero h2")).toHaveText("Gold desk");
  await expect(main.locator(".hero p")).toHaveText("one agent");
});
