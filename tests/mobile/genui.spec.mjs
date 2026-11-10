// M-a (GENUI_PLAN §9.7, §10.2 item 9): on mobile, Stop cancels a queued card submission sent
// from web, like web does, and the submission's bubble shows «لم يُنفَّذ» from the same core
// helper. R1 cards themselves show their fallback text on mobile.
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

const ROOT = fileURLToPath(new URL("../..", import.meta.url));
const python = (command, input = {}) =>
  JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_genui_browser.py", command], {
      cwd: ROOT,
      input: JSON.stringify(input),
      encoding: "utf8",
    }),
  );

test("Expo: Stop cancels a queued card submission and marks it «لم يُنفَّذ»", async ({
  page,
  context,
}) => {
  const fixture = python("setup");
  const csrf = fixture.cookies.find((row) => row.name === "lonora_csrf").value;
  const headers = { "X-CSRF-Token": csrf };
  await context.addCookies(
    fixture.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "ar"));
  await page.setViewportSize({ width: 390, height: 844 });
  try {
    python("stream", { thread_id: fixture.thread.id, connection: fixture.connection, delay: 0 });
    const messages = await (
      await context.request.get(`/api/threads/${fixture.thread.id}/messages`)
    ).json();
    const card = messages.find((row) =>
      row.rich_content?.parts?.some((part) => part.document?.v === 2),
    );
    const blocks = card.rich_content.parts[1].document.blocks;
    // The submission as web sends it: the server queues its own Run.
    const sent = await context.request.post(`/api/threads/${fixture.thread.id}/messages`, {
      headers,
      data: {
        content: "",
        ui_submit: {
          source_message_id: card.id,
          part: 1,
          path: String(blocks.length - 1),
          values: { price: 2400 },
        },
      },
    });
    expect(sent.status()).toBe(202);
    const submitted = (await sent.json()).message;
    await page.goto(`/thread?id=${fixture.thread.id}`);
    // R1: the card shows its fallback text on mobile.
    await expect(page.getByText("أستطيع إنشاء التنبيه.", { exact: false }).first()).toBeVisible();
    await expect(page.getByText(submitted.content)).toBeVisible();
    await page.getByRole("button", { name: "إيقاف", exact: true }).last().click();
    await expect(page.getByTestId("ui-submit-mark")).toHaveText("لم يُنفَّذ");
    const run = await (await context.request.get(`/api/runs/${submitted.ui_submit.run_id}`)).json();
    expect(run.status).toBe("cancelled");
  } finally {
    await context.request.delete(`/api/agents/${fixture.agent.id}`, { headers });
    await context.request.delete(`/api/trading/connections/${fixture.connection}`, { headers });
  }
});
