// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: This Playwright scenario runs without Turborepo caching.
import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

function fixture(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_streaming.py", "browser"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}

test("durable reply survives event eviction, reload and a fenced restart without duplicate handoff", async ({
  page,
  context,
}) => {
  test.setTimeout(60_000);
  let data = fixture({ action: "init", history: true });
  const login = await context.request.post("/api/auth/login", {
    data: {
      email: process.env.LONORA_UI_TEST_EMAIL ?? "ci@example.com",
      password: process.env.LONORA_UI_TEST_PASSWORD ?? "ci-only-owner-password",
    },
  });
  expect(login.ok()).toBeTruthy();
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  try {
    await page.goto(`/app/g/${data.group}`);
    const preview = page.locator(`[data-stream-run-id='${data.run.id}']`);
    await expect(preview).toContainText(data.text);
    await page.getByRole("button", { name: "Load earlier messages", exact: true }).click();
    await expect(
      page.getByTestId("transcript").getByText("HISTORY 000 immutable fixture", { exact: true }),
    ).toHaveCount(1);
    // Keep the initial DB preview in the client so the live accumulator must survive eviction.
    await page.route("**/api/runs**", (route) =>
      new URL(route.request().url()).pathname === "/api/runs" ? route.abort() : route.continue(),
    );
    data = fixture({ ...data, action: "append" });
    await expect(preview).toContainText("chunk-169");
    await expect(preview).toContainText("START durable browser prefix");
    await page.unroute("**/api/runs**");
    await page.reload();
    await expect(preview).toContainText("START durable browser prefix");
    await expect(preview).toContainText("chunk-169");
    await page.getByRole("button", { name: "Load earlier messages", exact: true }).click();
    await expect(
      page.getByTestId("transcript").getByText("HISTORY 000 immutable fixture", { exact: true }),
    ).toHaveCount(1);
    data = fixture({ ...data, action: "recover" });
    await expect(preview).toContainText(data.text);
    await expect(preview).not.toContainText("START durable browser prefix");
    await page.reload();
    await expect(preview).toContainText(data.text);
    await page.getByRole("button", { name: "Load earlier messages", exact: true }).click();
    fixture({ ...data, action: "complete" });
    await expect(page.getByTestId("transcript").getByText(data.text, { exact: true })).toHaveCount(
      1,
    );
    await expect(preview).toHaveCount(0);
    await expect(
      page.getByTestId("transcript").getByText("HISTORY 000 immutable fixture", { exact: true }),
    ).toHaveCount(1);
    expect(errors).toEqual([]);
  } finally {
    fixture({ ...data, action: "cleanup" });
  }
});

test("real peer requests and returned results remain visible in both canonical conversations", async ({
  page,
  context,
}) => {
  const data = fixture({ action: "peer_init" });
  const login = await context.request.post("/api/auth/login", {
    data: {
      email: process.env.LONORA_UI_TEST_EMAIL ?? "ci@example.com",
      password: process.env.LONORA_UI_TEST_PASSWORD ?? "ci-only-owner-password",
    },
  });
  expect(login.ok()).toBeTruthy();
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const card = page.locator(`[data-peer-message-id='${data.child.id}']`);
  try {
    await page.goto(`/app/${data.agents[0]}?thread=${data.source_thread}`);
    await expect(card.filter({ hasText: "PERSISTED peer request" })).toHaveCount(1);
    await card.locator(`a[href*='${data.agents[1]}']`).click();
    await expect(page).toHaveURL(
      new RegExp(`/app/${data.agents[1]}\\?thread=${data.target_thread}$`),
    );
    await expect(card.filter({ hasText: "PERSISTED peer request" })).toHaveCount(1);
    fixture({ ...data, action: "peer_complete" });
    await expect(card.filter({ hasText: "PERSISTED peer answer" })).toHaveCount(1);
    await page.goto(`/app/${data.agents[0]}?thread=${data.source_thread}`);
    await expect(card.filter({ hasText: "PERSISTED peer request" })).toHaveCount(1);
    await expect(card.filter({ hasText: "PERSISTED peer answer" })).toHaveCount(1);
    await page.reload();
    await expect(card.filter({ hasText: "PERSISTED peer answer" })).toHaveCount(1);
  } finally {
    fixture({ ...data, action: "peer_cleanup" });
  }
});
