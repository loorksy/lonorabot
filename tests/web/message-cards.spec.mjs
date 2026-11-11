import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

const LONG =
  "Prepare the weekly report on the gold positions, the open orders and the week's news, then send me a short summary with the three points that matter most for next week.";

async function setup(page, context) {
  const fixture = JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify({ action: "init" }),
      encoding: "utf8",
    }),
  );
  await context.addCookies(
    fixture.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  const headers = {
    "X-CSRF-Token": fixture.cookies.find((row) => row.name === "lonora_csrf").value,
  };
  const agent = await (
    await context.request.post("/api/agents", {
      headers,
      data: {
        name: `Message cards ${randomUUID()}`,
        trading_account_id: fixture.account,
        trading_symbol: fixture.symbol,
      },
    })
  ).json();
  const thread = await (
    await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
  ).json();
  const row = (seq, role, content, attachment_ids = []) => ({
    id: `cards-${seq}`,
    seq,
    thread_id: thread.id,
    agent_id: agent.id,
    role,
    content,
    created_at: new Date(Date.now() - (10 - seq) * 60_000).toISOString(),
    reply_to: null,
    attachment_ids,
  });
  const messages = [row(1, "user", "", [randomUUID()]), row(2, "assistant", LONG)];
  await page.route(`**/api/threads/${thread.id}/messages*`, (route) =>
    route.request().method() === "GET" ? route.fulfill({ json: messages }) : route.fallback(),
  );
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  return {
    agent,
    thread,
    cleanup: () => context.request.delete(`/api/agents/${agent.id}`, { headers }),
  };
}

for (const [size, viewport, cap] of [
  ["desktop", { width: 1280, height: 800 }, 0.68],
  ["phone", { width: 390, height: 844 }, 0.88],
]) {
  test(`a long ${size} bubble stops at the reference's width cap`, async ({ page, context }) => {
    const fixture = await setup(page, context);
    try {
      await page.setViewportSize(viewport);
      await page.goto(`/app/${fixture.agent.id}?thread=${fixture.thread.id}`);
      const message = page.locator('[data-message-id="cards-2"]');
      await expect(message).toBeVisible();
      const ratio = await message.evaluate(
        (node) =>
          node.querySelector(".msg-line").getBoundingClientRect().width /
          node.getBoundingClientRect().width,
      );
      expect(ratio).toBeGreaterThan(cap - 0.02);
      expect(ratio).toBeLessThanOrEqual(cap + 0.001);
    } finally {
      await fixture.cleanup();
    }
  });
}

test("a message turned into a task leaves a durable «Task created» card that opens the task", async ({
  page,
  context,
}) => {
  const fixture = await setup(page, context);
  try {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`/app/${fixture.agent.id}?thread=${fixture.thread.id}`);
    // A photo has no text to make a task of (reference 3885: only plain messages).
    const photo = page.locator('[data-message-id="cards-1"]');
    await photo.hover();
    await photo.locator(".msg-more").click();
    const menu = page.getByRole("menu");
    await expect(menu.getByRole("menuitem", { name: "Reply" })).toBeVisible();
    await expect(menu.getByRole("menuitem", { name: "Turn into a task" })).toHaveCount(0);
    await page.keyboard.press("Escape");
    await expect(menu).toHaveCount(0);

    const text = page.locator('[data-message-id="cards-2"]');
    await text.hover();
    await text.locator(".msg-more").click();
    await page.getByRole("menuitem", { name: "Turn into a task" }).click();
    const card = page.locator("[data-task-id]");
    await expect(card).toHaveCount(1);
    await expect(card.getByText("Task created", { exact: true })).toBeVisible();
    await expect(card.getByText(LONG, { exact: true })).toBeVisible();
    const id = await card.getAttribute("data-task-id");
    await page.reload();
    await expect(page.locator(`[data-task-id="${id}"]`)).toBeVisible();
    expect((await page.locator(".msg").last().getAttribute("data-message-id")) ?? "").toBe(
      `task:${id}`,
    );
    await page.getByRole("button", { name: "View task", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/app/tasks/${id}$`));
  } finally {
    await fixture.cleanup();
  }
});
