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
  test(`Expo ${locale}: the thread safety pill stops and resumes new trading in one tap`, async ({
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
    const original = await (await context.request.get("/api/trading/controls")).json();
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
            stopped: "التداول الجديد متوقف · الخروج متاح",
            asks: "يسألك قبل كل صفقة",
            resume: "استئناف التداول",
            stop: "إيقاف الصفقات الجديدة",
            running: "التداول الجديد يعمل",
            noLimit: "لا حد مالي محدد",
          }
        : {
            stopped: "New trading stopped · exits allowed",
            asks: "Asks you before each trade",
            resume: "Resume trading",
            stop: "Stop new trading",
            running: "New trading is running",
            noLimit: "No money limit set",
          };
    try {
      // The owner stopped it (not the never-started default), so the sheet offers Resume.
      for (const enabled of [true, false])
        await context.request.put("/api/trading/controls", {
          headers,
          data: { enabled, emergency_stop: false },
        });
      const permissions = await (
        await context.request.get(`/api/agents/${agent.id}/permissions`)
      ).json();
      const changed = await context.request.put(`/api/agents/${agent.id}/permissions`, {
        headers,
        data: { level: "supervised", expected_revision: permissions.revision },
      });
      expect(changed.ok()).toBeTruthy();
      const writes = [];
      page.on("request", (request) => {
        if (request.method() === "PUT" && request.url().endsWith("/api/trading/controls"))
          writes.push(request.postDataJSON());
      });
      await page.goto(`/thread?id=${thread.id}`);
      const pill = page.getByTestId("safety-pill");
      await expect(pill).toContainText(text.stopped);
      await pill.click();
      const sheet = page.getByTestId("safety-sheet");
      await expect(sheet.getByText(text.noLimit, { exact: true })).toBeVisible();
      await sheet.getByRole("button", { name: text.resume, exact: true }).click();
      await expect(sheet.getByTestId("safety-trading-state")).toContainText(text.running);
      await expect(pill).toContainText(text.asks);
      expect(writes).toEqual([{ enabled: true, emergency_stop: false }]);
      await sheet.getByRole("button", { name: text.stop, exact: true }).click();
      await expect(pill).toContainText(text.stopped);
      expect(writes.at(-1)).toEqual({ enabled: false, emergency_stop: true });
      expect(await (await context.request.get("/api/trading/controls")).json()).toEqual({
        enabled: false,
        emergency_stop: true,
      });
    } finally {
      await context.request.put("/api/trading/controls", { headers, data: original });
      await context.request.delete(`/api/agents/${agent.id}`, { headers });
      simulation({ ...data, action: "cleanup" });
    }
  });
