import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

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
}) => {
  const data = fixture({ action: "init", empty: true });
  try {
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

    const rail = page.locator(".desktop-rail");
    const fold = rail.locator(".rail-collapse");
    await expect(fold).toHaveAttribute("aria-label", "طي قائمة المحادثات");
    expect(await fold.locator("svg").evaluate((svg) => getComputedStyle(svg).transform)).toBe(
      "none",
    );
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
  } finally {
    fixture({ ...data, action: "cleanup" });
  }
});

test.describe("on a light device", () => {
  test.use({ colorScheme: "light" });
  test("a first visit follows the device; a toast with an action waits while reached for", async ({
    page,
    context,
  }) => {
    test.setTimeout(45_000);
    const data = fixture({ action: "init", empty: true });
    try {
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
    } finally {
      fixture({ ...data, action: "cleanup" });
    }
  });
});

test("message text: signed numbers keep their sign, Latin-only reads LTR, a quote is one plain line", async ({
  page,
  context,
}) => {
  const data = fixture({ action: "init", empty: true });
  try {
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
    await expect(bubble(4).locator('td bdi[dir="ltr"]')).toHaveText("+1.5%");
    // The quote reads one plain line: no «###», «**» or table pipes.
    await expect(bubble(5).locator(".quote-text")).toHaveText(
      "الملخص الذهب ارتفع الزوج · التغير XAUUSD · \u2066+1.5%\u2069",
    );
  } finally {
    fixture({ ...data, action: "cleanup" });
  }
});
