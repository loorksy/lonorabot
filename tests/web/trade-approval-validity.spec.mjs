import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

// A Trade Approval card shows the agent's reason labelled as the agent's words and the
// band it stays valid within (mandate 10.3, 10.3.1); a drifted card says nothing was sent.
// v38: the request reads in words with its entry, and an ended card is never folded: it
// keeps its frame and shows its end state inside, with no raw broker code or id.
const copy = {
  ar: {
    kicker: "طلب موافقة",
    title: "شراء 0.1",
    entry: "الدخول",
    market: "بسعر السوق",
    words: "بكلمات الوكيل:",
    band: "صالحة ما دام السعر ضمن",
    drifted: "خرج السعر عن الهامش — لم يُرسل شيء",
    rejected: "مرفوض — لم يُرسل شيء",
    expired: "انتهت صلاحيته",
    renew: "طلب جديد",
    limit: "بيع محدد 0.2",
    brokerWords: "بكلمات الوسيط:",
    failedReason: "لم يُنفَّذ هذا الطلب.",
    brokerPrice: "سعر الوسيط 105.4",
  },
  en: {
    kicker: "Approval request",
    title: "Buy 0.1",
    entry: "Entry",
    market: "At market price",
    words: "In the agent's words:",
    band: "Valid while the price stays within",
    drifted: "Price moved outside the tolerance — nothing was sent",
    rejected: "Rejected — nothing was sent",
    expired: "Expired",
    renew: "New request",
    limit: "Sell limit 0.2",
    brokerWords: "In the broker's words:",
    failedReason: "This request was not carried out.",
    brokerPrice: "Broker price 105.4",
  },
};

