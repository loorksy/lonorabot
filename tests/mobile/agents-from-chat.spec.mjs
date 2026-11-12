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

const copy = {
  ar: {
    monitoring: "يراقب",
    cancel: "إلغاء",
  },
  en: {
    monitoring: "Monitoring",
    cancel: "Cancel",
  },
};

for (const locale of ["ar", "en"])
  test(`Expo ${locale}: the status line's watch list cancels a watch`, async ({
    page,
    context,
  }) => {
    test.setTimeout(90000);
    const text = copy[locale];
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
    const made = await context.request.post("/api/agents", {
      headers,
      data: {
        name: `Native creator ${randomUUID().slice(0, 6)}`,
        trading_account_id: data.account,
        trading_symbol: data.symbol,
      },
    });
    expect(made.status()).toBe(201);
    const creator = await made.json();
    const thread = await (
      await context.request.post(`/api/agents/${creator.id}/conversation`, { headers, data: {} })
    ).json();
    try {
      const watch = await context.request.post("/api/watches", {
        headers,
        data: {
          agent_id: creator.id,
          payload: {
            kind: "price",
            account_id: data.account,
            symbol: data.symbol,
            condition: "below",
            level: "150",
            prompt: "Gold below 150",
            expires_at: new Date(Date.now() + 2 * 3600_000).toISOString(),
          },
        },
      });
      expect(watch.status()).toBe(201);
      const watchId = (await watch.json()).id;
      await page.goto(`/thread?id=${thread.id}`);
      const live = page.getByTestId("agent-live-state");
      await expect(live.getByText(text.monitoring, { exact: false })).toBeVisible();
      await live.getByRole("button").first().click();
      const row = page.getByTestId(`agent-watch-${watchId}`);
      await expect(row).toBeVisible();
      await row.getByRole("button", { name: text.cancel, exact: true }).click();
      await expect(row).toHaveCount(0);
      const stored = await (await context.request.get(`/api/watches/${watchId}`)).json();
      expect(stored.payload.enabled).toBe(false);
    } finally {
      await context.request.delete(`/api/agents/${creator.id}`, { headers });
      simulation({ ...data, action: "cleanup" });
    }
  });
