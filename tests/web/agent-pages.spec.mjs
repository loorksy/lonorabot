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
  await expect(main.locator(".wt-row")).toContainText(`${data.symbol} below 200`);
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
  await page.goto(`/app/agent/${data.research.id}`);
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
    supervisor_id: data.research.id,
    supervised_id: data.trader.id,
  });
  await expect(main.locator(".row", { hasText: data.trader.name })).toBeVisible();
  // The supervised agent's page names its supervisor.
  await page.goto(`/app/agent/${data.trader.id}`);
  await expect(main.locator(".sup-line")).toContainText(data.research.name);
  await page.goto(`/app/agent/${data.research.id}`);
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
  await expect(page).toHaveURL(/\/app\/settings\?tab=voice$/);
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
  await expect(sheet.locator("svg.chart rect").first()).toBeVisible();
  expect(await sheet.locator("svg.chart rect").count()).toBeGreaterThan(8);
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
