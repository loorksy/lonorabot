// The canonical alert card end to end on web (docs/genui.md, S-A01 acceptance), from a
// recorded stream replay of A01 through a real Run, a real card submission, the receipt,
// reload and «تعديل»; Stop on a queued submission; and §10.4's gate on the A01 card inside
// the real conversation pane against Desktop-37's own alert recipe.
import { execFileSync, spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

const ROOT = fileURLToPath(new URL("../..", import.meta.url));
const python = (command, input = {}) =>
  JSON.parse(
    execFileSync(".venv/bin/python", [`tests/check_genui_browser.py`, command], {
      cwd: ROOT,
      input: JSON.stringify(input),
      encoding: "utf8",
    }),
  );
const background = (command, input) =>
  new Promise((resolve, reject) => {
    const child = spawn(".venv/bin/python", ["tests/check_genui_browser.py", command], {
      cwd: ROOT,
    });
    let out = "";
    let err = "";
    child.stdout.on("data", (chunk) => {
      out += chunk;
    });
    child.stderr.on("data", (chunk) => {
      err += chunk;
    });
    child.on("close", (code) => (code === 0 ? resolve(JSON.parse(out)) : reject(new Error(err))));
    child.stdin.end(JSON.stringify(input));
  });

async function open(page, context, { theme = "dark", width = 390, height = 844 } = {}) {
  const fixture = python("setup");
  await context.addCookies(
    fixture.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript((value) => {
    localStorage.setItem("lonora.locale", "ar");
    localStorage.setItem("lonora.theme", JSON.stringify(value));
  }, theme);
  await page.setViewportSize({ width, height });
  await page.goto(`/app/${fixture.agent.id}?thread=${fixture.thread.id}`);
  const csrf = fixture.cookies.find((row) => row.name === "lonora_csrf").value;
  return {
    ...fixture,
    input: { thread_id: fixture.thread.id, connection: fixture.connection },
    cleanup: async () => {
      const headers = { "X-CSRF-Token": csrf };
      await context.request.delete(`/api/agents/${fixture.agent.id}`, { headers });
      await context.request.delete(`/api/trading/connections/${fixture.connection}`, { headers });
    },
  };
}

const card = (page) => page.locator(".ux").filter({ hasText: "تنبيه سعر" }).first();

test("A01: the alert card streams, computes, sends and locks in the conversation", async ({
  page,
  context,
}) => {
  const fixture = await open(page, context);
  const forbidden = [];
  page.on("request", (request) => {
    // No card control may decide an approval, an owner action or a restriction (§10.2).
    const path = new URL(request.url()).pathname;
    if (
      request.method() !== "GET" &&
      /^\/api\/(trading\/approvals|owner-actions|trading\/restrictions)/.test(path)
    )
      forbidden.push(path);
  });
  try {
    const streamed = background("stream", { ...fixture.input, delay: 0.15 });
    // Building: skeleton, aria-busy, every control disabled.
    const building = page.locator('.ux[aria-busy="true"]');
    await expect(building).toBeVisible({ timeout: 15_000 });
    await expect(building.locator(".ux-skel")).toBeVisible();
    for (const button of await building.locator("button").all())
      await expect(button).toBeDisabled();
    await streamed;
    const alert = card(page);
    await expect(alert).not.toHaveAttribute("aria-busy", "true");
    await expect(alert.getByText("الآن 2,368.40")).toBeVisible();
    await expect(alert.getByText("1.33%")).toBeVisible();
    await expect(alert.getByText("داخل التطبيق")).toBeVisible();
    await expect(alert.getByText("لماذا هذه الواجهة؟")).toBeVisible();
    const box = await alert.boundingBox();
    expect(box.height).toBeLessThanOrEqual(560);
    // Switching the asset: silver empties the price and shows its own quote.
    const price = alert.getByRole("textbox", { name: "السعر المستهدف" });
    const send = alert.getByRole("button", { name: "إنشاء التنبيه" });
    await alert.getByRole("radio", { name: "الفضة" }).click();
    await expect(price).toHaveValue("");
    await expect(alert.getByText("الآن 28.92")).toBeVisible();
    await expect(send).toBeDisabled();
    await price.press("Enter");
    await expect(alert.getByText("أكمل «السعر المستهدف» أولًا")).toBeVisible();
    await expect(price).toHaveAttribute("aria-invalid", "true");
    await alert.getByRole("radio", { name: "الذهب" }).click();
    await expect(price).toHaveValue("2400");
    // The condition is already met: the warn note replaces the distance.
    await price.fill("2300");
    await expect(alert.getByText("الشرط متحقق الآن؛ سيصلك التنبيه فور إنشائه.")).toBeVisible();
    // Typed key by key as the owner does: «2,4» is no number yet, so the send stays
    // disabled and no prefix (2) is ever sent; «2,400» reads as 2400 (review M7).
    await price.fill("");
    await price.pressSequentially("2,4");
    await expect(send).toBeDisabled();
    // Enter says why nothing was sent: the reference's field error (review round 4).
    await price.press("Enter");
    await expect(alert.getByRole("alert").filter({ hasText: "القيمة غير صحيحة." })).toBeVisible();
    await expect(price).toHaveAttribute("aria-invalid", "true");
    await price.pressSequentially("00");
    await expect(send).toBeEnabled();
    await expect(alert.getByText("القيمة غير صحيحة.")).toHaveCount(0);
    const posted = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url().endsWith(`/api/threads/${fixture.thread.id}/messages`),
    );
    await send.click();
    const response = await posted;
    expect(response.status(), await response.text()).toBe(202);
    const body = response.request().postDataJSON();
    expect(body.content).toBe("");
    expect(body.ui_submit.values).toMatchObject({ symbol: "XAUUSD", dir: "above", price: 2400 });
    // The server's bubble, quoting the card; the card locks.
    // With several accounts in the database the server appends « · <account>» (§8.3).
    await expect(
      page.getByText(/^أنشئ تنبيهًا: الذهب فوق 2,400\.00( · Simulation · \d+ · Demo)?$/),
    ).toBeVisible();
    await expect(page.locator(".ux-quote").getByText("تنبيه سعر")).toBeVisible();
    // The quote's sparkle at the reference's quote icon size (review U5).
    await expect(page.locator(".ux-quote svg")).toHaveCSS("width", "14px");
    // On the title's line, not above it (review round 4).
    const [icon, title] = await Promise.all([
      page.locator(".ux-quote svg").boundingBox(),
      page.locator(".ux-quote span").boundingBox(),
    ]);
    expect(
      icon && title && Math.abs(icon.y + icon.height / 2 - (title.y + title.height / 2)),
    ).toBeLessThan(6);
    await expect(alert).toHaveClass(/is-sent/);
    await expect(alert.getByText(/أُرسل إلى/)).toBeVisible();
    await expect(price).toBeDisabled();
    // Reload keeps the values and the lock.
    await page.reload();
    await expect(card(page)).toHaveClass(/is-sent/);
    await expect(card(page).getByRole("textbox", { name: "السعر المستهدف" })).toHaveValue("2400");
    // The agent acts with its own tools and answers with a receipt.
    await background("receipt", fixture.input);
    const receipt = page.locator(".ux").filter({ hasText: "تنبيه فعّال" });
    await expect(receipt).toBeVisible({ timeout: 15_000 });
    await expect(receipt.getByText("يصعد فوق 2,400")).toBeVisible();
    // The send ran: it is never marked «لم يُنفَّذ» and its card stays locked (review U1).
    await expect(page.locator("span[data-ui-mark]")).toHaveCount(0);
    await expect(card(page)).toHaveClass(/is-sent/);
    // «تعديل» unlocks the card.
    await card(page).getByRole("button", { name: "تعديل" }).click();
    await expect(card(page)).not.toHaveClass(/is-sent/);
    await expect(card(page).getByRole("textbox", { name: "السعر المستهدف" })).toBeEnabled();
    // A card goes only to the listed pages, through the shell's own navigation.
    await receipt.getByRole("button", { name: "تفضيلات المحادثة" }).click();
    await expect(page).toHaveURL(/\/app\/chat-prefs$/);
    await page.goBack();
    await receipt.getByRole("button", { name: "عرض التنبيهات" }).click();
    await expect(page).toHaveURL(/\/app\/market/);
    expect(forbidden).toEqual([]);
  } finally {
    await fixture.cleanup();
  }
});

test("A01: Stop before the submission's Run starts marks it «لم يُنفَّذ» and unlocks the card", async ({
  page,
  context,
}) => {
  const fixture = await open(page, context, { width: 1280, height: 800 });
  try {
    await background("stream", { ...fixture.input, delay: 0 });
    const alert = card(page);
    await expect(alert.getByRole("button", { name: "إنشاء التنبيه" })).toBeEnabled();
    await alert.getByRole("button", { name: "إنشاء التنبيه" }).click();
    await expect(alert).toHaveClass(/is-sent/);
    const stop = page.getByRole("button", { name: /^(Stop the reply|إيقاف الرد)$/ }).first();
    await expect(stop).toBeVisible();
    await stop.click();
    await expect(page.locator('span[data-ui-mark="not_run"]')).toHaveText("لم يُنفَّذ");
    await expect(alert).not.toHaveClass(/is-sent/);
  } finally {
    await fixture.cleanup();
  }
});

test("A01: «تعديل» on a queued send marks it «مُعدّلة» and collapses it as superseded", async ({
  page,
  context,
}) => {
  const fixture = await open(page, context, { width: 1280, height: 800 });
  try {
    await background("stream", { ...fixture.input, delay: 0 });
    const alert = card(page);
    await alert.getByRole("button", { name: "إنشاء التنبيه" }).click();
    await expect(alert).toHaveClass(/is-sent/);
    await alert.getByRole("button", { name: "تعديل" }).click();
    // Q21: the edit cancels the queued Run; the server records «مُعدّلة» (review U2).
    await expect(page.locator('span[data-ui-mark="superseded"]')).toHaveText("مُعدّلة");
    await expect(page.locator('article[data-ui-mark="superseded"]')).toBeVisible();
    await expect(page.locator('span[data-ui-mark="not_run"]')).toHaveCount(0);
    await expect(alert).not.toHaveClass(/is-sent/);
  } finally {
    await fixture.cleanup();
  }
});

// §10.4 inside the conversation pane: the A01 card as the owner sees it against the
// reference's alert recipe opened in its own conversation («جرّب في محادثة»).
const CLASSES = [
  ".ux",
  ".ux-head",
  ".ux-ic",
  ".ux-ic svg",
  ".ux-ht b",
  ".ux-ht small",
  ".ux-body",
  ".ux-field",
  // The Number field's label row: its hint sits beside the label (review U4).
  ".ux-field > label",
  ".ux-field > label span",
  ".ux-field > label small",
  ".ux-label",
  ".ux-seg",
  ".ux-seg button",
  '.ux-seg button[aria-checked="true"]',
  ".ux-input",
  ".ux-input input",
  ".ux-affix",
  ".ux-text",
  ".ux-picks",
  ".ux-box",
  ".ux .btn.primary",
  ".ux .btn.primary svg",
  ".ux-foot",
  ".ux-why-b",
];
const PROPS = [
  "display",
  "flex-direction",
  "justify-content",
  "align-items",
  "font-family",
  "font-size",
  "font-weight",
  "line-height",
  "color",
  "background-color",
  "background-image",
  "border-top-width",
  "border-top-color",
  "border-top-left-radius",
  "border-bottom-right-radius",
  "padding-top",
  "padding-right",
  "padding-bottom",
  "padding-left",
  "gap",
  "box-shadow",
  "opacity",
  "direction",
  "text-align",
  "stroke-width",
];
// Intended differences, each with its reason (docs/genui.md allow-list).
const ALLOWED = {
  // The delivery row shows only the real channels, read-only (Q39, Q59): one row where the
  // reference shows three, so the row, the body and the card are 84 px shorter.
  ".ux": ["height"],
  ".ux-body": ["height"],
  ".ux-picks": ["height"],
};

async function probe(page) {
  return page.evaluate(
    ([classes, props]) => {
      const root = [...document.querySelectorAll(".ux")].find((node) =>
        node.textContent.includes("تنبيه سعر"),
      );
      const out = {};
      for (const selector of classes) {
        const el = root?.matches(selector) ? root : root?.querySelector(selector);
        if (!el) continue;
        const style = getComputedStyle(el);
        out[selector] = Object.fromEntries(props.map((p) => [p, style.getPropertyValue(p)]));
        const rect = el.getBoundingClientRect();
        out[selector].height = Math.round(rect.height);
      }
      const thumb = root?.querySelector(".ux-seg");
      if (thumb) {
        const style = getComputedStyle(thumb, "::before");
        out[".ux-seg::before"] = {
          "background-color": style.backgroundColor,
          "border-top-left-radius": style.borderTopLeftRadius,
          "box-shadow": style.boxShadow,
        };
      }
      return out;
    },
    [CLASSES, PROPS],
  );
}

test("A01: the card can be read as text, and the interface switches are honoured", async ({
  page,
  context,
}) => {
  const fixture = await open(page, context, { width: 1280, height: 800 });
  try {
    await background("stream", { ...fixture.input, delay: 0 });
    const alert = card(page);
    await expect(alert).not.toHaveAttribute("aria-busy", "true");
    await expect(alert.getByText("لماذا هذه الواجهة؟")).toBeVisible();
    const message = page.locator(".msg.theirs").last();
    const menu = async () => {
      await message.click({ button: "right" });
      return page.locator(".msg-pop .pop-item");
    };
    // «عرض كنص» (reference openMsgMenu, Desktop-37 3885): the card's own text instead.
    await (await menu()).filter({ hasText: "عرض كنص" }).click();
    await expect(page.locator(".ux")).toHaveCount(0);
    await expect(message).not.toHaveClass(/k-ui/);
    await expect(message.locator(".bubble")).toContainText(/\S/);
    // …and back to the card, which kept its state.
    await (await menu()).filter({ hasText: "عرض الواجهة" }).click();
    await expect(card(page)).toBeVisible();
    await expect(message).toHaveClass(/k-ui/);

    // «سبب اختيار الواجهة» off: the card stays, its why button goes.
    await page.evaluate(() =>
      localStorage.setItem("lonora.chatPrefs", JSON.stringify({ genuiWhy: false })),
    );
    await page.reload();
    await expect(card(page)).toBeVisible();
    await expect(page.locator(".ux-why-b")).toHaveCount(0);

    // «عناصر تفاعلية في الردود» off: every card is its text, and the menu offers no switch.
    await page.evaluate(() =>
      localStorage.setItem("lonora.chatPrefs", JSON.stringify({ genui: false })),
    );
    await page.reload();
    await expect(page.locator(".msg.theirs").last().locator(".bubble")).toContainText(/\S/);
    await expect(page.locator(".ux")).toHaveCount(0);
    const items = await menu();
    await expect(items.filter({ hasText: "نسخ النص" })).toHaveCount(1);
    await expect(items.filter({ hasText: /عرض كنص|عرض الواجهة/ })).toHaveCount(0);
  } finally {
    await fixture.cleanup();
  }
});

for (const theme of ["dark", "light"]) {
  for (const [width, height] of [
    [390, 844],
    [1280, 800],
  ]) {
    test(`A01 in the conversation pane matches Desktop-37's alert recipe (${theme} ${width})`, async ({
      page,
      context,
      browser,
    }) => {
      const fixture = await open(page, context, { theme, width, height });
      const reference = await browser.newContext({
        viewport: { width, height },
        colorScheme: theme,
        locale: "ar",
      });
      try {
        await background("stream", { ...fixture.input, delay: 0 });
        await expect(card(page).getByText("الآن 2,368.40")).toBeVisible();
        const ref = await reference.newPage();
        await ref.goto(`file://${ROOT}docs/ui-reference/Lonora-Desktop-37.html`);
        await ref.evaluate((light) => {
          // The reference re-applies its own theme on every render (Desktop-37:3543).
          // biome-ignore lint/correctness/noUndeclaredVariables: the reference's global state
          S.theme = light ? "light" : "dark";
          window.handle("ux-try", { id: "alert" });
        }, theme === "light");
        await ref.waitForTimeout(300);
        await ref.evaluate(() => window.sendMessage("نبّهني إذا صعد الذهب فوق 2400"));
        await ref.waitForFunction(
          () =>
            [...document.querySelectorAll(".ux")].some(
              (node) =>
                node.textContent.includes("تنبيه سعر") && !node.classList.contains("is-building"),
            ),
          null,
          { timeout: 20_000 },
        );
        await ref.waitForTimeout(500);
        const [a, b] = [await probe(ref), await probe(page)];
        const defects = [];
        for (const selector of Object.keys(a)) {
          if (!b[selector]) {
            defects.push(`${selector}: missing in Lonora`);
            continue;
          }
          for (const [prop, value] of Object.entries(a[selector])) {
            if ((ALLOWED[selector] ?? []).includes(prop)) continue;
            const other = b[selector][prop];
            const same =
              prop === "height" ? Math.abs(Number(value) - Number(other)) <= 1 : value === other;
            if (!same) defects.push(`${selector} ${prop}: ref ${value} · app ${other}`);
          }
        }
        // The card's row is capped as the reference caps a ui message (Desktop-37 1312-1313,
        // review U3): min(440px, 94%) on phones, min(460px, 78%) from 900 px.
        const widths = await page.evaluate(() => {
          const root = [...document.querySelectorAll(".ux")].find((node) =>
            node.textContent.includes("تنبيه سعر"),
          );
          const row = root?.closest(".template-message-frame");
          const list = root?.closest(".template-message")?.parentElement;
          return {
            row: Math.round(row?.getBoundingClientRect().width ?? 0),
            list: Math.round(list?.getBoundingClientRect().width ?? 0),
          };
        });
        const cap =
          width >= 900 ? Math.min(460, widths.list * 0.78) : Math.min(440, widths.list * 0.94);
        if (widths.row > Math.ceil(cap) + 1)
          defects.push(
            `card row width ${widths.row} over ${Math.round(cap)} (list ${widths.list})`,
          );
        test.info().annotations.push({ type: "side-by-side", description: defects.join("\n") });
        expect(defects).toEqual([]);
      } finally {
        await reference.close();
        await fixture.cleanup();
      }
    });
  }
}

/** The catalog generated from the server contract (packages/contracts/src/genui-catalog.ts). */
function catalog(name) {
  const source = readFileSync(`${ROOT}packages/contracts/src/genui-catalog.ts`, "utf8");
  const list = new RegExp(`export const ${name} = \\[([^\\]]*)\\]`).exec(source)?.[1] ?? "";
  return [...list.matchAll(/"([^"]+)"/g)].map((match) => match[1]);
}

test("Parity: the web card draws every node the server accepts and runs every action", async ({
  page,
  context,
}) => {
  const fixture = await open(page, context);
  try {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    python("stream", { ...fixture.input, delay: 0 });
    python("parity", fixture.input);
    const ux = page.locator(".ux").filter({ hasText: "حاسبة حجم الصفقة" }).first();
    await expect(ux).toBeVisible();
    await expect(card(page)).toBeVisible();
    await ux.getByRole("button", { name: "المزيد" }).click();
    // «2%» (a set action) shows the Note its `when` hides at 1%.
    await ux.getByRole("button", { name: "2%", exact: true }).click();
    const drawn = await page
      .locator(".ux [data-ux-type]:not([data-ux-off])")
      .evaluateAll((nodes) => [...new Set(nodes.map((node) => node.dataset.uxType))].sort());
    expect(drawn).toEqual([...catalog("UI_NODE_TYPES"), ...catalog("UI_SERVER_NODE_TYPES")].sort());
    // Local actions and inputs, computed on the client from the server's expressions.
    const slider = ux.getByRole("slider", { name: "المخاطرة %" });
    await slider.fill("3");
    await expect(ux.locator("output")).toHaveText("3%");
    await expect(ux.getByText("مخاطرة مرتفعة")).toBeVisible();
    await expect(ux.locator(".ux-sub.tr-up")).toBeVisible();
    await ux.getByRole("button", { name: "2%", exact: true }).click();
    await expect(ux.locator("output")).toHaveText("2%");
    await expect(ux.locator(".ux-sub.tr-up")).toHaveCount(0);
    await ux.getByRole("button", { name: "التفاصيل" }).click();
    await expect(ux.getByText("تفاصيل إضافية")).toBeVisible();
    await ux.getByLabel("الرافعة").selectOption({ label: "1:500" });
    await expect(ux.getByLabel("الرافعة")).toHaveValue("3");
    await ux.getByRole("button", { name: "إعادة" }).click();
    await expect(ux.locator("output")).toHaveText("1%");
    await expect(ux.getByText("تفاصيل إضافية")).toBeHidden();
    await ux.getByRole("button", { name: "نسخ" }).click();
    await expect(ux.getByText("تم النسخ")).toBeVisible();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe("0.50 لوت");
    // `open` opens the server-checked literal URL with noopener (no network in the test).
    await context.route("https://example.com/**", (route) =>
      route.fulfill({ status: 200, contentType: "text/html", body: "<p>ok</p>" }),
    );
    const [popup] = await Promise.all([
      page.waitForEvent("popup"),
      ux.getByRole("button", { name: "المصدر" }).click(),
    ]);
    await popup.waitForURL("https://example.com/position-size");
    expect(await popup.evaluate(() => window.opener)).toBeNull();
    await popup.close();
    // The send goes through ui_submit and the server writes the owner's bubble. It is the
    // `ask` intent (a Button with no action), which never locks its card.
    await ux.getByRole("button", { name: "اشرح الحساب" }).click();
    await expect(page.getByText("اشرح الحساب", { exact: true })).toHaveCount(2);
    await expect(ux.locator(".ux-sent")).toHaveCount(0);
    await ux.getByRole("button", { name: "السوق" }).click();
    await expect(page).toHaveURL(/\/app\/market/);
  } finally {
    await fixture.cleanup();
  }
});
