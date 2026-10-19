import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

async function conversation(context) {
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
  const response = await context.request.post("/api/agents", {
    headers,
    data: {
      name: `Reliability ${randomUUID()}`,
      trading_account_id: fixture.account,
      trading_symbol: fixture.symbol,
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

test("inbox distinguishes pending hydration from empty and shows canonical message preview", async ({
  page,
  context,
}) => {
  const data = await conversation(context);
  let release;
  const loading = new Promise((resolve) => {
    release = resolve;
  });
  await page.route("**/api/threads/inbox", async (route) => {
    await loading;
    await route.fulfill({
      json: [
        {
          thread_id: data.thread.id,
          agent_id: data.agent.id,
          group_id: null,
          last_message: {
            id: "latest",
            seq: 1,
            role: "assistant",
            content: "آخر تحديث حقيقي XAUUSDm",
            created_at: "2026-10-15T14:00:00Z",
          },
          last_activity_at: "2026-10-15T14:00:00Z",
        },
      ],
    });
  });
  try {
    await page.goto("/");
    await expect(page.getByText(data.agent.name, { exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "وكيل جديد", exact: true })).toHaveCount(0);
    release();
    await expect(page.getByText("آخر تحديث حقيقي XAUUSDm", { exact: true })).toBeVisible();
    await expect(page.getByText(data.agent.name, { exact: true })).toBeVisible();
  } finally {
    release();
    await data.remove();
  }
});

test("native timeline opens latest, preserves history reading and keeps approvals before subsequent output", async ({
  page,
  context,
}) => {
  const data = await conversation(context);
  const messages = Array.from({ length: 100 }, (_, i) => ({
    id: `message-${i + 1}`,
    seq: i + 1,
    thread_id: data.thread.id,
    agent_id: data.agent.id,
    role: "assistant",
    attachment_ids: [],
    reply_to: null,
    content: `رسالة ${i + 1} ${"تحليل السوق الموثق. ".repeat(12)}`,
    created_at: new Date(Date.UTC(2026, 9, 15, 12, 0, i)).toISOString(),
  }));
  const approval = {
    id: randomUUID(),
    thread_id: data.thread.id,
    agent_id: data.agent.id,
    run_id: "run",
    timeline_seq: 100,
    created_at: messages[99].created_at,
    status: "pending",
    requests: [{ action: "buy", symbol: "EURUSDm", volume: "0.01" }],
    results: [],
  };
  await page.route(`**/api/threads/${data.thread.id}/messages*`, (route) =>
    route.fulfill({ json: messages }),
  );
  await page.route("**/api/trading/approvals?*", (route) => route.fulfill({ json: [approval] }));
  await page.route(`**/api/trading/approvals/${approval.id}/decision`, (route) => {
    approval.status = "rejected";
    return route.fulfill({ json: approval });
  });
  try {
    await page.goto(`/thread?id=${data.thread.id}`);
    const transcript = page.getByTestId("conversation-transcript");
    const newest = page.getByText(messages[99].content, { exact: true });
    await expect(newest).toBeInViewport();
    await page.getByRole("button", { name: "رفض", exact: true }).click();
    await expect(page.getByText("مرفوض", { exact: true })).toBeVisible();
    const approvalY = await page.getByText("buy · EURUSDm", { exact: false }).boundingBox();
    const newestY = await newest.boundingBox();
    expect(newestY.y).toBeGreaterThan(approvalY.y);
    await transcript.evaluate((element) => {
      element.scrollTop = 700;
    });
    await expect(
      page.getByRole("button", { name: "انتقل إلى أحدث رسالة", exact: true }),
    ).toBeVisible();
    messages.push({
      ...messages[99],
      id: "message-101",
      seq: 101,
      content: "رد جديد بعد قرار المالك",
      created_at: "2026-10-15T12:02:00Z",
    });
    await page.waitForTimeout(2800);
    await expect(
      page.getByRole("button", { name: "انتقل إلى أحدث رسالة", exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "انتقل إلى أحدث رسالة", exact: true }).click();
    await expect(page.getByText("رد جديد بعد قرار المالك", { exact: true })).toBeInViewport();
    await expect(
      page.getByRole("button", { name: "انتقل إلى أحدث رسالة", exact: true }),
    ).toHaveCount(0);
  } finally {
    await data.remove();
  }
});

test("return navigation retains confirmed messages while revalidation is delayed", async ({
  page,
  context,
}) => {
  const data = await conversation(context);
  let blocked = false;
  let release;
  const waiting = new Promise((resolve) => {
    release = resolve;
  });
  let releaseArtifacts;
  const artifactsReady = new Promise((resolve) => {
    releaseArtifacts = resolve;
  });
  await page.route(`**/api/artifacts?thread_id=${data.thread.id}`, async (route) => {
    await artifactsReady;
    await route.fulfill({ json: [] });
  });
  const messages = [
    {
      id: "retained-message",
      seq: 1,
      thread_id: data.thread.id,
      agent_id: data.agent.id,
      role: "assistant",
      content: "رسالة محفوظة أثناء التنقل",
      attachment_ids: [],
      reply_to: null,
      created_at: "2026-10-19T12:00:00Z",
    },
  ];
  await page.route(`**/api/threads/${data.thread.id}/messages*`, async (route) => {
    if (blocked) await waiting;
    await route.fulfill({ json: messages });
  });
  try {
    await page.goto("/");
    await page.getByText(data.agent.name, { exact: true }).click();
    await expect(page.getByText(messages[0].content, { exact: true })).toBeVisible();
    releaseArtifacts();
    await page.getByRole("button", { name: "إعدادات الوكيل", exact: true }).click();
    await expect(page).toHaveURL(/bot-settings/);
    blocked = true;
    await page.getByRole("button", { name: "رجوع", exact: true }).click();
    await expect(page.getByText(messages[0].content, { exact: true })).toBeVisible();
    messages.push({
      ...messages[0],
      id: "after-return",
      seq: 2,
      content: "تحديث حقيقي بعد العودة",
    });
    release();
    await expect(page.getByText(messages[1].content, { exact: true })).toBeVisible();
  } finally {
    releaseArtifacts();
    release();
    await data.remove();
  }
});
