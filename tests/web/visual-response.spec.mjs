// Native GenUI acceptance over Lonora's authenticated conversation and outbox.
// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: Playwright environment is not cached by Turbo.
import { randomUUID } from "node:crypto";
import { appendFileSync, readFileSync } from "node:fs";
import { test as base, expect } from "@playwright/test";
import { visualFixture } from "../fixtures/visual-response.mjs";
import { brokerFixture } from "./broker-fixture.mjs";

let session;
const test = base.extend({
  conversation: async ({ context, page }, use) => {
    const credentials = {
      email: process.env.LONORA_UI_TEST_EMAIL ?? "ci@example.com",
      password: process.env.LONORA_UI_TEST_PASSWORD ?? "ci-only-owner-password",
    };
    if (!(await (await context.request.get("/api/onboarding")).json()).owner_initialized) {
      const response = await context.request.post("/api/onboarding", {
        data: {
          ...credentials,
          bootstrap_token: process.env.LONORA_BOOTSTRAP_TOKEN ?? "lonora-ui-bootstrap-ci-only-2026",
        },
      });
      expect(response.status()).toBe(201);
    }
    if (session) await context.addCookies(session.cookies);
    if (!session || (await context.request.get("/api/auth/session")).status() !== 200) {
      const login = await context.request.post("/api/auth/login", { data: credentials });
      expect(login.status()).toBe(200);
      session = { cookies: await context.cookies(), csrf: (await login.json()).csrf };
    }
    const headers = { "X-CSRF-Token": session.csrf };
    const broker = await brokerFixture(context, headers);
    const response = await context.request.post("/api/agents", {
      headers,
      data: { name: `Visual response ${randomUUID()}`, ...broker.binding },
    });
    expect(response.status()).toBe(201);
    const agent = await response.json();
    const threadResponse = await context.request.post(`/api/agents/${agent.id}/conversation`, {
      headers,
      data: {},
    });
    expect(threadResponse.ok()).toBeTruthy();
    const thread = await threadResponse.json();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    try {
      await use({ agent, thread, headers });
      expect(errors).toEqual([]);
    } finally {
      await page.goto("about:blank");
      await context.request.delete(`/api/agents/${agent.id}`, { headers });
      await broker.close();
    }
  },
});

