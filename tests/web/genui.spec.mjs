// The canonical alert card end to end on web (docs/genui.md, S-A01 acceptance), from a
// recorded stream replay of A01 through a real Run, a real card submission, the receipt,
// reload and «تعديل»; Stop on a queued submission; and the side-by-side gate on the A01 card inside
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
    // No card control may decide an approval or an owner action (mandate 6.10).
    const path = new URL(request.url()).pathname;
    if (request.method() !== "GET" && /^\/api\/(trading\/approvals|owner-actions)/.test(path))
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
    // With several accounts in the database the server appends « · <account>» (docs/genui.md §7).
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

// The side-by-side gate inside the conversation pane: the A01 card as the owner sees it against the
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
  // v38 raised the field hint from --faint to --muted for contrast (Desktop-38 2271); the
  // port follows v38, Desktop-37 still draws it faint. Its border colour is currentColor.
  ".ux-field > label small": ["color", "border-top-color"],
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
    // A trusted slot needs a real record: the agent's card embeds a pending approval.
    const ids = python("records", fixture.input);
    python("slots", { ...fixture.input, record: ids.approval });
    const ux = page.locator(".ux").filter({ hasText: "حاسبة حجم الصفقة" }).first();
    await expect(ux).toBeVisible();
    await expect(card(page)).toBeVisible();
    await expect(page.locator(".ux-slot[data-slot-live]")).toBeVisible();
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

// The fixed cards in their slots at 390 px, in Arabic and in English, against the heights the
// compiler counts for each record as it is (genui_compile.slot_height, LD1-LD3): never taller
// than its height at rest, and every later state never taller than the waiting record's tallest
// later state. The Trade Approval at its tallest realistic shapes: a pending entry with stop
// loss and take profit, the tolerance row and a two-line reason, a modify_order with its ticket
// row, longer reasons and a batch of two; decided with a non-confirmed result line, a broker
// refusal or an outcome never confirmed under each code the executor records for it (core
// uncertainMessages).
const TALL_REASON = {
  ar: "اختراق فوق 2,400 مع افتتاح لندن، والوقف تحت القاع.",
  en: "Breakout above 2,400 at the London open.",
};
const LONG_REASON = {
  ar: "اختراق فوق المقاومة مع افتتاح لندن وحجم أعلى من المتوسط، والوقف تحت قاع الجلسة الآسيوية لأن الكسر الكاذب هناك يلغي الفكرة كلها، والهدف عند القمة السابقة.",
  en: "Breakout above resistance at the London open on higher than average volume, with the stop under the Asian session low because a false break there cancels the idea.",
};
// A non-confirmed result as the trade tool records it, by its code.
const UNCERTAIN = [
  "uncertain:broker_result_ambiguous",
  "uncertain:broker_result_mismatch",
  "uncertain:execution_interrupted_after_send",
];

const WIDE_NAME = "WMWM WMWM WMWM WMWM WMWM WMWM WMWM WMWM WMWM WMWM WMWM WMWM WMWM WMWM WMWM WMWM";
const LONG_LABEL = "مفتاح الواجهة البرمجية لحساب التداول في منصة العملات الرقمية";

