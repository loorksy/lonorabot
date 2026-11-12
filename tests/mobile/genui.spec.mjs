// M-a (GENUI_PLAN §9.7, §10.2 item 9): on mobile, Stop cancels a queued card submission sent
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
    // A submission that never ran does not lock its card (§9.3).
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
      await page.goto(`/thread?id=${fixture.thread.id}`);
      const ux = page.getByTestId("ux-card").filter({ hasText: "حاسبة حجم الصفقة" });
      await expect(ux).toBeVisible();
      await expect(page.getByTestId("ux-card").filter({ hasText: "تنبيه سعر" })).toBeVisible();
      await ux.getByRole("button", { name: "المزيد" }).click();
      // «2%» (a set action) shows the Note its `when` hides at 1%.
      await ux.getByRole("button", { name: "2%", exact: true }).click();
      await expect(ux.getByText("مخاطرة مرتفعة")).toBeVisible();
      const drawn = await page
        .locator('[data-testid^="ux-node-"]:not([data-testid$="-off"])')
        .evaluateAll((nodes) => [
          ...new Set(nodes.map((node) => node.dataset.testid.split("-")[2])),
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
    } finally {
      await context.request.delete(`/api/agents/${fixture.agent.id}`, { headers });
      await context.request.delete(`/api/trading/connections/${fixture.connection}`, { headers });
    }
  });
}
