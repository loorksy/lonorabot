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
  let secondAgent;
  let group;
  let uiAgent;
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
    const secondCreated = await context.request.post("/api/agents", {
      headers,
      data: { name: agent.name, avatar: "organic", color: agent.color, ...broker.binding },
    });
    expect(secondCreated.status()).toBe(201);
    secondAgent = await secondCreated.json();
    const grouped = await context.request.post("/api/groups/create", {
      headers,
      data: {
        name: `Independent motion ${randomUUID()}`,
        member_ids: [agent.id, secondAgent.id],
        participation: "mentions_or_lead",
      },
    });
    expect(grouped.ok()).toBeTruthy();
    group = await grouped.json();
    await page.goto(`/thread?id=${group.thread_id}`);
    for (const id of [agent.id, secondAgent.id]) {
      await expect(
        page.locator(`[data-testid="trading-avatar"][id$="-motion-${id}"]`),
      ).toBeVisible();
    }
    // Same names and simultaneous mounting still produce different faces and internal signals.
    await expect
      .poll(() =>
        page.evaluate(
          ([firstId, secondId]) => {
            const frames = [firstId, secondId].map((id) => {
              const root = document.querySelector(
                `[data-testid="trading-avatar"][id$="-motion-${id}"]`,
              );
              return {
                face: root.querySelector('g[id$="turn"] > g')?.getAttribute("transform"),
                signals: [...root.querySelectorAll("path")]
                  .map((path) => path.getAttribute("d"))
                  .join("|"),
              };
            });
            return frames[0].face !== frames[1].face && frames[0].signals !== frames[1].signals;
          },
          [agent.id, secondAgent.id],
        ),
      )
      .toBe(true);
    await page.screenshot({ path: ".runtime/individual-avatar-mobile.png", fullPage: true });
    // Existing-agent appearance saves independently of unsaved profile fields.
    await page.goto(`/bot-settings?botId=${agent.id}`);
    const dirtyName = `Unsaved profile ${randomUUID()}`;
    await page.getByRole("textbox", { name: "الاسم", exact: true }).fill(dirtyName);
    const editAvatar = page.getByRole("button", { name: "تعديل الأفاتار", exact: true });
    await editAvatar.click();
    const studio = page.getByTestId("avatar-studio");
    await expect(studio).toBeVisible();
    await expect(studio.getByTestId("avatar-face-face-wink")).toHaveAttribute(
      "aria-checked",
      "false",
    );
    await studio.getByTestId("avatar-face-face-wink").click();
    await expect(studio.getByTestId("avatar-face-face-wink")).toHaveAttribute(
      "aria-checked",
      "true",
    );
    await studio.getByRole("button", { name: "إلغاء", exact: true }).click();
    await editAvatar.click();
    await expect(studio.getByTestId("avatar-face-face-wink")).toHaveAttribute(
      "aria-checked",
      "false",
    );
    await studio.getByTestId("avatar-face-face-wink").click();
    await studio.getByRole("button", { name: "إعادة الضبط", exact: true }).click();
    await expect(studio.getByTestId("avatar-face-orb")).toHaveAttribute("aria-checked", "true");
    await studio.getByRole("button", { name: "إلغاء", exact: true }).click();
    await editAvatar.click();
    await studio.getByTestId("avatar-face-face-wink").click();
    await studio.getByRole("radio", { name: /#06B6D4/i }).click();
    const appearanceWrites = [];
    let failAppearance = true;
    await page.route(`**/api/agents/${agent.id}`, async (route) => {
      if (route.request().method() !== "PATCH") return route.continue();
      const body = route.request().postDataJSON();
      appearanceWrites.push(body);
      if (failAppearance) {
        failAppearance = false;
        return route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({ detail: "temporarily_unavailable" }),
        });
      }
      return route.continue();
    });
    await studio.getByRole("button", { name: "حفظ", exact: true }).click();
    await expect(studio).toBeVisible();
    await expect(studio.getByRole("alert")).toBeVisible();
    await expect(studio.getByTestId("avatar-face-face-wink")).toHaveAttribute(
      "aria-checked",
      "true",
    );
    const readAgent = async (id) => await (await context.request.get(`/api/agents/${id}`)).json();
    expect((await readAgent(agent.id)).avatar).toBe("organic");
    await studio.getByRole("button", { name: "حفظ", exact: true }).click();
    await expect(studio).not.toBeVisible();
    await expect.poll(async () => (await readAgent(agent.id)).avatar).toBe("face-wink");
    expect((await readAgent(agent.id)).name).toBe(agent.name);
    await expect(page.getByRole("textbox", { name: "الاسم", exact: true })).toHaveValue(dirtyName);
    expect(appearanceWrites).toEqual([
      { avatar: "face-wink", color: "#06B6D4" },
      { avatar: "face-wink", color: "#06B6D4" },
    ]);
    await page.getByRole("button", { name: "حفظ", exact: true }).click();
    await expect.poll(async () => (await readAgent(agent.id)).name).toBe(dirtyName);
    expect((await readAgent(agent.id)).avatar).toBe("face-wink");
    expect(appearanceWrites.at(-1)).not.toHaveProperty("avatar");
    expect(appearanceWrites.at(-1)).not.toHaveProperty("color");
    await expect(page.getByText("تم الحفظ", { exact: true })).toBeVisible();
    await page.reload();
    await page.getByRole("button", { name: "تعديل الأفاتار", exact: true }).click();
    await expect(studio.getByTestId("avatar-face-face-wink")).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect((await readAgent(agent.id)).color.toLowerCase()).toBe("#06b6d4");
    await page.screenshot({
      path: ".runtime/face-studio-native.png",
      fullPage: true,
      animations: "disabled",
    });
    await studio.getByRole("button", { name: "إلغاء", exact: true }).click();

    // Creation exposes the same picker and saves the selected expression without a broker binding.
    await page.goto("/new");
    await page.getByRole("button", { name: "التالي", exact: true }).click();
    await page
      .getByRole("textbox", { name: "اسم الوكيل", exact: true })
      .fill(`Native face ${randomUUID()}`);
    await page.getByRole("textbox", { name: "الوصف", exact: true }).fill("Face check");
    await page.getByRole("button", { name: "تعديل الأفاتار", exact: true }).click();
    await expect(studio.getByTestId("avatar-face-face-smile")).toHaveAttribute(
      "aria-checked",
      "true",
    );
    await studio.getByTestId("avatar-face-face-happy").click();
    await studio.getByRole("button", { name: "حفظ", exact: true }).click();
    const createdByUi = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/agents/create") && response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "إنشاء الوكيل", exact: true }).click();
    const uiResponse = await createdByUi;
    expect(uiResponse.status()).toBe(201);
    uiAgent = await uiResponse.json();
    await expect(page.getByTestId("trading-avatar").first()).toBeVisible();
    await expect.poll(async () => (await readAgent(uiAgent.id)).avatar).toBe("face-happy");

    expect(errors).toEqual([]);
  } finally {
    if (uiAgent) await context.request.delete(`/api/agents/${uiAgent.id}`, { headers });
    if (group) await context.request.delete(`/api/groups/${group.id}`, { headers });
    if (secondAgent) await context.request.delete(`/api/agents/${secondAgent.id}`, { headers });
    if (agent) await context.request.delete(`/api/agents/${agent.id}`, { headers });
    await broker.close();
  }
});
