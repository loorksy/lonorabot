import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { expect, test } from "../ui-test.mjs";

// The version of the built-in memory skill that this commit ships.
const MEMORY_VERSION = JSON.parse(
  readFileSync(
    new URL("../../packages/agent-runtime/resources/skills/memory/skill.json", import.meta.url),
    "utf8",
  ),
).version;

async function fixture(context) {
  const data = JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify({ action: "init" }),
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
  const headers = {
    "X-CSRF-Token": data.cookies.find((cookie) => cookie.name === "lonora_csrf").value,
  };
  const response = await context.request.post("/api/agents", {
    headers,
    data: {
      name: `Skills ${randomUUID()}`,
      trading_account_id: data.account,
      trading_symbol: data.symbol,
    },
  });
  expect(response.status()).toBe(201);
  const agent = await response.json();
  const name = `owner-skill-${randomUUID().slice(0, 8)}`;
  const manifest = {
    id: name,
    version: "1.0.0",
    title: "Owner review procedure",
    description: "Review actual evidence before presenting the result",
    source: "owner",
    activation: { mode: "explicit", triggers: [] },
    required_tools: ["memory_read"],
    required_capabilities: ["memory.read"],
    dependencies: ["memory"],
    priority: 42,
    context_budget: 2000,
  };
  const saved = await context.request.post("/api/skills", {
    headers,
    data: {
      agent_id: agent.id,
      payload: { name, content: "Keep all evidence attributed.", enabled: true, manifest },
    },
  });
  expect(saved.status()).toBe(201);
  const resource = await saved.json();
  return {
    agent,
    name,
    manifest,
    resource,
    headers,
    cleanup: () => context.request.delete(`/api/agents/${agent.id}`, { headers }),
  };
}

for (const locale of ["en", "ar"]) {
  test(`Expo ${locale} Skills shows read-only builtins and persists exact-version blocking`, async ({
    page,
    context,
    cleanup,
  }) => {
    const f = await fixture(context);
    const labels = {
      block: locale === "ar" ? "حظر هذا الإصدار" : "Block this version",
      confirm: locale === "ar" ? "حظر هذا الإصدار نهائيًا؟" : "Permanently block this version?",
      close: locale === "ar" ? "إغلاق" : "Close",
      builtin:
        locale === "ar"
          ? "تعليمات مدمجة للقراءة فقط. يمكنك حظر إصدار محدد لهذا المساعد."
          : "Built-in instructions are read only. You can block an exact version for this agent.",
      blocked:
        locale === "ar" ? "الإصدار محظور لهذا المساعد" : "This version is blocked for this agent",
      history: locale === "ar" ? "الإصدارات المحظورة" : "Blocked versions",
      current: locale === "ar" ? "الكتالوج الحالي" : "Current catalog",
      save: locale === "ar" ? "حفظ" : "Save",
    };
    cleanup(() => f.cleanup());
    await page.addInitScript((value) => localStorage.setItem("lonora.locale", value), locale);
    await page.goto(`/skills?botId=${f.agent.id}`);
    await expect(page.getByText(labels.current, { exact: true })).toBeVisible();
    const builtin = page.getByTestId("skill-entry-memory");
    await builtin.click();
    const details = page.getByTestId("skill-details");
    await expect(details.getByText(labels.builtin, { exact: true })).toBeVisible();
    await expect(details.getByRole("textbox")).toHaveCount(0);
    await expect(details.getByRole("button", { name: labels.save, exact: true })).toHaveCount(0);
    await details.getByRole("button", { name: labels.block, exact: true }).click();
    await expect(details.getByText(labels.confirm, { exact: true })).toBeVisible();
    await details.getByRole("button", { name: labels.block, exact: true }).click();
    await expect(details).toHaveCount(0);
    await expect(builtin.getByText(labels.blocked, { exact: true })).toBeVisible();
    await page.reload();
    await expect(builtin.getByText(labels.blocked, { exact: true })).toBeVisible();
    const controls = await (
      await context.request.get(`/api/agents/${f.agent.id}/skills/revocations`)
    ).json();
    expect(controls.revoked).toHaveLength(1);
    expect(controls.revoked[0]).toMatchObject({
      skill_id: "memory",
      version: MEMORY_VERSION,
      reason: "owner_revoked",
    });
    await expect(page.getByText(labels.history, { exact: true })).toBeVisible();
    // Removing an installed resource never erases a historical version denial.
    await context.request.delete(`/api/skills/${f.resource.id}`, { headers: f.headers });
    const final = await (
      await context.request.get(`/api/agents/${f.agent.id}/skills/revocations`)
    ).json();
    expect(final).toEqual(controls);
  });
}

