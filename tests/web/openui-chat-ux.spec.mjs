// OpenUI-derived chat interaction acceptance over Lonora's actual API and outbox.
// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: Playwright environment is not cached by Turbo.
import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
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
  // Hold the mic, then slide up to lock the recording.
  const mic = await page.locator(".composer .mic").boundingBox();
  await page.mouse.move(mic.x + mic.width / 2, mic.y + mic.height / 2);
  await page.mouse.down();
  await page.waitForTimeout(600);
  await page.mouse.move(mic.x + mic.width / 2, mic.y + mic.height / 2 - 100, { steps: 10 });
  await page.mouse.up();
  await expect(page.locator(".vrec-bar.locked")).toBeVisible();
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

test("the + sheet: rows with their counts, each opening this agent's own page", async ({
  page,
  context,
  conversation,
}) => {
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const id = conversation.agent.id;
  await page.goto(`/app/${id}`);
  const sheet = page.locator("#dialog");
  const open = async (name) => {
    await page.getByRole("button", { name: "Attachments and tools", exact: true }).click();
    await sheet.getByRole("button", { name }).click();
  };
  await page.getByRole("button", { name: "Attachments and tools", exact: true }).click();
  // The mic's long press records a voice message: the sheet has no second way in.
  await expect(sheet.getByRole("button", { name: "Voice message" })).toHaveCount(0);
  await expect(sheet.getByRole("button", { name: /^Integrations/ })).toContainText(/linked/);
  await expect(sheet.getByRole("button", { name: /^Skills/ })).toContainText(/skill/);
  await expect(sheet.getByRole("button", { name: /^Knowledge/ })).toContainText("Empty");
  await page.keyboard.press("Escape");
  await open(/^Skills/);
  await expect(page).toHaveURL(new RegExp(`/app/skills\\?agent=${id}$`));
  await page.goto(`/app/${id}`);
  await open(/^Schedule/);
  await expect(page).toHaveURL(new RegExp(`/app/new-schedule\\?agent=${id}$`));
  await page.goto(`/app/${id}`);
  await open(/^New task/);
  await expect(page).toHaveURL(new RegExp(`/app/new-task\\?agent=${id}$`));
  // A group has no one agent: no skills or knowledge rows, and Schedule picks the agent there.
  const created = await context.request.post("/api/groups/create", {
    headers: conversation.headers,
    data: { name: `Group ${randomUUID()}`, member_ids: [id], participation: "mentions_or_lead" },
  });
  expect(created.ok()).toBeTruthy();
  const group = await created.json();
  try {
    await page.goto(`/app/g/${group.id}`);
    await page.getByRole("button", { name: "Attachments and tools", exact: true }).click();
    await expect(sheet.getByRole("button", { name: /^Skills/ })).toHaveCount(0);
    await expect(sheet.getByRole("button", { name: /^Knowledge/ })).toHaveCount(0);
    await sheet.getByRole("button", { name: /^Schedule/ }).click();
    await expect(page).toHaveURL(/\/app\/new-schedule$/);
  } finally {
    await context.request.delete(`/api/groups/${group.id}`, { headers: conversation.headers });
  }
});

test("the @ list: the role in words, full-width rows, and a picked name drawn as a chip", async ({
  page,
  context,
  conversation,
}) => {
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const agents = await (await context.request.get("/api/agents")).json();
  const lonora = agents.find((row) => row.role === "personal");
  await page.goto(`/app/${conversation.agent.id}`);
  await page.getByRole("combobox").fill(`Hi @${lonora.name.slice(0, 3)}`);
  const row = page.getByRole("option", { name: new RegExp(lonora.name) });
  await expect(row.locator("strong")).toHaveText(`@${lonora.name}`);
  await expect(row.locator("small")).toHaveText(
    lonora.title || lonora.description || "Your personal assistant",
  );
  const list = await page.locator(".as-list").boundingBox();
  expect((await row.boundingBox()).width).toBeGreaterThan(list.width - 24);
  await page.keyboard.press("Enter");
  await expect(page.locator(".ta-mirror mark")).toHaveText(`@${lonora.name}`);
});

