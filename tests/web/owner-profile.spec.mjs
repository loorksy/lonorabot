// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: Playwright runs directly without Turborepo caching.
import { randomUUID } from "node:crypto";
import { test as base, expect } from "@playwright/test";

let authenticatedSession;

const test = base.extend({
  owner: async ({ context }, use) => {
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
    const profile = await (await context.request.get("/api/owner/profile")).json();
    // Start from an empty profile and the default reach-me preference.
    await context.request.put("/api/owner/profile", {
      data: { content: "", version: profile.version },
      headers,
    });
    await context.request.put("/api/owner/preferences", {
      data: { reply_language: null, reach_me: { channel: "message" } },
      headers,
    });
    const agents = await (await context.request.get("/api/agents")).json();
    expect(agents.length).toBeGreaterThan(0);
    await use({ headers, agent: agents[0] });
  },
});

async function openProfile(page, agent) {
  await page.goto(`/app/${agent.id}`);
  await page.locator(".tpl-chat-identity").click();
  const panel = page.getByTestId("side-panel");
  await panel.getByRole("button", { name: /^(Knowledge|المعرفة)$/ }).click();
  return panel;
}

test("the owner profile is edited, attributed, restored and its reach-me saved", async ({
  page,
  context,
  owner,
}) => {
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const panel = await openProfile(page, owner.agent);
  await expect(panel.getByRole("button", { name: "About you", exact: true })).toHaveClass(
    /selected/,
  );
  const profile = panel.getByRole("region", { name: "About you" });
  await expect(
    profile.getByText("Every agent reads this profile.", { exact: false }),
  ).toBeVisible();
  const text = profile.getByLabel("What agents know about you");
  const preference = `- Short replies ${randomUUID().slice(0, 8)}`;
  await text.fill(preference);
  await profile.getByRole("button", { name: "Save", exact: true }).click();
  await expect(profile.getByRole("status")).toHaveText("Saved");
  const history = panel.getByRole("region", { name: "Changes" });
  const change = history.locator("li", { hasText: preference }).first();
  await expect(change).toContainText("You");
  await expect(change).toContainText("Added:");
  await change.getByRole("button", { name: "Restore the text before this change" }).click();
  await expect(history.getByRole("status")).toHaveText("Restored");
  await expect(text).toHaveValue("");
  const restored = await (await context.request.get("/api/owner/profile")).json();
  expect(restored.content).toBe("");

  // One reach-me preference, the same one agents and the call gate read.
  const reach = panel.getByRole("form", { name: "How to reach you" });
  await reach.getByRole("radio", { name: /Activity only/ }).check();
  await reach.getByLabel("Reply language").selectOption("ar");
  await reach.getByRole("button", { name: "Save", exact: true }).click();
  await expect(reach.getByRole("status")).toHaveText("Saved");
  const policy = await (await context.request.get("/api/voice/incoming/policy")).json();
  expect(policy.channel).toBe("activity");
  expect(policy.enabled).toBe(false);
  const saved = await (await context.request.get("/api/owner/profile")).json();
  expect(saved.reply_language).toBe("ar");
  await expect(history.locator("li", { hasText: "How to reach you" }).first()).toContainText(
    "Message me → Activity only",
  );
});

test("the profile reads right to left in Arabic with shared labels", async ({
  page,
  context,
  owner,
}) => {
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "ar"));
  const panel = await openProfile(page, owner.agent);
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  const profile = panel.getByRole("region", { name: "عنك" });
  await expect(profile.getByLabel("ما يعرفه الوكلاء عنك")).toBeVisible();
  const reach = panel.getByRole("form", { name: "كيف نتواصل معك" });
  await expect(reach.getByRole("radio", { name: /راسلني/ })).toBeChecked();
  await expect(reach.getByText("يصل داخل لونورا حاليًا", { exact: false })).toBeVisible();
});
