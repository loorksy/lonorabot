import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

for (const locale of ["en", "ar"]) {
  test(`workspace home lists conversations without opening a bot (${locale})`, async ({
    page,
    context,
  }) => {
    const fixture = JSON.parse(
      execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
        input: JSON.stringify({ action: "init", empty: true }),
        encoding: "utf8",
      }),
    );
    await context.addCookies(
      fixture.cookies.map((cookie) => ({
        ...cookie,
        url: test.info().project.use.baseURL,
        httpOnly: cookie.name === "lonora_session",
        sameSite: "Strict",
      })),
    );
    const headers = {
      "X-CSRF-Token": fixture.cookies.find((row) => row.name === "lonora_csrf").value,
    };
    const created = await context.request.post("/api/agents", {
      headers,
      data: {
        name: `Inbox ${randomUUID()}`,
        trading_account_id: fixture.account,
        trading_symbol: fixture.symbol,
      },
    });
    expect(created.status()).toBe(201);
    const agent = await created.json();
    const thread = await (
      await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
    ).json();
    const response = await context.request.post("/api/groups/create", {
      headers,
      data: {
        name: `Group ${randomUUID()}`,
        member_ids: [agent.id],
        participation: "mentions_or_lead",
      },
    });
    expect(response.ok()).toBeTruthy();
    const group = await response.json();
    const owner = await (await context.request.get("/api/auth/session")).json();
    await context.addInitScript(
      ({ locale, owner, agent }) => {
        localStorage.setItem("lonora.locale", locale);
        localStorage.setItem(`lonora:last-context:${owner}`, `/app/${agent}`);
      },
      { locale, owner: owner.id, agent: agent.id },
    );
    if (locale === "ar") await page.setViewportSize({ width: 390, height: 844 });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    let openedThread = 0;
    page.on("request", (request) => {
      if (new URL(request.url()).pathname === `/api/threads/${thread.id}/messages`) openedThread++;
    });
    await page.route("**/api/threads/inbox", async (route) => {
      const rows = await (await route.fetch()).json();
      const entry = rows.find((row) => row.agent_id === agent.id);
      entry.last_message = {
        content: "Latest actual conversation preview",
        role: "assistant",
        id: "preview",
        seq: 1,
        created_at: "2026-10-19T13:00:00Z",
      };
      await route.fulfill({ json: rows });
    });
    try {
      for (const path of ["/app", "/app/"]) {
        await page.goto(path);
        const home = page.getByTestId("conversation-inbox");
        await expect(home).toBeVisible();
        await expect(page).toHaveURL(new RegExp(`${path}$`));
        await expect(home.locator(`[data-inbox-agent-id="${agent.id}"]`)).toContainText(
          "Latest actual conversation preview",
        );
        await expect(home.locator(`[data-inbox-group-id="${group.id}"]`)).toBeVisible();
        // Account's Personal Agent remains first even when specialists are newer.
        const agents = await (await context.request.get("/api/agents")).json();
        const personal = agents.find((row) => row.role === "personal");
        await expect(home.locator(".tpl-inbox-row").first()).toHaveAttribute(
          "data-inbox-agent-id",
          personal.id,
        );
      }
      expect(openedThread).toBe(0);
      await page
        .getByTestId("conversation-inbox")
        .locator(`[data-inbox-agent-id="${agent.id}"]`)
        .click();
      await expect(page).toHaveURL(new RegExp(`/app/${agent.id}\\?thread=${thread.id}$`));
      await expect(page.getByTestId("transcript")).toBeVisible();
      await page
        .getByRole("button", {
          name: locale === "ar" ? "العودة إلى المحادثات" : "Back to conversations",
          exact: true,
        })
        .click();
      await expect(page.getByTestId("conversation-inbox")).toBeVisible();
      await expect(
        page.getByTestId("conversation-inbox").locator(`[data-inbox-agent-id="${agent.id}"]`),
      ).toContainText("Latest actual conversation preview");
      expect(errors).toEqual([]);
    } finally {
      await context.request.delete(`/api/groups/${group.id}`, { headers });
      await context.request.delete(`/api/agents/${agent.id}`, { headers });
    }
  });
}

test("inbox projection failure preserves bots and retry recovers without reload", async ({
  page,
  context,
}) => {
  const fixture = JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify({ action: "init", empty: true }),
      encoding: "utf8",
    }),
  );
  await context.addCookies(
    fixture.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  let failing = true;
  let pageLoads = 0;
  page.on("domcontentloaded", () => pageLoads++);
  await page.route("**/api/threads/inbox", (route) =>
    failing ? route.fulfill({ status: 503, json: { code: "request_failed" } }) : route.continue(),
  );
  await page.goto("/app/");
  const home = page.getByTestId("conversation-inbox");
  await expect(home.locator(".tpl-inbox-row").first()).toBeVisible();
  await expect(home.getByRole("alert")).toBeVisible();
  failing = false;
  await home.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(home.getByRole("alert")).toHaveCount(0);
  expect(pageLoads).toBe(1);
  await expect(page).toHaveURL(/\/app\/$/);
});

