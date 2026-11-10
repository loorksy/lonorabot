import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

/* UI phase 5 (docs/ui-reference/CAPABILITY_MAP.md, owner decisions Q46-Q57): the settings root with
   the version line, notifications with quiet hours to the minute and per-agent rules, the app
   lock, integrations with the real dry-run tests, usage without a cap, and the auth screens. */
function fixture(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}
async function signIn(context, data, locale = "en") {
  await context.addCookies(
    data.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript((value) => {
    localStorage.setItem("lonora.locale", value);
    localStorage.setItem("lonora.auth.intro-seen", "1");
  }, locale);
}
const csrf = (data) => ({
  "X-CSRF-Token": data.cookies.find((cookie) => cookie.name === "lonora_csrf").value,
});

test("settings root, quiet hours to the minute and one agent's delivery rules", async ({
  page,
  context,
}) => {
  const data = fixture({ action: "init", empty: true });
  const headers = csrf(data);
  const before = await (await context.request.get("/api/voice/incoming/policy")).json();
  try {
    await signIn(context, data);
    await page.setViewportSize({ width: 1280, height: 860 });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto("/app/settings");
    await expect(page.getByText(/^Lonora · version \d/)).toBeVisible();
    await expect(page.getByText("About Lonora")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^Sign out/ })).toBeVisible();
    await page.getByRole("button", { name: /^Notifications and contact/ }).click();
    await expect(page.getByRole("radio", { name: /Activity log only/ })).toBeVisible();
    // No browser notification permission until a push channel exists (Q10).
    await expect(page.getByText(/Browser notifications/)).toHaveCount(0);
    const mute = page.getByRole("switch", { name: "Mute notifications at night" });
    if ((await mute.getAttribute("aria-checked")) !== "true") await mute.click();
    await expect(page.getByText("Urgent always arrives")).toBeVisible();
    await page.getByLabel("From").fill("22:30");
    await expect
      .poll(
        async () =>
          (await (await context.request.get("/api/voice/incoming/policy")).json())
            .quiet_start_minute,
      )
      .toBe(22 * 60 + 30);
    const agent = (await (await context.request.get("/api/agents")).json())[0];
    if (agent) {
      await page.goto(`/app/communication/${agent.id}`);
      await page.getByRole("switch", { name: "Agent calls" }).click();
      await page.getByLabel("Daily notification limit").fill("5");
      await page.getByRole("button", { name: "Save", exact: true }).click();
      await expect
        .poll(async () =>
          (await context.request.get(`/api/agents/${agent.id}/notifications`)).json(),
        )
        .toMatchObject({ calls: false, daily_limit: 5 });
      await context.request.put(`/api/agents/${agent.id}/notifications`, {
        headers,
        data: { calls: true, daily_limit: null },
      });
    }
    expect(errors).toEqual([]);
  } finally {
    const { enabled: _enabled, ...policy } = before;
    await context.request.put("/api/owner/preferences", { headers, data: { reach_me: policy } });
    fixture({ ...data, action: "cleanup" });
  }
});

test("app lock: a 4-digit code, wrong tries counted, unlocked again", async ({ page, context }) => {
  const data = fixture({ action: "init", empty: true });
  try {
    await signIn(context, data);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/app/privacy");
    // Headless Chromium has no platform authenticator: the biometric row stays hidden (Q51).
    await page.getByRole("switch", { name: "Lock the app with a code" }).click();
    const lock = page.locator("#lock");
    await expect(lock).toBeVisible();
    await page.keyboard.type("1234");
    await expect(lock.getByText("Enter the code again")).toBeVisible();
    await page.keyboard.type("1234");
    await expect(lock).toHaveCount(0);
    await expect(page.getByRole("switch", { name: "Unlock with fingerprint or face" })).toHaveCount(
      0,
    );
    const stored = await page.evaluate(() => localStorage.getItem("lonora.lock"));
    expect(stored).not.toContain("1234");
    await page.reload();
    await expect(lock).toBeVisible();
    await page.keyboard.type("1111");
    await expect(lock.getByText("Wrong code. 4 tries left")).toBeVisible();
    await page.keyboard.type("1234");
    await expect(lock).toHaveCount(0);
    await page.getByRole("switch", { name: "Lock the app with a code" }).click();
    await page.reload();
    await expect(lock).toHaveCount(0);
  } finally {
    fixture({ ...data, action: "cleanup" });
  }
});

