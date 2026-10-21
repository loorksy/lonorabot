import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

function fixture(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}
async function setup(context) {
  const data = fixture({ action: "init" });
  await context.addCookies(
    data.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  const headers = { "X-CSRF-Token": data.cookies.find((row) => row.name === "lonora_csrf").value };
  const agentResponse = await context.request.post("/api/agents", {
    headers,
    data: {
      name: `Compact Super Bot ${randomUUID()}`,
      trading_account_id: data.account,
      trading_symbol: data.symbol,
    },
  });
  expect(agentResponse.status()).toBe(201);
  const agent = await agentResponse.json();
  const thread = await (
    await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
  ).json();
  const goalResponse = await context.request.post("/api/trading/goals", {
    headers,
    data: {
      agent_id: agent.id,
      thread_id: thread.id,
      account_id: data.account,
      symbol: data.symbol,
      // Preserve the production legacy payload: internal plan scaffolding must
      // remain reviewable in details, never become squeezed transcript columns.
      title: `Super Bot activation request for ${data.symbol}`,
      objective: `Prepare a supervised Super Bot activation card for the bound ${data.symbol} market. Do not execute trades; only create the reviewable proposal and preserve the bound account/symbol context.`,
      maximum_volume: "0.10",
      max_trade_actions: 1,
      steps: [{ id: "review", title: "Inspect current market evidence", kind: "analysis" }],
    },
  });
  expect(goalResponse.status()).toBe(201);
  const goal = await goalResponse.json();
  const proposed = await context.request.post(`/api/agents/${agent.id}/super-bot/proposals`, {
    headers,
    data: { goal_id: goal.id, mode: "supervised" },
  });
  expect(proposed.status()).toBe(201);
  const request = await proposed.json();
  return {
    data,
    agent,
    request,
    headers,
    async cleanup() {
      await context.request.delete(`/api/agents/${agent.id}`, { headers });
      fixture({ ...data, action: "cleanup" });
    },
  };
}

for (const locale of ["en", "ar"]) {
  test(`compact ${locale} Super Bot request remains readable and rejection resolves the actual card`, async ({
    page,
    context,
  }) => {
    const state = await setup(context);
    await context.addInitScript((value) => localStorage.setItem("lonora.locale", value), locale);
    if (locale === "ar") await page.setViewportSize({ width: 390, height: 844 });
    try {
      const document = await page.goto(`/app/${state.agent.id}?thread=${state.request.thread_id}`);
      expect(document.headers()["cache-control"]).toBe("no-store");
      const card = page.locator(`[data-super-bot-id="${state.request.id}"]`);
      await expect(card).toBeVisible();
      // Match the accessible action from the catalog, without assuming translated technical details.
      await expect(card.locator(":scope > .super-bot-card-actions > button")).toHaveCount(2);
      await expect(card.locator(":scope > .super-bot-card-actions > button").first()).toBeVisible();
      await expect(card.locator(":scope > .super-bot-card-actions > button").last()).toBeVisible();
      expect((await card.boundingBox()).width).toBeGreaterThan(250);
      expect((await card.boundingBox()).height).toBeLessThan(300);
      expect(await card.evaluate((element) => getComputedStyle(element).flexDirection)).toBe(
        "column",
      );
      await expect(card.getByText(state.request.envelope.objective, { exact: true })).toBeHidden();
      await card.locator(".super-bot-card-heading").click();
      const details = card.getByRole("dialog");
      await expect(details).toBeVisible();
      await expect(
        details.getByText(state.request.envelope.objective, { exact: true }),
      ).toBeVisible();
      await expect(
        details.getByText("Inspect current market evidence", { exact: true }),
      ).toBeVisible();
      await expect(details.locator("dd").first()).toHaveText(state.request.envelope.symbol);
      await page.keyboard.press("Escape");
      await expect(details).not.toBeVisible();
      await card.locator(":scope > .super-bot-card-actions > button").last().click();
      await expect(card).toHaveAttribute("data-status", "rejected");
      await expect(card.locator(":scope > .super-bot-card-actions > button")).toHaveCount(0);
      const persisted = await (
        await context.request.get(`/api/agents/${state.agent.id}/super-bot`)
      ).json();
      expect(persisted.find((row) => row.id === state.request.id).status).toBe("rejected");
      await page.reload();
      await expect(card).toHaveAttribute("data-status", "rejected");
      const dimensions = await page.evaluate(() => ({
        width: document.documentElement.clientWidth,
        scroll: document.documentElement.scrollWidth,
      }));
      expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width + 1);
    } finally {
      await state.cleanup();
    }
  });
}

test("allow preserves device verification and only shows active after the server confirms", async ({
  page,
  context,
}) => {
  const state = await setup(context);
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const cdp = await context.newCDPSession(page);
  await cdp.send("WebAuthn.enable");
  await cdp.send("WebAuthn.addVirtualAuthenticator", {
    options: {
      protocol: "ctap2",
      transport: "internal",
      hasResidentKey: true,
      hasUserVerification: true,
      isUserVerified: true,
      automaticPresenceSimulation: true,
    },
  });
  try {
    await page.goto(`/app/${state.agent.id}?thread=${state.request.thread_id}`);
    const card = page.locator(`[data-super-bot-id="${state.request.id}"]`);
    await expect(page.locator('[data-super-bot="true"]')).toHaveCount(0);
    await card.getByRole("button", { name: "Review plan", exact: true }).click();
    const details = card.getByRole("dialog");
    await details.getByRole("button", { name: "Register a passkey", exact: true }).click();
    await expect(details.getByLabel("Confirm account password", { exact: true })).toBeVisible();
    await expect(card).toHaveAttribute("data-status", "pending");
    await details
      .getByLabel("Confirm account password", { exact: true })
      .fill("ci-only-owner-password");
    await details.getByRole("button", { name: "Register this device", exact: true }).click();
    await expect(details.getByLabel("Confirm account password", { exact: true })).toHaveCount(0);
    const verify = page.waitForResponse(
      (response) =>
        response.url().endsWith("/super-bot/verify") && response.request().method() === "POST",
    );
    await details
      .getByRole("button", { name: "Activate with device authentication", exact: true })
      .click();
    expect((await verify).ok()).toBeTruthy();
    await expect(card).toHaveAttribute("data-status", "activated");
    await expect(details).not.toBeVisible();
    const persisted = await (
      await context.request.get(`/api/agents/${state.agent.id}/super-bot`)
    ).json();
    expect(persisted.find((row) => row.id === state.request.id).status).toBe("activated");
    expect((await (await context.request.get("/api/trading/controls")).json()).enabled).toBe(false);
    await expect(page.locator('[data-super-bot="true"]').first()).toBeVisible();
    const stopped = await context.request.post("/api/super-bot/control", {
      headers: state.headers,
      data: { request_id: state.request.id, action: "pause" },
    });
    expect(stopped.ok()).toBeTruthy();
    await expect(page.locator('[data-super-bot="true"]')).toHaveCount(0);
  } finally {
    await state.cleanup();
  }
});