test("returning to a cached conversation stays visible while fresh reads wait, then logout cancels pending reads", async ({
  page,
  context,
}) => {
  const fixture = JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify({ action: "init", empty: true }),
      encoding: "utf8",
    }),
  );
  await context.addCookies(
    fixture.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const headers = {
    "X-CSRF-Token": fixture.cookies.find((row) => row.name === "lonora_csrf").value,
  };
  const created = await context.request.post("/api/agents", {
    headers,
    data: {
      name: `Cache ${randomUUID()}`,
      trading_account_id: fixture.account,
      trading_symbol: fixture.symbol,
    },
  });
  expect(created.status()).toBe(201);
  const agent = await created.json();
  const thread = await (
    await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
  ).json();
  let releaseMessages;
  const messageGate = new Promise((resolve) => {
    releaseMessages = resolve;
  });
  let releaseThreads;
  const threadGate = new Promise((resolve) => {
    releaseThreads = resolve;
  });
  let hold = false;
  let heldMessages = 0;
  let heldThreads = 0;
  const messages = [1, 2].map((seq) => ({
    id: randomUUID(),
    seq,
    thread_id: thread.id,
    agent_id: agent.id,
    role: "assistant",
    content: seq === 1 ? "Persisted conversation remains visible" : "New reconciled server message",
    created_at: "2026-10-19T12:00:00Z",
    reply_to: null,
    attachment_ids: [],
  }));
  await page.route(`**/api/threads/${thread.id}/messages*`, async (route) => {
    if (hold) {
      heldMessages++;
      await messageGate;
    }
    await route.fulfill({ json: hold ? messages : messages.slice(0, 1) });
  });
  await page.route("**/api/threads?agent_id=*", async (route) => {
    if (new URL(route.request().url()).searchParams.get("agent_id") === agent.id && hold) {
      heldThreads++;
      await threadGate;
    }
    await route.continue();
  });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  let releaseBackground = () => {};
  try {
    await page.goto(`/app/${agent.id}?thread=${thread.id}`);
    await expect(page.getByTestId("transcript")).toContainText(messages[0].content);
    await page.getByRole("button", { name: "Back to conversations", exact: true }).click();
    await expect(page.getByTestId("conversation-inbox")).toBeVisible();
    hold = true;
    await page
      .getByTestId("conversation-inbox")
      .locator(`[data-inbox-agent-id="${agent.id}"]`)
      .click();
    await expect.poll(() => heldMessages).toBeGreaterThan(0);
    await expect.poll(() => heldThreads).toBeGreaterThan(0);
    // Neither the canonical Thread nor its messages have returned from the network.
    await expect(page.getByTestId("transcript")).toContainText(messages[0].content);
    await expect(page.getByText("Opening conversation…", { exact: true })).toHaveCount(0);
    await expect(page.getByTestId("transcript")).not.toContainText(messages[1].content);
    releaseThreads();
    releaseMessages();
    await expect(page.getByTestId("transcript")).toContainText(messages[1].content);
    // Opening and closing agent settings leaves the same authoritative timeline.
    await page.getByRole("button", { name: `Agent settings: ${agent.name}`, exact: true }).click();
    await page.getByRole("button", { name: "Close context panel", exact: true }).click();
    await expect(page.getByTestId("transcript")).toContainText(messages[1].content);
    let backgroundStarted = false;
    const backgroundGate = new Promise((resolve) => {
      releaseBackground = resolve;
    });
    await page.route("**/api/groups", async (route) => {
      backgroundStarted = true;
      await backgroundGate;
      await route.continue();
    });
    await page.evaluate(() => window.dispatchEvent(new Event("online")));
    await expect.poll(() => backgroundStarted).toBe(true);
    await page.locator(".tpl-account-trigger").click();
    await page.getByRole("menuitem", { name: "Sign out", exact: true }).click();
    await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
    await expect(page).toHaveURL(/\/app$/);
    releaseBackground();
    expect(errors).toEqual([]);
  } finally {
    releaseThreads();
    releaseMessages();
    releaseBackground();
    // Logout intentionally invalidated this session; deletion may be refused.
    // The isolated fixture database is dropped by the browser-test harness.
  }
});
