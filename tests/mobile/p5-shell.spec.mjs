// P5 on mobile: outside conversations the app has only the agent and conversation list, the
// attention view, «ما أعرفه عنك», «ما الذي يعمل» and sign-in. A screen whose work is done from
// chat is gone: creating an agent (agent_create) and the models page (model_list and
// model_request). The screens still kept are listed in docs/mobile/p5-shell.md.
import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

test("no agent-creation or models screen: the new-chat sheet, agents and settings lead to chat", async ({
  page,
  context,
}) => {
  const data = JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify({ action: "init", empty: true }),
      encoding: "utf8",
    }),
  );
  await context.addCookies(
    data.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  await page.goto("/");
  await page.getByRole("button", { name: "New chat", exact: true }).click();
  const sheet = page.getByRole("dialog");
  await expect(sheet.getByRole("button", { name: /^New group/ })).toBeVisible();
  await expect(sheet.getByRole("button", { name: /^New agent/ })).toHaveCount(0);

  await page.goto("/agents");
  await expect(page.getByRole("button", { name: "Create agent", exact: true })).toHaveCount(0);

  await page.goto("/settings");
  await expect(page.getByRole("button", { name: "Account", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Models", exact: true })).toHaveCount(0);

  for (const path of ["/new", "/models"]) {
    await page.goto(path);
    await expect(page.getByText("Account", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("textbox", { name: "Agent name" })).toHaveCount(0);
    await expect(page.getByText("Providers", { exact: true })).toHaveCount(0);
  }
});
