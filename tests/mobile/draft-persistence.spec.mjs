// Composer drafts survive a restart (a reload of the Expo export), per conversation; an edit in
// progress does not come back as a new message.
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

async function fixture(context) {
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
  const headers = { "X-CSRF-Token": data.cookies.find((row) => row.name === "lonora_csrf").value };
  const create = async () => {
    const agent = await (
      await context.request.post("/api/agents", {
        headers,
        data: {
          name: `Draft ${randomUUID()}`,
          trading_account_id: data.account,
          trading_symbol: data.symbol,
        },
      })
    ).json();
    const thread = await (
      await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
    ).json();
    return { agent, thread };
  };
  return {
    create,
    remove: (id) => context.request.delete(`/api/agents/${id}`, { headers }),
  };
}

test("a draft comes back after a restart in its own conversation; an edit does not", async ({
  page,
  context,
}) => {
  const data = await fixture(context);
  const one = await data.create(),
    two = await data.create();
  const mine = {
    id: randomUUID(),
    thread_id: two.thread.id,
    agent_id: null,
    role: "user",
    seq: 1,
    content: "Buy gold at 2,400",
    attachment_ids: [],
    reply_to: null,
    reactions: [],
    created_at: new Date().toISOString(),
  };
  await page.route(`**/api/threads/${two.thread.id}/messages*`, (route) =>
    route.fulfill({ json: [mine] }),
  );
  try {
    const composer = page.getByRole("textbox", { name: "Message…", exact: true });
    await page.goto(`/thread?id=${one.thread.id}`);
    await composer.fill("Close half at 2,425 if it holds");
    await page.waitForTimeout(700);
    await page.reload();
    await expect(composer).toHaveValue("Close half at 2,425 if it holds");

    await page.goto(`/thread?id=${two.thread.id}`);
    await expect(composer).toHaveValue("");
    await page.getByText("Buy gold at 2,400", { exact: true }).click({ delay: 900 });
    await page.getByRole("button", { name: "Edit and resend", exact: true }).click();
    await expect(composer).toHaveValue("Buy gold at 2,400");
    await page.waitForTimeout(700);
    await page.reload();
    await expect(page.getByText("Buy gold at 2,400", { exact: true })).toBeVisible();
    await expect(composer).toHaveValue("");
  } finally {
    await data.remove(one.agent.id);
    await data.remove(two.agent.id);
  }
});
