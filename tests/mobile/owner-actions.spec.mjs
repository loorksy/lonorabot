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
                session.add(TradingJournalRow(operation_id=operation,owner_id=f.owner,account_id=data['account'],request_hash='ui-fixture',request={'account_id':data['account'],'action':'buy','symbol':data['symbol'],'volume':'0.10'},status='ambiguous',execution_mode='live',result={'status':'ambiguous','code':'broker_timeout','details':{'send_state':'sent','execution':{'agent_id':data['agent'],'send_authorized':True}}},submitted_at=utcnow(),updated_at=utcnow()))
                await session.flush()
                fields['operation_id']=operation
            proposal=OwnerActionProposal(**fields)
            if data['kind']=='grant_authority':
                from lonora_contracts.owner_actions import DailyLossDraft,GrantDraft
                from lonora_db.owner_actions import ALL_ACTIONS
                draft=GrantDraft(agent_id=data['agent'],account_id=data['account'],symbol_scope='selected',symbols=[data['symbol']],actions=list(ALL_ACTIONS),daily_loss=DailyLossDraft(amount='300.00',currency='USD',basis='suggested',percent='3',equity='10000'))
                if data.get('delegation')=='full':
                    # Preselected because the owner's own message asked for full delegation.
                    draft=draft.with_delegation('full')
                row,_=await propose(session,f.owner,proposal,card_id=str(uuid4()),agent_id=data['agent'],thread_id=data['thread'],run_id=None,grant=draft)
            elif data['kind']=='resume_trading':
                # As an agent proposes it when the owner asks to resume.
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

const copy = {
  ar: {
    resume: "استئناف التداول",
    resumed: "استؤنف التداول.",
    resolveTitle: "الوسيط لم يؤكد هذه الصفقة",
    executed: "نُفذت",
    unknown: "غير معروفة — ارفع التعليق",
    recorded: "سُجّل: نُفذت (تصريحك، لا تأكيد من الوسيط).",
    lift: "رفع الإيقاف",
    noPauses: "لا توجد إيقافات",
    grantTitle: "يتداول بنفسه",
    authorize: "التفويض بمفتاح المرور",
    notNow: "ليس الآن",
    dismissed: "تم التجاهل. لم يتغير شيء.",
  },
  en: {
    resume: "Resume trading",
    resumed: "Trading resumed.",
    resolveTitle: "The broker did not confirm this trade",
    executed: "It executed",
    unknown: "Unknown: release the hold",
    recorded: "Recorded: it executed (your statement, not broker confirmation).",
    lift: "Lift pause",
    noPauses: "No pauses",
    grantTitle: "trade on its own",
    authorize: "Authorize with passkey",
    notNow: "Not now",
    dismissed: "Dismissed. Nothing changed.",
  },
};

