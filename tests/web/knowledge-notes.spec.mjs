// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: Playwright runs directly without Turborepo caching.
/* Mandate 13.1: a knowledge note saves without the semantic-memory setting. With no embedding
   model configured, the note is kept and found by its words; embeddings only re-rank. */
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
    const call = async (method, path, data) => {
      const response = await context.request.fetch(`/api${path}`, { method, data, headers });
      expect(response.ok(), `${method} ${path}`).toBeTruthy();
      return response.json();
    };
    // No embedding model: the default of a fresh install.
    await call("PUT", "/memory/semantic/config", { enabled: false, model: null });
    const prefix = `Notes ${randomUUID().slice(0, 8)}`;
    const agent = await call("POST", "/agents/create", {
      template: "general",
      name: prefix,
      responsibility: "Keeps notes",
    });
    await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
    try {
      await use({ agent, prefix, call });
    } finally {
      await context.request.delete(`/api/agents/${agent.id}`, { headers });
    }
  },
});

test("a knowledge note saves with no embedding model configured", async ({ page, owner }) => {
  const { agent, prefix, call } = owner;
  await page.goto(`/app/knowledge-edit?agent=${agent.id}`);
  const form = page.locator('form[data-form="knowledge"]');
  await form.getByLabel("Title", { exact: true }).fill(`${prefix} rule`);
  await form.getByLabel("Content", { exact: true }).fill("Scale into gold after the London open.");
  await form.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/app/knowledge\\?agent=${agent.id}`));
  await expect(page.getByRole("button", { name: new RegExp(`${prefix} rule`) })).toBeVisible();

  // The memory page's own note form no longer waits for the semantic setting either.
  await page.goto("/app/memory");
  await page.getByRole("combobox", { name: "Agent" }).selectOption({ label: prefix });
  await page.getByRole("button", { name: "Long-term memory", exact: true }).click();
  await page.getByText("Semantic memory · optional", { exact: true }).click();
  await page.getByLabel("Knowledge note", { exact: true }).fill("Avoid trading the NFP minute.");
  const button = page.getByRole("button", { name: "Index note", exact: true });
  await expect(button).toBeEnabled();
  const posted = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname.endsWith(`/agents/${agent.id}/memory/semantic`),
  );
  await button.click();
  expect((await posted).status()).toBe(201);
  const items = await call("GET", `/agents/${agent.id}/knowledge`);
  expect(items.filter((item) => item.type === "note")).toHaveLength(2);
});
