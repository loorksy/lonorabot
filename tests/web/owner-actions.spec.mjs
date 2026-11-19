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

// Cards as the runtime raises them (no model): through lonora_db.owner_actions only.
function seedCard(data) {
  const script = `
import asyncio,json,sys
from uuid import uuid4
sys.path.insert(0,'tests')
from check_streaming import Fixture
from lonora_contracts.domain import utcnow
from lonora_contracts.owner_actions import OwnerActionProposal
from lonora_db.owner_actions import propose,raise_system_card
from lonora_db.schema import TradingJournalRow
async def main():
    data=json.load(sys.stdin)
    f=await Fixture().open()
    try:
        async with f.runtime.db.sessions() as session, session.begin():
            fields={'kind':data['kind']}
            if data['kind']=='resolve_operation':
                operation=str(uuid4())
                session.add(TradingJournalRow(operation_id=operation,owner_id=f.owner,account_id=data['account'],request_hash='ui-fixture',request={'account_id':data['account'],'action':'buy','symbol':data['symbol'],'volume':'0.10'},status='ambiguous',result={'status':'ambiguous','code':'broker_timeout','details':{'send_state':'sent','execution':{'agent_id':data['agent'],'send_authorized':True}}},submitted_at=utcnow(),updated_at=utcnow()))
                await session.flush()
                fields['operation_id']=operation
            proposal=OwnerActionProposal(**fields)
            if data['kind']=='grant_authority':
                # The draft the tool resolves: this account, this pair, every action, until
                # stopped and own positions excluded (D1).
                from lonora_contracts.owner_actions import GrantDraft
                from lonora_db.owner_actions import ALL_ACTIONS
                draft=GrantDraft(agent_id=data['agent'],account_id=data['account'],symbol_scope='selected',symbols=[data['symbol']],actions=list(ALL_ACTIONS))
                if data.get('delegation')=='full':
                    # Preselected because the owner's own message asked for full delegation.
                    draft=draft.with_delegation('full')
                row,_=await propose(session,f.owner,proposal,card_id=str(uuid4()),agent_id=data['agent'],thread_id=data['thread'],run_id=None,grant=draft)
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

async function setup(context, locale) {
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
    data: {
      name: `Gold agent ${randomUUID().slice(0, 6)}`,
      trading_account_id: account,
      trading_symbol: data.symbol,
    },
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

const copy = {
  en: {
    resolveTitle: "The broker did not confirm this trade",
    notExecuted: "It did not execute",
    unknown: "Unknown: release the hold",
    recorded: "Recorded: it did not execute (your statement, not broker confirmation).",
    grantTitle: "trade on its own",
    authorize: "Authorize with passkey",
    includeOwn: "Include positions I opened myself",
    password: "Account password",
    register: "Register this device first",
    signed: "Signed. It trades on its own inside this grant.",
    ownExcluded: "Positions you opened yourself are excluded",
  },
  ar: {
    resolveTitle: "الوسيط لم يؤكد هذه الصفقة",
    notExecuted: "لم تُنفذ",
    unknown: "غير معروفة — ارفع التعليق",
    recorded: "سُجّل: لم تُنفذ (تصريحك، لا تأكيد من الوسيط).",
    grantTitle: "يتداول بنفسه",
    authorize: "التفويض بمفتاح المرور",
    includeOwn: "اشمل المراكز التي فتحتها بنفسي",
    password: "كلمة مرور الحساب",
    register: "سجّل هذا الجهاز أولًا",
    signed: "وُقّع. يتداول بنفسه ضمن هذا التفويض.",
    ownExcluded: "لا يشمل المراكز التي فتحتها بنفسك",
  },
};

for (const locale of ["en", "ar"])
  test(`${locale}: a grant card signs with one passkey tap, registering the device inline`, async ({
    page,
    context,
  }) => {
    test.setTimeout(90000);
    const text = copy[locale];
    const state = await setup(context, locale);
    // A fresh authenticator: remove only the disposable owner's prior credentials.
    for (const device of await (await context.request.get("/api/auth/devices")).json())
      expect(
        (
          await context.request.delete(`/api/auth/devices/${device.id}`, { headers: state.headers })
        ).ok(),
      ).toBeTruthy();
    const cdp = await context.newCDPSession(page);
    await cdp.send("WebAuthn.enable");
    await cdp.send("WebAuthn.addVirtualAuthenticator", {
      options: {
        protocol: "ctap2",
        transport: "internal",
        hasResidentKey: true,
        hasUserVerification: true,
        isUserVerified: true,
        automaticPresenceSimulation: true,
      },
    });
    try {
      const seeded = seedCard({
        kind: "grant_authority",
        account: state.account,
        symbol: state.data.symbol,
        agent: state.agent.id,
        thread: state.thread.id,
      });
      const bodies = [];
      page.on("request", (request) => {
        if (request.method() === "POST" && request.url().includes(`/owner-actions/${seeded.id}/`))
          bodies.push([new URL(request.url()).pathname.split("/").pop(), request.postDataJSON()]);
      });
      await page.goto(`/app/${state.agent.id}`);
      const card = page.locator(`[data-owner-action="${seeded.id}"]`);
      await expect(card).toHaveAttribute("data-owner-action-status", "pending");
      await expect(card.locator(".oa-kind")).toContainText(text.grantTitle);
      await expect(card.locator(".oa-kind")).toContainText(state.agent.name);
      await expect(card.getByText(state.data.symbol)).toBeVisible();
      // The switch states the owner's own positions; no fixed line contradicts it.
      await expect(card.getByText(text.ownExcluded, { exact: true })).toHaveCount(0);
      // D1: the owner's own positions are excluded unless switched on.
      const own = card.getByRole("switch", { name: text.includeOwn });
      await expect(own).not.toBeChecked();
      // Amendment 1: the card offers no Resume trading switch.
      await expect(card.getByRole("switch", { name: /Resume trading|استأنف التداول/ })).toHaveCount(
        0,
      );
      if (locale === "ar") {
        await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
        await card.screenshot({ path: test.info().outputPath("owner-action-grant-ar.png") });
      }
      const authorize = card.getByRole("button", { name: text.authorize, exact: true });
      await authorize.click();
      // First time on this device: the same card asks for the password and registers it.
      await card.getByLabel(text.password, { exact: true }).fill("ci-only-owner-password");
      // Registering continues straight into the passkey prompt for this decision.
      await card.getByRole("button", { name: text.register, exact: true }).click();
      await expect(card).toHaveAttribute("data-owner-action-status", "confirmed");
      await expect(card.getByRole("status")).toHaveText(text.signed);
      await expect(card.locator("[data-owner-action-button]")).toHaveCount(0);
      const challenges = bodies.filter(([kind]) => kind === "challenge").map(([, body]) => body);
      // The challenge names the choice the card showed: Custom, with its own switch.
      expect(challenges.at(-1)).toEqual({ delegation: "custom", allow_manual_positions: false });
      const decision = bodies.find(([kind]) => kind === "decision")?.[1];
      expect(decision.decision).toBe("confirm");
      expect(decision).not.toHaveProperty("resume_trading");
      expect(decision.proof?.challenge_id).toBeTruthy();
      const permission = await (
        await context.request.get(`/api/agents/${state.agent.id}/permissions`)
      ).json();
      expect(permission.effective_level).toBe("autonomous");
      expect(permission.active_authorities[0].envelope.allow_manual_positions).toBe(false);
    } finally {
      await state.cleanup();
    }
  });

const delegationCopy = {
  en: {
    custom: "Custom",
    full: "Full delegation",
    customMeaning: "Custom: only the markets, actions and time shown here",
    fullMeaning: "Full delegation: every pair on this account and every action",
    allPairs: "Markets: All pairs on this account",
    ownIncluded: "Positions you opened yourself are included",
    notNow: "Not now",
    changed:
      "This card changed on another screen. It now shows the current choice; check it and tap again.",
  },
  ar: {
    custom: "مخصص",
    full: "تفويض كامل",
    customMeaning: "مخصص: الأسواق والعمليات والمدة الظاهرة هنا فقط",
    fullMeaning: "تفويض كامل: كل أزواج هذا الحساب وكل العمليات",
    allPairs: "الأسواق: كل أزواج هذا الحساب",
    ownIncluded: "يشمل المراكز التي فتحتها بنفسك",
    notNow: "ليس الآن",
    changed: "تغيّرت هذه البطاقة من شاشة أخرى، وهي تعرض الآن الاختيار الحالي؛ راجعها ثم اضغط مجددًا.",
  },
};

for (const locale of ["en", "ar"])
  test(`${locale}: Custom or Full delegation is one choice in the grant card's list, signed with the passkey`, async ({
    page,
    context,
  }) => {
    test.setTimeout(90000);
    const text = { ...copy[locale], ...delegationCopy[locale] };
    const state = await setup(context, locale);
    for (const device of await (await context.request.get("/api/auth/devices")).json())
      expect(
        (
          await context.request.delete(`/api/auth/devices/${device.id}`, { headers: state.headers })
        ).ok(),
      ).toBeTruthy();
    const cdp = await context.newCDPSession(page);
    await cdp.send("WebAuthn.enable");
    await cdp.send("WebAuthn.addVirtualAuthenticator", {
      options: {
        protocol: "ctap2",
        transport: "internal",
        hasResidentKey: true,
        hasUserVerification: true,
        isUserVerified: true,
        automaticPresenceSimulation: true,
      },
    });
    // A flexible agent: its grant may cover every pair on the account.
    const created = await context.request.post("/api/agents", {
      headers: state.headers,
      data: {
        name: `Full agent ${randomUUID().slice(0, 6)}`,
        scope_mode: "flexible",
        trading_account_id: state.account,
        trading_symbol: state.data.symbol,
      },
    });
    expect(created.status()).toBe(201);
    const agent = await created.json();
    const thread = await (
      await context.request.post(`/api/agents/${agent.id}/conversation`, {
        headers: state.headers,
        data: {},
      })
    ).json();
    try {
      const seeded = seedCard({
        kind: "grant_authority",
        account: state.account,
        symbol: state.data.symbol,
        agent: agent.id,
        thread: thread.id,
      });
      const bodies = [];
      page.on("request", (request) => {
        if (request.method() === "POST" && request.url().includes(`/owner-actions/${seeded.id}/`))
          bodies.push([new URL(request.url()).pathname.split("/").pop(), request.postDataJSON()]);
      });
      await page.goto(`/app/${agent.id}`);
      const card = page.locator(`[data-owner-action="${seeded.id}"]`);
      await expect(card).toHaveAttribute("data-owner-action-status", "pending");
      const custom = card.getByRole("radio", { name: text.custom, exact: true });
      const full = card.getByRole("radio", { name: text.full, exact: true });
      // One choice inside the card's own list, Custom selected; no separate button.
      await expect(custom).toBeChecked();
      await expect(full).not.toBeChecked();
      await expect(card.getByRole("button")).toHaveText([text.authorize, text.notNow]);
      await expect(card.locator("[data-owner-action-choice-detail]")).toContainText(
        text.customMeaning,
      );
      await expect(card.getByRole("switch", { name: text.includeOwn })).not.toBeChecked();
      // Choosing Full updates the card's stored draft; the card then reads as Full.
      await full.check();
      await expect(full).toBeChecked();
      const detail = card.locator("[data-owner-action-choice-detail]");
      await expect(detail).toContainText(text.fullMeaning);
      await expect(card.getByRole("switch", { name: text.includeOwn })).toHaveCount(0);
      await expect(card.getByText(text.ownIncluded, { exact: true })).toBeVisible();
      await expect(card.getByText(text.allPairs, { exact: true })).toBeVisible();
      // Back to Custom restores it exactly, then Full again.
      await custom.check();
      await expect(custom).toBeChecked();
      await expect(card.getByRole("switch", { name: text.includeOwn })).toBeVisible();
      await full.check();
      await expect(full).toBeChecked();
      if (locale === "ar") {
        await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
        await card.screenshot({ path: test.info().outputPath("owner-action-full-ar.png") });
      }
      await card.getByRole("button", { name: text.authorize, exact: true }).click();
      await card.getByLabel(text.password, { exact: true }).fill("ci-only-owner-password");
      await card.getByRole("button", { name: text.register, exact: true }).click();
      await expect(card).toHaveAttribute("data-owner-action-status", "confirmed");
      await expect(card.getByRole("status")).toHaveText(text.signed);
      await expect(card.getByText(text.full, { exact: true })).toBeVisible();
      const chosen = bodies
        .filter(([kind, body]) => kind === "decision" && body.decision === "choose")
        .map(([, body]) => body.delegation);
      expect(chosen).toEqual(["full", "custom", "full"]);
      // Full names its choice and sends no own-positions switch: the draft includes them.
      const challenges = bodies.filter(([kind]) => kind === "challenge").map(([, body]) => body);
      expect(challenges.at(-1)).toEqual({ delegation: "full" });
      const confirm = bodies.find(
        ([kind, body]) => kind === "decision" && body.decision === "confirm",
      );
      expect(confirm?.[1].proof?.challenge_id).toBeTruthy();
      const permission = await (
        await context.request.get(`/api/agents/${agent.id}/permissions`)
      ).json();
      expect(permission.effective_level).toBe("autonomous");
      const envelope = permission.active_authorities[0].envelope;
      expect(envelope.symbol_scope).toBe("account");
      expect(envelope.symbols).toEqual([]);
      expect(envelope.actions).toHaveLength(10);
      expect(envelope.allow_manual_positions).toBe(true);
      expect(envelope.valid_until).toBeNull();
      await page.reload();
      // «الحالة والأمان» from the chat's ⋮ menu says what the card signed.
      await page.getByRole("button", { name: /^(Chat menu|قائمة المحادثة)$/ }).click();
      await page
        .getByRole("menuitem", {
          name: /^(Status and safety|الحالة والأمان|Trading and safety|التداول والأمان)$/,
        })
        .click();
      await expect(page.getByTestId("agent-mode-line")).toContainText(text.full);
    } finally {
      await context.request.delete(`/api/agents/${agent.id}`, { headers: state.headers });
      await state.cleanup();
    }
  });

