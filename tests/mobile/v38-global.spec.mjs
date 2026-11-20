import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

/* The v38 design pass on mobile, global patterns: the first launch follows the device's theme
   (a saved choice still wins), the list filters keep a 44px tap area, a setting beside a switch
   is never cut, and a message in Latin letters only reads left-to-right. */
function fixture() {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify({ action: "init", empty: true }),
      encoding: "utf8",
    }),
  );
}
async function signIn(context, data) {
  await context.addCookies(
    data.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  // No saved theme: the first launch follows the device.
  await context.addInitScript(() => localStorage.setItem("lonora.locale", "en"));
  return { "X-CSRF-Token": data.cookies.find((row) => row.name === "lonora_csrf").value };
}
const painted = (page, color) =>
  page.evaluate(
    (color) =>
      [...document.querySelectorAll("div")].some(
        (node) => getComputedStyle(node).backgroundColor === color,
      ),
    color,
  );

test.describe("on a light device", () => {
  test.use({ colorScheme: "light" });
  test("the first launch is light and the filter chips answer over 44px", async ({
    page,
    context,
  }) => {
    const data = fixture();
    try {
      await signIn(context, data);
      await page.goto("/");
      const filters = page.getByRole("toolbar", { name: "Filter chats" });
      await filters.scrollIntoViewIfNeeded();
      await expect(filters).toBeVisible();
      await expect.poll(() => painted(page, "rgb(247, 245, 239)")).toBe(true);
      expect(await painted(page, "rgb(11, 12, 16)")).toBe(false);
      // The chips are 44px tall inside a 45px bar (its 1px line).
      const chip = filters.getByRole("button").first();
      expect((await chip.boundingBox()).height).toBeGreaterThanOrEqual(44);
      expect(Math.round((await filters.boundingBox()).height)).toBe(45);
    } finally {
      execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
        input: JSON.stringify({ ...data, action: "cleanup" }),
        encoding: "utf8",
      });
    }
  });
});

test("a switch row is never cut; a Latin-only message reads left-to-right", async ({
  page,
  context,
}) => {
  const data = fixture();
  try {
    const headers = await signIn(context, data);
    const agent = await (
      await context.request.post("/api/agents", {
        headers,
        data: {
          name: `V38 ${randomUUID().slice(0, 6)}`,
          trading_account_id: data.account,
          trading_symbol: data.symbol,
        },
      })
    ).json();
    const thread = await (
      await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
    ).json();
    const row = (seq, content) => ({
      id: `v38-${seq}`,
      thread_id: thread.id,
      agent_id: agent.id,
      seq,
      role: "assistant",
      content,
      reply_to: null,
      attachment_ids: [],
      created_at: "2026-11-19T10:00:00Z",
    });
    await page.route(`**/api/threads/${thread.id}/messages*`, (route) =>
      route.fulfill({ json: [row(1, "Hello, ready?"), row(2, "XAUUSD ارتفع (+$239)")] }),
    );
    await page.setViewportSize({ width: 320, height: 720 });
    await page.goto(`/thread?id=${thread.id}`);
    const latin = page.getByText("Hello, ready?", { exact: true });
    await expect(latin).toBeVisible();
    expect(await latin.evaluate((node) => getComputedStyle(node).direction)).toBe("ltr");
    // One Arabic letter keeps the message right-to-left; its signed number stays whole.
    const arabic = page.getByText("XAUUSD ارتفع (\u2066+$239\u2069)", { exact: true });
    expect(await arabic.evaluate((node) => getComputedStyle(node).direction)).toBe("rtl");

    await page.getByRole("button", { name: "Agent actions", exact: true }).click();
    await page.getByText("Chat experience", { exact: true }).click();
    const status = page.getByTestId("chat-pref-agentStatus");
    await expect(status).toBeVisible();
    // No line clamp on the explanation beside a switch, even at 320px.
    expect(
      await status.evaluate((node) =>
        [...node.querySelectorAll("*")].every(
          (child) => getComputedStyle(child).webkitLineClamp === "none",
        ),
      ),
    ).toBe(true);
  } finally {
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify({ ...data, action: "cleanup" }),
      encoding: "utf8",
    });
  }
});

