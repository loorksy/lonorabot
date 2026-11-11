// biome-ignore-all lint/suspicious/noUndeclaredEnvVars: Explicit disposable Playwright fixtures.
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

async function setup(context, locale = "en", theme = "dark") {
  const data = simulation({ action: "init", empty: true });
  await context.addCookies(
    data.cookies.map((cookie) => ({
      ...cookie,
      url: test.info().project.use.baseURL,
      httpOnly: cookie.name === "lonora_session",
      sameSite: "Strict",
    })),
  );
  await context.addInitScript(
    ({ language, appearance }) => {
      if (!/^https?:$/.test(location.protocol)) return;
      localStorage.setItem("lonora.locale", language);
      localStorage.setItem("lonora.theme", JSON.stringify(appearance));
    },
    { language: locale, appearance: theme },
  );
  const headers = { "X-CSRF-Token": data.cookies.find((row) => row.name === "lonora_csrf").value };
  const created = [];
  async function agent() {
    const response = await context.request.post("/api/agents", {
      headers,
      data: {
        name: `Permission UX ${randomUUID()}`,
        trading_account_id: data.account,
        trading_symbol: data.symbol,
      },
    });
    expect(response.status()).toBe(201);
    const value = await response.json();
    created.push(value.id);
    // A new trading agent starts at Ask me (W15-3); these scenarios start from No trading,
    // set explicitly through the owner API.
    const permission = await (
      await context.request.get(`/api/agents/${value.id}/permissions`)
    ).json();
    expect(permission.effective_level).toBe("supervised");
    const reset = await context.request.put(`/api/agents/${value.id}/permissions`, {
      headers,
      data: { level: "analysis", expected_revision: permission.revision },
    });
    expect(reset.ok()).toBeTruthy();
    const conversation = await context.request.post(`/api/agents/${value.id}/conversation`, {
      headers,
      data: {},
    });
    expect(conversation.ok()).toBeTruthy();
    return { agent: value, thread: await conversation.json() };
  }
  const selected = await agent();
  return {
    data,
    headers,
    ...selected,
    createAgent: agent,
    async state(id = selected.agent.id) {
      const response = await context.request.get(`/api/agents/${id}/permissions`);
      expect(response.ok()).toBeTruthy();
      return response.json();
    },
    async open(page, value = selected) {
      await page.goto(`/app/${value.agent.id}?thread=${value.thread.id}`);
      await expect(page.getByTestId("permission-chip")).toBeVisible();
    },
    async cleanup() {
      for (const id of created.reverse())
        await context.request.delete(`/api/agents/${id}`, { headers });
      simulation({ ...data, action: "cleanup" });
    },
  };
}

/* The full permission flow (review, editor, signing) lives in the agent's info panel; the
   conversation's chip is the reference's ladder (see the layouts test). */
async function legacy(page) {
  if (await page.getByTestId("permission-selector").count()) return;
  await page.locator(".chat-head .head-avatar").click();
  await page
    .locator("details.tpl-profile-advanced > summary", {
      hasText: /^(Agent Permissions|صلاحيات الوكيل)$/,
    })
    .click();
  await expect(page.getByTestId("permission-selector")).toBeVisible();
}

async function choose(page, level) {
  await legacy(page);
  await page.getByTestId("permission-selector").click();
  await expect(page.getByTestId("permission-options")).toBeVisible();
  await page.getByTestId(`permission-option-${level}`).click();
}

async function editor(page) {
  await choose(page, "autonomous");
  const review = page.getByTestId("permission-review");
  await expect(review).toBeVisible();
  await review.getByTestId("permission-advanced").click();
  const surface = page.getByTestId("permission-editor");
  await expect(surface).toBeVisible();
  return surface;
}

async function noOverflow(page) {
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
    ),
  ).toBeTruthy();
}