for (const variant of [
  { locale: "en", theme: "dark", width: 1440, height: 900 },
  { locale: "en", theme: "light", width: 390, height: 844 },
  { locale: "ar", theme: "dark", width: 390, height: 844 },
  { locale: "ar", theme: "light", width: 1440, height: 900 },
]) {
  test(`native composition, local interaction and reload in ${variant.locale}/${variant.theme}`, async ({
    page,
    context,
    conversation,
  }) => {
    await page.setViewportSize({ width: variant.width, height: variant.height });
    await page.addInitScript(({ locale, theme }) => {
      localStorage.setItem("lonora.locale", locale);
      localStorage.setItem("lonora.theme", JSON.stringify(theme));
    }, variant);
    const upload = await context.request.post("/api/artifacts/upload", {
      headers: conversation.headers,
      multipart: {
        thread_id: conversation.thread.id,
        file: {
          name: "verified.png",
          mimeType: "image/png",
          buffer: Buffer.from(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=",
            "base64",
          ),
        },
      },
    });
    expect(upload.status()).toBe(201);
    const artifact = await upload.json();
    const message = {
      id: randomUUID(),
      thread_id: conversation.thread.id,
      agent_id: conversation.agent.id,
      seq: 1,
      role: "assistant",
      content: "Plain fallback for legacy clients.",
      rich_content: visualFixture({ artifactId: artifact.id }),
      reply_to: null,
      attachment_ids: [],
      created_at: "2026-10-25T10:00:00Z",
    };
    await page.route(`**/api/threads/${conversation.thread.id}/messages*`, (route) => {
      if (route.request().method() === "GET") return route.fulfill({ json: [message] });
      return route.continue();
    });
    const mutations = [];
    page.on("request", (request) => {
      if (request.method() !== "GET" && request.url().includes("/api/"))
        mutations.push({ url: new URL(request.url()).pathname, body: request.postDataJSON() });
    });
    await page.goto(`/app/${conversation.agent.id}`);
    const response = page.locator(".native-visual-response");
    await expect(response).toBeVisible();
    mutations.length = 0;
    await expect(
      page.getByText("This is an interactive illustration, using no live account data."),
    ).toBeVisible();
    await expect(page.getByText("Plain fallback for legacy clients.")).toHaveCount(0);
    const metric = page.locator('[data-visual-value="calculated"]');
    const numeric = async () =>
      metric.evaluate((element) =>
        element.textContent.replace(/[٠-٩]/g, (value) => String(value.charCodeAt(0) - 0x660)),
      );
    await expect.poll(numeric).toBe("20");
    await page.getByRole("spinbutton", { name: "Quantity", exact: true }).fill("4");
    await expect.poll(numeric).toBe("40");
    const slider = page.getByRole("slider", { name: "Risk input", exact: true });
    await slider.press("End");
    await expect.poll(numeric).toBe("120");
    await slider.press("Home");
    const increase = await slider.evaluate((input) =>
      getComputedStyle(input).direction === "rtl" ? "ArrowLeft" : "ArrowRight",
    );
    for (let index = 0; index < 9; index += 1) await slider.press(increase);
    await expect.poll(numeric).toBe("40");
    await page.getByRole("checkbox", { name: "Show additional context" }).check();
    await expect(page.getByText("Additional context is visible.")).toBeVisible();
    await page.getByRole("combobox", { name: "Pace", exact: true }).selectOption("fast");
    await page.getByRole("textbox", { name: "Search illustration", exact: true }).fill("Beta");
    await expect(page.getByRole("cell", { name: "Alpha", exact: true })).toHaveCount(0);
    await expect(page.getByRole("cell", { name: "Beta", exact: true })).toBeVisible();
    const filter = page.locator(".native-visual-filter input");
    await filter.fill("Alpha");
    await expect(page.getByRole("cell", { name: "Alpha", exact: true })).toBeVisible();
    await expect(page.getByRole("cell", { name: "Beta", exact: true })).toHaveCount(0);
    await filter.fill("Beta");
    await expect(page.getByRole("img", { name: "line illustration", exact: true })).toHaveCount(1);
    await expect(page.getByRole("img", { name: "bar illustration", exact: true })).toHaveCount(1);
    await expect(page.getByRole("img", { name: "pie illustration", exact: true })).toHaveCount(1);
    await page.getByRole("tab", { name: "Flow", exact: true }).click();
    await expect(page.getByRole("tabpanel")).toBeVisible();
    await expect(page.getByRole("img", { name: "Illustrative flow", exact: true })).toBeVisible();
    await page.getByText("Illustration details", { exact: true }).click();
    await expect(page.getByText("No broker action is performed by local controls.")).toBeVisible();
    expect(mutations).toEqual([]);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
      ),
    ).toBe(true);
    await page.reload();
    await expect(response).toBeVisible();
    await expect.poll(numeric).toBe("40");
    await expect(page.getByRole("checkbox", { name: "Show additional context" })).toBeChecked();
    await expect(page.getByRole("combobox", { name: "Pace", exact: true })).toHaveValue("fast");
    await expect(
      page.getByRole("textbox", { name: "Search illustration", exact: true }),
    ).toHaveValue("Beta");
    await expect(page.getByRole("tab", { name: "Flow", exact: true })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    mutations.length = 0;
    await page.getByRole("button", { name: "Open image", exact: true }).click();
    await expect(page.locator(".workspace-file-preview")).toBeVisible();
    expect(mutations).toEqual([]);
    await page
      .getByRole("dialog")
      .getByRole("button", { name: variant.locale === "ar" ? "إغلاق" : "Close", exact: true })
      .click();
    await page
      .getByRole("heading", { name: "Native response illustration", exact: true })
      .scrollIntoViewIfNeeded();
    await page.screenshot({
      path: `.runtime/visual-web-${variant.locale}-${variant.theme}.png`,
      fullPage: true,
    });
    // Follow-up is the ordinary authenticated message route; controls above made no server call.
    const sent = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname.endsWith(`/threads/${conversation.thread.id}/messages`),
    );
    await page.getByRole("button", { name: "Discuss these inputs", exact: true }).click();
    expect((await sent).status()).toBe(202);
    await expect
      .poll(() => mutations.filter((request) => request.url.endsWith("/messages")).length)
      .toBe(1);
    const send = mutations.find((request) => request.url.endsWith("/messages"));
    expect(send.body.content).toBe("Discuss quantity 4, risk 10, pace fast.");
    expect(mutations.every((request) => request.url.endsWith("/messages"))).toBe(true);
  });
}

