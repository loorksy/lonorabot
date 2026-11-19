// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: Playwright runs directly without Turborepo caching.
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { test as base, expect } from "@playwright/test";

let authenticatedSession;

const test = base.extend({
  owner: async ({ context }, use) => {
    const status = await context.request.get("/api/onboarding");
    expect(status.ok()).toBeTruthy();
    const credentials = {
      email: process.env.LONORA_UI_TEST_EMAIL ?? "ci@example.com",
      password: process.env.LONORA_UI_TEST_PASSWORD ?? "ci-only-owner-password",
    };
    if (!(await status.json()).owner_initialized) {
      const initialized = await context.request.post("/api/onboarding", {
        data: {
          ...credentials,
          bootstrap_token: process.env.LONORA_BOOTSTRAP_TOKEN ?? "lonora-ui-bootstrap-ci-only-2026",
        },
      });
      expect(initialized.status()).toBe(201);
    }
    if (authenticatedSession) await context.addCookies(authenticatedSession.cookies);
    if (
      !authenticatedSession ||
      (await context.request.get("/api/auth/session")).status() !== 200
    ) {
      const login = await context.request.post("/api/auth/login", { data: credentials });
      expect(login.status()).toBe(200);
      authenticatedSession = { cookies: await context.cookies(), csrf: (await login.json()).csrf };
    }
    const headers = { "X-CSRF-Token": authenticatedSession.csrf };
    const profile = await (await context.request.get("/api/owner/profile")).json();
    // Start from an empty profile and the default reach-me preference.
    await context.request.put("/api/owner/profile", {
      data: { content: "", version: profile.version },
      headers,
    });
    await context.request.put("/api/owner/preferences", {
      data: {
        reply_language: null,
        name: null,
        address: null,
        reach_me: { channel: "message", quiet_start_hour: null, quiet_end_hour: null },
      },
      headers,
    });
    const agents = await (await context.request.get("/api/agents")).json();
    expect(agents.length).toBeGreaterThan(0);
    await use({ headers, agent: agents[0] });
  },
});

/* «الملف الشخصي» and «الإشعارات والتواصل» (UI phase 5): the shared profile is edited, its change
   is logged with its author and restored; the reach mode is one choice saved on the server. */
test("the owner profile is edited, logged, restored, and the reach mode saved", async ({
  page,
  context,
  owner,
}) => {
  await context.addInitScript(() => {
    localStorage.setItem("lonora.locale", "en");
    localStorage.setItem("lonora.auth.intro-seen", "1");
  });
  await page.goto("/app/owner");
  const name = `Owner ${randomUUID().slice(0, 6)}`;
  await page.getByLabel("Name", { exact: true }).fill(name);
  const line = `- Prefers short answers ${randomUUID().slice(0, 8)}`;
  await page.getByLabel("Preferences", { exact: true }).fill(line);
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect
    .poll(async () => (await (await context.request.get("/api/owner/profile")).json()).name)
    .toBe(name);
  const saved = await (await context.request.get("/api/owner/profile")).json();
  expect(saved.content.trim()).toBe(line);
  const log = page.locator(".pf-log");
  await expect(log.locator(".row").filter({ hasText: "Name" }).first()).toContainText(name);
  // Restoring the text change puts the previous (empty) profile back as a new change.
  const change = log.locator(".row").filter({ hasText: "Preferences" }).first();
  await change.getByRole("button", { name: "Restore", exact: true }).click();
  await expect
    .poll(async () =>
      (await (await context.request.get("/api/owner/profile")).json()).content.trim(),
    )
    .toBe("");
  await page.goto("/app/notify-settings");
  await page.getByRole("radio", { name: /An alert on your device/ }).click();
  await expect
    .poll(
      async () => (await (await context.request.get("/api/voice/incoming/policy")).json()).channel,
    )
    .toBe("notify");
  const after = await (await context.request.get("/api/owner/profile")).json();
  expect(after.name).toBe(name);
  // Restoring a preferences row the page does not reload for by itself (the reach mode) updates
  // the log in place, without a reload: the row reads «Restored» and the revert is the newest row.
  await page.goto("/app/owner");
  const rows = log.locator(".row");
  const reach = rows.filter({ has: page.locator("ins", { hasText: /^Notify me$/ }) }).first();
  await expect(reach).toBeVisible();
  const top = await rows.first().innerText();
  let reloaded = false;
  page.once("load", () => {
    reloaded = true;
  });
  await reach.getByRole("button", { name: "Restore", exact: true }).click();
  await expect(reach).toContainText("Restored");
  await expect(reach.getByRole("button", { name: "Restore", exact: true })).toHaveCount(0);
  await expect(rows.first()).not.toHaveText(top);
  await expect(rows.first().locator("ins", { hasText: /^Message me$/ })).toBeVisible();
  expect(reloaded).toBe(false);
  await expect
    .poll(
      async () => (await (await context.request.get("/api/voice/incoming/policy")).json()).channel,
    )
    .toBe("message");
  expect(owner.agent.id).toBeTruthy();
});

