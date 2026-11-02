// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: isolated UI-test credentials.
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { brokerFixture } from "../web/broker-fixture.mjs";

test("Expo chat renders interactive idle capsules for saved shape profiles", async ({
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
    const paths = avatar.locator("path");
    await expect(paths).toHaveCount(8);
    // Four rounded capsules remain visible: no second wick per trading candle.
    await expect
      .poll(() =>
        paths.evaluateAll(
          (nodes) =>
            nodes.filter(
              (node) =>
                Number(node.getAttribute("stroke-width")) > 1 &&
                Number(node.getAttribute("opacity")) > 0.01,
            ).length,
        ),
      )
      .toBe(4);
    await expect.poll(() => paths.nth(2).getAttribute("stroke")).toBe("rgb(31,212,179)");
    const initialPath = await paths.first().getAttribute("d");
    await expect.poll(() => paths.first().getAttribute("d")).not.toBe(initialPath);
    const turn = avatar.locator('g[id$="turn"]');
    const initialTurn = await turn.getAttribute("transform");
    await avatar.dispatchEvent("pointerdown", { pointerType: "touch", clientX: 8, clientY: 8 });
    await expect.poll(() => turn.getAttribute("transform")).not.toBe(initialTurn);
    // A full turn occludes the visor on the back, then returns it to the front.
    await expect
      .poll(async () => Number(await turn.getAttribute("opacity")), { intervals: [30, 50, 75] })
      .toBe(0);
    await expect.poll(async () => Number(await turn.getAttribute("opacity"))).toBeGreaterThan(0.9);
    await page.screenshot({ path: ".runtime/liquid-lonora-mobile.png", fullPage: true });
    expect(errors).toEqual([]);
  } finally {
    if (agent) await context.request.delete(`/api/agents/${agent.id}`, { headers });
    await broker.close();
  }
});
