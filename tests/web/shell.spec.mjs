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
      await expect(dialog).toHaveAttribute("aria-label", "قائمة المحادثة");
      await dialog.getByRole("button", { name: "الشارت", exact: true }).click();
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
      // The in-sheet pages: a menu row slides a page in with ← back to the menu.
      await page.getByRole("button", { name: "قائمة المحادثة", exact: true }).click();
      await dialog.getByRole("button", { name: "معلومات الوكيل", exact: true }).click();
      await expect(dialog).toHaveAttribute("aria-label", "معلومات الوكيل");
      await expect(dialog.locator(".sheet-page")).toHaveClass(/go-fwd/);
      await dialog.getByRole("button", { name: "رجوع", exact: true }).click();
      await expect(dialog).toHaveAttribute("aria-label", "قائمة المحادثة");
      await expect(dialog.locator(".sheet-page")).toHaveClass(/go-back/);
      await page.keyboard.press("Escape");
      await expect(dialog).not.toHaveAttribute("open", "");
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
});
