import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "../ui-test.mjs";

/* The v38 design pass, global patterns (docs/ui-reference/UI_CHANGES-38.md 92-121): 44px tap
   areas that keep the look, the list fold remembered with its arrow flipped, a first visit that
   follows the device, a toast with an action that waits while reached for, a row's second line
   on the narrowest phones, and message text: a signed number isolated left-to-right, a
   Latin-only text read left-to-right, a quote as one plain line. */
function fixture(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}
async function signIn(context, data, theme = "dark") {
  await context.addCookies(
    data.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript(
    ({ theme }) => {
      if (!localStorage.getItem("lonora.locale")) localStorage.setItem("lonora.locale", "ar");
      // No saved theme: the first visit follows the device.
      if (theme) localStorage.setItem("lonora.theme", JSON.stringify(theme));
    },
    { theme },
  );
}
const pseudo = (locator, which) =>
  locator.evaluate((element, which) => {
    const style = getComputedStyle(element, which);
    return { width: parseFloat(style.width), height: parseFloat(style.height) };
  }, which);

test("small controls answer over 44px; the fold is remembered and its arrow flips", async ({
  page,
  context,
  cleanup,
}) => {
  const data = fixture({ action: "init", empty: true });
  cleanup(async () => {
    fixture({ ...data, action: "cleanup" });
  });

  await signIn(context, data);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/app");
  // An icon button keeps its 40px circle; its tap area is 44px.
  const icon = page.locator(".desktop-list .icon").first();
  await expect(icon).toBeVisible();
  expect((await icon.boundingBox()).height).toBeLessThan(44);
  expect(await pseudo(icon, "::before")).toEqual({ width: 44, height: 44 });
  // The filter chips' area stays whole: the scroller gains no vertical scroll.
  const chip = page.locator(".list-filters .chip").first();
  expect((await pseudo(chip, "::before")).height).toBe(44);
  const bar = page.locator(".list-filters");
  expect(await bar.evaluate((el) => el.scrollHeight - el.clientHeight)).toBe(0);
  // The desktop bar keeps the area's top too: a tap 1px above the chip's edge is the chip's.
  expect(
    await chip.evaluate((el) => {
      const box = el.getBoundingClientRect();
      const hit = document.elementFromPoint(box.left + box.width / 2, box.top - 1);
      return el === hit || el.contains(hit);
    }),
  ).toBe(true);

  const rail = page.locator(".desktop-rail");
  const fold = rail.locator(".rail-collapse");
  await expect(fold).toHaveAttribute("aria-label", "طي قائمة المحادثات");
  expect(await fold.locator("svg").evaluate((svg) => getComputedStyle(svg).transform)).toBe("none");
  await fold.click();
  await expect(page.locator("#app")).toHaveClass(/list-collapsed/);
  // Folded: the label says what a press does and the arrow points outward.
  await expect(fold).toHaveAttribute("aria-label", "إظهار قائمة المحادثات");
  await expect
    .poll(() => fold.locator("svg").evaluate((svg) => getComputedStyle(svg).transform))
    .toBe("matrix(-1, 0, 0, 1, 0, 0)");
  await page.reload();
  await expect(page.locator("#app")).toHaveClass(/list-collapsed/);
  await rail.getByRole("button", { name: "إظهار قائمة المحادثات" }).click();
  await expect(page.locator("#app")).not.toHaveClass(/list-collapsed/);
  await page.reload();
  await expect(page.locator("#app")).not.toHaveClass(/list-collapsed/);
});

test("English: back and chevrons point its way, the tab says «Attention», a long id wraps", async ({
  page,
  context,
  cleanup,
}) => {
  const data = fixture({ action: "init", empty: true });
  cleanup(async () => {
    fixture({ ...data, action: "cleanup" });
  });

  await signIn(context, data);
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const transform = (locator) => locator.evaluate((el) => getComputedStyle(el).transform);
  const flipped = "matrix(-1, 0, 0, 1, 0, 0)";
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/app/integrations");
  // «back» and the row chevron are drawn for Arabic; English mirrors them.
  const back = page.locator(".topbar").getByRole("button", { name: "Back" }).locator("svg");
  await expect(back).toBeVisible();
  expect(await transform(back)).toBe(flipped);
  expect(await transform(page.locator(".row .chevron svg").first())).toBe(flipped);
  // A long account id wraps inside its row instead of running out of it.
  // Any of the suite's simulation accounts: each has such an id.
  const id = page.locator(".row span.ltr", { hasText: "chart-browser-" }).first();
  await expect(id).toBeVisible();
  const [box, row] = await id.evaluate((el) => [
    el.getBoundingClientRect().toJSON(),
    el.closest(".row").getBoundingClientRect().toJSON(),
  ]);
  expect(box.left).toBeGreaterThanOrEqual(row.left);
  expect(box.right).toBeLessThanOrEqual(row.right);
  // The tab says «Attention» and fits it; the button and the page keep the full words.
  await page.goto("/app");
  const tab = page.locator("nav.tabbar").getByRole("button", { name: "Needs your attention" });
  await expect(tab.locator(".nav-label")).toHaveText("Attention");
  const label = await tab.locator(".nav-label").evaluate((el) => el.scrollWidth);
  expect(label).toBeLessThanOrEqual((await tab.boundingBox()).width);
  await tab.click();
  await expect(page.locator("main > .large-title")).toHaveText(/Needs your attention/);
  // The rail's arrow mirrors too, and still flips when the list folds.
  await page.setViewportSize({ width: 1280, height: 800 });
  const fold = page.locator(".desktop-rail .rail-collapse");
  await expect(fold).toBeVisible();
  expect(await transform(fold.locator("svg"))).toBe(flipped);
  await fold.click();
  await expect(page.locator("#app")).toHaveClass(/list-collapsed/);
  await expect.poll(() => transform(fold.locator("svg"))).toBe("none");
  await fold.click();
  // The new agent's 34px avatar pencil answers over 44px too.
  await page.goto("/app/new-agent");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  const pencil = page.locator(".pencil");
  await expect(pencil).toBeVisible();
  expect((await pencil.boundingBox()).width).toBeLessThan(44);
  expect(await pseudo(pencil, "::before")).toEqual({ width: 44, height: 44 });
});

test.describe("on a light device", () => {
  test.use({ colorScheme: "light" });
  test("a first visit follows the device; a toast with an action waits while reached for", async ({
    page,
    context,
    cleanup,
  }) => {
    test.setTimeout(45_000);
    const data = fixture({ action: "init", empty: true });
    cleanup(async () => {
      fixture({ ...data, action: "cleanup" });
    });

    await signIn(context, data, null);
    await page.setViewportSize({ width: 360, height: 780 });
    await page.goto("/app/settings");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    await expect(page.locator('meta[name="theme-color"]')).toHaveAttribute("content", "#f7f5ef");
    // At 360px a row's second line may take three lines rather than be cut.
    const sub = page.locator(".signout .row small");
    await expect(sub).toBeVisible();
    expect(await sub.evaluate((el) => getComputedStyle(el).webkitLineClamp)).toBe("3");

    // The toast with an action («إعادة التحميل» after an unexpected error) stays while the
    // pointer is on it, then hides 2.4s after it leaves.
    await page.evaluate(() => window.dispatchEvent(new ErrorEvent("error", { message: "v38" })));
    const toast = page.locator("#toast.has-action");
    await expect(toast).toHaveClass(/show/);
    await toast.hover();
    await page.waitForTimeout(6_000);
    await expect(toast).toHaveClass(/show/);
    await page.mouse.move(2, 2);
    await page.waitForTimeout(1_000);
    await expect(toast).toHaveClass(/show/);
    await expect(toast).not.toHaveClass(/show/, { timeout: 3_000 });
  });
});

test("message text: signed numbers keep their sign, Latin-only reads LTR, a quote is one plain line", async ({
  page,
  context,
  cleanup,
}) => {
  const data = fixture({ action: "init", empty: true });
  cleanup(async () => {
    fixture({ ...data, action: "cleanup" });
  });

  await signIn(context, data);
  const headers = {
    "X-CSRF-Token": data.cookies.find((cookie) => cookie.name === "lonora_csrf").value,
  };
  const created = await context.request.post("/api/agents", {
    headers,
    data: {
      name: `V38 ${randomUUID()}`,
      trading_account_id: data.account,
      trading_symbol: data.symbol,
    },
  });
  expect(created.status()).toBe(201);
  const agent = await created.json();
  const opened = await context.request.post(`/api/agents/${agent.id}/conversation`, {
    headers,
    data: {},
  });
  expect(opened.ok()).toBeTruthy();
  const thread = await opened.json();
  const message = (seq, role, content, reply = null) => ({
    id: `v38-${seq}`,
    thread_id: thread.id,
    agent_id: agent.id,
    seq,
    role,
    content,
    reply_to: reply,
    attachment_ids: [],
    created_at: "2026-11-19T10:00:00Z",
  });
  const rows = [
    message(1, "assistant", "ربح الحساب (+$239) اليوم وتراجع −1.5% أمس"),
    message(2, "assistant", "Hello, ready?"),
    message(3, "assistant", "XAUUSD ارتفع اليوم"),
    message(
      4,
      "assistant",
      "### الملخص\n**الذهب** ارتفع\n\n| الزوج | التغير |\n|---|---|\n| XAUUSD | +1.5% |",
    ),
    message(5, "user", "شكرًا", "v38-4"),
    message(
      6,
      "assistant",
      "Gold is holding above the weekly pivot and momentum is fading into the close, so I wait for a retest past two pips.",
    ),
  ];
  await page.route(`**/api/threads/${thread.id}/messages*`, (route) =>
    route.fulfill({ json: rows }),
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/app/${agent.id}`);
  const bubble = (seq) => page.locator(`[data-message-id='v38-${seq}']`);
  await expect(bubble(5)).toBeVisible();
  await expect(bubble(1).locator('bdi[dir="ltr"]')).toHaveText(["+$239", "−1.5%"]);
  await expect(bubble(2).locator(".text")).toHaveAttribute("dir", "ltr");
  await expect(bubble(3).locator(".text")).toHaveAttribute("dir", "rtl");
  // Its wrapped lines start on its own side too: the Latin bubble lines up on the left.
  const align = (seq) =>
    bubble(seq)
      .locator(".bubble")
      .evaluate((el) => getComputedStyle(el).textAlign);
  expect(await align(2)).toBe("left");
  expect(await align(3)).toBe("right");
  await expect(bubble(4).locator('td bdi[dir="ltr"]')).toHaveText("+1.5%");
  // The quote reads one plain line: no «###», «**» or table pipes.
  await expect(bubble(5).locator(".quote-text")).toHaveText(
    "الملخص الذهب ارتفع الزوج · التغير XAUUSD · \u2066+1.5%\u2069",
  );
  // The time ends the words' last line: on the left of Arabic words, on the right of Latin
  // ones, never before the words, in either interface.
  const timeSide = (seq) =>
    bubble(seq)
      .locator(".bubble")
      .evaluate((el) => {
        const range = document.createRange();
        range.selectNodeContents(el.querySelector(":scope > .text"));
        const lines = [...range.getClientRects()];
        const last = lines[lines.length - 1];
        const meta = el.querySelector(":scope > .meta").getBoundingClientRect();
        const box = el.getBoundingClientRect();
        const side = meta.left + meta.width / 2 > box.left + box.width / 2 ? "right" : "left";
        // On the last line itself it sits past the words' end.
        const sameLine = meta.top < last.bottom && meta.bottom > last.top;
        const past = side === "right" ? meta.left >= last.right - 1 : meta.right <= last.left + 1;
        return sameLine && !past ? "overlap" : side;
      });
  expect(await timeSide(6)).toBe("right");
  expect(await timeSide(3)).toBe("left");
  await page.evaluate(() => localStorage.setItem("lonora.locale", "en"));
  await page.reload();
  await expect(bubble(6)).toBeVisible();
  expect(await timeSide(6)).toBe("right");
  expect(await timeSide(3)).toBe("left");
});

test("the one-time mic tip never covers a card or a message, and a scroll ends it", async ({
  page,
  context,
  cleanup,
}) => {
  const data = fixture({ action: "init", empty: true });
  cleanup(async () => {
    fixture({ ...data, action: "cleanup" });
  });

  await signIn(context, data);
  const headers = {
    "X-CSRF-Token": data.cookies.find((cookie) => cookie.name === "lonora_csrf").value,
  };
  const agent = await (
    await context.request.post("/api/agents", {
      headers,
      data: {
        name: `V38 tip ${randomUUID()}`,
        trading_account_id: data.account,
        trading_symbol: data.symbol,
      },
    })
  ).json();
  const thread = await (
    await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
  ).json();
  const pending = {
    id: randomUUID(),
    thread_id: thread.id,
    agent_id: agent.id,
    run_id: "run",
    created_at: "2026-11-19T10:00:00Z",
    timeline_seq: 1,
    status: "pending",
    reason: "Breakout above 100 on the London open",
    requests: [{ action: "buy", symbol: "XAUUSD", volume: "0.1", stop_loss: "95" }],
    results: [],
    expires_at: null,
    tolerance: "1.5",
    reference_price: "101",
  };
  let approvals = [pending];
  let messages = [];
  await page.route("**/api/trading/approvals?*", (route) => route.fulfill({ json: approvals }));
  await page.route(`**/api/threads/${thread.id}/messages*`, (route) =>
    route.fulfill({ json: messages }),
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/app/${agent.id}`);
  await expect(page.locator(`[data-trade-approval="${pending.id}"]`)).toBeVisible();
  await page.waitForTimeout(1500);
  await expect(page.locator(".mic-tip")).toHaveCount(0);
  expect(await page.evaluate(() => localStorage.getItem("lonora.tips.mic"))).toBeNull();
  // With nothing fixed under it, it shows on a later visit, and the first scroll ends it: a
  // card scrolled under it is never covered.
  approvals = [];
  await page.reload();
  await expect(page.locator(".mic-tip")).toHaveClass(/show/);
  await page.getByTestId("transcript").dispatchEvent("scroll");
  await expect(page.locator(".mic-tip")).toHaveCount(0);
  // Never over a message either: with the latest bubbles under it, it waits.
  await page.evaluate(() => localStorage.removeItem("lonora.tips.mic"));
  messages = Array.from({ length: 24 }, (_, index) => ({
    id: `tip-${index + 1}`,
    thread_id: thread.id,
    agent_id: agent.id,
    seq: index + 1,
    role: index % 2 ? "assistant" : "user",
    content: `حلّل الذهب وأخبرني قبل أي صفقة ${index + 1}`,
    reply_to: null,
    attachment_ids: [],
    created_at: "2026-11-19T10:00:00Z",
  }));
  await page.reload();
  await expect(page.getByText("حلّل الذهب وأخبرني قبل أي صفقة 24")).toBeVisible();
  await page.waitForTimeout(1500);
  await expect(page.locator(".mic-tip")).toHaveCount(0);
  expect(await page.evaluate(() => localStorage.getItem("lonora.tips.mic"))).toBeNull();
});