function activeAuthorityFixture(data) {
  const script = `
import asyncio,json,sys
from datetime import timedelta
from uuid import uuid4
sys.path.insert(0,'tests')
from check_streaming import Fixture
from device_fixture import Device
from lonora_contracts.domain import utcnow
async def main():
    data=json.load(sys.stdin)
    f=await Fixture().open()
    try:
        agents=await f.request('GET','/agents')
        personal=next(row for row in agents if row['role']=='personal')
        path='/agents/'+personal['id']+'/permissions'
        current=await f.request('GET',path)
        await f.request('PUT',path,{'level':'analysis','expected_revision':current['revision']})
        thread=await f.conversation(personal)
        connection=await f.request('POST','/trading/connections',{'provider':'simulation','account_id':'grant-review-'+uuid4().hex,'enabled':True})
        other_symbol='REVIEW.second'
        await f.request('POST','/trading/connections/'+connection['id']+'/simulation',{'snapshot':{'currency':'EUR','balance':'10000','instruments':[{'symbol':other_symbol,'digits':2,'tick_size':'0.01','volume_min':'0.01','volume_max':'100','volume_step':'0.01'}]}})
        device=await Device.enroll(f)
        async def propose(account,symbol,actions,maximum):
            return await f.request('POST','/agents/'+personal['id']+'/account-authorities',{'thread_id':thread['id'],'account_id':account,'management_mode':'full','symbol_scope':'selected','symbols':[symbol],'actions':actions,'maximum_order_volume':maximum,'valid_until':(utcnow()+timedelta(hours=12)).isoformat()})
        async def sign(proposal):
            challenge=await f.request('POST','/account-authorities/'+proposal['id']+'/challenge',{})
            return await f.request('POST','/account-authorities/verify',device.assertion(challenge,f.settings.allowed_origin))
        first=await sign(await propose(data['account'],data['symbol'],['buy'],'0.05'))
        second=await sign(await propose(connection['id'],other_symbol,['sell','modify_position'],'0.17'))
        current=await f.request('GET',path)
        await f.request('PUT',path+'/customization',{'expected_revision':current['revision'],'customization':{'account_id':data['account'],'symbol_scope':'selected','symbols':[data['symbol']],'actions':['buy'],'limits':{'maximum_order_volume':'0.96'},'duration':'7d','allow_manual_positions':True}})
        pending=await propose(data['account'],data['symbol'],['close_position'],'0.23')
        print(json.dumps({'agent':personal,'thread':thread,'first':first,'second':second,'pending':pending,'extra_account':connection['id']}))
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

for (const locale of ["en", "ar"])
  test(`${locale}: every active account scope is reviewable without replacing its signed grant`, async ({
    page,
    context,
  }) => {
    test.setTimeout(60000);
    if (locale === "ar") await page.setViewportSize({ width: 390, height: 844 });
    const state = await setup(context, locale);
    const granted = activeAuthorityFixture(state.data);
    const writes = [];
    page.on("request", (request) => {
      if (
        request.method() === "POST" &&
        /\/account-authorities(?:[/?]|$)/.test(new URL(request.url()).pathname) &&
        !new URL(request.url()).pathname.endsWith("/revoke")
      )
        writes.push(request.url());
    });
    try {
      await state.open(page, granted);
      await legacy(page);
      const trigger = page.getByTestId("permission-selector");
      await expect(trigger.locator("[data-permission-icon]")).toHaveAttribute(
        "data-permission-icon",
        "autonomous",
      );
      await expect(trigger).toHaveAccessibleName(
        locale === "ar"
          ? "صلاحيات الوكيل: مستقل ضمن تفويضي الموقّع"
          : "Agent Permissions: On its own (signed)",
      );
      await choose(page, "autonomous");
      const review = page.getByTestId("permission-review");
      const authorities = review.getByTestId("permission-authorities");
      await expect(authorities.locator("button")).toHaveCount(3);
      await expect(review.locator(".permission-summary")).toContainText("0.23");
      await expect(review.getByTestId("permission-sign")).toBeVisible();
      for (const [grant, limit] of [
        [granted.first, "0.05"],
        [granted.second, "0.17"],
      ]) {
        await authorities.getByTestId(`permission-authority-${grant.id}`).click();
        await expect(authorities.getByTestId(`permission-authority-${grant.id}`)).toHaveAttribute(
          "aria-pressed",
          "true",
        );
        await expect(review.locator(".permission-summary")).toContainText(limit);
        await expect(review.locator(".permission-summary")).toContainText(
          grant.envelope.symbols[0],
        );
        await expect(review.locator(".permission-summary")).not.toContainText("0.96");
        await expect(review.getByTestId("permission-sign")).toHaveCount(0);
        await expect(review.getByTestId("permission-review-state")).toHaveText(
          locale === "ar" ? "تفويض موقّع ساري" : "Active signed authorization",
        );
      }
      await authorities.getByTestId(`permission-authority-${granted.first.id}`).click();
      const revoke = await context.request.post(
        `/api/account-authorities/${granted.first.id}/revoke`,
        {
          headers: state.headers,
          data: {},
        },
      );
      expect(revoke.ok()).toBeTruthy();
      await expect(authorities.getByTestId(`permission-authority-${granted.first.id}`)).toHaveCount(
        0,
      );
      await authorities.getByTestId(`permission-authority-${granted.second.id}`).click();
      await expect(review.locator(".permission-summary")).toContainText("0.17");
      await authorities.getByTestId(`permission-authority-${granted.pending.id}`).click();
      await expect(review.locator(".permission-summary")).toContainText("0.23");
      await expect(review.getByTestId("permission-sign")).toBeVisible();
      await noOverflow(page);
      expect(writes).toEqual([]);
      const current = await state.state(granted.agent.id);
      expect(current.active_authorities.map((row) => row.id)).toEqual([granted.second.id]);
      expect(current.customization.limits.maximum_order_volume).toBe("0.96");
    } finally {
      const current = await state.state(granted.agent.id);
      await context.request.put(`/api/agents/${granted.agent.id}/permissions`, {
        headers: state.headers,
        data: { level: "analysis", expected_revision: current.revision },
      });
      await context.request.delete(`/api/trading/connections/${granted.extra_account}`, {
        headers: state.headers,
      });
      await state.cleanup();
    }
  });

const layouts = [
  { label: "desktop EN dark", locale: "en", theme: "dark", width: 1440, height: 900 },
  { label: "mobile AR dark", locale: "ar", theme: "dark", width: 390, height: 844 },
  { label: "small mobile EN light", locale: "en", theme: "light", width: 320, height: 640 },
  { label: "landscape AR light", locale: "ar", theme: "light", width: 844, height: 390 },
  { label: "tablet EN dark", locale: "en", theme: "dark", width: 768, height: 1024 },
];

for (const layout of layouts) {
  test(`${layout.label}: the composer's permission chip keeps the draft and opens the mandate sheet`, async ({
    page,
    context,
  }) => {
    test.setTimeout(60000);
    await page.setViewportSize({ width: layout.width, height: layout.height });
    const state = await setup(context, layout.locale, layout.theme);
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    try {
      await state.open(page);
      expect((await state.state()).effective_level).toBe("analysis");
      const chip = page.getByTestId("permission-chip");
      await expect(chip).toHaveAttribute("data-level", "analysis");
      // The chip sits in the composer row right after +, as in the reference.
      expect(
        await chip.evaluate((element) =>
          element.previousElementSibling?.classList.contains("cbtn"),
        ),
      ).toBeTruthy();
      await expect(chip).toContainText(layout.locale === "ar" ? "دون تنفيذ" : "No execution");
      await noOverflow(page);
      const draft = "Keep my trading question unsent — احفظ المسودة";
      await page.locator(".composer textarea").fill(draft);
      await chip.click();
      const menu = page.locator(".pop.mode-pop");
      await expect(menu).toBeVisible();
      for (const level of ["analysis", "supervised", "autonomous"])
        await expect(menu.getByTestId(`mode-option-${level}`)).toBeVisible();
      await menu.getByTestId("mode-option-supervised").click();
      await expect.poll(async () => (await state.state()).effective_level).toBe("supervised");
      await expect(chip).toHaveAttribute("data-level", "supervised");
      await expect(page.locator(".composer textarea")).toHaveValue(draft);
      await page.reload();
      await expect(page.locator(".composer textarea")).toHaveValue(draft);
      await expect(page.getByTestId("permission-chip")).toHaveAttribute("data-level", "supervised");
      // «تنفيذ مفوَّض» opens the mandate sheet; nothing changes before a signature.
      await page.getByTestId("permission-chip").click();
      await page.locator(".pop.mode-pop").getByTestId("mode-option-autonomous").click();
      const sheet = page.locator("#dialog .act-grant_authority");
      await expect(sheet).toBeVisible();
      expect(await sheet.getByRole("radio").count()).toBeGreaterThanOrEqual(7);
      await noOverflow(page);
      expect((await state.state()).effective_level).toBe("supervised");
      expect(errors).toEqual([]);
    } finally {
      await state.cleanup();
    }
  });
}

