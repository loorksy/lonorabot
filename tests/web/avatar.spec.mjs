// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: isolated UI-test credentials.
import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";
import { brokerFixture } from "./broker-fixture.mjs";

test("installed bot avatars use the supplied candles for old shape profiles", async ({
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
      const glyph = page.locator(".tpl-chat-identity .mta-avatar");
      await expect(glyph).toBeVisible();
      await expect(glyph.locator("[data-mta-bar]")).toHaveCount(8);
      await expect(glyph).toHaveAttribute("data-state", "waiting");
      const svg = glyph.locator("svg");
      await expect(svg).toHaveAttribute("viewBox", "22 22 356 356");
      const box = await svg.boundingBox();
      expect(box.width).toBeGreaterThan(20);
      expect(Math.abs(box.width - box.height)).toBeLessThan(1);
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await expect(page.locator(".tpl-chat-identity .mta-avatar")).toBeVisible();
    await page.screenshot({ path: ".runtime/liquid-lonora-web.png", fullPage: true });
    const svgIds = await page
      .locator(".mta-avatar clipPath")
      .evaluateAll((nodes) => nodes.map((node) => node.id));
    expect(new Set(svgIds).size).toBe(svgIds.length);
    expect(errors).toEqual([]);
  } finally {
    for (const id of ids) await context.request.delete(`/api/agents/${id}`, { headers });
    await broker.close();
  }
});

test("liquid engine renders all states and releases shared animation/listeners", async ({
  page,
}) => {
  const source = await readFile(
    new URL("../../packages/core/src/trading-avatar-motion.js", import.meta.url),
    "utf8",
  );
  const css = await readFile(
    new URL("../../packages/ui-web/src/trading-avatar.css", import.meta.url),
    "utf8",
  );
  await page.route("**/avatar-engine.js", (route) =>
    route.fulfill({ contentType: "text/javascript", body: source }),
  );
  await page.route("**/avatar-harness", (route) =>
    route.fulfill({
      contentType: "text/html",
      body: `<style>${css}body{background:#0b0b0f;color:white;display:flex;flex-wrap:wrap;gap:24px;font:14px sans-serif}section{text-align:center}.mta-avatar{width:140px;height:140px}</style>`,
    }),
  );
  await page.goto("/avatar-harness");
  await page.evaluate(async () => {
    const { STATE_IDS, markup, mount } = await import("/avatar-engine.js");
    const pending = new Set();
    const request = requestAnimationFrame;
    const cancel = cancelAnimationFrame;
    window.requestAnimationFrame = (callback) => {
      const id = request((now) => {
        pending.delete(id);
        callback(now);
      });
      pending.add(id);
      return id;
    };
    window.cancelAnimationFrame = (id) => {
      pending.delete(id);
      cancel(id);
    };
    const controllers = [];
    for (const state of STATE_IDS) {
      const holder = document.createElement("section");
      const root = document.createElement("span");
      root.className = "mta-avatar";
      root.innerHTML = markup(null, "full");
      holder.append(root, document.createElement("br"), document.createTextNode(state));
      document.body.append(holder);
      controllers.push(mount(root, { state }));
    }
    window.avatarHarness = { controllers, pending, mount };
  });
  await expect(page.locator("[data-state]")).toHaveCount(20);
  const first = page.locator("[data-mta-bar]").first();
  const before = await first.getAttribute("d");
  await expect.poll(() => first.getAttribute("d")).not.toBe(before);
  await page.screenshot({ path: ".runtime/liquid-avatar-gallery.png", fullPage: true });
  await page.emulateMedia({ reducedMotion: "reduce" });
  const still = await first.getAttribute("d");
  await page.evaluate(() => new Promise((resolve) => setTimeout(resolve, 100)));
  expect(await first.getAttribute("d")).toBe(still);
  await page.evaluate(() => {
    for (const ctl of window.avatarHarness.controllers) {
      ctl.destroy();
      ctl.destroy();
    }
  });
  expect(await page.evaluate(() => window.avatarHarness.pending.size)).toBe(0);
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.evaluate(() => {
    const ctl = window.avatarHarness.mount(document.querySelector(".mta-avatar"), {
      state: "listening",
    });
    ctl.setState("speaking");
    window.avatarHarness.controllers = [ctl];
  });
  await expect(page.locator(".mta-avatar").first()).toHaveAttribute("data-state", "speaking");
  await page.evaluate(() => window.avatarHarness.controllers[0].destroy());
  expect(await page.evaluate(() => window.avatarHarness.pending.size)).toBe(0);
});
