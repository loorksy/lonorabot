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
  en: {
    monitoring: /^Monitoring ⁨XAUUSD⁩ until /,
    cancel: "Cancel",
    condition: /⁨XAUUSD⁩ above ⁨2100⁩/,
  },
  ar: {
    monitoring: /^يراقب ⁨XAUUSD⁩ حتى /,
    cancel: "إلغاء",
    condition: /⁨XAUUSD⁩ فوق ⁨2100⁩/,
  },
};

for (const locale of ["en", "ar"])
  test(`${locale}: a watch is cancelled from the agent status line`, async ({ page, context }) => {
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
    await context.addInitScript((value) => {
      localStorage.setItem("lonora.locale", value);
      // «حالة الوكيل التفصيلية» is a per-device preference, off by default (Q35).
      localStorage.setItem("lonora.chatPrefs", JSON.stringify({ agentStatus: true }));
    }, locale);
    const headers = {
      "X-CSRF-Token": data.cookies.find((row) => row.name === "lonora_csrf").value,
    };
    const made = await context.request.post("/api/agents", {
      headers,
      data: {
        name: `Creator ${randomUUID().slice(0, 6)}`,
        trading_account_id: data.account,
        trading_symbol: data.symbol,
      },
    });
    expect(made.status()).toBe(201);
    const creator = await made.json();
    try {
      // A watch the creator keeps until the London close; the status line names it.
      const watch = await context.request.post("/api/watches", {
        headers,
        data: {
          agent_id: creator.id,
          payload: {
            kind: "price",
            account_id: data.account,
            symbol: data.symbol,
            condition: "above",
            level: "2100",
            prompt: "Gold above 2100",
            expires_at: new Date(Date.now() + 3 * 3600_000).toISOString(),
          },
        },
      });
      expect(watch.status()).toBe(201);
      const watchId = (await watch.json()).id;
      await page.goto(`/app/${creator.id}`);
      const line = page.getByTestId("agent-status-line");
      await expect(line).toHaveText(text.monitoring);
      if (locale === "ar") await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
      // The status line opens the AgentSheet; its watches row opens «المراقبات»; Cancel there.
      await line.click();
      await page.locator("#dialog .ev-row").click();
      const item = page.locator(`#dialog [data-watch="${watchId}"]`);
      await expect(item).toContainText(text.condition);
      await item.getByRole("button", { name: text.cancel, exact: true }).click();
      await expect(item).toHaveCount(0);
      const stored = await (await context.request.get(`/api/watches/${watchId}`)).json();
      expect(stored.payload.enabled).toBe(false);
      expect(stored.state.code).toBe("watch_cancelled");
      await expect(line).not.toHaveText(text.monitoring);
    } finally {
      await context.request.delete(`/api/agents/${creator.id}`, { headers });
      simulation({ ...data, action: "cleanup" });
    }
  });
