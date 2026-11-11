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

// A news agent whose cards ask the owner: connect Brave web search (a secure form) and
// trust a news feed's site; as the tools raise them, with no model involved.
function seedCards(data) {
  const script = `
import asyncio,json,sys
sys.path.insert(0,'tests')
from uuid import uuid4
from check_streaming import Fixture
from lonora_contracts.domain import AgentCreate
from lonora_db.agents import create_agent
from lonora_db.capability_cards import credential_payload, source_payload, trust_subject
from lonora_db.owner_actions import propose_capability
from lonora_db.schema import SkillRow
from lonora_db.threads import conversation_thread
async def main():
    data=json.load(sys.stdin)
    f=await Fixture().open()
    try:
        async with f.runtime.db.sessions() as session, session.begin():
            agent=await create_agent(session,f.owner,AgentCreate(name=data['agent'],scope_mode='flexible'))
            thread=await conversation_thread(session,f.owner,agent.id)
            subject,payload=credential_payload('brave_search',None)
            credential,_=await propose_capability(session,f.owner,'connect_credential',subject,payload,card_id=str(uuid4()),agent_id=agent.id,thread_id=thread.id,run_id=None)
            domain=data['domain']
            trust,_=await propose_capability(session,f.owner,'trust_source',trust_subject('feed_domain',domain),source_payload('feed_domain',domain),card_id=str(uuid4()),agent_id=agent.id,thread_id=thread.id,run_id=None)
            skill=data['skill']
            session.add(SkillRow(id=str(uuid4()),owner_id=f.owner,agent_id=agent.id,version=1,payload={'name':skill,'content':'---\\nname: '+skill+'\\ndescription: Short sourced notes.\\n---\\nUse cited evidence only.\\n','enabled':True,'manifest':{'id':skill,'version':'1.0.0','title':skill,'description':'Short sourced notes.','source':'installed','activation':{'mode':'explicit'}}}))
            print(json.dumps({'agent':agent.id,'credential':credential.id,'trust':trust.id}))
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
  en: {
    connectTitle: "Connect Brave web search",
    connect: "Connect",
    connected: "Connected. Agents see only that it is configured.",
    trustTitle: "Trust this source?",
    trust: "Trust",
    trusted: "Trusted.",
    domains: "News domains",
    agentMade: "Created by an agent",
    disable: "Disable",
    enable: "Enable",
    restore: (version) => `Restore to version ${version}`,
    undo: "Undo",
    blockVersion: "Block this version",
  },
  ar: {
    connectTitle: "ربط بحث Brave",
    connect: "ربط",
    connected: "تم الربط. لا يرى الوكلاء إلا أنه مُعدّ.",
    trustTitle: "الوثوق بهذا المصدر؟",
    trust: "ثقة",
    trusted: "صار موثوقًا.",
    domains: "نطاقات الأخبار",
    agentMade: "أنشأها وكيل",
    disable: "تعطيل",
    enable: "تفعيل",
    restore: (version) => `الرجوع إلى الإصدار ${version}`,
    undo: "تراجع",
    blockVersion: "حظر هذا الإصدار",
  },
};

for (const locale of ["en", "ar"])
  test(`${locale}: a secure credential card and a trust card, then Capabilities shows them`, async ({
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
    const suffix = randomUUID().slice(0, 8);
    const secret = `brave-key-${randomUUID()}`;
    const domain = `feeds-${suffix}.analyst.example`;
    const skill = `notes-${suffix}`;
    const seeded = seedCards({ agent: `News ${suffix}`, domain, skill });
    const posted = [];
    page.on("request", (request) => {
      if (request.method() === "POST" && request.url().includes("/api/"))
        posted.push({ url: new URL(request.url()).pathname, body: request.postData() ?? "" });
    });
    const created = [];
    try {
      await page.goto(`/app/${seeded.agent}`);
      const card = page.locator(`[data-owner-action="${seeded.credential}"]`);
      await expect(card).toHaveAttribute("data-owner-action-kind", "connect_credential");
      await expect(card.locator(".oa-kind")).toHaveText(text.connectTitle);
      const key = card.locator('input[name="secret"]');
      await expect(key).toHaveAttribute("type", "password");
      await expect(key).toHaveAttribute("dir", "ltr");
      if (locale === "ar") {
        await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
        await card.screenshot({ path: test.info().outputPath("credential-card-ar.png") });
      }
      await key.fill(secret);
      await card.getByRole("button", { name: text.connect, exact: true }).click();
      await expect(card).toHaveAttribute("data-owner-action-status", "confirmed");
      await expect(card.getByRole("status")).toHaveText(text.connected);
      // The value went only to the secrets route, never to the card or the chat.
      const carrying = posted.filter((item) => item.body.includes(secret)).map((item) => item.url);
      expect(carrying).toEqual(["/api/integrations/secrets"]);
      const decision = posted.find((item) => item.url.endsWith("/decision"));
      expect(JSON.parse(decision.body).connected.resource).toBe("integration");
      created.push(JSON.parse(decision.body).connected.id);

      const trust = page.locator(`[data-owner-action="${seeded.trust}"]`);
      await expect(trust.locator(".oa-kind")).toHaveText(text.trustTitle);
      await expect(trust).toContainText(`⁨${domain}⁩`);
      await trust.getByRole("button", { name: text.trust, exact: true }).click();
      await expect(trust).toHaveAttribute("data-owner-action-status", "confirmed");
      await expect(trust.getByRole("status")).toHaveText(text.trusted);

      // «التكاملات» (phase 5): the trusted news domain is in its sheet, and the skill its
      // agent wrote can be undone once from its row.
      await page.goto("/app/integrations");
      await page.getByRole("button", { name: new RegExp(text.domains) }).click();
      await expect(page.locator("dialog").getByText(domain, { exact: true })).toBeVisible();
      if (locale === "ar")
        await page.locator("dialog").screenshot({ path: test.info().outputPath("domains-ar.png") });
      await page.keyboard.press("Escape");
      const written = page.locator(".cap-skill").filter({ hasText: skill });
      await expect(written).toBeVisible();
      await expect(written.locator("small")).toContainText(text.agentMade);
      // Its row switches it off and on again.
      await written.getByRole("button", { name: text.disable, exact: true }).click();
      await expect(written).toHaveClass(/off/);
      await written.getByRole("button", { name: text.enable, exact: true }).click();
      await expect(written).not.toHaveClass(/off/);
      // A skill saved twice goes back to its earlier version from its row, and that is undone
      // from the toast.
      const plan = `plan-${suffix}`;
      const first = await (
        await context.request.post("/api/skills", {
          headers,
          data: { agent_id: seeded.agent, payload: { name: plan, content: "First." } },
        })
      ).json();
      await context.request.put(`/api/skills/${first.id}`, {
        headers,
        data: { version: first.version, payload: { name: plan, content: "Second." } },
      });
      const content = async () =>
        (await (await context.request.get(`/api/skills/${first.id}`)).json()).payload.content;
      await page.reload();
      const saved = page.locator(".cap-skill").filter({ hasText: plan });
      await saved.getByRole("button", { name: text.restore(1) }).click();
      await expect(saved.getByRole("button", { name: text.restore(2) })).toBeVisible();
      expect(await content()).toBe("First.");
      await page.locator("#toast").getByRole("button", { name: text.undo }).click();
      await expect(saved.getByRole("button", { name: text.restore(3) })).toBeVisible();
      expect(await content()).toBe("Second.");
      // Blocking denies the written skill's exact version: it stops loading, with no way back
      // from this row.
      await written.getByRole("button", { name: text.blockVersion }).click();
      await expect(written).toHaveClass(/off/);
      await expect(written.getByRole("button")).toHaveCount(0);
      const catalog = await (
        await context.request.get(`/api/agents/${seeded.agent}/skills/catalog/${skill}`)
      ).json();
      expect(catalog.code).toBe("skill_version_revoked");
      await expect(page.getByText(secret)).toHaveCount(0);
    } finally {
      for (const id of created)
        await context.request.delete(`/api/integrations/${id}`, { headers });
      await context.request.delete(`/api/agents/${seeded.agent}`, { headers });
    }
  });
