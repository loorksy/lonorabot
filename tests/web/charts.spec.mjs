// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: Playwright runs without Turborepo caching.
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
test("market reads a persistent cloud scene and edits the same chart without creation on reload", async ({
  page,
  context,
}) => {
  const data = fixture({ action: "init" });
  const errors = [];
  const writes = [];
  const candleReads = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (path === "/api/charts" && request.method() === "POST") writes.push(request);
    if (path === "/api/market/candles") candleReads.push(request);
  });
  async function selectMarket() {
    await page.goto("/app/market");
    await page
      .getByRole("combobox", { name: "Broker account", exact: true })
      .selectOption(data.account);
    await page.getByLabel("Exact broker symbol", { exact: true }).selectOption(data.symbol);
  }
  try {
    await context.addCookies(
      data.cookies.map((cookie) => ({
        ...cookie,
        url: test.info().project.use.baseURL,
        httpOnly: cookie.name === "lonora_session",
        sameSite: "Strict",
      })),
    );
    await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
    await selectMarket();
    const chart = page.locator(`[data-chart-id='${data.chart}']`);
    await expect(chart).toBeVisible();
    await expect(chart.getByRole("combobox", { name: "Timeframe", exact: true })).toHaveValue(
      "15m",
    );
    await expect(chart.locator("canvas").first()).toBeVisible();
    const initialVersion = Number(await chart.getAttribute("data-chart-scene-version"));
    expect(initialVersion).toBeGreaterThan(0);
    const change = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === `/api/charts/${data.chart}` &&
        response.request().method() === "PUT",
    );
    await chart.getByRole("combobox", { name: "Timeframe", exact: true }).selectOption("1h");
    expect((await change).ok()).toBeTruthy();
    fixture({ ...data, action: "refresh" });
    await expect(chart.getByRole("combobox", { name: "Timeframe", exact: true })).toHaveValue("1h");
    await expect
      .poll(async () => Number(await chart.getAttribute("data-chart-scene-version")))
      .toBeGreaterThan(initialVersion);
    await selectMarket();
    await expect(chart.getByRole("combobox", { name: "Timeframe", exact: true })).toHaveValue("1h");
    await expect(chart.locator("canvas").first()).toBeVisible();
    expect(writes).toHaveLength(0);
    expect(candleReads).toHaveLength(0);
    expect(errors).toEqual([]);
  } finally {
    fixture({ ...data, action: "cleanup" });
  }
});

test("opening an empty instrument creates exactly one chart through an explicit click", async ({
  page,
  context,
}) => {
  const data = fixture({ action: "init", empty: true });
  let creates = 0;
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/api/charts" && request.method() === "POST") creates++;
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
    await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
    await page.goto("/app/market");
    await page
      .getByRole("combobox", { name: "Broker account", exact: true })
      .selectOption(data.account);
    await page.getByLabel("Exact broker symbol", { exact: true }).selectOption(data.symbol);
    const open = page.getByRole("button", { name: "Open chart", exact: true });
    await expect(open).toBeVisible();
    expect(creates).toBe(0);
    const created = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === "/api/charts" &&
        response.request().method() === "POST",
    );
    await open.click();
    const response = await created;
    expect(response.ok()).toBeTruthy();
    data.chart = (await response.json()).id;
    fixture({ ...data, action: "refresh" });
    const chart = page.locator(`[data-chart-id='${data.chart}']`);
    await expect(chart.locator("canvas").first()).toBeVisible();
    await page.reload();
    await page
      .getByRole("combobox", { name: "Broker account", exact: true })
      .selectOption(data.account);
    await page.getByLabel("Exact broker symbol", { exact: true }).selectOption(data.symbol);
    await expect(chart.locator("canvas").first()).toBeVisible();
    expect(creates).toBe(1);
  } finally {
    fixture({ ...data, action: "cleanup" });
  }
});

test("resident live OHLC updates the selected chart through SSE without catalog or historical fetches", async ({
  page,
  context,
}) => {
  const data = fixture({ action: "init" });
  const errors = [];
  let catalogs = 0;
  let candleReads = 0;
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (path === "/api/charts" && request.method() === "GET") catalogs++;
    if (path === "/api/market/candles") candleReads++;
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
    await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
    await page.goto("/app/market");
    await page
      .getByRole("combobox", { name: "Broker account", exact: true })
      .selectOption(data.account);
    await page.getByLabel("Exact broker symbol", { exact: true }).selectOption(data.symbol);
    const chart = page.locator(`[data-chart-id='${data.chart}']`);
    await expect(chart.locator("canvas").first()).toBeVisible();
    const initial = Number(await chart.getAttribute("data-chart-scene-version"));
    expect(initial).toBeGreaterThan(0);
    const before = await chart.locator(".chart-renderer").screenshot();
    const initialCatalogs = catalogs;
    const published = fixture({ ...data, action: "live", close: "250" });
    expect(published.candles.at(-1).close).toBe("250");
    await expect
      .poll(async () => Number(await chart.getAttribute("data-chart-scene-version")))
      .toBeGreaterThanOrEqual(published.scene_version);
    await expect(chart.getByText("Loading chart…", { exact: true })).toHaveCount(0);
    const after = await chart.locator(".chart-renderer").screenshot();
    expect(after.equals(before)).toBe(false);
    expect(catalogs).toBe(initialCatalogs);
    expect(candleReads).toBe(0);
    const persisted = await page.request.get(`/api/charts/${data.chart}/scene`);
    expect(persisted.ok()).toBeTruthy();
    expect((await persisted.json()).candles.at(-1).close).toBe("250");
    await page.reload();
    await page
      .getByRole("combobox", { name: "Broker account", exact: true })
      .selectOption(data.account);
    await page.getByLabel("Exact broker symbol", { exact: true }).selectOption(data.symbol);
    await expect(chart.locator("canvas").first()).toBeVisible();
    await expect
      .poll(async () => Number(await chart.getAttribute("data-chart-scene-version")))
      .toBeGreaterThanOrEqual(published.scene_version);
    expect(errors).toEqual([]);
  } finally {
    fixture({ ...data, action: "cleanup" });
  }
});
