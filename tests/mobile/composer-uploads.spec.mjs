// Composer uploads on mobile, as on Web: «+» offers Files and Photos; several files upload at
// once, each with its ring and cancel; a message sent while files upload waits for them and
// goes out with their ids; cancelling a sent message's upload removes the message.
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

async function fixture(context) {
  const data = JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify({ action: "init", empty: true }),
      encoding: "utf8",
    }),
  );
  await context.addCookies(
    data.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  const headers = { "X-CSRF-Token": data.cookies.find((row) => row.name === "lonora_csrf").value };
  const agent = await (
    await context.request.post("/api/agents", {
      headers,
      data: {
        name: `Uploads ${randomUUID()}`,
        trading_account_id: data.account,
        trading_symbol: data.symbol,
      },
    })
  ).json();
  const thread = await (
    await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
  ).json();
  return {
    agent,
    thread,
    remove: () => context.request.delete(`/api/agents/${agent.id}`, { headers }),
  };
}
const file = (name) => ({
  name,
  mimeType: "text/plain",
  buffer: Buffer.from(`content of ${name}`),
});

async function held(page) {
  const waiting = [];
  const ids = new Map();
  await page.route("**/api/artifacts/upload", async (route) => {
    const id = randomUUID();
    // The picked file's name, from the multipart body: which id belongs to which file.
    ids.set(/filename="([^"]+)"/.exec(route.request().postData() ?? "")?.[1], id);
    await new Promise((resolve) => waiting.push(resolve));
    await route.fulfill({
      status: 201,
      json: {
        id,
        kind: "file",
        agent_id: null,
        thread_id: null,
        payload: { name: `uploaded-${waiting.length}`, media_type: "text/plain", size: 10 },
        version: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    });
  });
  return {
    idOf: (name) => ids.get(name),
    count: () => waiting.length,
    release: () => {
      for (const resolve of waiting.splice(0)) resolve();
    },
  };
}
async function choose(page, names) {
  await page.getByRole("button", { name: "Attach file", exact: true }).click();
  await expect(page.getByText("Add to the conversation", { exact: true })).toBeVisible();
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Files", exact: true }).click();
  await (await chooser).setFiles(names.map(file));
}

test("several files upload at once with rings; a cancelled one leaves; the rest go with the message", async ({
  page,
  context,
}) => {
  const data = await fixture(context);
  const uploads = await held(page);
  const posted = [];
  await page.route(`**/api/threads/${data.thread.id}/messages`, async (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: [] });
    posted.push(route.request().postDataJSON());
    return route.fulfill({ status: 503, json: { code: "request_failed" } });
  });
  try {
    await page.goto(`/thread?id=${data.thread.id}`);
    await choose(page, ["a.txt", "b.txt"]);
    await expect(page.getByTestId("composer-upload")).toHaveCount(2);
    await expect(page.getByRole("progressbar", { name: "Uploading a.txt" })).toBeVisible();
    await expect.poll(uploads.count).toBe(2);
    await page
      .getByRole("button", { name: "Cancel the upload: Uploading b.txt", exact: true })
      .click();
    await expect(page.getByTestId("composer-upload")).toHaveCount(1);
    uploads.release();
    await expect(page.getByTestId("composer-upload")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^Remove attachment: / })).toHaveCount(1);
    await page.getByRole("textbox", { name: "Message…", exact: true }).fill("Here is the file");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0].attachment_ids).toEqual([uploads.idOf("a.txt")]);
  } finally {
    await data.remove();
  }
});

