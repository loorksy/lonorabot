import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

function fixture(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}

async function setup(context, locale = "en") {
  const data = fixture({ action: "init", empty: true });
  await context.addCookies(
    data.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript((value) => localStorage.setItem("lonora.locale", value), locale);
  const headers = { "X-CSRF-Token": data.cookies.find((row) => row.name === "lonora_csrf").value };
  const response = await context.request.post("/api/agents", {
    headers,
    data: {
      name: `Skills browser ${randomUUID()}`,
      trading_account_id: data.account,
      trading_symbol: data.symbol,
    },
  });
  expect(response.status()).toBe(201);
  const agent = await response.json();
  return {
    agent,
    headers,
    async open(page) {
      await page.goto("/app/knowledge");
      await page.locator(".page-header select").selectOption(agent.id);
      await page
        .getByRole("button", { name: locale === "ar" ? "المهارات" : "Skills", exact: true })
        .click();
      await expect(page.locator(`[data-agent-skills="${agent.id}"]`)).toBeVisible();
    },
    async cleanup() {
      await context.request.delete(`/api/agents/${agent.id}`, { headers });
      fixture({ ...data, action: "cleanup" });
    },
  };
}

for (const locale of ["en", "ar"]) {
  test(`Web ${locale} Skills catalog lazily reads builtins and persists exact version blocking`, async ({
    page,
    context,
  }) => {
    const state = await setup(context, locale);
    await page.setViewportSize({ width: 390, height: 844 });
    const reads = [];
    page.on("request", (request) => {
      if (request.method() === "GET" && request.url().includes(`/skills/catalog/`))
        reads.push(request.url());
    });
    try {
      await state.open(page);
      const card = page.locator('[data-skill-id="chart-analysis"]');
      await expect(card).toBeVisible();
      expect(reads).toHaveLength(0);
      await card.locator(":scope > summary").click();
      await expect(card.locator(".skill-instructions")).toBeVisible();
      await expect(card.locator("textarea")).toHaveCount(0);
      await expect(card.locator(".skill-instructions")).toContainText("chart");
      expect(reads).toHaveLength(1);
      await card
        .getByRole("button", {
          name: locale === "ar" ? "حظر هذا الإصدار" : "Block this version",
          exact: true,
        })
        .click();
      const submit = page.waitForResponse(
        (response) =>
          response.request().method() === "POST" &&
          response.url().endsWith(`/agents/${state.agent.id}/skills/revocations`),
      );
      await card
        .getByRole("button", {
          name: locale === "ar" ? "حظر الإصدار نهائيًا" : "Block version permanently",
          exact: true,
        })
        .click();
      expect((await submit).ok()).toBeTruthy();
      await expect(card).toHaveAttribute("data-skill-available", "false");
      const controls = await (
        await context.request.get(`/api/agents/${state.agent.id}/skills/revocations`)
      ).json();
      expect(controls.revoked).toHaveLength(1);
      expect(controls.revoked[0]).toMatchObject({
        skill_id: "chart-analysis",
        reason: "owner_revoked",
      });
      await page.reload();
      await page.locator(".page-header select").selectOption(state.agent.id);
      await page
        .getByRole("button", { name: locale === "ar" ? "المهارات" : "Skills", exact: true })
        .click();
      await expect(card).toHaveAttribute("data-skill-available", "false");
      await card.locator(":scope > summary").click();
      await expect(card.locator(".skill-revoke button")).toHaveCount(0);
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow).toBeLessThanOrEqual(1);
    } finally {
      await state.cleanup();
    }
  });
}