async function locales(browser, fixture, page) {
  const english = await browser.newContext({ baseURL: test.info().project.use.baseURL });
  await english.addCookies(
    fixture.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await english.addInitScript(() => {
    localStorage.setItem("lonora.locale", "en");
    localStorage.setItem("lonora.theme", JSON.stringify("dark"));
  });
  const en = await english.newPage();
  await en.setViewportSize({ width: 390, height: 844 });
  return { pages: [["ar", page], ["en", en]], close: () => english.close() };
}

/** The slot's drawn height, after a fresh read of the conversation. */
async function drawn(target, fixture, card, record) {
  await target.goto(`/app/${fixture.agent.id}?thread=${fixture.thread.id}`);
  const slot = target.locator(`.ux .ux-slot[data-slot-card="${card}"]`, {
    has: target.locator(
      `[data-${card === "trade_approval" ? "trade-approval" : "owner-action"}="${record}"]`,
    ),
  });
  await expect(slot).toBeVisible();
  return slot.evaluate((node) => node.getBoundingClientRect().height);
}

test("Slots: the Trade Approval slot never outgrows the heights the compiler counts", async ({
  page,
  context,
  browser,
}) => {
  test.setTimeout(300_000);
  const fixture = await open(page, context);
  const { pages, close } = await locales(browser, fixture, page);
  try {
    const ids = python("records", fixture.input);
    python("slots", { ...fixture.input, record: ids.approval });
    const heights = () =>
      python("slot_heights", { ...fixture.input, card: "trade_approval", record: ids.approval });
    const shapes = [];
    for (const action of ["buy_limit", "modify_order"])
      shapes.push({ action, reason: TALL_REASON, results: [undefined, "failed", ...UNCERTAIN] });
    shapes.push({ action: "modify_order", reason: LONG_REASON, results: [undefined, UNCERTAIN[1]] });
    shapes.push({ action: "modify_order", reason: TALL_REASON, count: 2, results: [UNCERTAIN[1]] });
    for (const { action, reason, count, results } of shapes)
      for (const [locale, target] of pages) {
        const shape = { ...fixture.input, record: ids.approval, action, count };
        let later = Number.POSITIVE_INFINITY;
        for (const outcome of results) {
          const [result, code] = outcome ? outcome.split(":") : [];
          python("tallest_approval", { ...shape, reason: reason[locale], result, code });
          const counted = heights();
          if (!result) later = counted.later;
          const height = await drawn(target, fixture, "trade_approval", ids.approval);
          const label = `${locale} ${action} ×${count ?? 1} ${outcome ?? "pending"}`;
          expect(height, label).toBeLessThanOrEqual(counted.rest);
          expect(height, label).toBeLessThanOrEqual(later);
          if (reason === TALL_REASON) {
            // The reason is two lines at this width, as measured for the counts.
            const lines = await target
              .locator(`[data-trade-approval="${ids.approval}"] [data-trade-reason] > span`)
              .first()
              .evaluate((node) =>
                Math.round(
                  node.getBoundingClientRect().height /
                    Number.parseFloat(getComputedStyle(node).lineHeight),
                ),
              );
            expect(lines, label).toBe(2);
          }
        }
      }
  } finally {
    await close();
    await fixture.cleanup();
  }
});

test("Slots: the Settle, Mandate and Secret slots never outgrow the heights the compiler counts", async ({
  page,
  context,
  browser,
}) => {
  test.setTimeout(300_000);
  const fixture = await open(page, context);
  const { pages, close } = await locales(browser, fixture, page);
  try {
    const ids = python("records", { ...fixture.input, secret_fields: 2, broker: true });
    const slots = [
      ["settle", ids.settle],
      ["mandate", ids.mandate],
      ["secret", ids.secret],
      ["secret", ids.broker],
    ];
    for (const [card, record] of slots) python("slots", { ...fixture.input, card, record });
    // The Mandate card at its tallest lines: Ask and a signed grant's line. No value is saved
    // under the Secret card's names yet (another journey may have saved some): its «replaces»
    // line comes last.
    python("tallest_mandate", fixture.input);
    python("fixed_card", { ...fixture.input, record: ids.secret, saved: false });
    const check = async (card, record, label) => {
      const counted = python("slot_heights", { ...fixture.input, card, record });
      for (const [locale, target] of pages) {
        const height = await drawn(target, fixture, card, record);
        expect(height, `${locale} ${card} ${label}`).toBeLessThanOrEqual(counted.rest);
      }
      return counted;
    };
    // Each card names the agent: a name of words and one of wide capitals, the contract's
    // longest, which wraps further.
    for (const name of ["Genui browser", WIDE_NAME]) {
      python("fixed_card", { ...fixture.input, record: ids.settle, name });
      for (const [card, record] of slots) await check(card, record, name);
    }
    // A Settle card answered, or lapsed and renewed, is never taller than it was waiting.
    const waiting = await check("settle", ids.settle, "waiting");
    for (const state of [
      { status: "confirmed", result: { outcome: "unknown" } },
      { expired: true, renewed: true },
    ]) {
      python("fixed_card", { ...fixture.input, record: ids.settle, ...state });
      for (const [locale, target] of pages)
        expect(await drawn(target, fixture, "settle", ids.settle), locale).toBeLessThanOrEqual(
          waiting.later,
        );
    }
    // A Secret card's own field labels at the contract's longest, and the line naming the
    // saved values it replaces, read when it is shown: within its tallest later state.
    python("fixed_card", { ...fixture.input, record: ids.secret, labels: [LONG_LABEL] });
    const labelled = await check("secret", ids.secret, "long labels");
    python("fixed_card", { ...fixture.input, record: ids.secret, saved: true });
    try {
      for (const [locale, target] of pages) {
        const height = await drawn(target, fixture, "secret", ids.secret);
        await expect(target.locator(`.ux-slot [data-owner-action="${ids.secret}"]`)).toContainText(
          locale === "ar" ? "تحلّ محل ما حُفظ سابقًا" : "Replaces what was saved before",
        );
        expect(height, locale).toBeLessThanOrEqual(labelled.later);
      }
    } finally {
      python("fixed_card", { ...fixture.input, record: ids.secret, saved: false });
    }
  } finally {
    await close();
    await fixture.cleanup();
  }
});

test("Slots: a fixed card in the agent's card is the live record, and its row steps aside", async ({
  page,
  context,
  browser,
}) => {
  // Three replies, a stale tap, Enter, two decisions and two reloads: more than the default.
  test.setTimeout(60_000);
  const fixture = await open(page, context);
  const csrf = fixture.cookies.find((row) => row.name === "lonora_csrf").value;
  try {
    // The Secret card asks for two fields: its slot's height grows with them (10.1.4).
    const ids = python("records", { ...fixture.input, secret_fields: 2 });
    const approval = page.locator(`[data-trade-approval="${ids.approval}"]`);
    const settle = page.locator(`[data-owner-action="${ids.settle}"]`);
    // No message embeds them yet: each fixed card stands in its own row.
    await page.reload();
    await expect(approval).toHaveCount(1);
    await expect(settle).toHaveCount(1);
    await expect(page.locator(".ux-slot")).toHaveCount(0);
    python("slots", { ...fixture.input, record: ids.approval, number: true });
    python("slots", { ...fixture.input, card: "settle", record: ids.settle });
    python("slots", { ...fixture.input, card: "mandate", record: ids.mandate });
    python("slots", { ...fixture.input, card: "secret", record: ids.secret });
    const slot = page.locator('.ux .ux-slot[data-slot-card="trade_approval"]');
    const settleSlot = page.locator('.ux .ux-slot[data-slot-card="settle"]');
    await expect(slot).toBeVisible();
    await expect(settleSlot).toBeVisible();
    // The server's records, drawn by the client: only the cards' own words.
    await expect(slot.locator(`[data-trade-approval="${ids.approval}"]`)).toBeVisible();
    await expect(settleSlot.locator(`[data-owner-action="${ids.settle}"]`)).toBeVisible();
    await expect(slot).toContainText("XAUUSD");
    await expect(slot).toContainText("2350.00");
    await expect(settleSlot).toContainText("XAGUSD");
    for (const frame of [slot, settleSlot]) {
      await expect(frame).toContainText("بطاقة ثابتة من Lonora");
      for (const forged of ["صفقة مضمونة", "0.50 لوت"])
        await expect(frame).not.toContainText(forged);
    }
    // Enter in the agent's own Number field never reaches the fixed card's buttons: the
    // approval is still pending on the server afterwards. The Trade Approval is counted at its
    // tallest, so the agent's own blocks fold under More; the slot never does (10.2.2).
    await page
      .locator(".ux", { has: page.locator('.ux-slot[data-slot-card="trade_approval"]') })
      .getByRole("button", { name: "المزيد" })
      .click();
    const lots = page.getByLabel("الحجم المقترح");
    await lots.fill("0.2");
    await lots.press("Enter");
    const after = await context.request.get(
      `/api/trading/approvals?thread_id=${encodeURIComponent(fixture.thread.id)}`,
    );
    expect((await after.json()).find((row) => row.id === ids.approval).status).toBe("pending");
    // The slots are the records' places now: no standalone rows.
    await expect(approval).toHaveCount(1);
    await expect(settle).toHaveCount(1);
    // Each slot fits the height the compiler counts for its record at rest at 390 px
    // (genui_compile.slot_height, frame included).
    const heights = (card, record) => python("slot_heights", { ...fixture.input, card, record });
    const counted = (card, record) => heights(card, record).rest;
    expect((await slot.boundingBox()).height).toBeLessThanOrEqual(
      counted("trade_approval", ids.approval),
    );
    expect((await settleSlot.boundingBox()).height).toBeLessThanOrEqual(
      counted("settle", ids.settle),
    );
    // The Mandate card in its slot: the agent's mode read live and one button for the other
    // mode (mandate 10.3), which is the card's own action on the owner session.
    const mandateSlot = page.locator('.ux .ux-slot[data-slot-card="mandate"]');
    const mandate = page.locator(`[data-owner-action="${ids.mandate}"]`);
    await expect(mandateSlot.locator(`[data-owner-action="${ids.mandate}"]`)).toBeVisible();
    await expect(mandate).toHaveCount(1);
    await expect(mandateSlot).toContainText("التفويض");
    expect((await mandateSlot.boundingBox()).height).toBeLessThanOrEqual(
      counted("mandate", ids.mandate),
    );
    // The Secret card in its slot: W-ENV's own form, whose values go straight to the
    // encrypted store; its row steps aside too. The compiler counts its two fields, and the
    // line naming values saved under its names (read when it is shown) at its tallest.
    const secretSlot = page.locator('.ux .ux-slot[data-slot-card="secret"]');
    await expect(secretSlot.locator(`[data-owner-action="${ids.secret}"]`)).toBeVisible();
    await expect(page.locator(`[data-owner-action="${ids.secret}"]`)).toHaveCount(1);
    await expect(secretSlot).toContainText("بيانات سرّية");
    expect((await secretSlot.boundingBox()).height).toBeLessThanOrEqual(
      heights("secret", ids.secret).later,
    );
    // The Mandate and Secret cards with the agent's 80-character name (both cards show it),
    // Ask's line and the line a signed grant adds, in Arabic and in English, whose lines are
    // the longer: the compiler counts the name as the agent has it.
    python("tallest_mandate", fixture.input);
    await page.reload();
    await expect(mandateSlot).toContainText("صلاحيته الموقّعة تبقى سارية");
    const mandateHeight = counted("mandate", ids.mandate);
    const secretHeight = heights("secret", ids.secret).later;
    expect((await mandateSlot.boundingBox()).height).toBeLessThanOrEqual(mandateHeight);
    expect((await secretSlot.boundingBox()).height).toBeLessThanOrEqual(secretHeight);
    const english = await browser.newContext({ baseURL: test.info().project.use.baseURL });
    try {
      await english.addCookies(
        fixture.cookies.map((cookie) => ({
          ...cookie,
          url: test.info().project.use.baseURL,
          httpOnly: cookie.name === "lonora_session",
          sameSite: "Strict",
        })),
      );
      await english.addInitScript(() => {
        localStorage.setItem("lonora.locale", "en");
        localStorage.setItem("lonora.theme", JSON.stringify("dark"));
      });
      const en = await english.newPage();
      await en.setViewportSize({ width: 390, height: 844 });
      await en.goto(`/app/${fixture.agent.id}?thread=${fixture.thread.id}`);
      const enSlot = en.locator('.ux .ux-slot[data-slot-card="mandate"]');
      await expect(enSlot).toContainText("Now: Ask");
      await expect(enSlot).toContainText("Its signed grant still lets it trade");
      expect((await enSlot.boundingBox()).height).toBeLessThanOrEqual(mandateHeight);
      const enSecret = en.locator('.ux .ux-slot[data-slot-card="secret"]');
      await expect(enSecret.locator(`[data-owner-action="${ids.secret}"]`)).toBeVisible();
      expect((await enSecret.boundingBox()).height).toBeLessThanOrEqual(secretHeight);
    } finally {
      await english.close();
    }
    // Decided elsewhere while this screen still shows it pending: the second tap is refused
    // and the slot shows the record as it is now.
    await page.route("**/api/trading/approvals?*", (route) => route.abort());
    const elsewhere = await context.request.post(
      `/api/trading/approvals/${ids.approval}/decision`,
      { data: { decision: "reject" }, headers: { "X-CSRF-Token": csrf } },
    );
    expect(elsewhere.status()).toBe(200);
    await expect(slot.getByRole("button", { name: "موافقة", exact: true })).toBeVisible();
    await page.unroute("**/api/trading/approvals?*");
    const [stale] = await Promise.all([
      page.waitForResponse((response) =>
        response.url().endsWith(`/api/trading/approvals/${ids.approval}/decision`),
      ),
      slot.getByRole("button", { name: "موافقة", exact: true }).click(),
    ]);
    expect(stale.status()).toBe(409);
    await expect(slot.locator('[data-trade-status="rejected"]')).toBeVisible();
    // The settle slot's buttons are the card's own server action on the owner session.
    const [settled] = await Promise.all([
      page.waitForResponse((response) =>
        response.url().endsWith(`/api/owner-actions/${ids.settle}/decision`),
      ),
      settleSlot.getByRole("button", { name: "لم تُنفذ", exact: true }).click(),
    ]);
    expect(settled.status()).toBe(200);
    await expect(settleSlot.getByRole("button", { name: "لم تُنفذ", exact: true })).toHaveCount(0);
    // Read again later, the slots show the records as they are now, and still no rows.
    await page.reload();
    await expect(slot.locator('[data-trade-status="rejected"]')).toBeVisible();
    await expect(approval).toHaveCount(1);
    await expect(settle).toHaveCount(1);
    // Last, as it withdraws the agent's pending approvals (4.2.3): the Mandate slot's button
    // switches the mode, and the slot then offers the other mode.
    const [switched] = await Promise.all([
      page.waitForResponse((response) =>
        response.url().endsWith(`/api/owner-actions/${ids.mandate}/decision`),
      ),
      mandateSlot.getByRole("button", { name: "وكّله", exact: true }).click(),
    ]);
    expect(switched.status()).toBe(200);
    await expect(mandateSlot.getByRole("button", { name: "يستأذن", exact: true })).toBeVisible();
  } finally {
    await fixture.cleanup();
  }
});