for (const locale of ["ar", "en"])
  test(`Expo ${locale}: owner action cards in the thread act with one tap`, async ({
    page,
    context,
  }) => {
    test.setTimeout(90000);
    const text = copy[locale];
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
    const headers = {
      "X-CSRF-Token": data.cookies.find((row) => row.name === "lonora_csrf").value,
    };
    const original = await (await context.request.get("/api/trading/controls")).json();
    const created = await context.request.post("/api/agents", {
      headers,
      data: {
        name: `Native cards ${randomUUID().slice(0, 6)}`,
        trading_account_id: data.account,
        trading_symbol: data.symbol,
      },
    });
    expect(created.status()).toBe(201);
    const agent = await created.json();
    const thread = await (
      await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
    ).json();
    let pause;
    try {
      for (const enabled of [true, false])
        await context.request.put("/api/trading/controls", {
          headers,
          data: { enabled, emergency_stop: false },
        });
      const resume = seedCard({ kind: "resume_trading", agent: agent.id, thread: thread.id });
      const uncertain = seedCard({
        kind: "resolve_operation",
        account: data.account,
        symbol: data.symbol,
        agent: agent.id,
        thread: thread.id,
      });
      await page.goto(`/thread?id=${thread.id}`);
      const resumeCard = page.getByTestId(`owner-action-${resume.id}`);
      await expect(resumeCard.getByText(text.resume).first()).toBeVisible();
      const resolveCard = page.getByTestId(`owner-action-${uncertain.id}`);
      await expect(resolveCard.getByText(text.resolveTitle, { exact: true })).toBeVisible();
      await expect(resolveCard.getByText(data.symbol, { exact: false }).first()).toBeVisible();
      await expect(
        resolveCard.getByRole("button", { name: text.unknown, exact: true }),
      ).toBeVisible();
      if (locale === "ar")
        await resolveCard.screenshot({
          path: test.info().outputPath("owner-action-resolve-native-ar.png"),
        });
      // A grant card renders the same shared spec: what is signed, the owner's switches
      // and one passkey tap; "Not now" changes nothing.
      const grant = seedCard({
        kind: "grant_authority",
        account: data.account,
        symbol: data.symbol,
        agent: agent.id,
        thread: thread.id,
      });
      await page.reload();
      const grantCard = page.getByTestId(`owner-action-${grant.id}`);
      await expect(grantCard.getByText(text.grantTitle, { exact: false }).first()).toBeVisible();
      await expect(grantCard.getByText(data.symbol, { exact: false }).first()).toBeVisible();
      for (const option of ["manual", "no_money_limit", "resume"])
        await expect(grantCard.getByTestId(`owner-action-option-${option}`)).toBeVisible();
      await expect(
        grantCard.getByRole("button", { name: text.authorize, exact: true }),
      ).toBeVisible();
      if (locale === "ar")
        await grantCard.screenshot({
          path: test.info().outputPath("owner-action-grant-native-ar.png"),
        });
      await grantCard.getByRole("button", { name: text.notNow, exact: true }).click();
      await expect(grantCard.getByText(text.dismissed, { exact: true })).toBeVisible();
      const level = await (await context.request.get(`/api/agents/${agent.id}/permissions`)).json();
      expect(level.effective_level).toBe("supervised");
      await resumeCard.getByRole("button", { name: text.resume, exact: true }).click();
      await expect(resumeCard.getByText(text.resumed, { exact: true })).toBeVisible();
      expect(await (await context.request.get("/api/trading/controls")).json()).toEqual({
        enabled: true,
        emergency_stop: false,
      });
      await resolveCard.getByRole("button", { name: text.executed, exact: true }).click();
      await expect(resolveCard.getByText(text.recorded, { exact: true })).toBeVisible();
      const journal = await (
        await context.request.get(`/api/trading/journal?account_id=${data.account}`)
      ).json();
      const row = journal.find((item) => item.operation_id === uncertain.operation_id);
      expect(row.status).toBe("resolved");
      expect(row.result.details.resolution.outcome).toBe("executed");
      // The header sheet lifts a pause with one tap too.
      const made = await context.request.post("/api/trading/restrictions", {
        headers,
        data: { account_id: data.account, action_class: "no_new_entries" },
      });
      expect(made.status()).toBe(201);
      pause = (await made.json()).id;
      await page.reload();
      await page.getByTestId("safety-pill").click();
      const sheet = page.getByTestId("safety-sheet");
      await sheet.getByRole("button", { name: text.lift, exact: true }).click();
      await expect(sheet.getByText(text.noPauses, { exact: true })).toBeVisible();
      pause = undefined;
    } finally {
      if (pause)
        await context.request.post(`/api/trading/restrictions/${pause}/revoke`, {
          headers,
          data: { reason: "" },
        });
      await context.request.put("/api/trading/controls", { headers, data: original });
      simulation({ ...data, action: "cleanup" });
    }
  });

