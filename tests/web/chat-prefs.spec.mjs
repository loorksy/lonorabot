// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: This Playwright scenario runs without Turborepo caching.
import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

/* «تجربة المحادثة» (reference chatPrefsPage and streamAnswer, Desktop-37 5753-5830): the
   page's sections and rows in the reference's order, and what each switch does to a reply:
   the stream, its pacing, the formatting and the vibration. */
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

test("the page: the reference's sections and rows, a dependent switch, and the vibration gate", async ({
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
  // Recorded before the app wraps it: what really reaches the device.
  await context.addInitScript(() => {
    window.__vibrated = [];
    navigator.vibrate = (pattern) => {
      window.__vibrated.push(pattern);
      return true;
    };
  });
  await page.goto("/app/chat-prefs");
  await expect(page.locator("main h3")).toHaveText([
    "Replies",
    "Interactive interfaces",
    "Agents",
    "Writing",
    "Touch",
  ]);
  const rows = page.getByRole("switch");
  await expect(rows).toHaveCount(10);
  expect(
    await rows.evaluateAll((list) => list.map((row) => row.getAttribute("aria-label"))),
  ).toEqual([
    "Stream the reply word by word",
    "The agent's work steps",
    "Open the steps automatically",
    "Formatted replies",
    "Interactive elements in replies",
    "Why this interface",
    "Detailed agent status",
    "Send with Enter",
    "@ suggestions",
    "Vibration",
  ]);
  // «سبب اختيار الواجهة» depends on the interfaces themselves.
  const why = page.getByRole("switch", { name: "Why this interface" });
  await expect(why).toBeEnabled();
  await page.getByRole("switch", { name: "Interactive elements in replies" }).click();
  await expect(why).toBeDisabled();
  // «الاهتزاز» off: nothing vibrates, whoever asks.
  expect(await page.evaluate(() => navigator.vibrate(7))).toBe(true);
  const vibration = page.getByRole("switch", { name: "Vibration" });
  await vibration.click();
  await expect(vibration).toHaveAttribute("aria-checked", "false");
  expect(await page.evaluate(() => navigator.vibrate(9))).toBe(false);
  expect(await page.evaluate(() => window.__vibrated)).toEqual([7]);
  // The choices are kept on this device.
  await page.reload();
  await expect(page.getByRole("switch", { name: "Vibration" })).toHaveAttribute(
    "aria-checked",
    "false",
  );

  // In Arabic the section is «الكتابة», not the typing status «يكتب».
  await page.evaluate(() => localStorage.setItem("lonora.locale", "ar"));
  await page.reload();
  await expect(page.locator("main h3").nth(3)).toHaveText("الكتابة");
  await expect(page.locator("main h3").nth(4)).toHaveText("اللمس");
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

test("with «بث الرد» off the reply lands whole; with «تنسيق الردود» off it is plain text", async ({
  page,
  context,
}) => {
  test.setTimeout(60_000);
  const data = fixture({ action: "init" });
  await login(context);
  await prefs(context, { stream: false, markdown: false });
  try {
    await page.goto(`/app/g/${data.group}`);
    // The run works (its row and ■ show) but no text is painted while it streams.
    await expect(page.locator("form .stop")).toBeVisible();
    await expect(page.locator(`[data-stream-run-id='${data.run.id}']`)).toHaveCount(0);
    await expect(page.getByTestId("transcript")).not.toContainText("START durable browser prefix");
    const text = "# Weekly plan\n\n- first step\n- second step";
    fixture({ ...data, action: "complete", text });
    const reply = page.locator(".msg:not(.mine)").last();
    await expect(reply).toContainText("first step");
    // Formatting off: the marks stay as typed, with no heading and no list.
    await expect(reply).toContainText("# Weekly plan");
    await expect(reply.locator(".md, h1, h2, h3, ul")).toHaveCount(0);

    // Formatting back on (the default): the same reply is laid out.
    await page.evaluate(() =>
      localStorage.setItem("lonora.chatPrefs", JSON.stringify({ stream: false })),
    );
    await page.reload();
    const laid = page.locator(".msg:not(.mine)").last();
    await expect(laid.locator(".md")).toHaveCount(1);
    await expect(laid.locator("li")).toHaveText(["first step", "second step"]);
  } finally {
    fixture({ ...data, action: "cleanup" });
  }
});
