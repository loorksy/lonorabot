// On mobile (docs/genui.md §7, rules L and N), Stop cancels a queued card submission sent
// from web, like web does, and the submission's bubble shows «لم يُنفَّذ» from the same core
// helper. Cards render natively on mobile (mandate 10.1.5): every node the server accepts.
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

const ROOT = fileURLToPath(new URL("../..", import.meta.url));
const python = (command, input = {}) =>
  JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_genui_browser.py", command], {
      cwd: ROOT,
      input: JSON.stringify(input),
      encoding: "utf8",
    }),
  );

test("Expo: Stop cancels a queued card submission and marks it «لم يُنفَّذ»", async ({
  page,
  context,
}) => {
  const fixture = python("setup");
  const csrf = fixture.cookies.find((row) => row.name === "lonora_csrf").value;
  const headers = { "X-CSRF-Token": csrf };
  await context.addCookies(
    fixture.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "ar"));
  await page.setViewportSize({ width: 390, height: 844 });
  try {
    python("stream", { thread_id: fixture.thread.id, connection: fixture.connection, delay: 0 });
    const messages = await (
      await context.request.get(`/api/threads/${fixture.thread.id}/messages`)
    ).json();
    const card = messages.find((row) =>
      row.rich_content?.parts?.some((part) => part.document?.v === 2),
    );
    const blocks = card.rich_content.parts[1].document.blocks;
    // The submission as web sends it: the server queues its own Run.
    const sent = await context.request.post(`/api/threads/${fixture.thread.id}/messages`, {
      headers,
      data: {
        content: "",
        ui_submit: {
          source_message_id: card.id,
          part: 1,
          path: String(blocks.length - 1),
          values: { price: 2400 },
        },
      },
    });
    expect(sent.status()).toBe(202);
    const submitted = (await sent.json()).message;
    await page.goto(`/thread?id=${fixture.thread.id}`);
    // The card renders natively, locked by the queued submission sent from web.
    const ux = page.getByTestId("ux-card").filter({ hasText: "تنبيه سعر" });
    await expect(ux).toBeVisible();
    await expect(ux.getByTestId("ux-node-Delivery-5")).toBeVisible();
    await expect(ux.getByTestId("ux-sent")).toBeVisible();
    await expect(page.getByText(submitted.content)).toBeVisible();
    await page.getByRole("button", { name: "إيقاف", exact: true }).last().click();
    await expect(page.getByTestId("ui-submit-mark")).toHaveText("لم يُنفَّذ");
    // A submission that never ran does not lock its card (docs/genui.md §7).
    await expect(ux.getByTestId("ux-sent")).toBeHidden();
    const run = await (await context.request.get(`/api/runs/${submitted.ui_submit.run_id}`)).json();
    expect(run.status).toBe("cancelled");
  } finally {
    await context.request.delete(`/api/agents/${fixture.agent.id}`, { headers });
    await context.request.delete(`/api/trading/connections/${fixture.connection}`, { headers });
  }
});

/** The catalog generated from the server contract (packages/contracts/src/genui-catalog.ts). */
function catalog(name) {
  const source = readFileSync(`${ROOT}packages/contracts/src/genui-catalog.ts`, "utf8");
  const list = new RegExp(`export const ${name} = \\[([^\\]]*)\\]`).exec(source)?.[1] ?? "";
  return [...list.matchAll(/"([^"]+)"/g)].map((match) => match[1]);
}