for (const locale of ["en", "ar"])
  test(`${locale}: a grant card changed on another screen is read again and never signs the other choice`, async ({
    page,
    context,
  }) => {
    test.setTimeout(90000);
    const text = { ...copy[locale], ...delegationCopy[locale] };
    const state = await setup(context, locale);
    const created = await context.request.post("/api/agents", {
      headers: state.headers,
      data: {
        name: `Stale card ${randomUUID().slice(0, 6)}`,
        scope_mode: "flexible",
        trading_account_id: state.account,
        trading_symbol: state.data.symbol,
      },
    });
    expect(created.status()).toBe(201);
    const agent = await created.json();
    const thread = await (
      await context.request.post(`/api/agents/${agent.id}/conversation`, {
        headers: state.headers,
        data: {},
      })
    ).json();
    const cards = async () =>
      (await context.request.get(`/api/owner-actions?thread_id=${thread.id}`)).json();
    try {
      const seeded = seedCard({
        kind: "grant_authority",
        account: state.account,
        symbol: state.data.symbol,
        agent: agent.id,
        thread: thread.id,
      });
      // This screen keeps what it last read until its tap reaches the server: another
      // screen's choice (or a lost answer to one) has not reached it yet.
      let frozen = null;
      await page.route(
        (url) => url.pathname.endsWith("/owner-actions"),
        async (route) => {
          if (frozen && route.request().method() === "GET") await route.fulfill({ json: frozen });
          else await route.continue();
        },
      );
      const challenges = [];
      await page.route(
        (url) => url.pathname.endsWith(`/owner-actions/${seeded.id}/challenge`),
        async (route) => {
          challenges.push(route.request().postDataJSON());
          frozen = null;
          await route.continue();
        },
      );
      await page.goto(`/app/${agent.id}`);
      const card = page.locator(`[data-owner-action="${seeded.id}"]`);
      const custom = card.getByRole("radio", { name: text.custom, exact: true });
      const full = card.getByRole("radio", { name: text.full, exact: true });
      await expect(custom).toBeChecked();
      await expect(card.getByRole("switch", { name: text.includeOwn })).toBeVisible();
      frozen = await cards();
      // The owner picks Full on another screen; this one still shows Custom.
      const other = await context.request.post(`/api/owner-actions/${seeded.id}/decision`, {
        headers: state.headers,
        data: { decision: "choose", delegation: "full" },
      });
      expect(other.ok()).toBeTruthy();
      await card.getByRole("switch", { name: text.includeOwn }).click();
      await expect(custom).toBeChecked();
      await card.getByRole("button", { name: text.authorize, exact: true }).click();
      // Refused before any passkey prompt: the card is read again and shows Full now.
      await expect(card.getByRole("alert")).toHaveText(text.changed);
      await expect(full).toBeChecked();
      await expect(card.locator("[data-owner-action-choice-detail]")).toContainText(
        text.fullMeaning,
      );
      await expect(card.getByText(text.allPairs, { exact: true })).toBeVisible();
      await expect(card.getByRole("switch", { name: text.includeOwn })).toHaveCount(0);
      expect(challenges).toEqual([{ delegation: "custom", allow_manual_positions: true }]);
      // Nothing was prepared or signed.
      const stored = (await cards()).find((row) => row.id === seeded.id);
      expect(stored.status).toBe("pending");
      expect(stored.result).toEqual({});
      const permission = await (
        await context.request.get(`/api/agents/${agent.id}/permissions`)
      ).json();
      expect(permission.effective_level).toBe("supervised");
      expect(permission.active_authorities).toEqual([]);
      if (locale === "ar") {
        await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
        await card.screenshot({ path: test.info().outputPath("owner-action-changed-ar.png") });
      }
      await card.getByRole("button", { name: text.notNow, exact: true }).click();
      await expect(card).toHaveAttribute("data-owner-action-status", "cancelled");
    } finally {
      await context.request.delete(`/api/agents/${agent.id}`, { headers: state.headers });
      await state.cleanup();
    }
  });

