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

for (const locale of ["en", "ar"]) {
  test(`${locale}: an agent that cannot trade shows "No trading", one that can shows its level`, async ({
    page,
    context,
  }) => {
    const data = fixture({ action: "init" });
    const headers = {
      "X-CSRF-Token": data.cookies.find((cookie) => cookie.name === "lonora_csrf").value,
    };
    const agents = [];
    try {
      await context.addCookies(
        data.cookies.map((cookie) => ({
          ...cookie,
          url: test.info().project.use.baseURL,
          httpOnly: cookie.name === "lonora_session",
          sameSite: "Strict",
        })),
      );
      await context.addInitScript((value) => localStorage.setItem("lonora.locale", value), locale);
      // A research agent: no account, no grant, no trade waiting for the owner.
      const research = await context.request.post("/api/agents", {
        headers,
        data: { name: `Research ${randomUUID()}`, scope_mode: "flexible" },
      });
      expect(research.status()).toBe(201);
      const general = await research.json();
      agents.push(general.id);
      expect(general.trades_on_its_own).toBe(false);
      expect(general).not.toHaveProperty("super_bot_active");
      await page.goto(`/app/${general.id}`);
      const badge = page.getByTestId("permission-no-trading");
      await expect(badge).toBeVisible();
      await expect(badge).toHaveText(locale === "ar" ? "لا يتداول" : "No trading");
      await expect(page.getByTestId("permission-selector")).toHaveCount(0);
      await expect(page.getByText(/Super Bot|سوبر بوت/)).toHaveCount(0);

      // A trading agent with its focus pair keeps the one trading control.
      const trading = await context.request.post("/api/agents", {
        headers,
        data: {
          name: `Gold ${randomUUID()}`,
          trading_account_id: data.account,
          trading_symbol: data.symbol,
        },
      });
      expect(trading.status()).toBe(201);
      const gold = await trading.json();
      agents.push(gold.id);
      await page.goto(`/app/${gold.id}`);
      await expect(page.getByTestId("permission-selector")).toBeVisible();
      await expect(page.getByTestId("permission-no-trading")).toHaveCount(0);
    } finally {
      for (const id of agents) await context.request.delete(`/api/agents/${id}`, { headers });
      fixture({ ...data, action: "cleanup" });
    }
  });
}

for (const locale of ["en", "ar"]) {
  test(`${locale}: an uncertain broker result never says "Try again"`, async ({
    page,
    context,
  }) => {
    const data = fixture({ action: "init" });
    const headers = {
      "X-CSRF-Token": data.cookies.find((cookie) => cookie.name === "lonora_csrf").value,
    };
    await context.addCookies(
      data.cookies.map((cookie) => ({
        ...cookie,
        url: test.info().project.use.baseURL,
        httpOnly: cookie.name === "lonora_session",
        sameSite: "Strict",
      })),
    );
    await context.addInitScript((value) => localStorage.setItem("lonora.locale", value), locale);
    const created = await context.request.post("/api/agents", {
      headers,
      data: {
        name: `Uncertain ${randomUUID()}`,
        trading_account_id: data.account,
        trading_symbol: data.symbol,
      },
    });
    expect(created.status()).toBe(201);
    const agent = await created.json();
    try {
      const thread = await (
        await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
      ).json();
      const message = {
        id: "uncertain-1",
        seq: 1,
        thread_id: thread.id,
        agent_id: agent.id,
        role: "assistant",
        content: "Sent to the broker.",
        created_at: "2026-11-08T12:00:00Z",
        reply_to: null,
        attachment_ids: [],
      };
      const approval = {
        id: randomUUID(),
        thread_id: thread.id,
        agent_id: agent.id,
        run_id: "run",
        timeline_seq: 1,
        created_at: message.created_at,
        status: "completed",
        requests: [{ action: "buy", symbol: "EURUSDm", volume: "0.01" }],
        results: [
          // The executor's after-send codes, and a LonoraError wrapped as uncertain.
          {
            operation_id: "op-1",
            status: "ambiguous",
            code: "broker_result_ambiguous",
            details: {},
          },
          {
            operation_id: "op-2",
            status: "ambiguous",
            code: "execution_interrupted_after_send",
            details: {},
          },
          { operation_id: "op-3", status: "ambiguous", code: "broker_disabled", details: {} },
        ],
      };
      await page.route(`**/api/threads/${thread.id}/messages*`, (route) =>
        route.fulfill({ json: [message] }),
      );
      await page.route("**/api/trading/approvals?*", (route) =>
        route.fulfill({ json: [approval] }),
      );
      await page.goto(`/app/${agent.id}`);
      const card = page.locator(`[data-trade-approval="${approval.id}"]`);
      await expect(card).toHaveCount(1);
      await expect(card.locator('[data-trade-result="ambiguous"]')).toHaveCount(3);
      const uncertain =
        locale === "ar"
          ? "نتيجة غير مؤكدة — لن تُرسل مجددًا"
          : "Outcome uncertain — it will not be sent again";
      await expect(card.getByText(uncertain, { exact: true })).toHaveCount(3);
      await expect(
        card.getByText(
          locale === "ar"
            ? "انقطع الطلب بعد إرساله، فنتيجته غير مؤكدة ولن يُرسل مجددًا. تحقّق من مراكزك وأوامرك قبل أي إجراء."
            : "The request was interrupted after it was sent, so its result is not confirmed and it will not be sent again. Check your positions and orders before acting.",
          { exact: true },
        ),
      ).toBeVisible();
      const text = await card.innerText();
      expect(text).not.toMatch(/try again|retry|أعد المحاولة|حاول/i);
      expect(text).not.toMatch(/broker_result_ambiguous|execution_interrupted|broker_disabled/);
    } finally {
      await context.request.delete(`/api/agents/${agent.id}`, { headers });
      fixture({ ...data, action: "cleanup" });
    }
  });
}
