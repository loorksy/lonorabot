// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: Explicit disposable Playwright fixtures.
import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

function fixture(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/model_browser_fixture.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}

async function setup(context, locale) {
  const data = fixture({ action: "init", locale });
  await context.addCookies(
    data.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript((language) => {
    if (!/^https?:$/.test(location.protocol)) return;
    localStorage.setItem("lonora.locale", language);
  }, locale);
  return data;
}

for (const locale of ["en", "ar"]) {
  test(`the owner chooses an agent's model in its settings; there is no mode (${locale})`, async ({
    page,
    context,
  }) => {
    const data = await setup(context, locale);
    try {
      const { agent, thread } = data;
      const record = async () =>
        (await context.request.get(`/api/agents/${agent.id}/model`)).json();
      await page.goto(`/app/${agent.id}?thread=${thread.id}`);
      await page
        .getByRole("button", {
          name: locale === "ar" ? "معلومات الوكيل" : "Agent info",
          exact: true,
        })
        .click();
      const model = page.locator(".lonora-agent-model");
      await expect(model).toBeVisible();
      await expect(model).toContainText("GPT Default UI");
      await expect(model).toContainText(
        locale === "ar" ? "لا استخدام للنماذج" : "No model use in the last",
      );
      // Only the owner chooses: no Automatic / Fixed toggle, and every catalog model.
      await expect(model.getByRole("radio")).toHaveCount(0);
      await expect(model).toContainText(
        locale === "ar" ? "أنت وحدك تختار نموذجه" : "Only you choose its model",
      );
      await model.locator("select").selectOption("anthropic:claude-opus-ui");
      await model
        .getByRole("button", { name: locale === "ar" ? "حفظ النموذج" : "Save model", exact: true })
        .click();
      await expect
        .poll(async () => (await record()).preference.primary?.model)
        .toBe("claude-opus-ui");
      const chosen = await record();
      expect(chosen.chosen_by).toBe("owner");
      expect(chosen).not.toHaveProperty("mode");
      await expect(model).toContainText(locale === "ar" ? "اخترته أنت" : "Chosen by you");
      // A model someone set: one action returns it to the default model.
      const back = model.getByRole("button", {
        name: locale === "ar" ? "العودة إلى نموذجك الافتراضي" : "Back to your default model",
      });
      await back.click();
      await expect.poll(async () => (await record()).preference.primary).toBeNull();
      await expect(back).toHaveCount(0);
      if (locale === "ar") await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    } finally {
      fixture({ action: "cleanup", restore: data.restore });
    }
  });
}
