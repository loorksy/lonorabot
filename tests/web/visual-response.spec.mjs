// Native GenUI acceptance over Lonora's authenticated conversation and outbox.
// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: Playwright environment is not cached by Turbo.
import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
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
    expect(checked).toBeGreaterThan(0);
    await page.screenshot({ path: ".runtime/visual-web-live-model.png", fullPage: true });
  });
}
