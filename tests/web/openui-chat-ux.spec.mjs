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
  test(`the reference's reading column and growing floating composer in ${variant.locale}/${variant.theme}`, async ({
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
    // The reference's geometry (Desktop-37 327-435): a 760px reading column, a floating
    // composer card of at most 820px, a 28px field growing to min(164px, 34vh).
    const composer = page.locator(".composer textarea");
    const card = page.locator(".composer-card");
    const geometry = await page.evaluate(() => ({
      column: document.querySelector(".messages").getBoundingClientRect().width,
      card: document.querySelector(".composer-card").getBoundingClientRect().width,
      width: document.documentElement.clientWidth,
      scroll: document.documentElement.scrollWidth,
    }));
    expect(geometry.column).toBeLessThanOrEqual(760);
    expect(geometry.card).toBeLessThanOrEqual(820);
    expect(geometry.scroll).toBeLessThanOrEqual(geometry.width + 1);
    if (variant.width > 767)
      expect(await composer.evaluate((input) => document.activeElement === input)).toBe(true);
    else expect(await composer.evaluate((input) => document.activeElement === input)).toBe(false);
    await expect.poll(() => composer.evaluate((input) => input.clientHeight)).toBe(28);
    await composer.fill(Array.from({ length: 24 }, (_, index) => `Line ${index + 1}`).join("\n"));
    const cap = Math.min(164, Math.round(variant.height * 0.34));
    await expect.poll(() => composer.evaluate((input) => input.clientHeight)).toBe(cap);
    const box = await card.boundingBox();
    expect(box.y + box.height).toBeLessThanOrEqual(variant.height);
    await composer.fill("Short draft");
    await expect.poll(() => composer.evaluate((input) => input.clientHeight)).toBe(28);
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
  const composer = page.locator(".composer textarea");
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
  await expect(page.locator(".composer .stop")).toBeVisible();
  await expect(page.locator(".composer .send")).toBeHidden();
  expect(posts).toBe(1);
  await composer.fill("Continue with this direction");
  // A direction typed while the agent works: send comes back (steering) and ■ Stop stays
  // reachable, so the owner can always stop a run that may be heading to a trade.
  await expect(page.locator(".composer .send")).toBeVisible();
  await expect(page.locator(".composer .stop")).toBeVisible();
  await expect(page.getByRole("button", { name: "Stop the reply", exact: true })).toBeEnabled();
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
  const composer = page.locator(".composer textarea");
  await composer.fill(Array.from({ length: 16 }, (_, index) => `Draft ${index}`).join("\n"));
  await expect
    .poll(() =>
      transcript.evaluate(
        (element) => element.scrollHeight - element.clientHeight - element.scrollTop,
      ),
    )
    .toBeLessThanOrEqual(2);
  const latest = await page.locator("[data-message-id='ux-message-24']").boundingBox();
  const growingBar = await page.locator(".composer-card").boundingBox();
  expect(latest.y + latest.height).toBeLessThan(growingBar.y);
  await composer.fill("");
  await transcript.evaluate((element) => {
    element.scrollTop = 150;
    element.dispatchEvent(new Event("scroll", { bubbles: true }));
  });
  // The ↓ button turns on more than 260px from the newest message (reference syncJump).
  await expect(page.locator(".jump")).toHaveClass(/\bon\b/);
  rows.push(message(conversation, 25, "assistant", "New content while the owner reads above."));
  await page.evaluate(() => window.dispatchEvent(new Event("online")));
  await expect(page.locator("[data-message-id='ux-message-25']")).toHaveCount(1);
  expect(await transcript.evaluate((element) => element.scrollTop)).toBeLessThan(200);
  await page.locator(".jump").click();
  await expect(page.locator(".jump")).not.toHaveClass(/\bon\b/);
  const newest = await page.locator("[data-message-id='ux-message-25']").boundingBox();
  const restingBar = await page.locator(".composer-card").boundingBox();
  expect(newest.y + newest.height).toBeLessThan(restingBar.y);
});

test("M6: leaving the chat while recording releases the microphone and sends nothing", async ({
  page,
  conversation,
}) => {
  await page.addInitScript(() => {
    localStorage.setItem("lonora.locale", "en");
    // A real audio track (an oscillator) whose stop() is counted.
    window.__micStopped = 0;
    navigator.mediaDevices.getUserMedia = async () => {
      const ctx = new AudioContext();
      const osc = ctx.createOscillator();
      const out = ctx.createMediaStreamDestination();
      osc.connect(out);
      osc.start();
      for (const track of out.stream.getTracks()) {
        const stop = track.stop.bind(track);
        track.stop = () => {
          window.__micStopped += 1;
          stop();
        };
      }
      return out.stream;
    };
  });
  const sends = [];
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (
      request.method() === "POST" &&
      (path.endsWith("/messages") || path.startsWith("/api/artifacts"))
    )
      sends.push(path);
  });
  await page.goto(`/app/${conversation.agent.id}`);
  await page.getByRole("button", { name: "Attachments and tools", exact: true }).click();
  await page.locator("#dialog").getByRole("button", { name: "Voice message" }).click();
  await expect(page.locator(".vrec-bar")).toBeVisible();
  await page.waitForTimeout(600);
  // Leave the conversation (the composer unmounts, as a thread switch does).
  await page
    .locator(".desktop-rail")
    .getByRole("button", { name: "Settings", exact: true })
    .click();
  await expect(page.locator(".vrec-bar")).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => window.__micStopped)).toBeGreaterThan(0);
  await page.waitForTimeout(1500);
  expect(sends).toEqual([]);
});

