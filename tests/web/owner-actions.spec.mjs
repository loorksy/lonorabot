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
from datetime import timedelta
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
            if data['kind']=='trading_mode':
                fields['agent_id']=data['agent']
            if data['kind']=='settle_operation':
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
            elif data['kind']=='trading_mode':
                # As an agent proposes its own Mandate card.
                row,_=await propose(session,f.owner,proposal,card_id=str(uuid4()),agent_id=data['agent'],thread_id=data['thread'],run_id=None)
            else:
                row=await raise_system_card(session,f.owner,proposal,agent_id=data['agent'],thread_id=data['thread'],run_id=None)
            if data.get('expired'):
                # A stored card whose server lifetime ran out while the outcome stays unknown.
                row.expires_at=utcnow()-timedelta(minutes=1)
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
    settleKind: "Unconfirmed operation",
    resolveTitle: "The broker did not confirm this trade",
    hold: "New risk on this market is held until it settles; exits stay allowed.",
    renew: "New request",
    notExecuted: "It did not execute",
    unknown: "Unknown",
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
    settleKind: "عملية غير مؤكَّدة",
    resolveTitle: "الوسيط لم يؤكد هذه الصفقة",
    hold: "المخاطرة الجديدة على هذا السوق معلّقة حتى تُحسم؛ يبقى الخروج متاحًا.",
    renew: "طلب جديد",
    latest: "عرض الأحدث",
    notExecuted: "لم تُنفذ",
    unknown: "غير معروفة",
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
      // A grant is not one of the five fixed cards: settled, it stays one line until W-AUTH
      // deletes the kind; only the fixed cards keep their whole frame (10.2.2).
      await expect(card).toHaveClass(/\boa-line\b/);
      await expect(page.locator(".msg.k-line", { has: card })).toHaveCount(1);
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

const mandateCopy = {
  en: {
    title: "Trading mode",
    full: "Full",
    ask: "Ask",
    askNow: "Now: Ask",
    fullNow: "Now: Full",
  },
  ar: {
    title: "التفويض",
    full: "وكّله",
    ask: "يستأذن",
    askNow: "الآن: يستأذن",
    fullNow: "الآن: وكّله",
  },
};