test("the mic hint shows once above the mic, goes on the first press and never comes back", async ({
  page,
  conversation,
}) => {
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  await page.goto(`/app/${conversation.agent.id}`);
  const tip = page.locator(".mic-tip");
  await expect(tip).toHaveClass(/show/);
  await expect(tip).toContainText("Tap to dictate");
  await expect(tip).toContainText("Hold to record a voice message");
  const [box, mic] = [await tip.boundingBox(), await page.locator(".composer .mic").boundingBox()];
  expect(box.y + box.height).toBeLessThan(mic.y);
  await page.getByRole("combobox").click();
  await expect(tip).toHaveCount(0);
  await page.reload();
  await page.waitForTimeout(1500);
  await expect(tip).toHaveCount(0);
});

test("the mic hint waits while the @ list is open and is not used up there", async ({
  page,
  context,
  conversation,
}) => {
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const agents = await (await context.request.get("/api/agents")).json();
  const other = agents.find((row) => row.id !== conversation.agent.id);
  await page.goto(`/app/${conversation.agent.id}`);
  await page.getByRole("combobox").fill(`@${other.name.slice(0, 2)}`);
  await expect(page.getByRole("listbox")).toBeVisible();
  await page.waitForTimeout(1500);
  await expect(page.locator(".mic-tip")).toHaveCount(0);
  expect(await page.evaluate(() => localStorage.getItem("lonora.tips.mic"))).toBeNull();
  await page.reload();
  await expect(page.locator(".mic-tip")).toHaveClass(/show/);
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
  // Scrolling to the top keeps loading: the failed read, then (after scrolling away and back,
  // as an owner would) two pages, down to the first.
  await expect
    .poll(
      async () => {
        await transcript.evaluate((element) => {
          element.scrollTop = element.scrollHeight;
        });
        await page.waitForTimeout(100);
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
  // Item 18: the tools sheet's Permission row says the same, never «No execution».
  await page.getByRole("button", { name: "Attachments and tools", exact: true }).click();
  const row = page.locator("#dialog").getByRole("button", { name: /^Permission/ });
  await expect(row).toContainText("Permission unknown");
  await expect(row).not.toContainText("No execution");
  await page.keyboard.press("Escape");
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

test("S10: the mandate sheet follows D1: until stopped, the agent's own pair, the daily loss sent only when set", async ({
  page,
  conversation,
}) => {
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const { agent } = conversation;
  expect(agent.trading_symbol).toBeTruthy();
  let accountLoss = null;
  await page.route(
    `**/api/trading/accounts/${agent.trading_account_id}/execution-policy`,
    async (route) => {
      const response = await route.fetch();
      const body = await response.json();
      await route.fulfill({
        json: { ...body, risk: { ...body.risk, max_daily_loss: accountLoss, currency: "USD" } },
      });
    },
  );
  const drafts = [];
  await page.route(`**/api/agents/${agent.id}/account-authorities/draft`, async (route) => {
    drafts.push(route.request().postDataJSON());
    await route.fulfill({ status: 409, json: { code: "service_unavailable" } });
  });
  const open = async () => {
    await page.goto(`/app/${agent.id}`);
    const chip = page.getByTestId("permission-chip");
    await expect(chip).toHaveAttribute("data-level", /^(analysis|supervised)$/);
    await chip.click();
    await page.getByRole("menu").getByText("Delegated execution", { exact: true }).click();
  };
  await open();
  const sheet = page.locator("#dialog");
  await expect(sheet.getByRole("radio", { name: "Until cancelled", exact: true })).toHaveAttribute(
    "aria-checked",
    "true",
  );
  // A fixed-pair agent: its own pair only, never «all pairs».
  await expect(sheet.getByRole("radio", { name: agent.trading_symbol, exact: true })).toBeVisible(); // Q17: its «Full» is full delegation on its own pair, and the subtitle says so.
  const full = sheet.getByRole("radio", { name: /Full mandate/ });
  await expect(full).toContainText(`${agent.trading_symbol} only`);
  await expect(full).not.toContainText("All pairs");

  await expect(sheet.getByText("All pairs on the account")).toHaveCount(0);
  await expect(sheet.locator("[data-daily-loss='suggested']")).toContainText("Suggested value 3%");
  await sheet.getByRole("button", { name: "Review and sign with the passkey" }).click();
  await expect.poll(() => drafts.length).toBe(1);
  expect(drafts[0].duration).toBe("until_stopped");
  expect(drafts[0].symbols).toEqual([agent.trading_symbol]);
  expect(drafts[0].all_pairs).toBeUndefined();
  // The suggestion is the server's (basis «suggested»), not the owner's request.
  expect(drafts[0].daily_loss_percent).toBeUndefined();
  await sheet.getByRole("group", { name: "Daily loss limit" }).getByLabel("Increase").click();
  await sheet.getByRole("button", { name: "Review and sign with the passkey" }).click();
  await expect.poll(() => drafts.length).toBe(2);
  expect(drafts[1].daily_loss_percent).toBe("3.5");
  // The account has its own daily loss limit: it is shown and stays, nothing is sent.
  accountLoss = "250";
  await open();
  await expect(sheet.locator("[data-daily-loss='account']")).toContainText("250 USD");
  await sheet.getByRole("button", { name: "Review and sign with the passkey" }).click();
  await expect.poll(() => drafts.length).toBe(3);
  expect(drafts[2].daily_loss_percent).toBeUndefined();
});

test("S15: on a phone the history picker sits under the header, not beneath it", async ({
  page,
  conversation,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const { thread, agent } = conversation;
  await page.route(`**/api/threads?agent_id=${agent.id}`, (route) =>
    route.fulfill({
      json: [thread, { ...thread, id: `${thread.id.slice(0, -4)}0000`, title: "Earlier chat" }],
    }),
  );
  await page.goto(`/app/${agent.id}?thread=${thread.id}`);
  const picker = page.locator(".tpl-history-picker");
  await expect(picker).toBeVisible();
  const header = await page.locator(".chat-head").boundingBox();
  const box = await picker.boundingBox();
  expect(box.y).toBeGreaterThanOrEqual(header.y + header.height - 1);
  // The control itself is reachable: nothing covers its centre.
  const select = await picker.locator("select").boundingBox();
  const hit = await page.evaluate(
    ({ x, y }) => document.elementFromPoint(x, y)?.closest(".tpl-history-picker") != null,
    { x: select.x + select.width / 2, y: select.y + select.height / 2 },
  );
  expect(hit).toBe(true);

  // Item 26: on a desktop the solid header already clears it: the phone's header margin
  // never applies there, so the gap is not doubled.
  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(picker).toBeVisible();
  const desk = await page.locator(".chat-head").boundingBox();
  const deskBox = await picker.boundingBox();
  expect(deskBox.y).toBeGreaterThanOrEqual(desk.y + desk.height - 1);
  expect(await picker.evaluate((element) => getComputedStyle(element).marginTop)).toBe("0px");
});

test("R1/R2: the order sheet draws the executor's own rows: blocked before sending, the broker's reason", async ({
  page,
  conversation,
}) => {
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const rows = JSON.parse(readFileSync("tests/fixtures/order-rows.json", "utf8"));
  const anchored = Object.values(rows).map((row) => ({
    ...row,
    thread_id: conversation.thread.id,
    agent_id: conversation.agent.id,
  }));
  await page.route(`**/api/trading/journal?thread_id=${conversation.thread.id}`, (route) =>
    route.fulfill({ json: anchored }),
  );
  await page.goto(`/app/${conversation.agent.id}`);
  const sheet = page.locator("#dialog");
  await page.locator("[data-operation-id='op-not-sent']").click();
  await expect(sheet.locator(".od-line")).toHaveAttribute("data-steps", "requested blocked");
  await expect(sheet.locator(".od-line li")).toHaveText([/Requested/, /Blocked before sending/]);
  await expect(sheet.locator(".od-line")).not.toContainText("Sent");
  await expect(sheet.locator(".od-line")).not.toContainText("Accepted by the broker");
  await expect(sheet.locator("[data-order-reason='blocked']")).toContainText(
    "Not sent to the broker",
  );
  await page.keyboard.press("Escape");
  await page.locator("[data-operation-id='op-rejected']").click();
  const reason = sheet.locator("[data-order-reason='rejected']");
  await expect(reason).toContainText("The broker rejected the order");
  await expect(reason).toContainText("Not enough money to complete the request");
  await expect(sheet).not.toContainText(/try again/i);
});

test("R5: «Resolve» in Lonora's sheet opens the conversation that holds the card", async ({
  page,
  context,
  conversation,
}) => {
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const lonora = (await (await context.request.get("/api/agents")).json()).find(
    (row) => row.role === "personal",
  );
  const card = "ux-message-1";
  await page.route(`**/api/threads/${conversation.thread.id}/messages*`, (route) =>
    route.request().method() === "GET"
      ? route.fulfill({ json: [message(conversation, 1, "assistant", "The resolve card")] })
      : route.continue(),
  );
  await page.route(`**/api/agents/${lonora.id}/state`, async (route) => {
    const live = await (await route.fetch()).json();
    const readiness = live.trading_readiness ?? {};
    await route.fulfill({
      json: {
        ...live,
        trading_readiness: {
          ...readiness,
          unresolved_count: 1,
          unresolved_operations: [
            {
              operation_id: "op-elsewhere",
              account_id: "acct",
              symbol: "XAUUSD",
              action: "buy",
              status: "ambiguous",
              submitted_at: null,
              this_agent: false,
              blocks: "new_risk_on_this_symbol_or_ticket",
              // The card lives in another agent's chat.
              resolve_card: {
                id: card,
                thread_id: conversation.thread.id,
                agent_id: conversation.agent.id,
                group_id: null,
                timeline_seq: 1,
              },
            },
          ],
        },
      },
    });
  });
  await page.goto(`/app/${lonora.id}`);
  await expect(page.getByTestId("permission-chip")).toBeVisible();
  await page.getByRole("button", { name: "Chat menu", exact: true }).click();
  await page.getByRole("button", { name: "Status and safety", exact: true }).click();
  await page.locator(`#dialog [data-resolve-card="${card}"]`).click();
  await expect(page).toHaveURL(new RegExp(`/app/${conversation.agent.id}\\?.*card=${card}`));
  await expect(page).toHaveURL(new RegExp(`thread=${conversation.thread.id}`));
  await expect(page.locator(`[data-message-id="${card}"]`)).toBeVisible();
});

test("paging: a failing older read is not retried in a loop while the sentinel stays in view", async ({
  page,
  conversation,
}) => {
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const all = Array.from({ length: 80 }, (_, index) =>
    message(conversation, index + 1, index % 2 ? "assistant" : "user", `Row ${index + 1}`),
  );
  let reads = 0;
  await page.route(`**/api/threads/${conversation.thread.id}/messages*`, (route) => {
    if (route.request().method() !== "GET") return route.continue();
    if (!new URL(route.request().url()).searchParams.get("before"))
      return route.fulfill({ json: all.slice(-60) });
    reads += 1;
    return route.fulfill({ status: 503, json: { code: "service_unavailable" } });
  });
  await page.goto(`/app/${conversation.agent.id}`);
  const transcript = page.getByTestId("transcript");
  await expect(page.locator("[data-message-id='ux-message-80']")).toBeVisible();
  await transcript.evaluate((element) => {
    element.scrollTop = 0;
  });
  await expect.poll(() => reads).toBeGreaterThanOrEqual(1);
  // The sentinel stays in view: no tight loop of failing reads.
  await page.waitForTimeout(2500);
  expect(reads).toBeLessThanOrEqual(2);
  // Leaving and coming back tries again.
  const before = reads;
  await transcript.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });
  await page.waitForTimeout(300);
  await transcript.evaluate((element) => {
    element.scrollTop = 0;
  });
  await expect.poll(() => reads).toBeGreaterThan(before);
});

test("M2(d): a retried reply's error card settles at once and stays settled", async ({
  page,
  conversation,
}) => {
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const { thread, agent } = conversation;
  const run = (id, status, metadata = {}) => ({
    id,
    thread_id: thread.id,
    agent_id: agent.id,
    parent_run_id: null,
    status,
    trigger: "user",
    input_seq: 1,
    error_code: status === "failed" ? "model_provider_unavailable" : null,
    failure:
      status === "failed"
        ? { code: "model_provider_unavailable", family: "model", retry_after_seconds: null }
        : null,
    result: null,
    model_metadata: metadata,
    created_at: "2026-10-25T10:00:01Z",
    updated_at: "2026-10-25T10:00:02Z",
  });
  let runs = [run("run-failed", "failed")];
  await page.route(`**/api/threads/${thread.id}/messages*`, (route) =>
    route.request().method() === "GET"
      ? route.fulfill({ json: [message(conversation, 1, "user", "Analyse gold")] })
      : route.continue(),
  );
  await page.route(`**/api/runs?thread_id=${thread.id}*`, (route) => route.fulfill({ json: runs }));
  await page.route("**/api/runs/run-failed/retry", (route) => {
    const retry = run("run-retry", "queued", { retry_of: "run-failed" });
    runs = [...runs, retry];
    return route.fulfill({ status: 202, json: retry });
  });
  await page.goto(`/app/${agent.id}`);
  const card = page.locator("[data-failed-run-id='run-failed']");
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(card).toHaveCount(0);
  // After a reload the runs list itself (the retry's retry_of) keeps it settled.
  await page.reload();
  await expect(page.getByText("Analyse gold")).toBeVisible();
  await expect(card).toHaveCount(0);
});

test("M4: the safety sheet shows the money limits of every account, each as set", async ({
  page,
  context,
  conversation,
}) => {
  void conversation;
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const lonora = (await (await context.request.get("/api/agents")).json()).find(
    (row) => row.role === "personal",
  );
  const accounts = [
    {
      account_id: "acct-one",
      configured: true,
      currency: "USD",
      limits: { max_daily_loss: "250", max_open_risk: "400" },
      not_configured: [],
    },
    {
      account_id: "acct-two",
      configured: true,
      currency: "EUR",
      limits: { max_daily_loss: "90" },
      not_configured: [],
    },
    {
      account_id: "acct-three",
      configured: false,
      currency: null,
      limits: {},
      not_configured: ["max_daily_loss"],
    },
  ];
  await page.route(`**/api/agents/${lonora.id}/state`, async (route) => {
    const live = await (await route.fetch()).json();
    await route.fulfill({
      json: {
        ...live,
        trading_readiness: { ...(live.trading_readiness ?? {}), money_limits: accounts },
      },
    });
  });
  await page.goto(`/app/${lonora.id}`);
  await expect(page.getByTestId("permission-chip")).toBeVisible();
  await page.getByRole("button", { name: "Chat menu", exact: true }).click();
  await page.getByRole("button", { name: "Status and safety", exact: true }).click();
  const sheet = page.locator("#dialog");
  await expect(sheet.locator("[data-account-limits]")).toHaveCount(3);
  const one = sheet.locator("[data-account-limits='acct-one']");
  await expect(one.locator("[data-money-limit='max_daily_loss']")).toContainText("250 USD");
  await expect(one.locator("[data-money-limit='max_open_risk']")).toContainText("400 USD");
  const two = sheet.locator("[data-account-limits='acct-two']");
  await expect(two.locator("[data-money-limit='max_daily_loss']")).toContainText("90 EUR");
  await expect(two.locator("[data-money-limit='max_open_risk_equity_percent']")).toHaveAttribute(
    "data-unset",
    "",
  );
  await expect(
    sheet.locator("[data-account-limits='acct-three'] [data-money-limit='none']"),
  ).toHaveCount(1);
});
