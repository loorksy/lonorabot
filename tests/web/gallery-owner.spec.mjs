// Card gallery (review/ui-cards only, not a test of behaviour): the cards the owner acts on
// in a conversation (Mandate, Settle Uncertain Operation, Secret), seeded as real records.
import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { eachVariant, shot, useVariant, VARIANTS, view } from "./gallery.mjs";

function simulation(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}

// Cards as the runtime raises them (no model): through lonora_db.owner_actions only
// (tests/web/owner-actions.spec.mjs). With `anchor`, the uncertain operation's journal row
// sits in the conversation, as an agent Run of that conversation records it.
function seedCard(data) {
  const script = `
import asyncio,json,sys
from uuid import uuid4
sys.path.insert(0,'tests')
from check_streaming import Fixture
from lonora_contracts.domain import utcnow
from lonora_contracts.owner_actions import OwnerActionProposal
from lonora_db.owner_actions import propose,raise_system_card
from lonora_db.schema import ThreadRow,TradingJournalRow
async def main():
    data=json.load(sys.stdin)
    f=await Fixture().open()
    try:
        async with f.runtime.db.sessions() as session, session.begin():
            fields={'kind':data['kind']}
            if data['kind']=='trading_mode':
                fields['agent_id']=data['agent']
            if data['kind']=='resolve_operation':
                operation=str(uuid4())
                anchor={}
                if data.get('anchor'):
                    thread=await session.get(ThreadRow,data['thread'])
                    anchor={'thread_id':thread.id,'timeline_seq':thread.next_seq}
                session.add(TradingJournalRow(operation_id=operation,owner_id=f.owner,account_id=data['account'],request_hash='ui-fixture',request={'account_id':data['account'],'action':'buy','symbol':data['symbol'],'volume':'0.10'},status='ambiguous',result={'status':'ambiguous','code':'broker_timeout','details':{'send_state':'sent','execution':{'agent_id':data['agent'],'send_authorized':True}}},submitted_at=utcnow(),updated_at=utcnow(),**anchor))
                await session.flush()
                fields['operation_id']=operation
            proposal=OwnerActionProposal(**fields)
            if data['kind']=='trading_mode':
                # As an agent proposes its own Mandate card.
                row,_=await propose(session,f.owner,proposal,card_id=str(uuid4()),agent_id=data['agent'],thread_id=data['thread'],run_id=None)
            else:
                row=await raise_system_card(session,f.owner,proposal,agent_id=data['agent'],thread_id=data['thread'],run_id=None)
            print(json.dumps({'id':row.id if row else None,'operation_id':fields.get('operation_id')}))
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

// An agent's Secret card, raised through the same proposal path its tool uses
// (tests/web/secret-card-fixture.mjs); with `broker`, the broker card as broker_connect
// raises it: its two fixed fields and the account line (tests/check_genui_browser.py).
function seedSecretCard(data) {
  const script = `
import asyncio,json,sys
sys.path.insert(0,'tests')
from uuid import uuid4
from check_streaming import Fixture
from lonora_contracts.domain import AgentCreate
from lonora_contracts.owner_actions import OwnerActionProposal
from lonora_db.agents import create_agent
from lonora_db.owner_actions import create_card,propose
from lonora_db.secret_cards import broker_card_payload
from lonora_db.threads import conversation_thread
async def main():
    data=json.load(sys.stdin)
    f=await Fixture().open()
    try:
        async with f.runtime.db.sessions() as session, session.begin():
            agent=await create_agent(session,f.owner,AgentCreate(name=data['agent'],scope_mode='flexible'))
            thread=await conversation_thread(session,f.owner,agent.id)
            if data.get('broker'):
                subject,payload=broker_card_payload(login='5001234',server='Demo-Server',platform='mt5',token_needed=True)
                card=await create_card(session,f.owner,card_id=uuid4().hex,agent_id=agent.id,thread=thread,run_id=None,source='agent',kind='secret',subject=subject,payload=payload)
            else:
                proposal=OwnerActionProposal(kind='secret',label=data['label'],secret_fields=data['fields'])
                card,_=await propose(session,f.owner,proposal,card_id=str(uuid4()),agent_id=agent.id,thread_id=thread.id,run_id=None)
            print(json.dumps({'agent':agent.id,'thread':thread.id,'card':card.id}))
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

async function signIn(context) {
  const data = simulation({ action: "init", empty: true });
  await context.addCookies(
    data.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  // The gallery harness sets the locale and theme per variant; no init script may force them.
  const headers = { "X-CSRF-Token": data.cookies.find((row) => row.name === "lonora_csrf").value };
  return { data, headers };
}

// tests/web/owner-actions.spec.mjs setup(), with a fixed agent name so shots compare.
async function setup(context) {
  const { data, headers } = await signIn(context);
  const connected = await context.request.post("/api/trading/connections", {
    headers,
    data: { provider: "simulation", account_id: `cards-${randomUUID()}`, enabled: true },
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
  const agentResponse = await context.request.post("/api/agents", {
    headers,
    data: { name: "Gold agent", trading_account_id: account, trading_symbol: data.symbol },
  });
  expect(agentResponse.status()).toBe(201);
  const agent = await agentResponse.json();
  const thread = await (
    await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
  ).json();
  return {
    data,
    headers,
    account,
    agent,
    thread,
    async cleanup() {
      // Every test's own agent goes; leaked ones count against the agent-creation cap.
      await context.request.delete(`/api/agents/${agent.id}`, { headers });
      simulation({ ...data, action: "cleanup" });
    },
  };
}

const card = (page, id) => page.locator(`[data-owner-action="${id}"]`);
// The card in its bubble, as the conversation frames it.
const bubble = (page, id) => page.locator(`.msg[data-mid="${id}"] .bubble`);

async function decide(context, state, id, data) {
  const response = await context.request.post(`/api/owner-actions/${id}/decision`, {
    headers: state.headers,
    data,
  });
  expect(response.ok()).toBeTruthy();
}

test.use({ deviceScaleFactor: 2 });

// ---------------------------------------------------------------------------------------
// Mandate (10.3): the owner-action kind trading_mode.

test("mandate: pending in Ask, then Full after the owner's tap, then back to Ask", async ({
  page,
  context,
}) => {
  test.setTimeout(600_000);
  const state = await setup(context);
  try {
    const seeded = seedCard({ kind: "trading_mode", agent: state.agent.id, thread: state.thread.id });
    await page.goto(`/app/${state.agent.id}`);
    await eachVariant(page, "mandate", "pending-ask", async (p) => {
      await expect(card(p, seeded.id)).toHaveAttribute("data-owner-action-status", "pending");
      await expect(card(p, seeded.id).locator('[data-owner-action-button="full"]')).toBeVisible();
      return bubble(p, seeded.id);
    });
    await card(page, seeded.id).locator('[data-owner-action-button="full"]').click();
    await expect(card(page, seeded.id)).toHaveAttribute("data-owner-action-status", "confirmed");
    await expect(card(page, seeded.id).locator('[data-owner-action-button="ask"]')).toBeVisible();
    await eachVariant(page, "mandate", "settled-full", async (p) => {
      await expect(card(p, seeded.id)).toHaveAttribute("data-owner-action-status", "confirmed");
      await expect(card(p, seeded.id).locator('[data-owner-action-button="ask"]')).toBeVisible();
      return bubble(p, seeded.id);
    });
    await card(page, seeded.id).locator('[data-owner-action-button="ask"]').click();
    await expect(card(page, seeded.id).locator('[data-owner-action-button="full"]')).toBeVisible();
    await eachVariant(page, "mandate", "settled-back-to-ask", async (p) => {
      await expect(card(p, seeded.id)).toHaveAttribute("data-owner-action-status", "confirmed");
      await expect(card(p, seeded.id).locator('[data-owner-action-button="full"]')).toBeVisible();
      return bubble(p, seeded.id);
    });
  } finally {
    await state.cleanup();
  }
});

test("mandate: pending while the agent is in Full", async ({ page, context }) => {
  test.setTimeout(300_000);
  const state = await setup(context);
  try {
    // The owner already set Full on an earlier card; the agent proposes a new one.
    const first = seedCard({ kind: "trading_mode", agent: state.agent.id, thread: state.thread.id });
    await decide(context, state, first.id, { decision: "confirm", trading_mode: "full" });
    const second = seedCard({ kind: "trading_mode", agent: state.agent.id, thread: state.thread.id });
    await page.goto(`/app/${state.agent.id}`);
    await eachVariant(page, "mandate", "pending-full", async (p) => {
      await expect(card(p, second.id)).toHaveAttribute("data-owner-action-status", "pending");
      await expect(card(p, second.id).locator('[data-owner-action-button="ask"]')).toBeVisible();
      return bubble(p, second.id);
    });
  } finally {
    await state.cleanup();
  }
});

test("mandate: pending in Ask with a signed grant still active (mock)", async ({
  page,
  context,
}) => {
  test.setTimeout(300_000);
  const state = await setup(context);
  try {
    const seeded = seedCard({ kind: "trading_mode", agent: state.agent.id, thread: state.thread.id });
    // A real active grant needs a passkey signature: only the fact is set on the real row.
    await page.route("**/api/owner-actions?thread_id=*", async (route) => {
      const response = await route.fetch();
      const rows = await response.json();
      await route.fulfill({
        response,
        json: rows.map((row) =>
          row.kind === "trading_mode" ? { ...row, facts: { ...row.facts, active_grant: true } } : row,
        ),
      });
    });
    await page.goto(`/app/${state.agent.id}`);
    await eachVariant(page, "mandate", "pending-ask-active-grant-mock", async (p) => {
      await expect(card(p, seeded.id)).toHaveAttribute("data-owner-action-status", "pending");
      await expect(card(p, seeded.id).locator(".oa-sub")).toHaveCount(2);
      return bubble(p, seeded.id);
    });
  } finally {
    await state.cleanup();
  }
});

test("mandate: the legacy Delegated execution sheet from the composer's permission chip", async ({
  page,
  context,
}) => {
  test.setTimeout(300_000);
  const state = await setup(context);
  try {
    await page.goto(`/app/${state.agent.id}`);
    await eachVariant(page, "mandate", "legacy-delegated-execution-sheet", async (p) => {
      await p.getByTestId("permission-chip").click();
      await p.locator(".pop.mode-pop").getByTestId("mode-option-autonomous").click();
      await expect(p.locator("#dialog .act-grant_authority")).toBeVisible();
      return p.locator("#dialog");
    });
  } finally {
    await state.cleanup();
  }
});

// ---------------------------------------------------------------------------------------
// Settle Uncertain Operation: the owner-action kind resolve_operation.

async function settlePending(page, id) {
  await expect(card(page, id)).toHaveAttribute("data-owner-action-status", "pending");
  await expect(card(page, id).locator("[data-owner-action-button]")).toHaveCount(3);
}

async function settleTo(page, family, state, id, outcome) {
  await card(page, id).locator(`[data-owner-action-button="${outcome}"]`).click();
  await expect(card(page, id)).toHaveAttribute("data-owner-action-status", "confirmed");
  await eachVariant(page, family, state, async (p) => {
    await expect(card(p, id)).toHaveAttribute("data-owner-action-status", "confirmed");
    await expect(card(p, id).getByRole("status")).toBeVisible();
    return bubble(p, id);
  });
}

test("settle: pending, its note fields open, then Executed", async ({ page, context }) => {
  test.setTimeout(600_000);
  const state = await setup(context);
  try {
    const seeded = seedCard({
      kind: "resolve_operation",
      account: state.account,
      symbol: state.data.symbol,
      agent: state.agent.id,
      thread: state.thread.id,
    });
    await page.goto(`/app/${state.agent.id}`);
    await eachVariant(page, "settle", "pending", async (p) => {
      await settlePending(p, seeded.id);
      return bubble(p, seeded.id);
    });
    await eachVariant(page, "settle", "pending-note-fields-open", async (p) => {
      await settlePending(p, seeded.id);
      await card(p, seeded.id).locator(".oa-link").click();
      await expect(card(p, seeded.id).locator(".oa-fields .oa-input")).toHaveCount(2);
      return bubble(p, seeded.id);
    });
    await settleTo(page, "settle", "executed", seeded.id, "executed");
  } finally {
    await state.cleanup();
  }
});

for (const [outcome, name] of [
  ["not_executed", "not-executed"],
  ["unknown", "unknown"],
])
  test(`settle: ${name}`, async ({ page, context }) => {
    test.setTimeout(300_000);
    const state = await setup(context);
    try {
      const seeded = seedCard({
        kind: "resolve_operation",
        account: state.account,
        symbol: state.data.symbol,
        agent: state.agent.id,
        thread: state.thread.id,
      });
      await page.goto(`/app/${state.agent.id}`);
      await settlePending(page, seeded.id);
      await settleTo(page, "settle", name, seeded.id, outcome);
    } finally {
      await state.cleanup();
    }
  });

test("settle: the uncertain order line and its sheet with Resolve the operation", async ({
  page,
  context,
}) => {
  test.setTimeout(600_000);
  const state = await setup(context);
  try {
    const seeded = seedCard({
      kind: "resolve_operation",
      account: state.account,
      symbol: state.data.symbol,
      agent: state.agent.id,
      thread: state.thread.id,
      anchor: true,
    });
    const line = (p) => p.locator(`[data-operation-id="${seeded.operation_id}"]`);
    await page.goto(`/app/${state.agent.id}`);
    await eachVariant(page, "settle", "order-line-uncertain", async (p) => {
      await expect(line(p)).toHaveAttribute("data-order-state", "uncertain");
      await settlePending(p, seeded.id);
      return p.locator(`.msg:has([data-operation-id="${seeded.operation_id}"])`);
    });
    await eachVariant(page, "settle", "order-sheet-resolve", async (p) => {
      await expect(line(p)).toBeVisible();
      await settlePending(p, seeded.id);
      await line(p).click();
      await expect(p.locator("#dialog .od-sheet")).toBeVisible();
      await expect(p.locator("#dialog .od-sheet .oa-actions button")).toBeVisible();
      return p.locator("#dialog");
    });
  } finally {
    await state.cleanup();
  }
});

// ---------------------------------------------------------------------------------------
// Secret: the owner-action kind secret. The label and field labels are the agent's words,
// so each language has its own card, written in that language.

const SECRET_WORDS = {
  ar: {
    agent: "وكيل المنصّة",
    label: "مفاتيح المنصّة",
    fields: [
      { key: "EXCHANGE_API_KEY", label: "مفتاح API" },
      { key: "EXCHANGE_USERNAME", label: "اسم المستخدم", secret: false },
    ],
  },
  en: {
    agent: "Exchange agent",
    label: "Exchange keys",
    fields: [
      { key: "EXCHANGE_API_KEY", label: "API key" },
      { key: "EXCHANGE_USERNAME", label: "Username", secret: false },
    ],
  },
};

const secretCards = () => ({
  ar: seedSecretCard(SECRET_WORDS.ar),
  en: seedSecretCard(SECRET_WORDS.en),
});

/** Every variant, each language on its own card (and so its own conversation). */
async function eachLocale(page, family, state, records, ready) {
  for (const variant of VARIANTS) {
    const record = records[variant.locale];
    const path = `/app/${record.agent}`;
    if (new URL(page.url()).pathname !== path) await page.goto(path);
    await useVariant(page, variant);
    const locator = await ready(page, record);
    await shot(locator, family, state, variant);
    await view(page, family, state, variant);
  }
}

async function secretCleanup(context, headers, agents) {
  for (const agent of agents) await context.request.delete(`/api/agents/${agent}`, { headers });
  const names = SECRET_WORDS.en.fields.map((field) => field.key);
  const listed = await (await context.request.get("/api/secrets")).json();
  for (const item of listed.filter((row) => names.includes(row.name)))
    await context.request.delete(`/api/secrets/${item.id}`, { headers });
}

test("secret: pending with the agent's fields, then saved", async ({ page, context }) => {
  test.setTimeout(600_000);
  const { data, headers } = await signIn(context);
  const records = secretCards();
  try {
    await eachLocale(page, "secret", "pending", records, async (p, record) => {
      await expect(card(p, record.card)).toHaveAttribute("data-owner-action-status", "pending");
      await expect(card(p, record.card).locator('input[name="EXCHANGE_API_KEY"]')).toBeVisible();
      return bubble(p, record.card);
    });
    for (const record of Object.values(records)) {
      await page.goto(`/app/${record.agent}`);
      const form = card(page, record.card);
      await form.locator('input[name="EXCHANGE_API_KEY"]').fill(`live-${randomUUID()}`);
      await form.locator('input[name="EXCHANGE_USERNAME"]').fill("trader");
      await form.locator('[data-owner-action-button="save"]').click();
      await expect(form).toHaveAttribute("data-owner-action-status", "confirmed");
    }
    await eachLocale(page, "secret", "saved", records, async (p, record) => {
      await expect(card(p, record.card)).toHaveAttribute("data-owner-action-status", "confirmed");
      await expect(card(p, record.card).getByRole("status")).toBeVisible();
      return bubble(p, record.card);
    });
  } finally {
    await secretCleanup(
      context,
      headers,
      Object.values(records).map((record) => record.agent),
    );
    simulation({ ...data, action: "cleanup" });
  }
});

test("secret: dismissed with Not now", async ({ page, context }) => {
  test.setTimeout(300_000);
  const { data, headers } = await signIn(context);
  // Their pending state is the one shot above; these cards are only dismissed.
  const records = secretCards();
  try {
    for (const record of Object.values(records)) {
      await page.goto(`/app/${record.agent}`);
      await card(page, record.card).locator('[data-owner-action-button="cancel"]').click();
      await expect(card(page, record.card)).toHaveAttribute(
        "data-owner-action-status",
        "cancelled",
      );
    }
    await eachLocale(page, "secret", "dismissed", records, async (p, record) => {
      await expect(card(p, record.card)).toHaveAttribute("data-owner-action-status", "cancelled");
      await expect(card(p, record.card).getByRole("status")).toBeVisible();
      return bubble(p, record.card);
    });
  } finally {
    await secretCleanup(
      context,
      headers,
      Object.values(records).map((record) => record.agent),
    );
    simulation({ ...data, action: "cleanup" });
  }
});

test("secret: the broker card (Connect trading account), pending", async ({ page, context }) => {
  test.setTimeout(300_000);
  const { data, headers } = await signIn(context);
  // Every word on it is Lonora's; saving would provision at MetaApi, so only pending.
  const seeded = seedSecretCard({ agent: "Broker agent", broker: true });
  try {
    await page.goto(`/app/${seeded.agent}`);
    await eachVariant(page, "secret", "broker-connect-pending", async (p) => {
      await expect(card(p, seeded.card)).toHaveAttribute("data-owner-action-status", "pending");
      await expect(card(p, seeded.card).locator('input[name="PASSWORD"]')).toBeVisible();
      return bubble(p, seeded.card);
    });
  } finally {
    await context.request.delete(`/api/agents/${seeded.agent}`, { headers });
    simulation({ ...data, action: "cleanup" });
  }
});
