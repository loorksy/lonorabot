import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

for (const locale of ["en", "ar"])
  test(`${locale}: avatar studio creates and saves a face while cancelled drafts stay local`, async ({
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
        .getByRole("button", {
          name: locale === "ar" ? "إنشاء محادثة" : "Create conversation",
          exact: true,
        })
        .first()
        .click();
      await page.getByTestId("create-new-agent").click();
      const panel = page.getByTestId("side-panel");
      await panel
        .getByLabel(locale === "ar" ? "الاسم" : "Name", { exact: true })
        .fill(`Avatar Studio ${randomUUID()}`);
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
      await studio.getByTestId("avatar-studio-done").click();
      await expect(studio).not.toBeVisible();
      const creating = page.waitForResponse(
        (response) =>
          new URL(response.url()).pathname === "/api/agents" &&
          response.request().method() === "POST",
      );
      await panel
        .getByRole("button", { name: locale === "ar" ? "إنشاء وكيل" : "Create agent", exact: true })
        .click();
      const created = await creating;
      expect(created.status()).toBe(201);
      agent = await created.json();
      expect(agent.avatar).toBe("face-wink");
      expect(agent.color).toBe("#06B6D4");
      await page.goto(`/app/${agent.id}`);
      await page.locator(".tpl-chat-identity").click();
      await panel.getByTestId("avatar-studio-trigger").click();
      await studio.locator('[data-face-option="face-angry"]').click();
      await studio.getByTestId("avatar-studio-cancel").click();
      await expect(
        panel.getByTestId("avatar-studio-trigger").locator("[data-shape]"),
      ).toHaveAttribute("data-shape", "face-wink");
      expect((await read()).avatar).toBe("face-wink");
      await panel.getByTestId("avatar-studio-trigger").click();
      await studio.getByTestId("avatar-studio-reset").click();
      await studio.getByTestId("avatar-studio-done").click();
      await expect(
        panel.getByTestId("avatar-studio-trigger").locator("[data-shape]"),
      ).toHaveAttribute("data-shape", "orb");
      expect((await read()).avatar).toBe("face-wink");
      await panel
        .getByRole("button", { name: locale === "ar" ? "حفظ" : "Save", exact: true })
        .click();
      await expect.poll(async () => (await read()).avatar).toBe("orb");
      expect((await read()).color).toBe("#8B5CF6");
      await page.reload();
      await page.locator(".tpl-chat-identity").click();
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