test("a message sent while its file uploads waits, then goes out with the file", async ({
  page,
  context,
}) => {
  const data = await fixture(context);
  const uploads = await held(page);
  const posted = [];
  await page.route(`**/api/threads/${data.thread.id}/messages`, async (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: [] });
    posted.push(route.request().postDataJSON());
    return route.fulfill({ status: 503, json: { code: "request_failed" } });
  });
  try {
    await page.goto(`/thread?id=${data.thread.id}`);
    await choose(page, ["report.txt"]);
    await expect.poll(uploads.count).toBe(1);
    await page.getByRole("textbox", { name: "Message…", exact: true }).fill("Read this report");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(page.getByTestId("composer-upload")).toHaveCount(0);
    const transcript = page.getByTestId("conversation-transcript");
    await expect(transcript.getByText("Uploading…", { exact: true })).toBeVisible();
    expect(posted).toHaveLength(0);
    uploads.release();
    await expect.poll(() => posted.length).toBe(1);
    expect(posted[0].content).toBe("Read this report");
    expect(posted[0].attachment_ids).toEqual([uploads.idOf("report.txt")]);
  } finally {
    await data.remove();
  }
});

test("cancelling a sent message's upload removes the message; nothing is posted", async ({
  page,
  context,
}) => {
  const data = await fixture(context);
  const uploads = await held(page);
  const posted = [];
  await page.route(`**/api/threads/${data.thread.id}/messages`, async (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: [] });
    posted.push(route.request().postDataJSON());
    return route.fulfill({ status: 503, json: { code: "request_failed" } });
  });
  try {
    await page.goto(`/thread?id=${data.thread.id}`);
    await choose(page, ["late.txt"]);
    await expect.poll(uploads.count).toBe(1);
    await page.getByRole("textbox", { name: "Message…", exact: true }).fill("Never mind");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    const transcript = page.getByTestId("conversation-transcript");
    await transcript
      .getByRole("button", { name: "Cancel the upload: Uploading…", exact: true })
      .click();
    await expect(transcript.getByText("Never mind", { exact: true })).toHaveCount(0);
    uploads.release();
    await page.waitForTimeout(500);
    expect(posted).toHaveLength(0);
  } finally {
    await data.remove();
  }
});

test("a sent message whose file fails to upload comes back to the composer; nothing is posted", async ({
  page,
  context,
}) => {
  const data = await fixture(context);
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  await page.route("**/api/artifacts/upload", async (route) => {
    // ok.txt arrives at once; broken.txt fails once released.
    if ((route.request().postData() ?? "").includes('filename="ok.txt"'))
      return route.fulfill({
        status: 201,
        json: {
          id: randomUUID(),
          kind: "file",
          agent_id: null,
          thread_id: null,
          payload: { name: "ok.txt", media_type: "text/plain", size: 10 },
          version: 1,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      });
    await gate;
    await route.fulfill({ status: 500, json: { code: "request_failed" } });
  });
  const posted = [];
  await page.route(`**/api/threads/${data.thread.id}/messages`, async (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: [] });
    posted.push(route.request().postDataJSON());
    return route.fulfill({ status: 503, json: { code: "request_failed" } });
  });
  try {
    await page.goto(`/thread?id=${data.thread.id}`);
    await choose(page, ["ok.txt", "broken.txt"]);
    await expect(page.getByRole("button", { name: "Remove attachment: ok.txt" })).toBeVisible();
    await expect(page.getByTestId("composer-upload")).toHaveCount(1);
    const composer = page.getByRole("textbox", { name: "Message…", exact: true });
    await composer.fill("With a broken file");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    const transcript = page.getByTestId("conversation-transcript");
    await expect(transcript.getByText("Uploading…", { exact: true })).toBeVisible();
    await expect(composer).toHaveValue("");
    release();
    // The owner's text is back in the composer; the unsent bubble is gone.
    await expect(composer).toHaveValue("With a broken file");
    // The file that was already up comes back with it.
    await expect(page.getByRole("button", { name: "Remove attachment: ok.txt" })).toBeVisible();
    await expect(transcript.getByText("With a broken file", { exact: true })).toHaveCount(0);
    expect(posted).toHaveLength(0);
  } finally {
    await data.remove();
  }
});
