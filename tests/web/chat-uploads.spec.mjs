import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

/* An attachment on its way (reference uploadMarkup and cancelUpload, Desktop-37 5530-5534): its
   ring and cancel are in the composer's tray while it uploads, and the composer stays free. */
function fixture(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/agent_pages_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}
let data = null;
const errors = [];
test.beforeEach(async ({ page, context }) => {
  data = fixture({ action: "init" });
  data.groups = [];
  data.agents = [];
  await context.addCookies(
    data.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  page.on("pageerror", (error) => errors.push(error.message));
});
test.afterEach(() => {
  expect(errors.splice(0)).toEqual([]);
  if (data) fixture({ ...data, action: "cleanup" });
  data = null;
});

const report = { name: "report.txt", mimeType: "text/plain", buffer: Buffer.alloc(300 * 1024, 97) };

test("an upload shows its ring in the tray, can be cancelled, and leaves the composer free", async ({
  page,
}) => {
  await page.goto(`/app/${data.research.id}`);
  let release = () => {};
  let held = new Promise((resolve) => {
    release = resolve;
  });
  await page.route("**/api/artifacts/upload", async (route) => {
    await held;
    await route.continue().catch(() => {});
  });
  const input = page.locator('form input[type="file"]');
  const tray = page.getByRole("list", { name: "Attachments" });
  await input.setInputFiles(report);
  const chip = tray.locator(".att.file.uploading");
  await expect(chip.locator("b")).toHaveText("report.txt");
  await expect(chip.locator("small")).toHaveText("Uploading · 300 KB");
  await expect(chip.getByRole("progressbar", { name: "Uploading report.txt" })).toBeVisible();
  // The composer is not held by the upload: text can be typed and another file attached.
  await page.getByRole("combobox").fill("The weekly report");
  await expect(
    page.getByRole("button", { name: "Attachments and tools", exact: true }),
  ).toBeEnabled();
  await chip.getByRole("button", { name: "Cancel the upload" }).click();
  await expect(tray).toHaveCount(0);
  await expect(page.locator("#toast")).toHaveText("Upload cancelled");
  await expect(page.getByRole("combobox")).toHaveValue("The weekly report");

  // An upload that finishes becomes an ordinary attachment of the draft.
  held = Promise.resolve();
  release();
  await input.setInputFiles(report);
  const done = tray.locator(".att.file:not(.uploading)");
  await expect(done.locator("b")).toHaveText("report.txt");
  await expect(done.getByRole("button", { name: "Remove report.txt" })).toBeVisible();
  await expect(tray.getByRole("progressbar")).toHaveCount(0);
});

test("a message sent while its file uploads carries the ring; cancelling withdraws it, finishing posts it", async ({
  page,
}) => {
  await page.goto(`/app/${data.research.id}`);
  let release = () => {};
  const held = new Promise((resolve) => {
    release = resolve;
  });
  await page.route("**/api/artifacts/upload", async (route) => {
    await held;
    await route.continue().catch(() => {});
  });
  const posts = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && /\/api\/threads\/[^/]+\/messages$/.test(request.url()))
      posts.push(request.postDataJSON());
  });
  const input = page.locator('form input[type="file"]');
  const tray = page.getByRole("list", { name: "Attachments" });
  const mine = page.locator(".msg.mine");
  const before = await mine.count();
  await input.setInputFiles(report);
  await expect(tray.locator(".att.file.uploading")).toBeVisible();
  await page.getByRole("combobox").fill("The weekly report");
  await page.keyboard.press("Enter");
  // The composer is free at once; the file left the tray with the message, ring and all.
  await expect(page.getByRole("combobox")).toHaveValue("");
  await expect(tray).toHaveCount(0);
  const chip = mine.last().locator(".file-chip.uploading");
  await expect(chip.locator("strong")).toHaveText("report.txt");
  await expect(chip.locator("small")).toHaveText("Uploading · 300 KB");
  await expect(chip.getByRole("progressbar", { name: "Uploading report.txt" })).toBeVisible();
  expect(posts).toEqual([]);
  // Cancelled before it was up: the message was never posted and is gone.
  await chip.getByRole("button", { name: "Cancel the upload" }).click();
  await expect(mine).toHaveCount(before);
  await expect(page.locator("#toast")).toHaveText("Upload cancelled");
  expect(posts).toEqual([]);

  // Sent again and left to finish: posted once, with the uploaded file.
  await input.setInputFiles(report);
  await page.getByRole("combobox").fill("The weekly report");
  await page.keyboard.press("Enter");
  await expect(mine.last().locator(".file-chip.uploading")).toBeVisible();
  release();
  await expect.poll(() => posts.length).toBe(1);
  expect(posts[0].content).toBe("The weekly report");
  expect(posts[0].attachment_ids).toHaveLength(1);
  await expect(page.locator(".file-chip.uploading")).toHaveCount(0);
  await expect(mine.last().locator(".file-chip strong")).toHaveText("report.txt");
});

test("a message whose file fails to upload keeps the owner's words: «Copy text» before «Delete»", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto(`/app/${data.research.id}`);
  let fail = () => {};
  const held = new Promise((resolve) => {
    fail = resolve;
  });
  await page.route("**/api/artifacts/upload", async (route) => {
    await held;
    await route.fulfill({ status: 500, body: "upload failed" }).catch(() => {});
  });
  const posts = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && /\/api\/threads\/[^/]+\/messages$/.test(request.url()))
      posts.push(request.postDataJSON());
  });
  const mine = page.locator(".msg.mine");
  await page.locator('form input[type="file"]').setInputFiles(report);
  await page.getByRole("combobox").fill("Words worth keeping");
  await page.keyboard.press("Enter");
  await expect(mine.last().locator(".file-chip.uploading")).toBeVisible();
  fail();
  // The file never arrived: the message is not sent and cannot be retried.
  await expect(mine.last().locator(".fail-note")).toHaveText("The message was not sent");
  expect(posts).toEqual([]);
  await mine.last().getByRole("button", { name: "The message was not sent. Options" }).click();
  await expect(page.getByRole("menuitem", { name: "Delete" })).toBeVisible();
  await expect(page.getByRole("menuitem", { name: "Retry" })).toHaveCount(0);
  await page.getByRole("menuitem", { name: "Copy text" }).click();
  await expect(page.locator("#toast")).toHaveText("Copied");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe("Words worth keeping");
});

test("a files-only message whose upload fails offers no «Copy text»: nothing was typed", async ({
  page,
}) => {
  await page.goto(`/app/${data.research.id}`);
  let fail = () => {};
  const held = new Promise((resolve) => {
    fail = resolve;
  });
  await page.route("**/api/artifacts/upload", async (route) => {
    await held;
    await route.fulfill({ status: 500, body: "upload failed" }).catch(() => {});
  });
  const mine = page.locator(".msg.mine");
  await page.locator('form input[type="file"]').setInputFiles(report);
  await page.getByRole("combobox").press("Enter");
  await expect(mine.last().locator(".file-chip.uploading")).toBeVisible();
  fail();
  await expect(mine.last().locator(".fail-note")).toHaveText("The message was not sent");
  await mine.last().getByRole("button", { name: "The message was not sent. Options" }).click();
  await expect(page.getByRole("menuitem", { name: "Delete" })).toBeVisible();
  // The body is the «Attached files» placeholder, not the owner's words.
  await expect(page.getByRole("menuitem", { name: "Copy text" })).toHaveCount(0);
});
