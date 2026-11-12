import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

// The fixture's agent holds an uncertain trade, which rightly refuses its deletion: it is
// paused after the test, so it never counts against the agent cap.
let fixtureAgent;
test.afterEach(() => {
  if (!fixtureAgent) return;
  execFileSync(".venv/bin/python", ["tests/browser_agents.py"], {
    input: JSON.stringify({ action: "pause", ids: [fixtureAgent] }),
    encoding: "utf8",
  });
  fixtureAgent = undefined;
});

test("Expo Arabic attention view lists what needs the owner and opens its conversation", async ({
  page,
  context,
}) => {
  const fixture = JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_attention_browser.py"], { encoding: "utf8" }),
  );
  fixtureAgent = fixture.agent?.id;
  await context.addCookies(
    fixture.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      sameSite: "Strict",
      httpOnly: cookie.name === "lonora_session",
    })),
  );
  await page.goto("/");
  await page.getByTestId("tab-updates").click();
  // «يحتاج انتباهك» (11.7): the same server view as the web, in Arabic.
  const view = page.getByTestId("attention-view");
  const row = view.getByTestId("attention-row-settle_operation").filter({
    hasText: fixture.agent.name,
  });
  await expect(
    row.getByText("الوسيط لم يؤكد صفقة — أخبر لونورا هل نُفذت", { exact: true }),
  ).toBeVisible();
  await expect(row.getByText("XAUUSD", { exact: true })).toBeVisible();
  await expect(row).not.toContainText(fixture.uncertain.parameters.operation_id);
  // Opening it shows the conversation, where the Settle card stands; it settles nothing.
  await row.getByRole("button", { name: "فتح المحادثة", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/thread\\?id=${fixture.uncertain.thread_id}`));
  const listed = await (await context.request.get("/api/attention/view")).json();
  expect(listed.map((entry) => entry.id)).toContain(fixture.uncertain.id);
});
