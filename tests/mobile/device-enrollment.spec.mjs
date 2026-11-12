// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: Playwright runs directly without Turborepo caching.
import { expect, test } from "@playwright/test";

/* A call rings only a device registered with the owner's passkey (voice/incoming.py), so the
   incoming-call settings register this device: the account password, then the passkey
   (virtual WebAuthn on the Expo web build). */
test("Expo call settings register this device with the passkey, in Arabic", async ({
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
  // Fresh authenticator: remove only this owner's prior credentials.
  const forget = async () => {
    for (const device of await (await context.request.get("/api/auth/devices")).json())
      expect(
        (await context.request.delete(`/api/auth/devices/${device.id}`, { headers })).ok(),
      ).toBeTruthy();
  };
  // The owner is shared with other specs: its reach-me setting is put back afterwards.
  const before = await (await context.request.get("/api/voice/incoming/policy")).json();
  try {
    await forget();
    const reset = await context.request.put("/api/owner/preferences", {
      data: { reach_me: { channel: "message" } },
      headers,
    });
    expect(reset.ok()).toBeTruthy();
    const cdp = await context.newCDPSession(page);
    await cdp.send("WebAuthn.enable");
    await cdp.send("WebAuthn.addVirtualAuthenticator", {
      options: {
        protocol: "ctap2",
        transport: "internal",
        hasResidentKey: true,
        hasUserVerification: true,
        isUserVerified: true,
        automaticPresenceSimulation: true,
      },
    });
    await page.goto("/voice");
    await expect(page.getByText("كيف نتواصل معك", { exact: true })).toBeVisible();
    // Without a registered device, calling is not offered.
    await expect(page.getByRole("button", { name: "اتصل بي", exact: true })).toBeDisabled();
    const register = page.getByRole("button", { name: "سجّل هذا الجهاز", exact: true });
    await expect(register).toBeDisabled();
    await page.getByLabel("كلمة مرور الحساب", { exact: true }).fill("ci-only-owner-password");
    const verification = page.waitForResponse(
      (response) =>
        response.url().endsWith("/auth/devices/enrollment/verify") &&
        response.request().method() === "POST",
    );
    await register.click();
    expect((await verification).ok()).toBeTruthy();
    await expect(page.getByText("تم تسجيل هذا الجهاز.", { exact: true })).toBeVisible();
    // The device is there at once: calling can be chosen now.
    await expect(page.getByRole("button", { name: "اتصل بي", exact: true })).toBeEnabled();
    const devices = await (await context.request.get("/api/auth/devices")).json();
    expect(devices.map((device) => device.name)).toEqual(["جهازي"]);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
    ).toBeTruthy();
  } finally {
    await forget();
    const { enabled: _enabled, ...policy } = before;
    const restored = await context.request.put("/api/owner/preferences", {
      data: { reach_me: policy },
      headers,
    });
    expect(restored.ok()).toBeTruthy();
  }
});