test("the profile page reads right to left in Arabic with the reference's labels", async ({
  page,
  context,
  owner,
}) => {
  await context.addInitScript(() => {
    localStorage.setItem("lonora.locale", "ar");
    localStorage.setItem("lonora.auth.intro-seen", "1");
  });
  await page.goto("/app/owner");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.getByLabel("الاسم", { exact: true })).toBeVisible();
  await expect(page.getByLabel("طريقة المخاطبة", { exact: true })).toBeVisible();
  await expect(page.getByText("سجل التغييرات")).toBeVisible();
  await page.goto("/app/notify-settings");
  await expect(page.getByRole("radio", { name: /رسالة/ })).toHaveAttribute("aria-checked", "true");
  expect(owner.agent.id).toBeTruthy();
});

test("one name and initial everywhere, every time zone, a Save that waits for a change and no call without a device", async ({
  page,
  context,
  owner,
}) => {
  await context.addInitScript(() => {
    localStorage.setItem("lonora.locale", "ar");
    localStorage.setItem("lonora.auth.intro-seen", "1");
  });
  await page.setViewportSize({ width: 1280, height: 800 });
  const local = (process.env.LONORA_UI_TEST_EMAIL ?? "ci@example.com").split("@")[0];
  await page.goto("/app/owner");
  // No name yet: the field shows the e-mail name as a hint, and every avatar the same capital.
  const name = page.getByLabel("الاسم", { exact: true });
  await expect(name).toHaveValue("");
  await expect(name).toHaveAttribute("placeholder", local);
  const initial = local.slice(0, 1).toUpperCase();
  await expect(page.locator(".hero .avatar")).toHaveText(initial);
  await expect(page.locator(".desktop-rail .avatar.initial")).toHaveText(initial);
  // Every IANA time zone the browser knows, each by its own name.
  const zones = page.locator("select[name=zone] option");
  await expect(zones.filter({ hasText: /^Asia\/Damascus$/ })).toHaveCount(1);
  expect(await zones.count()).toBeGreaterThan(100);
  // «حفظ» waits for a change.
  const save = page.getByRole("button", { name: "حفظ", exact: true });
  await expect(save).toBeDisabled();
  await name.fill("Ahmed");
  // A blank form of address is no address: the initial stays the name's.
  await page.getByLabel("طريقة المخاطبة", { exact: true }).fill(" ");
  await expect(page.locator(".hero .avatar")).toHaveText("A");
  await page.getByLabel("طريقة المخاطبة", { exact: true }).fill("أبو سامي");
  await expect(page.locator(".hero .avatar")).toHaveText("أ");
  await save.click();
  await expect(page.locator(".desktop-rail .avatar.initial")).toHaveText("أ");
  await page.goto("/app");
  await expect(page.locator(".welcome h2")).toHaveText("مرحبًا أبو سامي");
  // A new agent's empty chat: its avatar at 88px over the same greeting.
  const made = await context.request.post("/api/agents/create", {
    headers: owner.headers,
    data: { name: `Empty ${randomUUID().slice(0, 6)}`, template: "general" },
  });
  expect(made.status()).toBe(201);
  await page.goto(`/app/${(await made.json()).id}`);
  await expect(page.locator(".chat-empty h2")).toHaveText("مرحبًا أبو سامي");
  expect((await page.locator(".chat-empty > .lonora-agent-avatar").boundingBox())?.width).toBe(88);
  await page.goto("/app/accessibility");
  await expect(page.getByRole("heading", { name: "حجم النص · افتراضي" })).toBeVisible();
  await page.goto("/app/settings");
  await expect(page.getByRole("button", { name: /أبو سامي/ })).toBeVisible();
  await expect(page.locator(".settings-version")).toHaveText(
    /^Lonora · الإصدار \S+( · [0-9a-f]{1,7})?$/,
  );
  await page.getByRole("button", { name: /^تسجيل الخروج/ }).click();
  await expect(page.locator("#dialog")).toContainText("تسجيل الخروج؟");
  await page.keyboard.press("Escape");
  // The reach options are bare nouns, and the settings row shows the same word.
  await page.goto("/app/notify-settings");
  await expect(page.getByRole("radio", { name: /^رسالة/ })).toHaveAttribute("aria-checked", "true");
  await expect(page.getByRole("radio", { name: /^مكالمة/ })).toBeVisible();
  // The device list shows exactly when the owner has a passkey device (an earlier test may have
  // registered one for this owner). Without one, «مكالمة» does not save and the server says why.
  const profile = await (await context.request.get("/api/owner/profile")).json();
  const device = page.getByRole("heading", { name: "الجهاز", exact: true });
  if (profile.devices.length) await expect(device).toBeVisible();
  else {
    await expect(device).toHaveCount(0);
    await page.getByRole("radio", { name: /^مكالمة/ }).click();
    await expect(
      page.locator(".t-msg").getByText("سجّل جهازًا بمفتاح المرور قبل اختيار الاتصال."),
    ).toBeVisible();
    expect((await (await context.request.get("/api/voice/incoming/policy")).json()).channel).toBe(
      "message",
    );
  }
  expect(owner.agent.id).toBeTruthy();
});