test("invalid or executable display content falls back to the original text", async ({
  page,
  conversation,
}) => {
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  await page.route(`**/api/threads/${conversation.thread.id}/messages*`, (route) =>
    route.fulfill({
      json: [
        {
          id: randomUUID(),
          thread_id: conversation.thread.id,
          agent_id: conversation.agent.id,
          seq: 1,
          role: "assistant",
          content: "The original answer is still available.",
          rich_content: {
            version: 1,
            parts: [
              {
                type: "ui",
                document: {
                  version: 1,
                  mode: "observed",
                  root: {
                    id: "bad",
                    type: "button",
                    label: "Do not execute",
                    action: { kind: "execute_trade", text: "buy" },
                  },
                },
              },
            ],
          },
          reply_to: null,
          attachment_ids: [],
          created_at: "2026-10-25T10:00:00Z",
        },
      ],
    }),
  );
  await page.goto(`/app/${conversation.agent.id}`);
  await expect(page.getByText("The original answer is still available.")).toBeVisible();
  await expect(page.locator(".native-visual-response")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Do not execute" })).toHaveCount(0);
});

for (const locale of ["en", "ar"]) {
  test(`compact numeric drafts remain editable on a phone in ${locale}`, async ({
    page,
    conversation,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.addInitScript((language) => {
      localStorage.setItem("lonora.locale", language);
      localStorage.setItem("lonora.theme", JSON.stringify("dark"));
    }, locale);
    const state = { a: 1, b: 1000, c: 3, d: 4, e: 5, f: 6 };
    const document = {
      version: 1,
      mode: "example",
      state,
      root: {
        id: "calc",
        type: "card",
        label: "Educational calculation",
        children: [
          {
            id: "fields",
            type: "grid",
            columns: 2,
            children: Object.keys(state).map((key) => ({
              id: key,
              type: "input",
              label: `Input ${key}`,
              input_kind: "number",
              state_key: key,
              minimum: key === "b" ? 100 : -100,
              maximum: key === "b" ? 10000 : 100,
              step: key === "a" ? 1 : 0.01,
            })),
          },
          {
            id: "metrics",
            type: "grid",
            columns: 2,
            children: [
              { id: "m1", type: "metric", label: "Quantity", value: { state: "a" } },
              {
                id: "m2",
                type: "metric",
                label: "Double",
                value: { op: "mul", args: [{ state: "a" }, 2] },
              },
            ],
          },
        ],
      },
    };
    const row = {
      id: randomUUID(),
      thread_id: conversation.thread.id,
      agent_id: conversation.agent.id,
      seq: 1,
      role: "assistant",
      content: "Educational example.",
      rich_content: { version: 1, parts: [{ type: "ui", document }] },
      reply_to: null,
      attachment_ids: [],
      created_at: "2026-10-26T08:00:00Z",
    };
    await page.route(`**/api/threads/${conversation.thread.id}/messages*`, (route) =>
      route.request().method() === "GET" ? route.fulfill({ json: [row] }) : route.continue(),
    );
    await page.goto(`/app/${conversation.agent.id}`);
    const response = page.locator('[data-visual-document="calc"]');
    await expect(response).toBeVisible();
    const mutations = [];
    page.on("request", (request) => {
      if (request.method() !== "GET" && request.url().includes("/api/"))
        mutations.push(request.url());
    });
    const height = (await response.boundingBox()).height;
    expect(height).toBeLessThan(550);
    const geometry = await page.evaluate(() => {
      const fields = document.querySelector('[data-visual-node="fields"]');
      const input = fields.querySelector("input");
      return {
        gridColumns: getComputedStyle(fields).gridTemplateColumns,
        inputFont: getComputedStyle(input).fontSize,
        inputHeight: input.getBoundingClientRect().height,
        rootWidth: document.documentElement.clientWidth,
        scrollWidth: document.documentElement.scrollWidth,
      };
    });
    expect(geometry.gridColumns.split(" ")).toHaveLength(2);
    expect(geometry.inputHeight).toBeGreaterThanOrEqual(44);
    expect(geometry.inputFont).toBe("16px");
    expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.rootWidth + 1);
    const input = page.getByRole("spinbutton", { name: "Input a", exact: true });
    await input.fill("");
    await input.pressSequentially("-1.25");
    await expect(input).toHaveValue("-1.25");
    await expect(input).toHaveAttribute("aria-valuenow", "-1.25");
    const derived = page.locator('[data-visual-value="m2"]');
    await expect(derived).toHaveText(new Intl.NumberFormat(locale).format(-2.5));
    const bounded = page.getByRole("spinbutton", { name: "Input b", exact: true });
    await bounded.fill("");
    await bounded.pressSequentially("2");
    await expect(bounded).not.toHaveAttribute("aria-valuenow");
    await bounded.pressSequentially("50");
    await expect(bounded).toHaveValue("250");
    await expect(bounded).toHaveAttribute("aria-valuenow", "250");
    await input.fill("1.");
    await expect(input).toHaveValue("1.");
    await bounded.focus();
    await expect(input).toHaveValue("1");
    await input.fill("-");
    await expect(input).toHaveValue("-");
    await bounded.focus();
    await expect(input).toHaveValue("1");
    await input.fill("١٢٫٥");
    await expect(input).toHaveValue("١٢٫٥");
    await expect(derived).toHaveText(new Intl.NumberFormat(locale).format(25));
    await input.press("ArrowUp");
    await expect(input).toHaveValue("13.5");
    await bounded.fill("20000");
    await input.focus();
    await expect(bounded).toHaveValue("10000");
    expect(mutations).toEqual([]);
    appendFileSync(
      ".runtime/visual-density-after.jsonl",
      `${JSON.stringify({ locale, height, geometry, numeric: "editable/decimal/Arabic/bounds passed" })}\n`,
    );
    await response.screenshot({ path: `.runtime/visual-density-after-${locale}.png` });
    await page.reload();
    await expect(input).toHaveValue("13.5");
    await expect(bounded).toHaveValue("10000");
  });
}

test("dense tables, charts and diagrams remain local and contained at 320px", async ({
  page,
  conversation,
}) => {
  await page.setViewportSize({ width: 320, height: 740 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "ar"));
  const document = {
    version: 1,
    mode: "example",
    root: {
      id: "compact",
      type: "column",
      children: [
        {
          id: "table",
          type: "table",
          label: "جدول توضيحي",
          fields: [
            { key: "name", label: "الاسم" },
            { key: "amount", label: "القيمة" },
            { key: "detail", label: "التفاصيل" },
          ],
          rows: Array.from({ length: 12 }, (_, index) => ({
            name: `Illustrative symbol ${index}`,
            amount: index * 12.5,
            detail: "شرح طويل توضيحي مستقل عن بيانات الحساب",
          })),
        },
        {
          id: "chart",
          type: "chart",
          chart_kind: "line",
          label: "رسم توضيحي",
          points: Array.from({ length: 12 }, (_, index) => ({
            label: `Example ${index}`,
            value: index * 12.5,
          })),
        },
        {
          id: "diagram",
          type: "diagram",
          label: "مخطط توضيحي",
          vertices: [
            { id: "a", label: "قراءة السوق والتحقق من البيانات الحديثة قبل التحليل" },
            { id: "b", label: "تفسير البيانات وتوضيح النتيجة باللغة المناسبة" },
          ],
          edges: [{ source: "a", target: "b", label: "شرح توضيحي" }],
        },
      ],
    },
  };
  await page.route(`**/api/threads/${conversation.thread.id}/messages*`, (route) =>
    route.fulfill({
      json: [
        {
          id: randomUUID(),
          thread_id: conversation.thread.id,
          agent_id: conversation.agent.id,
          seq: 1,
          role: "assistant",
          content: "Illustrative examples.",
          rich_content: { version: 1, parts: [{ type: "ui", document }] },
          reply_to: null,
          attachment_ids: [],
          created_at: "2026-10-26T08:00:00Z",
        },
      ],
    }),
  );
  await page.goto(`/app/${conversation.agent.id}`);
  await expect(page.locator(".native-visual-response")).toBeVisible();
  const mutations = [];
  page.on("request", (request) => {
    if (request.method() !== "GET" && request.url().includes("/api/"))
      mutations.push(request.url());
  });
  await expect(page.locator(".native-visual-table tbody tr")).toHaveCount(8);
  await page.getByRole("button", { name: "عرض المزيد (12)", exact: true }).click();
  await expect(page.locator(".native-visual-table tbody tr")).toHaveCount(12);
  await page.getByRole("button", { name: "عرض أقل", exact: true }).click();
  await expect(page.locator(".native-visual-table tbody tr")).toHaveCount(8);
  await expect(page.locator(".native-visual-table th[data-numeric]")).toHaveText("القيمة");
  await expect(page.locator(".native-visual-chart-values > div:visible")).toHaveCount(8);
  await page.locator(".native-visual-chart-more summary").click();
  await expect(page.locator(".native-visual-chart-values > div:visible")).toHaveCount(12);
  await page.locator(".native-visual-diagram-description summary").click();
  await expect(page.locator(".native-visual-diagram-description li")).toHaveCount(2);
  expect(mutations).toEqual([]);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
    ),
  ).toBe(true);
  const table = page.locator(".native-visual-table-scroll");
  await table.focus();
  expect(
    await table.evaluate((element) => Number.parseFloat(getComputedStyle(element).outlineWidth)),
  ).toBeGreaterThanOrEqual(2);
  expect(await table.evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(true);
  await page.screenshot({ path: ".runtime/visual-320px-after.png", fullPage: true });
});

