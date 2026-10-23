import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

function fixture(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}
async function setup(context, locale = "en") {
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
  const response = await context.request.post("/api/agents", {
    headers,
    data: {
      name: `Bounded permission ${randomUUID()}`,
      trading_account_id: data.account,
      trading_symbol: data.symbol,
    },
  });
  expect(response.status()).toBe(201);
  const agent = await response.json();
  const thread = await (
    await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
  ).json();
  const proposed = await context.request.post(`/api/agents/${agent.id}/account-authorities`, {
    headers,
    data: {
      thread_id: thread.id,
      account_id: data.account,
      symbols: [data.symbol],
      actions: ["buy"],
      maximum_order_volume: "0.10",
      maximum_symbol_volume: "0.30",
      maximum_positions: 3,
      maximum_pending_orders: 1,
      maximum_actions: 5,
      minimum_equity: "8000",
      valid_until: new Date(Date.now() + 3600000).toISOString(),
      allow_manual_positions: false,
    },
  });
  expect(proposed.status()).toBe(201);
  const row = await proposed.json();
  return {
    data,
    agent,
    thread,
    row,
    headers,
    async open(page) {
      await page.goto(`/app/${agent.id}?thread=${thread.id}`);
      await page
        .getByRole("button", {
          name: locale === "ar" ? agent.name : `Agent settings: ${agent.name}`,
          exact: true,
        })
        .click();
      const surface = page.locator("details.tpl-profile-advanced").filter({
        has: page.locator(":scope > summary", {
          hasText: locale === "ar" ? "إدارة الحساب تلقائيًا" : "Automatic account management",
        }),
      });
      await surface.locator(":scope > summary").click();
      return surface;
    },
    async cleanup() {
      await context.request.delete(`/api/agents/${agent.id}`, { headers });
      fixture({ ...data, action: "cleanup" });
    },
  };
}
for (const locale of ["en", "ar"])
  test(`account permission ${locale} is unsigned until device proof and revocation persists`, async ({
    page,
    context,
  }) => {
    const state = await setup(context, locale);
    if (locale === "ar") await page.setViewportSize({ width: 390, height: 844 });
    try {
      const surface = await state.open(page);
      await expect(surface).toContainText(
        locale === "ar" ? "بانتظار توقيعك" : "Waiting for your signature",
      );
      await expect(surface).toContainText(state.data.symbol);
      await surface
        .locator("details > summary")
        .filter({ hasText: locale === "ar" ? "إعدادات متقدمة" : "Advanced:" })
        .click();
      await expect(surface).toContainText(locale === "ar" ? "لا تضمن" : "cannot guarantee");
      await surface
        .getByRole("button", {
          name: locale === "ar" ? "إيقاف الإدارة" : "Stop management",
          exact: true,
        })
        .click();
      await expect(surface).toContainText(locale === "ar" ? "ملغى" : "Revoked");
      const saved = await (
        await context.request.get(`/api/agents/${state.agent.id}/account-authorities`)
      ).json();
      expect(saved.find((row) => row.id === state.row.id).status).toBe("revoked");
      expect((await (await context.request.get("/api/trading/controls")).json()).enabled).toBe(
        false,
      );
    } finally {
      await state.cleanup();
    }
  });
for (const full of [false, true])
  test(`owner signs ${full ? "full" : "bounded"} independent scope through real WebAuthn and can revoke it`, async ({
    page,
    context,
  }) => {
    const state = await setup(context);
    // Fresh authenticator: remove only the disposable owner's prior credentials.
    const devices = await (await context.request.get("/api/auth/devices")).json();
    for (const device of devices) {
      expect(
        (
          await context.request.delete(`/api/auth/devices/${device.id}`, { headers: state.headers })
        ).ok(),
      ).toBeTruthy();
    }
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
      const surface = await state.open(page);
      if (full)
        await surface
          .getByRole("button", { name: "Enable automatic management", exact: true })
          .click();
      else await surface.getByRole("button", { name: "Review and sign", exact: true }).click();
      const review = surface.locator('section[aria-label="Review and sign"]');
      await expect(review).toContainText(full ? "The agent chooses trades" : "0.10");
      const sign = review.getByRole("button", { name: "Review and sign", exact: true });
      if (full) await expect(sign).toBeEnabled();
      else {
        await expect(sign).toBeDisabled();
        await review.getByRole("checkbox").check();
      }
      await sign.click();
      await review
        .getByLabel("Confirm account password", { exact: true })
        .fill("ci-only-owner-password");
      await review.getByRole("button", { name: "Register this device", exact: true }).click();
      await expect(review.getByLabel("Confirm account password", { exact: true })).toHaveCount(0);
      const verification = page.waitForResponse(
        (response) =>
          response.url().endsWith("/account-authorities/verify") &&
          response.request().method() === "POST",
      );
      await sign.click();
      const verified = await verification;
      expect(verified.ok()).toBeTruthy();
      const activated = await verified.json();
      if (full) {
        expect(activated.envelope.schema_version).toBe(2);
        expect(activated.envelope.management_mode).toBe("full");
        expect(activated.valid_until).toBeNull();
        expect(activated.envelope.maximum_order_volume).toBeNull();
      }
      await expect(review).toHaveCount(0);
      await expect(surface.locator(":scope > summary")).toContainText("Active");
      const saved = await (
        await context.request.get(`/api/agents/${state.agent.id}/account-authorities`)
      ).json();
      expect(saved.find((row) => row.id === activated.id).status).toBe("active");
      expect((await (await context.request.get("/api/trading/controls")).json()).enabled).toBe(
        false,
      );
      await surface.getByRole("button", { name: "Stop management", exact: true }).first().click();
      await expect(surface).toContainText("Revoked");
    } finally {
      await state.cleanup();
    }
  });
