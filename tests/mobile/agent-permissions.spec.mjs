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

function signedAccounts() {
  // Standards-shaped proofs reach the actual production verifier. No direct
  // status changes or test-only authorization switches seed active authority.
  const source = `
import asyncio,json,sys
from datetime import timedelta
from uuid import uuid4
sys.path.insert(0,'tests')
from check_streaming import Fixture
from device_fixture import Device
from lonora_contracts.domain import utcnow
async def main():
 f=await Fixture().open()
 try:
  agent=next(row for row in await f.request('GET','/agents') if row['role']=='personal')
  thread=await f.conversation(agent)
  previous={row['id'] for row in await f.request('GET','/auth/devices')}
  device=await Device.enroll(f)
  device_id=next(row['id'] for row in await f.request('GET','/auth/devices') if row['id'] not in previous)
  accounts=[];grants=[]
  for index,symbol in enumerate(('EURUSD.exact','XAUUSD.exact')):
   connection=await f.request('POST','/trading/connections',{'provider':'simulation','account_id':'native-active-'+uuid4().hex,'enabled':True})
   account=connection['id'];accounts.append(account)
   await f.request('POST',f'/trading/connections/{account}/simulation',{'snapshot':{'currency':'USD','balance':'10000','instruments':[{'symbol':symbol,'digits':2,'tick_size':'0.01','volume_min':'0.01','volume_max':'10','volume_step':'0.01'}]}})
   body={'thread_id':thread['id'],'account_id':account,'management_mode':'full','symbol_scope':'selected','symbols':[symbol],'actions':['buy'] if index==0 else ['sell'],'maximum_order_volume':'0.11' if index==0 else '0.22','valid_until':(utcnow()+timedelta(hours=12)).isoformat() if index==0 else None,'allow_manual_positions':index==1}
   pending=await f.request('POST',f"/agents/{agent['id']}/account-authorities",body)
   challenge=await f.request('POST',f"/account-authorities/{pending['id']}/challenge",{})
   active=await f.request('POST','/account-authorities/verify',device.assertion(challenge,f.settings.allowed_origin))
   assert active['status']=='active';grants.append(active)
  state=await f.request('GET',f"/agents/{agent['id']}/permissions")
  draft={'account_id':accounts[0],'symbol_scope':'account','symbols':[],'actions':['modify_order'],'limits':{'maximum_order_volume':'0.77','maximum_symbol_volume':'','maximum_positions':'','maximum_pending_orders':'','maximum_actions':'','minimum_equity':''},'duration':'7d','allow_manual_positions':False}
  state=await f.request('PUT',f"/agents/{agent['id']}/permissions/customization",{'expected_revision':state['revision'],'customization':draft})
  assert len(state['active_authorities'])==2
  print(json.dumps({'agent':agent,'thread':thread,'accounts':accounts,'grants':grants,'draft':draft,'device_id':device_id,'cookies':[{'name':cookie.name,'value':cookie.value} for cookie in f.client.cookies.jar]}))
 finally:await f.close(cleanup=False)
asyncio.run(main())
`;
  return JSON.parse(execFileSync(".venv/bin/python", ["-c", source], { encoding: "utf8" }));
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
  const created = [];
  async function create() {
    const response = await context.request.post("/api/agents", {
      headers,
      data: {
        name: `Native permission ${randomUUID()}`,
        trading_account_id: data.account,
        trading_symbol: data.symbol,
      },
    });
    expect(response.status()).toBe(201);
    const agent = await response.json();
    created.push(agent.id);
    const conversation = await context.request.post(`/api/agents/${agent.id}/conversation`, {
      headers,
      data: {},
    });
    expect(conversation.ok()).toBeTruthy();
    return { agent, thread: await conversation.json() };
  }
  const selected = await create();
  return {
    ...selected,
    data,
    create,
    async open(page, value = selected) {
      await page.goto(`/thread?id=${value.thread.id}`);
      await expect(page.getByTestId("permission-selector-native")).toBeVisible();
    },
    async state(id = selected.agent.id) {
      const response = await context.request.get(`/api/agents/${id}/permissions`);
      expect(response.ok()).toBeTruthy();
      return response.json();
    },
    async cleanup() {
      for (const id of created.reverse())
        await context.request.delete(`/api/agents/${id}`, { headers });
      simulation({ ...data, action: "cleanup" });
    },
  };
}