const delegation = {
  ar: {
    custom: "مخصص",
    full: "تفويض كامل",
    customMeaning: "مخصص: الأسواق والعمليات والمدة الظاهرة هنا فقط",
    fullMeaning: "تفويض كامل: كل أزواج هذا الحساب وكل العمليات",
    fullLimits:
      "تبقى الحدود المالية التي ضبطتها لهذا الحساب في مكان آخر نافذة؛ وإزالتها خطوة منفصلة بمفتاح المرور.",
    markets: "الأسواق: كل أزواج هذا الحساب",
    ownIncluded: "يشمل المراكز التي فتحتها بنفسك",
    changed: "تغيّرت هذه البطاقة من شاشة أخرى، وهي تعرض الآن الاختيار الحالي؛ راجعها ثم اضغط مجددًا.",
  },
  en: {
    custom: "Custom",
    full: "Full delegation",
    customMeaning: "Custom: only the markets, actions and time shown here",
    fullMeaning: "Full delegation: every pair on this account and every action",
    fullLimits:
      "Money limits you set on this account elsewhere stay in force; removing them is a separate step with your passkey.",
    markets: "Markets: All pairs on this account",
    ownIncluded: "Positions you opened yourself are included",
    changed:
      "This card changed on another screen. It now shows the current choice; check it and tap again.",
  },
};

for (const locale of ["ar", "en"])
  test(`Expo ${locale}: Custom or Full delegation is one choice in the grant card's list`, async ({
    page,
    context,
  }) => {
    test.setTimeout(90000);
    const text = { ...copy[locale], ...delegation[locale] };
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
    const headers = {
      "X-CSRF-Token": data.cookies.find((row) => row.name === "lonora_csrf").value,
    };
    // A flexible agent: its grant may cover every pair on the account.
    const created = await context.request.post("/api/agents", {
      headers,
      data: {
        name: `Native full ${randomUUID().slice(0, 6)}`,
        scope_mode: "flexible",
        trading_account_id: data.account,
        trading_symbol: data.symbol,
      },
    });
    expect(created.status()).toBe(201);
    const agent = await created.json();
    const thread = await (
      await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
    ).json();
    const stored = async (id) =>
      (await (await context.request.get(`/api/owner-actions?thread_id=${thread.id}`)).json()).find(
        (row) => row.id === id,
      );
    try {
      const seeded = seedCard({
        kind: "grant_authority",
        account: data.account,
        symbol: data.symbol,
        agent: agent.id,
        thread: thread.id,
      });
      await page.goto(`/thread?id=${thread.id}`);
      const card = page.getByTestId(`owner-action-${seeded.id}`);
      const custom = card.getByTestId("owner-action-choice-custom");
      const full = card.getByTestId("owner-action-choice-full");
      // One choice inside the card's own list, Custom selected, the same words as Web.
      await expect(custom).toHaveAttribute("aria-checked", "true");
      await expect(full).toHaveAttribute("aria-checked", "false");
      await expect(custom).toContainText(text.custom);
      await expect(full).toContainText(text.full);
      await expect(card.getByTestId("owner-action-choice-detail-custom")).toContainText(
        text.customMeaning,
      );
      await expect(card.getByTestId("owner-action-option-manual")).toBeVisible();
      await full.click();
      await expect(full).toHaveAttribute("aria-checked", "true");
      const detail = card.getByTestId("owner-action-choice-detail-full");
      await expect(detail).toContainText(text.fullMeaning);
      await expect(detail).toContainText(text.fullLimits);
      await expect(card.getByTestId("owner-action-option-manual")).toHaveCount(0);
      await expect(card.getByTestId("owner-action-option-no_money_limit")).toHaveCount(0);
      await expect(card.getByText(text.ownIncluded, { exact: true })).toBeVisible();
      await expect(card.getByText(text.markets, { exact: true })).toBeVisible();
      await expect(card.getByRole("button", { name: text.authorize, exact: true })).toBeVisible();
      // The choice is stored in the card's draft on the server.
      expect((await stored(seeded.id)).facts.grant.delegation).toBe("full");
      if (locale === "ar")
        await card.screenshot({ path: test.info().outputPath("owner-action-full-native-ar.png") });
      await custom.click();
      await expect(custom).toHaveAttribute("aria-checked", "true");
      await expect(card.getByTestId("owner-action-option-manual")).toBeVisible();
      expect((await stored(seeded.id)).facts.grant.delegation).toBe("custom");
      await card.getByRole("button", { name: text.notNow, exact: true }).click();
      await expect(card.getByText(text.dismissed, { exact: true })).toBeVisible();
      const level = await (await context.request.get(`/api/agents/${agent.id}/permissions`)).json();
      expect(level.effective_level).toBe("supervised");
      // A card Lonora raised from the owner's own words opens on Full; the owner chooses.
      const preselected = seedCard({
        kind: "grant_authority",
        account: data.account,
        symbol: data.symbol,
        agent: agent.id,
        thread: thread.id,
        delegation: "full",
      });
      await page.reload();
      const second = page.getByTestId(`owner-action-${preselected.id}`);
      await expect(second.getByTestId("owner-action-choice-full")).toHaveAttribute(
        "aria-checked",
        "true",
      );
      await expect(second.getByTestId("owner-action-choice-detail-full")).toContainText(
        text.fullLimits,
      );
      await second.getByRole("button", { name: text.notNow, exact: true }).click();
      await expect(second.getByText(text.dismissed, { exact: true })).toBeVisible();
    } finally {
      await context.request.delete(`/api/agents/${agent.id}`, { headers });
      simulation({ ...data, action: "cleanup" });
    }
  });

