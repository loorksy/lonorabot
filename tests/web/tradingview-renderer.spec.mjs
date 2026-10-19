import { expect, test } from "@playwright/test";

function fixture() {
  const start = Math.floor(Date.now() / 3600000) * 3600000 - 150 * 3600000;
  const candles = Array.from({ length: 150 }, (_, i) => ({
    time: new Date(start + i * 3600000).toISOString(),
    open: 1.1 + i * 0.0001,
    high: 1.102 + i * 0.0001,
    low: 1.098 + i * 0.0001,
    close: 1.101 + i * 0.0001,
  }));
  const a = { time: candles[110].time, price: 1.109 },
    b = { time: candles[135].time, price: 1.115 };
  const annotations = [
    { type: "price", price: 1.11 },
    { type: "horizontal_line", price: 1.112, label: "Saved level" },
    { type: "trend_line", start: a, end: b },
    { type: "note", time: a.time, price: a.price, text: "Saved note" },
    { type: "price_zone", start: a, end: b },
    { type: "ray", start: a, end: b },
    { type: "channel", start: a, end: b, parallel: { time: a.time, price: 1.113 } },
    { type: "fibonacci", start: a, end: b },
    { type: "arrow", start: a, end: b },
    { type: "scenario", start: a, end: b, stop: 1.106 },
  ].map((item, i) => ({
    ...item,
    id: `saved-${i}`,
    source: i % 2 ? "agent" : "user",
    scope: { chart_id: "fixture-chart", symbol: "EURUSD.raw", account_id: "fixture-account" },
    style: { color: "#6289e8", line_width: 1, line_style: "solid" },
  }));
  return {
    chart_id: "fixture-chart",
    revision: 1,
    scene_version: 1,
    status: "ready",
    updated_at: new Date().toISOString(),
    symbol: "EURUSD.raw",
    timeframe: "1h",
    candles,
    indicators: [
      { name: "RSI", period: 14, series: { rsi: candles.map((_, i) => 40 + (i % 20)) } },
    ],
    annotations,
  };
}
async function send(page, scene, extra = {}) {
  await page.evaluate(
    ({ scene, extra }) =>
      window.postMessage(
        { type: "lonora.chart.scene", account_id: "fixture-account", scene, ...extra },
        window.location.origin,
      ),
    { scene, extra },
  );
  await expect(page.locator("[data-applied-scene-version]")).toHaveAttribute(
    "data-applied-scene-version",
    String(scene.scene_version),
  );
}
for (const locale of ["en", "ar"])
  test(`licensed ${locale} renderer cold-loads saved geometry, live bars, corrections and viewport`, async ({
    page,
  }) => {
    const failures = [],
      errors = [],
      external = [],
      vendorAssets = [];
    page.on("response", (response) => {
      if (response.url().includes("/charting_library/") && response.status() >= 400)
        failures.push(response.url());
    });
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("request", (request) => {
      if (request.url().includes("/charting_library/")) vendorAssets.push(request.url());
      if (new URL(request.url()).hostname === "www.tradingview.com") external.push(request.url());
    });
    await page.goto(`/charts/render?locale=${locale}`);
    // Capture the actual vendor widget for behavioral assertions, without product test hooks.
    await page.addScriptTag({ url: "/charting_library/charting_library.standalone.js" });
    await page.evaluate(() => {
      const Widget = window.TradingView.widget;
      window.TradingView.widget = class extends Widget {
        constructor(options) {
          super(options);
          window.testChart = this;
        }
      };
      window.chartAcks = [];
      window.ReactNativeWebView = {
        postMessage: (message) => window.chartAcks.push(JSON.parse(message)),
      };
    });
    const scene = fixture();
    await send(page, scene);
    const chart = () =>
      page.evaluate(() => ({
        symbol: window.testChart.activeChart().symbol(),
        resolution: window.testChart.activeChart().resolution(),
        shapes: window.testChart.activeChart().getAllShapes().length,
        studies: window.testChart.activeChart().getAllStudies().length,
      }));
    expect(await chart()).toEqual({
      symbol: "EURUSD.raw",
      resolution: "60",
      shapes: 16,
      studies: 1,
    });
    await expect(
      page.frameLocator(".chart-renderer iframe").locator("canvas").first(),
    ).toBeVisible();
    const iframe = await page.locator(".chart-renderer iframe").getAttribute("id");
    const range = {
      from: Date.parse(scene.candles[25].time) / 1000,
      to: Date.parse(scene.candles[80].time) / 1000,
    };
    await page.evaluate((range) => window.testChart.activeChart().setVisibleRange(range), range);
    const before = await page.evaluate(() => window.testChart.activeChart().getVisibleRange());
    scene.scene_version++;
    scene.candles.at(-1).close += 0.0002;
    await send(page, scene);
    scene.scene_version++;
    scene.candles.push({
      ...scene.candles.at(-1),
      time: new Date(Date.parse(scene.candles.at(-1).time) + 3600000).toISOString(),
    });
    scene.indicators[0].series.rsi.push(51);
    await send(page, scene);
    expect(await page.locator(".chart-renderer iframe").getAttribute("id")).toBe(iframe);
    expect(await page.evaluate(() => window.testChart.activeChart().getVisibleRange())).toEqual(
      before,
    );
    scene.scene_version++;
    scene.candles[10].high += 0.0003;
    await send(page, scene);
    expect(await page.evaluate(() => window.testChart.activeChart().getVisibleRange())).toEqual(
      before,
    );
    expect((await chart()).shapes).toBe(16);
    await page.evaluate(
      (scene) =>
        window.postMessage(
          { type: "lonora.chart.scene", scene: { ...scene, scene_version: 1 } },
          location.origin,
        ),
      scene,
    );
    await expect(page.locator("[data-applied-scene-version]")).toHaveAttribute(
      "data-applied-scene-version",
      "4",
    );
    expect(await page.evaluate(() => window.chartAcks.at(-1).scene_version)).toBe(4);
    const otherLocale = locale === "en" ? "ar" : "en";
    await send(page, scene, { locale: otherLocale });
    await expect(page.locator("html")).toHaveAttribute("lang", otherLocale);
    await expect
      .poll(() => page.locator(".chart-renderer iframe").getAttribute("id"))
      .not.toBe(iframe);
    await expect(page.locator("[data-applied-scene-version]")).toHaveAttribute(
      "data-applied-scene-version",
      "4",
    );
    const translatedRange = await page.evaluate(() =>
      window.testChart.activeChart().getVisibleRange(),
    );
    // Localized price-axis widths can quantize the left edge by one candle.
    expect(Math.abs(translatedRange.from - before.from)).toBeLessThanOrEqual(3600);
    expect(translatedRange.to).toBe(before.to);
    const acknowledgements = await page.evaluate(() => window.chartAcks.length);
    await page.evaluate(
      (scene) =>
        window.dispatchEvent(
          new MessageEvent("message", {
            origin: "https://untrusted.example",
            source: window,
            data: { type: "lonora.chart.scene", scene: { ...scene, scene_version: 99 } },
          }),
        ),
      scene,
    );
    expect(await page.evaluate(() => window.chartAcks.length)).toBe(acknowledgements);
    expect(
      vendorAssets.some((url) => new URL(url).pathname.split("/").at(-1).startsWith(`${locale}.`)),
    ).toBe(true);
    expect(
      vendorAssets
        .filter((url) => /\/[a-z]{2}\./.test(new URL(url).pathname))
        .every((url) => /\/(en|ar)\./.test(new URL(url).pathname)),
    ).toBe(true);
    expect(failures).toEqual([]);
    expect(errors).toEqual([]);
    expect(external).toEqual([]);
  });