const layouts = [
  { label: "standard mobile EN", locale: "en", width: 390, height: 844 },
  { label: "narrow mobile EN", locale: "en", width: 320, height: 640 },
  { label: "landscape mobile AR", locale: "ar", width: 844, height: 390 },
];

async function insideViewport(page, control) {
  await expect
    .poll(async () => {
      const box = await control.boundingBox();
      const viewport = page.viewportSize();
      return Boolean(box && viewport && box.y >= 0 && box.y + box.height <= viewport.height + 1);
    })
    .toBeTruthy();
}

for (const layout of layouts)
  test(`Expo ${layout.label}: permissions persist, preserve the composer and keep unsigned autonomy inactive`, async ({
    page,
    context,
  }) => {
    test.setTimeout(60000);
    await page.setViewportSize({ width: layout.width, height: layout.height });
    const state = await setup(context, layout.locale);
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    try {
      await state.open(page);
      expect((await state.state()).effective_level).toBe("analysis");
      const selector = page.getByTestId("permission-selector-native");
      const inputSurface = page.getByTestId("thread-composer-input-native");
      await expect(inputSurface.getByTestId("permission-selector-native")).toBeVisible();
      await expect(selector).toHaveText("");
      await expect(selector).toHaveAccessibleName(
        layout.locale === "ar" ? "صلاحيات الوكيل: تحليل فقط" : "Agent Permissions: Analysis Only",
      );
      await expect(selector.getByTestId("permission-icon-analysis-native")).toBeVisible();
      const attachBox = await page.getByTestId("thread-composer-attach-native").boundingBox();
      const selectorBox = await selector.boundingBox();
      expect(Math.abs(attachBox.y - selectorBox.y)).toBeLessThanOrEqual(1);
      expect(Math.abs(attachBox.height - selectorBox.height)).toBeLessThanOrEqual(1);
      const inlineGap =
        layout.locale === "ar"
          ? attachBox.x - (selectorBox.x + selectorBox.width)
          : selectorBox.x - (attachBox.x + attachBox.width);
      expect(inlineGap).toBeGreaterThanOrEqual(0);
      expect(inlineGap).toBeLessThanOrEqual(9);
      const composer = page.getByRole("textbox", {
        name: layout.locale === "ar" ? "اكتب رسالة…" : "Message…",
        exact: true,
      });
      const draft = "Keep this market question unsent — لا ترسلها";
      await composer.fill(draft);
      await page.getByTestId("permission-selector-native").click();
      const sheet = page.getByTestId("permission-sheet-native");
      for (const level of ["analysis", "supervised", "autonomous"]) {
        await expect(sheet.getByTestId(`permission-choice-${level}`)).toBeVisible();
        await expect(sheet.getByTestId(`permission-choice-icon-${level}`)).toBeVisible();
      }
      await expect(sheet.getByRole("switch")).toHaveCount(0);
      if (layout.height > layout.width) {
        for (const level of ["analysis", "supervised", "autonomous"])
          await insideViewport(page, sheet.getByTestId(`permission-choice-${level}`));
      } else {
        const last = sheet.getByTestId("permission-choice-autonomous");
        await last.scrollIntoViewIfNeeded();
        await insideViewport(page, last);
      }
      await expect(sheet.getByTestId("permission-advanced-native")).toHaveCount(0);
      if (layout.width === 390)
        await page.screenshot({ path: ".runtime/permission-qa-native-web-sheet.png" });
      await sheet.getByTestId("permission-choice-supervised").click();
      await expect.poll(async () => (await state.state()).effective_level).toBe("supervised");
      await expect(selector.getByTestId("permission-icon-supervised-native")).toBeVisible();
      await expect(selector).toHaveText("");
      await expect(composer).toHaveValue(draft);
      await page.reload();
      await expect(page.getByTestId("permission-selector-native")).toBeVisible();
      expect((await state.state()).effective_level).toBe("supervised");
      await composer.fill(draft);
      await page.getByTestId("permission-selector-native").click();
      await sheet.getByTestId("permission-choice-autonomous").click();
      const review = page.getByTestId("permission-review-native");
      await expect(review).toBeVisible();
      const pending = await state.state();
      expect(pending.requested_level).toBe("autonomous");
      expect(pending.effective_level).toBe("supervised");
      expect(pending.active_authorities).toEqual([]);
      expect(pending.pending_authority.status).toBe("pending");
      await review.getByTestId("permission-review-advanced-native").click();
      const editor = page.getByTestId("permission-editor-native");
      await expect(editor).toBeVisible();
      for (const group of ["scope", "operations", "limits", "duration"])
        await expect(editor.getByTestId(`permission-group-${group}`)).toHaveAttribute(
          "aria-expanded",
          "false",
        );
      await editor.getByTestId("permission-group-scope").click();
      await expect(editor).toContainText(state.data.symbol);
      await editor.getByTestId("permission-group-limits").click();
      const limit = editor.getByTestId("permission-limit-maximum_order_volume-native");
      await limit.fill("0.05");
      await editor.getByTestId("permission-group-limits").click();
      await editor.getByTestId("permission-group-limits").click();
      await expect(limit).toHaveValue("0.05");
      await editor.getByTestId("permission-review-continue-native").click();
      await expect(review).toContainText("0.05");
      expect((await state.state()).effective_level).toBe("supervised");
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
        ),
      ).toBeTruthy();
      expect(errors).toEqual([]);
    } finally {
      await state.cleanup();
    }
  });

