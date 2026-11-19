import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

// The Execution Receipt (mandate 10.3, 11.2): one card per broker-confirmed operation, with
// the broker's facts and the agent's reason labelled as the agent's words. A confirmed
// operation is shown once: as its receipt, never also as an order line.
const copy = {
  ar: {
    kicker: "إيصال التنفيذ",
    words: "بكلمات الوكيل",
    confirmed: "أكّده الوسيط · جارٍ التحقق من حالة الحساب…",
    verified: "أكّده الوسيط · تم التحقق من حالة الحساب",
    price: "سعر التنفيذ",
  },
  en: {
    kicker: "Execution receipt",
    words: "In the agent's words",
    confirmed: "Confirmed by the broker · Checking the account state…",
    verified: "Confirmed by the broker · Account state verified",
    price: "Fill price",
  },
};

for (const locale of ["ar", "en"])
  test(`${locale}: a confirmed operation is one Execution Receipt with the broker's facts`, async ({
    page,
    context,
  }) => {
    const text = copy[locale];
    const fixture = JSON.parse(
      execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
        input: JSON.stringify({ action: "init" }),
        encoding: "utf8",
      }),
    );
    await context.addCookies(
      fixture.cookies.map((cookie) => ({
        ...cookie,
        url: test.info().project.use.baseURL,
        httpOnly: cookie.name === "lonora_session",
        sameSite: "Strict",
      })),
    );
    const headers = {
      "X-CSRF-Token": fixture.cookies.find((row) => row.name === "lonora_csrf").value,
    };
    const agent = await (
      await context.request.post("/api/agents", {
        headers,
        data: {
          name: `Receipt ${randomUUID().slice(0, 6)}`,
          trading_account_id: fixture.account,
          trading_symbol: fixture.symbol,
        },
      })
    ).json();
    const thread = await (
      await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
    ).json();
    const fill = {
      operation_id: randomUUID(),
      thread_id: thread.id,
      timeline_seq: 1,
      agent_id: agent.id,
      created_at: "2026-11-12T12:00:00Z",
      kind: "fill",
      action: "buy",
      symbol: "XAUUSD",
      ticket: "50071",
      volume: "0.1",
      price: "2400.55",
      partial: false,
      reason: "Breakout above 2,400 on the London open",
      verification: "pending",
    };
    const modify = {
      ...fill,
      operation_id: randomUUID(),
      timeline_seq: 2,
      kind: "modify",
      action: "modify_position",
      volume: null,
      price: null,
      stop_loss: "2400.55",
      take_profit: null,
      reason: null,
      verification: "verified",
    };
    // The journal still lists the confirmed fill: it must not draw a second line for it.
    const journal = {
      operation_id: fill.operation_id,
      account_id: fixture.account,
      status: "confirmed",
      request: { action: "buy", symbol: "XAUUSD", volume: "0.1" },
      result: { status: "confirmed", broker_id: "50071", details: { price: "2400.55" } },
      submitted_at: fill.created_at,
      updated_at: fill.created_at,
      thread_id: thread.id,
      timeline_seq: 1,
    };
    await page.route("**/api/trading/receipts?*", (route) =>
      route.fulfill({ json: [fill, modify] }),
    );
    await page.route("**/api/trading/journal?*", (route) => route.fulfill({ json: [journal] }));
    try {
      await page.addInitScript((value) => localStorage.setItem("lonora.locale", value), locale);
      await page.goto(`/app/${agent.id}`);
      const card = page.locator(`[data-execution-receipt="${fill.operation_id}"]`);
      await expect(card.getByText(text.kicker)).toBeVisible();
      await expect(card.getByText("50071", { exact: true })).toBeVisible();
      await expect(card.getByText("2400.55", { exact: true })).toBeVisible();
      await expect(card.getByText(text.price, { exact: true })).toBeVisible();
      await expect(card.locator("[data-receipt-status]")).toHaveText(text.confirmed);
      await expect(card.getByText(text.words, { exact: true })).toBeVisible();
      await expect(card.locator("[data-receipt-reason] p")).toHaveText(fill.reason);
      const changed = page.locator(`[data-execution-receipt="${modify.operation_id}"]`);
      await expect(changed).toHaveAttribute("data-receipt-kind", "modify");
      await expect(changed.locator("[data-receipt-status]")).toHaveText(text.verified);
      await expect(changed.locator("[data-receipt-reason]")).toHaveCount(0);
      // One representation: no order line for the confirmed operation.
      await expect(page.locator(`[data-operation-id="${fill.operation_id}"]`)).toHaveCount(0);
      // No raw operation id in the normal view.
      await expect(page.getByText(fill.operation_id)).toHaveCount(0);
      if (locale === "ar") {
        await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
        await card.screenshot({ path: test.info().outputPath("execution-receipt-ar.png") });
      }
    } finally {
      await context.request.delete(`/api/agents/${agent.id}`, { headers });
    }
  });
