import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

// The fixture's agent holds an uncertain trade, which rightly refuses its deletion: it is
// paused after the test, so it never wakes in later tests.
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
  // A MetaApi throttle is a broker health row of its own code: the view adds one to the
  // server's answer, so the label it shows is the client's own choice.
  const throttle = `browser-throttle-${Date.now()}`;
  // Once set, the view answers with the fixture's own row only, so the dot follows it alone.
  let fixtureOnly = false;
  await page.route("**/api/attention/view", async (route) => {
    const response = await route.fetch();
    const rows = await response.json();
    if (fixtureOnly)
      return route.fulfill({
        response,
        json: rows.filter((entry) => entry.id === fixture.uncertain.id),
      });
    await route.fulfill({
      response,
      json: [
        {
          kind: "broker_health",
          id: throttle,
          agent_id: fixture.agent.id,
          thread_id: fixture.uncertain.thread_id,
          code: "broker_rate_limited",
          created_at: new Date().toISOString(),
        },
        ...rows,
      ],
    });
  });
  // The 50 newest open items may hold none of the view's rows (an old card under newer
  // updates): the tab's dot follows the view itself.
  await page.route("**/api/attention", (route) => route.fulfill({ json: [] }));
  await page.goto("/");
  await expect(page.getByTestId("tab-updates")).toHaveAttribute("aria-label", /جديد/);
  await page.getByTestId("tab-updates").click();
  // «يحتاج انتباهك» (11.7): the same server view as the web, in Arabic.
  const view = page.getByTestId("attention-view");
  // A throttle says MetaApi is limiting requests, never that the connection was lost.
  const limited = view.getByTestId("attention-row-broker_health").filter({
    hasText: fixture.agent.name,
  });
  await expect(limited.getByText("MetaApi تحدّ من الطلبات حاليًا", { exact: true })).toBeVisible();
  await expect(limited).not.toContainText("انقطع الاتصال بالحساب");
  const row = view.getByTestId("attention-row-settle_operation").filter({
    hasText: fixture.agent.name,
  });
  await expect(
    row.getByText("الوسيط لم يؤكد صفقة — أخبر لونورا هل نُفذت", { exact: true }),
  ).toBeVisible();
  await expect(row.getByText("XAUUSD", { exact: true })).toBeVisible();
  await expect(row).not.toContainText(fixture.uncertain.parameters.operation_id);
  // Opening it shows the conversation, where the Settle card stands; it settles nothing.
  fixtureOnly = true;
  await row.getByRole("button", { name: "فتح المحادثة", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/thread\\?id=${fixture.uncertain.thread_id}`));
  // Opening read the card: it stays listed until it is settled, seen, and lights no dot.
  await expect
    .poll(async () => {
      const listed = await (await context.request.get("/api/attention/view")).json();
      return listed.find((entry) => entry.id === fixture.uncertain.id)?.seen;
    })
    .toBe(true);
  await page.goBack();
  await expect(row).toBeVisible();
  await expect(page.getByTestId("tab-updates")).not.toHaveAttribute("aria-label", /جديد/, {
    timeout: 15_000,
  });
});
