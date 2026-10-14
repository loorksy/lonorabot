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
    const image = page.getByRole("img", { name: `${data.symbol} · 15m`, exact: true });
    await expect(image).toBeVisible();
    await expect.poll(() => sockets).toBeGreaterThan(0);
    const before = await image.screenshot();
    const publication = fixture({ ...data, action: "live", close: "250" });
    expect(publication.candles.at(-1).close).toBe("250");
    await expect(page.getByText(/C (250|٢٥٠)/)).toBeVisible();
    expect((await image.screenshot()).equals(before)).toBe(false);
    await page.reload();
    await page.getByRole("button", { name: `${data.symbol} · 15m`, exact: true }).click();
    await expect(page.getByText(/C (250|٢٥٠)/)).toBeVisible();
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
