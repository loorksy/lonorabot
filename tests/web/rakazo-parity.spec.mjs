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
    await expect(page.locator(".chat-head .chat-name")).toContainText(data.name);
    // The rail opens «المستجدات» (UI phase 4b: stories, notifications, upcoming, latest actions).
    await page
      .locator(".desktop-rail")
      .getByRole("button", { name: "Updates", exact: true })
      .click();
    await expect(page).toHaveURL(/\/app\/updates$/);
    await expect(page.locator("main .stories")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Latest actions", exact: true })).toBeVisible();
    await page.goto(`/app/${data.agent}?thread=${data.thread}`);
    await page.getByRole("button", { name: "Agent info", exact: true }).click();
    const profile = page.locator("#dialog");
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
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Chat menu", exact: true }).click();
    await page.locator("#dialog").getByRole("button", { name: "Chart", exact: true }).click();
    const panel = page.locator("#dialog");
    // Q37: the reference's chart sheet draws the chart's candles as SVG.
    await expect(
      panel.locator(`[data-chart-id='${data.chart}'] svg.chart > g > rect`).first(),
    ).toBeVisible();
    await image.evaluate((element) => element.decode());
    await image.screenshot({ path: ".runtime/rakazo-parity/svg-isolated.png" });
    await page.evaluate(
      () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
    );
    await page.screenshot({ path: ".runtime/rakazo-parity/web-chat-chart.png", fullPage: true });
    await page.keyboard.press("Escape");
    await expect(panel).not.toHaveAttribute("open", "");
    // The reference names a photo generically («صورة، اضغط لعرضها»): open it by its file.
    await page.locator(`.img-msg[data-artifact-id='${data.artifact}']`).click();
    // The reference's photo sheet: the image itself, never a frame.
    const preview = page.locator("#dialog");
    await expect(preview.locator(".sheet-photo-box.ld img")).toBeVisible();
    await expect(preview.locator("iframe")).toHaveCount(0);
    await page.keyboard.press("Escape");
    await expect(page.locator("#app")).not.toHaveAttribute("inert", "");
    await page.locator(".composer textarea").fill("**Keep these characters** https://example.com");
    await page.locator(".composer .send").click();
    const literal = page.getByTestId("transcript").locator(".msg.mine .bubble .text");
    await expect(literal).toContainText("**Keep these characters**");
    await expect(literal.locator("strong")).toHaveCount(0);
    await expect(
      literal.getByRole("link", { name: "https://example.com", exact: true }),
    ).toHaveAttribute("href", "https://example.com");
    // There is no creation form (P5): the new agent comes from the agents API here.
    const csrf = data.cookies.find((cookie) => cookie.name === "lonora_csrf").value;
    const response = await context.request.post("/api/agents", {
      headers: { "X-CSRF-Token": csrf },
      data: {
        name: "Role parity fixture",
        description: "Review exposure before trading.",
        trading_account_id: data.account,
        trading_symbol: data.symbol,
      },
    });
    const created = await response.json();
    expect(response.status(), JSON.stringify(created)).toBe(201);
    data.extra_agents.push(created.id);
    expect(created.description).toBe("Review exposure before trading.");
    await page.goto(`/app/${created.id}`);
    await expect(page.locator(".chat-head .chat-name")).toContainText("Role parity fixture");
    await page.getByRole("button", { name: "Agent info", exact: true }).click();
    await expect(
      page.locator("#dialog").getByRole("textbox", { name: "Description", exact: true }),
    ).toHaveValue("Review exposure before trading.");
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
      `[data-message-id='${png.message_id}'].theirs [data-artifact-id='${png.artifact_id}'] img`,
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