test("Expo Skills edits installed version and enabled state without dropping its manifest", async ({
  page,
  context,
  cleanup,
}) => {
  const f = await fixture(context);
  cleanup(() => f.cleanup());
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  await page.goto(`/bot-settings?botId=${f.agent.id}`);
  await page.getByRole("button", { name: "Skills", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/skills\\?botId=${f.agent.id}`));
  await page.getByTestId(`skill-entry-${f.name}`).click();
  const details = page.getByTestId("skill-details");
  await details.getByRole("textbox", { name: "Version", exact: true }).fill("2.0.0");
  await details
    .getByRole("textbox", { name: "Skill instructions", exact: true })
    .fill("Compare the result with its original evidence.");
  await details.getByRole("switch", { name: "Enabled", exact: true }).click();
  await details.getByRole("button", { name: "Save", exact: true }).click();
  await expect(details.getByText("Saved", { exact: true })).toBeVisible();
  const saved = await (await context.request.get(`/api/skills/${f.resource.id}`)).json();
  expect(saved.payload.manifest).toMatchObject({ ...f.manifest, version: "2.0.0" });
  expect(saved.payload.content).toBe("Compare the result with its original evidence.");
  expect(saved.payload.enabled).toBe(false);
  await details.getByRole("button", { name: "Close", exact: true }).click();
  await page.reload();
  await expect(
    page.getByTestId(`skill-entry-${f.name}`).getByText("2.0.0", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByTestId(`skill-entry-${f.name}`).getByText("This skill is disabled", { exact: true }),
  ).toBeVisible();
});

test("Expo Skills says a skill loads on an event only when it has triggers", async ({
  page,
  context,
  cleanup,
}) => {
  const f = await fixture(context);
  const names = {};
  cleanup(() => f.cleanup());
  // Unless explicit, a skill loads by itself only when the run's trigger is one of its
  // triggers, whatever its mode; with no triggers it loads only on request.
  for (const [key, mode, triggers] of [
    ["request", "automatic", []],
    ["event", "automatic", ["watch"]],
    ["untriggered", "trigger_based", []],
  ]) {
    const name = `${key}-${randomUUID().slice(0, 8)}`;
    const saved = await context.request.post("/api/skills", {
      headers: f.headers,
      data: {
        agent_id: f.agent.id,
        payload: {
          name,
          content: "Keep all evidence attributed.",
          enabled: true,
          manifest: { ...f.manifest, id: name, activation: { mode, triggers } },
        },
      },
    });
    expect(saved.status()).toBe(201);
    names[key] = name;
  }
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "ar"));
  await page.goto(`/skills?botId=${f.agent.id}`);
  for (const [key, label] of [
    ["request", "التفعيل: عند الطلب"],
    ["event", "التفعيل: بحدث"],
    ["untriggered", "التفعيل: عند الطلب"],
  ]) {
    await page.getByTestId(`skill-entry-${names[key]}`).click();
    const details = page.getByTestId("skill-details");
    await expect(details.getByText(label, { exact: true })).toBeVisible();
    await details.getByRole("button", { name: "إغلاق", exact: true }).click();
    await expect(details).toHaveCount(0);
  }
});

test("Expo Skills can block an older pinned version absent from the current catalog", async ({
  page,
  context,
  cleanup,
}) => {
  const f = await fixture(context);
  cleanup(() => f.cleanup());
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  await page.goto(`/skills?botId=${f.agent.id}`);
  await page.getByRole("button", { name: "Block an exact version", exact: true }).click();
  const form = page.getByTestId("skill-exact-version-block");
  await form.getByRole("textbox", { name: "Skill ID", exact: true }).fill(f.name);
  await form.getByRole("textbox", { name: "Version", exact: true }).fill("0.9.0");
  await form.getByRole("button", { name: "Block this version", exact: true }).click();
  await expect(form.getByText("Permanently block this version?", { exact: true })).toBeVisible();
  expect(
    (await (await context.request.get(`/api/agents/${f.agent.id}/skills/revocations`)).json())
      .revoked,
  ).toEqual([]);
  await form.getByRole("button", { name: "Block this version", exact: true }).click();
  await expect(form).toHaveCount(0);
  await page.reload();
  await expect(page.getByText(`${f.name} · 0.9.0`, { exact: true })).toBeVisible();
  await expect(page.getByTestId(`skill-entry-${f.name}`).getByText(/ · Available$/)).toBeVisible();
  const controls = await (
    await context.request.get(`/api/agents/${f.agent.id}/skills/revocations`)
  ).json();
  expect(controls.revoked).toHaveLength(1);
  expect(controls.revoked[0]).toMatchObject({ skill_id: f.name, version: "0.9.0" });
});

test("Expo Skills creates typed owner instructions and deletes only after confirmation", async ({
  page,
  context,
  cleanup,
}) => {
  const f = await fixture(context);
  const name = `created-${randomUUID().slice(0, 8)}`;
  cleanup(() => f.cleanup());
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  await page.goto(`/skills?botId=${f.agent.id}`);
  await page.getByRole("button", { name: "Add a skill", exact: true }).click();
  const form = page.getByTestId("skill-create");
  await form.getByRole("textbox", { name: "Skill ID", exact: true }).fill(name);
  await form
    .getByRole("textbox", { name: "Title", exact: true })
    .fill("Verify evidence before delivery");
  await form
    .getByRole("textbox", { name: "Purpose", exact: true })
    .fill("Check references before presenting analysis");
  await form
    .getByRole("textbox", { name: "Skill instructions", exact: true })
    .fill("Inspect the original saved evidence and report its limits.");
  await expect(form.getByRole("textbox", { name: "Version", exact: true })).toHaveValue("1.0.0");
  await form.getByRole("button", { name: "Create skill", exact: true }).click();
  await expect(form).toHaveCount(0);
  const catalog = await (
    await context.request.get(`/api/agents/${f.agent.id}/skills/catalog`)
  ).json();
  const created = catalog.items.find((row) => row.id === name);
  expect(created.manifest).toMatchObject({
    id: name,
    version: "1.0.0",
    source: "owner",
    risk_class: "read_only",
    activation: { mode: "explicit", triggers: [] },
    required_tools: [],
    required_capabilities: [],
    dependencies: [],
    conflicts: [],
    description: "Check references before presenting analysis",
  });
  await page.getByTestId(`skill-entry-${name}`).click();
  const details = page.getByTestId("skill-details");
  await details.getByRole("button", { name: "Delete skill", exact: true }).click();
  const confirmation = page.getByTestId("skill-delete-confirmation");
  await expect(
    confirmation.getByText("Delete this installed skill?", { exact: true }),
  ).toBeVisible();
  expect((await context.request.get(`/api/skills/${created.resource_id}`)).status()).toBe(200);
  const deleted = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/skills/${created.resource_id}`) &&
      response.request().method() === "DELETE",
  );
  await confirmation.getByRole("button", { name: "Delete skill", exact: true }).click();
  expect(await (await deleted).json()).toEqual({ deleted: true });
  await expect(details).toHaveCount(0);
  await expect(page.getByTestId(`skill-entry-${name}`)).toHaveCount(0);
  expect((await context.request.get(`/api/skills/${created.resource_id}`)).status()).toBe(404);
});