for (const theme of ["dark", "light"]) {
  test(`Expo: the native card draws every node the server accepts (${theme})`, async ({
    page,
    context,
  }) => {
    const fixture = python("setup");
    const csrf = fixture.cookies.find((row) => row.name === "lonora_csrf").value;
    const headers = { "X-CSRF-Token": csrf };
    await context.addCookies(
      fixture.cookies.map((cookie) => ({
        ...cookie,
        url: test.info().project.use.baseURL,
        httpOnly: cookie.name === "lonora_session",
        sameSite: "Strict",
      })),
    );
    await context.addInitScript(() => localStorage.setItem("lonora.locale", "ar"));
    await page.emulateMedia({ colorScheme: theme });
    await page.setViewportSize({ width: 390, height: 844 });
    try {
      const input = { thread_id: fixture.thread.id, connection: fixture.connection };
      python("stream", { ...input, delay: 0 });
      python("parity", input);
      // A trusted slot needs a real record: the agent's card embeds a pending approval.
      const ids = python("records", input);
      python("slots", { ...input, record: ids.approval });
      await page.goto(`/thread?id=${fixture.thread.id}`);
      await expect(page.getByTestId("ui-slot-trade_approval")).toBeVisible();
      const ux = page.getByTestId("ux-card").filter({ hasText: "حاسبة حجم الصفقة" });
      await expect(ux).toBeVisible();
      await expect(page.getByTestId("ux-card").filter({ hasText: "تنبيه سعر" })).toBeVisible();
      await ux.getByRole("button", { name: "المزيد" }).click();
      // «2%» (a set action) shows the Note its `when` hides at 1%.
      await ux.getByRole("button", { name: "2%", exact: true }).click();
      await expect(ux.getByText("مخاطرة مرتفعة")).toBeVisible();
      // A node counts as drawn only when its renderer produced something with a size.
      const drawn = await page
        .locator('[data-testid^="ux-node-"]:not([data-testid$="-off"])')
        .evaluateAll((nodes) => [
          ...new Set(
            nodes
              .filter((node) => {
                const box = node.getBoundingClientRect();
                return box.width > 0 && box.height > 0;
              })
              .map((node) => node.dataset.testid.split("-")[2]),
          ),
        ]);
      expect(drawn.sort()).toEqual(
        [...catalog("UI_NODE_TYPES"), ...catalog("UI_SERVER_NODE_TYPES")].sort(),
      );
      // The card follows the theme with the reference tokens' card mix (no model colours):
      // color-mix(text 3.5%, bubble-in) in dark, color-mix(text 2%, #fff) in light.
      const background = await ux.evaluate((node) => getComputedStyle(node).backgroundColor);
      expect(background).toBe(theme === "light" ? "rgb(250, 250, 250)" : "rgb(29, 30, 34)");
      // Local actions and inputs, computed with the same core evaluator as web.
      await expect(ux.getByText("2%").first()).toBeVisible();
      await ux.getByRole("button", { name: "التفاصيل" }).click();
      await expect(ux.getByText("تفاصيل إضافية")).toBeVisible();
      await ux.getByRole("combobox", { name: "الرافعة" }).click();
      await ux.getByRole("radio", { name: "1:500" }).click();
      await expect(ux.getByRole("combobox", { name: "الرافعة" })).toHaveText(/1:500/);
      await ux.getByRole("button", { name: "إعادة" }).click();
      await expect(ux.getByText("تفاصيل إضافية")).toBeHidden();
      await ux.getByRole("button", { name: "نسخ" }).click();
      await expect(ux.getByText("تم النسخ")).toBeVisible();
      // The Slider follows the reading direction: in Arabic its start is on the right.
      const slider = ux.getByRole("slider", { name: "المخاطرة %" });
      const box = await slider.boundingBox();
      await page.mouse.click(box.x + box.width * 0.05, box.y + box.height / 2);
      await expect(ux.getByText("5%", { exact: true })).toBeVisible();
      // open: the server-checked literal URL.
      await context.route("https://example.com/**", (route) =>
        route.fulfill({ status: 200, contentType: "text/html", body: "<p>ok</p>" }),
      );
      const [popup] = await Promise.all([
        page.waitForEvent("popup"),
        ux.getByRole("button", { name: "المصدر" }).click(),
      ]);
      await popup.waitForURL("https://example.com/position-size");
      await popup.close();
      // The send goes through ui_submit and the server writes the owner's bubble. It is the
      // `ask` intent (a Button with no action), which never locks its card.
      await ux.getByRole("button", { name: "اشرح الحساب" }).click();
      await expect(page.getByText("اشرح الحساب", { exact: true })).toHaveCount(2);
      await expect(ux.getByTestId("ux-sent")).toHaveCount(0);
      const messages = await (
        await context.request.get(`/api/threads/${fixture.thread.id}/messages`)
      ).json();
      expect(
        messages.filter((row) => row.origin === "ui_submit").map((row) => row.content),
      ).toEqual(["اشرح الحساب"]);
      // go: the server's route on mobile's own screen.
      await ux.getByRole("button", { name: "السوق" }).click();
      await expect(page).toHaveURL(/\/charts/);
    } finally {
      await context.request.delete(`/api/agents/${fixture.agent.id}`, { headers });
      await context.request.delete(`/api/trading/connections/${fixture.connection}`, { headers });
    }
  });
}

