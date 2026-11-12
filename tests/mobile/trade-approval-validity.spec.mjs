import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

// A Trade Approval card shows the agent's reason labelled as the agent's words and the
// band it stays valid within (mandate 10.3, 10.3.1); a drifted card says nothing was sent.
const copy = {
  ar: {
    words: "بكلمات الوكيل",
    band: "صالحة ما دام السعر ضمن",
    price: "السعر",
    stopLoss: "وقف الخسارة",
    takeProfit: "جني الربح",
    drifted: "خرج السعر عن الهامش — لم يُرسل شيء",
  },
  en: {
    words: "In the agent's words",
    band: "Valid while the price stays within",
    price: "Price",
    stopLoss: "Stop loss",
    takeProfit: "Take profit",
    drifted: "Price moved outside the tolerance — nothing was sent",
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
    await page.route("**/api/trading/approvals?*", (route) =>
      route.fulfill({ json: [pending, drifted] }),
    );
    try {
      await page.addInitScript((value) => localStorage.setItem("lonora.locale", value), locale);
      await page.goto(`/thread?id=${thread.id}`);
      // The native card renders the same shared texts.
      await expect(page.getByText(text.words, { exact: true })).toBeVisible();
      await expect(page.getByText(pending.reason, { exact: true })).toBeVisible();
      await expect(page.getByText(`${text.band} 101 ± 1.5`, { exact: true }).first()).toBeVisible();
      await expect(page.getByText(text.drifted, { exact: true })).toBeVisible();
      // 10.3: entry, stop loss and take profit are labelled, never bare numbers.
      for (const [label, value] of [
        [text.price, "99"],
        [text.stopLoss, "95"],
        [text.takeProfit, "110"],
      ])
        await expect(page.getByText(`${label}: ${value}`, { exact: true }).first()).toBeVisible();
      if (locale === "ar")
        await page.screenshot({
          path: test.info().outputPath("trade-approval-validity-native-ar.png"),
        });
    } finally {
      await context.request.delete(`/api/agents/${agent.id}`, { headers });
    }
  });