test("integrations: the demo account tests for real, MCP is remote only, usage has no cap", async ({
  page,
  context,
}) => {
  const data = fixture({ action: "init", empty: true });
  try {
    await signIn(context, data);
    await page.setViewportSize({ width: 1280, height: 860 });
    await page.goto("/app/integrations");
    await expect(page.getByText("Trading accounts")).toBeVisible();
    await page.goto("/app/broker");
    // MetaApi is the default broker (Q52): preselected with its token and region fields.
    await expect(page.getByLabel("Broker")).toHaveValue("metaapi");
    await expect(page.getByLabel("Region")).toBeVisible();
    await page.getByLabel("Broker").selectOption("simulation");
    await expect(page.getByText("Demo", { exact: true })).toBeVisible();
    await expect(page.getByLabel(/Password/)).toHaveCount(0);
    await page.getByLabel("Account number").fill(`demo-${randomUUID().slice(0, 8)}`);
    await page.getByRole("button", { name: "Test the connection" }).click();
    await expect(
      page.getByRole("status").filter({ hasText: "The connection works" }),
    ).toBeVisible();
    await page.goto("/app/mcp");
    await expect(page.getByText("Streamable HTTP")).toBeVisible();
    await expect(page.locator("option", { hasText: /stdio/ })).toHaveCount(0);
    await expect(page.getByText(/allowed agents/i)).toHaveCount(0);
    await page.goto("/app/usage");
    await expect(page.getByText("No spending cap: usage never stops a request.")).toBeVisible();
    await expect(page.getByText(/Edit (the )?limit/)).toHaveCount(0);
    const csv = page.getByRole("link", { name: "Export CSV" });
    await expect(csv).toHaveAttribute("href", /period=month/);
    await page.getByRole("tab", { name: "7 days" }).click();
    await expect(csv).toHaveAttribute("href", /period=week/);
    const exported = await context.request.get("/api/usage/export.csv?period=week");
    expect((await exported.text()).replace(/^﻿/, "").split(/\r?\n/)[0]).toBe(
      "date,cost_usd,tokens,requests",
    );
  } finally {
    fixture({ ...data, action: "cleanup" });
  }
});

test("auth: intro once, e-mail sign-in, and «Your session ended»", async ({ page, context }) => {
  const data = fixture({ action: "init", empty: true });
  try {
    await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/app");
    await expect(page.getByRole("heading", { name: "Welcome to Lonora" })).toBeVisible();
    await page.getByRole("button", { name: "Next" }).click();
    await page.getByRole("button", { name: "Next" }).click();
    await page.getByRole("button", { name: "Start now" }).click();
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    // Only e-mail + password (Q46): no phone, sign-up or forgot-password.
    await expect(page.getByText(/phone|Forgot|Create an account/i)).toHaveCount(0);
    await page.getByLabel("Email").fill(process.env.LONORA_UI_TEST_EMAIL ?? "ci@example.com");
    await page
      .getByLabel("Password")
      .fill(process.env.LONORA_UI_TEST_PASSWORD ?? "ci-only-owner-password");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page.locator("#auth")).toHaveCount(0);
    await page.evaluate(() => window.dispatchEvent(new Event("lonora:session-expired")));
    await expect(page.getByRole("heading", { name: "Your session ended" })).toBeVisible();
    await page.reload();
    // The intro shows once per device.
    await expect(page.getByRole("heading", { name: "Welcome to Lonora" })).toHaveCount(0);
  } finally {
    fixture({ ...data, action: "cleanup" });
  }
});
