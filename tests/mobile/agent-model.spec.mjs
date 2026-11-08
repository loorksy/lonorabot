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
  await context.addInitScript((value) => localStorage.setItem("lonora.locale", value), locale);
  return data;
}

for (const locale of ["en", "ar"]) {
  test(`Mobile chooses an agent's model from the chat card and its settings (${locale})`, async ({
    page,
    context,
  }) => {
    const data = await setup(context, locale);
    try {
      const { agent, thread } = data;
      await page.goto(`/thread?id=${thread.id}`);
      const card = page.getByTestId(`owner-action-${data.card}`);
      await expect(
        card.getByText(locale === "ar" ? "تغيير نموذج" : "Change the model of", { exact: false }),
      ).toBeVisible();
      await expect(card.getByText("Claude Opus UI", { exact: false }).first()).toBeVisible();
      await card
        .getByRole("button", { name: locale === "ar" ? "استخدمه" : "Use it", exact: true })
        .click();
      await expect(
        card.getByText(locale === "ar" ? "تم. يستخدم" : "Done.", { exact: false }),
      ).toBeVisible();
      const after = await (await context.request.get(`/api/agents/${agent.id}/model`)).json();
      expect(after.preference.primary.model).toBe("claude-opus-ui");

      await page.goto(`/bot-settings?botId=${agent.id}`);
      const settings = page.getByTestId("agent-model-settings");
      await expect(settings).toBeVisible();
      await expect(settings.getByText("Claude Opus UI", { exact: false }).first()).toBeVisible();
      // Automatic on a model someone set: one action returns it to the default model.
      await settings.getByTestId("agent-model-default").click();
      await expect
        .poll(
          async () =>
            (await (await context.request.get(`/api/agents/${agent.id}/model`)).json()).preference
              .primary,
        )
        .toBeNull();
      await expect(settings.getByTestId("agent-model-default")).toHaveCount(0);
      await settings.getByTestId("agent-model-fixed").click();
      await settings.getByText("Claude Sonnet UI", { exact: true }).click();
      await expect
        .poll(async () => (await context.request.get(`/api/agents/${agent.id}/model`)).json())
        .toMatchObject({ mode: "fixed", preference: { primary: { model: "claude-sonnet-ui" } } });
      await settings.getByTestId("agent-model-automatic").click();
      await expect
        .poll(
          async () =>
            (await (await context.request.get(`/api/agents/${agent.id}/model`)).json()).mode,
        )
        .toBe("automatic");
      if (locale === "ar")
        await settings.screenshot({ path: test.info().outputPath("agent-model-native-ar.png") });
    } finally {
      fixture({ action: "cleanup", restore: data.restore });
    }
  });
}
