import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

/* A call rings only a device registered with the owner's passkey (voice/incoming.py), so the
   call settings register this device: the account password, then the passkey (virtual WebAuthn). */
function fixture(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}
async function setup(context, locale) {
  const data = fixture({ action: "init", empty: true });
  await context.addCookies(
    data.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript((value) => localStorage.setItem("lonora.locale", value), locale);
  const headers = { "X-CSRF-Token": data.cookies.find((row) => row.name === "lonora_csrf").value };
  // Fresh authenticator: remove only the disposable owner's prior credentials.
  const forget = async () => {
    for (const device of await (await context.request.get("/api/auth/devices")).json())
      expect(
        (await context.request.delete(`/api/auth/devices/${device.id}`, { headers })).ok(),
      ).toBeTruthy();
  };
  await forget();
  return {
    async cleanup() {
      await forget();
      fixture({ ...data, action: "cleanup" });
    },
  };
}
const text = {
  ar: {
    password: "كلمة مرور الحساب",
    register: "سجّل هذا الجهاز",
    device: "جهازي",
    registered: "تم تسجيل هذا الجهاز.",
    already: "هذا الجهاز مسجّل من قبل.",
  },
  en: {
    password: "Account password",
    register: "Register this device",
    device: "My device",
    registered: "This device is registered.",
    already: "This device is already registered.",
  },
};
for (const locale of ["ar", "en"])
  test(`call settings register this device with the passkey (${locale})`, async ({
    page,
    context,
  }) => {
    const state = await setup(context, locale);
    if (locale === "ar") await page.setViewportSize({ width: 390, height: 844 });
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
    try {
      const words = text[locale];
      await page.goto("/app/notify-settings");
      const register = page.getByRole("button", { name: words.register, exact: true });
      await expect(register).toBeDisabled();
      // No device yet: nothing to ring.
      await expect(page.getByRole("radio", { name: new RegExp(words.device) })).toHaveCount(0);
      await page.getByLabel(words.password, { exact: true }).fill("ci-only-owner-password");
      const verification = page.waitForResponse(
        (response) =>
          response.url().endsWith("/auth/devices/enrollment/verify") &&
          response.request().method() === "POST",
      );
      await register.click();
      expect((await verification).ok()).toBeTruthy();
      await expect(page.getByText(words.registered, { exact: true })).toBeVisible();
      // The registered device is listed at once as one a call can ring; the password is cleared.
      await expect(page.getByRole("radio", { name: new RegExp(words.device) })).toBeVisible();
      await expect(page.getByLabel(words.password, { exact: true })).toHaveValue("");
      // Again on the same device: its authenticator already holds the excluded credential.
      await page.getByLabel(words.password, { exact: true }).fill("ci-only-owner-password");
      await register.click();
      await expect(page.getByText(words.already, { exact: true })).toBeVisible();
      const devices = await (await context.request.get("/api/auth/devices")).json();
      expect(devices.map((device) => device.name)).toEqual([words.device]);
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
      ).toBeTruthy();
    } finally {
      await state.cleanup();
    }
  });

test("a wrong account password registers nothing", async ({ page, context }) => {
  const state = await setup(context, "en");
  try {
    await page.goto("/app/notify-settings");
    await page.getByLabel("Account password", { exact: true }).fill("not-the-password");
    const enrollment = page.waitForResponse(
      (response) =>
        response.url().endsWith("/auth/devices/enrollment") &&
        response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Register this device", exact: true }).click();
    expect((await enrollment).status()).toBe(401);
    // Still signed in on the same page, and no device was added.
    await expect(page).toHaveURL(/\/app\/notify-settings$/);
    expect(await (await context.request.get("/api/auth/devices")).json()).toEqual([]);
  } finally {
    await state.cleanup();
  }
});
