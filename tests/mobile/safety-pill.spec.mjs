import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "../ui-test.mjs";

function simulation(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}

for (const locale of ["ar", "en"])
  test(`Expo ${locale}: the safety pill stays hidden until something is uncertain, and there is no Stop`, async ({
    page,
    context,
    cleanup,
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
    const stop =
      locale === "ar"
        ? /إيقاف الصفقات الجديدة|استئناف التداول|بدء التداول/
        : /Stop new trading|Resume trading|Start trading/;
    cleanup(async () => {
      await context.request.delete(`/api/agents/${agent.id}`, { headers });
      simulation({ ...data, action: "cleanup" });
    });
    await page.goto(`/thread?id=${thread.id}`);
    // Nothing is uncertain: the capsule is absent. There is no Stop control.
    await expect(page.getByTestId("safety-pill")).toHaveCount(0);
    await expect(page.getByRole("button", { name: stop })).toHaveCount(0);
    await expect(page.getByTestId("safety-trading-state")).toHaveCount(0);
  });