test("Expo Skills blocks the reviewed version after the installed catalog advances", async ({
  page,
  context,
  cleanup,
}) => {
  const f = await fixture(context);
  cleanup(() => f.cleanup());
  await page.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  await page.goto(`/skills?botId=${f.agent.id}`);
  await page.getByTestId(`skill-entry-${f.name}`).click();
  const details = page.getByTestId("skill-details");
  await details.getByRole("button", { name: "Block this version", exact: true }).click();
  const confirmation = page.getByTestId("skill-version-confirmation");
  await expect(confirmation.getByText(`${f.name} · 1.0.0`, { exact: true })).toBeVisible();
  await details.getByRole("textbox", { name: "Version", exact: true }).fill("2.0.0");
  await details.getByRole("button", { name: "Save", exact: true }).click();
  await expect(details.getByText("Saved", { exact: true })).toBeVisible();
  await expect(confirmation.getByText(`${f.name} · 1.0.0`, { exact: true })).toBeVisible();
  await confirmation.getByRole("button", { name: "Block this version", exact: true }).click();
  await expect(details).toHaveCount(0);
  const controls = await (
    await context.request.get(`/api/agents/${f.agent.id}/skills/revocations`)
  ).json();
  expect(controls.revoked).toHaveLength(1);
  expect(controls.revoked[0]).toMatchObject({ skill_id: f.name, version: "1.0.0" });
  const catalog = await (
    await context.request.get(`/api/agents/${f.agent.id}/skills/catalog`)
  ).json();
  expect(catalog.items.find((row) => row.id === f.name)).toMatchObject({
    version: "2.0.0",
    available: true,
  });
});
