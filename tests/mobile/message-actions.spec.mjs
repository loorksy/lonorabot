// The message menu on mobile, as on Web: a long press opens the six quick reactions and the
// message's actions (reply, copy, edit and resend, turn into a task); a failed message offers
// retry and delete; reactions show under the bubble and the owner's own one is removed by a tap.
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
  const response = await context.request.post("/api/agents", {
    headers,
    data: {
      name: `Menu ${randomUUID()}`,
      trading_account_id: data.account,
      trading_symbol: data.symbol,
    },
  });
  expect(response.status()).toBe(201);
  const agent = await response.json();
  const thread = await (
    await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
  ).json();
  return {
    agent,
    thread,
    remove: () => context.request.delete(`/api/agents/${agent.id}`, { headers }),
  };
}
const message = (data, fields) => ({
  id: randomUUID(),
  thread_id: data.thread.id,
  agent_id: null,
  role: "user",
  seq: 1,
  content: "",
  attachment_ids: [],
  reply_to: null,
  reactions: [],
  created_at: new Date().toISOString(),
  ...fields,
});
const longPress = (locator) => locator.click({ delay: 900 });

test("a long press opens reactions and actions; edit resends with edited_from; a task is created", async ({
  page,
  context,
}) => {
  test.setTimeout(60000);
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  const data = await fixture(context);
  const mine = message(data, { content: "Buy gold at 2,400" });
  const answer = message(data, {
    role: "assistant",
    agent_id: data.agent.id,
    seq: 2,
    content: "Bought 0.10 gold at 2,400.",
    reply_to: mine.id,
  });
  const saved = [mine, answer];
  const posted = [],
    reacted = [],
    tasks = [];
  await page.route(`**/api/threads/${data.thread.id}/messages`, async (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: saved });
    const body = route.request().postDataJSON();
    posted.push(body);
    const sent = message(data, {
      seq: 3,
      content: body.content,
      client_nonce: body.client_nonce,
      edited_from: body.edited_from ?? null,
    });
    saved.push(sent);
    return route.fulfill({ status: 202, json: { message: sent, run_ids: [], runs: [] } });
  });
  await page.route(`**/api/threads/${data.thread.id}/messages/*/reactions**`, async (route) => {
    const method = route.request().method();
    reacted.push([method, decodeURIComponent(route.request().url().split("/").pop())]);
    const reactions =
      method === "PUT"
        ? [{ reactor: "owner", emoji: "❤️", created_at: new Date().toISOString() }]
        : [];
    return route.fulfill({ json: { message_id: answer.id, reactions } });
  });
  await page.route("**/api/tasks?*", async (route) => {
    tasks.push([route.request().url(), route.request().postDataJSON()]);
    return route.fulfill({ status: 201, json: { id: randomUUID(), title: "t" } });
  });
  try {
    await page.goto(`/thread?id=${data.thread.id}`);
    await expect(page.getByTestId("conversation-transcript")).toBeVisible();

    // Reactions: the menu's quick reaction, the chip under the bubble, removal from the list.
    await longPress(page.getByText("Bought 0.10 gold at 2,400.", { exact: true }));
    await expect(page.getByText("Message options", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Edit and resend" })).toHaveCount(0);
    await page.getByRole("button", { name: "React ❤️", exact: true }).click();
    const chips = page.getByTestId("message-reactions");
    await expect(chips).toContainText("❤️");
    await chips.click();
    await expect(page.getByText("Tap to remove", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "You", exact: true }).click();
    await expect(chips).toHaveCount(0);
    expect(reacted).toEqual([
      ["PUT", "❤️"],
      ["DELETE", "reactions"],
    ]);

    // Copy text.
    await longPress(page.getByText("Bought 0.10 gold at 2,400.", { exact: true }));
    await page.getByRole("button", { name: "Copy text", exact: true }).click();
    await expect(page.getByText("Copied", { exact: true })).toBeVisible();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(
      "Bought 0.10 gold at 2,400.",
    );

    // Turn into a task.
    await longPress(page.getByText("Bought 0.10 gold at 2,400.", { exact: true }));
    await page.getByRole("button", { name: "Turn into a task", exact: true }).click();
    await expect(page.getByText("Task created", { exact: true })).toBeVisible();
    expect(tasks).toHaveLength(1);
    expect(tasks[0][0]).toContain(`agent_id=${data.agent.id}`);
    expect(tasks[0][0]).toContain(`thread_id=${data.thread.id}`);
    expect(tasks[0][1]).toEqual({
      title: "Bought 0.10 gold at 2,400.",
      description: "Bought 0.10 gold at 2,400.",
    });

    // Edit and resend: the owner's own text comes back into the composer and replaces it.
    await longPress(page.getByText("Buy gold at 2,400", { exact: true }).last());
    await page.getByRole("button", { name: "Edit and resend", exact: true }).click();
    const composer = page.getByRole("textbox", { name: "Message…", exact: true });
    await expect(composer).toHaveValue("Buy gold at 2,400");
    await expect(page.getByText("Edit the message", { exact: true })).toBeVisible();
    await composer.fill("Buy gold at 2,395");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0].edited_from).toBe(mine.id);
    expect(posted[0].reply_to).toBeNull();
    await expect(page.getByText("Edit the message", { exact: true })).toHaveCount(0);
  } finally {
    await data.remove();
  }
});