test("quiet hours turned off log only the struck window", async ({ page, context, owner }) => {
  await context.addInitScript(() => {
    localStorage.setItem("lonora.locale", "ar");
    localStorage.setItem("lonora.auth.intro-seen", "1");
  });
  for (const [start, end] of [
    [22, 8],
    [null, null],
  ]) {
    const put = await context.request.put("/api/owner/preferences", {
      headers: owner.headers,
      data: { reach_me: { channel: "message", quiet_start_hour: start, quiet_end_hour: end } },
    });
    expect(put.ok()).toBeTruthy();
  }
  await page.goto("/app/owner");
  const off = page.locator(".pf-log .row").filter({ hasText: "ساعات الهدوء" }).first();
  await expect(off.locator("del")).toHaveText("22:00 – 08:00");
  await expect(off.locator("ins")).toHaveCount(0);
});

test("the Knowledge panel's profile link closes the chat menu and opens the profile page", async ({
  page,
  context,
  owner,
}) => {
  await context.addInitScript(() => {
    localStorage.setItem("lonora.locale", "en");
    localStorage.setItem("lonora.auth.intro-seen", "1");
  });
  await page.goto(`/app/memory?agent=${owner.agent.id}`);
  const panel = page.locator("main");
  await panel.getByRole("button", { name: "Open the profile", exact: true }).click();
  await expect(page).toHaveURL(/\/app\/owner$/);
  await expect(page.locator("#dialog[open]")).toHaveCount(0);
  await expect(page.getByLabel("Name", { exact: true })).toBeVisible();
});

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

/* «ما أعرفه عنك» (8.4): every profile line shows its origin; the owner corrects or deletes one,
   and the server records the change as his own word. */
test("what I know about you lists each line with its origin, corrected or deleted", async ({
  page,
  context,
  owner,
}) => {
  await context.addInitScript(() => {
    localStorage.setItem("lonora.locale", "en");
    localStorage.setItem("lonora.auth.intro-seen", "1");
  });
  const tag = randomUUID().slice(0, 8);
  const profile = await (await context.request.get("/api/owner/profile")).json();
  const written = await context.request.put("/api/owner/profile", {
    data: { content: `- Trades gold ${tag}\n- Short reports ${tag}\n`, version: profile.version },
    headers: owner.headers,
  });
  expect(written.ok()).toBeTruthy();
  seedEarlier(tag, `- Old note ${tag}`);
  await page.goto("/app/owner");
  await expect(page.getByText("What I know about you")).toBeVisible();
  const known = page.locator(".pf-known .row");
  await expect(known.filter({ hasText: `Old note ${tag}` })).toContainText("Earlier");
  const gold = known.filter({ hasText: `Trades gold ${tag}` });
  await expect(gold).toContainText("You said");
  // Typed with its own bullet: the stored line keeps exactly one.
  await gold.getByRole("button", { name: "Correct the fact", exact: true }).click();
  const field = page.getByRole("textbox", { name: "Correct the fact", exact: true });
  await expect(field).toHaveValue(`Trades gold ${tag}`);
  await field.fill(`- Trades silver ${tag}`);
  await page.getByRole("button", { name: "Save", exact: true }).last().click();
  await expect(known.filter({ hasText: `Trades silver ${tag}` })).toContainText("You said");
  // Typed without one: the line's bullet is kept.
  await known
    .filter({ hasText: `Old note ${tag}` })
    .getByRole("button", { name: "Correct the fact", exact: true })
    .click();
  await field.fill(`New note ${tag}`);
  await page.getByRole("button", { name: "Save", exact: true }).last().click();
  await expect(known.filter({ hasText: `New note ${tag}` })).toContainText("You said");
  await known
    .filter({ hasText: `Short reports ${tag}` })
    .getByRole("button", { name: "Delete the fact", exact: true })
    .click();
  await expect(known.filter({ hasText: `Short reports ${tag}` })).toHaveCount(0);
  const lines = await (await context.request.get("/api/owner/profile/lines")).json();
  expect(lines.lines.map((line) => line.text)).toEqual([
    `- Trades silver ${tag}`,
    `- New note ${tag}`,
  ]);
  const revisions = await (await context.request.get("/api/owner/profile/revisions")).json();
  expect(revisions[0]).toMatchObject({ author: "owner", change: "correction" });
});
