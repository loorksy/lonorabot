// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: Playwright runs directly without Turborepo caching.
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

test("Expo profile, routines, groups and authenticated artifacts use the persistent server", async ({
  page,
  context,
}) => {
  const prefix = `Expo regression ${randomUUID()}`;
  const owned = { agents: new Set(), groups: new Set(), routines: new Set(), artifacts: new Set() };
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
    await expect(
      page.getByRole("textbox", { name: "ابحث عن وكيل أو مجموعة", exact: true }),
    ).toBeVisible();
    expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toMatch(
      /Bearer|"token"|"session"/,
    );
    await page.getByRole("button", { name: "+", exact: true }).click();
    await page.getByLabel("الاسم", { exact: true }).fill(prefix);
    const created = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/agents") && response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "إنشاء", exact: true }).click();
    const agent = await (await created).json();
    owned.agents.add(agent.id);
    await expect(page.getByLabel("اكتب رسالة…", { exact: true })).toBeVisible();
    const threadUrl = page.url();
    await page.getByRole("button", { name: "إعدادات الوكيل", exact: true }).click();
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
    expect(
      (await (await context.request.get(`/api/groups/${group.id}`)).json()).payload.name,
    ).toContain("revised team");
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
    await expect(page.getByText("LiveKit", { exact: true })).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
    ).toBeTruthy();
    await page.goto("/account");
    await page.getByRole("button", { name: "Sign out", exact: true }).click();
    await expect(page.getByRole("textbox", { name: "Email", exact: true })).toBeVisible();
    expect(errors).toEqual([]);
  } finally {
    const login = await context.request.post("/api/auth/login", { data: credentials });
    if (login.ok()) {
      headers = { "X-CSRF-Token": (await login.json()).csrf };
      for (const kind of ["artifacts", "routines", "groups", "agents"])
        for (const id of owned[kind])
          expect([200, 404]).toContain(
            (await context.request.delete(`/api/${kind}/${id}`, { headers })).status(),
          );
    }
  }
});
