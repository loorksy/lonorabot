import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

function simulation(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}

async function setup(context, locale) {
  const data = simulation({ action: "init", empty: true });
  await context.addCookies(
    data.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript((value) => localStorage.setItem("lonora.locale", value), locale);
  const headers = { "X-CSRF-Token": data.cookies.find((row) => row.name === "lonora_csrf").value };
  const created = [];
  async function create() {
    const response = await context.request.post("/api/agents", {
      headers,
      data: {
        name: `Native permission ${randomUUID()}`,
        trading_account_id: data.account,
        trading_symbol: data.symbol,
      },
    });
    expect(response.status()).toBe(201);
    const agent = await response.json();
    created.push(agent.id);
    const conversation = await context.request.post(`/api/agents/${agent.id}/conversation`, {
      headers,
      data: {},
    });
    expect(conversation.ok()).toBeTruthy();
    return { agent, thread: await conversation.json() };
  }
  const selected = await create();
  return {
    ...selected,
    data,
    create,
    async open(page, value = selected) {
      await page.goto(`/thread?id=${value.thread.id}`);
      await expect(page.getByTestId("permission-selector-native")).toBeVisible();
    },
    async state(id = selected.agent.id) {
      const response = await context.request.get(`/api/agents/${id}/permissions`);
      expect(response.ok()).toBeTruthy();
      return response.json();
    },
    async cleanup() {
      for (const id of created.reverse())
        await context.request.delete(`/api/agents/${id}`, { headers });
      simulation({ ...data, action: "cleanup" });
    },
  };
}

const layouts = [
  { label: "standard mobile EN", locale: "en", width: 390, height: 844 },
  { label: "narrow mobile EN", locale: "en", width: 320, height: 640 },
  { label: "landscape mobile AR", locale: "ar", width: 844, height: 390 },
];

async function insideViewport(page, control) {
  await expect
    .poll(async () => {
      const box = await control.boundingBox();
      const viewport = page.viewportSize();
      return Boolean(box && viewport && box.y >= 0 && box.y + box.height <= viewport.height + 1);
    })
    .toBeTruthy();
}

for (const layout of layouts)
  test(`Expo ${layout.label}: permissions persist, preserve the composer and keep unsigned autonomy inactive`, async ({
    page,
    context,
  }) => {
    test.setTimeout(60000);
    await page.setViewportSize({ width: layout.width, height: layout.height });
    const state = await setup(context, layout.locale);
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    try {
      await state.open(page);
      expect((await state.state()).effective_level).toBe("analysis");
      const composer = page.getByRole("textbox", {
        name: layout.locale === "ar" ? "اكتب رسالة…" : "Message…",
        exact: true,
      });
      const draft = "Keep this market question unsent — لا ترسلها";
      await composer.fill(draft);
      await page.getByTestId("permission-selector-native").click();
      const sheet = page.getByTestId("permission-sheet-native");
      for (const level of ["analysis", "supervised", "autonomous"])
        await expect(sheet.getByTestId(`permission-choice-${level}`)).toBeVisible();
      if (layout.height > layout.width) {
        for (const level of ["analysis", "supervised", "autonomous"])
          await insideViewport(page, sheet.getByTestId(`permission-choice-${level}`));
      } else {
        const last = sheet.getByTestId("permission-choice-autonomous");
        await last.scrollIntoViewIfNeeded();
        await insideViewport(page, last);
      }
      await expect(sheet.getByTestId("permission-advanced-native")).toHaveCount(0);
      if (layout.width === 390)
        await page.screenshot({ path: ".runtime/permission-qa-native-web-sheet.png" });
      await sheet.getByTestId("permission-choice-supervised").click();
      await expect.poll(async () => (await state.state()).effective_level).toBe("supervised");
      await expect(composer).toHaveValue(draft);
      await page.reload();
      await expect(page.getByTestId("permission-selector-native")).toBeVisible();
      expect((await state.state()).effective_level).toBe("supervised");
      await composer.fill(draft);
      await page.getByTestId("permission-selector-native").click();
      await sheet.getByTestId("permission-choice-autonomous").click();
      const review = page.getByTestId("permission-review-native");
      await expect(review).toBeVisible();
      const pending = await state.state();
      expect(pending.requested_level).toBe("autonomous");
      expect(pending.effective_level).toBe("supervised");
      expect(pending.active_authorities).toEqual([]);
      expect(pending.pending_authority.status).toBe("pending");
      await review.getByTestId("permission-review-advanced-native").click();
      const editor = page.getByTestId("permission-editor-native");
      await expect(editor).toBeVisible();
      for (const group of ["scope", "operations", "limits", "duration"])
        await expect(editor.getByTestId(`permission-group-${group}`)).toHaveAttribute(
          "aria-expanded",
          "false",
        );
      await editor.getByTestId("permission-group-scope").click();
      await expect(editor).toContainText(state.data.symbol);
      await editor.getByTestId("permission-group-limits").click();
      const limit = editor.getByTestId("permission-limit-maximum_order_volume-native");
      await limit.fill("0.05");
      await editor.getByTestId("permission-group-limits").click();
      await editor.getByTestId("permission-group-limits").click();
      await expect(limit).toHaveValue("0.05");
      await editor.getByTestId("permission-review-continue-native").click();
      await expect(review).toContainText("0.05");
      expect((await state.state()).effective_level).toBe("supervised");
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
        ),
      ).toBeTruthy();
      expect(errors).toEqual([]);
    } finally {
      await state.cleanup();
    }
  });