test("personal agent explicitly chooses the account-wide scope and cannot activate it unsigned", async ({
  page,
  context,
}) => {
  test.setTimeout(60000);
  const state = await setup(context);
  let personal;
  try {
    const agents = await (await context.request.get("/api/agents")).json();
    personal = agents.find((agent) => agent.role === "personal");
    expect(personal).toBeTruthy();
    const current = await state.state(personal.id);
    const reset = await context.request.put(`/api/agents/${personal.id}/permissions`, {
      headers: state.headers,
      data: { level: "analysis", expected_revision: current.revision },
    });
    expect(reset.ok()).toBeTruthy();
    const thread = await (
      await context.request.post(`/api/agents/${personal.id}/conversation`, {
        headers: state.headers,
        data: {},
      })
    ).json();
    await state.open(page, { agent: personal, thread });
    await choose(page, "autonomous");
    await expect(page.getByTestId("permission-review")).toBeVisible();
    await page.getByTestId("permission-review").getByTestId("permission-advanced").click();
    const surface = page.getByTestId("permission-editor");
    await expect(surface).toBeVisible();
    await expect(surface.getByTestId("permission-review-continue")).toBeDisabled();
    await surface.getByTestId("permission-group-scope").locator("summary").click();
    await surface.getByTestId("permission-account").selectOption(state.data.account);
    await surface.getByTestId("permission-symbol-scope").selectOption("account");
    await surface.getByTestId("permission-review-continue").click();
    await expect(page.getByTestId("permission-review")).toBeVisible();
    const pending = await state.state(personal.id);
    expect(pending.effective_level).toBe("analysis");
    expect(pending.pending_authority.envelope.account_id).toBe(state.data.account);
    expect(pending.pending_authority.envelope.symbol_scope).toBe("account");
    expect(pending.pending_authority.envelope.symbols).toEqual([]);
    expect(pending.pending_authority.envelope.maximum_order_volume).toBeNull();
    expect(pending.pending_authority.envelope.valid_until).toBeNull();
  } finally {
    if (personal) {
      const current = await state.state(personal.id);
      await context.request.put(`/api/agents/${personal.id}/permissions`, {
        headers: state.headers,
        data: { level: "analysis", expected_revision: current.revision },
      });
    }
    await state.cleanup();
  }
});