/** Signs the owner in on Expo web, Arabic, phone-sized. */
async function signIn(page, context, fixture) {
  await context.addCookies(
    fixture.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "ar"));
  await page.setViewportSize({ width: 390, height: 844 });
}

// A Grid cell keeps its identity when a sibling's `when` changes: the field being typed in
// keeps its focus and draft while the Note before it appears.
const GRID = [
  '{"v":2,"kind":"calculator","title":"شبكة الحقول","icon":"chart"}',
  '{"state":{"a":1}}',
  '{"type":"Grid","cols":2,"children":[{"type":"Note","text":"قيمة كبيرة","when":"$a>5"},{"type":"Number","bind":"a","label":"القيمة"}]}',
  '{"why":"حقل تجرّبه بنفسك.","fallback":"اكتب القيمة."}',
].join("\n");

test("Expo: a Grid cell keeps its field while a sibling appears", async ({ page, context }) => {
  const fixture = python("setup");
  const csrf = fixture.cookies.find((row) => row.name === "lonora_csrf").value;
  const headers = { "X-CSRF-Token": csrf };
  await signIn(page, context, fixture);
  try {
    python("card", {
      thread_id: fixture.thread.id,
      owner: "أعطني حقلًا أجرّب فيه",
      lead: "تفضّل.\n",
      document: GRID,
    });
    await page.goto(`/thread?id=${fixture.thread.id}`);
    const ux = page.getByTestId("ux-card").filter({ hasText: "شبكة الحقول" });
    await expect(ux).toBeVisible();
    await expect(ux.getByText("قيمة كبيرة")).toBeHidden();
    const field = ux.getByLabel("القيمة", { exact: true });
    await field.selectText();
    // «7» shows the Note before the field; the «0» typed next still lands in it.
    await page.keyboard.type("70");
    await expect(ux.getByText("قيمة كبيرة")).toBeVisible();
    await expect(field).toHaveValue("70");
    await expect(field).toBeFocused();
  } finally {
    await context.request.delete(`/api/agents/${fixture.agent.id}`, { headers });
    await context.request.delete(`/api/trading/connections/${fixture.connection}`, { headers });
  }
});

test("Expo: «تعديل» unlocks a card outside the newest page", async ({ page, context }) => {
  const fixture = python("setup");
  const csrf = fixture.cookies.find((row) => row.name === "lonora_csrf").value;
  const headers = { "X-CSRF-Token": csrf };
  await signIn(page, context, fixture);
  try {
    python("stream", { thread_id: fixture.thread.id, connection: fixture.connection, delay: 0 });
    const messages = await (
      await context.request.get(`/api/threads/${fixture.thread.id}/messages`)
    ).json();
    const card = messages.find((row) =>
      row.rich_content?.parts?.some((part) => part.document?.v === 2),
    );
    const blocks = card.rich_content.parts[1].document.blocks;
    const sent = await context.request.post(`/api/threads/${fixture.thread.id}/messages`, {
      headers,
      data: {
        content: "",
        ui_submit: {
          source_message_id: card.id,
          part: 1,
          path: String(blocks.length - 1),
          values: { price: 2400 },
        },
      },
    });
    expect(sent.status()).toBe(202);
    const submitted = (await sent.json()).message;
    // More than one history page after the card: the newest page no longer holds it.
    python("pad", { thread_id: fixture.thread.id, agent_id: fixture.agent.id, count: 120 });
    const newest = await (
      await context.request.get(`/api/threads/${fixture.thread.id}/messages`)
    ).json();
    expect(newest.some((row) => row.id === card.id)).toBe(false);
    // The owner loads the older page and scrolls up to the card, which its queued submission
    // locks.
    await page.goto(`/thread?id=${fixture.thread.id}`);
    await expect(page.getByText("رسالة 120", { exact: true })).toBeVisible();
    const older = page.getByRole("button", { name: "رسائل أقدم", exact: true });
    const ux = page.getByTestId("ux-card").filter({ hasText: "تنبيه سعر" });
    await page.mouse.move(195, 420);
    for (let step = 0; step < 80 && !(await ux.isVisible()); step += 1) {
      if (await older.isVisible()) await older.click();
      await page.mouse.wheel(0, -1500);
      await page.waitForTimeout(100);
    }
    await expect(ux.getByTestId("ux-sent")).toBeVisible();
    await ux.getByRole("button", { name: "تعديل", exact: true }).click();
    await expect(ux.getByText("عدّل ثم أرسل من جديد")).toBeVisible();
    // The card re-reads its own state: unlocked, though it is not in the newest page.
    await expect(ux.getByTestId("ux-sent")).toBeHidden();
    const run = await (await context.request.get(`/api/runs/${submitted.ui_submit.run_id}`)).json();
    expect(run.status).toBe("cancelled");
  } finally {
    await context.request.delete(`/api/agents/${fixture.agent.id}`, { headers });
    await context.request.delete(`/api/trading/connections/${fixture.connection}`, { headers });
  }
});

