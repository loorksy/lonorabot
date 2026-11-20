import { execFileSync } from "node:child_process";
import { expect, test } from "../ui-test.mjs";

/* A call rings only a device registered with the owner's passkey, so the call settings
   register this device: the account password, then the passkey (virtual WebAuthn). */
function fixture(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}
async function setup(context, locale, cleanup) {
  const data = fixture({ action: "init", empty: true });
  await context.addCookies(
    data.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript((value) => {
    localStorage.setItem("lonora.locale", value);
    localStorage.setItem("lonora.auth.intro-seen", "1");
  }, locale);
  const headers = { "X-CSRF-Token": data.cookies.find((row) => row.name === "lonora_csrf").value };
  const forget = async () => {
    for (const device of await (await context.request.get("/api/auth/devices")).json())
      expect(
        (await context.request.delete(`/api/auth/devices/${device.id}`, { headers })).ok(),
      ).toBeTruthy();
  };
  await forget();
  cleanup(async () => {
    await forget();
    fixture({ ...data, action: "cleanup" });
  });
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
    cleanup,
  }) => {
    await setup(context, locale, cleanup);
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
    const words = text[locale];
    await page.goto("/app/notify-settings");
    const register = page.getByRole("button", { name: words.register, exact: true });
    await expect(register).toBeDisabled();
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
    await expect(page.getByRole("radio", { name: new RegExp(words.device) })).toBeVisible();
    await expect(page.getByLabel(words.password, { exact: true })).toHaveValue("");
    await page.getByLabel(words.password, { exact: true }).fill("ci-only-owner-password");
    await register.click();
    await expect(page.getByText(words.already, { exact: true })).toBeVisible();
    const devices = await (await context.request.get("/api/auth/devices")).json();
    expect(devices.map((device) => device.name)).toEqual([words.device]);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
    ).toBeTruthy();
  });

test("a wrong account password registers nothing", async ({ page, context, cleanup }) => {
  await setup(context, "en", cleanup);
  await page.goto("/app/notify-settings");
  await page.getByLabel("Account password", { exact: true }).fill("not-the-password");
  const enrollment = page.waitForResponse(
    (response) =>
      response.url().endsWith("/auth/devices/enrollment") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Register this device", exact: true }).click();
  expect((await enrollment).status()).toBe(401);
  await expect(page).toHaveURL(/\/app\/notify-settings$/);
  expect(await (await context.request.get("/api/auth/devices")).json()).toEqual([]);
});
