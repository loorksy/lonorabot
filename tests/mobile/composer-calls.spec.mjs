// The suggested reply, the chat's web-search switch, and «الرد برسالة» on an incoming call, as on Web.
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "../ui-test.mjs";

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

const words = {
  en: {
    message: "Message…",
    reply: "Reply",
    cancelReply: "Cancel reply",
    attach: "Attach file",
    webSearch: "Web search",
    webSearchOn: "Gathers sources before replying",
    globe: "Web search is on, tap to turn it off",
    turnedOff: "Web search turned off",
    answer: "Gold is at 2,425. Shall I add 0.05?",
    suggestion: "Yes, add 0.05",
  },
  ar: {
    message: "اكتب رسالة…",
    reply: "رد",
    cancelReply: "إلغاء الرد",
    attach: "إرفاق ملف",
    webSearch: "البحث في الويب",
    webSearchOn: "يجمع المصادر قبل الرد",
    globe: "البحث في الويب مفعّل، اضغط لإيقافه",
    turnedOff: "أُوقف البحث في الويب",
    answer: "الذهب عند 2,425. هل أضيف 0.05؟",
    suggestion: "نعم، أضف 0.05",
  },
};

for (const [locale, word] of Object.entries(words))
  test(`${locale}: the agent's suggested reply goes into the composer; web search is the chat's switch`, async ({
    page,
    context,
    cleanup,
  }) => {
    const data = await fixture(context);
    await context.addInitScript((value) => localStorage.setItem("lonora.locale", value), locale);
    const now = new Date().toISOString();
    const answer = {
      id: randomUUID(),
      thread_id: data.thread.id,
      agent_id: data.agent.id,
      role: "assistant",
      seq: 2,
      content: word.answer,
      suggested_reply: word.suggestion,
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
    cleanup(() => data.remove());
    await page.goto(`/thread?id=${data.thread.id}`);
    const chip = page.getByTestId("suggested-reply");
    await expect(chip).toHaveText(word.suggestion);
    await chip.click();
    await expect(page.getByRole("textbox", { name: word.message, exact: true })).toHaveValue(
      word.suggestion,
    );
    await expect(chip).toHaveCount(0);
    // As Web: the chip is back over an empty composer, and gone while a reply is set.
    await page.getByRole("textbox", { name: word.message, exact: true }).fill("");
    await expect(chip).toBeVisible();
    await page.getByText(word.answer, { exact: true }).click({ delay: 900 });
    await page.getByRole("button", { name: word.reply, exact: true }).click();
    await expect(chip).toHaveCount(0);
    await page.getByRole("button", { name: word.cancelReply }).click();
    await expect(chip).toBeVisible();

    await page.getByRole("button", { name: word.attach, exact: true }).click();
    await page.getByRole("switch", { name: word.webSearch }).click();
    await expect.poll(() => options.length).toBe(1);
    expect(options[0]).toEqual({ web_search: true });
    await expect(page.getByText(word.webSearchOn, { exact: true })).toBeVisible();

    // On, the globe beside «+» says so and turns it off, as Web's composer button.
    await page.route(`**/api/threads/${data.thread.id}`, async (route) =>
      route.fulfill({
        json: { ...(await (await route.fetch()).json()), options: { web_search: true } },
      }),
    );
    await page.reload();
    const globe = page.getByRole("button", { name: word.globe });
    await globe.click();
    await expect.poll(() => options.at(-1)).toEqual({ web_search: false });
    await expect(page.getByText(word.turnedOff, { exact: true })).toBeVisible();
    await expect(globe).toHaveCount(0);

    // Switched elsewhere (Web, another device), the globe follows the server's event.
    const csrf = (await context.cookies()).find((row) => row.name === "lonora_csrf").value;
    const headers = { "X-CSRF-Token": csrf };
    const path = `/api/threads/${data.thread.id}/options`;
    await context.request.put(path, { headers, data: { web_search: true } });
    await expect(globe).toBeVisible();
    await context.request.put(path, { headers, data: { web_search: false } });
    await expect(globe).toHaveCount(0);
  });

test("no suggested reply under a generated interface or while a run works, as on Web", async ({
  page,
  context,
  cleanup,
}) => {
  const data = await fixture(context);
  const now = new Date().toISOString();
  const plain = {
    id: randomUUID(),
    thread_id: data.thread.id,
    agent_id: data.agent.id,
    role: "assistant",
    seq: 2,
    content: "Gold is at 2,425.",
    suggested_reply: "Thanks",
    attachment_ids: [],
    reply_to: null,
    reactions: [],
    created_at: now,
  };
  const calculator = {
    ...plain,
    id: randomUUID(),
    content: "Try the calculator.",
    rich_content: {
      version: 1,
      parts: [
        { type: "text", text: "Try the calculator." },
        {
          type: "ui",
          document: {
            version: 1,
            mode: "example",
            state: { amount: 1000 },
            root: {
              id: "calculator",
              type: "column",
              children: [
                {
                  id: "amount",
                  type: "input",
                  label: "Example amount",
                  state_key: "amount",
                  input_kind: "number",
                  minimum: 100,
                  maximum: 10000,
                  step: 1,
                },
              ],
            },
          },
        },
      ],
    },
  };
  let messages = [calculator];
  let runs = [];
  await page.route(`**/api/threads/${data.thread.id}/messages*`, (route) =>
    route.fulfill({ json: messages }),
  );
  await page.route("**/api/runs?thread_id=*", (route) => route.fulfill({ json: runs }));
  const chip = page.getByTestId("suggested-reply");
  cleanup(() => data.remove());
  await page.goto(`/thread?id=${data.thread.id}`);
  await expect(page.getByText("Try the calculator.", { exact: true })).toBeVisible();
  await expect(chip).toHaveCount(0);

  // The same suggestion under a plain answer shows ...
  messages = [plain];
  await page.reload();
  await expect(chip).toHaveText("Thanks");

  // ... and not while a run works.
  runs = [
    {
      id: randomUUID(),
      thread_id: data.thread.id,
      agent_id: data.agent.id,
      parent_run_id: null,
      status: "running",
      trigger: "user",
      input_seq: 3,
      model_metadata: {},
      result: null,
      error_code: null,
      created_at: now,
      updated_at: now,
    },
  ];
  await page.reload();
  await expect(page.getByText("Gold is at 2,425.", { exact: true })).toBeVisible();
  await expect(chip).toHaveCount(0);
});

test("«Reply with a message» opens the agent's chat and the call steps aside", async ({
  page,
  context,
  cleanup,
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
  let ticks = 0;
  await page.route("**/api/voice/incoming", (route) => {
    ticks += 1;
    return route.fulfill({
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
    });
  });
  cleanup(() => data.remove());
  await page.goto("/");
  await expect(page.getByText("Gold broke 2,425", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Reply with a message", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`id=${data.thread.id}`));
  // The server still lists the call: two more polls, so the first one's answer is drawn.
  const seen = ticks;
  await expect.poll(() => ticks, { timeout: 10000 }).toBeGreaterThanOrEqual(seen + 2);
  await expect(page.getByText("Gold broke 2,425", { exact: true })).toHaveCount(0);
});

for (const [locale, typing] of [
  ["en", "is typing…"],
  ["ar", "يكتب…"],
])
  test(`${locale}: a group's header names the agent whose reply is running`, async ({
    page,
    context,
    cleanup,
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
    cleanup(async () => {
      await context.request.delete(`/api/groups/${group.id}`, { headers });
      await data.remove();
    });
    await page.goto(`/thread?id=${group.thread_id}`);
    await expect(page.getByTestId("thread-subtitle")).toHaveText(`${data.agent.name} ${typing}`);
  });
