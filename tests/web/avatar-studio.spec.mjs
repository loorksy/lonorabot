import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

/* «تعديل الأفتار» (Q42) is one sheet, opened from the agent picture on its page or form. The
   avatar saves on its own: an unsaved name in the identity form is neither sent nor lost. */
for (const locale of ["en", "ar"])
  test(`${locale}: the avatar sheet saves independently without submitting unsaved profile fields`, async ({
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
      agent = await (
        await context.request.post("/api/agents/create", {
          headers,
          data: {
            template: "general",
            name: `Avatar ${randomUUID().slice(0, 8)}`,
            responsibility: "Answers questions",
          },
        })
      ).json();
      await page.goto(`/app/identity/${agent.id}`);
      const main = page.locator("main");
      const nameField = main.getByLabel(locale === "ar" ? "الاسم" : "Name", { exact: true });
      const unsavedName = `${agent.name} draft`;
      await nameField.fill(unsavedName);
      const patches = [];
      page.on("request", (request) => {
        if (
          new URL(request.url()).pathname === `/api/agents/${agent.id}` &&
          request.method() === "PATCH"
        )
          patches.push(request.postDataJSON());
      });
      const studio = page.getByTestId("avatar-studio");
      const shape = main.locator(".edit-wrap [data-shape]");
      await main.locator(".pencil").click();
      await expect(studio.locator("[data-face-option]")).toHaveCount(16);
      await studio.locator('[data-face-option="face-wink"]').click();
      const swatch = studio.locator(".swatch").nth(2);
      const color = (await swatch.getAttribute("aria-label")).split(" ").at(-1);
      await swatch.click();
      await expect(
        studio.getByTestId("avatar-studio-preview").locator("[data-shape]"),
      ).toHaveAttribute("data-shape", "face-wink");
      await studio.getByTestId("avatar-studio-save").click();
      await expect(studio).toHaveCount(0);
      expect(patches.at(-1)).toEqual({ avatar: "face-wink", color });
      await expect(shape).toHaveAttribute("data-shape", "face-wink");
      expect((await read()).name).toBe(agent.name);
      await expect(nameField).toHaveValue(unsavedName);
      // «إلغاء» keeps the saved look.
      await main.locator(".pencil").click();
      await studio.locator('[data-face-option="face-angry"]').click();
      await studio.getByTestId("avatar-studio-cancel").click();
      await expect(studio).toHaveCount(0);
      await expect(shape).toHaveAttribute("data-shape", "face-wink");
      expect((await read()).avatar).toBe("face-wink");
      // A failed save keeps the sheet, the pick and the error; nothing is stored.
      await main.locator(".pencil").click();
      await studio.locator('[data-face-option="face-happy"]').click();
      const failedRoute = (route) =>
        route.request().method() === "PATCH"
          ? route.fulfill({
              status: 503,
              contentType: "application/json",
              body: JSON.stringify({ code: "service_unavailable" }),
            })
          : route.continue();
      await page.route(`**/api/agents/${agent.id}`, failedRoute);
      await studio.getByTestId("avatar-studio-save").click();
      await expect(studio.getByRole("alert")).toBeVisible();
      await expect(studio.locator('[data-face-option="face-happy"]')).toHaveAttribute(
        "aria-pressed",
        "true",
      );
      expect((await read()).avatar).toBe("face-wink");
      await page.unroute(`**/api/agents/${agent.id}`, failedRoute);
      await studio.getByTestId("avatar-studio-save").click();
      await expect(studio).toHaveCount(0);
      expect((await read()).avatar).toBe("face-happy");
      // «إعادة تعيين» goes back to Lonora's signals shape.
      await main.locator(".pencil").click();
      await studio.getByTestId("avatar-studio-reset").click();
      await studio.getByTestId("avatar-studio-save").click();
      await expect(shape).toHaveAttribute("data-shape", "orb");
      await expect.poll(async () => (await read()).avatar).toBe("orb");
      expect((await read()).name).toBe(agent.name);
      await expect(nameField).toHaveValue(unsavedName);
      // The form's own save sends the name, never the look.
      await main
        .getByRole("button", { name: locale === "ar" ? "حفظ" : "Save", exact: true })
        .click();
      await expect.poll(async () => (await read()).name).toBe(unsavedName);
      expect((await read()).avatar).toBe("orb");
      expect(patches.at(-1)).not.toHaveProperty("avatar");
      expect(patches.at(-1)).not.toHaveProperty("color");
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