test("customized scope signs through actual virtual WebAuthn, then downgrade revokes it and retains the draft", async ({
  page,
  context,
}) => {
  test.setTimeout(90000);
  const state = await setup(context);
  const originalControls = await (await context.request.get("/api/trading/controls")).json();
  const devices = await (await context.request.get("/api/auth/devices")).json();
  for (const device of devices)
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
    await state.open(page);
    const observer = await context.newPage();
    await state.open(observer);
    await expect(observer.getByTestId("permission-chip")).toHaveAttribute("data-level", "analysis");
    // WebAuthn requires the signing document to be the active tab. Keep the
    // second tab as an observer without moving the signing flow to the background.
    await page.bringToFront();
    const surface = await editor(page);
    await surface.getByTestId("permission-group-actions").locator("summary").click();
    const actions = [
      "buy",
      "sell",
      "buy_limit",
      "sell_limit",
      "buy_stop",
      "sell_stop",
      "close_position",
      "modify_position",
      "cancel_order",
      "modify_order",
    ];
    for (const action of actions) {
      await expect(surface.getByTestId(`permission-action-${action}`)).toHaveAttribute(
        "role",
        "switch",
      );
      await expect(surface.getByTestId(`permission-action-${action}`)).toBeChecked();
    }
    await surface.getByTestId("permission-deselect-all").click();
    await expect(surface.getByTestId("permission-review-continue")).toBeDisabled();
    await surface.getByTestId("permission-action-buy").check();
    await surface.getByTestId("permission-action-modify_position").check();
    await surface.getByTestId("permission-group-limits").locator("summary").click();
    const limits = {
      maximum_order_volume: "0.05",
      maximum_symbol_volume: "0.20",
      maximum_positions: "3",
      maximum_pending_orders: "0",
      maximum_actions: "7",
      minimum_equity: "9000",
    };
    for (const [field, value] of Object.entries(limits))
      await surface.getByTestId(`permission-limit-${field}`).fill(value);
    await surface.getByTestId("permission-limit-maximum_positions").fill("1.5");
    await expect(surface.getByTestId("permission-review-continue")).toBeDisabled();
    await surface.getByTestId("permission-limit-maximum_positions").fill("3");
    await surface.getByTestId("permission-group-duration").locator("summary").click();
    await surface.getByTestId("permission-duration").selectOption("12h");
    await surface.getByTestId("permission-manual").uncheck();
    await surface.getByTestId("permission-review-continue").click();
    const review = page.getByTestId("permission-review");
    await expect(review).toBeVisible();
    const pending = await state.state();
    const envelope = pending.pending_authority.envelope;
    expect(pending.effective_level).toBe("analysis");
    expect(envelope.management_mode).toBe("full");
    expect(envelope.symbols).toEqual([state.data.symbol]);
    expect(envelope.actions).toEqual(["buy", "modify_position"]);
    expect(envelope.maximum_order_volume).toBe("0.05");
    expect(envelope.maximum_symbol_volume).toBe("0.20");
    expect(envelope.maximum_positions).toBe(3);
    expect(envelope.maximum_pending_orders).toBe(0);
    expect(envelope.maximum_actions).toBe(7);
    expect(envelope.minimum_equity).toBe("9000");
    expect(envelope.allow_manual_positions).toBe(false);
    expect(Math.abs(Date.parse(envelope.valid_until) - Date.now() - 12 * 3600000)).toBeLessThan(
      60000,
    );
    await review.getByTestId("permission-sign").click();
    await review
      .getByLabel("Confirm account password", { exact: true })
      .fill("ci-only-owner-password");
    await review.getByRole("button", { name: "Register this device", exact: true }).click();
    await expect(review.getByLabel("Confirm account password", { exact: true })).toHaveCount(0);
    const verification = page.waitForResponse(
      (r) => r.url().endsWith("/account-authorities/verify") && r.request().method() === "POST",
    );
    await review.getByTestId("permission-sign").click();
    expect((await verification).ok()).toBeTruthy();
    await expect.poll(async () => (await state.state()).effective_level).toBe("autonomous");
    await expect(page.getByTestId("permission-chip")).toHaveAttribute("data-level", "autonomous");
    await expect(observer.getByTestId("permission-chip")).toHaveAttribute(
      "data-level",
      "autonomous",
    );
    await choose(page, "supervised");
    // Moving down says plainly that it revokes the signed grant, and asks once.
    const warning = page.getByTestId("permission-downgrade");
    await expect(warning).toContainText("revokes the signed grant for");
    await expect(warning).toContainText("going back needs a new signature");
    expect((await state.state()).effective_level).toBe("autonomous");
    await warning.getByTestId("permission-downgrade-confirm").click();
    await expect.poll(async () => (await state.state()).effective_level).toBe("supervised");
    const downgraded = await state.state();
    expect(downgraded.active_authorities).toEqual([]);
    expect(downgraded.pending_authority).toBeNull();
    expect(downgraded.customization.limits.maximum_order_volume).toBe("0.05");
    expect(downgraded.customization.duration).toBe("12h");
    await expect(observer.getByTestId("permission-chip")).toHaveAttribute(
      "data-level",
      "supervised",
    );
    await observer.close();
    expect(await (await context.request.get("/api/trading/controls")).json()).toEqual(
      originalControls,
    );
    const other = await state.createAgent();
    await state.open(page, other);
    await expect(page.getByTestId("permission-chip")).toHaveAttribute("data-level", "analysis");
    await state.open(page);
    await expect(page.getByTestId("permission-chip")).toHaveAttribute("data-level", "supervised");
    await choose(page, "autonomous");
    await expect(page.getByTestId("permission-review")).toBeVisible();
    await expect.poll(async () => (await state.state()).pending_authority?.status).toBe("pending");
    expect((await state.state()).effective_level).toBe("supervised");
  } finally {
    await state.cleanup();
  }
});
