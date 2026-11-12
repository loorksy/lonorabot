// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: Playwright runs directly without Turborepo caching.
/* UI phase 4b, the domain pages, end to end through the owner's own controls: every screen
   reads and writes the real API (nothing intercepted), and what it shows comes back after a
   reload. «تحديد كمكتملة» stops work without approving anything; skills restore with undo. */
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { test as base, expect } from "@playwright/test";

const test = base.extend({
  owner: async ({ context }, use) => {
    const credentials = {
      email: process.env.LONORA_UI_TEST_EMAIL ?? "ci@example.com",
      password: process.env.LONORA_UI_TEST_PASSWORD ?? "ci-only-owner-password",
    };
    const status = await (await context.request.get("/api/onboarding")).json();
    if (!status.owner_initialized)
      await context.request.post("/api/onboarding", {
        data: {
          ...credentials,
          bootstrap_token: process.env.LONORA_BOOTSTRAP_TOKEN ?? "lonora-ui-bootstrap-ci-only-2026",
        },
      });
    const login = await context.request.post("/api/auth/login", { data: credentials });
    expect(login.status()).toBe(200);
    const headers = { "X-CSRF-Token": (await login.json()).csrf };
    const call = async (method, path, data) => {
      const response = await context.request.fetch(`/api${path}`, { method, data, headers });
      expect(response.ok(), `${method} ${path}`).toBeTruthy();
      return response.json();
    };
    const prefix = `Domain ${randomUUID().slice(0, 8)}`;
    const agent = await call("POST", "/agents/create", {
      template: "general",
      name: prefix,
      responsibility: "Keeps notes",
    });
    await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
    try {
      await use({ agent, prefix, call });
    } finally {
      // Test cleanup only (the UI never deletes agents): a run's agent creation is capped
      // on active agents, so a fixture agent left behind would fail later specs.
      await context.request.delete(`/api/agents/${agent.id}`, { headers });
    }
  },
});

const saved = (page, method, pattern) =>
  page.waitForResponse(
    (response) =>
      response.request().method() === method && pattern.test(new URL(response.url()).pathname),
  );

test("tasks: create with due time and criterion, then mark as completed", async ({
  page,
  owner,
}) => {
  const { agent, prefix } = owner;
  await page.goto(`/app/new-task?agent=${agent.id}`);
  const form = page.locator('form[data-form="task"]');
  await form.getByLabel("Task title", { exact: true }).fill(`${prefix} report`);
  await form.getByLabel("What is needed", { exact: true }).fill("Summarise the week");
  await form.getByLabel("Due time", { exact: true }).fill("18:30");
  await form.getByLabel("Completion criterion", { exact: true }).fill("A report in the chat");
  const created = saved(page, "POST", /^\/api\/tasks$/);
  await form.getByRole("button", { name: "Create task", exact: true }).click();
  const task = await (await created).json();
  expect(new Date(task.due_at).getMinutes()).toBe(30);
  await expect(page.locator("main h2")).toHaveText(`${prefix} report`);
  await expect(page.locator("main .badge")).toHaveText("In progress");
  await expect(page.getByText("A report in the chat", { exact: true })).toBeVisible();
  const done = saved(page, "POST", /\/api\/tasks\/[^/]+\/complete$/);
  await page.getByRole("button", { name: "Mark as completed", exact: true }).click();
  expect((await (await done).json()).status).toBe("completed");
  await expect(page.locator("main .badge")).toHaveText("Completed");
  await page.reload();
  await expect(page.locator("main .badge")).toHaveText("Completed");
  await page.goto("/app/tasks");
  await page.getByRole("tab", { name: "Completed", exact: true }).click();
  await expect(page.getByRole("button", { name: new RegExp(`${prefix} report`) })).toBeVisible();
  // The activity log is the server's projection of what happened.
  await page.goto("/app/activity");
  await expect(
    page.locator('[data-activity="task_completed"]').filter({ hasText: `${prefix} report` }),
  ).toBeVisible();
});

