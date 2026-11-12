// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: This Playwright scenario runs without Turborepo caching.
import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

/* «تجربة المحادثة» (reference chatPrefsPage and streamAnswer, Desktop-37 5753-5830): the
   page's sections and rows, and a streaming reply's pacing. */
function fixture(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_streaming.py", "browser"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}
async function login(context) {
  const response = await context.request.post("/api/auth/login", {
    data: {
      email: process.env.LONORA_UI_TEST_EMAIL ?? "ci@example.com",
      password: process.env.LONORA_UI_TEST_PASSWORD ?? "ci-only-owner-password",
    },
  });
  expect(response.ok()).toBeTruthy();
}
const prefs = (context, value, locale = "en") =>
  context.addInitScript(
    ([stored, language]) => {
      if (!localStorage.getItem("lonora.locale")) localStorage.setItem("lonora.locale", language);
      if (!localStorage.getItem("lonora.chatPrefs"))
        localStorage.setItem("lonora.chatPrefs", JSON.stringify(stored));
    },
    [value, locale],
  );

test("the page: its sections and rows, a dependent switch, and the choices kept", async ({
  page,
  context,
}) => {
  const owner = JSON.parse(
    execFileSync(".venv/bin/python", ["tests/agent_pages_browser.py"], {
      input: JSON.stringify({ action: "init" }),
      encoding: "utf8",
    }),
  );
  await context.addCookies(
    owner.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await prefs(context, {});
  await page.goto("/app/chat-prefs");
  await expect(page.locator("main h3")).toHaveText(["Replies", "Agents", "Writing"]);
  const rows = page.getByRole("switch");
  await expect(rows).toHaveCount(5);
  expect(
    await rows.evaluateAll((list) => list.map((row) => row.getAttribute("aria-label"))),
  ).toEqual([
    "The agent's work steps",
    "Open the steps automatically",
    "Detailed agent status",
    "Send with Enter",
    "@ suggestions",
  ]);
  // «فتح الخطوات تلقائياً» depends on the steps themselves.
  const open = page.getByRole("switch", { name: "Open the steps automatically" });
  await expect(open).toBeEnabled();
  const steps = page.getByRole("switch", { name: "The agent's work steps" });
  await steps.click();
  await expect(steps).toHaveAttribute("aria-checked", "false");
  await expect(open).toBeDisabled();
  // The choices are kept on this device.
  await page.reload();
  await expect(page.getByRole("switch", { name: "The agent's work steps" })).toHaveAttribute(
    "aria-checked",
    "false",
  );

  // In Arabic the section is «الكتابة», not the typing status «يكتب».
  await page.evaluate(() => localStorage.setItem("lonora.locale", "ar"));
  await page.reload();
  await expect(page.locator("main h3").nth(2)).toHaveText("الكتابة");
  execFileSync(".venv/bin/python", ["tests/agent_pages_browser.py"], {
    input: JSON.stringify({ ...owner, groups: [], agents: [], action: "cleanup" }),
    encoding: "utf8",
  });
});

test("a streaming reply flows a word at a time and a finished one is shown whole", async ({
  page,
  context,
}) => {
  test.setTimeout(60_000);
  let data = fixture({ action: "init" });
  await login(context);
  await prefs(context, {});
  try {
    await page.goto(`/app/g/${data.group}`);
    const preview = page.locator(`[data-stream-run-id='${data.run.id}']`);
    await expect(preview).toContainText(data.text.trim());
    // A long piece arrives at once: it is not painted in one burst, and it all arrives.
    const before = (await preview.innerText()).length;
    data = fixture({ ...data, action: "append" });
    await expect.poll(async () => (await preview.innerText()).length).toBeGreaterThan(before);
    await expect(preview.locator(".caret")).toHaveCount(1);
    await expect(preview).toContainText("chunk-169");
    // The composer shows ■ while the reply is written.
    await expect(page.locator("form .stop")).toBeVisible();
    fixture({ ...data, action: "complete" });
    await expect(preview).toHaveCount(0);
    await expect(page.getByTestId("transcript")).toContainText("chunk-169");
    await expect(page.locator(".caret")).toHaveCount(0);
  } finally {
    fixture({ ...data, action: "cleanup" });
  }
});