for (const locale of ["ar", "en"])
  test(`${locale}: a Trade Approval card shows the agent's reason and its tolerance band`, async ({
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
          name: `Validity ${randomUUID().slice(0, 6)}`,
          trading_account_id: fixture.account,
          trading_symbol: fixture.symbol,
        },
      })
    ).json();
    const thread = await (
      await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
    ).json();
    const base = {
      thread_id: thread.id,
      agent_id: agent.id,
      run_id: "run",
      created_at: "2026-11-12T12:00:00Z",
      requests: [{ action: "buy", symbol: "XAUUSD", volume: "0.1", stop_loss: "95" }],
      results: [],
      expires_at: null,
      tolerance: "1.5",
      reference_price: "101",
    };
    const pending = {
      ...base,
      id: randomUUID(),
      timeline_seq: 1,
      status: "pending",
      reason: "Breakout above 100 on the London open",
    };
    const drifted = { ...base, id: randomUUID(), timeline_seq: 2, status: "drifted", reason: "" };
    const rejected = { ...base, id: randomUUID(), timeline_seq: 3, status: "rejected", reason: "" };
    const expired = {
      ...base,
      id: randomUUID(),
      timeline_seq: 4,
      status: "expired",
      reason: "",
      expires_at: "2026-11-12T12:45:00Z",
    };
    // A pending entry with a broker refusal recorded: the broker's codes and ids stay off it.
    const failed = {
      ...base,
      id: randomUUID(),
      timeline_seq: 5,
      status: "completed",
      reason: "",
      requests: [{ action: "sell_limit", symbol: "XAUUSD", volume: "0.2", price: "105.5" }],
      results: [
        {
          operation_id: randomUUID(),
          status: "failed",
          code: "broker_rejected",
          details: {
            numeric_code: 10019,
            string_code: "TRADE_RETCODE_NO_MONEY",
            message: "No money",
            order_id: "77001",
            deal_id: "77002",
            position_id: "77003",
            price: "105.4",
            description: "Not enough money",
          },
        },
      ],
    };
    // Approved, and completed with every result confirmed: the only success looks (D2).
    const approved = { ...base, id: randomUUID(), timeline_seq: 6, status: "approved", reason: "" };
    const filled = {
      ...base,
      id: randomUUID(),
      timeline_seq: 7,
      status: "completed",
      reason: "",
      results: [{ operation_id: randomUUID(), status: "confirmed", details: {} }],
    };
    // Completed with an outcome the broker never confirmed: a warning, never a success.
    const unsure = {
      ...base,
      id: randomUUID(),
      timeline_seq: 8,
      status: "completed",
      reason: "",
      results: [
        { operation_id: randomUUID(), status: "ambiguous", code: "broker_timeout", details: {} },
      ],
    };
    await page.route("**/api/trading/approvals?*", (route) =>
      route.fulfill({
        json: [pending, drifted, rejected, expired, failed, approved, filled, unsure],
      }),
    );
    try {
      await page.addInitScript((value) => localStorage.setItem("lonora.locale", value), locale);
      await page.goto(`/app/${agent.id}`);
      const card = page.locator(`[data-trade-approval="${pending.id}"]`);
      await expect(card.locator(".mcard-kicker")).toHaveText(`${text.kicker} · XAUUSD`);
      // The request in words, never its raw action id.
      await expect(card.locator(".mcard-request strong")).toHaveText(text.title);
      await expect(card).not.toContainText("buy");
      await expect(card.getByText(text.entry, { exact: true })).toBeVisible();
      await expect(card.getByText(text.market, { exact: true })).toBeVisible();
      await expect(card.locator("[data-trade-reason] b")).toHaveText(text.words);
      await expect(card.locator("[data-trade-reason] bdi")).toHaveText(pending.reason);
      await expect(card.getByText(text.band, { exact: true })).toBeVisible();
      await expect(card.getByText("101 ± 1.5", { exact: true })).toBeVisible();
      const ended = page.locator(`[data-trade-approval="${drifted.id}"]`);
      await expect(ended).toHaveAttribute("data-trade-status", "drifted");
      await expect(ended.getByText(text.drifted, { exact: true })).toBeVisible();
      await expect(ended.getByRole("button", { name: /Approve|موافقة/ })).toHaveCount(0);
      // Never folded (10.2.2): the ended card keeps its frame, request and facts.
      await expect(ended.locator(".mcard-kicker")).toHaveText(`${text.kicker} · XAUUSD`);
      await expect(ended.locator(".mcard-request strong")).toHaveText(text.title);
      await expect(ended.getByText(text.band, { exact: true })).toBeVisible();
      await expect(page.locator(".msg.k-line")).toHaveCount(0);
      const width = async (id) =>
        (
          await page
            .locator(".msg", { has: page.locator(`[data-trade-approval="${id}"]`) })
            .locator(".msg-line")
            .boundingBox()
        ).width;
      expect(await width(drifted.id)).toBe(await width(pending.id));
      const no = page.locator(`[data-trade-approval="${rejected.id}"]`);
      await expect(no.getByText(text.rejected, { exact: true })).toBeVisible();
      await expect(no.locator(".mcard-request strong")).toHaveText(text.title);
      // A stored card that expired: the shared text, and «طلب جديد» inside its frame.
      const old = page.locator(`[data-trade-approval="${expired.id}"]`);
      await expect(old.getByText(text.expired, { exact: true })).toBeVisible();
      await expect(old.getByRole("button", { name: text.renew, exact: true })).toBeVisible();
      // A pending entry shows its price; a broker refusal shows its words, not its codes.
      const refused = page.locator(`[data-trade-approval="${failed.id}"]`);
      await expect(refused.locator(".mcard-request strong")).toHaveText(text.limit);
      await expect(refused.getByText("105.5", { exact: true })).toBeVisible();
      await expect(refused.locator('[data-trade-result="failed"]')).toContainText(
        "Not enough money",
      );
      for (const raw of ["TRADE_RETCODE_NO_MONEY", "10019", "No money", "77001", "77002", "77003"])
        await expect(refused).not.toContainText(raw);
      // The broker's own sentence is labelled as its words, after our localized reason (D10).
      const words = refused.locator("[data-trade-broker-words]");
      await expect(words.locator("b")).toHaveText(text.brokerWords);
      await expect(words.locator("bdi")).toHaveText("Not enough money");
      const resultText = await refused.locator('[data-trade-result="failed"]').innerText();
      expect(resultText.indexOf(text.brokerWords)).toBeGreaterThan(0);
      // A code no catalog explains reads the shared fallback, as on Mobile, never «try
      // again» on a decided card; the broker's price is labelled, never a bare number.
      expect(resultText).toContain(text.failedReason);
      expect(resultText).toContain(text.brokerPrice);
      expect(resultText.indexOf(text.failedReason)).toBeLessThan(
        resultText.indexOf(text.brokerWords),
      );
      // A completed card whose broker refused it never reads as a success (0.4, D2): no
      // success tint and no check mark beside «نتيجة الوسيط».
      const tone = (row) =>
        page.locator(`[data-trade-approval="${row.id}"] [data-trade-status-tone]`);
      const check = '[data-trade-status-tone] path[d="M5 12l4 4L19 6"]';
      await expect(tone(failed)).toHaveAttribute("data-trade-status-tone", "plain");
      await expect(tone(failed)).not.toHaveClass(/\bok\b/);
      await expect(refused.locator(check)).toHaveCount(0);
      // The success look is kept for a fill the broker confirmed; an approval still awaiting
      // the broker's result waits; drift and an unconfirmed outcome warn; a rejection is plain.
      for (const [row, expected] of [
        [approved, "wait"],
        [filled, "ok"],
        [drifted, "warn"],
        [unsure, "warn"],
        [rejected, "plain"],
      ]) {
        await expect(tone(row)).toHaveAttribute("data-trade-status-tone", expected);
        await expect(tone(row)).toHaveClass(
          expected === "plain" ? /^od-ev$/ : new RegExp(`\\b${expected}\\b`),
        );
      }
      await expect(page.locator(`[data-trade-approval="${filled.id}"] ${check}`)).toHaveCount(1);
      await expect(page.locator(`[data-trade-approval="${unsure.id}"] ${check}`)).toHaveCount(0);
      await expect(page.locator(`[data-trade-approval="${approved.id}"] ${check}`)).toHaveCount(0);
      // As wide as every other fixed card (v38 k-oa).
      await expect(page.locator(".msg.k-oa", { has: card })).toHaveCount(1);
      if (locale === "ar") {
        await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
        await card.screenshot({ path: test.info().outputPath("trade-approval-validity-ar.png") });
      }
    } finally {
      await context.request.delete(`/api/agents/${agent.id}`, { headers });
    }
  });
