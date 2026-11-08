import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

function simulation(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}

async function setup(context, locale = "en") {
  const data = simulation({ action: "init", empty: true });
  await context.addCookies(
    data.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript((value) => localStorage.setItem("lonora.locale", value), locale);
  const headers = { "X-CSRF-Token": data.cookies.find((row) => row.name === "lonora_csrf").value };
  const original = await (await context.request.get("/api/trading/controls")).json();
  // A simulation account with a fresh quote, so owner market orders pass execution quality.
  const connected = await context.request.post("/api/trading/connections", {
    headers,
    data: { provider: "simulation", account_id: `safety-${randomUUID()}`, enabled: true },
  });
  expect(connected.status()).toBe(201);
  const account = (await connected.json()).id;
  const imported = await context.request.post(`/api/trading/connections/${account}/simulation`, {
    headers,
    data: {
      snapshot: {
        balance: "10000",
        currency: "USD",
        instruments: [
          {
            symbol: data.symbol,
            digits: 2,
            tick_size: "0.01",
            volume_min: "0.01",
            volume_max: "100",
            volume_step: "0.01",
          },
        ],
        quotes: {
          [data.symbol]: {
            symbol: data.symbol,
            bid: "160",
            ask: "161",
            observed_at: new Date().toISOString(),
            source: "simulation/ui-fixture",
          },
        },
      },
    },
  });
  expect(imported.ok()).toBeTruthy();
  const controls = async (value) => {
    const response = await context.request.put("/api/trading/controls", { headers, data: value });
    expect(response.ok()).toBeTruthy();
  };
  return {
    data: { ...data, account },
    headers,
    controls,
    read: async () => (await context.request.get("/api/trading/controls")).json(),
    async cleanup() {
      await controls(original);
      await context.request.delete(`/api/trading/connections/${account}`, { headers });
      simulation({ ...data, action: "cleanup" });
    },
  };
}

test("owner close: a double click and a retry after a timeout make exactly one operation", async ({
  page,
  context,
}) => {
  test.setTimeout(60000);
  const state = await setup(context);
  try {
    await state.controls({ enabled: true, emergency_stop: false });
    for (let index = 0; index < 2; index += 1) {
      const opened = await context.request.post("/api/trading/execute", {
        headers: state.headers,
        data: {
          account_id: state.data.account,
          operation_id: randomUUID(),
          action: "buy",
          symbol: state.data.symbol,
          volume: "0.10",
        },
      });
      expect(opened.ok()).toBeTruthy();
      expect((await opened.json()).status).toBe("confirmed");
    }
    const snapshot = await (
      await context.request.get(`/api/trading/accounts/${state.data.account}`)
    ).json();
    expect(snapshot.positions).toHaveLength(2);
    const [first, second] = snapshot.positions;
    // The owner keeps looking at the list as it was: the rows stay while closes settle.
    await page.route(`**/api/trading/accounts/${state.data.account}`, (route) =>
      route.fulfill({ json: snapshot }),
    );
    const sent = [];
    let dropped = false;
    await page.route("**/api/trading/execute", async (route) => {
      const body = route.request().postDataJSON();
      sent.push(body);
      if (body.position_id === first.id && !dropped) {
        dropped = true;
        // The server records the close, but the browser never hears back.
        await route.fetch();
        await route.abort("timedout");
        return;
      }
      await route.continue();
    });
    await page.goto("/app/trading");
    const control = page.getByTestId("trading-control");
    await expect(control.getByRole("status")).toHaveText("New trading is running");
    await expect(control.getByRole("button")).toHaveCount(1);
    await expect(control.getByRole("button", { name: "Stop new trading" })).toBeVisible();
    await page.getByLabel("Broker account").selectOption(state.data.account);

    const firstRow = page.locator(`[data-position-id="${first.id}"]`);
    await firstRow.getByRole("button", { name: "Close position", exact: true }).click();
    await expect(page.getByRole("alert").first()).toBeVisible();
    // The identity is kept: the button now asks the journal instead of closing again.
    const retry = firstRow.getByRole("button", { name: "Check close result", exact: true });
    await expect(retry).toBeEnabled();
    await retry.click();
    await expect(firstRow.locator('[data-operation-status="confirmed"]')).toHaveText("Confirmed");

    const secondRow = page.locator(`[data-position-id="${second.id}"]`);
    await secondRow.getByRole("button", { name: "Close position", exact: true }).dblclick();
    await expect(secondRow.locator('[data-operation-status="confirmed"]')).toHaveText("Confirmed");

    const forFirst = sent.filter((body) => body.position_id === first.id);
    const forSecond = sent.filter((body) => body.position_id === second.id);
    expect(forFirst).toHaveLength(2);
    expect(new Set(forFirst.map((body) => body.operation_id)).size).toBe(1);
    expect(forSecond).toHaveLength(1);
    const journal = await (
      await context.request.get(`/api/trading/journal?account_id=${state.data.account}`)
    ).json();
    const closes = (id) =>
      journal.filter(
        (row) => row.request.action === "close_position" && row.request.position_id === id,
      );
    expect(closes(first.id)).toHaveLength(1);
    expect(closes(first.id)[0].operation_id).toBe(forFirst[0].operation_id);
    expect(closes(second.id)).toHaveLength(1);
    expect(closes(second.id)[0].operation_id).toBe(forSecond[0].operation_id);
  } finally {
    await state.cleanup();
  }
});

test("header safety pill: one line, one brake, Resume in one call", async ({ page, context }) => {
  test.setTimeout(60000);
  const state = await setup(context);
  const response = await context.request.post("/api/agents", {
    headers: state.headers,
    data: {
      name: `Safety pill ${randomUUID()}`,
      trading_account_id: state.data.account,
      trading_symbol: state.data.symbol,
    },
  });
  expect(response.status()).toBe(201);
  const agent = await response.json();
  try {
    await state.controls({ enabled: false, emergency_stop: false });
    const permissions = await (
      await context.request.get(`/api/agents/${agent.id}/permissions`)
    ).json();
    const changed = await context.request.put(`/api/agents/${agent.id}/permissions`, {
      headers: state.headers,
      data: { level: "supervised", expected_revision: permissions.revision },
    });
    expect(changed.ok()).toBeTruthy();
    const writes = [];
    page.on("request", (request) => {
      if (request.method() === "PUT" && request.url().endsWith("/api/trading/controls"))
        writes.push(request.postDataJSON());
    });
    await page.goto(`/app/${agent.id}`);
    const pill = page.getByTestId("safety-pill");
    await expect(pill).toHaveAttribute("data-readiness", "stopped");
    await expect(pill).toHaveText("New trading stopped · exits allowed");
    await pill.click();
    const sheet = page.getByTestId("safety-sheet");
    await expect(sheet.locator('[data-trading-state="stopped"]')).toContainText(
      "New trading is stopped",
    );
    await expect(sheet.getByText("Ask me", { exact: true })).toBeVisible();
    await expect(sheet.getByText("No pauses", { exact: true })).toBeVisible();
    await expect(sheet.getByText("No money limit set", { exact: true })).toBeVisible();
    await expect(sheet.getByText("No operation is waiting for the broker.")).toBeVisible();
    await sheet.getByRole("button", { name: "Resume trading", exact: true }).click();
    await expect(pill).toHaveText("Asks you before each trade");
    expect(writes).toEqual([{ enabled: true, emergency_stop: false }]);
    expect(await state.read()).toEqual({ enabled: true, emergency_stop: false });
    await expect(sheet.locator('[data-trading-state="running"]')).toContainText(
      "New trading is running",
    );
    await sheet.getByRole("button", { name: "Stop new trading", exact: true }).click();
    await expect(pill).toHaveAttribute("data-readiness", "stopped");
    expect(writes.at(-1)).toEqual({ enabled: false, emergency_stop: true });
    expect(await state.read()).toEqual({ enabled: false, emergency_stop: true });
  } finally {
    await context.request.delete(`/api/agents/${agent.id}`, { headers: state.headers });
    await state.cleanup();
  }
});
