// OpenUI-derived chat interaction acceptance over Lonora's actual API and outbox.
// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: Playwright environment is not cached by Turbo.
import { randomUUID } from "node:crypto";
import { test as base, expect } from "@playwright/test";
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
      data: { name: `Chat UX ${randomUUID()}`, ...broker.binding },
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
      await context.request.delete(`/api/agents/${agent.id}`, { headers });
      await broker.close();
    }
  },
});

function message(conversation, seq, role, content) {
  return {
    id: `ux-message-${seq}`,
    thread_id: conversation.thread.id,
    agent_id: conversation.agent.id,
    seq,
    role,
    content,
    reply_to: null,
    attachment_ids: [],
    created_at: "2026-10-25T10:00:00Z",
  };
}

for (const variant of [
  { locale: "en", theme: "dark", width: 1440, height: 900 },
  { locale: "ar", theme: "light", width: 390, height: 844 },
]) {
  test(`shared reading column, unboxed reply and growing floating composer in ${variant.locale}/${variant.theme}`, async ({
    page,
    conversation,
  }) => {
    await page.setViewportSize({ width: variant.width, height: variant.height });
    await page.addInitScript(({ locale, theme }) => {
      localStorage.setItem("lonora.locale", locale);
      localStorage.setItem("lonora.theme", JSON.stringify(theme));
    }, variant);
    const rows = [
      message(
        conversation,
        1,
        "user",
        variant.locale === "ar" ? "كيف وضع الحساب؟" : "How is my account?",
      ),
      message(
        conversation,
        2,
        "assistant",
        variant.locale === "ar"
          ? "لا توجد بيانات حديثة مؤكدة لهذا الحساب."
          : "No fresh verified account information is available.",
      ),
    ];
    await page.route(`**/api/threads/${conversation.thread.id}/messages*`, (route) =>
      route.fulfill({ json: rows }),
    );
    await page.goto(`/app/${conversation.agent.id}`);
    await expect(page.locator("[data-message-id='ux-message-2']")).toBeVisible();
    const composer = page.getByRole("combobox", {
      name: variant.locale === "ar" ? "الرسالة" : "Message",
      exact: true,
    });
    const bar = page.getByTestId("composer-bar");
    const initial = await bar.boundingBox();
    expect(initial.height).toBeGreaterThanOrEqual(55);
    expect(initial.height).toBeLessThanOrEqual(58);
    const geometry = await page.evaluate(() => {
      const content = document
        .querySelector(".template-transcript-content")
        .getBoundingClientRect();
      const composer = document.querySelector(".template-composer-bar").getBoundingClientRect();
      const assistant = getComputedStyle(
        document.querySelector(".template-message.assistant .template-message-text"),
      );
      return {
        content: content.width,
        composer: composer.width,
        assistantFill: assistant.backgroundColor,
        width: document.documentElement.clientWidth,
        scroll: document.documentElement.scrollWidth,
      };
    });
    if (variant.width > 767) {
      expect(geometry.content).toBeCloseTo(728, 0);
      expect(geometry.composer).toBeCloseTo(geometry.content, 0);
      expect(await composer.evaluate((input) => document.activeElement === input)).toBe(true);
      expect(
        await page.locator(".tpl-main").evaluate((main) => getComputedStyle(main).borderRadius),
      ).toBe("22px");
    } else {
      expect(geometry.composer).toBeLessThanOrEqual(variant.width - 24);
      expect(await composer.evaluate((input) => document.activeElement === input)).toBe(false);
    }
    expect(geometry.assistantFill).toBe("rgba(0, 0, 0, 0)");
    expect(geometry.scroll).toBeLessThanOrEqual(geometry.width + 1);
    await composer.fill(Array.from({ length: 24 }, (_, index) => `Line ${index + 1}`).join("\n"));
    await expect.poll(() => composer.evaluate((input) => input.clientHeight)).toBe(200);
    // Filling leaves the caret at the bottom, as ordinary typing does. Move
    // deliberately to the top before checking the lower overflow affordance.
    await composer.evaluate((input) => {
      input.scrollTop = 0;
      input.dispatchEvent(new Event("scroll", { bubbles: true }));
    });
    await expect(bar).toHaveAttribute("data-overflow-bottom", "true");
    await composer.evaluate((input) => {
      input.scrollTop = input.scrollHeight;
      input.dispatchEvent(new Event("scroll", { bubbles: true }));
    });
    await expect(bar).toHaveAttribute("data-overflow-top", "true");
    const box = await bar.boundingBox();
    expect(box.y + box.height).toBeLessThanOrEqual(variant.height);
    await composer.fill("Short draft");
    await expect.poll(() => composer.evaluate((input) => input.clientHeight)).toBe(32);
    await page.screenshot({
      path: `.runtime/openui-chat-${variant.locale}-${variant.theme}.png`,
      fullPage: true,
    });
  });
}

