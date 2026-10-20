import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

async function requestFixture(context) {
  const data = JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify({ action: "init" }),
      encoding: "utf8",
    }),
  );
  const headers = {
    "X-CSRF-Token": data.cookies.find((cookie) => cookie.name === "lonora_csrf").value,
  };
  await context.addCookies(
    data.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  const response = await context.request.post("/api/agents", {
    headers,
    data: {
      name: `Device review ${randomUUID()}`,
      trading_account_id: data.account,
      trading_symbol: data.symbol,
    },
  });
  expect(response.status()).toBe(201);
  const agent = await response.json();
  const thread = await (
    await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
  ).json();
  const goal = await (
    await context.request.post("/api/trading/goals", {
      headers,
      data: {
        agent_id: agent.id,
        thread_id: thread.id,
        account_id: data.account,
        symbol: data.symbol,
        title: "Device review plan",
        objective: "Review actual evidence without financial execution",
        maximum_volume: "0.1",
        max_trade_actions: 1,
        steps: [{ id: "review", title: "Read current broker evidence", kind: "analysis" }],
      },
    })
  ).json();
  const proposed = await context.request.post(`/api/agents/${agent.id}/super-bot/proposals`, {
    headers,
    data: { goal_id: goal.id, mode: "supervised" },
  });
  expect(proposed.status()).toBe(201);
  const request = await proposed.json();
  return {
    agent,
    thread,
    goal,
    request,
    cleanup: () => context.request.delete(`/api/agents/${agent.id}`, { headers }),
  };
}

for (const locale of ["ar", "en"]) {
  test(`Expo ${locale} uses a compact chat approval with details and durable rejection`, async ({
    page,
    context,
  }) => {
    const fixture = await requestFixture(context);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.addInitScript((value) => localStorage.setItem("lonora.locale", value), locale);
    const label = {
      review: locale === "ar" ? "مراجعة الخطة" : "Review plan",
      approve: locale === "ar" ? "موافقة" : "Approve",
      reject: locale === "ar" ? "رفض" : "Reject",
      question: locale === "ar" ? "تفعيل سوبر بوت؟" : "Activate Super Bot?",
      rejected: locale === "ar" ? "مرفوض" : "Rejected",
      close: locale === "ar" ? "إغلاق" : "Close",
    };
    try {
      await page.goto(`/thread?id=${fixture.thread.id}`);
      const card = page.getByTestId(`super-bot-card-${fixture.request.id}`);
      await expect(card.getByText(label.question, { exact: true })).toBeVisible();
      await expect(card.getByRole("button")).toHaveCount(3);
      await expect(card.getByRole("button", { name: label.approve, exact: true })).toBeVisible();
      await expect(card.getByRole("button", { name: label.reject, exact: true })).toBeVisible();
      await expect(card.getByText("Device review plan", { exact: true })).toHaveCount(0);
      await expect(page.getByRole("textbox", { name: /password|كلمة مرور/i })).toHaveCount(0);
      const dimensions = await card.boundingBox();
      expect(dimensions.width).toBeLessThanOrEqual(390);
      expect(dimensions.height).toBeLessThan(230);
      const approve = await card
        .getByRole("button", { name: label.approve, exact: true })
        .boundingBox();
      const reject = await card
        .getByRole("button", { name: label.reject, exact: true })
        .boundingBox();
      expect(Math.abs(approve.y - reject.y)).toBeLessThan(2);
      await card.getByRole("button", { name: label.review, exact: true }).click();
      const details = page.getByTestId(`super-bot-details-${fixture.request.id}`);
      await expect(details.getByText("Device review plan", { exact: true })).toBeVisible();
      await expect(
        details.getByText("Read current broker evidence", { exact: true }),
      ).toBeVisible();
      await details.getByRole("button", { name: label.close, exact: true }).click();
      await card.getByRole("button", { name: label.reject, exact: true }).click();
      await expect(card.getByText(label.rejected, { exact: true })).toBeVisible();
      await expect(card.getByRole("button", { name: label.approve, exact: true })).toHaveCount(0);
      await expect(card.getByRole("button", { name: label.reject, exact: true })).toHaveCount(0);
      await page.reload();
      await expect(card.getByText(label.rejected, { exact: true })).toBeVisible();
      const goal = await (
        await context.request.get(`/api/trading/goals/${fixture.goal.id}`)
      ).json();
      expect(goal.state.autonomous).toBe(false);
    } finally {
      await fixture.cleanup();
    }
  });
}

test("device enrollment is requested inside details with a labelled, clearable password", async ({
  page,
  context,
}) => {
  const fixture = await requestFixture(context);
  await page.addInitScript(() => {
    localStorage.setItem("lonora.locale", "en");
    // Exercising the actual server's registration-required path requires the
    // browser to advertise support; this does not create a credential or proof.
    if (!window.PublicKeyCredential) window.PublicKeyCredential = class {};
  });
  let verified = 0;
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/api/super-bot/verify") verified++;
  });
  try {
    await page.goto(`/thread?id=${fixture.thread.id}`);
    const card = page.getByTestId(`super-bot-card-${fixture.request.id}`);
    await card.getByRole("button", { name: "Approve", exact: true }).click();
    const details = page.getByTestId(`super-bot-details-${fixture.request.id}`);
    const password = details.getByLabel("Confirm account password", { exact: true });
    // Native/Web credential availability does not replace persisted registration.
    await expect(password).toBeVisible();
    await password.fill("do-not-send-this-cancelled-value");
    await details.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(password).toHaveCount(0);
    await details.getByRole("button", { name: "Register a passkey", exact: true }).click();
    await expect(password).toHaveValue("");
    expect(verified).toBe(0);
    const stored = await (
      await context.request.get(`/api/agents/${fixture.agent.id}/super-bot`)
    ).json();
    expect(stored.find((row) => row.id === fixture.request.id).status).toBe("pending");
  } finally {
    await fixture.cleanup();
  }
});

test("an older background snapshot cannot reopen a rejected activation request", async ({
  page,
  context,
}) => {
  const fixture = await requestFixture(context);
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  let heldRoute;
  let hold = true;
  let releaseWaiting;
  const waiting = new Promise((resolve) => {
    releaseWaiting = resolve;
  });
  try {
    await page.goto(`/thread?id=${fixture.thread.id}`);
    const card = page.getByTestId(`super-bot-card-${fixture.request.id}`);
    await expect(card.getByText("Activate Super Bot?", { exact: true })).toBeVisible();
    await page.route(`**/api/agents/${fixture.agent.id}/super-bot`, (route) => {
      if (hold) {
        hold = false;
        heldRoute = route;
        releaseWaiting();
        return;
      }
      return route.continue();
    });
    await waiting;
    await card.getByRole("button", { name: "Reject", exact: true }).click();
    await expect(card.getByText("Rejected", { exact: true })).toBeVisible();
    const oldSnapshot = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === `/api/agents/${fixture.agent.id}/super-bot`,
    );
    await heldRoute.fulfill({ json: [fixture.request] });
    heldRoute = undefined;
    await (await oldSnapshot).finished();
    await page.evaluate(
      () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
    );
    await expect(card.getByText("Rejected", { exact: true })).toBeVisible();
    await expect(card.getByRole("button", { name: "Approve", exact: true })).toHaveCount(0);
  } finally {
    if (heldRoute) await heldRoute.continue().catch(() => undefined);
    await fixture.cleanup();
  }
});
