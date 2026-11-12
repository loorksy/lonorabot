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

// A news agent whose cards ask the owner to add a news feed (a Secret card for its
// address) and to trust another feed's site, as the tools raise them (no model involved).
function seedCards(data) {
  const script = `
import asyncio,json,sys
sys.path.insert(0,'tests')
from uuid import uuid4
from check_streaming import Fixture
from lonora_contracts.domain import AgentCreate
from lonora_db.agents import create_agent
from lonora_contracts.owner_actions import OwnerActionProposal
from lonora_db.capability_cards import source_payload, trust_subject
from lonora_db.owner_actions import propose, propose_capability
from lonora_db.schema import SkillRow
from lonora_db.threads import conversation_thread
async def main():
    data=json.load(sys.stdin)
    f=await Fixture().open()
    try:
        async with f.runtime.db.sessions() as session, session.begin():
            agent=await create_agent(session,f.owner,AgentCreate(name=data['agent'],scope_mode='flexible'))
            thread=await conversation_thread(session,f.owner,agent.id)
            credential,_=await propose(session,f.owner,OwnerActionProposal(kind='secret',target='news_feed',name=data['feed']),card_id=str(uuid4()),agent_id=agent.id,thread_id=thread.id,run_id=None)
            domain=data['domain']
            trust,_=await propose_capability(session,f.owner,'trust_source',trust_subject('feed_domain',domain),source_payload('feed_domain',domain),card_id=str(uuid4()),agent_id=agent.id,thread_id=thread.id,run_id=None)
            skill=data['skill']
            session.add(SkillRow(id=str(uuid4()),owner_id=f.owner,agent_id=agent.id,version=1,payload={'name':skill,'content':'---\\nname: '+skill+'\\ndescription: Short sourced notes.\\n---\\nUse cited evidence only.\\n','enabled':True,'manifest':{'id':skill,'version':'1.0.0','title':skill,'description':'Short sourced notes.','source':'installed','activation':{'mode':'explicit'}}}))
            print(json.dumps({'agent':agent.id,'thread':thread.id,'credential':credential.id,'trust':trust.id}))
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
    connectTitle: "إضافة موجز أخبار",
    url: "عنوان الموجز",
    connect: "ربط",
    connected: "تم الربط. لا يرى الوكلاء إلا أنه مُعدّ.",
    trustTitle: "الوثوق بهذا المصدر؟",
    trust: "ثقة",
    trusted: "صار موثوقًا.",
    title: "القدرات",
    remove: "إزالة",
    undo: "تراجع",
    undone: "تم التراجع",
    setUp: "إعداد التكاملات على الويب",
  },
  en: {
    connectTitle: "Add a news feed",
    url: "Feed URL",
    connect: "Connect",
    connected: "Connected. Agents see only that it is configured.",
    trustTitle: "Trust this source?",
    trust: "Trust",
    trusted: "Trusted.",
    title: "Capabilities",
    remove: "Remove",
    undo: "Undo",
    undone: "undone",
    setUp: "Set up integrations on the web",
  },
};

for (const locale of ["ar", "en"])
  test(`Expo ${locale}: a feed form and a trust card in the chat, then Capabilities`, async ({
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
    const site = `site-${suffix}.analyst.example`;
    const feed = `https://desk-${suffix}.news.example/rss`;
    const skill = `notes-${suffix}`;
    const seeded = seedCards({
      agent: `News ${suffix}`,
      domain: site,
      skill,
      feed: `Desk ${suffix}`,
    });
    try {
      await page.goto(`/thread?id=${seeded.thread}`);
      const card = page.getByTestId(`owner-action-${seeded.credential}`);
      await expect(card.getByText(text.connectTitle, { exact: true })).toBeVisible();
      // The feed's name came from chat; the owner types only its address.
      await expect(card).toContainText(`⁨Desk ${suffix}⁩`);
      await card.getByLabel(text.url, { exact: true }).fill(feed);
      if (locale === "ar")
        await card.screenshot({ path: test.info().outputPath("credential-native-ar.png") });
      await card.getByRole("button", { name: text.connect, exact: true }).click();
      await expect(card.getByText(text.connected, { exact: true })).toBeVisible();

      const trust = page.getByTestId(`owner-action-${seeded.trust}`);
      await expect(trust.getByText(text.trustTitle, { exact: true })).toBeVisible();
      await expect(trust).toContainText(`⁨${site}⁩`);
      await trust.getByRole("button", { name: text.trust, exact: true }).click();
      await expect(trust.getByText(text.trusted, { exact: true })).toBeVisible();

      await page.goto("/integrations");
      await expect(page.getByText(text.title, { exact: true }).first()).toBeVisible();
      const report = await (await context.request.get("/api/capabilities")).json();
      const added = report.integrations.find((item) => item.name === `Desk ${suffix}`);
      expect(added.type).toBe("news_feed");
      expect(added.domain).toBe(`desk-${suffix}.news.example`);
      const trusted = report.trusted_sources.find((item) => item.identifier === site);
      expect(trusted.added_via).toBe("owner_card");
      const row = page.getByTestId(`integration-${added.id}`);
      await expect(row).toContainText(`⁨Desk ${suffix}⁩`);
      if (locale === "ar")
        await page.screenshot({ path: test.info().outputPath("capabilities-native-ar.png") });
      await row.getByRole("button", { name: text.remove, exact: true }).click();
      await expect(row).toHaveCount(0);
      // The last feed of its site is gone: the site leaves the trusted list too.
      const after = await (await context.request.get("/api/capabilities")).json();
      expect(
        after.trusted_sources.some(
          (item) => item.identifier === `desk-${suffix}.news.example` && item.active,
        ),
      ).toBe(false);
      const written = after.skills.find((item) => item.skill_id === skill);
      const line = page.getByTestId(`capability-skill-${written.resource_id}`);
      await line.getByRole("button", { name: text.undo, exact: true }).click();
      await expect(line).toContainText(text.undone);
      await expect(line.getByRole("button", { name: text.undo, exact: true })).toHaveCount(0);
      await expect(page.getByRole("button", { name: text.setUp, exact: true })).toBeVisible();
    } finally {
      await context.request.delete(`/api/agents/${seeded.agent}`, { headers });
      simulation({ ...data, action: "cleanup" });
    }
  });

