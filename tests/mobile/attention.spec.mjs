import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

test("Expo Arabic attention uses durable server state and read does not grant trading", async ({
  page,
  context,
}) => {
  const fixture = JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_attention_browser.py"], { encoding: "utf8" }),
  );
  await context.addCookies(
    fixture.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      sameSite: "Strict",
      httpOnly: cookie.name === "lonora_session",
    })),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "النشاط", exact: true }).click();
  await expect(page.getByText("الإيقاف الطارئ مفعّل", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "تحديد كمقروء", exact: true }).click();
  await expect(page.getByText("الإيقاف الطارئ مفعّل", { exact: true })).toHaveCount(0);
  await page.reload();
  await page.getByRole("button", { name: "النشاط", exact: true }).click();
  await expect(page.getByText("لا توجد تنبيهات جديدة", { exact: true })).toBeVisible();
  const controls = await (await context.request.get("/api/trading/controls")).json();
  expect(controls).toMatchObject({ enabled: false, emergency_stop: true });
});
