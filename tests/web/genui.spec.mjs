// The canonical alert card end to end on web (GENUI_PLAN §10.5, S-A01 acceptance), from a
// recorded stream replay of A01 through a real Run, a real card submission, the receipt,
// reload and «تعديل»; Stop on a queued submission; and §10.4's gate on the A01 card inside
// the real conversation pane against Desktop-37's own alert recipe.
import { execFileSync, spawn } from "node:child_process";
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
    await price.fill("2400");
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
    await expect(page.getByText(/^أنشئ تنبيهًا: الذهب فوق 2,400\.00( · Simulation · \d+ · Demo)?$/)).toBeVisible();
    await expect(page.locator(".ux-quote").getByText("تنبيه سعر")).toBeVisible();
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
    const stop = page.getByRole("button", { name: /^(Stop|إيقاف)$/ }).first();
    await expect(stop).toBeVisible();
    await stop.click();
    await expect(page.locator('[data-ui-mark="not_run"]')).toHaveText("لم يُنفَّذ");
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
// Intended differences, each with its reason (GENUI_PLAN §10.4 allow-list).
const ALLOWED = {
  // The delivery row shows only the real channels, read-only (Q39, Q59): one row where the
  // reference shows three, so the row, the body and the card are 84 px shorter.
  ".ux": ["height"],
  ".ux-body": ["height"],
  ".ux-picks": ["height"],
  ".ux-box": ["opacity"],
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
        test.info().annotations.push({ type: "side-by-side", description: defects.join("\n") });
        expect(defects).toEqual([]);
      } finally {
        await reference.close();
        await fixture.cleanup();
      }
    });
  }
}
