// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: Playwright runs without Turborepo caching.
import { execFileSync } from "node:child_process";
import { expect, test } from "../ui-test.mjs";

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
  cleanup,
}) => {
  const data = fixture({ action: "init" });
  const [lead, watch] = data.runs;
  const [leadName, observerName] = data.names;
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  cleanup(() => fixture({ ...data, action: "cleanup" }));
  const login = await context.request.post("/api/auth/login", {
    data: {
      email: process.env.LONORA_UI_TEST_EMAIL ?? "ci@example.com",
      password: process.env.LONORA_UI_TEST_PASSWORD ?? "ci-only-owner-password",
    },
  });
  expect(login.ok()).toBeTruthy();
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  // A message that names no one is the lead's to answer; the observer is not asked.
  expect(data.admitted).toEqual([data.agents[0]]);
  await page.goto(`/app/g/${data.group}`);
  const transcript = page.getByTestId("transcript");
  await expect(page.locator(`[data-progress-run-id='${lead.id}']`)).toContainText(leadName);
  // The observer's watch wake is background work: it takes no reply slot of the owner's.
  await expect(page.locator(`[data-progress-run-id='${watch.id}']`)).toHaveCount(0);
  fixture({ ...data, action: "finish" });
  await expect(page.locator("[data-progress-run-id]")).toHaveCount(0);
  await expect(transcript).toContainText("GROUP LEAD durable answer");
  // With nothing new, the observer's run posts nothing (VISION 11.5).
  await expect(transcript).not.toContainText(observerName);
  await page.reload();
  await expect(transcript).toContainText("GROUP LEAD durable answer");
  await expect(page.locator("[data-progress-run-id]")).toHaveCount(0);
  await expect(transcript).not.toContainText(observerName);
  expect(errors).toEqual([]);
});