test("Web Skill editing retains complete manifest, explicit version and optimistic resource revision", async ({
  page,
  context,
}) => {
  const state = await setup(context);
  const id = `owner-${randomUUID().replaceAll("-", "")}`;
  const payload = {
    name: id,
    content: "Read broker evidence before discussing the market.",
    enabled: true,
    manifest: {
      id,
      version: "1.2.3",
      title: "Owner verified checklist",
      description: "Explicitly scoped owner instructions.",
      source: "owner",
      stability: "experimental",
      activation: { mode: "explicit", intents: [], triggers: [] },
      risk_class: "read_only",
      required_tools: ["market_quote"],
      required_capabilities: ["market.read"],
      dependencies: ["chart-analysis"],
      conflicts: [],
      priority: 31,
      context_budget: 500,
    },
  };
  try {
    const response = await context.request.post("/api/skills", {
      headers: state.headers,
      data: { agent_id: state.agent.id, payload },
    });
    expect(response.status()).toBe(201);
    const original = await response.json();
    await state.open(page);
    const card = page.locator(`[data-skill-id="${id}"]`);
    await card.locator(":scope > summary").click();
    await card.getByLabel("Instruction version", { exact: true }).fill("1.2.4");
    await card
      .getByLabel("Content", { exact: true })
      .fill("Read broker evidence and current spreads before discussing the market.");
    await card.getByRole("checkbox", { name: "Enabled", exact: true }).uncheck();
    const edited = page.waitForResponse(
      (result) =>
        result.request().method() === "PUT" && result.url().endsWith(`/skills/${original.id}`),
    );
    await card.getByRole("button", { name: "Save", exact: true }).click();
    const changed = await (await edited).json();
    expect(changed.version).toBe(original.version + 1);
    expect(changed.payload.manifest).toEqual({ ...payload.manifest, version: "1.2.4" });
    expect(changed.payload.enabled).toBe(false);
    await expect(card).toHaveAttribute("data-skill-available", "false");
    // A concurrent owner edit cannot be overwritten by a stale form or a blind retry.
    const other = await context.request.put(`/api/skills/${original.id}`, {
      headers: state.headers,
      data: {
        version: changed.version,
        payload: { ...changed.payload, content: "Newer owner revision." },
      },
    });
    expect(other.ok()).toBeTruthy();
    await card.getByLabel("Content", { exact: true }).fill("Stale browser revision.");
    const conflict = page.waitForResponse(
      (result) =>
        result.request().method() === "PUT" && result.url().endsWith(`/skills/${original.id}`),
    );
    await card.getByRole("button", { name: "Save", exact: true }).click();
    expect((await conflict).status()).toBe(409);
    await expect(card.getByRole("alert")).toContainText("Reload");
    await card.getByRole("alert").getByRole("button", { name: "Reload", exact: true }).click();
    await expect(card.getByLabel("Content", { exact: true })).toHaveValue("Newer owner revision.");
    const current = await (await context.request.get(`/api/skills/${original.id}`)).json();
    expect(current.payload.content).toBe("Newer owner revision.");
  } finally {
    await state.cleanup();
  }
});

test("Web permanent block freezes the reviewed version while current catalog advances", async ({
  page,
  context,
}) => {
  const state = await setup(context);
  const id = `review-${randomUUID().replaceAll("-", "")}`;
  const payload = {
    name: id,
    content: "Review source evidence.",
    enabled: true,
    manifest: {
      id,
      version: "1.0.0",
      title: "Review frozen version",
      description: "Owner-reviewed procedures.",
      source: "owner",
      activation: { mode: "explicit" },
    },
  };
  try {
    const response = await context.request.post("/api/skills", {
      headers: state.headers,
      data: { agent_id: state.agent.id, payload },
    });
    expect(response.status()).toBe(201);
    const original = await response.json();
    await state.open(page);
    const card = page.locator(`[data-skill-id="${id}"]`);
    await card.locator(":scope > summary").click();
    await expect(card.getByLabel("Content", { exact: true })).toBeVisible();
    await card.getByRole("button", { name: "Block this version", exact: true }).click();
    await expect(card.locator(".skill-revoke bdi")).toHaveText(`${id}@1.0.0`);
    const updated = await context.request.put(`/api/skills/${original.id}`, {
      headers: state.headers,
      data: {
        version: original.version,
        payload: {
          ...original.payload,
          manifest: { ...original.payload.manifest, version: "2.0.0" },
        },
      },
    });
    expect(updated.ok()).toBeTruthy();
    await page
      .locator(".skills-toolbar")
      .getByRole("button", { name: "Reload", exact: true })
      .click();
    await expect(card.locator(":scope > summary")).toContainText("2.0.0");
    await expect(card.locator(".skill-revoke bdi")).toHaveText(`${id}@1.0.0`);
    const submission = page.waitForResponse(
      (result) =>
        result.request().method() === "POST" &&
        result.url().endsWith(`/agents/${state.agent.id}/skills/revocations`),
    );
    await card.getByRole("button", { name: "Block version permanently", exact: true }).click();
    const result = await submission;
    expect(result.request().postDataJSON().version).toBe("1.0.0");
    expect(result.ok()).toBeTruthy();
    const actual = await result.json();
    expect(actual.revoked.map((row) => row.version)).toEqual(["1.0.0"]);
    await expect(card).toHaveAttribute("data-skill-available", "true");
  } finally {
    await state.cleanup();
  }
});
