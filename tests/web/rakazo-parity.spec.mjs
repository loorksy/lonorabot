// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: Playwright runs without Turborepo caching.
import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

function fixture(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_rakazo_ui.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}
test("conversation shows safe generated SVG, cloud chart side panel and persisted role creation", async ({
  page,
  context,
}) => {
  test.setTimeout(60_000);
  const data = fixture({ action: "init" });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  try {
    await context.addCookies(
      data.cookies.map((cookie) => ({
        ...cookie,
        url: test.info().project.use.baseURL,
        httpOnly: cookie.name === "lonora_session",
        sameSite: "Strict",
      })),
    );
    await context.addInitScript(() => {
      localStorage.setItem("lonora.locale", "en");
      localStorage.setItem("lonora.theme", JSON.stringify("light"));
    });
    await page.goto(`/app/${data.agent}`);
    const image = page
      .getByTestId("transcript")
      .locator(`[data-artifact-id='${data.artifact}'] img`);
    await expect(image).toBeVisible();
    await expect
      .poll(() => image.evaluate((element) => element.complete && element.naturalWidth > 0))
      .toBe(true);
    expect(await page.evaluate(() => window.svgProbe)).toBeUndefined();
    await expect(page.locator(".tpl-chat-identity")).toContainText("Market research");
    await page.getByRole("button", { name: "Activity", exact: true }).click();
    const activity = page.locator(".tpl-sidebar-activity");
    await expect(activity).toBeVisible();
    await expect(activity.locator(`[data-sidebar-run-id='${data.run}']`)).toContainText(data.name);
    await activity
      .getByRole("searchbox", { name: "Search runs", exact: true })
      .fill("NO MATCHING RUN FIXTURE");
    await expect(activity.getByText("No runs match these filters.", { exact: true })).toBeVisible();
    await activity.getByRole("searchbox", { name: "Search runs", exact: true }).fill(data.name);
    await activity.getByRole("combobox", { name: "Status", exact: true }).selectOption("completed");
    await activity.locator(`[data-sidebar-run-id='${data.run}']`).click();
    await expect(page).toHaveURL(new RegExp(`/app/${data.agent}\\?thread=${data.thread}$`));
    await page.getByRole("button", { name: "Activity", exact: true }).click();
    await expect(activity).toHaveCount(0);
    await page.locator(".tpl-chat-identity").click();
    const profile = page.getByTestId("side-panel");
    await expect(profile.getByLabel("Instructions", { exact: true })).not.toBeVisible();
    await profile.getByText("Advanced", { exact: true }).click();
    await profile
      .getByLabel("Instructions", { exact: true })
      .fill("Actual persisted analysis instructions.");
    const update = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === `/api/agents/${data.agent}` &&
        response.request().method() === "PATCH",
    );
    await profile.getByRole("button", { name: "Save", exact: true }).click();
    expect((await update).ok()).toBeTruthy();
    const savedAgents = await context.request.get("/api/agents");
    expect(savedAgents.ok()).toBeTruthy();
    expect((await savedAgents.json()).find((agent) => agent.id === data.agent).instructions).toBe(
      "Actual persisted analysis instructions.",
    );
    await page.getByRole("button", { name: "Charts", exact: true }).click();
    const panel = page.getByTestId("side-panel");
    await expect(panel.locator(`[data-chart-id='${data.chart}'] canvas`).first()).toBeVisible();
    await image.evaluate((element) => element.decode());
    await image.screenshot({ path: ".runtime/rakazo-parity/svg-isolated.png" });
    await page.evaluate(
      () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
    );
    await page.screenshot({ path: ".runtime/rakazo-parity/web-chat-chart.png", fullPage: true });
    await page.getByRole("button", { name: "Close context panel", exact: true }).click();
    await page.getByRole("button", { name: "Preview analysis.svg", exact: true }).click();
    const preview = page.getByRole("dialog", { name: "analysis.svg", exact: true });
    await expect(preview.locator("img")).toBeVisible();
    await expect(preview.locator("iframe")).toHaveCount(0);
    await preview.getByRole("button", { name: "Close", exact: true }).click();
    await page
      .getByRole("combobox", { name: "Message", exact: true })
      .fill("**Keep these characters** https://example.com");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    const literal = page.getByTestId("transcript").locator(".template-user-text");
    await expect(literal).toContainText("**Keep these characters**");
    await expect(literal.locator("strong")).toHaveCount(0);
    await expect(
      literal.getByRole("link", { name: "https://example.com", exact: true }),
    ).toHaveAttribute("href", "https://example.com");
    await page.getByRole("button", { name: "Create", exact: true }).click();
    await expect(page.getByTestId("new-conversation-picker")).toBeVisible();
    await page.getByTestId("create-new-agent").click();
    await panel.getByLabel("Name", { exact: true }).fill("Role parity fixture");
    await panel.getByLabel("Title", { exact: true }).fill("Risk analyst");
    await panel.getByLabel("Description", { exact: true }).fill("Review exposure before trading.");
    await panel.getByLabel("Broker account", { exact: true }).selectOption(data.account);
    await page.getByRole("button", { name: "Choose trading pair", exact: true }).click();
    await page.getByRole("option", { name: data.symbol, exact: true }).click();
    const creation = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === "/api/agents" &&
        response.request().method() === "POST",
    );
    await panel.getByRole("button", { name: "Create agent", exact: true }).click();
    const created = await (await creation).json();
    data.extra_agents.push(created.id);
    expect(created.title).toBe("Risk analyst");
    expect(created.description).toBe("Review exposure before trading.");
    await page.reload();
    await expect(page.locator(".tpl-chat-identity")).toContainText("Risk analyst");
    expect(errors).toEqual([]);
  } finally {
    fixture({ ...data, action: "cleanup" });
  }
});

test("actual chart snapshot arrives as an assistant image card and survives reload", async ({
  page,
  context,
}) => {
  const png = JSON.parse(
    execFileSync(".venv/bin/python", ["tests/seed_chart_reply.py"], {
      input: JSON.stringify({ action: "init" }),
      encoding: "utf8",
    }),
  );
  try {
    await context.addCookies(
      png.cookies.map((cookie) => ({
        ...cookie,
        url: test.info().project.use.baseURL,
        httpOnly: cookie.name === "lonora_session",
        sameSite: "Strict",
      })),
    );
    await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
    await page.goto(`/app/${png.agent_id}`);
    const image = page.locator(
      `[data-message-id='${png.message_id}'][class*='assistant'] [data-artifact-id='${png.artifact_id}'] img`,
    );
    await expect(image).toBeVisible();
    await expect
      .poll(() => image.evaluate((element) => element.complete && element.naturalWidth > 0))
      .toBe(true);
    const file = await context.request.get(`/api/artifacts/${png.artifact_id}/file`);
    expect(file.ok()).toBeTruthy();
    expect(file.headers()["content-type"]).toContain("image/png");
    expect([...(await file.body()).subarray(0, 8)]).toEqual([137, 80, 78, 71, 13, 10, 26, 10]);
    await page.reload();
    await expect(image).toBeVisible();
    await expect
      .poll(() => image.evaluate((element) => element.complete && element.naturalWidth > 0))
      .toBe(true);
    await page.screenshot({
      path: ".runtime/rakazo-parity/web-generated-chart.png",
      fullPage: true,
    });
  } finally {
    execFileSync(".venv/bin/python", ["tests/seed_chart_reply.py"], {
      input: JSON.stringify({ ...png, action: "cleanup" }),
      encoding: "utf8",
    });
  }
});