const review = {
  en: {
    review: "Review and trust",
    writes: "may change something (only with non-financial writes)",
    trust: "Trust",
    trustWrite: "Trust: non-financial writes",
  },
  ar: {
    review: "مراجعة ووثوق",
    writes: "قد تغيّر شيئًا (مع الكتابة غير المالية فقط)",
    trust: "ثقة",
    trustWrite: "ثقة: كتابة غير مالية",
  },
};

for (const locale of ["ar", "en"])
  test(`Expo ${locale}: a server whose tools are not trusted yet is reviewed and trusted here`, async ({
    page,
    context,
  }) => {
    const text = review[locale];
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
    // The saved server and its tools are scripted; the routes and their bodies are real.
    const server = {
      connection_id: "scripted-server",
      name: "X posts",
      enabled: true,
      credentials_configured: true,
      trusted_tier: null,
      trusted_tools: [],
      write_tools: [],
      blocked_tools: [],
      operator_declared: 0,
      trust_source_id: null,
      last_used_at: null,
    };
    await page.route("**/api/capabilities", async (route) => {
      const response = await route.fetch();
      const report = await response.json();
      await route.fulfill({ response, json: { ...report, mcp_servers: [server] } });
    });
    await page.route("**/api/trusted-sources/mcp/scripted-server/preview", (route) =>
      route.fulfill({
        json: {
          name: "X posts",
          tools: ["post_note", "search_posts"],
          writes: ["post_note"],
          blocked: ["send_usdc"],
          unsupported: 0,
          digest: "a".repeat(64),
          trusted_tier: null,
        },
      }),
    );
    const trusted = [];
    await page.route("**/api/trusted-sources/mcp/scripted-server", (route) => {
      trusted.push(JSON.parse(route.request().postData() ?? "{}"));
      return route.fulfill({ json: {} });
    });
    try {
      await page.goto("/integrations");
      const line = page.getByTestId("mcp-server-scripted-server");
      await line.getByRole("button", { name: text.review, exact: true }).click();
      const preview = page.getByTestId("mcp-preview");
      await expect(preview).toContainText("⁨search_posts⁩");
      await expect(preview).toContainText(`${text.writes}: ⁨post_note⁩`);
      await expect(preview).toContainText("⁨send_usdc⁩");
      // A server that offers a blocked money tool is trusted to read only: no write tier.
      await expect(preview.getByRole("button", { name: text.trustWrite, exact: true })).toHaveCount(
        0,
      );
      if (locale === "ar")
        await page.screenshot({ path: test.info().outputPath("mcp-review-native-ar.png") });
      await preview.getByRole("button", { name: text.trust, exact: true }).click();
      await expect(preview).toHaveCount(0);
      expect(trusted).toEqual([{ tier: "read", digest: "a".repeat(64) }]);
    } finally {
      simulation({ ...data, action: "cleanup" });
    }
  });