for (const locale of ["ar", "en"])
  test(`Expo ${locale}: a grant card changed on another screen is read again and never signs the other choice`, async ({
    page,
    context,
  }) => {
    test.setTimeout(90000);
    const text = { ...copy[locale], ...delegation[locale] };
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
    const headers = {
      "X-CSRF-Token": data.cookies.find((row) => row.name === "lonora_csrf").value,
    };
    const created = await context.request.post("/api/agents", {
      headers,
      data: {
        name: `Native stale ${randomUUID().slice(0, 6)}`,
        scope_mode: "flexible",
        trading_account_id: data.account,
        trading_symbol: data.symbol,
      },
    });
    expect(created.status()).toBe(201);
    const agent = await created.json();
    const thread = await (
      await context.request.post(`/api/agents/${agent.id}/conversation`, { headers, data: {} })
    ).json();
    const cards = async () =>
      (await context.request.get(`/api/owner-actions?thread_id=${thread.id}`)).json();
    try {
      const seeded = seedCard({
        kind: "grant_authority",
        account: data.account,
        symbol: data.symbol,
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
      await page.goto(`/thread?id=${thread.id}`);
      const card = page.getByTestId(`owner-action-${seeded.id}`);
      const custom = card.getByTestId("owner-action-choice-custom");
      const full = card.getByTestId("owner-action-choice-full");
      await expect(custom).toHaveAttribute("aria-checked", "true");
      await expect(card.getByTestId("owner-action-option-manual")).toBeVisible();
      frozen = await cards();
      // The owner picks Full on another screen; this one still shows Custom.
      const other = await context.request.post(`/api/owner-actions/${seeded.id}/decision`, {
        headers,
        data: { decision: "choose", delegation: "full" },
      });
      expect(other.ok()).toBeTruthy();
      await expect(custom).toHaveAttribute("aria-checked", "true");
      await card.getByRole("button", { name: text.authorize, exact: true }).click();
      // Refused before any passkey prompt: the card is read again and shows Full now.
      await expect(card.getByText(text.changed, { exact: true })).toBeVisible();
      await expect(full).toHaveAttribute("aria-checked", "true");
      await expect(card.getByTestId("owner-action-choice-detail-full")).toContainText(
        text.fullMeaning,
      );
      await expect(card.getByTestId("owner-action-option-manual")).toHaveCount(0);
      await expect(card.getByText(text.markets, { exact: true })).toBeVisible();
      expect(challenges).toEqual([{ delegation: "custom", allow_manual_positions: false }]);
      // Nothing was prepared or signed.
      const stored = (await cards()).find((row) => row.id === seeded.id);
      expect(stored.status).toBe("pending");
      expect(stored.result).toEqual({});
      const level = await (await context.request.get(`/api/agents/${agent.id}/permissions`)).json();
      expect(level.effective_level).toBe("supervised");
      if (locale === "ar")
        await card.screenshot({
          path: test.info().outputPath("owner-action-changed-native-ar.png"),
        });
      await card.getByRole("button", { name: text.notNow, exact: true }).click();
      await expect(card.getByText(text.dismissed, { exact: true })).toBeVisible();
    } finally {
      await context.request.delete(`/api/agents/${agent.id}`, { headers });
      simulation({ ...data, action: "cleanup" });
    }
  });
