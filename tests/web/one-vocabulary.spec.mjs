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
