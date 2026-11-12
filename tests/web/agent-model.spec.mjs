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

      // The same choice on the agent's «الهوية والنموذج» page: Fixed on one model, then
      // Automatic, which drops the model the agent set and returns to the default.
      const ar = locale === "ar";
      const identity = async () => {
        await page.goto(`/app/agent/${agent.id}`);
        await page
          .getByRole("button", { name: ar ? "الهوية والنموذج" : "Identity and model" })
          .click();
        await expect(page).toHaveURL(new RegExp(`/app/identity/${agent.id}$`));
        const select = page.getByRole("combobox", { name: ar ? "النموذج" : "Model", exact: true });
        await expect(select).toBeEnabled();
        // The page saves the whole identity: the fixture agent has no role yet.
        const role = page.getByRole("textbox", { name: ar ? "الدور" : "Role", exact: true });
        if (!(await role.inputValue())) await role.fill("Model tests");
        return select;
      };
      const save = () => page.getByRole("button", { name: ar ? "حفظ" : "Save", exact: true });
      const stored = async () =>
        (await context.request.get(`/api/agents/${agent.id}/model`)).json();
      let model = await identity();
      // The agent's own choice is not the owner's fixed model: the page shows Automatic.
      await expect(model).toHaveValue("");
      await expect(model.locator("option", { hasText: "Claude Sonnet UI" })).toHaveCount(1);
      await model.selectOption("anthropic:claude-sonnet-ui");
      await save().click();
      await expect.poll(async () => (await stored()).mode).toBe("fixed");
      const fixed = await stored();
      expect(fixed.chosen_by).toBe("owner");
      expect(fixed.preference.primary.model).toBe("claude-sonnet-ui");
      model = await identity();
      await expect(model).toHaveValue("anthropic:claude-sonnet-ui");
      await model.selectOption("");
      await save().click();
      await expect.poll(async () => (await stored()).mode).toBe("automatic");
      expect((await stored()).preference.primary).toBeNull();
      if (locale === "ar") await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    } finally {
      fixture({ action: "cleanup", restore: data.restore });
    }
  });
}
