import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

function response(locale) {
  const ar = locale === "ar";
  const labels = {
    intro: ar ? "حاسبة محلية للتوضيح فقط." : "A local calculator for illustration only.",
    outro: ar ? "هذه الافتراضات لا تنفذ أي صفقة." : "These assumptions do not execute a trade.",
    budget: ar ? "ميزانية المثال" : "Example budget",
    risk: ar ? "نسبة المثال" : "Example percentage",
    result: ar ? "القيمة المحسوبة" : "Calculated amount",
    include: ar ? "عرض التفاصيل" : "Show details",
    details: ar ? "الافتراضات" : "Assumptions",
    detailText: ar
      ? "قيم توضيحية، وليست بيانات حسابك."
      : "Illustrative values, not your account data.",
    follow: ar ? "اشرح النتيجة" : "Explain the result",
    filter: ar ? "جدول المثال" : "Example table",
  };
  const document = {
    version: 1,
    mode: "example",
    state: { budget: 1000, risk: 2, show: true, period: "daily", tab: "a", filter: "" },
    root: {
      id: "calculator",
      type: "column",
      children: [
        { id: "title", type: "heading", text: labels.budget, level: 2 },
        {
          id: "budget",
          type: "input",
          label: labels.budget,
          state_key: "budget",
          input_kind: "number",
          minimum: 0,
          maximum: 100000,
          step: 1,
        },
        {
          id: "risk",
          type: "slider",
          label: labels.risk,
          state_key: "risk",
          minimum: 0,
          maximum: 10,
          step: 1,
        },
        {
          id: "result",
          type: "metric",
          label: labels.result,
          value: {
            op: "div",
            args: [{ op: "mul", args: [{ state: "budget" }, { state: "risk" }] }, 100],
          },
          unit: "USD",
        },
        { id: "toggle", type: "checkbox", label: labels.include, state_key: "show" },
        { id: "visible", type: "text", text: labels.detailText, visible: { state: "show" } },
        {
          id: "period",
          type: "select",
          label: ar ? "المدة" : "Period",
          state_key: "period",
          options: [
            { value: "daily", label: ar ? "يومي" : "Daily" },
            { value: "weekly", label: ar ? "أسبوعي" : "Weekly" },
          ],
        },
        {
          id: "tabs",
          type: "tabs",
          state_key: "tab",
          options: [
            { value: "a", label: ar ? "الأول" : "First" },
            { value: "b", label: ar ? "الثاني" : "Second" },
          ],
          children: [
            { id: "first", type: "text", text: "Alpha" },
            { id: "second", type: "text", text: "Beta" },
          ],
        },
        {
          id: "table",
          type: "table",
          label: labels.filter,
          filter_key: "filter",
          fields: [
            { key: "name", label: ar ? "الاسم" : "Name" },
            { key: "value", label: ar ? "القيمة" : "Value" },
          ],
          rows: [
            { name: "Sample A", value: 10 },
            { name: "Sample B", value: 20 },
          ],
        },
        {
          id: "chart",
          type: "chart",
          label: ar ? "مسار المثال" : "Example trend",
          chart_kind: "line",
          points: [
            { label: "A", value: 10 },
            { label: "B", value: 20 },
          ],
        },
        {
          id: "diagram",
          type: "diagram",
          label: ar ? "المسار" : "Flow",
          vertices: [
            { id: "input", label: ar ? "المدخلات" : "Inputs" },
            { id: "output", label: ar ? "النتيجة" : "Result" },
          ],
          edges: [{ source: "input", target: "output" }],
        },
        {
          id: "details",
          type: "disclosure",
          label: labels.details,
          children: [{ id: "detail", type: "text", text: "No broker action" }],
        },
        {
          id: "follow",
          type: "button",
          label: labels.follow,
          action: {
            kind: "follow_up",
            text: "Explain this illustrative calculation at {{budget}} and {{risk}}%.",
          },
        },
      ],
    },
  };
  return {
    labels,
    document,
    rich: {
      version: 1,
      parts: [
        { type: "text", text: labels.intro },
        { type: "ui", document },
        { type: "text", text: labels.outro },
      ],
    },
  };
}

