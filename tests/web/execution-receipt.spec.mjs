import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "../ui-test.mjs";

// The Execution Receipt (mandate 10.3, 11.2): one card per broker-confirmed operation, with
// the broker's facts and the agent's reason labelled as the agent's words. An operation is
// drawn in the chat only by its fixed cards (v38): never as an order line.
const copy = {
  ar: {
    kicker: "إيصال التنفيذ",
    words: "بكلمات الوكيل:",
    confirmed: "أكّده الوسيط · جارٍ التحقق من حالة الحساب…",
    verified: "أكّده الوسيط · تم التحقق من حالة الحساب",
    price: "سعر التنفيذ",
    ticket: "تذكرة الوسيط",
    mine: "بيع · أمرك",
  },
  en: {
    kicker: "Execution receipt",
    words: "In the agent's words:",
    confirmed: "Confirmed by the broker · Checking the account state…",
    verified: "Confirmed by the broker · Account state verified",
    price: "Fill price",
    ticket: "Broker ticket",
    mine: "Sell · your order",
  },
};

for (const locale of ["ar", "en"])
  test(`${locale}: a confirmed operation is one Execution Receipt with the broker's facts`, async ({
    page,
    context,
    cleanup,
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
    // The owner's own order: no agent, no agent's words, and the receipt says it is yours.
    const mine = {
      ...fill,
      operation_id: randomUUID(),
      timeline_seq: 3,
      agent_id: null,
      action: "sell",
      ticket: "a7a20cc5-3521-4051-ab6f-8d4645b82545",
      reason: null,
      verification: "verified",
    };
    // The journal lists operations that never reached a receipt: the chat draws no line for them.
    const journal = [
      {
        operation_id: randomUUID(),
        account_id: fixture.account,
        status: "failed",
        request: { action: "buy", symbol: "XAUUSD", volume: "0.1" },
        result: { status: "failed", code: "broker_rejected", details: {} },
        submitted_at: fill.created_at,
        updated_at: fill.created_at,
        thread_id: thread.id,
        timeline_seq: 1,
      },
    ];
    await page.route("**/api/trading/receipts?*", (route) =>
      route.fulfill({ json: [fill, modify, mine] }),
    );
    await page.route("**/api/trading/journal?*", (route) => route.fulfill({ json: journal }));
    cleanup(async () => {
      await context.request.delete(`/api/agents/${agent.id}`, { headers });
    });

    await page.addInitScript((value) => localStorage.setItem("lonora.locale", value), locale);
    await page.setViewportSize({ width: 320, height: 844 });
    await page.goto(`/app/${agent.id}`);
    const card = page.locator(`[data-execution-receipt="${fill.operation_id}"]`);
    await expect(card.getByText(text.kicker)).toBeVisible();
    await expect(card.getByText("50071", { exact: true })).toBeVisible();
    await expect(card.getByText("2400.55", { exact: true })).toBeVisible();
    await expect(card.getByText(text.price, { exact: true })).toBeVisible();
    await expect(card.locator("[data-receipt-status]")).toHaveText(text.confirmed);
    await expect(card.getByText(text.ticket, { exact: true })).toBeVisible();
    // The facts are the Trade Approval's label/value rows (v38 oaDL), in the same frame
    // width as every fixed card.
    const rows = card.locator(".oa-dl > div");
    await expect(rows).toHaveCount(3);
    await expect(rows.nth(0).locator("dt")).toHaveText(text.ticket);
    await expect(rows.nth(0).locator("dd")).toHaveText("50071");
    await expect(rows.nth(2).locator("dt")).toHaveText(text.price);
    await expect(rows.nth(2).locator("dd")).toHaveText("2400.55");
    await expect(card.locator(".mcard-facts")).toHaveCount(0);
    await expect(page.locator(".msg.k-oa", { has: card })).toHaveCount(1);
    await expect(card.locator("[data-receipt-reason] b")).toHaveText(text.words);
    await expect(card.locator("[data-receipt-reason] bdi")).toHaveText(fill.reason);
    const changed = page.locator(`[data-execution-receipt="${modify.operation_id}"]`);
    await expect(changed).toHaveAttribute("data-receipt-kind", "modify");
    await expect(changed.locator("[data-receipt-status]")).toHaveText(text.verified);
    await expect(changed.locator("[data-receipt-reason]")).toHaveCount(0);
    const own = page.locator(`[data-execution-receipt="${mine.operation_id}"]`);
    await expect(own.locator(".mcard-request strong")).toHaveText(text.mine);
    const longTicket = own.getByText(mine.ticket, { exact: true });
    await expect(longTicket).toBeVisible();
    const cardBox = await own.boundingBox();
    const ticketBox = await longTicket.boundingBox();
    expect(ticketBox.x).toBeGreaterThanOrEqual(cardBox.x);
    expect(ticketBox.x + ticketBox.width).toBeLessThanOrEqual(cardBox.x + cardBox.width);
    expect(cardBox.x).toBeGreaterThanOrEqual(0);
    expect(cardBox.x + cardBox.width).toBeLessThanOrEqual(320);
    await expect(own.locator("[data-receipt-reason]")).toHaveCount(0);
    // No order line in the chat, for a confirmed operation or any other (v38).
    await expect(page.locator(".od-chat, [data-operation-id]")).toHaveCount(0);
    // No raw operation id in the normal view.
    await expect(page.getByText(fill.operation_id)).toHaveCount(0);
    if (locale === "ar") {
      await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
      await card.screenshot({ path: test.info().outputPath("execution-receipt-ar.png") });
    }
  });
