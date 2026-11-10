import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

test("durable notification is shared across views and stays read after reload", async ({
  page,
  context,
}) => {
  const fixture = JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_attention_browser.py", "--uncertain"], {
      encoding: "utf8",
    }),
  );
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
  await expect(alert.getByText("New trading stopped", { exact: true })).toBeVisible();
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
  // «تحديد الكل كمقروء» keeps critical and action-required items unread (Q4).
  const before = await (await context.request.get("/api/attention")).json();
  const open = (rows) => rows.filter((row) => row.id === fixture.notification.id);
  const markAll = page.getByRole("button", { name: "Mark all as read", exact: true });
  const keptUnread = ["critical", "action_required"].includes(fixture.notification.importance);
  // The fixture's own alert is still unread here, so the bulk action is offered.
  await expect(markAll).toBeVisible();
  {
    const seenAll = page.waitForResponse((response) =>
      response.url().endsWith("/api/attention/seen-all"),
    );
    await markAll.click();
    expect((await seenAll).ok()).toBeTruthy();
  }
  const after = await (await context.request.get("/api/attention")).json();
  if (keptUnread) expect(open(after)).toEqual(open(before));
  else expect(open(after)).toEqual([]);
  await page.reload();
  await expect(uncertain.locator(".dot")).toHaveCount(0);
  const controls = await (await context.request.get("/api/trading/controls")).json();
  expect(controls).toMatchObject({ enabled: false, emergency_stop: true });
});
