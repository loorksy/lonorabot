import { expect, test } from "@playwright/test";

// Browser interaction coverage for the Expo shell; this does not certify Android.
for (const locale of ["en", "ar"]) {
  test(`chart sheet (${locale}) preserves conversation through expand, minimize, Escape and reopen`, async ({
    page,
  }) => {
    await page.addInitScript((value) => localStorage.setItem("lonora.locale", value), locale);
    const label = (english, arabic) => (locale === "ar" ? arabic : english);
    const chart = {
      id: "chart-sheet",
      payload: {
        account_id: "owned-account",
        symbol: "XAUUSD.raw",
        timeframe: "15m",
        indicators: [],
        annotations: [],
      },
      thread_id: "sheet-thread",
      agent_id: null,
    };
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      const data =
        path === "/api/auth/session"
          ? { id: "sheet-owner", email: "chart@example.test", name: "Owner" }
          : path === "/api/threads/sheet-thread"
            ? { id: "sheet-thread", title: "Chart conversation", agent_id: null, group_id: null }
            : path === "/api/charts"
              ? [chart]
              : path === "/api/charts/chart-sheet/scene"
                ? {
                    chart_id: chart.id,
                    scene_version: 1,
                    revision: 1,
                    status: "ready",
                    updated_at: "2026-10-18T00:00:00Z",
                    symbol: chart.payload.symbol,
                    timeframe: "15m",
                    candles: [],
                    indicators: [],
                    annotations: [],
                  }
                : path.endsWith("/collaboration")
                  ? null
                  : [];
      await route.fulfill({ json: data });
    });
    await page.route("**/charts/render?*", (route) =>
      route.fulfill({
        contentType: "text/html",
        body: `<script>document.addEventListener('keydown',e=>{if(e.key==='Escape')parent.postMessage({type:'lonora.chart.escape'},location.origin)});window.addEventListener('message',e=>{if(e.data?.type==='lonora.chart.scene')parent.postMessage({type:'lonora.chart.applied',chart_id:e.data.scene.chart_id,scene_version:e.data.scene.scene_version},location.origin)});parent.postMessage({type:'lonora.chart.ready'},location.origin)</script>`,
      }),
    );
    await page.goto("/thread?id=sheet-thread");
    const composer = page.getByRole("textbox");
    await composer.fill("Keep this draft");
    await page
      .getByRole("button", { name: label("Agent actions", "إجراءات الوكيل"), exact: true })
      .click();
    await page
      .getByRole("button", { name: label("Charts", "الرسوم البيانية"), exact: true })
      .click();
    await expect(
      page.getByText(label("Saved scene rendered", "تم عرض المشهد المحفوظ"), { exact: true }),
    ).toBeVisible();
    const frame = page.locator("iframe");
    await expect(frame).toHaveCount(1);
    expect(await frame.getAttribute("src")).not.toContain("token");
    await frame.evaluate((node) => {
      node.dataset.retainedFrame = "yes";
    });
    await page
      .getByRole("button", { name: label("Expand chart", "توسيع الرسم"), exact: true })
      .click();
    await page.frameLocator("iframe").locator("body").press("Escape");
    await expect(
      page.getByRole("button", { name: label("Expand chart", "توسيع الرسم"), exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: label("Minimize chart", "تصغير الرسم"), exact: true })
      .click();
    await expect(composer).toHaveValue("Keep this draft");
    await page
      .getByRole("button", { name: label("Reopen chart", "إعادة فتح الرسم"), exact: true })
      .click();
    await expect(frame).toHaveCount(1);
    await expect(frame).toHaveAttribute("data-retained-frame", "yes");
    await page.keyboard.press("Escape");
    await expect(frame).toHaveCount(0);
    await expect(composer).toHaveValue("Keep this draft");
    await expect(page).toHaveURL(/thread\?id=sheet-thread/);
  });
}

test("renderer acknowledges only its own frame and exact scene revision", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const scene = {
    chart_id: "ack-chart",
    scene_version: 7,
    revision: 2,
    data_revision: "market-9",
    status: "ready",
    updated_at: "2026-10-18T00:00:00Z",
    symbol: "EURUSD.raw",
    timeframe: "1h",
    candles: [],
    indicators: [],
    annotations: [],
  };
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    return route.fulfill({
      json:
        path === "/api/auth/session"
          ? { id: "ack-owner" }
          : path === "/api/charts"
            ? [
                {
                  id: scene.chart_id,
                  payload: {
                    account_id: "owned-account",
                    symbol: scene.symbol,
                    timeframe: scene.timeframe,
                  },
                  agent_id: null,
                  thread_id: null,
                },
              ]
            : path.endsWith("/scene")
              ? scene
              : [],
    });
  });
  await page.route("**/charts/render?*", (route) =>
    route.fulfill({
      contentType: "text/html",
      body: "<script>parent.postMessage({type:'lonora.chart.ready'},location.origin)</script>",
    }),
  );
  await page.goto("/charts");
  await expect(page.locator("iframe")).toBeVisible();
  const acknowledge = async (changes, source = "frame", origin = "current") =>
    page.evaluate(
      ({ changes, source, origin }) => {
        window.dispatchEvent(
          new MessageEvent("message", {
            origin: origin === "current" ? location.origin : "https://untrusted.example",
            source: source === "frame" ? document.querySelector("iframe").contentWindow : window,
            data: {
              type: "lonora.chart.applied",
              chart_id: "ack-chart",
              scene_version: 7,
              data_revision: "market-9",
              ...changes,
            },
          }),
        );
      },
      { changes, source, origin },
    );
  await acknowledge({}, "parent");
  await acknowledge({}, "frame", "wrong");
  await acknowledge({ chart_id: "other-chart" });
  await acknowledge({ scene_version: 6 });
  await acknowledge({ data_revision: "market-8" });
  await expect(page.getByText("Saved scene rendered", { exact: true })).toHaveCount(0);
  await acknowledge({});
  await expect(page.getByText("Saved scene rendered", { exact: true })).toBeVisible();
});