test("composer respects IME and multiline input while preserving immediate sends and ongoing steering", async ({
  page,
  conversation,
}) => {
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  let posts = 0;
  await page.route(`**/api/threads/${conversation.thread.id}/messages`, (route) => {
    if (route.request().method() === "POST") posts += 1;
    return route.continue();
  });
  await page.goto(`/app/${conversation.agent.id}`);
  const composer = page.getByRole("combobox", { name: "Message", exact: true });
  await composer.fill("A composed draft");
  await composer.dispatchEvent("keydown", { key: "Enter", code: "Enter", isComposing: true });
  await expect(composer).toHaveValue("A composed draft");
  expect(posts).toBe(0);
  await composer.press("End");
  await composer.press("Shift+Enter");
  await expect(composer).toHaveValue("A composed draft\n");
  expect(posts).toBe(0);
  await composer.press("Enter");
  await expect(
    page.getByTestId("transcript").getByText("A composed draft", { exact: true }),
  ).toHaveCount(1);
  await expect(composer).toHaveValue("");
  await expect(page.getByRole("button", { name: "Stop", exact: true })).toHaveCount(1);
  await expect(page.getByRole("button", { name: "Send direction", exact: true })).toHaveCount(0);
  expect(posts).toBe(1);
  await composer.fill("Continue with this direction");
  await expect(page.getByRole("button", { name: "Send direction", exact: true })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Stop", exact: true })).toHaveCount(1);
});

test("manual transcript scrolling is preserved as fresh content arrives", async ({
  page,
  conversation,
}) => {
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const rows = Array.from({ length: 24 }, (_, index) =>
    message(
      conversation,
      index + 1,
      index % 2 ? "assistant" : "user",
      `History ${index}: ${"Long bounded conversation text. ".repeat(8)}`,
    ),
  );
  await page.route(`**/api/threads/${conversation.thread.id}/messages*`, (route) =>
    route.fulfill({ json: rows }),
  );
  await page.goto(`/app/${conversation.agent.id}`);
  const transcript = page.getByTestId("transcript");
  await expect(page.locator("[data-message-id='ux-message-24']")).toBeVisible();
  const composer = page.getByRole("combobox", { name: "Message", exact: true });
  await composer.fill(Array.from({ length: 16 }, (_, index) => `Draft ${index}`).join("\n"));
  await expect
    .poll(() =>
      transcript.evaluate(
        (element) => element.scrollHeight - element.clientHeight - element.scrollTop,
      ),
    )
    .toBeLessThanOrEqual(2);
  const latest = await page.locator("[data-message-id='ux-message-24']").boundingBox();
  const growingBar = await page.getByTestId("composer-bar").boundingBox();
  expect(latest.y + latest.height).toBeLessThan(growingBar.y);
  await composer.fill("");
  await transcript.evaluate((element) => {
    element.scrollTop = 150;
    element.dispatchEvent(new Event("scroll", { bubbles: true }));
  });
  await expect(page.getByRole("button", { name: "Jump to latest", exact: true })).toBeVisible();
  rows.push(message(conversation, 25, "assistant", "New content while the owner reads above."));
  await page.evaluate(() => window.dispatchEvent(new Event("online")));
  await expect(page.locator("[data-message-id='ux-message-25']")).toHaveCount(1);
  expect(await transcript.evaluate((element) => element.scrollTop)).toBeLessThan(200);
  await page.getByRole("button", { name: "Jump to latest", exact: true }).click();
  await expect(page.getByRole("button", { name: "Jump to latest", exact: true })).toHaveCount(0);
  const newest = await page.locator("[data-message-id='ux-message-25']").boundingBox();
  const restingBar = await page.getByTestId("composer-bar").boundingBox();
  expect(newest.y + newest.height).toBeLessThan(restingBar.y);
});