test("schedules: a titled daily routine and a one-shot, with the switch", async ({
  page,
  owner,
}) => {
  const { agent, prefix, call } = owner;
  await page.goto(`/app/new-schedule?agent=${agent.id}`);
  let form = page.locator('form[data-form="schedule"]');
  await form.getByLabel("Task", { exact: true }).fill(`${prefix} brief`);
  await form.getByLabel("Repeat", { exact: true }).selectOption("workdays");
  await form.getByLabel("Time", { exact: true }).fill("07:15");
  let created = saved(page, "POST", new RegExp(`^/api/routines/${agent.id}$`));
  await form.getByRole("button", { name: "Save schedule", exact: true }).click();
  const daily = await (await created).json();
  expect(daily).toMatchObject({ title: `${prefix} brief`, run_at: null });
  expect(daily.cron).toMatch(/^15 7 \* \* 1-5$/);
  await page.goto(`/app/new-schedule?agent=${agent.id}`);
  form = page.locator('form[data-form="schedule"]');
  await form.getByLabel("Task", { exact: true }).fill(`${prefix} once`);
  await form.getByLabel("Schedule type", { exact: true }).selectOption("once");
  await form.getByRole("button", { name: "Save schedule", exact: true }).click();
  await expect(page.locator("#toast")).toContainText("Choose the task's date.");
  await form.getByLabel("Date", { exact: true }).fill("2030-01-02");
  created = saved(page, "POST", new RegExp(`^/api/routines/${agent.id}$`));
  await form.getByRole("button", { name: "Save schedule", exact: true }).click();
  const once = await (await created).json();
  expect(once.run_at).toBeTruthy();
  expect(once.cron).toBeNull();
  await page.goto(`/app/routines?agent=${agent.id}`);
  const toggle = page.getByRole("switch", { name: `Enable ${prefix} brief`, exact: true });
  await expect(toggle).toHaveAttribute("aria-checked", "true");
  const put = saved(page, "PUT", new RegExp(`^/api/routines/${daily.id}$`));
  await toggle.click();
  expect((await (await put).json()).enabled).toBe(false);
  await page.reload();
  await expect(toggle).toHaveAttribute("aria-checked", "false");
  const routines = await call("GET", `/routines?agent_id=${agent.id}`);
  expect(routines.map((row) => row.title).sort()).toEqual([`${prefix} brief`, `${prefix} once`]);
  // A general agent has no account: no conditional type is offered.
  await page.goto(`/app/new-schedule?agent=${agent.id}`);
  await expect(page.locator('select[name="type"] option[value="condition"]')).toHaveCount(0);
});

/** Marks a one-shot as fired («نُفّذت»): its time passed, it ran and switched itself off. */
const fireOneShot = (routineId) =>
  execFileSync(
    ".venv/bin/python",
    [
      "-c",
      `import asyncio, os, sys, asyncpg
async def main():
    url = os.environ["LONORA_DATABASE_URL"].replace("postgresql+asyncpg", "postgresql")
    conn = await asyncpg.connect(url)
    await conn.execute(
        "UPDATE ln_routines SET enabled = false, run_at = now() - interval '2 minutes',"
        " last_run_at = now() - interval '1 minute' WHERE id::text = $1", sys.argv[1])
    await conn.close()
asyncio.run(main())`,
      routineId,
    ],
    { encoding: "utf8" },
  );

test("schedules: a fired one-shot reschedules from its details sheet, from both lists", async ({
  page,
  owner,
}) => {
  const { agent, prefix, call } = owner;
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const once = await call("POST", `/routines/${agent.id}`, {
    title: `${prefix} fired`,
    prompt: "Send the summary",
    run_at: "2031-01-02T09:00:00Z",
    timezone: "UTC",
  });
  fireOneShot(once.id);
  const reschedule = async (date) => {
    const row = page.locator("#app main .row", { hasText: `${prefix} fired` });
    await expect(row.locator(".value")).toHaveText("Done");
    await row.getByRole("button", { name: new RegExp(`${prefix} fired`) }).click();
    const sheet = page.locator('form[data-form="reschedule"]');
    await sheet.getByLabel("Date", { exact: true }).fill(date);
    await sheet.getByLabel("Time", { exact: true }).fill("08:45");
    const put = saved(page, "PUT", new RegExp(`^/api/routines/${once.id}$`));
    await sheet.getByRole("button", { name: "Schedule again", exact: true }).click();
    const body = await (await put).json();
    expect(body.enabled).toBe(true);
    expect(new Date(body.run_at).getMinutes()).toBe(45);
    await expect(
      page.getByRole("switch", { name: `Enable ${prefix} fired`, exact: true }),
    ).toHaveAttribute("aria-checked", "true");
  };
  await page.goto(`/app/routines?agent=${agent.id}`);
  await reschedule("2031-03-04");
  fireOneShot(once.id);
  await page.goto("/app/tasks");
  await page.getByRole("tab", { name: "Scheduled", exact: true }).click();
  await reschedule("2031-05-06");
  const [row] = (await call("GET", `/routines?agent_id=${agent.id}`)).filter(
    (item) => item.id === once.id,
  );
  expect(row).toMatchObject({ enabled: true, title: `${prefix} fired` });
  expect(new Date(row.run_at).getDate()).toBe(6);
  expect(errors).toEqual([]);
});

