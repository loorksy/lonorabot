import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "../ui-test.mjs";

// The Execution Receipt (mandate 10.3, 11.2): one card per broker-confirmed operation, with
// the broker's facts as label/value rows and the agent's reason labelled as the agent's words.
// The chat draws no order line for any operation (v38, as on Web). Mobile draws the same
// record natively.
const copy = {
  ar: {
    kicker: "إيصال التنفيذ",
    words: "بكلمات الوكيل",
    confirmed: "أكّده الوسيط · جارٍ التحقق من حالة الحساب…",
    verified: "أكّده الوسيط · تم التحقق من حالة الحساب",
    price: "سعر التنفيذ",
    ticket: "تذكرة الوسيط",
    mine: "بيع · أمرك",
  },
  en: {
    kicker: "Execution receipt",
    words: "In the agent's words",
    confirmed: "Confirmed by the broker · Checking the account state…",
    verified: "Confirmed by the broker · Account state verified",
    price: "Fill price",
    ticket: "Broker ticket",
    mine: "Sell · your order",
  },
};

for (const locale of ["ar", "en"])
  test(`Expo ${locale}: a confirmed operation is one Execution Receipt with the broker's facts`, async ({
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
    // The journal lists the confirmed fill and an operation the broker refused: the chat
    // draws a line for neither; it does not even read the journal.
    const journal = [
      {
        operation_id: fill.operation_id,
        account_id: fixture.account,
        status: "confirmed",
        request: { action: "buy", symbol: "XAUUSD", volume: "0.1" },
        result: { status: "confirmed", broker_id: "50071", details: { price: "2400.55" } },
        submitted_at: fill.created_at,
        updated_at: fill.created_at,
        thread_id: thread.id,
        timeline_seq: 1,
      },
      {
        operation_id: randomUUID(),
        account_id: fixture.account,
        status: "failed",
        request: { action: "sell", symbol: "XAUUSD", volume: "0.3" },
        result: { status: "failed", code: "broker_rejected", details: {} },
        submitted_at: fill.created_at,
        updated_at: fill.created_at,
        thread_id: thread.id,
        timeline_seq: 2,
      },
    ];
    await page.route("**/api/trading/receipts?*", (route) =>
      route.fulfill({ json: [fill, modify, mine] }),
    );
    const journalReads = [];
    await page.route("**/api/trading/journal?*", (route) => {
      journalReads.push(route.request().url());
      return route.fulfill({ json: journal });
    });
    cleanup(async () => {
      await context.request.delete(`/api/agents/${agent.id}`, { headers });
    });

    await page.addInitScript((value) => localStorage.setItem("lonora.locale", value), locale);
    await page.setViewportSize({ width: 320, height: 844 });
    await page.goto(`/thread?id=${thread.id}`);
    const cards = page.getByTestId("execution-receipt");
    await expect(cards).toHaveCount(3);
    // No order line in the chat, for the confirmed operation or any other (v38, D4).
    await expect(page.getByText(/0\.3/)).toHaveCount(0);
    expect(journalReads).toEqual([]);
    // The list is inverted: pick each card by what it holds, not by its place.
    const card = cards.filter({ hasText: fill.reason });
    const changed = cards.filter({ hasNotText: fill.reason }).filter({ hasNotText: mine.ticket });
    const own = cards.filter({ hasText: mine.ticket });
    const longTicket = own.getByText(mine.ticket, { exact: true });
    await expect(longTicket).toBeVisible();
    const cardBox = await own.boundingBox();
    const ticketBox = await longTicket.boundingBox();
    expect(ticketBox.x).toBeGreaterThanOrEqual(cardBox.x);
    expect(ticketBox.x + ticketBox.width).toBeLessThanOrEqual(cardBox.x + cardBox.width);
    await expect(card.getByText(text.kicker)).toBeVisible();
    // The kicker carries its check, and a receipt still verifying waits with the hourglass
    // (never the calendar), as the web card's (v38).
    await expect(card.locator('path[d^="M5 12l4 4L19 6"]')).toHaveCount(1);
    await expect(card.locator('path[d^="M6 2h12M6 22h12"]')).toHaveCount(1);
    await expect(card.locator('path[d^="M7 3v3M17 3v3"]')).toHaveCount(0);
    await expect(card.getByText("50071", { exact: true })).toBeVisible();
    await expect(card.getByText("2400.55", { exact: true })).toBeVisible();
    await expect(card.getByText(text.price, { exact: true })).toBeVisible();
    await expect(card.getByText(text.ticket, { exact: true })).toBeVisible();
    // The facts are label/value rows, as the Trade Approval's (v38 `.oa-dl`, D7): each label
    // shares its row with its value.
    const row = (label, value) =>
      card
        .locator("div")
        .filter({ has: page.getByText(label, { exact: true }) })
        .filter({ has: page.getByText(value, { exact: true }) })
        .last();
    for (const [label, value] of [
      [text.ticket, "50071"],
      [text.price, "2400.55"],
    ]) {
      const cells = row(label, value);
      await expect(cells).toBeVisible();
      // Side by side on one row, never a label stacked above its value.
      const [a, b] = await Promise.all([
        cells.getByText(label, { exact: true }).boundingBox(),
        cells.getByText(value, { exact: true }).boundingBox(),
      ]);
      expect(Math.abs(a.y + a.height / 2 - (b.y + b.height / 2))).toBeLessThan(8);
      expect(Math.abs(a.x - b.x)).toBeGreaterThan(40);
    }
    await expect(card.getByTestId("execution-receipt-status")).toHaveText(text.confirmed);
    await expect(card.getByText(text.words, { exact: true })).toBeVisible();
    await expect(card.getByText(fill.reason, { exact: true })).toBeVisible();
    await expect(changed.getByTestId("execution-receipt-status")).toHaveText(text.verified);
    await expect(changed.getByTestId("execution-receipt-reason")).toHaveCount(0);
    await expect(own.getByText(text.mine, { exact: true })).toBeVisible();
    await expect(own.getByTestId("execution-receipt-reason")).toHaveCount(0);
    await expect(page.getByText(fill.operation_id)).toHaveCount(0);
    if (locale === "ar")
      await page.screenshot({ path: test.info().outputPath("execution-receipt-native-ar.png") });
  });
