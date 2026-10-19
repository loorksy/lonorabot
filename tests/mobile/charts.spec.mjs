import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

function fixture(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}

test("Expo renders durable live candles from the authenticated server event stream", async ({
  page,
  context,
}) => {
  const data = fixture({ action: "init" });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  let sockets = 0;
  page.on("websocket", (socket) => {
    if (socket.url().includes("/api/ws/events")) {
      sockets++;
      expect(new URL(socket.url()).searchParams.has("token")).toBe(false);
    }
  });
  try {
    await context.addCookies(
      data.cookies.map((cookie) => ({
        ...cookie,
        url: test.info().project.use.baseURL,
        httpOnly: cookie.name === "lonora_session",
        sameSite: "Strict",
      })),
    );
    await page.goto("/charts");
    await page.getByRole("button", { name: `${data.symbol} · 15m`, exact: true }).click();
    const frame = page.frameLocator(`iframe[title="${data.symbol} · 15m"]`);
    const renderer = frame.locator('[data-renderer="tradingview"]');
    await expect(renderer).toBeVisible();
    await expect(renderer).toHaveAttribute("data-applied-scene-version", /[1-9]/);
    await expect.poll(() => sockets).toBeGreaterThan(0);
    const before = await renderer.screenshot();
    const publication = fixture({ ...data, action: "live", close: "250" });
    expect(publication.candles.at(-1).close).toBe("250");
    await expect
      .poll(async () => Number(await renderer.getAttribute("data-applied-scene-version")))
      .toBeGreaterThanOrEqual(publication.scene_version);
    expect((await renderer.screenshot()).equals(before)).toBe(false);
    await page.reload();
    await page.getByRole("button", { name: `${data.symbol} · 15m`, exact: true }).click();
    await expect
      .poll(async () => Number(await renderer.getAttribute("data-applied-scene-version")))
      .toBeGreaterThanOrEqual(publication.scene_version);
    const persisted = await page.request.get(`/api/charts/${data.chart}/scene`);
    expect((await persisted.json()).candles.at(-1).close).toBe("250");
    expect(errors).toEqual([]);
  } finally {
    fixture({ ...data, action: "cleanup" });
  }
});

test("a bound bot chart keeps its account and symbol fixed while timeframe stays editable", async ({
  page,
  context,
}) => {
  const data = fixture({ action: "init" });
  const headers = {
    "X-CSRF-Token": data.cookies.find((cookie) => cookie.name === "lonora_csrf").value,
  };
  let agent;
  try {
    await context.addCookies(
      data.cookies.map((cookie) => ({
        ...cookie,
        url: test.info().project.use.baseURL,
        httpOnly: cookie.name === "lonora_session",
        sameSite: "Strict",
      })),
    );
    const created = await context.request.post("/api/agents", {
      headers,
      data: {
        name: "Bound chart owner",
        trading_account_id: data.account,
        trading_symbol: data.symbol,
      },
    });
    expect(created.status()).toBe(201);
    agent = await created.json();
    await page.goto(`/charts?botId=${agent.id}`);
    await expect(
      page.getByRole("button", { name: `${data.symbol} · 15m`, exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "إنشاء رسم بياني", exact: true }).click();
    await expect(page.getByRole("button", { name: "حساب الوسيط", exact: true })).toBeDisabled();
    await expect(page.getByRole("button", { name: "الرمز", exact: true })).toBeDisabled();
    await expect(page.getByText(data.symbol, { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "الفاصل الزمني", exact: true })).toBeEnabled();
  } finally {
    if (agent) await context.request.delete(`/api/agents/${agent.id}`, { headers });
    fixture({ ...data, action: "cleanup" });
  }
});