test("Expo: a slot is the live record in its trust frame, and its row steps aside", async ({
  page,
  context,
}) => {
  const fixture = python("setup");
  const csrf = fixture.cookies.find((row) => row.name === "lonora_csrf").value;
  const headers = { "X-CSRF-Token": csrf };
  await context.addCookies(
    fixture.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "ar"));
  await page.setViewportSize({ width: 390, height: 844 });
  try {
    const input = { thread_id: fixture.thread.id, connection: fixture.connection };
    const ids = python("records", input);
    await page.goto(`/thread?id=${fixture.thread.id}`);
    // No message embeds the approval yet: it stands in its own row.
    await expect(page.getByText("طلب تداول", { exact: true })).toHaveCount(1);
    await expect(page.getByText("الوسيط لم يؤكد هذه الصفقة", { exact: true })).toHaveCount(1);
    await expect(page.getByTestId("ui-slot-trade_approval")).toHaveCount(0);
    python("slots", { ...input, record: ids.approval });
    python("slots", { ...input, card: "settle", record: ids.settle });
    python("slots", { ...input, card: "mandate", record: ids.mandate });
    await page.reload();
    // The Mandate card in its slot: the agent's mode read live, one button for the other.
    const mandate = page.getByTestId("ui-slot-mandate");
    await expect(mandate).toBeVisible();
    await expect(mandate.getByText("التفويض", { exact: true })).toBeVisible();
    await expect(mandate.getByRole("button", { name: "وكّله", exact: true })).toBeVisible();
    await expect(page.getByText("التفويض", { exact: true })).toHaveCount(1);
    // The settle card too: drawn in its slot from the live record, its row gone.
    const settle = page.getByTestId("ui-slot-settle");
    await expect(settle).toBeVisible();
    await expect(settle.getByText(/XAGUSD/)).toBeVisible();
    await expect(page.getByText("الوسيط لم يؤكد هذه الصفقة", { exact: true })).toHaveCount(1);
    const slot = page.getByTestId("ui-slot-trade_approval");
    await expect(slot).toBeVisible();
    // The server's record, drawn natively; none of the words the agent tried to give it.
    await expect(slot.getByText("بطاقة ثابتة من Lonora")).toBeVisible();
    await expect(slot.getByText(/XAUUSD/)).toBeVisible();
    for (const forged of ["صفقة مضمونة", "0.50 لوت"])
      await expect(slot.getByText(forged)).toHaveCount(0);
    // The slot is its place now: one approval card on the screen, inside the slot.
    await expect(page.getByText("طلب تداول", { exact: true })).toHaveCount(1);
    const [decision] = await Promise.all([
      page.waitForResponse((response) =>
        response.url().endsWith(`/api/trading/approvals/${ids.approval}/decision`),
      ),
      slot.getByRole("button", { name: "رفض", exact: true }).click(),
    ]);
    expect(decision.status()).toBe(200);
    await expect(slot.getByRole("button", { name: "رفض", exact: true })).toHaveCount(0);
    await page.reload();
    await expect(page.getByTestId("ui-slot-trade_approval")).toBeVisible();
    await expect(page.getByText("طلب تداول", { exact: true })).toHaveCount(1);
  } finally {
    await context.request.delete(`/api/agents/${fixture.agent.id}`, { headers });
    await context.request.delete(`/api/trading/connections/${fixture.connection}`, { headers });
  }
});
