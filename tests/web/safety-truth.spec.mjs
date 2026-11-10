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

// Durable close rows on the owner's own positions, as an earlier tab left them.
function seedCloses(data) {
  const script = `
import asyncio,json,sys
from uuid import uuid4
sys.path.insert(0,'tests')
from check_streaming import Fixture
from lonora_contracts.domain import utcnow
from lonora_contracts.trading import TradeRequest
from lonora_db.schema import TradingJournalRow
from lonora_trading.idempotency import trade_fingerprint
async def main():
    data=json.load(sys.stdin)
    f=await Fixture().open()
    try:
        rows={}
        async with f.runtime.db.sessions() as session, session.begin():
            for position,status,code in data['rows']:
                operation=str(uuid4())
                request=TradeRequest(account_id=data['account'],operation_id=operation,action='close_position',symbol=data['symbol'],position_id=position)
                session.add(TradingJournalRow(operation_id=operation,owner_id=f.owner,account_id=data['account'],request_hash=trade_fingerprint(request),request=request.model_dump(mode='json'),status=status,result={'status':status,'code':code,'details':{}},submitted_at=utcnow(),updated_at=utcnow()))
                rows[position]=operation
        print(json.dumps(rows))
    finally:
        await f.close(cleanup=False)
asyncio.run(main())
`;
  return JSON.parse(
    execFileSync(".venv/bin/python", ["-c", script], {
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

async function openPositions(context, state, count) {
  for (let index = 0; index < count; index += 1) {
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
  expect(snapshot.positions).toHaveLength(count);
  return snapshot;
}

test("owner close: a double click and a retry after a timeout make exactly one operation", async ({
  page,
  context,
}) => {
  test.setTimeout(60000);
  const state = await setup(context);
  try {
    await state.controls({ enabled: true, emergency_stop: false });
    const snapshot = await openPositions(context, state, 2);
    const [first, second] = snapshot.positions;
    // The owner keeps looking at the list as it was: the rows stay while closes settle.
    await page.route(`**/api/trading/accounts/${state.data.account}`, (route) =>
      route.fulfill({ json: snapshot }),
    );
    // Nor has the page heard from the journal yet: the retry is how it learns the outcome.
    await page.route("**/api/trading/journal", (route) => route.fulfill({ json: [] }));
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

test("owner close: a settled journal row releases the held identity for a new close", async ({
  page,
  context,
}) => {
  test.setTimeout(60000);
  const state = await setup(context);
  try {
    await state.controls({ enabled: true, emergency_stop: false });
    const [attested, failed] = (await openPositions(context, state, 2)).positions;
    // An uncertain close the owner attests was not executed, and a close that failed:
    // both positions are still open.
    const seeded = seedCloses({
      account: state.data.account,
      symbol: state.data.symbol,
      rows: [
        [attested.id, "ambiguous", "broker_timeout"],
        [failed.id, "failed", "broker_rejected"],
      ],
    });
    const resolved = await context.request.post(
      `/api/trading/journal/${seeded[attested.id]}/resolve`,
      {
        headers: state.headers,
        data: { outcome: "not_executed", statement: "Checked the terminal: still open." },
      },
    );
    expect(resolved.ok()).toBeTruthy();
    expect((await resolved.json()).status).toBe("resolved");
    const sent = [];
    await page.route("**/api/trading/execute", async (route) => {
      sent.push(route.request().postDataJSON());
      await route.continue();
    });
    await page.goto("/app/trading");
    // The tab still holds both identities, as it did when those closes were made.
    await page.evaluate(
      ({ account, rows }) => {
        for (const [ticket, operation] of Object.entries(rows))
          sessionStorage.setItem(
            `lonora.held-operation:close_position:${account}:${ticket}`,
            operation,
          );
      },
      { account: state.data.account, rows: seeded },
    );
    await page.reload();
    await page.getByLabel("Broker account").selectOption(state.data.account);
    for (const [position, status, label] of [
      [attested, "resolved", "Resolved by owner"],
      [failed, "failed", "Failed"],
    ]) {
      const row = page.locator(`[data-position-id="${position.id}"]`);
      // The settled outcome stays on the row; the button closes again.
      await expect(row.locator(`[data-operation-status="${status}"]`)).toHaveText(label);
      await row.getByRole("button", { name: "Close position", exact: true }).click();
      await expect(row).toHaveCount(0);
    }
    expect(sent).toHaveLength(2);
    expect(sent.map((body) => body.position_id)).toEqual([attested.id, failed.id]);
    expect(sent[0].operation_id).not.toBe(seeded[attested.id]);
    expect(sent[1].operation_id).not.toBe(seeded[failed.id]);
    const journal = await (
      await context.request.get(`/api/trading/journal?account_id=${state.data.account}`)
    ).json();
    for (const [position, body] of [
      [attested, sent[0]],
      [failed, sent[1]],
    ]) {
      const closes = journal.filter(
        (row) => row.request.action === "close_position" && row.request.position_id === position.id,
      );
      expect(closes).toHaveLength(2);
      expect(closes.find((row) => row.operation_id === body.operation_id)?.status).toBe(
        "confirmed",
      );
    }
    const after = await (
      await context.request.get(`/api/trading/accounts/${state.data.account}`)
    ).json();
    expect(after.positions).toHaveLength(0);
    expect(
      await page.evaluate(() =>
        Object.keys(sessionStorage).filter((name) => name.startsWith("lonora.held-operation:")),
      ),
    ).toEqual([]);
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
    // The owner stopped it (not the never-started default), so the sheet offers Resume.
    await state.controls({ enabled: true, emergency_stop: false });
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
    // The capsule under the header shows abnormal states only (reference safetyCap).
    const capsule = page.getByTestId("safety-capsule");
    await expect(capsule).toHaveAttribute("data-readiness", "stopped");
    await expect(capsule).toContainText("Trading is stopped");
    await capsule.click();
    const sheet = page.locator("#dialog");
    const trading = sheet.getByRole("switch", { name: "Trading", exact: true });
    await expect(trading).toHaveAttribute("aria-checked", "false");
    await expect(
      sheet.getByText("Stopped · no new orders are sent", { exact: true }),
    ).toBeVisible();
    await trading.click();
    await expect(trading).toHaveAttribute("aria-checked", "true");
    expect(writes).toEqual([{ enabled: true, emergency_stop: false }]);
    expect(await state.read()).toEqual({ enabled: true, emergency_stop: false });
    // A normal state pins nothing under the header.
    await expect(capsule).toHaveCount(0);
    await trading.click();
    await expect(trading).toHaveAttribute("aria-checked", "false");
    expect(writes.at(-1)).toEqual({ enabled: false, emergency_stop: true });
    expect(await state.read()).toEqual({ enabled: false, emergency_stop: true });
    await expect(capsule).toHaveAttribute("data-readiness", "stopped");
  } finally {
    await context.request.delete(`/api/agents/${agent.id}`, { headers: state.headers });
    await state.cleanup();
  }
});

for (const locale of ["en", "ar"])
  test(`${locale}: a stop with a freeze says exits are frozen too, in the line and the sheet`, async ({
    page,
    context,
  }) => {
    test.setTimeout(60000);
    const state = await setup(context, locale);
    const response = await context.request.post("/api/agents", {
      headers: state.headers,
      data: {
        name: `Freeze ${randomUUID()}`,
        trading_account_id: state.data.account,
        trading_symbol: state.data.symbol,
      },
    });
    expect(response.status()).toBe(201);
    const agent = await response.json();
    const text =
      locale === "ar"
        ? {
            allowed: "التداول متوقف",
            frozen: "التداول الجديد متوقف · والخروج مجمّد أيضًا",
            alert: "يوجد تجميد نشط: الخروج محظور أيضًا.",
          }
        : {
            allowed: "Trading is stopped",
            frozen: "New trading stopped · exits frozen too",
            alert: "A freeze is active: exits are blocked too.",
          };
    let freeze;
    try {
      const permissions = await (
        await context.request.get(`/api/agents/${agent.id}/permissions`)
      ).json();
      const changed = await context.request.put(`/api/agents/${agent.id}/permissions`, {
        headers: state.headers,
        data: { level: "supervised", expected_revision: permissions.revision },
      });
      expect(changed.ok()).toBeTruthy();
      await state.controls({ enabled: true, emergency_stop: false });
      await state.controls({ enabled: false, emergency_stop: true });
      await page.goto(`/app/${agent.id}`);
      const pill = page.getByTestId("safety-capsule");
      await expect(pill.locator(".sc-text")).toHaveText(text.allowed);
      const created = await context.request.post("/api/trading/restrictions", {
        headers: state.headers,
        data: { account_id: state.data.account, action_class: "all_mutations" },
      });
      expect(created.status()).toBe(201);
      freeze = (await created.json()).id;
      await page.reload();
      await expect(pill).toHaveAttribute("data-readiness", "stopped");
      // A freeze blocks exits too: the capsule says it in the server's words.
      await expect(pill.locator(".sc-text")).toHaveText(text.frozen);
      await pill.click();
      const sheet = page.locator("#dialog");
      // The sheet never says closing is allowed while a freeze blocks it.
      await expect(sheet.getByRole("alert")).toHaveText(text.alert);
      await expect(sheet.getByText(text.allowed, { exact: true })).toHaveCount(0);
    } finally {
      if (freeze)
        await context.request.post(`/api/trading/restrictions/${freeze}/revoke`, {
          headers: state.headers,
          data: {},
        });
      await context.request.delete(`/api/agents/${agent.id}`, { headers: state.headers });
      await state.cleanup();
    }
  });
