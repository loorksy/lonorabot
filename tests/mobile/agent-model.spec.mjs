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
  test(`Mobile chooses an agent's model in its settings; there is no mode (${locale})`, async ({
    page,
    context,
  }) => {
    const data = await setup(context, locale);
    try {
      const { agent } = data;
      const record = async () =>
        (await context.request.get(`/api/agents/${agent.id}/model`)).json();
      await page.goto(`/bot-settings?botId=${agent.id}`);
      const settings = page.getByTestId("agent-model-settings");
      await expect(settings).toBeVisible();
      await expect(settings.getByTestId("agent-model-automatic")).toHaveCount(0);
      await expect(settings.getByTestId("agent-model-fixed")).toHaveCount(0);
      await settings.getByTestId("agent-model-choose").click();
      await settings.getByText("Claude Sonnet UI", { exact: true }).click();
      await expect.poll(record).toMatchObject({
        chosen_by: "owner",
        preference: { primary: { model: "claude-sonnet-ui" } },
      });
      expect(await record()).not.toHaveProperty("mode");
      // A model someone set: one action returns it to the default model.
      await settings.getByTestId("agent-model-default").click();
      await expect.poll(async () => (await record()).preference.primary).toBeNull();
      await expect(settings.getByTestId("agent-model-default")).toHaveCount(0);
      if (locale === "ar")
        await settings.screenshot({ path: test.info().outputPath("agent-model-native-ar.png") });
    } finally {
      fixture({ action: "cleanup", restore: data.restore });
    }
  });
}