test("M10: older history keeps paging page after page, and a failed read does not end it", async ({
  page,
  conversation,
}) => {
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const all = Array.from({ length: 180 }, (_, index) =>
    message(conversation, index + 1, index % 2 ? "assistant" : "user", `Page row ${index + 1}`),
  );
  let failed = false;
  const befores = [];
  await page.route(`**/api/threads/${conversation.thread.id}/messages*`, (route) => {
    if (route.request().method() !== "GET") return route.continue();
    const before = new URL(route.request().url()).searchParams.get("before");
    if (!before) return route.fulfill({ json: all.slice(-60) });
    befores.push(Number(before));
    // The first older read fails once: paging must stay on.
    if (!failed) {
      failed = true;
      return route.fulfill({ status: 503, json: { code: "service_unavailable" } });
    }
    const rows = all.filter((row) => row.seq < Number(before)).slice(-60);
    return route.fulfill({ json: rows });
  });
  await page.goto(`/app/${conversation.agent.id}`);
  const transcript = page.getByTestId("transcript");
  await expect(page.locator("[data-message-id='ux-message-180']")).toBeVisible();
  // Scrolling to the top keeps loading: the failed read, then two pages, down to the first.
  await expect
    .poll(
      async () => {
        await transcript.evaluate((element) => {
          element.scrollTop = 0;
        });
        return page.locator("[data-message-id='ux-message-1']").count();
      },
      { timeout: 20000, intervals: [400] },
    )
    .toBe(1);
  expect(befores.length).toBeGreaterThanOrEqual(3);
  await expect(page.locator("[data-message-id='ux-message-1']")).toHaveCount(1);
});

test("S2: long-press opens the message menu by touch, never by a held mouse button", async ({
  page,
  conversation,
}) => {
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  await page.route(`**/api/threads/${conversation.thread.id}/messages*`, (route) =>
    route.request().method() === "GET"
      ? route.fulfill({ json: [message(conversation, 1, "assistant", "Hold me")] })
      : route.continue(),
  );
  await page.goto(`/app/${conversation.agent.id}`);
  const bubble = page.locator("[data-message-id='ux-message-1'] .bubble");
  await expect(bubble).toBeVisible();
  const hold = async (pointerType) => {
    const box = await bubble.boundingBox();
    const at = { clientX: box.x + 20, clientY: box.y + box.height / 2, pointerId: 7, pointerType };
    await bubble.dispatchEvent("pointerdown", { ...at, button: 0, buttons: 1, isPrimary: true });
    await page.waitForTimeout(700);
    await bubble.dispatchEvent("pointerup", { ...at, button: 0, buttons: 0, isPrimary: true });
  };
  await hold("mouse");
  await expect(page.getByRole("menu")).toHaveCount(0);
  await hold("touch");
  await expect(page.getByRole("menu")).toBeVisible();
});

test("S7: the permission chip never guesses a level, and the mandate draft belongs to this chat", async ({
  page,
  conversation,
}) => {
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const permissions = `**/api/agents/${conversation.agent.id}/permissions`;
  await page.route(permissions, (route) =>
    route.fulfill({ status: 503, json: { code: "service_unavailable" } }),
  );
  await page.goto(`/app/${conversation.agent.id}`);
  const chip = page.getByTestId("permission-chip");
  await expect(chip).toHaveAttribute("data-level", "unknown");
  await expect(chip).toContainText("Permission unknown");
  await expect(chip).not.toContainText("No execution");
  await page.unroute(permissions);
  const drafts = [];
  await page.route(
    `**/api/agents/${conversation.agent.id}/account-authorities/draft`,
    async (route) => {
      drafts.push(route.request().postDataJSON());
      await route.fulfill({ status: 409, json: { code: "service_unavailable" } });
    },
  );
  await page.reload();
  await expect(chip).toHaveAttribute("data-level", /^(analysis|supervised)$/);
  await chip.click();
  await page.getByRole("menu").getByText("Delegated execution", { exact: true }).click();
  await page.getByRole("button", { name: "Review and sign with the passkey" }).click();
  await expect.poll(() => drafts.length).toBe(1);
  expect(drafts[0].thread_id).toBe(conversation.thread.id);
});

test("S8: Lonora's chat has the trading and safety section like any trading agent's", async ({
  page,
  context,
  conversation,
}) => {
  void conversation;
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const lonora = (await (await context.request.get("/api/agents")).json()).find(
    (row) => row.role === "personal",
  );
  expect(lonora).toBeTruthy();
  await page.goto(`/app/${lonora.id}`);
  // The menu is built when it opens: wait until the agent is loaded.
  await expect(page.getByTestId("permission-chip")).toBeVisible();
  await page.getByRole("button", { name: "Chat menu", exact: true }).click();
  await expect(page.getByRole("button", { name: "Watches", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Status and safety", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Trading and safety" })).toBeVisible();
  await expect(page.getByTestId("agent-mode-line")).toBeVisible();
});
