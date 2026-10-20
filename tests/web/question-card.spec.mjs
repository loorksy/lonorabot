import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

async function setup(context, locale) {
  const fixture = JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_question_browser.py"], {
      input: JSON.stringify({ locale }),
      encoding: "utf8",
    }),
  );
  await context.addCookies(
    fixture.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript((value) => localStorage.setItem("lonora.locale", value), locale);
  return {
    ...fixture,
    cleanup: () =>
      context.request.delete(`/api/agents/${fixture.agent.id}`, {
        headers: {
          "X-CSRF-Token": fixture.cookies.find((row) => row.name === "lonora_csrf").value,
        },
      }),
  };
}

for (const locale of ["en", "ar"]) {
  test(`informational ${locale} question is a durable message card with an authoritative selected answer`, async ({
    page,
    context,
  }) => {
    const fixture = await setup(context, locale);
    await page.setViewportSize({ width: 390, height: 844 });
    const submissions = [];
    page.on("request", (request) => {
      if (
        request.method() === "POST" &&
        new URL(request.url()).pathname === `/api/threads/${fixture.thread.id}/messages`
      )
        submissions.push(request.postDataJSON());
    });
    try {
      await page.goto(`/app/${fixture.agent.id}?thread=${fixture.thread.id}`);
      const message = page.locator(`[data-message-id="${fixture.question.message_id}"]`);
      const card = message.locator(`[data-question-id="${fixture.question.id}"]`);
      await expect(card).toBeVisible();
      await expect(card.getByText(fixture.question.question, { exact: true })).toBeVisible();
      const option = card.getByRole("button", {
        name: fixture.question.choices[0].label,
        exact: false,
      });
      await expect(option).toBeEnabled();
      expect((await card.boundingBox()).width).toBeGreaterThan(220);
      const response = page.waitForResponse(
        (result) =>
          result.request().method() === "POST" &&
          new URL(result.url()).pathname === `/api/threads/${fixture.thread.id}/messages`,
      );
      await option.click();
      expect((await response).ok()).toBeTruthy();
      await expect(option).toHaveAttribute("aria-pressed", "true");
      await expect(option).toBeDisabled();
      await expect(card.getByRole("button")).toHaveCount(2);
      expect(submissions).toHaveLength(1);
      expect(submissions[0].input_answer).toEqual({
        run_id: fixture.run.id,
        question_id: fixture.question.id,
        choice_id: "analysis",
      });
      const actual = await (await context.request.get(`/api/runs/${fixture.run.id}`)).json();
      expect(actual.input_request.status).toBe("answered");
      expect(actual.input_request.selected_choice_id).toBe("analysis");
      const messages = await (
        await context.request.get(`/api/threads/${fixture.thread.id}/messages`)
      ).json();
      expect(
        messages.filter(
          (row) => row.role === "user" && row.content === fixture.question.choices[0].label,
        ),
      ).toHaveLength(1);
      const grants = await (
        await context.request.get(`/api/agents/${fixture.agent.id}/super-bot`)
      ).json();
      expect(grants).toHaveLength(0);
      const journal = await (await context.request.get("/api/trading/journal")).json();
      expect(
        journal.filter((row) => row.agent_id === fixture.agent.id || row.run_id === fixture.run.id),
      ).toHaveLength(0);
      await page.reload();
      await expect(
        card.getByRole("button", { name: fixture.question.choices[0].label, exact: false }),
      ).toHaveAttribute("aria-pressed", "true");
      await expect(card.getByRole("button").first()).toBeDisabled();
    } finally {
      await fixture.cleanup();
    }
  });
}

test("ordinary free text can answer a card without selecting or granting an option", async ({
  page,
  context,
}) => {
  const fixture = await setup(context, "en");
  try {
    await page.goto(`/app/${fixture.agent.id}?thread=${fixture.thread.id}`);
    const card = page.locator(`[data-question-id="${fixture.question.id}"]`);
    await expect(card).toBeVisible();
    const composer = page.locator("textarea");
    await composer.fill("Please compare both scenarios first");
    await composer.press("Enter");
    await expect(card.getByRole("button").first()).toBeDisabled();
    const current = await (await context.request.get(`/api/runs/${fixture.run.id}`)).json();
    expect(current.input_request.status).toBe("answered");
    expect(current.input_request.selected_choice_id).toBeNull();
  } finally {
    await fixture.cleanup();
  }
});
