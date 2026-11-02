// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: isolated UI-test credentials.
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { brokerFixture } from "./broker-fixture.mjs";

test("installed bot avatars use the supplied cat for old shape profiles", async ({
  page,
  context,
}) => {
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
  const login = await context.request.post("/api/auth/login", { data: credentials });
  expect(login.status()).toBe(200);
  const headers = { "X-CSRF-Token": (await login.json()).csrf };
  const broker = await brokerFixture(context, headers);
  const ids = [];
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  try {
    await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
    for (const avatar of ["orb", "organic", "diamond"]) {
      const response = await context.request.post("/api/agents", {
        headers,
        data: {
          name: `Liquid ${avatar} ${randomUUID()}`,
          avatar,
          color: "#818cf8",
          ...broker.binding,
        },
      });
      expect(response.status()).toBe(201);
      const agent = await response.json();
      ids.push(agent.id);
      await page.goto(`/app/${agent.id}`);
      const glyph = page.locator(".tpl-chat-identity .lonora-cat-avatar");
      await expect(glyph).toBeVisible();
      await expect(glyph.locator("[data-cat-signal]")).toHaveCount(8);
      await expect(glyph).toHaveAttribute("data-state", "waiting");
      const svg = glyph.locator("svg");
      await expect(svg).toHaveAttribute("viewBox", "0 0 400 400");
      const box = await svg.boundingBox();
      expect(box.width).toBeGreaterThan(20);
      expect(Math.abs(box.width - box.height)).toBeLessThan(1);
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await expect(page.locator(".tpl-chat-identity .lonora-cat-avatar")).toBeVisible();
    await page.screenshot({ path: ".runtime/liquid-lonora-web.png", fullPage: true });
    const svgIds = await page
      .locator(".lonora-cat-avatar clipPath")
      .evaluateAll((nodes) => nodes.map((node) => node.id));
    expect(new Set(svgIds).size).toBe(svgIds.length);
    expect(errors).toEqual([]);
  } finally {
    for (const id of ids) await context.request.delete(`/api/agents/${id}`, { headers });
    await broker.close();
  }
});