for (const locale of ["en", "ar"]) {
  for (const theme of ["dark", "light"]) {
    test(`Expo native ${locale} ${theme}: mixed visuals, local interaction and reopen`, async ({
      page,
      context,
    }) => {
      test.setTimeout(60000);
      const fixture = JSON.parse(
        execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
          input: JSON.stringify({ action: "init", empty: true }),
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
      await page.emulateMedia({ colorScheme: theme });
      await context.addInitScript(
        ({ locale, theme }) => {
          localStorage.setItem("lonora.locale", locale);
          document.documentElement.setAttribute("data-theme", theme);
        },
        { locale, theme },
      );
      const headers = {
        "X-CSRF-Token": fixture.cookies.find((row) => row.name === "lonora_csrf").value,
      };
      const agentResponse = await context.request.post("/api/agents", {
        headers,
        data: {
          name: `Native visual ${randomUUID()}`,
          trading_account_id: fixture.account,
          trading_symbol: fixture.symbol,
        },
      });
      expect(agentResponse.ok()).toBeTruthy();
      const agent = await agentResponse.json();
      const thread = await (
        await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
      ).json();
      const { labels, rich } = response(locale);
      const message = {
        id: randomUUID(),
        seq: 1,
        thread_id: thread.id,
        agent_id: agent.id,
        role: "assistant",
        content: "Legacy fallback only",
        attachment_ids: [],
        reply_to: null,
        created_at: new Date().toISOString(),
        rich_content: rich,
      };
      await page.route(`**/api/threads/${thread.id}/messages`, async (route) =>
        route.request().method() === "GET" ? route.fulfill({ json: [message] }) : route.continue(),
      );
      const posts = [];
      page.on("request", (request) => {
        if (
          request.method() === "POST" &&
          new URL(request.url()).pathname === `/api/threads/${thread.id}/messages`
        )
          posts.push(request.postDataJSON());
      });
      try {
        await page.goto(`/thread?id=${thread.id}`);
        const visual = page.getByTestId("native-visual-calculator");
        await expect(visual).toBeVisible();
        await expect(page.getByText("Legacy fallback only", { exact: true })).toHaveCount(0);
        await expect(page.getByText(labels.intro, { exact: true })).toHaveCount(1);
        await expect(page.getByText(labels.outro, { exact: true })).toHaveCount(1);
        await expect(
          visual.getByText(locale === "ar" ? "مثال توضيحي" : "Illustrative example", {
            exact: true,
          }),
        ).toBeVisible();
        const budget = visual.getByRole("textbox", { name: labels.budget, exact: true });
        await budget.fill(locale === "ar" ? "٢٠٠٠" : "2000");
        await budget.blur();
        await expect(visual.getByText("40 USD", { exact: true })).toBeVisible();
        await visual.getByRole("button", { name: `${labels.risk} +`, exact: true }).click();
        await expect(visual.getByText("60 USD", { exact: true })).toBeVisible();
        await visual.getByRole("switch", { name: labels.include, exact: true }).click();
        await expect(visual.getByText(labels.detailText, { exact: true })).toHaveCount(0);
        await visual
          .getByRole("radio", { name: locale === "ar" ? "أسبوعي" : "Weekly", exact: true })
          .click();
        await visual
          .getByRole("tab", { name: locale === "ar" ? "الثاني" : "Second", exact: true })
          .click();
        await expect(visual.getByText("Beta", { exact: true })).toBeVisible();
        await expect(visual.getByText("Alpha", { exact: true })).toHaveCount(0);
        await visual
          .getByRole("textbox", {
            name: `${locale === "ar" ? "تصفية" : "Filter"} ${labels.filter}`,
            exact: true,
          })
          .fill("Sample B");
        await expect(visual.getByText("Sample A", { exact: true })).toHaveCount(0);
        await expect(visual.getByText("Sample B", { exact: true })).toBeVisible();
        await visual.getByRole("button", { name: labels.details, exact: true }).click();
        await expect(visual.getByText("No broker action", { exact: true })).toBeVisible();
        expect(posts).toHaveLength(0);
        await expect
          .poll(() =>
            visual.evaluate((element) => element.getBoundingClientRect().width <= innerWidth),
          )
          .toBeTruthy();
        const color = await visual.evaluate((element) => getComputedStyle(element).backgroundColor);
        expect(color).toBe(theme === "dark" ? "rgb(11, 12, 14)" : "rgb(250, 250, 248)");
        await expect
          .poll(() =>
            page.evaluate(
              () =>
                Object.keys(localStorage).filter((key) => key.startsWith("lonora.visual.")).length,
            ),
          )
          .toBeGreaterThan(0);
        await page.reload();
        await expect(visual.getByText("60 USD", { exact: true })).toBeVisible();
        await expect(visual.getByText("No broker action", { exact: true })).toBeVisible();
        await expect(
          visual.getByRole("radio", { name: locale === "ar" ? "أسبوعي" : "Weekly", exact: true }),
        ).toHaveAttribute("aria-checked", "true");
        expect(posts).toHaveLength(0);
        if (locale === "en" && theme === "dark") {
          const sent = page.waitForResponse(
            (result) =>
              result.request().method() === "POST" &&
              new URL(result.url()).pathname === `/api/threads/${thread.id}/messages`,
          );
          await visual.getByRole("button", { name: labels.follow, exact: true }).click();
          expect((await sent).ok()).toBeTruthy();
          expect(posts).toHaveLength(1);
          expect(posts[0].content).toBe("Explain this illustrative calculation at 2000 and 3%.");
          expect(posts[0].client_nonce).toBeTruthy();
          expect(posts[0].attachment_ids).toEqual([]);
          expect(posts[0]).not.toHaveProperty("approval");
          const journal = await (await context.request.get("/api/trading/journal")).json();
          expect(journal.filter((row) => row.agent_id === agent.id)).toHaveLength(0);
          const grants = await (
            await context.request.get(`/api/agents/${agent.id}/super-bot`)
          ).json();
          expect(grants).toHaveLength(0);
        }
        await page.screenshot({
          path: test.info().outputPath(`native-visual-${locale}-${theme}.png`),
          fullPage: true,
        });
      } finally {
        await context.request.delete(`/api/agents/${agent.id}`, { headers });
      }
    });
  }
}
