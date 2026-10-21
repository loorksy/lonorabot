// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: Playwright runs directly without Turborepo caching.
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { brokerFixture } from "../web/broker-fixture.mjs";

test("Expo profile, routines, groups and authenticated artifacts use the persistent server", async ({
  page,
  context,
}) => {
  test.setTimeout(90_000);
  const prefix = `Expo regression ${randomUUID()}`;
  const owned = {
    agents: new Set(),
    groups: new Set(),
    routines: new Set(),
    charts: new Set(),
    artifacts: new Set(),
  };
  const credentials = {
    email: process.env.LONORA_UI_TEST_EMAIL ?? "ci@example.com",
    password: process.env.LONORA_UI_TEST_PASSWORD ?? "ci-only-owner-password",
  };
  const status = await (await context.request.get("/api/onboarding")).json();
  if (!status.owner_initialized) {
    const result = await context.request.post("/api/onboarding", {
      data: {
        ...credentials,
        bootstrap_token: process.env.LONORA_BOOTSTRAP_TOKEN ?? "lonora-ui-bootstrap-ci-only-2026",
      },
    });
    expect(result.status()).toBe(201);
  }
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  let headers;
  let chartFixture;
  let broker;
  try {
    await page.goto("/");
    await page
      .getByRole("textbox", { name: "البريد الإلكتروني", exact: true })
      .fill(credentials.email);
    await page.getByLabel("كلمة المرور", { exact: true }).fill(credentials.password);
    const loggedIn = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/auth/login") && response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "تسجيل الدخول", exact: true }).click();
    headers = { "X-CSRF-Token": (await (await loggedIn).json()).csrf };
    broker = await brokerFixture(context, headers);
    await expect(page.getByRole("button", { name: "إنشاء", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "ابحث عن وكيل أو مجموعة", exact: true }).click();
    await expect(
      page.getByRole("textbox", { name: "ابحث عن وكيل أو مجموعة", exact: true }),
    ).toBeVisible();
    expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toMatch(
      /Bearer|"token"|"session"/,
    );
    await page.getByRole("button", { name: "إنشاء", exact: true }).click();
    await page.getByRole("menu").getByRole("button", { name: "وكيل جديد", exact: true }).click();
    await page.getByLabel("الاسم", { exact: true }).fill(prefix);
    await page.getByLabel("الدور", { exact: true }).fill("Portfolio review");
    await page
      .getByLabel("الوصف", { exact: true })
      .fill("Monitor positions and summarize market data.");
    await page.getByRole("button", { name: "اختر حساب الوسيط", exact: true }).click();
    await page.getByTestId(`broker-choice-${broker.account}`).click();
    await page.getByRole("button", { name: "اختر زوج التداول", exact: true }).click();
    await page.getByRole("button", { name: broker.symbol, exact: true }).click();
    const created = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/agents") && response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "إنشاء", exact: true }).click();
    const agent = await (await created).json();
    owned.agents.add(agent.id);
    expect(agent.title).toBe("Portfolio review");
    expect(agent.description).toContain("market data");
    await expect(page.getByLabel("اكتب رسالة…", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "اتصل بالوكيل", exact: true })).toBeVisible();
    const threadUrl = page.url();
    await page.getByRole("button", { name: "إعدادات الوكيل", exact: true }).click();
    const shadow = page.getByRole("switch", {
      name: "تداول ظلي — أوامر افتراضية فقط",
      exact: true,
    });
    await expect(shadow).not.toBeChecked();
    await shadow.click();
    await expect(shadow).toBeChecked();
    await expect
      .poll(async () => {
        const rows = await (await context.request.get("/api/agents")).json();
        return rows.find((row) => row.id === agent.id).execution_mode;
      })
      .toBe("shadow");
    await page
      .getByLabel("التعليمات", { exact: true })
      .fill("Review spreads and current positions before proposing trades.");
    await page
      .getByLabel("الذاكرة الدائمة", { exact: true })
      .fill("Prefer daily portfolio reviews.");
    await page.getByRole("button", { name: "حفظ", exact: true }).click();
    await expect(page.getByText("تم الحفظ", { exact: true })).toBeVisible();
    expect(
      (await (await context.request.get(`/api/agents/${agent.id}/memory`)).json()).content,
    ).toContain("daily portfolio");
    await page.getByRole("button", { name: "رجوع", exact: true }).click();
    await page.getByRole("button", { name: "إجراءات الوكيل", exact: true }).click();
    await page.getByRole("button", { name: "المهام المجدولة", exact: true }).click();
    await page.getByRole("button", { name: "إنشاء", exact: true }).click();
    await page.getByLabel("المهمة", { exact: true }).fill(`${prefix} market review`);
    await page.getByLabel("كل · دقائق", { exact: true }).fill("17");
    const scheduled = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/api/routines/${agent.id}`) &&
        response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "حفظ", exact: true }).click();
    const routine = await (await scheduled).json();
    owned.routines.add(routine.id);
    expect(routine.interval_seconds).toBe(1020);
    await page.getByRole("button", { name: "سجل التنفيذ", exact: true }).click();
    await expect(page.getByText("لا يوجد تنفيذ بعد", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "رجوع", exact: true }).click();
    await expect(page).toHaveURL(threadUrl);
    const chooser = page.waitForEvent("filechooser");
    await page.getByRole("button", { name: "إرفاق ملف", exact: true }).click();
    const filename = `report-${agent.id}.txt`;
    const uploaded = page.waitForResponse((response) =>
      response.url().endsWith("/api/artifacts/upload"),
    );
    await (await chooser).setFiles({
      name: filename,
      mimeType: "text/plain",
      buffer: Buffer.from("Persistent trading review"),
    });
    const artifact = await (await uploaded).json();
    owned.artifacts.add(artifact.id);
    const content = `${prefix} durable attachment message`;
    await page.getByLabel("اكتب رسالة…", { exact: true }).fill(content);
    const threadId = new URL(threadUrl).searchParams.get("id");
    let firstReceipt;
    const nonces = [];
    const lostResponse = async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      nonces.push(route.request().postDataJSON().client_nonce);
      firstReceipt = await (await route.fetch()).json();
      await route.abort("failed");
    };
    const messagePath = `**/api/threads/${threadId}/messages`;
    await page.route(messagePath, lostResponse);
    const transportFailure = page.waitForEvent("requestfailed", {
      predicate: (request) =>
        request.method() === "POST" && request.url().endsWith(`/threads/${threadId}/messages`),
    });
    await page.getByRole("button", { name: "إرسال", exact: true }).click();
    await transportFailure;
    await expect(page.getByRole("button", { name: "إرسال", exact: true })).toBeEnabled();
    expect(firstReceipt.message.attachment_ids).toContain(artifact.id);
    await page.unroute(messagePath, lostResponse);
    const retried = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url().endsWith(`/threads/${threadId}/messages`),
    );
    await page.getByRole("button", { name: "إرسال", exact: true }).click();
    const retryResponse = await retried;
    nonces.push(retryResponse.request().postDataJSON().client_nonce);
    const retryReceipt = await retryResponse.json();
    expect(retryReceipt.deduplicated).toBe(true);
    expect(retryReceipt.message.id).toBe(firstReceipt.message.id);
    expect(nonces[0]).toBe(nonces[1]);
    expect(
      (await (await context.request.get(`/api/threads/${threadId}/messages`)).json()).filter(
        (row) => row.content === content,
      ),
    ).toHaveLength(1);
    await page.goto("/");
    await page.getByRole("button", { name: prefix, exact: true }).click();
    await expect(page).toHaveURL(threadUrl);
    await expect(
      page.getByTestId("conversation-transcript").getByText(content, { exact: true }),
    ).toBeVisible();
    await page
      .getByTestId("conversation-transcript")
      .getByText(content, { exact: true })
      .click({ delay: 650 });
    await expect(page.getByRole("button", { name: "إلغاء الرد", exact: true })).toBeVisible();
    await page.getByLabel("اكتب رسالة…", { exact: true }).fill("A reply to the persistent message");
    const replying = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url().endsWith(`/threads/${threadId}/messages`),
    );
    await page.getByRole("button", { name: "إرسال", exact: true }).click();
    expect((await (await replying).json()).message.reply_to).toBe(firstReceipt.message.id);
    await page.getByRole("button", { name: "إجراءات الوكيل", exact: true }).click();
    await page.getByRole("button", { name: "الملفات", exact: true }).click();
    await page.getByRole("button", { name: filename, exact: true }).click();
    await expect(page.getByText("Persistent trading review", { exact: true })).toBeVisible();
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "تنزيل", exact: true }).click();
    expect((await download).suggestedFilename()).toBe(filename);
    await page.goto("/new-group");
    await page.getByLabel("الاسم", { exact: true }).fill(`${prefix} team`);
    await page.getByRole("checkbox", { name: prefix, exact: true }).click();
    const grouped = page.waitForResponse((response) =>
      response.url().endsWith("/api/groups/create"),
    );
    await page.getByRole("button", { name: "إنشاء", exact: true }).click();
    const group = await (await grouped).json();
    owned.groups.add(group.id);
    await expect(page.getByLabel("اكتب رسالة…", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "إعدادات المجموعة", exact: true }).click();
    await page.getByLabel("الاسم", { exact: true }).fill(`${prefix} revised team`);
    await page.getByRole("button", { name: "حفظ", exact: true }).click();
    await expect(page.getByText("تم الحفظ", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "رجوع", exact: true }).click();
    await page.getByLabel("اكتب رسالة…", { exact: true }).fill("@");
    await page.getByRole("button", { name: `@${prefix}`, exact: true }).click();
    await expect(page.getByLabel("اكتب رسالة…", { exact: true })).toHaveValue(`@${prefix} `);
    const mentioned = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url().endsWith(`/threads/${group.thread_id}/messages`),
    );
    await page.getByRole("button", { name: "إرسال", exact: true }).click();
    const mentionReceipt = await (await mentioned).json();
    expect(mentionReceipt.run_ids).toHaveLength(1);
    expect(
      (await (await context.request.get(`/api/runs/${mentionReceipt.run_ids[0]}`)).json()).agent_id,
    ).toBe(agent.id);
    expect(
      (await (await context.request.get(`/api/groups/${group.id}`)).json()).payload.name,
    ).toContain("revised team");
    chartFixture = JSON.parse(
      execFileSync(".venv/bin/python", ["tests/seed_chart_reply.py"], {
        input: JSON.stringify({ action: "init" }),
        encoding: "utf8",
        env: process.env,
      }),
    );
    await page.goto(`/thread?id=${chartFixture.thread_id}`);
    await expect(
      page.getByText("Here is the saved XAUUSD chart image.", { exact: true }),
    ).toBeVisible();
    const image = page.getByRole("img", { name: "XAUUSD.png", exact: true }).last();
    await expect(image).toBeVisible();
    await expect
      .poll(() =>
        image.evaluate((element) => {
          const image = element.querySelector("img") ?? element;
          return image.complete && image.naturalWidth > 0;
        }),
      )
      .toBeTruthy();
    const transcript = await (
      await context.request.get(`/api/threads/${chartFixture.thread_id}/messages`)
    ).json();
    expect(transcript.find((row) => row.id === chartFixture.message_id).attachment_ids).toContain(
      chartFixture.artifact_id,
    );
    const fileResponse = await context.request.get(
      `/api/artifacts/${chartFixture.artifact_id}/file`,
    );
    expect(fileResponse.status()).toBe(200);
    expect(fileResponse.headers()["content-type"]).toMatch(/^image\/png/);
    const png = await fileResponse.body();
    expect(png.subarray(0, 8).toString("hex")).toBe("89504e470d0a1a0a");
    await page.screenshot({ path: ".runtime/rakazo-parity/mobile-chat-image.png" });
    await page.getByRole("button", { name: "إجراءات الوكيل", exact: true }).click();
    await page.getByRole("button", { name: "الرسوم البيانية", exact: true }).click();
    const chartFrame = page.frameLocator('iframe[title="XAUUSD · 1h"]');
    const renderer = chartFrame.locator('[data-renderer="tradingview"]');
    await expect(renderer).toBeVisible();
    await expect(page.getByRole("menu")).not.toBeVisible();
    await expect(
      chartFrame.frameLocator("iframe").getByText("Lonora rsi 14 (1)", { exact: true }),
    ).toBeVisible();
    const scene = await (
      await context.request.get(`/api/charts/${chartFixture.chart_id}/scene`)
    ).json();
    expect(scene.candles).toHaveLength(20);
    expect(scene.annotations).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ type: "price", price: 110, label: "Fixture support" }),
      ]),
    );
    // The renderer acknowledges this exact scene only after study creation and
    // all saved drawing promises complete; labels themselves live on a canvas.
    await expect(renderer).toHaveAttribute(
      "data-applied-scene-version",
      String(scene.scene_version),
    );
    await page.screenshot({ path: ".runtime/rakazo-parity/mobile-chart.png" });
    const refreshed = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url().endsWith(`/charts/${chartFixture.chart_id}/refresh`),
    );
    await page.getByRole("button", { name: "تحديث", exact: true }).click();
    expect((await (await refreshed).json()).requested).toBe(true);
    await page.getByRole("button", { name: "إنشاء رسم بياني", exact: true }).click();
    const saveChart = page.getByRole("button", { name: "حفظ", exact: true });
    // This migrated fixture has no immutable market binding. Creation requires
    // an explicit owner choice even when a chart already exists in the thread.
    await expect(saveChart).toBeDisabled();
    const chartConnections = await (await context.request.get("/api/trading/connections")).json();
    const chartAccountIndex = chartConnections
      .filter((connection) => connection.payload.enabled)
      .findIndex((connection) => connection.id === chartFixture.connection_id);
    expect(chartAccountIndex).toBeGreaterThanOrEqual(0);
    await page.getByRole("button", { name: "حساب الوسيط", exact: true }).click();
    await page.getByRole("menu").getByRole("button").nth(chartAccountIndex).click();
    await expect(saveChart).toBeDisabled();
    await page.getByRole("button", { name: "الرمز", exact: true }).click();
    await page.getByRole("menu").getByRole("button", { name: "XAUUSD", exact: true }).click();
    await expect(saveChart).toBeEnabled();
    const chartCreated = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" && response.url().endsWith("/api/charts"),
    );
    await page.getByRole("button", { name: "حفظ", exact: true }).click();
    const nativeChart = await (await chartCreated).json();
    owned.charts.add(nativeChart.id);
    expect(nativeChart.payload.account_id).toBe(chartFixture.connection_id);
    expect(nativeChart.payload.symbol).toBe("XAUUSD");
    expect(nativeChart.thread_id).toBe(chartFixture.thread_id);
    await page.goto("/settings");
    await page.getByRole("button", { name: "الحساب", exact: true }).click();
    await page.getByRole("button", { name: "English", exact: true }).click();
    await expect(page.getByRole("button", { name: "Sign out", exact: true })).toBeVisible();
    await page.goto("/models");
    await expect(page.getByText("Providers", { exact: true })).toBeVisible();
    await page.goto("/integrations");
    await expect(
      page.getByRole("button", { name: "Open Web settings", exact: true }),
    ).toBeVisible();
    await page.goto("/voice");
    await expect(page.getByText("GPT-Live", { exact: true })).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
    ).toBeTruthy();
    const personal = (await (await context.request.get("/api/agents")).json()).find(
      (row) => row.role === "personal",
    );
    expect(personal).toBeTruthy();
    await page.goto(`/bot-settings?botId=${personal.id}`);
    await expect(page.getByRole("img", { name: "Personal Agent", exact: true })).toBeVisible();
    await expect(
      page.getByText("Your Personal Agent cannot be deleted.", { exact: true }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Delete agent", exact: true })).toHaveCount(0);
    await page.goto(`/bot-settings?botId=${agent.id}`);
    await page.getByRole("button", { name: "Delete agent", exact: true }).click();
    await expect(page.getByText("Delete agent permanently?", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Cancel", exact: true }).click();
    expect(
      (await (await context.request.get("/api/agents")).json()).some((row) => row.id === agent.id),
    ).toBe(true);
    await page.getByRole("button", { name: "Delete agent", exact: true }).click();
    const deleted = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/api/agents/${agent.id}`) &&
        response.request().method() === "DELETE",
    );
    await page.getByRole("button", { name: "Delete permanently", exact: true }).click();
    expect((await deleted).ok()).toBe(true);
    await expect(page).toHaveURL(/\/$/);
    await page.reload();
    expect(
      (await (await context.request.get("/api/agents")).json()).some((row) => row.id === agent.id),
    ).toBe(false);
    await page.goto("/account");
    await page.getByRole("button", { name: "Sign out", exact: true }).click();
    await expect(page.getByRole("textbox", { name: "Email", exact: true })).toBeVisible();
    expect(errors).toEqual([]);
  } finally {
    await broker?.close();
    if (chartFixture)
      execFileSync(".venv/bin/python", ["tests/seed_chart_reply.py"], {
        input: JSON.stringify({ ...chartFixture, action: "cleanup" }),
        encoding: "utf8",
        env: process.env,
      });
    const login = await context.request.post("/api/auth/login", { data: credentials });
    if (login.ok()) {
      headers = { "X-CSRF-Token": (await login.json()).csrf };
      for (const kind of ["charts", "artifacts", "routines", "groups", "agents"])
        for (const id of owned[kind])
          expect([200, 404]).toContain(
            (await context.request.delete(`/api/${kind}/${id}`, { headers })).status(),
          );
    }
  }
});
