// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: Playwright runs directly without Turborepo caching.
/* Mandate P1 / 3.3.2: no cap on the agents in a group. The New Group page let the owner pick
   at most 12 members; every agent can now be picked, and the server accepts them all. */
import { randomUUID } from "node:crypto";
import { test as base, expect } from "@playwright/test";

const test = base.extend({
  owner: async ({ context }, use) => {
    const credentials = {
      email: process.env.LONORA_UI_TEST_EMAIL ?? "ci@example.com",
      password: process.env.LONORA_UI_TEST_PASSWORD ?? "ci-only-owner-password",
    };
    const status = await (await context.request.get("/api/onboarding")).json();
    if (!status.owner_initialized)
      await context.request.post("/api/onboarding", {
        data: {
          ...credentials,
          bootstrap_token: process.env.LONORA_BOOTSTRAP_TOKEN ?? "lonora-ui-bootstrap-ci-only-2026",
        },
      });
    const login = await context.request.post("/api/auth/login", { data: credentials });
    expect(login.status()).toBe(200);
    const headers = { "X-CSRF-Token": (await login.json()).csrf };
    const prefix = `Team ${randomUUID().slice(0, 6)}`;
    const agents = [];
    for (let index = 0; index < 13; index += 1) {
      const response = await context.request.post("/api/agents/create", {
        data: { template: "general", name: `${prefix} ${index}`, responsibility: "Desk" },
        headers,
      });
      expect(response.ok()).toBeTruthy();
      agents.push(await response.json());
    }
    await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
    const groups = [];
    try {
      await use({ agents, prefix, groups });
    } finally {
      for (const group of groups) await context.request.delete(`/api/groups/${group}`, { headers });
      for (const agent of agents)
        await context.request.delete(`/api/agents/${agent.id}`, { headers });
    }
  },
});

test("a new group takes more than twelve members", async ({ page, owner }) => {
  const { agents, prefix, groups } = owner;
  await page.goto("/app/new-group");
  const main = page.locator("main");
  await main.getByLabel("Group name", { exact: true }).fill(`${prefix} all hands`);
  for (const agent of agents) {
    const member = main.getByRole("switch", { name: agent.name });
    await expect(member).toBeEnabled();
    await member.check();
  }
  const create = page.waitForResponse(
    (response) => new URL(response.url()).pathname === "/api/groups/create",
  );
  await main.getByRole("button", { name: "Create the group", exact: true }).click();
  const response = await create;
  expect(response.status()).toBe(201);
  const group = await response.json();
  groups.push(group.id);
  expect(response.request().postDataJSON().member_ids).toHaveLength(13);
});