test("goals, knowledge links and text files persist", async ({ page, owner }) => {
  const { agent, prefix } = owner;
  await page.goto(`/app/goals?agent=${agent.id}`);
  await expect(page.getByText("No goals for this agent.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Add a goal", exact: true }).click();
  let form = page.locator('form[data-form="goal"]');
  await form.getByLabel("Goal title", { exact: true }).fill(`${prefix} learn`);
  await form.getByRole("button", { name: "Save", exact: true }).click();
  const row = page.getByRole("button", { name: new RegExp(`${prefix} learn`) });
  await expect(row).toContainText("Active");
  await row.click();
  form = page.locator('form[data-form="goal"]');
  await form.getByRole("switch", { name: "Completed" }).check();
  await form.getByRole("button", { name: "Save", exact: true }).click();
  await expect(row).toContainText("Completed");

  await page.goto(`/app/knowledge-edit?agent=${agent.id}`);
  form = page.locator('form[data-form="knowledge"]');
  await form.getByLabel("Title", { exact: true }).fill(`${prefix} docs`);
  await form.getByLabel("Type", { exact: true }).selectOption("link");
  await form.getByLabel("Link", { exact: true }).fill("https://example.com/docs");
  await form.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/app/knowledge\\?agent=${agent.id}`));
  await expect(page.getByRole("button", { name: new RegExp(`${prefix} docs`) })).toContainText(
    "Link",
  );

  await page.goto(`/app/file-edit?agent=${agent.id}`);
  form = page.locator('form[data-form="file"]');
  await form.getByLabel("File name", { exact: true }).fill("plan.md");
  await form.getByLabel("Content", { exact: true }).fill("first draft");
  await form.getByRole("button", { name: "Save file", exact: true }).click();
  const file = page.getByRole("button", { name: /plan\.md/ });
  await expect(file).toBeVisible();
  await file.click();
  await expect(page.locator("#dialog .paper")).toHaveText("first draft");
  await page.locator("#dialog").getByRole("button", { name: "Edit", exact: true }).click();
  form = page.locator('form[data-form="file"]');
  await form.getByLabel("Content", { exact: true }).fill("second draft");
  const put = saved(page, "PUT", /\/api\/artifacts\/[^/]+\/text$/);
  await form.getByRole("button", { name: "Save file", exact: true }).click();
  expect((await put).ok()).toBeTruthy();
  await file.click();
  await expect(page.locator("#dialog .paper")).toHaveText("second draft");
});

test("skills: create, edit, version history, restore and undo", async ({ page, owner }) => {
  const { agent, prefix, call } = owner;
  await page.goto(`/app/new-skill?agent=${agent.id}`);
  let form = page.locator('form[data-form="skill"]');
  await form.getByLabel("Name", { exact: true }).fill(`${prefix} brief`);
  await form.getByLabel("Description", { exact: true }).fill("Summarise news");
  await form.getByLabel("Instructions", { exact: true }).fill("First instructions.");
  await form.getByLabel("Tool", { exact: true }).selectOption("web_search");
  const created = saved(page, "POST", /^\/api\/skills$/);
  await form.getByRole("button", { name: "Save skill", exact: true }).click();
  const skill = await (await created).json();
  expect(skill.payload.manifest).toMatchObject({
    title: `${prefix} brief`,
    description: "Summarise news",
    required_tools: ["web_search"],
  });
  await expect(page).toHaveURL(new RegExp(`/app/skills/${skill.id}$`));
  form = page.locator('form[data-form="skill"]');
  await form.getByLabel("Instructions", { exact: true }).fill("Second instructions.");
  await form.getByRole("button", { name: "Save skill", exact: true }).click();
  await expect(page.locator("#toast")).toContainText("Skill saved");
  await page.getByRole("button", { name: "Version history", exact: true }).click();
  const restored = saved(page, "POST", /\/api\/skills\/[^/]+\/restore$/);
  await page
    .locator("#dialog .row", { hasText: "Version 1" })
    .getByRole("button", { name: "Restore", exact: true })
    .click();
  expect((await (await restored).json()).payload.content).toBe("First instructions.");
  await expect(form.getByLabel("Instructions", { exact: true })).toHaveValue("First instructions.");
  const undone = saved(page, "POST", /\/api\/skills\/[^/]+\/restore$/);
  await page.locator("#toast").getByRole("button", { name: "Undo", exact: true }).click();
  expect((await (await undone).json()).payload.content).toBe("Second instructions.");
  const versions = await call("GET", `/skills/${skill.id}/versions`);
  expect(versions.map((row) => row.version)).toEqual([4, 3, 2, 1]);
  await page.goto(`/app/skills?agent=${agent.id}`);
  const toggle = page.getByRole("switch", { name: `Enable ${prefix} brief`, exact: true });
  await toggle.click();
  await expect(page.locator("#toast")).toContainText("Skill disabled");
  expect((await call("GET", `/skills/${skill.id}`)).payload.enabled).toBe(false);
});

test("task page: a task held for the owner offers pause and resume, each sending its own action", async ({
  page,
  owner,
}) => {
  const { agent, prefix, call } = owner;
  const thread = await call("POST", `/agents/${agent.id}/conversation`, {});
  const task = await call("POST", `/tasks?agent_id=${agent.id}&thread_id=${thread.id}`, {
    title: `${prefix} held`,
  });
  // The server's projection for a run waiting on the owner (waiting_input): both controls.
  await page.route(`**/api/tasks/${task.id}`, async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    await route.fulfill({
      response,
      json: { ...body, status: "waiting", can_pause: true, can_resume: true },
    });
  });
  const sent = [];
  await page.route("**/api/tasks/control", async (route) => {
    sent.push(route.request().postDataJSON().action);
    await route.fulfill({
      json: { ...task, status: "paused", can_pause: false, can_resume: true },
    });
  });
  await page.goto(`/app/tasks/${task.id}`);
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  await expect.poll(() => sent).toEqual(["pause"]);
  await page.getByRole("button", { name: "Resume", exact: true }).click();
  await expect.poll(() => sent).toEqual(["pause", "resume"]);
});
