// The suggested reply, the chat's web-search switch, and «الرد برسالة» on an incoming call, as on Web.
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
      name: `Composer ${randomUUID()}`,
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

test("the agent's suggested reply goes into the composer; web search is the chat's switch", async ({
  page,
  context,
}) => {
  const data = await fixture(context);
  const now = new Date().toISOString();
  const answer = {
    id: randomUUID(),
    thread_id: data.thread.id,
    agent_id: data.agent.id,
    role: "assistant",
    seq: 2,
    content: "Gold is at 2,425. Shall I add 0.05?",
    suggested_reply: "Yes, add 0.05",
    attachment_ids: [],
    reply_to: null,
    reactions: [],
    created_at: now,
  };
  await page.route(`**/api/threads/${data.thread.id}/messages*`, (route) =>
    route.fulfill({ json: [answer] }),
  );
  const options = [];
  await page.route(`**/api/threads/${data.thread.id}/options`, (route) => {
    const body = route.request().postDataJSON();
    options.push(body);
    return route.fulfill({ json: { ...data.thread, options: body } });
  });
  try {
    await page.goto(`/thread?id=${data.thread.id}`);
    const chip = page.getByTestId("suggested-reply");
    await expect(chip).toHaveText("Yes, add 0.05");
    await chip.click();
    await expect(page.getByRole("textbox", { name: "Message…", exact: true })).toHaveValue(
      "Yes, add 0.05",
    );
    await expect(chip).toHaveCount(0);
    // As Web: the chip is back over an empty composer, and gone while a reply is set.
    await page.getByRole("textbox", { name: "Message…", exact: true }).fill("");
    await expect(chip).toBeVisible();
    await page
      .getByText("Gold is at 2,425. Shall I add 0.05?", { exact: true })
      .click({ delay: 900 });
    await page.getByRole("button", { name: "Reply", exact: true }).click();
    await expect(chip).toHaveCount(0);
    await page.getByRole("button", { name: "Cancel reply" }).click();
    await expect(chip).toBeVisible();

    await page.getByRole("button", { name: "Attach file", exact: true }).click();
    await page.getByRole("switch", { name: "Web search" }).click();
    await expect.poll(() => options.length).toBe(1);
    expect(options[0]).toEqual({ web_search: true });
    await expect(page.getByText("Gathers sources before replying", { exact: true })).toBeVisible();

    // On, the globe beside «+» says so and turns it off, as Web's composer button.
    await page.route(`**/api/threads/${data.thread.id}`, async (route) =>
      route.fulfill({
        json: { ...(await (await route.fetch()).json()), options: { web_search: true } },
      }),
    );
    await page.reload();
    const globe = page.getByRole("button", { name: "Web search is on, tap to turn it off" });
    await globe.click();
    await expect.poll(() => options.at(-1)).toEqual({ web_search: false });
    await expect(page.getByText("Web search turned off", { exact: true })).toBeVisible();
    await expect(globe).toHaveCount(0);
  } finally {
    await data.remove();
  }
});

test("«Reply with a message» opens the agent's chat and the call steps aside", async ({
  page,
  context,
}) => {
  const data = await fixture(context);
  await page.route("**/api/voice/incoming/policy", (route) =>
    route.fulfill({
      json: {
        channel: "call",
        enabled: true,
        device_id: "device-1",
        opportunities: true,
        action_required: true,
        critical: true,
        timezone: "UTC",
        quiet_start_hour: null,
        quiet_end_hour: null,
      },
    }),
  );
  await page.route("**/api/voice/incoming", (route) =>
    route.fulfill({
      json: [
        {
          id: "call-1",
          agent_id: data.agent.id,
          thread_id: data.thread.id,
          status: "ringing",
          reason: "Gold broke 2,425",
          expires_at: new Date(Date.now() + 120000).toISOString(),
          version: 1,
          execution_authorized: false,
        },
      ],
    }),
  );
  try {
    await page.goto("/");
    await expect(page.getByText("Gold broke 2,425", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Reply with a message", exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`id=${data.thread.id}`));
    await page.waitForTimeout(3500);
    await expect(page.getByText("Gold broke 2,425", { exact: true })).toHaveCount(0);
  } finally {
    await data.remove();
  }
});

for (const [locale, typing] of [
  ["en", "is typing…"],
  ["ar", "يكتب…"],
])
  test(`${locale}: a group's header names the agent whose reply is running`, async ({
    page,
    context,
  }) => {
    const data = await fixture(context);
    await context.addInitScript((value) => localStorage.setItem("lonora.locale", value), locale);
    const csrf = (await context.cookies()).find((row) => row.name === "lonora_csrf").value;
    const headers = { "X-CSRF-Token": csrf };
    const group = await (
      await context.request.post("/api/groups/create", {
        headers,
        data: {
          name: `Typing ${randomUUID()}`,
          member_ids: [data.agent.id],
          participation: "mentions_or_lead",
        },
      })
    ).json();
    const now = new Date().toISOString();
    await page.route("**/api/runs?thread_id=*", (route) =>
      route.fulfill({
        json: [
          {
            id: randomUUID(),
            thread_id: group.thread_id,
            agent_id: data.agent.id,
            parent_run_id: null,
            status: "running",
            trigger: "user",
            input_seq: 1,
            model_metadata: {},
            result: null,
            error_code: null,
            created_at: now,
            updated_at: now,
          },
        ],
      }),
    );
    try {
      await page.goto(`/thread?id=${group.thread_id}`);
      await expect(page.getByTestId("thread-subtitle")).toHaveText(`${data.agent.name} ${typing}`);
    } finally {
      await context.request.delete(`/api/groups/${group.id}`, { headers });
      await data.remove();
    }
  });
