import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

function simulation(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}

for (const locale of ["ar", "en"])
  test(`Expo ${locale}: the thread safety pill shows the status line and offers no Stop`, async ({
    page,
    context,
  }) => {
    test.setTimeout(60000);
    const data = simulation({ action: "init", empty: true });
    await context.addCookies(
      data.cookies.map((cookie) => ({
        ...cookie,
        url: test.info().project.use.baseURL,
        httpOnly: cookie.name === "lonora_session",
        sameSite: "Strict",
      })),
    );
    await context.addInitScript((value) => localStorage.setItem("lonora.locale", value), locale);
    const headers = {
      "X-CSRF-Token": data.cookies.find((row) => row.name === "lonora_csrf").value,
    };
    const created = await context.request.post("/api/agents", {
      headers,
      data: {
        name: `Native safety ${randomUUID()}`,
        trading_account_id: data.account,
        trading_symbol: data.symbol,
      },
    });
    expect(created.status()).toBe(201);
    const agent = await created.json();
    const thread = await (
      await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
    ).json();
    const text =
      locale === "ar"
        ? {
            asks: "يسألك قبل كل صفقة",
            stop: /إيقاف الصفقات الجديدة|استئناف التداول|بدء التداول/,
          }
        : {
            asks: "Asks you before each trade",
            stop: /Stop new trading|Resume trading|Start trading/,
          };
    try {
      const permissions = await (
        await context.request.get(`/api/agents/${agent.id}/permissions`)
      ).json();
      const changed = await context.request.put(`/api/agents/${agent.id}/permissions`, {
        headers,
        data: { level: "supervised", expected_revision: permissions.revision },
      });
      expect(changed.ok()).toBeTruthy();
      await page.goto(`/thread?id=${thread.id}`);
      const pill = page.getByTestId("safety-pill");
      await expect(pill).toContainText(text.asks);
      await pill.click();
      const sheet = page.getByTestId("safety-sheet");
      // Amendment 1: Lonora has no Stop control; the sheet offers no Stop, Resume or Start.
      await expect(sheet.getByRole("button", { name: text.stop })).toHaveCount(0);
      await expect(sheet.getByTestId("safety-trading-state")).toHaveCount(0);
    } finally {
      await context.request.delete(`/api/agents/${agent.id}`, { headers });
      simulation({ ...data, action: "cleanup" });
    }
  });