test("a failed message offers retry and delete; delete drops it from the device", async ({
  page,
  context,
}) => {
  const data = await fixture(context);
  await page.route(`**/api/threads/${data.thread.id}/messages`, async (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: [] });
    return route.fulfill({ status: 422, json: { code: "message_rejected" } });
  });
  try {
    await page.goto(`/thread?id=${data.thread.id}`);
    const composer = page.getByRole("textbox", { name: "Message…", exact: true });
    await composer.fill("Never arrives");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(page.getByText("Message not sent", { exact: true })).toBeVisible();
    await longPress(page.getByText("Never arrives", { exact: true }));
    await expect(page.getByText("The message was not sent", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Retry", exact: true }).last()).toBeVisible();
    await page.getByRole("button", { name: "Delete", exact: true }).click();
    await expect(page.getByText("Never arrives", { exact: true })).toHaveCount(0);
    await page.reload();
    await expect(page.getByTestId("conversation-transcript")).toBeVisible();
    await expect(page.getByText("Never arrives", { exact: true })).toHaveCount(0);
  } finally {
    await data.remove();
  }
});

test("a tap on a quoted message rests the list on it", async ({ page, context }) => {
  const data = await fixture(context);
  const first = message(data, { content: "Where is support?" });
  const rows = [first];
  for (let seq = 2; seq < 40; seq++)
    rows.push(
      message(data, {
        role: "assistant",
        agent_id: data.agent.id,
        seq,
        content: `Line ${seq}`,
      }),
    );
  rows.push(
    message(data, {
      role: "assistant",
      agent_id: data.agent.id,
      seq: 40,
      content: "Support is at 2,380.",
      reply_to: first.id,
    }),
  );
  await page.route(`**/api/threads/${data.thread.id}/messages*`, (route) =>
    route.fulfill({ json: rows }),
  );
  try {
    await page.goto(`/thread?id=${data.thread.id}`);
    await expect(page.getByText("Support is at 2,380.", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Reply: Where is support?", exact: true }).click();
    await expect(page).toHaveURL(/around=1/);
    // The quoted message's neighbourhood is on screen; the newest answer has scrolled away.
    await expect(page.getByText("Line 2", { exact: true })).toBeInViewport();
    await expect(page.getByText("Support is at 2,380.", { exact: true })).not.toBeInViewport();
  } finally {
    await data.remove();
  }
});

test("a failed reply offers Retry once; the retry names it and the banner settles", async ({
  page,
  context,
}) => {
  const data = await fixture(context);
  const now = new Date().toISOString();
  const failed = {
    id: randomUUID(),
    thread_id: data.thread.id,
    agent_id: data.agent.id,
    parent_run_id: null,
    status: "failed",
    trigger: "user",
    input_seq: 1,
    model_metadata: {},
    result: null,
    error_code: "provider_unavailable",
    created_at: now,
    updated_at: now,
  };
  const runs = [failed];
  const retried = [];
  await page.route("**/api/runs?thread_id=*", (route) => route.fulfill({ json: runs }));
  await page.route(`**/api/runs/${failed.id}/retry`, (route) => {
    retried.push(failed.id);
    const next = {
      ...failed,
      id: randomUUID(),
      status: "queued",
      error_code: null,
      model_metadata: { retry_of: failed.id },
    };
    runs.push(next);
    return route.fulfill({ status: 202, json: next });
  });
  try {
    await page.goto(`/thread?id=${data.thread.id}`);
    const retry = page.getByRole("button", { name: "Retry", exact: true });
    await expect(retry).toBeVisible();
    await retry.click();
    await expect.poll(() => retried.length).toBe(1);
    await expect(retry).toHaveCount(0);
  } finally {
    await data.remove();
  }
});

test("a failed background run stays out of the banner (11.5); a failed peer run shows without Retry", async ({
  page,
  context,
}) => {
  const data = await fixture(context);
  const now = new Date().toISOString();
  const failed = {
    id: randomUUID(),
    thread_id: data.thread.id,
    agent_id: data.agent.id,
    parent_run_id: null,
    status: "failed",
    trigger: "routine",
    background: true,
    input_seq: null,
    model_metadata: {},
    result: null,
    error_code: "model_credentials_rejected",
    created_at: now,
    updated_at: now,
  };
  // Work another agent asked for is not background: its failure still shows.
  const peer = {
    ...failed,
    id: randomUUID(),
    trigger: "peer",
    background: false,
    error_code: "model_provider_unavailable",
  };
  await page.route("**/api/runs?thread_id=*", (route) => route.fulfill({ json: [failed, peer] }));
  try {
    await page.goto(`/thread?id=${data.thread.id}`);
    await expect(page.getByText(/The model provider is unavailable right now/)).toBeVisible();
    await expect(page.getByText(/The provider rejected this API key/)).toHaveCount(0);
    await expect(page.getByText(/· Failed/)).toHaveCount(1);
    await expect(page.getByRole("button", { name: "Retry", exact: true })).toHaveCount(0);
  } finally {
    await data.remove();
  }
});