test("Arabic: the page says its language", async ({ page, context }) => {
  const data = fixture();
  try {
    await signIn(context, data);
    await context.addInitScript(() => localStorage.setItem("lonora.locale", "ar"));
    await page.goto("/");
    await expect(page.locator("html")).toHaveAttribute("lang", "ar");
  } finally {
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify({ ...data, action: "cleanup" }),
      encoding: "utf8",
    });
  }
});

test("the tab says «Attention»; the held line and the live chip read whole; the transcript keeps a column", async ({
  page,
  context,
}) => {
  test.setTimeout(60000);
  const data = fixture();
  try {
    const headers = await signIn(context, data);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    // The tab says «Attention»; the button keeps the full words.
    const tab = page.getByTestId("tab-updates");
    await expect(tab).toHaveAttribute("aria-label", /^Needs your attention/);
    await expect(tab.getByText("Attention", { exact: true })).toBeVisible();
    // The Agents list's chevron, drawn for Arabic, points the English way.
    await page.goto("/agents");
    const chevron = page.locator('path[d="M14 6l-6 6 6 6"]').first();
    await expect(chevron).toHaveCount(1);
    expect(
      await chevron.evaluate((node) => {
        let element = node;
        while (element && getComputedStyle(element).transform === "none")
          element = element.parentElement;
        return element ? getComputedStyle(element).transform : "none";
      }),
    ).toBe("matrix(-1, 0, 0, 1, 0, 0)");

    const agent = await (
      await context.request.post("/api/agents", {
        headers,
        data: {
          name: `V38 ${randomUUID().slice(0, 6)}`,
          trading_account_id: data.account,
          trading_symbol: data.symbol,
        },
      })
    ).json();
    const thread = await (
      await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
    ).json();
    const rows = Array.from({ length: 40 }, (_, index) => ({
      id: `v38-${index + 1}`,
      thread_id: thread.id,
      agent_id: agent.id,
      seq: index + 1,
      role: "assistant",
      content: `Row ${index + 1}`,
      reply_to: null,
      attachment_ids: [],
      created_at: "2026-11-19T10:00:00Z",
    }));
    await page.route(`**/api/threads/${thread.id}/messages*`, (route) =>
      route.fulfill({ json: rows }),
    );
    // A trade the broker has not confirmed: the held line and a problem in the live chip.
    await page.route(`**/api/agents/${agent.id}/state*`, async (route) => {
      const response = await route.fetch();
      const state = await response.json();
      const readiness = state.trading_readiness ?? {};
      await route.fulfill({
        response,
        json: {
          ...state,
          state: "degraded",
          trading_readiness: {
            ...readiness,
            state: "uncertain",
            params: { ...(readiness.params ?? {}), count: 1, symbol: "XAUUSD" },
          },
        },
      });
    });
    await page.goto(`/thread?id=${thread.id}`);
    const held = page.getByTestId("safety-pill").getByText(/held$/);
    await expect(held).toBeVisible();
    expect(
      await held.evaluate(
        (el) => el.scrollWidth <= el.clientWidth + 1 && el.scrollHeight <= el.clientHeight + 1,
      ),
    ).toBe(true);
    // The chip's words take the text color; its amber stays on the dot and the arrow.
    const words = page.getByTestId("agent-live-state").getByText(/^Background activity/);
    await expect(words).toBeVisible();
    const color = (locator) => locator.evaluate((el) => getComputedStyle(el).color);
    expect(await color(words)).toBe(await color(held));

    // Scrolled back, the way to the latest message is a down chevron.
    await expect(page.getByText("Row 40", { exact: true })).toBeVisible();
    await page.getByTestId("conversation-transcript").evaluate((el) => {
      el.scrollTop = 600;
      el.dispatchEvent(new Event("scroll"));
    });
    const jump = page.getByRole("button", { name: "Jump to latest" });
    await expect(jump).toBeVisible();
    await expect(jump.locator("path")).toHaveAttribute("d", "M6 9l6 6 6-6");
    await jump.click();

    // On a wide screen the transcript keeps Web's column instead of the window's width.
    await page.setViewportSize({ width: 1280, height: 800 });
    const latest = page.getByText("Row 40", { exact: true });
    await expect(latest).toBeVisible();
    expect((await latest.boundingBox()).x).toBeGreaterThanOrEqual((1280 - 792) / 2);
  } finally {
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify({ ...data, action: "cleanup" }),
      encoding: "utf8",
    });
  }
});