for (const locale of ["en", "ar"])
  test(`${locale}: an uncertain trade card settles with one answer and never resends`, async ({
    page,
    context,
  }) => {
    test.setTimeout(60000);
    const text = copy[locale];
    const state = await setup(context, locale);
    try {
      const seeded = seedCard({
        kind: "resolve_operation",
        account: state.account,
        symbol: state.data.symbol,
        agent: state.agent.id,
        thread: state.thread.id,
      });
      const sent = [];
      await page.route("**/api/trading/execute", async (route) => {
        sent.push(route.request().postDataJSON());
        await route.continue();
      });
      await page.goto(`/app/${state.agent.id}`);
      const card = page.locator(`[data-owner-action="${seeded.id}"]`);
      await expect(card.locator(".oa-kind")).toHaveText(text.resolveTitle);
      await expect(card.locator("[data-owner-action-button]")).toHaveCount(3);
      // "Unknown" says that it releases the hold; it never reads as "wait".
      await expect(card.locator('[data-owner-action-button="unknown"]')).toHaveText(text.unknown);
      await expect(card.getByText(state.data.symbol)).toBeVisible();
      if (locale === "ar") {
        await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
        // The first answer starts the row on the reading side: right in Arabic.
        const [first, next] = await Promise.all([
          card.locator('[data-owner-action-button="executed"]').boundingBox(),
          card.locator('[data-owner-action-button="not_executed"]').boundingBox(),
        ]);
        expect(first && next && first.x > next.x).toBeTruthy();
        await card.screenshot({ path: test.info().outputPath("owner-action-resolve-ar.png") });
      }
      await card.getByRole("button", { name: text.notExecuted, exact: true }).click();
      await expect(card).toHaveAttribute("data-owner-action-status", "confirmed");
      await expect(card.getByRole("status")).toHaveText(text.recorded);
      const journal = await (
        await context.request.get(`/api/trading/journal?account_id=${state.account}`)
      ).json();
      const row = journal.find((item) => item.operation_id === seeded.operation_id);
      expect(row.status).toBe("resolved");
      expect(row.result.details.resolution.outcome).toBe("not_executed");
      expect(row.result.details.resolution.broker_confirmed).toBe(false);
      expect(sent).toEqual([]);
    } finally {
      await state.cleanup();
    }
  });
