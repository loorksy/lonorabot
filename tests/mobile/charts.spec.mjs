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
    await expect(page.getByText("تم عرض المشهد المحفوظ", { exact: true })).toBeVisible();
    await page.evaluate(() => {
      window.chartLoadingFlashes = [];
      const observer = new MutationObserver(() => {
        if (document.body.textContent.includes("جارٍ إعداد الرسم"))
          window.chartLoadingFlashes.push(true);
      });
      observer.observe(document.body, { subtree: true, childList: true, characterData: true });
    });
    const before = await renderer.screenshot();
    const publication = fixture({ ...data, action: "live", close: "250" });
    expect(publication.candles.at(-1).close).toBe("250");
    await expect
      .poll(async () => Number(await renderer.getAttribute("data-applied-scene-version")))
      .toBeGreaterThanOrEqual(publication.scene_version);
    expect((await renderer.screenshot()).equals(before)).toBe(false);
    await expect(page.getByText("تم عرض المشهد المحفوظ", { exact: true })).toBeVisible();
    expect(await page.evaluate(() => window.chartLoadingFlashes)).toEqual([]);
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

test("an unbound chart requires explicit account and symbol even for a single broker instrument", async ({
  page,
  context,
}) => {
  const data = fixture({ action: "init", empty: true });
  const headers = {
    "X-CSRF-Token": data.cookies.find((cookie) => cookie.name === "lonora_csrf").value,
  };
  let createdChart;
  const creationRequests = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && new URL(request.url()).pathname === "/api/charts")
      creationRequests.push(request.postDataJSON());
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
    await page.getByRole("button", { name: "إنشاء رسم بياني", exact: true }).click();
    const save = page.getByRole("button", { name: "حفظ", exact: true });
    await expect(page.getByText("اختر الحساب", { exact: true })).toBeVisible();
    await expect(page.getByText("اختر الرمز", { exact: true })).toBeVisible();
    await expect(save).toBeDisabled();
    expect(creationRequests).toEqual([]);
    const connections = await (await context.request.get("/api/trading/connections")).json();
    const accountIndex = connections
      .filter((connection) => connection.payload.enabled)
      .findIndex((connection) => connection.id === data.account);
    expect(accountIndex).toBeGreaterThanOrEqual(0);
    await page.getByRole("button", { name: "حساب الوسيط", exact: true }).click();
    await page.getByRole("menu").getByRole("button").nth(accountIndex).click();
    await expect(page.getByRole("button", { name: "الرمز", exact: true })).toBeEnabled();
    await expect(page.getByText("اختر الرمز", { exact: true })).toBeVisible();
    await expect(save).toBeDisabled();
    expect(creationRequests).toEqual([]);
    await page.getByRole("button", { name: "الرمز", exact: true }).click();
    await page.getByRole("menu").getByRole("button", { name: data.symbol, exact: true }).click();
    await expect(save).toBeEnabled();
    const created = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname === "/api/charts",
    );
    await save.click();
    const response = await created;
    expect(response.status()).toBe(201);
    createdChart = await response.json();
    expect(creationRequests).toHaveLength(1);
    expect(creationRequests[0].payload).toMatchObject({
      account_id: data.account,
      symbol: data.symbol,
    });
  } finally {
    if (createdChart) await context.request.delete(`/api/charts/${createdChart.id}`, { headers });
    fixture({ ...data, action: "cleanup" });
  }
});

test("unacknowledged live updates retain their deadline and stale acknowledgements cannot hide failure", async ({
  page,
  context,
}) => {
  const data = fixture({ action: "init" });
  await page.addInitScript(() => {
    const add = window.addEventListener.bind(window);
    const remove = window.removeEventListener.bind(window);
    const wrappers = new WeakMap();
    window.addEventListener = (type, listener, options) => {
      if (type !== "message" || !listener) return add(type, listener, options);
      const wrapped = (event) => {
        if (
          event.data?.type === "lonora.chart.applied" &&
          window.blockChartAcksAfter !== undefined &&
          event.data.scene_version > window.blockChartAcksAfter
        )
          return;
        if (typeof listener === "function") listener.call(window, event);
        else listener.handleEvent(event);
      };
      wrappers.set(listener, wrapped);
      add(type, wrapped, options);
    };
    window.removeEventListener = (type, listener, options) =>
      remove(type, type === "message" ? (wrappers.get(listener) ?? listener) : listener, options);
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
    const renderer = page
      .frameLocator(`iframe[title="${data.symbol} · 15m"]`)
      .locator('[data-renderer="tradingview"]');
    await expect(page.getByText("تم عرض المشهد المحفوظ", { exact: true })).toBeVisible();
    const initialVersion = Number(await renderer.getAttribute("data-applied-scene-version"));
    await page.evaluate((version) => {
      window.blockChartAcksAfter = version;
    }, initialVersion);
    await page.clock.install();
    const first = fixture({ ...data, action: "live", close: "251" });
    await expect
      .poll(async () => Number(await renderer.getAttribute("data-applied-scene-version")))
      .toBeGreaterThanOrEqual(first.scene_version);
    await page.clock.fastForward(8000);
    const second = fixture({ ...data, action: "live", close: "252" });
    await expect
      .poll(async () => Number(await renderer.getAttribute("data-applied-scene-version")))
      .toBeGreaterThanOrEqual(second.scene_version);
    await renderer.evaluate(
      (_element, old) => {
        window.parent.postMessage(
          {
            type: "lonora.chart.applied",
            chart_id: old.chart,
            scene_version: old.version,
            data_revision: "stale",
          },
          "*",
        );
      },
      { chart: data.chart, version: initialVersion },
    );
    await page.clock.fastForward(8000);
    await expect(page.getByText("عارض الرسم غير متاح حاليًا", { exact: true })).toBeVisible();
  } finally {
    fixture({ ...data, action: "cleanup" });
  }
});
