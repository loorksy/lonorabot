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
    row,
    headers,
    async cleanup() {
      await context.request.delete(`/api/agents/${agent.id}`, { headers });
      fixture({ ...data, action: "cleanup" });
    },
  };
}
for (const locale of ["en", "ar"])
  test(`Expo ${locale} independent permission is reviewed and revoked without activating trading`, async ({
    page,
    context,
  }) => {
    const state = await setup(context, locale);
    const title = locale === "ar" ? "إدارة الحساب تلقائيًا" : "Automatic account management";
    const revoke = locale === "ar" ? "إيقاف الإدارة" : "Stop management";
    try {
      await page.goto(`/bot-settings?botId=${state.agent.id}`);
      await page.getByRole("button", { name: title, exact: true }).click();
      await page
        .getByRole("button", {
          name:
            locale === "ar" ? "إعدادات متقدمة: تحديد حدود خاصة" : "Advanced: set specific limits",
          exact: true,
        })
        .click();
      await expect(
        page.getByText(locale === "ar" ? /تضبط هذه الحدود الحجم/ : /These limits control volume/),
      ).toBeVisible();
      await expect(
        page.getByText(locale === "ar" ? /بانتظار توقيعك/ : /Waiting for your signature/),
      ).toBeVisible();
      await page.getByRole("button", { name: revoke, exact: true }).click();
      await expect(page.getByText(locale === "ar" ? /ملغى/ : /Revoked/)).toBeVisible();
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

for (const locale of ["en", "ar"])
  test(`Expo ${locale} prepares full management without numeric forms or granting authority`, async ({
    page,
    context,
  }) => {
    const state = await setup(context, locale);
    try {
      await page.goto(`/bot-settings?botId=${state.agent.id}`);
      await page
        .getByRole("button", {
          name: locale === "ar" ? "إدارة الحساب تلقائيًا" : "Automatic account management",
          exact: true,
        })
        .click();
      const response = page.waitForResponse(
        (r) =>
          r.url().endsWith(`/agents/${state.agent.id}/account-authorities`) &&
          r.request().method() === "POST",
      );
      await page
        .getByRole("button", {
          name: locale === "ar" ? "تفعيل الإدارة التلقائية" : "Enable automatic management",
          exact: true,
        })
        .click();
      const proposed = await response;
      expect(proposed.status()).toBe(201);
      const row = await proposed.json();
      expect(row.envelope.management_mode).toBe("full");
      expect(row.envelope.schema_version).toBe(2);
      expect(row.envelope.symbols).toEqual([state.data.symbol]);
      expect(row.envelope.maximum_actions).toBeNull();
      expect(row.valid_until).toBeNull();
      expect(row.status).toBe("pending");
      await expect(
        page.getByText(
          locale === "ar" ? /يختار الوكيل الصفقات واللوت/ : /The agent chooses trades, lot sizes/,
        ),
      ).toBeVisible();
      await expect(
        page.getByText(locale === "ar" ? /أقصى حجم للأمر/ : /Maximum volume per order/),
      ).toHaveCount(0);
      expect((await (await context.request.get("/api/trading/controls")).json()).enabled).toBe(
        false,
      );
    } finally {
      await state.cleanup();
    }
  });
