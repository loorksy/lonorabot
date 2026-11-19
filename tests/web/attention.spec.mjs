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

test("the attention view lists what needs the owner, opens its conversation and decides nothing", async ({
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
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  // «يحتاج انتباهك» (11.7): the page is one skeleton until the server's view loads.
  let release;
  const held = new Promise((resolve) => {
    release = resolve;
  });
  await page.route("**/api/attention/view", async (route) => {
    await held;
    await route.continue();
  });
  await page.goto("/app/updates");
  const main = page.getByRole("main");
  await expect(main.locator(".sk-page[aria-busy='true']")).toBeVisible();
  release();
  await expect(main.locator(".sk-page")).toHaveCount(0);
  await expect(page.getByTestId("attention-view")).toBeVisible();
  // The uncertain trade: owner text, the agent that placed it and the symbol, no raw id.
  const uncertain = page.locator(`[data-attention-id="${fixture.uncertain.id}"]`);
  await expect(
    uncertain.getByText("The broker did not confirm a trade — tell Lonora whether it executed", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(uncertain).toHaveAttribute("data-attention-kind", "settle_operation");
  await expect(uncertain.getByText("XAUUSD", { exact: true })).toBeVisible();
  await expect(uncertain.getByText(fixture.agent.name, { exact: true })).toBeVisible();
  await expect(uncertain).not.toContainText(fixture.uncertain.parameters.operation_id);
  // A plain update needs nothing: the view never lists it, and no other section remains.
  await expect(page.locator(`[data-attention-id="${fixture.informational.id}"]`)).toHaveCount(0);
  await expect(main.getByRole("button", { name: "Mark all as read" })).toHaveCount(0);
  await expect(main.getByText("Latest actions")).toHaveCount(0);
  // A tap opens the agent's conversation, where the Settle card stands; it settles nothing.
  await uncertain.click();
  await expect(page).toHaveURL(new RegExp(`/app/${fixture.agent.id}\\?thread=`));
  const view = await (await context.request.get("/api/attention/view")).json();
  expect(view.map((row) => row.id)).toContain(fixture.uncertain.id);
});
