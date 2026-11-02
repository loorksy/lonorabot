// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: isolated UI-test credentials.
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { brokerFixture } from "../web/broker-fixture.mjs";

test("Expo chat renders the native candle avatar for saved shape profiles", async ({
  page,
  context,
}) => {
  test.setTimeout(90_000);
  const credentials = {
    email: process.env.LONORA_UI_TEST_EMAIL ?? "ci@example.com",
    password: process.env.LONORA_UI_TEST_PASSWORD ?? "ci-only-owner-password",
  };
  const onboarding = await (await context.request.get("/api/onboarding")).json();
  if (!onboarding.owner_initialized)
    expect(
      (
        await context.request.post("/api/onboarding", {
          data: {
            ...credentials,
            bootstrap_token:
              process.env.LONORA_BOOTSTRAP_TOKEN ?? "lonora-ui-bootstrap-ci-only-2026",
          },
        })
      ).status(),
    ).toBe(201);
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await page
    .getByRole("textbox", { name: "البريد الإلكتروني", exact: true })
    .fill(credentials.email);
  await page.getByLabel("كلمة المرور", { exact: true }).fill(credentials.password);
  const loggingIn = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/auth/login") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "تسجيل الدخول", exact: true }).click();
  const headers = { "X-CSRF-Token": (await (await loggingIn).json()).csrf };
  const broker = await brokerFixture(context, headers);
  let agent;
  try {
    const created = await context.request.post("/api/agents", {
      headers,
      data: {
        name: `Native candle ${randomUUID()}`,
        avatar: "organic",
        color: "#818cf8",
        ...broker.binding,
      },
    });
    expect(created.status()).toBe(201);
    agent = await created.json();
    const conversation = await context.request.post(`/api/agents/${agent.id}/conversation`, {
      headers,
      data: {},
    });
    expect(conversation.ok()).toBeTruthy();
    const thread = await conversation.json();
    await page.goto(`/thread?id=${thread.id}`);
    const avatar = page.getByTestId("trading-avatar").first();
    await expect(avatar).toBeVisible();
    await expect(avatar.locator("svg").first()).toHaveAttribute("viewBox", "22 22 356 356");
    await expect(avatar.locator("path")).toHaveCount(8);
    await page.screenshot({ path: ".runtime/liquid-lonora-mobile.png", fullPage: true });
    expect(errors).toEqual([]);
  } finally {
    if (agent) await context.request.delete(`/api/agents/${agent.id}`, { headers });
    await broker.close();
  }
});
