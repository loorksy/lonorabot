import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

for (const locale of ["en", "ar"]) {
  test(`Expo ${locale} informational choices resolve the original durable message`, async ({
    page,
    context,
  }) => {
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
    await page.setViewportSize({ width: 390, height: 844 });
    const headers = {
      "X-CSRF-Token": fixture.cookies.find((row) => row.name === "lonora_csrf").value,
    };
    const submissions = [];
    page.on("request", (request) => {
      if (
        request.method() === "POST" &&
        new URL(request.url()).pathname === `/api/threads/${fixture.thread.id}/messages`
      )
        submissions.push(request.postDataJSON());
    });
    try {
      await page.goto(`/thread?id=${fixture.thread.id}`);
      const card = page.getByTestId(`question-${fixture.question.id}`);
      await expect(card).toBeVisible();
      await expect(card.getByText(fixture.question.question, { exact: true })).toBeVisible();
      const option = card.getByRole("button", {
        name: fixture.question.choices[0].label,
        exact: true,
      });
      await expect(option).toBeEnabled();
      const response = page.waitForResponse(
        (result) =>
          result.request().method() === "POST" &&
          new URL(result.url()).pathname === `/api/threads/${fixture.thread.id}/messages`,
      );
      await option.click();
      expect((await response).ok()).toBeTruthy();
      await expect(option).toHaveAttribute("aria-selected", "true");
      await expect(option).toBeDisabled();
      expect(submissions).toHaveLength(1);
      expect(submissions[0].input_answer).toEqual({
        run_id: fixture.run.id,
        question_id: fixture.question.id,
        choice_id: "analysis",
      });
      const current = await (await context.request.get(`/api/runs/${fixture.run.id}`)).json();
      expect(current.input_request.status).toBe("answered");
      expect(current.input_request.selected_choice_id).toBe("analysis");
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
        card.getByRole("button", { name: fixture.question.choices[0].label, exact: true }),
      ).toHaveAttribute("aria-selected", "true");
      await expect(card.getByRole("button").first()).toBeDisabled();
      await expect(page.getByRole("alert")).toHaveCount(0);
    } finally {
      await context.request.delete(`/api/agents/${fixture.agent.id}`, { headers });
    }
  });
}
