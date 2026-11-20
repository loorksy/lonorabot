import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

// A Trade Approval card shows the agent's reason labelled as the agent's words and the
// band it stays valid within (mandate 10.3, 10.3.1); a drifted card says nothing was sent.
const copy = {
  ar: {
    words: "بكلمات الوكيل",
    band: "صالحة ما دام السعر ضمن",
    kicker: "طلب موافقة",
    title: "شراء محدد 0.1",
    price: "الدخول",
    stopLoss: "وقف الخسارة",
    takeProfit: "جني الربح",
    drifted: "خرج السعر عن الهامش — لم يُرسل شيء",
    market: "بسعر السوق",
    marketTitle: "شراء 0.2",
    failedReason: "لم يُنفَّذ هذا الطلب.",
    brokerPrice: "سعر الوسيط: 2360.00",
    brokerWords: "بكلمات الوسيط: Not enough money",
  },
  en: {
    words: "In the agent's words",
    band: "Valid while the price stays within",
    kicker: "Approval request",
    title: "Buy limit 0.1",
    price: "Entry",
    stopLoss: "Stop loss",
    takeProfit: "Take profit",
    drifted: "Price moved outside the tolerance — nothing was sent",
    market: "At market price",
    marketTitle: "Buy 0.2",
    failedReason: "This request was not carried out.",
    brokerPrice: "Broker price: 2360.00",
    brokerWords: "In the broker's words: Not enough money",
  },
};

for (const locale of ["ar", "en"])
  test(`Expo ${locale}: a Trade Approval card shows the agent's reason and its tolerance band`, async ({
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
      requests: [
        {
          action: "buy_limit",
          symbol: "XAUUSD",
          volume: "0.1",
          price: "99",
          stop_loss: "95",
          take_profit: "110",
        },
      ],
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
    // A market buy: its entry reads «بسعر السوق», as on Web.
    const market = {
      ...base,
      id: randomUUID(),
      timeline_seq: 3,
      status: "pending",
      reason: "",
      requests: [{ action: "buy", symbol: "XAUUSD", volume: "0.2", stop_loss: "90" }],
    };
    // Completed, but the broker refused it: never a success look (D2); the broker's own
    // sentence is labelled as its words, after the localized reason (D10).
    const failed = {
      ...base,
      id: randomUUID(),
      timeline_seq: 4,
      status: "completed",
      reason: "",
      results: [
        {
          operation_id: randomUUID(),
          status: "failed",
          code: "broker_rejected",
          details: {
            string_code: "TRADE_RETCODE_NO_MONEY",
            price: "2360.00",
            description: "Not enough money",
          },
        },
      ],
    };
    // Approved and awaiting the broker's result: it waits, never a success yet (D2).
    const approved = { ...base, id: randomUUID(), timeline_seq: 5, status: "approved", reason: "" };
    await page.route("**/api/trading/approvals?*", (route) =>
      route.fulfill({ json: [pending, drifted, market, failed, approved] }),
    );
    try {
      await page.addInitScript((value) => localStorage.setItem("lonora.locale", value), locale);
      await page.goto(`/thread?id=${thread.id}`);
      // The native card renders the same shared texts: «طلب موافقة · XAUUSD», the request in
      // words (never «buy_limit · XAUUSD · 0.1»).
      await expect(
        page.getByText(`${text.kicker} · \u2068XAUUSD\u2069`, { exact: true }).first(),
      ).toBeVisible();
      await expect(
        page.getByText(text.title.replace(/ (\S+)$/, " \u2068$1\u2069"), { exact: true }).first(),
      ).toBeVisible();
      await expect(page.getByText("buy_limit")).toHaveCount(0);
      await expect(page.getByText(text.words, { exact: true })).toBeVisible();
      await expect(page.getByText(pending.reason, { exact: true })).toBeVisible();
      // The facts are label/value rows, as the web card's (v38 `.oa-dl`); the tolerance stays
      // whole and in order (isolated left-to-right, no-break spaces).
      const row = (label, value) =>
        page
          .locator("div")
          .filter({ has: page.getByText(label, { exact: true }) })
          .filter({ has: page.getByText(value, { exact: true }) })
          .last();
      await expect(row(text.band, "\u2066101 ± 1.5\u2069")).toBeVisible();
      await expect(page.getByText(text.drifted, { exact: true })).toBeVisible();
      // 10.3: entry, stop loss and take profit are labelled, never bare numbers.
      for (const [label, value] of [
        [text.price, "99"],
        [text.stopLoss, "95"],
        [text.takeProfit, "110"],
        [text.price, text.market],
      ])
        await expect(row(label, value)).toBeVisible();
      await expect(
        page
          .getByText(text.marketTitle.replace(/ (\S+)$/, " \u2068$1\u2069"), { exact: true })
          .first(),
      ).toBeVisible();
      // The kicker carries its shield, as the web card's (v38).
      await expect(
        page.getByTestId("trade-approval").first().locator('path[d^="M12 2l9 4v6"]'),
      ).toHaveCount(1);
      // The decided cards' end states: drift warns, a broker refusal is plain, an approval
      // awaiting the broker waits; never «ok».
      await expect(page.getByTestId("trade-approval-status-warn")).toHaveCount(1);
      await expect(page.getByTestId("trade-approval-status-plain")).toHaveCount(1);
      await expect(page.getByTestId("trade-approval-status-wait")).toHaveCount(1);
      await expect(page.getByTestId("trade-approval-status-ok")).toHaveCount(0);
      const result = page.getByTestId("trade-approval-result-failed");
      // The shared fallback for a code no catalog explains, as on Web (D10).
      await expect(result.getByText(text.failedReason, { exact: true })).toBeVisible();
      // The broker's price is labelled, never a bare number.
      await expect(page.getByTestId("trade-approval-result-price")).toHaveText(text.brokerPrice);
      await expect(page.getByTestId("trade-approval-broker-words")).toHaveText(text.brokerWords);
      await expect(result).not.toContainText("TRADE_RETCODE_NO_MONEY");
      if (locale === "ar")
        await page.screenshot({
          path: test.info().outputPath("trade-approval-validity-native-ar.png"),
        });
    } finally {
      await context.request.delete(`/api/agents/${agent.id}`, { headers });
    }
  });
