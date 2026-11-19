// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: Playwright runs directly without Turborepo caching.
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

/* A profile line from before origins were recorded: written to the row directly, with no
   revision, so «ما أعرفه عنك» shows it as earlier. The row is found by the test's tag. */
function seedEarlier(tag, line) {
  execFileSync(".venv/bin/python", [
    "-c",
    `import asyncio, os, sys
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
async def main():
    engine = create_async_engine(os.environ["LONORA_DATABASE_URL"])
    async with engine.begin() as connection:
        await connection.execute(text("UPDATE ln_owner_profile SET content = content || :line WHERE content LIKE :tag"), {"line": sys.argv[2] + "\\n", "tag": "%" + sys.argv[1] + "%"})
    await engine.dispose()
asyncio.run(main())`,
    tag,
    line,
  ]);
}

/* «ما أعرفه عنك» on mobile (8.4): the same lines and origins the web shows; a correction and a
   deletion are recorded as the owner's word. */
test("Expo Arabic what-I-know view lists origins and records corrections", async ({
  page,
  context,
}) => {
  const credentials = {
    email: process.env.LONORA_UI_TEST_EMAIL ?? "ci@example.com",
    password: process.env.LONORA_UI_TEST_PASSWORD ?? "ci-only-owner-password",
  };
  if (!(await (await context.request.get("/api/onboarding")).json()).owner_initialized) {
    const initialized = await context.request.post("/api/onboarding", {
      data: {
        ...credentials,
        bootstrap_token: process.env.LONORA_BOOTSTRAP_TOKEN ?? "lonora-ui-bootstrap-ci-only-2026",
      },
    });
    expect(initialized.status()).toBe(201);
  }
  const login = await context.request.post("/api/auth/login", { data: credentials });
  expect(login.status()).toBe(200);
  const headers = { "X-CSRF-Token": (await login.json()).csrf };
  const tag = randomUUID().slice(0, 8);
  const profile = await (await context.request.get("/api/owner/profile")).json();
  const written = await context.request.put("/api/owner/profile", {
    data: { content: `- يتداول الذهب ${tag}\n- تقارير قصيرة ${tag}\n`, version: profile.version },
    headers,
  });
  expect(written.ok()).toBeTruthy();
  seedEarlier(tag, `- ملاحظة قديمة ${tag}`);
  await page.goto("/settings");
  await page.getByTestId("what-i-know").click();
  await expect(page.getByText("ما أعرفه عنك", { exact: true }).last()).toBeVisible();
  const lines = page.getByTestId("known-line");
  await expect(lines.filter({ hasText: `ملاحظة قديمة ${tag}` })).toContainText("من قبل");
  const gold = lines.filter({ hasText: `يتداول الذهب ${tag}` });
  await expect(gold).toContainText("قلتَه");
  // Typed with its own bullet: the stored line keeps exactly one.
  await gold.getByRole("button", { name: "صحّح المعلومة", exact: true }).click();
  const field = page.getByRole("textbox", { name: "صحّح المعلومة", exact: true });
  await expect(field).toHaveValue(`يتداول الذهب ${tag}`);
  await field.fill(`- يتداول الفضة ${tag}`);
  await page.getByRole("button", { name: "حفظ", exact: true }).click();
  await expect(lines.filter({ hasText: `يتداول الفضة ${tag}` })).toContainText("قلتَه");
  // Typed without one: the line's bullet is kept.
  await lines
    .filter({ hasText: `ملاحظة قديمة ${tag}` })
    .getByRole("button", { name: "صحّح المعلومة", exact: true })
    .click();
  await field.fill(`ملاحظة جديدة ${tag}`);
  await page.getByRole("button", { name: "حفظ", exact: true }).click();
  await expect(lines.filter({ hasText: `ملاحظة جديدة ${tag}` })).toContainText("قلتَه");
  await lines
    .filter({ hasText: `تقارير قصيرة ${tag}` })
    .getByRole("button", { name: "احذف المعلومة", exact: true })
    .click();
  await expect(lines.filter({ hasText: `تقارير قصيرة ${tag}` })).toHaveCount(0);
  const known = await (await context.request.get("/api/owner/profile/lines")).json();
  expect(known.lines.map((line) => line.text)).toEqual([
    `- يتداول الفضة ${tag}`,
    `- ملاحظة جديدة ${tag}`,
  ]);
  const revisions = await (await context.request.get("/api/owner/profile/revisions")).json();
  expect(revisions[0]).toMatchObject({ author: "owner", change: "correction" });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
  ).toBeTruthy();
});