for (const locale of ["en", "ar"])
  test(`Expo ${locale}: all active signed accounts remain readable independently of draft and pending changes`, async ({
    page,
    context,
  }) => {
    test.setTimeout(60000);
    const data = signedAccounts();
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
    const endpoint = `/api/agents/${data.agent.id}/permissions`;
    const read = async () => {
      const response = await context.request.get(endpoint);
      expect(response.ok()).toBeTruthy();
      return response.json();
    };
    const mutations = [];
    page.on("request", (request) => {
      if (
        ["POST", "PUT", "PATCH", "DELETE"].includes(request.method()) &&
        /account-authorities|\/permissions/.test(request.url())
      )
        mutations.push(`${request.method()} ${new URL(request.url()).pathname}`);
    });
    try {
      const before = await read();
      const journalBefore = await (await context.request.get("/api/trading/journal")).json();
      await page.goto(`/thread?id=${data.thread.id}`);
      await expect(page.getByTestId("permission-icon-autonomous-native")).toBeVisible();
      await expect(page.getByTestId("permission-selector-native")).toHaveText("");
      await page.getByTestId("permission-selector-native").click();
      await page.getByTestId("permission-choice-autonomous").click();
      const review = page.getByTestId("permission-review-native");
      await expect(review).toBeVisible();
      const exact = review.getByTestId("permission-exact-scope-native");
      for (const grant of data.grants) {
        await review.getByTestId(`permission-active-${grant.id}-native`).click();
        await expect(exact).toContainText(grant.envelope.symbols[0]);
        await expect(exact).toContainText(grant.envelope.maximum_order_volume);
        await expect(exact).not.toContainText("0.77");
        await expect(exact).toContainText(
          locale === "ar"
            ? grant.envelope.actions[0] === "buy"
              ? "شراء سوقي"
              : "بيع سوقي"
            : grant.envelope.actions[0] === "buy"
              ? "Market buy"
              : "Market sell",
        );
        await expect(exact).toContainText(
          locale === "ar"
            ? grant.envelope.allow_manual_positions
              ? "يشمل الصفقات المفتوحة خارج لونورا"
              : "لا يشمل الصفقات المفتوحة خارج لونورا"
            : grant.envelope.allow_manual_positions
              ? "Includes positions opened outside Lonora"
              : "Positions opened outside Lonora are excluded",
        );
        await expect(exact).toContainText(
          grant.valid_until ?? (locale === "ar" ? "حتى أوقفه" : "Until I Stop It"),
        );
        await expect(review.getByTestId("permission-sign-native")).toHaveCount(0);
        await expect(review).not.toContainText(
          locale === "ar" ? "انتهى التفويض" : "Authorization Expired",
        );
      }
      expect(mutations).toEqual([]);
      expect((await read()).active_authorities).toEqual(before.active_authorities);
      expect((await read()).customization).toEqual(data.draft);

      // A replacement stays pending while each older active account remains
      // visible. Reviewing those scopes must not create/verify another proposal.
      const pendingResponse = await context.request.post(
        `/api/agents/${data.agent.id}/account-authorities`,
        {
          headers,
          data: {
            thread_id: data.thread.id,
            account_id: data.accounts[1],
            management_mode: "full",
            symbol_scope: "selected",
            symbols: ["XAUUSD.exact"],
            actions: ["buy_limit"],
            maximum_order_volume: "0.33",
            allow_manual_positions: false,
          },
        },
      );
      expect(pendingResponse.status()).toBe(201);
      const pending = await pendingResponse.json();
      await page.reload();
      await page.getByTestId("permission-selector-native").click();
      await page.getByTestId("permission-choice-autonomous").click();
      await expect(review).toBeVisible();
      await expect(exact).toContainText("0.33");
      for (const grant of data.grants) {
        await review.getByTestId(`permission-active-${grant.id}-native`).click();
        await expect(exact).toContainText(grant.envelope.symbols[0]);
        await expect(exact).toContainText(grant.envelope.maximum_order_volume);
        await expect(review.getByTestId("permission-sign-native")).toHaveCount(0);
      }
      const after = await read();
      expect(after.pending_authority.id).toBe(pending.id);
      expect(after.active_authorities).toEqual(before.active_authorities);
      expect(after.customization).toEqual(data.draft);
      expect(mutations).toEqual([]);
      expect(await (await context.request.get("/api/trading/journal")).json()).toEqual(
        journalBefore,
      );
      await review.getByTestId(`permission-active-${data.grants[0].id}-native`).click();
      const revoked = page.waitForResponse(
        (response) =>
          response.url().endsWith(`/account-authorities/${data.grants[0].id}/revoke`) &&
          response.request().method() === "POST",
      );
      await review.getByTestId("permission-cancel-native").click();
      expect((await revoked).ok()).toBeTruthy();
      await expect
        .poll(async () => (await read()).active_authorities.map((grant) => grant.id))
        .toEqual([data.grants[1].id]);
      const reduced = await read();
      expect(reduced.effective_level).toBe("autonomous");
      expect(reduced.pending_authority.id).toBe(pending.id);
      expect(await (await context.request.get("/api/trading/journal")).json()).toEqual(
        journalBefore,
      );
    } finally {
      const current = await read();
      for (const grant of [...current.active_authorities, current.pending_authority].filter(
        Boolean,
      ))
        await context.request.post(`/api/account-authorities/${grant.id}/revoke`, {
          headers,
          data: {},
        });
      await context.request.delete(`/api/auth/devices/${data.device_id}`, { headers });
      for (const account of data.accounts)
        await context.request.delete(`/api/trading/connections/${account}`, { headers });
    }
  });
