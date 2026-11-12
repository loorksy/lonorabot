// The composer's / commands on mobile, as on Web: «/» lists the chat's commands; a task or a
// search is sent as the owner's text with its command; «summary» goes at once; «clear» asks,
// then clears; a task without a title is not sent; a sent command shows its chip.
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
  const agent = await (
    await context.request.post("/api/agents", {
      headers,
      data: {
        name: `Commands ${randomUUID()}`,
        trading_account_id: data.account,
        trading_symbol: data.symbol,
      },
    })
  ).json();
  const thread = await (
    await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
  ).json();
  return {
    agent,
    thread,
    remove: () => context.request.delete(`/api/agents/${agent.id}`, { headers }),
  };
}

test("«/» lists the commands; a task is sent with its command; summary goes at once; clear asks first", async ({
  page,
  context,
}) => {
  test.setTimeout(60000);
  const data = await fixture(context);
  const saved = [
    {
      id: randomUUID(),
      thread_id: data.thread.id,
      agent_id: null,
      role: "user",
      seq: 1,
      content: "/search gold news",
      attachment_ids: [],
      reply_to: null,
      reactions: [],
      created_at: new Date().toISOString(),
      rich_content: {
        version: 1,
        parts: [{ type: "command", name: "search", argument: "gold news" }],
      },
    },
  ];
  const posted = [];
  let cleared = 0;
  await page.route(`**/api/threads/${data.thread.id}/messages`, async (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: cleared ? [] : saved });
    posted.push(route.request().postDataJSON());
    return route.fulfill({ status: 503, json: { code: "request_failed" } });
  });
  await page.route(`**/api/threads/${data.thread.id}/clear`, (route) => {
    cleared += 1;
    return route.fulfill({
      json: {
        thread_id: data.thread.id,
        agent_id: data.agent.id,
        group_id: null,
        last_message: null,
        unread_count: 0,
        last_read_seq: 0,
        pinned_order: null,
        muted: false,
        archived: false,
        favourite: false,
        marked_unread: false,
      },
    });
  });
  await page.route("**/api/skills?agent_id=*", (route) =>
    route.fulfill({
      json: [{ id: "skill-1", payload: { name: "gold review", enabled: true } }],
    }),
  );
  try {
    await page.goto(`/thread?id=${data.thread.id}`);
    // A sent command shows its chip.
    await expect(page.getByTestId("command-chip")).toHaveText("/search");
    const composer = page.getByRole("textbox", { name: "Message…", exact: true });
    await composer.fill("/");
    const list = page.getByRole("list", { name: "Commands" });
    for (const name of ["task", "search", "summary", "chart", "call", "clear", "gold review"])
      await expect(list.getByRole("button", { name: `/${name}`, exact: true })).toBeVisible();

    // A task without its title is not sent.
    await composer.fill("/task");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(page.getByText(/Write the task title after/)).toBeVisible();
    expect(posted).toHaveLength(0);

    // Picked from the list, then sent with its title.
    await composer.fill("/ta");
    await list.getByRole("button", { name: "/task", exact: true }).click();
    await expect(composer).toHaveValue("/task ");
    await composer.fill("/task watch 2,425 tonight");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0].content).toBe("/task watch 2,425 tonight");
    expect(posted[0].command).toEqual({ name: "task", argument: "watch 2,425 tonight" });

    // A skill carries its id.
    await composer.fill("/gold review today");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect.poll(() => posted.length).toBe(2);
    expect(posted[1].command).toEqual({ name: "skill", argument: "today", skill_id: "skill-1" });

    // «summary» goes at once.
    await composer.fill("/sum");
    await list.getByRole("button", { name: "/summary", exact: true }).click();
    await expect.poll(() => posted.length).toBe(3);
    expect(posted[2].command).toEqual({ name: "summary", argument: "" });
    await expect(composer).toHaveValue("");

    // «clear» asks first, says what it does, and can be cancelled.
    await composer.fill("/cl");
    await list.getByRole("button", { name: "/clear", exact: true }).click();
    await expect(page.getByText("Clear the messages?", { exact: true })).toBeVisible();
    await expect(page.getByText(/hidden for you/)).toBeVisible();
    await page.getByRole("button", { name: "Cancel", exact: true }).click();
    expect(cleared).toBe(0);
    await composer.fill("/clear");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await page.getByRole("button", { name: "Clear", exact: true }).click();
    await expect.poll(() => cleared).toBe(1);
    // The cleared history does not come back (the unsent commands of this test stay on the
    // device, failed, as any unsent message does).
    await expect(page.getByText("/search gold news", { exact: true })).toHaveCount(0);
  } finally {
    await data.remove();
  }
});
