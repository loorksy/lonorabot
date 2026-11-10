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
      data: {
        reply_language: null,
        name: null,
        address: null,
        reach_me: { channel: "message", quiet_start_hour: null, quiet_end_hour: null },
      },
      headers,
    });
    const agents = await (await context.request.get("/api/agents")).json();
    expect(agents.length).toBeGreaterThan(0);
    await use({ headers, agent: agents[0] });
  },
});

/* «الملف الشخصي» and «الإشعارات والتواصل» (UI phase 5): the shared profile is edited, its change
   is logged with its author and restored; the reach mode is one choice saved on the server. */
test("the owner profile is edited, logged, restored, and the reach mode saved", async ({
  page,
  context,
  owner,
}) => {
  await context.addInitScript(() => {
    localStorage.setItem("lonora.locale", "en");
    localStorage.setItem("lonora.auth.intro-seen", "1");
  });
  await page.goto("/app/owner");
  const name = `Owner ${randomUUID().slice(0, 6)}`;
  await page.getByLabel("Name", { exact: true }).fill(name);
  const line = `- Prefers short answers ${randomUUID().slice(0, 8)}`;
  await page.getByLabel("Preferences", { exact: true }).fill(line);
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect
    .poll(async () => (await (await context.request.get("/api/owner/profile")).json()).name)
    .toBe(name);
  const saved = await (await context.request.get("/api/owner/profile")).json();
  expect(saved.content.trim()).toBe(line);
  const log = page.locator(".pf-log");
  await expect(log.locator(".row").filter({ hasText: "Name" }).first()).toContainText(name);
  // Restoring the text change puts the previous (empty) profile back as a new change.
  const change = log.locator(".row").filter({ hasText: "Preferences" }).first();
  await change.getByRole("button", { name: "Restore", exact: true }).click();
  await expect
    .poll(async () =>
      (await (await context.request.get("/api/owner/profile")).json()).content.trim(),
    )
    .toBe("");
  await page.goto("/app/notify-settings");
  await page.getByRole("radio", { name: /Activity log only/ }).click();
  await expect
    .poll(
      async () => (await (await context.request.get("/api/voice/incoming/policy")).json()).channel,
    )
    .toBe("activity");
  const after = await (await context.request.get("/api/owner/profile")).json();
  expect(after.name).toBe(name);
  expect(owner.agent.id).toBeTruthy();
});

test("the profile page reads right to left in Arabic with the reference's labels", async ({
  page,
  context,
  owner,
}) => {
  await context.addInitScript(() => {
    localStorage.setItem("lonora.locale", "ar");
    localStorage.setItem("lonora.auth.intro-seen", "1");
  });
  await page.goto("/app/owner");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.getByLabel("الاسم", { exact: true })).toBeVisible();
  await expect(page.getByLabel("طريقة المخاطبة", { exact: true })).toBeVisible();
  await expect(page.getByText("سجل التغييرات")).toBeVisible();
  await page.goto("/app/notify-settings");
  await expect(page.getByRole("radio", { name: /رسالة/ })).toHaveAttribute("aria-checked", "true");
  expect(owner.agent.id).toBeTruthy();
});
