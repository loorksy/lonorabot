// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: Playwright runs directly without Turborepo caching.
import { expect, test } from "@playwright/test";

test("Expo Arabic reach-me preference is the same one the Web and agents read", async ({
  page,
  context,
}) => {
  const credentials = {
    email: process.env.LONORA_UI_TEST_EMAIL ?? "ci@example.com",
    password: process.env.LONORA_UI_TEST_PASSWORD ?? "ci-only-owner-password",
  };
  if (!(await (await context.request.get("/api/onboarding")).json()).owner_initialized) {
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
  const reset = await context.request.put("/api/owner/preferences", {
    data: { reply_language: null, reach_me: { channel: "message" } },
    headers,
  });
  expect(reset.ok()).toBeTruthy();
  await page.goto("/voice");
  await expect(page.getByText("كيف نتواصل معك", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "✓ راسلني", exact: true })).toBeVisible();
  // Without an enrolled passkey device, calling is not offered.
  await expect(page.getByRole("button", { name: "اتصل بي", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "أرسل لي تنبيهًا", exact: true }).click();
  await page.getByRole("button", { name: "العربية", exact: true }).click();
  await page.getByRole("button", { name: "حفظ", exact: true }).click();
  await expect(page.getByText("تم الحفظ", { exact: true })).toBeVisible();
  const policy = await (await context.request.get("/api/voice/incoming/policy")).json();
  expect(policy).toMatchObject({ channel: "notify", enabled: false });
  const profile = await (await context.request.get("/api/owner/profile")).json();
  expect(profile.reply_language).toBe("ar");
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
  ).toBeTruthy();
});