// Replay only when a live, existing-Agent acceptance record was explicitly supplied.
// The regular deterministic cases above always execute without a model or network provider.
if (process.env.LONORA_MODEL_VISUAL_RESULT) {
  const recorded = JSON.parse(readFileSync(process.env.LONORA_MODEL_VISUAL_RESULT, "utf8"));
  test("live-model composed response renders through the native message boundary", async ({
    page,
    conversation,
  }) => {
    expect(recorded.rich_content?.version).toBe(1);
    expect(recorded.rich_content.parts.some((part) => part.type === "ui")).toBe(true);
    await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
    await page.route(`**/api/threads/${conversation.thread.id}/messages*`, (route) =>
      route.fulfill({
        json: [
          {
            id: randomUUID(),
            thread_id: conversation.thread.id,
            agent_id: conversation.agent.id,
            seq: 1,
            role: "assistant",
            content: recorded.content,
            rich_content: recorded.rich_content,
            reply_to: null,
            attachment_ids: [],
            created_at: "2026-10-25T10:00:00Z",
          },
        ],
      }),
    );
    await page.goto(`/app/${conversation.agent.id}`);
    await expect(page.locator(".native-visual-response")).toBeVisible();
    await expect(page.locator(".native-visual-response").first()).toHaveAttribute(
      "data-visual-mode",
      "observed",
    );
    let checked = 0;
    for (const part of recorded.rich_content.parts) {
      if (part.type !== "ui") continue;
      const walk = async (node) => {
        if (
          node.type === "metric" &&
          node.value &&
          typeof node.value === "object" &&
          "source" in node.value
        ) {
          const scalar = part.document.facts[node.value.source]?.value;
          expect(scalar).not.toBeUndefined();
          const shown =
            typeof scalar === "number"
              ? new Intl.NumberFormat("en", { maximumFractionDigits: 8 }).format(scalar)
              : String(scalar);
          await expect(page.locator(`[data-visual-value="${node.id}"]`)).toHaveText(shown);
          checked += 1;
        }
        for (const child of node.children ?? []) await walk(child);
      };
      await walk(part.document.root);
    }
    if (!checked) {
      // Presentation is model-owned: a table/chart with a derived total is also
      // valid. Do not force a particular metric template in the acceptance test.
      const rendered = await page.locator(".native-visual-response").allTextContents();
      for (const part of recorded.rich_content.parts) {
        if (part.type !== "ui") continue;
        for (const fact of Object.values(part.document.facts ?? {})) {
          const shown =
            typeof fact.value === "number"
              ? new Intl.NumberFormat("en", { maximumFractionDigits: 8 }).format(fact.value)
              : String(fact.value);
          if (rendered.some((text) => text.includes(shown))) checked += 1;
        }
      }
    }
    expect(checked).toBeGreaterThan(0);
    await page.locator(".native-visual-response").first().screenshot({
      path: ".runtime/visual-web-live-model.png",
    });
  });
}