test("vendor theme updates wait for readiness, survive locale replacement and report failures", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/charts/render?locale=en");
  await page.addScriptTag({ url: "/charting_library/charting_library.standalone.js" });
  await page.evaluate(() => {
    const Widget = window.TradingView.widget;
    window.themeCalls = 0;
    window.TradingView.widget = class extends Widget {
      constructor(options) {
        super(options);
        let ready = false,
          disposed = false;
        this.onChartReady(() => {
          ready = true;
        });
        const changeTheme = this.changeTheme.bind(this),
          remove = this.remove.bind(this);
        this.changeTheme = (...args) => {
          if (!ready || disposed) throw new Error("theme_outside_ready_lifecycle");
          window.themeCalls++;
          if (window.failTheme === "async")
            return Promise.reject(new Error("fixture_theme_failure"));
          if (window.failTheme) throw new Error("fixture_theme_failure");
          return changeTheme(...args);
        };
        this.remove = () => {
          disposed = true;
          remove();
        };
        // Reproduce an app preference update while the inner frame is still loading.
        document.documentElement.dataset.theme = "light";
      }
    };
  });
  const scene = fixture();
  await send(page, scene);
  await expect.poll(() => page.evaluate(() => window.themeCalls)).toBeGreaterThan(0);
  await page.evaluate(() => {
    window.failTheme = true;
    document.documentElement.dataset.theme = "dark";
  });
  await expect(page.getByRole("alert")).toContainText("chart_theme_failed");
  await page.evaluate(() => {
    window.failTheme = false;
    document.documentElement.dataset.theme = "light";
  });
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.evaluate(() => {
    window.failTheme = "async";
    document.documentElement.dataset.theme = "dark";
  });
  await expect(page.getByRole("alert")).toContainText("chart_theme_failed");
  await page.evaluate(() => {
    window.failTheme = false;
    document.documentElement.dataset.theme = "light";
  });
  await expect(page.getByRole("alert")).toHaveCount(0);
  const frameId = await page.locator(".chart-renderer iframe").getAttribute("id");
  await send(page, scene, { locale: "ar" });
  await expect
    .poll(() => page.locator(".chart-renderer iframe").getAttribute("id"))
    .not.toBe(frameId);
  await expect(page.locator("html")).toHaveAttribute("lang", "ar");
  await expect(page.locator("[data-applied-scene-version]")).toHaveAttribute(
    "data-applied-scene-version",
    "1",
  );
  expect(errors).toEqual([]);
});
