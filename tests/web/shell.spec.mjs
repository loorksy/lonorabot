import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

/* The reference shell (docs/ui-reference/Lonora-Desktop-37.html): phone and desktop layouts in
   Arabic, dark and light; the tab pager; the glass edge; the dissolving title; the sheet system;
   Escape and Back. Gestures are driven with synthetic touch pointers, which the handlers accept. */
function fixture(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}
async function signIn(context, data, { locale = "ar", theme = "dark" } = {}) {
  await context.addCookies(
    data.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript(
    ({ locale, theme }) => {
      localStorage.setItem("lonora.locale", locale);
      localStorage.setItem("lonora.theme", JSON.stringify(theme));
    },
    { locale, theme },
  );
}
async function tradingAgent(context, data) {
  const headers = {
    "X-CSRF-Token": data.cookies.find((cookie) => cookie.name === "lonora_csrf").value,
  };
  const response = await context.request.post("/api/agents", {
    headers,
    data: {
      name: `Shell ${randomUUID()}`,
      trading_account_id: data.account,
      trading_symbol: data.symbol,
    },
  });
  expect(response.status()).toBe(201);
  return { agent: await response.json(), headers };
}
/** A finger: pointer events the shell's document listeners receive (pointerType touch). */
async function swipe(page, selector, from, to, { steps = 8, hold = 0 } = {}) {
  await page.evaluate(
    async ({ selector, from, to, steps, hold }) => {
      const target = document.querySelector(selector);
      const fire = (type, x, y) =>
        target.dispatchEvent(
          new PointerEvent(type, {
            bubbles: true,
            cancelable: true,
            composed: true,
            pointerId: 7,
            pointerType: "touch",
            isPrimary: true,
            clientX: x,
            clientY: y,
          }),
        );
      const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
      fire("pointerdown", from.x, from.y);
      for (let i = 1; i <= steps; i++) {
        await wait(16);
        fire(
          "pointermove",
          from.x + ((to.x - from.x) * i) / steps,
          from.y + ((to.y - from.y) * i) / steps,
        );
      }
      if (hold) await wait(hold);
      fire("pointerup", to.x, to.y);
    },
    { selector, from, to, steps, hold },
  );
}

test.describe("phone shell (390×844, Arabic)", () => {
  test("tab bar, lens, pager swipe and tap, glass edge and the dissolving title", async ({
    page,
    context,
  }) => {
    const data = fixture({ action: "init", empty: true });
    try {
      await signIn(context, data);
      await page.setViewportSize({ width: 390, height: 844 });
      const errors = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.goto("/app");
      await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
      const nav = page.locator("nav.tabbar");
      await expect(nav).toHaveAttribute("aria-label", "التنقل الرئيسي");
      await expect(nav.getByRole("button")).toHaveCount(4);
      // Unread chats other specs leave behind add a badge to the tab's name: match the tab.
      await expect(nav.locator('button[data-root="chats"]')).toContainText("المحادثات");
      await expect(nav.locator('button[data-root="chats"]')).toHaveAttribute(
        "aria-current",
        "page",
      );
      await expect(page.locator(".topbar")).toHaveAttribute("data-route", "chats");
      await expect(page.locator("header.chats-header h1")).toHaveText("Lonora");
      // The lens sits under the active tab.
      const lens = nav.locator(".nav-lens");
      await expect.poll(async () => (await lens.boundingBox())?.width).toBeGreaterThan(60);
      await page.screenshot({ path: ".runtime/shell/phone-chats-dark.png" });

      // Tap: المستجدات slides in; the bare tab has no title bar, the title lives in the page.
      await nav.getByRole("button", { name: /^المستجدات/ }).click();
      await expect(page).toHaveURL(/\/app\/updates$/);
      await expect(page.locator(".topbar")).toHaveClass(/bare/);
      const title = page.locator("main > .large-title");
      await expect(title).toHaveText(/المستجدات/);
      await expect(nav.getByRole("button", { name: /^المستجدات/ })).toHaveAttribute(
        "aria-current",
        "page",
      );
      await expect.poll(() => page.locator(".pager-ghost").count()).toBe(0);
      await expect(page.locator("#app")).not.toHaveClass(/paging/);

      // Glass edge and title dissolve, measured at scroll offsets.
      await page.evaluate(() => {
        const main = document.getElementById("view-scroll");
        const filler = document.createElement("div");
        filler.style.height = "3000px";
        main.appendChild(filler);
      });
      const main = page.locator("#view-scroll");
      const read = async (top) => {
        await main.evaluate((element, top) => {
          element.scrollTop = top;
          element.dispatchEvent(new Event("scroll"));
        }, top);
        return page.evaluate(() => {
          const title = document.querySelector("main > .large-title");
          return {
            edge: document.querySelector(".topbar").style.getPropertyValue("--edge"),
            opacity: title.style.opacity,
            transform: title.style.transform,
            crisp: title.querySelector(".lt-crisp").style.opacity,
            blur: title.querySelector(".lt-blur").style.opacity,
            filter: title.style.filter,
          };
        });
      };
      // The browser serialises inline numbers (1.000 → 1); the custom property keeps its text.
      const num = (value) => Number.parseFloat(value);
      const rest = await read(0);
      expect(rest.edge).toBe("0.000");
      expect(num(rest.opacity)).toBe(1);
      expect(rest.transform).toBe("");
      expect(rest.filter).toBe("");
      const half = await read(20); // p = 0.5 of a 40px title
      expect(num(half.opacity)).toBeCloseTo(0.35, 3);
      const moved = half.transform.match(/^translateY\(([\d.]+)px\) scale\(([\d.]+)\)$/);
      expect(moved).not.toBeNull();
      expect(num(moved[1])).toBeCloseTo(9, 1); // parallax 0.45 of 20px
      expect(num(moved[2])).toBeCloseTo(0.96, 3); // −8% at p = 1
      expect(num(half.crisp)).toBeCloseTo(0.5, 3);
      expect(num(half.blur)).toBeCloseTo(0.5, 3);
      expect(half.edge).toBe("0.000"); // rest = 60% of the title: 24px
      const edge = await read(28);
      expect(edge.edge).toBe("0.250");
      const gone = await read(60);
      expect(num(gone.opacity)).toBe(0);
      expect(gone.edge).toBe("1.000");
      // Scrolling down folds the tab bar to icons; a touch unfolds it.
      await main.evaluate((element) => {
        element.scrollTop = 200;
        element.dispatchEvent(new Event("scroll"));
        element.scrollTop = 260;
        element.dispatchEvent(new Event("scroll"));
      });
      await expect(nav).toHaveClass(/compact/);
      await read(0);

      // Swipe (RTL: finger right → the next tab enters from the left). The incoming page is a
      // real render beside the current one; past 50% the release commits.
      const swiped = swipe(
        page,
        "#view-scroll",
        { x: 60, y: 500 },
        { x: 330, y: 500 },
        { steps: 10 },
      );
      await expect(page.locator("main.pager-ghost")).toHaveCount(1);
      await expect(page.locator("#app")).toHaveClass(/paging/);
      await swiped;
      await expect(page).toHaveURL(/\/app\/tasks$/);
      await expect(page.locator("main > .large-title")).toHaveText(/المهام/);
      await expect.poll(() => page.locator(".pager-ghost").count()).toBe(0);
      await expect(page.locator("#app")).not.toHaveClass(/paging/);
      expect(await page.locator("#view-scroll").evaluate((m) => m.style.transform)).toBe("");
      // A short drag springs back.
      await swipe(page, "#view-scroll", { x: 200, y: 500 }, { x: 240, y: 500 }, { steps: 4 });
      await expect(page).toHaveURL(/\/app\/tasks$/);
      await expect.poll(() => page.locator(".pager-ghost").count()).toBe(0);
      // Light theme: the frame takes the reference's ivory background (the sign-in init script
      // writes the theme on every load, so a later init script switches it).
      await context.addInitScript(() =>
        localStorage.setItem("lonora.theme", JSON.stringify("light")),
      );
      await page.reload();
      await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
      expect(
        await page.locator("#app").evaluate((app) => getComputedStyle(app).backgroundColor),
      ).toBe("rgb(247, 245, 239)");
      await page.screenshot({ path: ".runtime/shell/phone-tasks-light.png" });
      expect(errors).toEqual([]);
    } finally {
      fixture({ ...data, action: "cleanup" });
    }
  });

  test("sheets: open, Escape, Back, drag to dismiss, expandable detents; the chat's back button", async ({
    page,
    context,
  }) => {
    const data = fixture({ action: "init", empty: true });
    let trading;
    try {
      await signIn(context, data);
      trading = await tradingAgent(context, data);
      const { agent } = trading;
      await page.setViewportSize({ width: 390, height: 844 });
      await page.goto("/app");
      const dialog = page.locator("#dialog");
      await page.getByRole("button", { name: "محادثة جديدة", exact: true }).click();
      await expect(dialog).toHaveAttribute("open", "");
      await expect(dialog).toHaveAttribute("aria-label", "محادثة جديدة");
      await expect(dialog.getByRole("button", { name: "وكيل جديد" })).toBeVisible();
      await expect(dialog.locator(`[data-new-chat-agent="${agent.id}"]`)).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(dialog).not.toHaveAttribute("open", "");
      // Back closes the sheet before it changes the route.
      await page.getByRole("button", { name: "محادثة جديدة", exact: true }).click();
      await expect(dialog).toHaveAttribute("open", "");
      await page.goBack();
      await expect(dialog).not.toHaveAttribute("open", "");
      await expect(page).toHaveURL(/\/app$/);
      // Drag the handle row down past the dismiss threshold.
      await page.getByRole("button", { name: "محادثة جديدة", exact: true }).click();
      await expect(dialog).toHaveAttribute("open", "");
      const top = await dialog.locator(".sheet-top").boundingBox();
      await swipe(
        page,
        "#dialog .sheet-top",
        { x: 195, y: top.y + 10 },
        { x: 195, y: top.y + 320 },
        { steps: 12, hold: 120 },
      );
      await expect(dialog).not.toHaveAttribute("open", "");
      // Open the chat: the conversation header, then its menu and the expandable chart sheet.
      await page.locator(`[data-inbox-agent-id="${agent.id}"]`).click();
      await expect(page).toHaveURL(new RegExp(`/app/${agent.id}`));
      await expect(page.locator(".chat-head .chat-name")).toContainText(agent.name);
      await page.getByRole("button", { name: "قائمة المحادثة", exact: true }).click();
      await page
        .getByRole("menu", { name: "قائمة المحادثة" })
        .getByRole("menuitem", { name: "الشارت" })
        .click();
      await expect(dialog).toHaveClass(/expandable/);
      // The chart sheet names the pair when the agent has one (chart.sheet, Q37).
      await expect(dialog).toHaveAttribute("aria-label", `الشارت ${agent.trading_symbol}`);
      const resting = (await dialog.boundingBox()).height;
      await dialog.getByRole("button", { name: "ملء الشاشة", exact: true }).click();
      await expect(dialog).toHaveClass(/expanded/);
      await expect(dialog.getByRole("button", { name: "تصغير", exact: true })).toBeVisible();
      await expect
        .poll(async () => (await dialog.boundingBox()).height)
        .toBeGreaterThan(resting + 100);
      await expect.poll(async () => (await dialog.boundingBox()).height).toBeGreaterThan(800);
      await dialog.getByRole("button", { name: "تصغير", exact: true }).click();
      await expect(dialog).not.toHaveClass(/expanded/);
      await page.keyboard.press("Escape");
      await expect(dialog).not.toHaveAttribute("open", "");
      // «معلومات الوكيل» opens the agent page; Back returns to the chat.
      await page.getByRole("button", { name: "قائمة المحادثة", exact: true }).click();
      await page.getByRole("menuitem", { name: "معلومات الوكيل" }).click();
      await expect(page).toHaveURL(new RegExp(`/app/agent/${agent.id}$`));
      await page.getByRole("button", { name: "رجوع", exact: true }).first().click();
      await expect(page).toHaveURL(new RegExp(`/app/${agent.id}$`));
      // Back from the chat returns to the list.
      await page.getByRole("button", { name: "رجوع", exact: true }).click();
      await expect(page).toHaveURL(/\/app$/);
      await expect(page.getByTestId("conversation-inbox")).toBeVisible();
    } finally {
      if (trading)
        await context.request.delete(`/api/agents/${trading.agent.id}`, {
          headers: trading.headers,
        });
      fixture({ ...data, action: "cleanup" });
    }
  });

  test("every page keeps its scroll: back, a tab round trip, a chat and back", async ({
    page,
    context,
  }) => {
    const data = fixture({ action: "init", empty: true });
    try {
      await signIn(context, data);
      await page.setViewportSize({ width: 390, height: 844 });
      await settingsScrollRoundTrip(page);
      const main = page.locator("#view-scroll");
      const nav = page.locator("nav.tabbar");
      await main.evaluate((element) => {
        element.scrollTop = 120;
      });
      await expect.poll(() => main.evaluate((element) => element.scrollTop)).toBe(120);
      await nav.locator('button[data-root="tasks"]').click();
      await expect(page).toHaveURL(/\/app\/tasks$/);
      await expect.poll(() => page.locator(".pager-ghost").count()).toBe(0);
      await nav.locator('button[data-root="settings"]').click();
      await expect(page).toHaveURL(/\/app\/settings$/);
      await expect.poll(() => main.evaluate((element) => element.scrollTop)).toBe(120);
      // The chat list rests past its filters, and stays so after a round trip or a chat.
      // While the list loads it is a skeleton without filters: the poll waits for them.
      const filters = () =>
        main.evaluate((element) => ({
          top: element.scrollTop,
          rest: element.querySelector(".list-filters")?.offsetHeight,
          opacity: element.querySelector(".list-filters")?.style.opacity,
          // The room to rest that way is the same on every visit.
          room: element.querySelector("#chat-rows")?.style.minHeight,
        }));
      await nav.locator('button[data-root="chats"]').click();
      await expect(page).toHaveURL(/\/app$/);
      await expect.poll(async () => (await filters()).opacity).toBe("0");
      const { rest, room } = await filters();
      await nav.locator('button[data-root="updates"]').click();
      await expect(page).toHaveURL(/\/app\/updates$/);
      await nav.locator('button[data-root="chats"]').click();
      await expect(page).toHaveURL(/\/app$/);
      await expect.poll(filters).toEqual({ top: rest, rest, opacity: "0", room });
      await page.locator("#chat-rows .row.thread").first().click();
      await expect(page.locator(".composer")).toBeVisible();
      await page.goBack();
      await expect(page).toHaveURL(/\/app$/);
      await expect.poll(filters).toEqual({ top: rest, rest, opacity: "0", room });
    } finally {
      fixture({ ...data, action: "cleanup" });
    }
  });

  test("a tab change moves the lens once, straight to the new tab", async ({ page, context }) => {
    const data = fixture({ action: "init", empty: true });
    try {
      await signIn(context, data);
      await page.setViewportSize({ width: 390, height: 844 });
      await page.goto("/app/updates");
      const nav = page.locator("nav.tabbar");
      await expect(nav.locator('button[data-root="updates"]')).toHaveAttribute(
        "aria-current",
        "page",
      );
      for (const [from, to] of [
        ["updates", "tasks"],
        ["tasks", "updates"],
        ["updates", "settings"],
      ]) {
        await expect(nav.locator(`button[data-root="${from}"]`)).toHaveAttribute(
          "aria-current",
          "page",
        );
        await page.waitForTimeout(500);
        const trace = await page.evaluate(async (to) => {
          const nav = document.querySelector("nav.tabbar");
          const lens = nav.querySelector(".nav-lens");
          const target = nav.querySelector(`button[data-root="${to}"]`);
          const left = () => lens.getBoundingClientRect().left;
          const xs = [left()];
          target.click();
          const end = performance.now() + 1500;
          while (performance.now() < end) {
            await new Promise(requestAnimationFrame);
            xs.push(left());
          }
          return { xs, goal: target.getBoundingClientRect().left };
        }, to);
        const { xs, goal } = trace;
        expect(Math.abs(xs.at(-1) - goal)).toBeLessThan(1);
        // Once the lens has reached the new tab it never leaves it again.
        const arrived = xs.findIndex((x) => Math.abs(x - goal) < 2);
        expect(arrived).toBeGreaterThan(0);
        for (const x of xs.slice(arrived)) expect(Math.abs(x - goal)).toBeLessThan(6);
        // On the way it only travels toward the new tab.
        const dir = Math.sign(goal - xs[0]);
        for (let i = 1; i < arrived; i++) expect((xs[i] - xs[i - 1]) * dir).toBeGreaterThan(-2);
      }
    } finally {
      fixture({ ...data, action: "cleanup" });
    }
  });
  test("popover menus: Back and Escape leave «النموذج» first, then close; the chip toggles its menu", async ({
    page,
    context,
  }) => {
    const data = fixture({ action: "init", empty: true });
    let trading;
    try {
      await signIn(context, data);
      trading = await tradingAgent(context, data);
      const { agent } = trading;
      await page.setViewportSize({ width: 390, height: 844 });
      await page.goto("/app");
      await page.locator(`[data-inbox-agent-id="${agent.id}"]`).click();
      await expect(page).toHaveURL(new RegExp(`/app/${agent.id}`));
      const chat = page.url();
      // The chat header keeps its own tight gap and padding, which leaves the title its room.
      expect(
        await page.locator("header.chat-head").evaluate((head) => {
          const style = getComputedStyle(head);
          return [style.columnGap, style.paddingInlineStart];
        }),
      ).toEqual(["2px", "6px"]);
      const chip = page.getByTestId("permission-chip");
      const menu = page.locator(".pop.mode-pop");
      const pages = menu.locator(".mp-pages");
      // Back closes the menu and stays in the chat.
      await chip.click();
      await expect(menu).toBeVisible();
      await page.goBack();
      await expect(menu).toHaveCount(0);
      expect(page.url()).toBe(chat);
      // From «النموذج», Back returns to the first page, then closes the menu.
      await chip.click();
      await menu.locator(".mp-model-row").click();
      await expect(pages).toHaveAttribute("data-page", "2");
      await page.goBack();
      await expect(pages).toHaveAttribute("data-page", "1");
      await expect(menu.locator(".mp-model-row")).toBeFocused();
      await page.goBack();
      await expect(menu).toHaveCount(0);
      expect(page.url()).toBe(chat);
      // Escape does the same, and a second tap on the chip closes its menu.
      await chip.click();
      await menu.locator(".mp-model-row").click();
      await expect(pages).toHaveAttribute("data-page", "2");
      await page.keyboard.press("Escape");
      await expect(pages).toHaveAttribute("data-page", "1");
      await expect(menu).toBeVisible();
      await chip.click();
      await expect(menu).toHaveCount(0);
      // Menus closed in the page leave no dead Back: one Back leaves the chat.
      await page.goBack();
      await expect(page).toHaveURL(/\/app$/);
    } finally {
      if (trading)
        await context.request.delete(`/api/agents/${trading.agent.id}`, {
          headers: trading.headers,
        });
      fixture({ ...data, action: "cleanup" });
    }
  });
  test("«النموذج» shows seven days of usage, hides a total it cannot price, and leads to the providers", async ({
    page,
    context,
  }) => {
    const data = fixture({ action: "init", empty: true });
    let trading;
    try {
      await signIn(context, data);
      trading = await tradingAgent(context, data);
      const { agent } = trading;
      const costs = [0, 0.5, 1, 0.25, 0, 2, 0.1];
      let unpriced = 0;
      const asked = [];
      await page.route("**/api/usage/agents**", (route) => {
        asked.push(new URL(route.request().url()).searchParams.toString());
        return route.fulfill({
          json: {
            days: 7,
            bucket: "day",
            agents: [],
            buckets: costs.map((cost_usd, index) => ({
              date: `2026-11-${String(5 + index).padStart(2, "0")}`,
              cost_usd,
              requests: cost_usd ? 3 : 0,
              unpriced_requests: index === 2 ? unpriced : 0,
            })),
          },
        });
      });
      await page.setViewportSize({ width: 390, height: 844 });
      await page.goto(`/app/${agent.id}`);
      const chip = page.getByTestId("permission-chip");
      const menu = page.locator(".pop.mode-pop");
      const bars = menu.locator(".mp-bar");
      await chip.click();
      await menu.locator(".mp-model-row").click();
      await expect(bars).toHaveCount(7);
      expect(asked[0]).toBe(`days=7&bucket=day&agent_id=${agent.id}`);
      await expect(menu.locator(".p2 .pop-title")).toContainText("آخر 7 أيام");
      await expect(bars.last()).toHaveClass(/\btoday\b/);
      // The dearest day fills the height; a day with no cost keeps a sliver.
      expect(
        await bars.evaluateAll((all) => all.map((bar) => bar.style.getPropertyValue("--h"))),
      ).toEqual(["4%", "25%", "50%", "13%", "4%", "100%", "5%"]);
      await expect(bars.first().locator("small")).toHaveText("خ");
      await expect(menu.locator(".mp-tot")).toHaveText("$3.85 خلال 7 أيام · دون سقف لهذا الوكيل");
      await expect(menu.locator(".mp-usage")).toHaveAttribute(
        "aria-label",
        "استهلاك آخر 7 أيام: $3.85",
      );
      // Requests with no list price: no amount is shown as if it were the whole cost.
      await chip.click();
      await expect(menu).toHaveCount(0);
      unpriced = 4;
      await chip.click();
      await menu.locator(".mp-model-row").click();
      await expect(menu.locator(".mp-tot")).toHaveText([
        "— خلال 7 أيام · دون سقف لهذا الوكيل",
        "4 طلبات دون سعر معلن",
      ]);
      await expect(bars.nth(2)).toHaveAttribute("title", /: —$/);
      await menu.getByRole("menuitem", { name: "ربط مزوّد نماذج" }).click();
      await expect(page).toHaveURL(/\/app\/providers$/);
      await expect(menu).toHaveCount(0);
    } finally {
      if (trading)
        await context.request.delete(`/api/agents/${trading.agent.id}`, {
          headers: trading.headers,
        });
      fixture({ ...data, action: "cleanup" });
    }
  });
  test("a trading agent with no account is led to choose one, or to link the first", async ({
    page,
    context,
  }) => {
    const data = fixture({ action: "init", empty: true });
    let trading;
    try {
      await signIn(context, data);
      trading = await tradingAgent(context, data);
      const { agent } = trading;
      // The server gives a trading agent its account when it is created; one whose account
      // is gone is what this agent looks like on the wire.
      await page.route("**/api/agents", async (route) => {
        const response = await route.fetch();
        const rows = await response.json();
        return route.fulfill({
          response,
          json: rows.map((row) =>
            row.id === agent.id
              ? { ...row, template: "trading", trading_account_id: null, trading_symbol: null }
              : row,
          ),
        });
      });
      await page.setViewportSize({ width: 390, height: 844 });
      await page.goto(`/app/${agent.id}`);
      const chip = page.locator("button.no-trade");
      const sheet = page.locator("#dialog");
      // The fixture's account is linked: the agent only has to choose it.
      await expect(chip).toHaveAttribute("aria-label", "دون تنفيذ: لم يُختر حساب تداول");
      await chip.click();
      await expect(sheet.locator(".state-lead")).toContainText("لا يرتبط");
      await sheet.getByRole("button", { name: "اختيار حساب التداول" }).click();
      await expect(page).toHaveURL(new RegExp(`/app/identity/${agent.id}$`));
      await expect(page.locator("select[name=account]")).toBeVisible();
      // No linked account at all (a switched-off one does not count): link the first.
      await page.route("**/api/trading/connections", (route) =>
        route.fulfill({ json: [{ id: "off", payload: { enabled: false }, state: {} }] }),
      );
      await page.goto(`/app/${agent.id}`);
      await expect(chip).toHaveAttribute("aria-label", "دون تنفيذ: لا يوجد حساب تداول مرتبط");
      await chip.click();
      await expect(sheet.locator(".state-lead")).toContainText("لا يوجد حساب تداول مرتبط");
      await sheet.getByRole("button", { name: "ربط حساب تداول" }).click();
      await expect(page).toHaveURL(/\/app\/broker$/);
    } finally {
      if (trading)
        await context.request.delete(`/api/agents/${trading.agent.id}`, {
          headers: trading.headers,
        });
      fixture({ ...data, action: "cleanup" });
    }
  });
});

test.describe("phone with touch (390×844, Arabic)", () => {
  test.use({ hasTouch: true });
  test("the tap that dismisses the chip menu does not also go back", async ({ page, context }) => {
    const data = fixture({ action: "init", empty: true });
    let trading;
    try {
      await signIn(context, data);
      trading = await tradingAgent(context, data);
      await page.setViewportSize({ width: 390, height: 844 });
      await page.goto(`/app/${trading.agent.id}`);
      const chat = page.url();
      const chip = page.getByTestId("permission-chip");
      const menu = page.locator(".pop.mode-pop");
      const back = page.locator(".chat-back");
      await chip.tap();
      await expect(menu).toBeVisible();
      // The menu's scrim covers the header: the tap lands where the back button is.
      const at = await back.boundingBox();
      await page.touchscreen.tap(at.x + at.width / 2, at.y + at.height / 2);
      await expect(menu).toHaveCount(0);
      expect(page.url()).toBe(chat);
      await back.tap();
      await expect(page).toHaveURL(/\/app$/);
    } finally {
      if (trading)
        await context.request.delete(`/api/agents/${trading.agent.id}`, {
          headers: trading.headers,
        });
      fixture({ ...data, action: "cleanup" });
    }
  });
  test("the permission menu forms out of the composer; a drag down folds it back, a sideways drag leaves «النموذج»", async ({
    page,
    context,
  }) => {
    const data = fixture({ action: "init", empty: true });
    let trading;
    try {
      await signIn(context, data);
      trading = await tradingAgent(context, data);
      await page.setViewportSize({ width: 390, height: 844 });
      await page.goto(`/app/${trading.agent.id}`);
      const chat = page.url();
      const chip = page.getByTestId("permission-chip");
      const menu = page.locator(".pop.mode-pop");
      const card = page.locator(".composer-card");
      const pages = menu.locator(".mp-pages");
      await chip.tap();
      await expect(menu).toHaveClass(/\bmorph\b/);
      await expect(card).toHaveClass(/\bmp-open\b/);
      await expect(page.locator(".mp-scrim")).toHaveClass(/\bon\b/);
      await expect(menu).toHaveClass(/\bsettled\b/);
      // Joined to the composer: as wide as it less its corners and fillets, standing on its top edge.
      const at = await page.evaluate(() => {
        const c = document.querySelector(".composer-card").getBoundingClientRect();
        const p = document.querySelector(".pop.morph .mp-in").getBoundingClientRect();
        return { card: [c.left, c.top, c.width], panel: [p.left, p.bottom, p.width] };
      });
      expect(at.panel[0]).toBeCloseTo(at.card[0] + 26, 0);
      expect(at.panel[1]).toBeCloseTo(at.card[1], 0);
      expect(at.panel[2]).toBeCloseTo(at.card[2] - 52, 0);
      const row = await menu.locator(".mp-model-row").boundingBox();
      const x = row.x + row.width / 2;
      const y = row.y + row.height / 2;
      // A short drag springs it back open.
      await swipe(page, ".pop.morph .mp-model-row", { x, y }, { x, y: y + 30 }, { hold: 200 });
      await expect(menu).toHaveClass(/\bsettled\b/);
      await expect(menu).not.toHaveAttribute("aria-hidden", "true");
      // Sideways toward where «النموذج» came from: back to the first page.
      await menu.locator(".mp-model-row").tap();
      await expect(pages).toHaveAttribute("data-page", "2");
      await swipe(page, ".pop.morph .p2 .mp-head", { x: 300, y }, { x: 100, y });
      await expect(pages).toHaveAttribute("data-page", "1");
      await expect(menu).toBeVisible();
      // Down past 28%: it folds back into the composer and is gone; the chat stays.
      await swipe(page, ".pop.morph .mp-model-row", { x, y }, { x, y: y + 260 });
      await expect(menu).toHaveAttribute("aria-hidden", "true");
      await expect(card).not.toHaveClass(/\bmp-open\b/);
      await expect(chip).toHaveAttribute("aria-expanded", "false");
      await expect(menu).toHaveCount(0);
      await expect(page.locator(".mp-scrim")).toHaveCount(0);
      expect(page.url()).toBe(chat);
    } finally {
      if (trading)
        await context.request.delete(`/api/agents/${trading.agent.id}`, {
          headers: trading.headers,
        });
      fixture({ ...data, action: "cleanup" });
    }
  });
  test("with reduced motion the permission menu fades in place and out", async ({
    page,
    context,
  }) => {
    const data = fixture({ action: "init", empty: true });
    let trading;
    try {
      await signIn(context, data);
      trading = await tradingAgent(context, data);
      await page.emulateMedia({ reducedMotion: "reduce" });
      await page.setViewportSize({ width: 390, height: 844 });
      await page.goto(`/app/${trading.agent.id}`);
      const chip = page.getByTestId("permission-chip");
      const menu = page.locator(".pop.mode-pop");
      await chip.tap();
      await expect(menu).toHaveClass(/\bfade\b/);
      await expect(menu).toHaveClass(/\bsettled\b/);
      await chip.tap();
      await expect(menu).toHaveClass(/\bleaving\b/);
      await expect(menu).toHaveCount(0);
    } finally {
      if (trading)
        await context.request.delete(`/api/agents/${trading.agent.id}`, {
          headers: trading.headers,
        });
      fixture({ ...data, action: "cleanup" });
    }
  });
});

/** Leave the settings page scrolled, open an inner page, come back: the list is where it was.
    The positions stay within the short list's travel on a phone. */
async function settingsScrollRoundTrip(page) {
  await page.goto("/app/settings");
  const main = page.locator("#view-scroll");
  await expect(page.getByText("الإشعارات والتواصل")).toBeVisible();
  await main.evaluate((element) => {
    element.scrollTop = 160;
  });
  await expect.poll(() => main.evaluate((element) => element.scrollTop)).toBe(160);
  await page.getByText("الإشعارات والتواصل").click();
  await expect(page).toHaveURL(/\/app\/notify-settings$/);
  await page.goBack();
  await expect(page).toHaveURL(/\/app\/settings$/);
  await expect.poll(() => main.evaluate((element) => element.scrollTop)).toBe(160);
}

test.describe("desktop shell (1280×800, Arabic)", () => {
  test("a window narrowed to the phone layout takes the open permission menu with it", async ({
    page,
    context,
  }) => {
    const data = fixture({ action: "init", empty: true });
    let trading;
    try {
      await signIn(context, data);
      trading = await tradingAgent(context, data);
      await page.setViewportSize({ width: 1280, height: 800 });
      await page.goto(`/app/${trading.agent.id}`);
      const menu = page.locator(".pop.mode-pop");
      await page.getByTestId("permission-chip").click();
      await expect(menu).toHaveClass(/\bsettled\b/);
      await page.setViewportSize({ width: 700, height: 700 });
      await expect(menu).toHaveCount(0);
      await expect(page.locator(".mp-scrim")).toHaveCount(0);
      await expect(page.getByTestId("permission-chip")).toHaveAttribute("aria-expanded", "false");
    } finally {
      if (trading)
        await context.request.delete(`/api/agents/${trading.agent.id}`, {
          headers: trading.headers,
        });
      fixture({ ...data, action: "cleanup" });
    }
  });
  test("the press that dismisses the list menu does not open the row beneath", async ({
    page,
    context,
  }) => {
    const data = fixture({ action: "init", empty: true });
    let trading;
    try {
      await signIn(context, data);
      trading = await tradingAgent(context, data);
      await page.setViewportSize({ width: 1280, height: 800 });
      await page.goto("/app");
      const more = page.locator(".desktop-list [aria-haspopup=menu]");
      const menu = page.locator(".pop[role=menu]");
      const row = page.locator(`.desktop-list [data-inbox-agent-id="${trading.agent.id}"]`);
      await more.click();
      await expect(menu).toBeVisible();
      await more.click();
      await expect(menu).toHaveCount(0);
      await more.click();
      await expect(menu).toBeVisible();
      await row.click();
      await expect(menu).toHaveCount(0);
      await expect(page).toHaveURL(/\/app$/);
      await row.click();
      await expect(page).toHaveURL(new RegExp(`/app/${trading.agent.id}`));
    } finally {
      if (trading)
        await context.request.delete(`/api/agents/${trading.agent.id}`, {
          headers: trading.headers,
        });
      fixture({ ...data, action: "cleanup" });
    }
  });

  test("the settings page keeps its scroll across an inner page and a rail round trip", async ({
    page,
    context,
  }) => {
    const data = fixture({ action: "init", empty: true });
    try {
      await signIn(context, data);
      await page.setViewportSize({ width: 1280, height: 800 });
      await settingsScrollRoundTrip(page);
      const rail = page.locator(".desktop-rail");
      await rail.getByRole("button", { name: "المهام", exact: true }).click();
      await expect(page).toHaveURL(/\/app\/tasks$/);
      await rail.getByRole("button", { name: "الإعدادات", exact: true }).click();
      await expect(page).toHaveURL(/\/app\/settings$/);
      await expect
        .poll(() => page.locator("#view-scroll").evaluate((element) => element.scrollTop))
        .toBe(160);
    } finally {
      fixture({ ...data, action: "cleanup" });
    }
  });
  for (const theme of ["dark", "light"]) {
    test(`rail, list pane, welcome and the solid header (${theme})`, async ({ page, context }) => {
      const data = fixture({ action: "init", empty: true });
      try {
        await signIn(context, data, { theme });
        await page.setViewportSize({ width: 1280, height: 800 });
        await page.goto("/app");
        await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
        await expect(page.locator("nav.tabbar")).toHaveCount(0);
        const rail = page.locator(".desktop-rail");
        await expect(rail).toBeVisible();
        await expect(rail.getByRole("button", { name: "المحادثات", exact: true })).toHaveAttribute(
          "aria-current",
          "page",
        );
        await expect(page.locator(".desktop-list h2")).toHaveText("المحادثات");
        await expect(page.locator(".desktop-content")).toHaveClass(/is-home/);
        await expect(page.locator(".welcome h2")).toContainText("مرحبًا");
        await expect(page.locator(".welcome")).toContainText("ماذا سنفعل اليوم مع وكلائك؟");
        await expect(page.locator(".welcome")).toContainText("الصلاحيات مستقلة لكل وكيل");
        expect(
          await page.locator("#app").evaluate((app) => getComputedStyle(app).backgroundColor),
        ).toBe(theme === "light" ? "rgb(247, 245, 239)" : "rgb(11, 12, 16)");
        await page.screenshot({ path: `.runtime/shell/desktop-home-${theme}.png` });
        await rail.getByRole("button", { name: "المستجدات", exact: true }).click();
        await expect(page).toHaveURL(/\/app\/updates$/);
        await expect(page.locator(".topbar header h1")).toHaveText("المستجدات");
        await expect(page.locator(".topbar")).not.toHaveClass(/bare/);
        // The list collapses from the rail and the state is not persisted.
        await rail.getByRole("button", { name: "طي قائمة المحادثات" }).click();
        await expect(page.locator("#app")).toHaveClass(/list-collapsed/);
        await page.reload();
        await expect(page.locator("#app")).not.toHaveClass(/list-collapsed/);
        // Sheets are centred modals: the welcome's «محادثة جديدة» opens one; Escape closes it.
        await rail.getByRole("button", { name: "المحادثات", exact: true }).click();
        await page.locator(".welcome").getByRole("button", { name: "محادثة جديدة" }).click();
        const dialog = page.locator("#dialog");
        await expect(dialog).toHaveAttribute("open", "");
        const box = await dialog.boundingBox();
        expect(box.width).toBeLessThanOrEqual(560);
        expect(Math.abs(box.x + box.width / 2 - 640)).toBeLessThan(8);
        await page.screenshot({ path: `.runtime/shell/desktop-sheet-${theme}.png` });
        await page.keyboard.press("Escape");
        await expect(dialog).not.toHaveAttribute("open", "");
        // ⌘/Ctrl / opens the shortcuts sheet.
        await page.keyboard.press("Control+/");
        await expect(dialog).toHaveAttribute("aria-label", "اختصارات لوحة المفاتيح");
        await page.keyboard.press("Escape");
      } finally {
        fixture({ ...data, action: "cleanup" });
      }
    });
  }
  test("the rail follows the section, Ctrl+K opens a folded list, the shortcuts are keys", async ({
    page,
    context,
  }) => {
    const data = fixture({ action: "init", empty: true });
    try {
      await signIn(context, data);
      await page.setViewportSize({ width: 1280, height: 800 });
      const rail = page.locator(".desktop-rail");
      const current = (name) =>
        expect(rail.getByRole("button", { name, exact: true })).toHaveAttribute(
          "aria-current",
          "page",
        );
      await page.goto("/app/artifacts");
      await current("الإعدادات");
      await page.goto("/app/recovery");
      await current("الإعدادات");
      await page.goto("/app/new-schedule");
      await current("المهام");
      await page.goto("/app/my-profile");
      await expect(page).toHaveURL(/\/app\/owner$/);
      await page.goto("/app/reach-me");
      await expect(page).toHaveURL(/\/app\/notify-settings$/);
      await page.goto("/app");
      await rail.getByRole("button", { name: "طي قائمة المحادثات" }).click();
      await expect(page.locator("#app")).toHaveClass(/list-collapsed/);
      await page.keyboard.press("Control+k");
      await expect(page.locator("#app")).not.toHaveClass(/list-collapsed/);
      await expect(page.locator("#desktop-search")).toBeFocused();
      await page.keyboard.press("Control+/");
      const rows = page.locator("#dialog .kbd-list .row");
      const show = rows.filter({ hasText: "عرض الاختصارات" });
      await expect(show.locator("kbd")).toHaveText(["Ctrl", "/"]);
      const step = rows.filter({ hasText: "المحادثة السابقة / التالية" });
      await expect(step.locator("kbd")).toHaveCount(4);
    } finally {
      fixture({ ...data, action: "cleanup" });
    }
  });
});

test("an unknown address shows the not-found page without a chat header", async ({
  page,
  context,
}) => {
  const data = fixture({ action: "init", empty: true });
  try {
    await signIn(context, data);
    for (const size of [
      { width: 390, height: 844 },
      { width: 1280, height: 800 },
    ]) {
      await page.setViewportSize(size);
      for (const path of ["/app/nope-route", "/app/g/nope-group"]) {
        await page.goto(path);
        await expect(page.locator("main .state-page h2")).toHaveText("الصفحة غير موجودة");
        await expect(page.locator(".chat-head")).toHaveCount(0);
        await expect(page.locator(".topbar")).toHaveAttribute("data-route", "not-found");
      }
    }
  } finally {
    fixture({ ...data, action: "cleanup" });
  }
});

test("a server that does not answer at startup shows maintenance, which leaves when it answers", async ({
  page,
  context,
}) => {
  const data = fixture({ action: "init", empty: true });
  try {
    await signIn(context, data, { locale: "en" });
    await page.setViewportSize({ width: 390, height: 844 });
    let down = true;
    const gateway = (route) => (down ? route.fulfill({ status: 502, body: "" }) : route.continue());
    await page.route("**/api/onboarding", gateway);
    await page.route("**/health", gateway);
    await page.goto("/app");
    const heading = page.getByRole("heading", { name: "Lonora is under maintenance" });
    await expect(heading).toBeVisible();
    await expect(page.locator(".auth-card")).toHaveCount(0);
    await page.getByRole("button", { name: "Try again" }).click();
    await expect(
      page.getByText("Maintenance is still in progress. Try again shortly"),
    ).toBeVisible();
    down = false;
    await page.getByRole("button", { name: "Try again" }).click();
    await expect(heading).toHaveCount(0);
    await expect(page.locator("header.chats-header")).toBeVisible();
  } finally {
    fixture({ ...data, action: "cleanup" });
  }
});

test("an unexpected startup error is its own page with a retry, not maintenance", async ({
  page,
  context,
}) => {
  const data = fixture({ action: "init", empty: true });
  try {
    await signIn(context, data, { locale: "en" });
    await page.setViewportSize({ width: 390, height: 844 });
    let broken = true;
    await page.route("**/api/onboarding", (route) =>
      broken ? route.fulfill({ status: 500, json: { code: "internal_error" } }) : route.continue(),
    );
    await page.goto("/app");
    await expect(page.getByRole("heading", { name: "An unexpected error occurred" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Lonora is under maintenance" })).toHaveCount(0);
    broken = false;
    await page.getByRole("button", { name: "Try again" }).click();
    await expect(page.locator("header.chats-header")).toBeVisible();
  } finally {
    fixture({ ...data, action: "cleanup" });
  }
});

test("gateway errors in the middle of a session bring maintenance, which clears by itself", async ({
  page,
  context,
}) => {
  const data = fixture({ action: "init", empty: true });
  try {
    await signIn(context, data, { locale: "en" });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/app");
    await expect(page.locator("header.chats-header")).toBeVisible();
    let down = true;
    const gateway = (route) =>
      down && !route.request().url().includes("/events")
        ? route.fulfill({ status: 504, body: "" })
        : route.continue();
    await page.route("**/api/**", gateway);
    await page.route("**/health", gateway);
    const heading = page.getByRole("heading", { name: "Lonora is under maintenance" });
    // Three reads without an answer within half a minute.
    for (const tab of ["Updates", "Tasks", "Settings", "Chats"]) {
      if (await heading.isVisible()) break;
      await page.locator("nav.tabbar").getByRole("button", { name: tab }).click({ force: true });
    }
    await expect(heading).toBeVisible();
    down = false;
    await expect(heading).toHaveCount(0, { timeout: 12_000 });
  } finally {
    fixture({ ...data, action: "cleanup" });
  }
});
