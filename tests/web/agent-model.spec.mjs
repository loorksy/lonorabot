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
  test(`the owner chooses an agent's model in its settings and from a chat card (${locale})`, async ({
    page,
    context,
  }) => {
    const data = await setup(context, locale);
    try {
      const { agent, thread } = data;
      await page.goto(`/app/${agent.id}?thread=${thread.id}`);
      // The agent asked for a model outside the allowed list: one card, one tap.
      const card = page.locator(`[data-owner-action="${data.card}"]`);
      await expect(card).toBeVisible();
      await expect(card).toContainText(locale === "ar" ? "تغيير نموذج" : "Change the model of");
      await expect(card).toContainText("Claude Opus UI");
      await expect(card).not.toContainText("claude-opus-ui");
      await expect(card).not.toContainText(data.card);
      await card.getByRole("button", { name: locale === "ar" ? "استخدمه" : "Use it" }).click();
      await expect(card).toContainText(locale === "ar" ? "تم. يستخدم" : "Done.");
      const after = await (await context.request.get(`/api/agents/${agent.id}/model`)).json();
      expect(after.mode).toBe("automatic");
      expect(after.preference.primary).toEqual({
        provider: "anthropic",
        model: "claude-opus-ui",
      });
      const allowed = await (await context.request.get("/api/settings/models/allowed")).json();
      expect(allowed.added).toContainEqual({ provider: "anthropic", model: "claude-opus-ui" });

      // The same choice in the agent's settings: Fixed on one model, then Automatic.
      await page
        .getByRole("button", {
          name: locale === "ar" ? "معلومات الوكيل" : "Agent info",
          exact: true,
        })
        .click();
      const model = page.locator(".lonora-agent-model");
      await expect(model).toBeVisible();
      await expect(model).toHaveAttribute("data-agent-model-mode", "automatic");
      await expect(model).toContainText("Claude Opus UI");
      await expect(model).toContainText(
        locale === "ar" ? "لا استخدام للنماذج" : "No model use in the last",
      );
      // Automatic on a model someone set: one action returns it to the default model.
      const back = model.getByRole("button", {
        name: locale === "ar" ? "العودة إلى نموذجك الافتراضي" : "Back to your default model",
      });
      await back.click();
      await expect
        .poll(
          async () =>
            (await (await context.request.get(`/api/agents/${agent.id}/model`)).json()).preference
              .primary,
        )
        .toBeNull();
      await expect(back).toHaveCount(0);
      await expect(model).toContainText("GPT Default UI");
      await model.getByLabel(locale === "ar" ? "ثابت" : "Fixed").check();
      await model.locator("select").selectOption("anthropic:claude-sonnet-ui");
      await model
        .getByRole("button", { name: locale === "ar" ? "حفظ النموذج" : "Save model", exact: true })
        .click();
      await expect(model).toHaveAttribute("data-agent-model-mode", "fixed");
      const fixed = await (await context.request.get(`/api/agents/${agent.id}/model`)).json();
      expect(fixed.mode).toBe("fixed");
      expect(fixed.chosen_by).toBe("owner");
      expect(fixed.preference.primary.model).toBe("claude-sonnet-ui");
      await model.getByLabel(locale === "ar" ? "تلقائي" : "Automatic").check();
      await model
        .getByRole("button", { name: locale === "ar" ? "حفظ النموذج" : "Save model", exact: true })
        .click();
      await expect(model).toHaveAttribute("data-agent-model-mode", "automatic");
      if (locale === "ar") await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    } finally {
      fixture({ action: "cleanup", restore: data.restore });
    }
  });
}
