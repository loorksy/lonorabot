import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

for (const locale of ["en", "ar"])
  test(`${locale}: avatar studio saves independently without submitting unsaved profile fields`, async ({
    page,
    context,
  }) => {
    test.setTimeout(60000);
    const fixture = (input) =>
      JSON.parse(
        execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
          input: JSON.stringify(input),
          encoding: "utf8",
        }),
      );
    const data = fixture({ action: "init", empty: true });
    let agent;
    await context.addCookies(
      data.cookies.map((cookie) => ({
        ...cookie,
        url: test.info().project.use.baseURL,
        httpOnly: cookie.name === "lonora_session",
        sameSite: "Strict",
      })),
    );
    await context.addInitScript(
      (language) => localStorage.setItem("lonora.locale", language),
      locale,
    );
    if (locale === "ar") await page.setViewportSize({ width: 390, height: 844 });
    const headers = {
      "X-CSRF-Token": data.cookies.find((cookie) => cookie.name === "lonora_csrf").value,
    };
    const read = async () => (await context.request.get(`/api/agents/${agent.id}`)).json();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    try {
      await page.goto("/app/");
      await page
        .getByRole("button", { name: locale === "ar" ? "محادثة جديدة" : "New chat", exact: true })
        .first()
        .click();
      await page
        .locator("#dialog")
        .getByRole("button", { name: locale === "ar" ? /^وكيل جديد/ : /^New agent/ })
        .click();
      await expect(page).toHaveURL(/\/app\/new-agent$/);
      // The creation form is a page (a template first, owner decision Q9); the agent's info
      // opens as a sheet from the chat header.
      let panel = page.locator("main");
      await panel
        .getByRole("button", { name: locale === "ar" ? "التالي" : "Next", exact: true })
        .click();
      await panel
        .getByLabel(locale === "ar" ? "اسم الوكيل" : "Agent name", { exact: true })
        .fill(`Avatar Studio ${randomUUID()}`);
      await panel
        .getByLabel(locale === "ar" ? "الوصف" : "Description", { exact: true })
        .fill("Avatar studio fixture");
      await panel.getByTestId("avatar-studio-trigger").click();
      const studio = page.getByTestId("avatar-studio");
      await expect(studio).toBeVisible();
      await expect(studio.locator("[data-face-option]")).toHaveCount(16);
      await studio.locator('[data-face-option="face-wink"]').click();
      await studio.locator('button[aria-label$="#06B6D4"]').click();
      await expect(
        studio.getByTestId("avatar-studio-preview").locator("[data-shape]"),
      ).toHaveAttribute("data-shape", "face-wink");
      await page.screenshot({ path: `.runtime/avatar-studio-${locale}.png`, fullPage: true });
      await studio.getByTestId("avatar-studio-save").click();
      await expect(studio).not.toBeVisible();
      const creating = page.waitForResponse(
        (response) =>
          new URL(response.url()).pathname === "/api/agents/create" &&
          response.request().method() === "POST",
      );
      const styled = page.waitForResponse(
        (response) =>
          /^\/api\/agents\/[^/]+$/.test(new URL(response.url()).pathname) &&
          response.request().method() === "PATCH",
      );
      await panel
        .getByRole("button", {
          name: locale === "ar" ? "إنشاء الوكيل" : "Create the agent",
          exact: true,
        })
        .click();
      const created = await creating;
      expect(created.status()).toBe(201);
      agent = await created.json();
      expect(agent.template).toBe("general");
      // The chosen face and colour are saved on the new agent right after.
      expect((await styled).ok()).toBe(true);
      expect((await read()).avatar).toBe("face-wink");
      expect((await read()).color).toBe("#06B6D4");
      await page.goto(`/app/${agent.id}`);
      await page
        .getByRole("button", {
          name: locale === "ar" ? "معلومات الوكيل" : "Agent info",
          exact: true,
        })
        .click();
      panel = page.locator("#dialog");
      const nameField = panel.getByLabel(locale === "ar" ? "الاسم" : "Name", { exact: true });
      const persistedName = agent.name;
      const unsavedName = `${persistedName} draft`;
      await nameField.fill(unsavedName);
      const patches = [];
      page.on("request", (request) => {
        if (
          new URL(request.url()).pathname === `/api/agents/${agent.id}` &&
          request.method() === "PATCH"
        )
          patches.push(request.postDataJSON());
      });
      await panel.getByTestId("avatar-studio-trigger").click();
      await studio.locator('[data-face-option="face-angry"]').click();
      await studio.getByTestId("avatar-studio-cancel").click();
      await expect(
        panel.getByTestId("avatar-studio-trigger").locator("[data-shape]"),
      ).toHaveAttribute("data-shape", "face-wink");
      expect((await read()).avatar).toBe("face-wink");
      await panel.getByTestId("avatar-studio-trigger").click();
      await studio.locator('[data-face-option="face-happy"]').click();
      let rejectSave;
      const rejected = new Promise((resolve) => {
        rejectSave = resolve;
      });
      const failedRoute = async (route) => {
        if (route.request().method() !== "PATCH") return route.continue();
        await rejected;
        await route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({ code: "service_unavailable" }),
        });
      };
      await page.route(`**/api/agents/${agent.id}`, failedRoute);
      await studio.getByTestId("avatar-studio-save").click();
      await expect(studio.getByTestId("avatar-studio-save")).toBeDisabled();
      await expect(studio.locator('[data-face-option="face-happy"]')).toBeDisabled();
      await page.keyboard.press("Escape");
      await expect(studio).toBeVisible();
      rejectSave();
      await expect(studio.getByRole("alert")).toBeVisible();
      await expect(studio.locator('[data-face-option="face-happy"]')).toHaveAttribute(
        "aria-pressed",
        "true",
      );
      expect((await read()).avatar).toBe("face-wink");
      await page.unroute(`**/api/agents/${agent.id}`, failedRoute);
      await studio.getByTestId("avatar-studio-save").click();
      await expect(studio).not.toBeVisible();
      expect((await read()).avatar).toBe("face-happy");
      expect((await read()).name).toBe(persistedName);
      await expect(nameField).toHaveValue(unsavedName);
      expect(patches.at(-1)).toEqual({ avatar: "face-happy", color: "#06B6D4" });
      await panel.getByTestId("avatar-studio-trigger").click();
      await studio.getByTestId("avatar-studio-reset").click();
      await studio.getByTestId("avatar-studio-save").click();
      await expect(
        panel.getByTestId("avatar-studio-trigger").locator("[data-shape]"),
      ).toHaveAttribute("data-shape", "orb");
      await expect.poll(async () => (await read()).avatar).toBe("orb");
      expect((await read()).name).toBe(persistedName);
      await expect(nameField).toHaveValue(unsavedName);
      await panel
        .getByRole("button", { name: locale === "ar" ? "حفظ" : "Save", exact: true })
        .click();
      await expect.poll(async () => (await read()).avatar).toBe("orb");
      expect((await read()).color).toBe("#8B5CF6");
      expect((await read()).name).toBe(unsavedName);
      expect(patches.at(-1)).not.toHaveProperty("avatar");
      expect(patches.at(-1)).not.toHaveProperty("color");
      await page.reload();
      await page
        .getByRole("button", {
          name: locale === "ar" ? "معلومات الوكيل" : "Agent info",
          exact: true,
        })
        .click();
      await panel.getByTestId("avatar-studio-trigger").click();
      await expect(studio.locator('[data-face-option="orb"]')).toHaveAttribute(
        "aria-pressed",
        "true",
      );
      await studio.locator('[data-face-option="face-thoughtful"]').click();
      await page.keyboard.press("Escape");
      await expect(studio).not.toBeVisible();
      await expect(
        panel.getByTestId("avatar-studio-trigger").locator("[data-shape]"),
      ).toHaveAttribute("data-shape", "orb");
      expect(errors).toEqual([]);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
        ),
      ).toBeTruthy();
    } finally {
      if (agent) await context.request.delete(`/api/agents/${agent.id}`, { headers });
      fixture({ ...data, action: "cleanup" });
    }
  });
