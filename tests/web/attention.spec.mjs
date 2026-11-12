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

test("durable notification is shared across views and stays read after reload", async ({
  page,
  context,
}) => {
  const fixture = JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_attention_browser.py", "--uncertain"], {
      encoding: "utf8",
    }),
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
  // «التنبيهات» on «المستجدات» (UI phase 4b).
  await page.goto("/app/updates");
  const alert = page.locator(`[data-attention-id="${fixture.notification.id}"]`);
  await expect(
    alert.getByText("Work stopped after repeated interruptions", { exact: true }),
  ).toBeVisible();
  await expect(alert.locator(".dot")).toHaveCount(1);
  // The watchdog's aging-operation item: owner text and the symbol, never a raw id.
  const uncertain = page.locator(`[data-attention-id="${fixture.uncertain.id}"]`);
  await expect(
    uncertain.getByText("A trade still has no confirmed broker result", { exact: true }),
  ).toBeVisible();
  await expect(uncertain.getByText("XAUUSD", { exact: true })).toBeVisible();
  await expect(uncertain).not.toContainText(fixture.uncertain.parameters.operation_id);
  // It names the agent that placed the trade, not the Personal Agent, and opens it.
  await expect(uncertain.getByText(fixture.agent.name, { exact: true })).toBeVisible();
  await page.reload();
  await expect(alert.locator(".dot")).toHaveCount(1);
  await uncertain.click();
  await expect(page).toHaveURL(new RegExp(`/app/${fixture.agent.id}\\?thread=`));
  await page.goto("/app/updates");
  await expect(uncertain.locator(".dot")).toHaveCount(0);
  // «تحديد الكل كمقروء»: the plain update is read, the critical item stays unread (Q4).
  const info = page.locator(`[data-attention-id="${fixture.informational.id}"]`);
  await expect(info.locator(".dot")).toHaveCount(1);
  const seenAll = page.waitForResponse((response) =>
    response.url().endsWith("/api/attention/seen-all"),
  );
  await page.getByRole("button", { name: "Mark all as read", exact: true }).click();
  expect((await seenAll).ok()).toBeTruthy();
  await expect(info.locator(".dot")).toHaveCount(0);
  await expect(alert.locator(".dot")).toHaveCount(1);
  const open = (await (await context.request.get("/api/attention")).json()).map((row) => row.id);
  expect(open).toContain(fixture.notification.id);
  expect(open).not.toContain(fixture.informational.id);
  await page.reload();
  await expect(uncertain.locator(".dot")).toHaveCount(0);
});