for (const locale of ["en", "ar"])
  test(`${locale}: the Mandate card shows the mode now and one button for the other mode`, async ({
    page,
    context,
  }) => {
    test.setTimeout(60000);
    const text = mandateCopy[locale];
    const state = await setup(context, locale);
    try {
      const seeded = seedCard({
        kind: "trading_mode",
        agent: state.agent.id,
        thread: state.thread.id,
      });
      const decisions = [];
      page.on("request", (request) => {
        if (request.method() === "POST" && request.url().includes("/api/owner-actions/"))
          decisions.push(request.postDataJSON());
      });
      await page.goto(`/app/${state.agent.id}`);
      const card = page.locator(`[data-owner-action="${seeded.id}"]`);
      await expect(card).toHaveAttribute("data-owner-action-status", "pending");
      await expect(card.locator(".oa-kind")).toHaveText(text.title);
      await expect(card).toContainText(text.askNow);
      // One button, for the other mode.
      await expect(card.locator("[data-owner-action-button]")).toHaveCount(1);
      if (locale === "ar") {
        await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
        await card.screenshot({ path: test.info().outputPath("owner-action-mandate-ar.png") });
      }
      const line = page.locator(".msg.k-oa", { has: card }).locator(".msg-line");
      const before = (await line.boundingBox()).width;
      await card.getByRole("button", { name: text.full, exact: true }).click();
      await expect(card).toHaveAttribute("data-owner-action-status", "confirmed");
      await expect(card).toContainText(text.fullNow);
      // A tapped Mandate card keeps its frame and its width (10.2.2, v38).
      expect((await line.boundingBox()).width).toBe(before);
      // Still the agent's switch: the button now shows Ask, and applies exactly Ask.
      await card.getByRole("button", { name: text.ask, exact: true }).click();
      await expect(card).toContainText(text.askNow);
      await expect(card.getByRole("button", { name: text.full, exact: true })).toBeVisible();
      expect(decisions).toEqual([
        { decision: "confirm", trading_mode: "full" },
        { decision: "confirm", trading_mode: "ask" },
      ]);
    } finally {
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
        kind: "settle_operation",
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
      // v38: the kind in the head, the broker's silence as the title; no timer.
      await expect(card.locator(".oa-kind")).toHaveText(text.settleKind);
      await expect(card.locator(".oa-title")).toHaveText(text.resolveTitle);
      await expect(card.locator(".oa-exp")).toHaveCount(0);
      await expect(card.locator("[data-owner-action-button]")).toHaveCount(3);
      await expect(card.locator('[data-owner-action-button="unknown"]')).toHaveText(text.unknown);
      // The hint keeps the true safety sentence: new risk on this market stays held while the
      // outcome is unknown, and exits stay allowed (admission; 6).
      await expect(card.locator(".oa-hint")).toContainText(text.hold);
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
      // Never folded (10.2.2): the answered card keeps its frame, in an unchanged wrapper.
      await expect(card.locator(".oa-kind")).toHaveText(text.settleKind);
      await expect(card.locator(".oa-title")).toHaveText(text.resolveTitle);
      await expect(card.getByText(state.data.symbol)).toBeVisible();
      await expect(page.locator(".msg.k-oa", { has: card })).toHaveCount(1);
      await expect(page.locator(".oa-line, .msg.k-line")).toHaveCount(0);
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

test("ar: an expired Settle card keeps its frame and asks again from inside it", async ({
  page,
  context,
}) => {
  const text = copy.ar;
  const state = await setup(context, "ar");
  try {
    const seeded = seedCard({
      kind: "settle_operation",
      account: state.account,
      symbol: state.data.symbol,
      agent: state.agent.id,
      thread: state.thread.id,
      expired: true,
    });
    await page.goto(`/app/${state.agent.id}`);
    const card = page.locator(`[data-owner-action="${seeded.id}"]`);
    await expect(card).toHaveAttribute("data-owner-action-status", "expired");
    // Never folded (10.2.2): its kind, title and operation, with «طلب جديد» inside the frame.
    await expect(card.locator(".oa-kind")).toHaveText(text.settleKind);
    await expect(card.locator(".oa-title")).toHaveText(text.resolveTitle);
    await expect(card.getByText(state.data.symbol)).toBeVisible();
    await expect(page.locator(".msg.k-oa", { has: card })).toHaveCount(1);
    const [renewed] = await Promise.all([
      page.waitForResponse((response) =>
        response.url().endsWith(`/api/owner-actions/${seeded.id}/renew`),
      ),
      card.locator(".oa-actions").getByRole("button", { name: text.renew, exact: true }).click(),
    ]);
    expect(renewed.status()).toBe(200);
    // «طلب جديد» asks again: a fresh card for the same operation waits; nothing is decided.
    const fresh = await renewed.json();
    expect(fresh.id).not.toBe(seeded.id);
    expect(fresh.kind).toBe("settle_operation");
    expect(fresh.status).toBe("pending");
    expect(fresh.facts.operation.operation_id).toBe(seeded.operation_id);
    // Once renewed, the old card shows the newer one, never «طلب جديد» again (which the
    // server would refuse).
    await page.reload();
    await expect(card).toHaveAttribute("data-owner-action-status", "expired");
    await expect(card.getByRole("button", { name: text.renew, exact: true })).toHaveCount(0);
    await expect(card.getByRole("button", { name: text.latest, exact: true })).toBeVisible();
    await expect(page.locator(`[data-owner-action="${fresh.id}"]`)).toHaveCount(1);
  } finally {
    await state.cleanup();
  }
});

test("ar: a broker card whose connection failed shows its failed end state inside the frame", async ({
  page,
  context,
}) => {
  const state = await setup(context, "ar");
  try {
    // A saved broker card whose provisioning failed (D3), as /owner-actions returns it.
    const card = {
      id: randomUUID(),
      kind: "secret",
      status: "confirmed",
      status_reason: null,
      superseded_by: null,
      source: "agent",
      agent_id: state.agent.id,
      thread_id: state.thread.id,
      run_id: null,
      timeline_seq: 1,
      facts: {
        several_accounts: false,
        secret: {
          label: "70000001 @ Exness-MT5Trial16",
          fields: [{ key: "PASSWORD", label: "كلمة مرور التداول", secret: true }],
          destination: "broker",
          agent_name: "Lonora",
          account: { login: "70000001", server: "Exness-MT5Trial16", platform: "mt5" },
        },
      },
      requires_passkey: false,
      result: { provisioning: "failed" },
      expires_at: null,
      decided_at: new Date().toISOString(),
      decided_via: "owner",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    await page.route("**/api/owner-actions?*", (route) => route.fulfill({ json: [card] }));
    await page.goto(`/app/${state.agent.id}`);
    const frame = page.locator(`[data-owner-action="${card.id}"]`);
    await expect(frame).toHaveAttribute("data-owner-action-kind", "secret");
    // Never folded, and its end state is the failure in the neutral tint, never «Done».
    await expect(page.locator(".oa-line")).toHaveCount(0);
    const done = frame.locator(".oa-done");
    await expect(done).toHaveText("تعذّر الربط. أوضحت لونورا السبب في المحادثة.");
    await expect(done).toHaveClass(/\bbad\b/);
    await expect(done).toHaveAttribute("data-owner-action-failed", "true");
  } finally {
    await state.cleanup();
  }
});
