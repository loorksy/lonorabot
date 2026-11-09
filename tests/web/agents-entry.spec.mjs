import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

/* «إدارة الوكلاء» and «وكيل جديد» (docs/ui-reference/Lonora-Desktop-37.html, phase 2): the
   ghost button of the new-chat sheet and the list menu item open the agents page on real data;
   a new agent is created from a template through POST /api/agents/create (owner decision Q9)
   and, with nothing said yet, sorts below every chat that has a message. */
function seed(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/chat_lists_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}
let cleanup = null;
test.afterEach(async ({ context }) => {
  if (!cleanup) return;
  const { fixture, headers, extra } = cleanup;
  cleanup = null;
  await context.request.delete(`/api/groups/${fixture.group.id}`, { headers });
  for (const id of [...fixture.agents.map((agent) => agent.id), ...extra])
    await context.request.delete(`/api/agents/${id}`, { headers });
});
async function signIn(context, fixture) {
  await context.addCookies(
    fixture.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const headers = {
    "X-CSRF-Token": fixture.cookies.find((cookie) => cookie.name === "lonora_csrf").value,
  };
  cleanup = { fixture, headers, extra: [] };
  return cleanup;
}

test("«إدارة الوكلاء» opens the agents page from the new-chat sheet and the list menu", async ({
  page,
  context,
}) => {
  const fixture = seed({ action: "init" });
  await signIn(context, fixture);
  await page.goto("/app");
  await page.locator('.desktop-list button[aria-label="New chat"]').click();
  const sheet = page.locator("#dialog");
  // The personal agent's role line is the reference's «مساعدك الشخصي» until it has one.
  const agents = await (await context.request.get("/api/agents")).json();
  const personal = agents.find((agent) => agent.role === "personal");
  if (personal && !personal.title && !personal.description)
    await expect(sheet.locator(`[data-new-chat-agent="${personal.id}"]`)).toContainText(
      "Your personal assistant",
    );
  await sheet.getByRole("button", { name: "Manage agents", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/agents$/);
  const main = page.locator("main");
  for (const agent of fixture.agents) await expect(main).toContainText(agent.name);
  await expect(
    main.getByRole("button", { name: new RegExp(fixture.group.payload.name) }),
  ).toContainText("2 agents");
  await expect(main.locator(".status.on").first()).toHaveText("Active");
  await main.getByRole("button", { name: new RegExp(fixture.group.payload.name) }).click();
  await expect(page).toHaveURL(new RegExp(`/app/g/${fixture.group.id}`));

  await page.getByRole("button", { name: "List options", exact: true }).click();
  await page.getByRole("menuitem", { name: "Manage agents" }).click();
  await expect(page).toHaveURL(/\/app\/agents$/);
  await page.getByRole("button", { name: "Create agent", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/new-agent$/);
});

test("«وكيل جديد» persists its template and the new chat sorts below the chats with messages", async ({
  page,
  context,
}) => {
  const fixture = seed({ action: "init" });
  const state = await signIn(context, fixture);
  const posts = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && new URL(request.url()).pathname.startsWith("/api/agents"))
      posts.push(new URL(request.url()).pathname);
  });
  await page.goto("/app/new-agent");
  const main = page.locator("main");
  await main.getByRole("radio", { name: /^Research agent/ }).check();
  await main.getByRole("button", { name: "Next", exact: true }).click();
  await expect(main.locator(".row .value")).toHaveText("Research agent");
  await main
    .getByLabel("Agent name", { exact: true })
    .fill(`Reader ${fixture.group.id.slice(0, 6)}`);
  await main.getByLabel("Description", { exact: true }).fill("Summarises the week's research");
  const creation = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/api/agents/create" &&
      response.request().method() === "POST",
  );
  await main.getByRole("button", { name: "Create the agent", exact: true }).click();
  const response = await creation;
  expect(response.status()).toBe(201);
  expect(response.request().postDataJSON()).toMatchObject({ template: "research" });
  const agent = await response.json();
  state.extra.push(agent.id);
  expect(agent.template).toBe("research");
  expect(posts).toEqual(["/api/agents/create"]);
  await expect(page).toHaveURL(new RegExp(`/app/${agent.id}$`));
  // Nothing said yet: below every seeded chat that has a message (the reference's lastAt).
  await expect(page.locator(`.desktop-list .thread[data-key="agent:${agent.id}"]`)).toBeVisible();
  const keys = await page
    .locator(".desktop-list .thread[data-key]")
    .evaluateAll((rows) => rows.map((row) => row.getAttribute("data-key")));
  const position = keys.indexOf(`agent:${agent.id}`);
  expect(position).toBeGreaterThan(-1);
  for (const seeded of fixture.agents.slice(0, 2))
    expect(keys.indexOf(`agent:${seeded.id}`)).toBeLessThan(position);
});
