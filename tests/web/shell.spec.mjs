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
      await expect(nav.getByRole("button", { name: "المحادثات", exact: true })).toHaveAttribute(
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
      await nav.getByRole("button", { name: "المستجدات", exact: true }).click();
      await expect(page).toHaveURL(/\/app\/updates$/);
      await expect(page.locator(".topbar")).toHaveClass(/bare/);
      const title = page.locator("main > .large-title");
      await expect(title).toHaveText(/المستجدات/);
      await expect(nav.getByRole("button", { name: "المستجدات", exact: true })).toHaveAttribute(
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
      const rest = await read(0);
      expect(rest.edge).toBe("0.000");
      expect(rest.opacity).toBe("1.000");
      expect(rest.transform).toBe("");
      expect(rest.filter).toBe("");
      const half = await read(20); // p = 0.5 of a 40px title
      expect(half.opacity).toBe("0.350");
      expect(half.transform).toBe("translateY(9.0px) scale(0.960)");
      expect(half.crisp).toBe("0.500");
      expect(half.blur).toBe("0.500");
      expect(half.edge).toBe("0.000"); // rest = 60% of the title: 24px
      const edge = await read(28);
      expect(edge.edge).toBe("0.250");
      const gone = await read(60);
      expect(gone.opacity).toBe("0.000");
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
      // Light theme: the frame takes the reference's ivory background.
      await page.evaluate(() => localStorage.setItem("lonora.theme", JSON.stringify("light")));
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
    const { agent, headers } = await tradingAgent(context, data);
    try {
      await signIn(context, data);
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
      await expect(dialog).toHaveAttribute("aria-label", "الشارت");
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
      await context.request.delete(`/api/agents/${agent.id}`, { headers });
      fixture({ ...data, action: "cleanup" });
    }
  });
});

test.describe("desktop shell (1280×800, Arabic)", () => {
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
