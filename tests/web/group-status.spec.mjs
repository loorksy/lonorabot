// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: Playwright runs without Turborepo caching.
import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

function fixture(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_group_ux.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}

test("group distinguishes an answered lead from a silent observer and clears completed progress", async ({
  page,
  context,
}) => {
  const data = fixture({ action: "init" });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  try {
    const login = await context.request.post("/api/auth/login", {
      data: {
        email: process.env.LONORA_UI_TEST_EMAIL ?? "ci@example.com",
        password: process.env.LONORA_UI_TEST_PASSWORD ?? "ci-only-owner-password",
      },
    });
    expect(login.ok()).toBeTruthy();
    await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
    await page.goto(`/app/g/${data.group}`);
    for (const [index, run] of data.runs.entries()) {
      await expect(page.locator(`[data-run-status-id='${run.id}']`)).toContainText(
        data.names[index],
      );
      await expect(page.locator(`[data-progress-run-id='${run.id}']`)).toContainText(
        data.names[index],
      );
    }
    fixture({ ...data, action: "finish" });
    await expect(page.locator(`[data-run-status-id='${data.runs[0].id}']`)).toContainText(
      "Completed",
    );
    await expect(page.locator(`[data-run-status-id='${data.runs[1].id}']`)).toContainText(
      "No reply needed",
    );
    await expect(page.locator("[data-progress-run-id]")).toHaveCount(0);
    await expect(page.getByTestId("transcript")).toContainText("GROUP LEAD durable answer");
    await page.reload();
    await expect(page.locator(`[data-run-status-id='${data.runs[1].id}']`)).toContainText(
      "No reply needed",
    );
    await expect(page.locator("[data-progress-run-id]")).toHaveCount(0);
    expect(errors).toEqual([]);
  } finally {
    fixture({ ...data, action: "cleanup" });
  }
});
